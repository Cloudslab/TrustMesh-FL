#!/bin/bash
# run_experiment.sh - TrustMesh-FL experiment runner
# Usage: ./run_experiment.sh <config.yaml>
# Launches federated learning experiments across IoT pods based on YAML config.
set -e

CONFIG_FILE="${1:?Usage: $0 <config.yaml>}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RESULTS_BASE="$SCRIPT_DIR/results"

# Simple YAML parser (works for flat key: value within sections)
parse_yaml() {
    local file="$1" key="$2"
    grep -E "^\s+${key}:" "$file" | head -1 | sed 's/.*: *//' | sed 's/ *#.*//' | tr -d '"' | tr -d "'"
}

# Parse config
EXPERIMENT_NAME=$(parse_yaml "$CONFIG_FILE" "name")
DESCRIPTION=$(parse_yaml "$CONFIG_FILE" "description")
RUNS=$(parse_yaml "$CONFIG_FILE" "runs")
IOT_NODES=$(parse_yaml "$CONFIG_FILE" "iot_nodes")
MAX_ROUNDS=$(parse_yaml "$CONFIG_FILE" "max_rounds")
NON_IID_ALPHA=$(parse_yaml "$CONFIG_FILE" "non_iid_alpha")
TOTAL_NODES_VAL=$(parse_yaml "$CONFIG_FILE" "total_nodes")
AGG_TIMEOUT=$(parse_yaml "$CONFIG_FILE" "aggregation_timeout")
MIN_NODES=$(parse_yaml "$CONFIG_FILE" "min_nodes_for_aggregation")
WORKFLOW_ID=$(parse_yaml "$CONFIG_FILE" "workflow_id")
BYZANTINE_ENABLED=$(parse_yaml "$CONFIG_FILE" "enabled")
BYZANTINE_COUNT=$(parse_yaml "$CONFIG_FILE" "byzantine_node_count")
ATTACK_MODE=$(parse_yaml "$CONFIG_FILE" "attack_mode")
SKIP_VALIDATION=$(parse_yaml "$CONFIG_FILE" "skip_validation")

echo "========================================"
echo "TrustMesh-FL Experiment Runner"
echo "========================================"
echo "Experiment: $EXPERIMENT_NAME"
echo "Description: $DESCRIPTION"
echo "Runs: $RUNS"
echo "IoT Nodes: $IOT_NODES"
echo "Rounds: $MAX_ROUNDS"
echo "Alpha: $NON_IID_ALPHA"
echo "Byzantine: $BYZANTINE_ENABLED (count=$BYZANTINE_COUNT, mode=$ATTACK_MODE)"
echo "Skip Validation: $SKIP_VALIDATION"
echo "========================================"

