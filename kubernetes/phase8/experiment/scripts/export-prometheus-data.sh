#!/bin/bash
#
# Export Prometheus data for experiment analysis
#

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

EXPERIMENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESULTS_DIR="$EXPERIMENT_DIR/results"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Prometheus configuration
PROMETHEUS_HOST="localhost"
PROMETHEUS_PORT="9090"

echo -e "${GREEN}Exporting Prometheus data for experiment analysis...${NC}"
echo ""

# Check if port-forward is needed
if ! nc -z $PROMETHEUS_HOST $PROMETHEUS_PORT 2>/dev/null; then
    echo "Starting port-forward to Prometheus..."
    kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
    PF_PID=$!
    echo "Port-forward PID: $PF_PID"
    sleep 5
else
    PF_PID=""
    echo "Using existing Prometheus connection on port 9090"
fi

# Create results directory
mkdir -p "$RESULTS_DIR"

# Query time range (last 24 hours)
END_TIME=$(date +%s)
START_TIME=$((END_TIME - 86400))

echo "Query range: $(date -d @$START_TIME) to $(date -d @$END_TIME)"
echo ""

# Export Reactive HPA data
echo "Exporting Reactive HPA data..."
REACTIVE_FILE="$RESULTS_DIR/reactive_data_$TIMESTAMP.json"

curl -s "http://$PROMETHEUS_HOST:$PROMETHEUS_PORT/api/v1/query_range" \
  --data-urlencode "query=node_pressure_memory_waiting{namespace=\"experiment-reactive\"}" \
  --data-urlencode "start=$START_TIME" \
  --data-urlencode "end=$END_TIME" \
  --data-urlencode "step=20s" \
  > "$REACTIVE_FILE.tmp"

# Get replica count over time
curl -s "http://$PROMETHEUS_HOST:$PROMETHEUS_PORT/api/v1/query_range" \
  --data-urlencode "query=kube_statefulset_replicas{namespace=\"experiment-reactive\",statefulset=\"workload-reactive\"}" \
  --data-urlencode "start=$START_TIME" \
  --data-urlencode "end=$END_TIME" \
  --data-urlencode "step=60s" \
  > "$REACTIVE_FILE.replicas.tmp"

# Get HPA events
kubectl get events -n experiment-reactive --sort-by='.lastTimestamp' -o json > "$REACTIVE_FILE.events.tmp"

echo -e "${GREEN}✅ Reactive data exported${NC}"

# Export Predictive HPA data
echo "Exporting Predictive HPA data..."
PREDICTIVE_FILE="$RESULTS_DIR/predictive_data_$TIMESTAMP.json"

curl -s "http://$PROMETHEUS_HOST:$PROMETHEUS_PORT/api/v1/query_range" \
  --data-urlencode "query=predicted_psi_confirmed{namespace=\"experiment-predictive\"}" \
  --data-urlencode "start=$START_TIME" \
  --data-urlencode "end=$END_TIME" \
  --data-urlencode "step=20s" \
  > "$PREDICTIVE_FILE.tmp"

# Get replica count over time
curl -s "http://$PROMETHEUS_HOST:$PROMETHEUS_PORT/api/v1/query_range" \
  --data-urlencode "query=kube_statefulset_replicas{namespace=\"experiment-predictive\",statefulset=\"workload-predictive\"}" \
  --data-urlencode "start=$START_TIME" \
  --data-urlencode "end=$END_TIME" \
  --data-urlencode "step=60s" \
  > "$PREDICTIVE_FILE.replicas.tmp"

# Get HPA events
kubectl get events -n experiment-predictive --sort-by='.lastTimestamp' -o json > "$PREDICTIVE_FILE.events.tmp"

# Get prediction service metrics
curl -s "http://$PROMETHEUS_HOST:$PROMETHEUS_PORT/api/v1/query_range" \
  --data-urlencode "query=predicted_psi_raw{namespace=\"experiment-predictive\"}" \
  --data-urlencode "start=$START_TIME" \
  --data-urlencode "end=$END_TIME" \
  --data-urlencode "step=20s" \
  > "$PREDICTIVE_FILE.raw.tmp"

echo -e "${GREEN}✅ Predictive data exported${NC}"

# Stop port-forward if we started it
if [ -n "$PF_PID" ]; then
    kill $PF_PID 2>/dev/null || true
fi

echo ""
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║                                                               ║"
echo "║              DATA EXPORT COMPLETE                             ║"
echo "║                                                               ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

echo "Exported files:"
echo "  Reactive:"
ls -lh "$RESULTS_DIR"/reactive_data_$TIMESTAMP* | awk '{print "    " $9 " (" $5 ")"}'
echo "  Predictive:"
ls -lh "$RESULTS_DIR"/predictive_data_$TIMESTAMP* | awk '{print "    " $9 " (" $5 ")"}'
echo ""

echo "Next steps:"
echo "  1. Process exported data:"
echo "     python3 scripts/process-prometheus-export.py results/"
echo ""
echo "  2. Analyze results:"
echo "     python3 scripts/analyze-results.py results/reactive_processed.json results/predictive_processed.json"
echo ""
