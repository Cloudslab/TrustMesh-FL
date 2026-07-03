#!/bin/bash
# run_campaign.sh - Sequential TrustMesh-FL experiment campaign
#
# Usage: ./run_campaign.sh [config-name ...]
#   With no args, runs the full paper matrix in the order below.
#
# Ordering constraints encoded here:
#   - overhead-passthrough MUST run last: toggling SKIP_VALIDATION restarts the pbft
#     pods, and chain data is container-ephemeral, so the blockchain (including app and
#     workflow registrations) is reset. This script re-registers the FL application and
#     workflow after the toggle, and restores the validated configuration afterwards.
#   - All other configs share the running chain and registrations.
set -u
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"

DEFAULT_ORDER=(
    convergence-iid
    convergence-moderate
    convergence-mild
    convergence-extreme
    scale-4
    scale-6
    scale-8
    scale-10
    byzantine-noise-1
    byzantine-noise-2
    byzantine-flip-1
    byzantine-scale-1
    overhead-validated
    overhead-passthrough
)
CONFIGS=("${@:-${DEFAULT_ORDER[@]}}")

log() { echo "[campaign $(date +%H:%M:%S)] $*"; }

register_app_and_workflow() {
    log "Registering FL application and workflow (chain was reset)..."
    cd "$REPO_DIR"
    CONSOLE=$(kubectl get pods -o name | grep network-management-console | sed 's|pod/||')
    kubectl cp sample-apps/mnist-federated-learning/sample_jsons/app_requirements.json \
        "$CONSOLE":/app/app_requirements.json -c application-deployment-client

    timeout 1500 kubectl exec "$CONSOLE" -c application-deployment-client -- \
        python docker_image_client.py deploy_image federated-training-task.tar.gz app_requirements.json \
        > /tmp/campaign_app_deploy.log 2>&1
    APP_ID=$(grep -ioE "Application ID: [0-9a-f-]{36}" /tmp/campaign_app_deploy.log | grep -oE "[0-9a-f-]{36}" | tail -1)
    if [ -z "$APP_ID" ]; then
        log "ERROR: app deployment failed (no APP_ID); see /tmp/campaign_app_deploy.log"
        return 1
    fi
    log "APP_ID=$APP_ID; waiting for on-chain commit..."

    p=$(kubectl get pods -o name | grep -oE "pbft-0-[a-z0-9-]+" | head -1)
    for i in $(seq 1 20); do
        FOUND=$(kubectl exec "$p" -c sawtooth-rest-api -- python3 -c "
import urllib.request, hashlib
addr = hashlib.sha512('docker-image'.encode()).hexdigest()[:6] + hashlib.sha512('$APP_ID'.encode()).hexdigest()[:64]
try:
    urllib.request.urlopen('http://localhost:8008/state/' + addr); print('YES')
except Exception: print('NO')
" 2>/dev/null)
        [ "$FOUND" = "YES" ] && break
        sleep 10
    done
    [ "$FOUND" = "YES" ] || { log "ERROR: app registration never committed"; return 1; }

    PLACEHOLDER=$(python3 -c "import json;d=json.load(open('sample-apps/mnist-federated-learning/federated_dependency_graph.json'));print(d['start'])")
    sed "s/$PLACEHOLDER/$APP_ID/g" sample-apps/mnist-federated-learning/federated_dependency_graph.json > /tmp/campaign_fl_graph.json
    kubectl cp /tmp/campaign_fl_graph.json "$CONSOLE":/app/federated_dependency_graph.json -c workflow-creation-client
    timeout 120 kubectl exec "$CONSOLE" -c workflow-creation-client -- \
        python workflow_creation_client.py federated_dependency_graph.json fl-experiment > /dev/null 2>&1

    for i in $(seq 1 15); do
        FOUND=$(kubectl exec "$p" -c sawtooth-rest-api -- python3 -c "
import urllib.request, hashlib
addr = hashlib.sha512('workflow-dependency'.encode()).hexdigest()[:6] + hashlib.sha512('fl-experiment'.encode()).hexdigest()[:64]
try:
    urllib.request.urlopen('http://localhost:8008/state/' + addr); print('YES')
except Exception: print('NO')
" 2>/dev/null)
        [ "$FOUND" = "YES" ] && break
        sleep 10
    done
    [ "$FOUND" = "YES" ] || { log "ERROR: workflow registration never committed"; return 1; }
    log "App + workflow registered and committed."
}

set_skip_validation() {
    local value="$1"
    log "Setting SKIP_VALIDATION=$value on pbft deployments (chain will reset)..."
    kubectl set env deployment/pbft-0 deployment/pbft-1 deployment/pbft-2 deployment/pbft-3 \
        -c aggregation-confirmation-tp SKIP_VALIDATION="$value"
    for d in pbft-0 pbft-1 pbft-2 pbft-3; do
        kubectl rollout status deployment/"$d" --timeout=300s
    done
    log "Waiting for chain to re-form and resource batches to flow (150s)..."
    sleep 150
    register_app_and_workflow || return 1
    log "Warming training containers with settling time (60s)..."
    sleep 60
}

FAILED=()
for cfg in "${CONFIGS[@]}"; do
    CONFIG_FILE="$SCRIPT_DIR/configs/$cfg.yaml"
    if [ ! -f "$CONFIG_FILE" ]; then
        log "SKIP: no such config $cfg"; continue
    fi

    if [ "$cfg" = "overhead-passthrough" ]; then
        set_skip_validation "true" || { log "FAILED to prepare passthrough env"; FAILED+=("$cfg"); continue; }
    fi

    log "======== Running $cfg ========"
    if ! "$SCRIPT_DIR/run_experiment.sh" "$CONFIG_FILE" > "/tmp/campaign_$cfg.log" 2>&1; then
        log "CONFIG FAILED: $cfg (see /tmp/campaign_$cfg.log)"
        FAILED+=("$cfg")
    else
        log "Completed $cfg"
    fi

    if [ "$cfg" = "overhead-passthrough" ]; then
        # Restore validated mode and leave the cluster in a usable, registered state.
        set_skip_validation "false" || log "WARNING: failed to restore validated mode"
    fi
done

log "Campaign finished. Failed configs: ${FAILED[*]:-none}"