# Discover IoT pods (deployed with label name=iot-0, name=iot-1, ...)
IOT_PODS=($(kubectl get pods -o name | grep -E "^pod/iot-[0-9]" | sed 's|pod/||' | sort))
if [ ${#IOT_PODS[@]} -lt "$IOT_NODES" ]; then
    echo "ERROR: Found ${#IOT_PODS[@]} IoT pods but config expects $IOT_NODES. Aborting."
    echo "       (Empty/short discovery is what produced stray '_simulation.log' files before.)"
    exit 1
fi
echo "Discovered IoT pods: ${IOT_PODS[*]}"

# Discover compute node pods — pbft pods contain aggregation-confirmation-tp container
COMPUTE_PODS=($(kubectl get pods -o name | grep -E "^pod/pbft-[0-9]" | sed 's|pod/||' | sort))
echo "Discovered compute pods: ${COMPUTE_PODS[*]}"

# SKIP_VALIDATION requires updating the deployment (env on a running pod is immutable). (env on a running pod is immutable).
# This triggers a rolling restart of pbft pods before the experiment runs.
if [ "$SKIP_VALIDATION" = "true" ]; then
    echo "Setting SKIP_VALIDATION=true on pbft deployments (triggers rolling restart)..."
    for pod in "${COMPUTE_PODS[@]}"; do
        # Pod name is pbft-N-<hash>; deployment name is pbft-N
        deployment=$(echo "$pod" | grep -oE "^pbft-[0-9]+")
        kubectl set env deployment/"$deployment" -c aggregation-confirmation-tp SKIP_VALIDATION=true
    done
    echo "Waiting for pbft pods to restart..."
    for pod in "${COMPUTE_PODS[@]}"; do
        deployment=$(echo "$pod" | grep -oE "^pbft-[0-9]+")
        kubectl rollout status deployment/"$deployment" --timeout=120s
    done
fi

# Calculate which nodes are byzantine (highest indices)
NORMAL_COUNT=$(( IOT_NODES - BYZANTINE_COUNT ))

# Run loop
for run in $(seq 1 "$RUNS"); do
    echo ""
    echo "======== Run $run / $RUNS ========"
    RUN_DIR="$RESULTS_BASE/$EXPERIMENT_NAME/run_$run"
    mkdir -p "$RUN_DIR/logs"

    PIDS=()
    WF_ID="${WORKFLOW_ID}"

    # Clear stale FLTimer data on the IoT pods before launching. FLTimer appends to
    # /tmp/fl-timing/*.jsonl, so leftovers from a previous run in the same pod would
    # pollute this run's collected timing/accuracy data.
    for i in $(seq 0 $(( IOT_NODES - 1 ))); do
        pod="${IOT_PODS[$i]}"
        [ -n "$pod" ] && kubectl exec "$pod" -- rm -rf /tmp/fl-timing 2>/dev/null || true
    done

    # Launch FL simulation on each IoT node
    for i in $(seq 0 $(( IOT_NODES - 1 ))); do
        pod="${IOT_PODS[$i]}"
        if [ -z "$pod" ]; then
            echo "  WARNING: no pod at index $i; skipping (would have written '_simulation.log')"
            continue
        fi
        # Stable per-node filename from the node label (iot-N), NOT the full pod name.
        # The pod suffix changes every (re)deploy, so using it accumulated one stale file
        # per deploy in the same run dir. The label is stable, so reruns overwrite cleanly.
        node_label=$(echo "$pod" | grep -oE 'iot-[0-9]+')
        LOG_FILE="$RUN_DIR/logs/${node_label}_simulation.log"

        # Inter-round think-time: uniform(20,60)s for experiment campaigns (default in the
        # simulation is uniform(90,300)s). Keeps nodes aligned within the 180s collection
        # window and roughly halves campaign wall-clock; per-phase metrics are unaffected.
        # AGGREGATION_WAIT_TIMEOUT=360: successful aggregation broadcasts ~2min after
        # submission, so 6min is ample margin; bounds the cost of expected-failure rounds
        # (Byzantine rejections) which otherwise wait the full default 600s every round.
        ENV_VARS="TOTAL_NODES=$TOTAL_NODES_VAL NON_IID_ALPHA=$NON_IID_ALPHA AGGREGATION_TIMEOUT=$AGG_TIMEOUT MIN_NODES_FOR_AGGREGATION=$MIN_NODES INTER_ROUND_PAUSE_MIN=20 INTER_ROUND_PAUSE_MAX=60 AGGREGATION_WAIT_TIMEOUT=360"

        # Determine if this node is byzantine (highest indices)
        if [ "$BYZANTINE_ENABLED" = "true" ] && [ "$i" -ge "$NORMAL_COUNT" ]; then
            echo "  Launching BYZANTINE node $pod (mode=$ATTACK_MODE)..."
            kubectl exec "$pod" -- bash -c \
                "$ENV_VARS python mnist-federated-learning-simulation.py --workflow-id $WF_ID --max-rounds $MAX_ROUNDS --byzantine-mode $ATTACK_MODE" \
                > "$LOG_FILE" 2>&1 &
        else
            echo "  Launching normal node $pod..."
            kubectl exec "$pod" -- bash -c \
                "$ENV_VARS python mnist-federated-learning-simulation.py --workflow-id $WF_ID --max-rounds $MAX_ROUNDS" \
                > "$LOG_FILE" 2>&1 &
        fi
        PIDS+=($!)
    done

    # Wait for all background processes
    echo "  Waiting for all nodes to complete..."
    FAILED=0
    for pid in "${PIDS[@]}"; do
        if ! wait "$pid"; then
            echo "  WARNING: Process $pid exited with non-zero status"
            FAILED=$((FAILED + 1))
        fi
    done

    if [ "$FAILED" -gt 0 ]; then
        echo "  WARNING: $FAILED process(es) failed in run $run"
    else
        echo "  All nodes completed successfully."
    fi

    # Collect results
    echo "  Collecting results..."
    bash "$SCRIPT_DIR/collect_results.sh" "$EXPERIMENT_NAME" "$run"

    # Brief pause between runs
    if [ "$run" -lt "$RUNS" ]; then
        echo "  Pausing 10 seconds before next run..."
        sleep 10
    fi
done

echo ""
echo "========================================"
echo "Experiment '$EXPERIMENT_NAME' complete."
echo "Results saved to: $RESULTS_BASE/$EXPERIMENT_NAME/"
echo "Total runs: $RUNS"
echo "========================================"
