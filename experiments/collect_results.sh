#!/bin/bash
# collect_results.sh - Collect experiment results from Kubernetes pods
# Usage: ./collect_results.sh <experiment_name> <run_number>
# Gathers FL timing logs, container logs, and resource data from pods.
set -e

EXPERIMENT_NAME="${1:?Usage: $0 <experiment_name> <run_number>}"
RUN_NUMBER="${2:?Usage: $0 <experiment_name> <run_number>}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT_DIR="$SCRIPT_DIR/results/$EXPERIMENT_NAME/run_$RUN_NUMBER"

mkdir -p "$OUTPUT_DIR/timing" "$OUTPUT_DIR/logs" "$OUTPUT_DIR/resources"

# Discover pods
IOT_PODS=($(kubectl get pods -l app=iot -o name | sed 's|pod/||'))
COMPUTE_PODS=($(kubectl get pods -l app=compute-node -o name | sed 's|pod/||'))

echo "Collecting results for $EXPERIMENT_NAME run $RUN_NUMBER..."

# Copy FL timing logs from IoT pods
for pod in "${IOT_PODS[@]}"; do
    echo "  Copying timing logs from $pod..."
    kubectl cp "$pod":/tmp/fl-timing/ "$OUTPUT_DIR/timing/${pod}/" 2>/dev/null || \
        echo "    WARNING: No timing data found on $pod"
done

# Capture IoT pod logs (main container)
for pod in "${IOT_PODS[@]}"; do
    echo "  Capturing logs from $pod..."
    kubectl logs "$pod" > "$OUTPUT_DIR/logs/${pod}_main.log" 2>/dev/null || true
done

# Capture compute node logs for key containers
CONTAINERS=(aggregation-confirmation-tp scheduling-request-tp status-update-tp)
for pod in "${COMPUTE_PODS[@]}"; do
    for container in "${CONTAINERS[@]}"; do
        kubectl logs "$pod" -c "$container" > "$OUTPUT_DIR/logs/${pod}_${container}.log" 2>/dev/null || true
    done
done

# Capture resource usage snapshot if metrics-server is available
if kubectl top pods > /dev/null 2>&1; then
    echo "  Capturing resource metrics..."
    kubectl top pods > "$OUTPUT_DIR/resources/pod_metrics.txt" 2>/dev/null || true
    kubectl top nodes > "$OUTPUT_DIR/resources/node_metrics.txt" 2>/dev/null || true
else
    echo "  Metrics server not available, skipping resource capture."
fi

# Print summary
FILE_COUNT=$(find "$OUTPUT_DIR" -type f | wc -l | tr -d ' ')
echo ""
echo "Collection complete: $FILE_COUNT files saved to $OUTPUT_DIR/"
ls -R "$OUTPUT_DIR/" | head -30
