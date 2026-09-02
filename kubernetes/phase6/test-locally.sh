#!/bin/bash
#
# Complete local testing workflow (no Docker/K8s deployment needed!)
# This tests the prediction service running on your laptop
#

set -e

PROJECT_ROOT="/home/kesavan-p/Documents/major project/implementation/Major-Project-Synchronized-Predictive-Orchestration"
cd "$PROJECT_ROOT"

echo "=========================================="
echo " Phase 6: Local Testing (No Docker!)"
echo "=========================================="
echo ""
echo "This will:"
echo "  1. Start prediction service locally"
echo "  2. Generate workload spikes in K8s"
echo "  3. Service predicts spikes from Prometheus"
echo "  4. Collect results after 2 hours"
echo ""

read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 0
fi

# Check if Prometheus is accessible
echo "Step 1: Checking Prometheus..."
kubectl get service -n monitoring prometheus-operated > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "❌ Prometheus not found in cluster"
    echo "Please ensure Phase 3 (Prometheus) is running"
    exit 1
fi

echo "✅ Prometheus found"
echo ""

# Start port-forward in background
echo "Step 2: Port-forwarding Prometheus..."
kubectl port-forward -n monitoring service/prometheus-operated 9090:9090 > /dev/null 2>&1 &
PROM_PF_PID=$!
sleep 3

# Test connection
if curl -s http://localhost:9090/-/healthy > /dev/null 2>&1; then
    echo "✅ Prometheus accessible on localhost:9090"
else
    echo "❌ Cannot connect to Prometheus"
    kill $PROM_PF_PID 2>/dev/null || true
    exit 1
fi
echo ""

# Start prediction service in background
echo "Step 3: Starting prediction service..."
cd kubernetes/phase6

# Set environment
export PROMETHEUS_URL="http://localhost:9090"
export MODEL_PATH="$PROJECT_ROOT/models/tft_psi_model.ckpt"
export SPIKE_THRESHOLD="1.80"
export PREDICTION_INTERVAL="20"

source "$PROJECT_ROOT/.venv/bin/activate"

# Run service in background, logging to file
python prediction_service.py > /tmp/prediction-service.log 2>&1 &
SERVICE_PID=$!

echo "  Service PID: $SERVICE_PID"
echo "  Logs: /tmp/prediction-service.log"

# Wait for service to start
sleep 10

# Check if service is running
if ps -p $SERVICE_PID > /dev/null; then
    echo "✅ Prediction service running"
else
    echo "❌ Service failed to start"
    echo "Check logs: cat /tmp/prediction-service.log"
    kill $PROM_PF_PID 2>/dev/null || true
    exit 1
fi

# Test health endpoint
curl -s http://localhost:8080/health > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "✅ Health endpoint responding"
else
    echo "⚠️  Health endpoint not responding yet"
fi
echo ""

# Cleanup function
cleanup() {
    echo ""
    echo "=========================================="
    echo " Cleanup"
    echo "=========================================="
    echo "Stopping services..."
    kill $SERVICE_PID 2>/dev/null || true
    kill $PROM_PF_PID 2>/dev/null || true
    echo "✅ Stopped"
}
trap cleanup EXIT

# Now run workload tests
echo "=========================================="
echo " Running Workload Tests"
echo "=========================================="
echo ""

# Check if workload pods exist
WORKLOAD_COUNT=$(kubectl get statefulset workload-app -o jsonpath='{.status.replicas}' 2>/dev/null || echo "0")

if [ "$WORKLOAD_COUNT" = "0" ]; then
    echo "Creating workload pods..."
    kubectl apply -f ../phase2/workload-statefulset.yaml
    kubectl wait --for=condition=ready pod -l app=workload --timeout=180s
    echo "✅ Workload pods ready"
else
    echo "✅ Found $WORKLOAD_COUNT workload pods"
fi
echo ""

DURATION=${1:-30}  # Default 30 minutes for quick test
BURST_DURATION=180  # 3 minutes burst
IDLE_DURATION=120   # 2 minutes idle

echo "Test configuration:"
echo "  Duration: $DURATION minutes"
echo "  Pattern: ${BURST_DURATION}s burst + ${IDLE_DURATION}s idle"
echo ""

START_TIME=$(date +%s)
CYCLE_DURATION=$((BURST_DURATION + IDLE_DURATION))
ITERATIONS=$((DURATION * 60 / CYCLE_DURATION))

echo "Starting $ITERATIONS test cycles..."
echo ""

for i in $(seq 1 $ITERATIONS); do
    echo "--- Cycle $i/$ITERATIONS ---"
    
    # BURST: Generate spikes
    echo "[$(date +%H:%M:%S)] Generating spikes..."
    kubectl exec workload-app-0 -c workload -- stress-ng --vm 2 --vm-bytes 80% --timeout ${BURST_DURATION}s &
    kubectl exec workload-app-1 -c workload -- stress-ng --cpu 2 --timeout ${BURST_DURATION}s &
    kubectl exec workload-app-2 -c workload -- stress-ng --vm 1 --vm-bytes 70% --cpu 1 --timeout ${BURST_DURATION}s &
    
    sleep $BURST_DURATION
    
    # Check predictions
    PRED_COUNT=$(grep -c "Spike predicted:" /tmp/prediction-service.log || echo "0")
    echo "[$(date +%H:%M:%S)] Predictions so far: $PRED_COUNT"
    
    # IDLE: Recovery
    echo "[$(date +%H:%M:%S)] Idle period..."
    sleep $IDLE_DURATION
    
    echo ""
done

# Collect results
echo "=========================================="
echo " Test Complete - Collecting Results"
echo "=========================================="
echo ""

TOTAL_TIME=$(($(date +%s) - START_TIME))
echo "Test duration: $((TOTAL_TIME / 60))m $((TOTAL_TIME % 60))s"
echo ""

# Get final metrics
echo "Final metrics:"
curl -s http://localhost:8080/metrics-summary | jq '.' || echo "Could not fetch metrics"
echo ""

# Analyze logs
TOTAL_PREDICTIONS=$(grep -c "Spike predicted:" /tmp/prediction-service.log || echo "0")
SPIKES_DETECTED=$(grep "Spike predicted: True" /tmp/prediction-service.log | wc -l || echo "0")

echo "Log analysis:"
echo "  Total predictions: $TOTAL_PREDICTIONS"
echo "  Spikes detected: $SPIKES_DETECTED"
echo ""

# Save results
RESULTS_DIR="phase6-local-results-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$RESULTS_DIR"

cp /tmp/prediction-service.log "$RESULTS_DIR/service.log"
curl -s http://localhost:8080/metrics-summary > "$RESULTS_DIR/metrics.json" 2>/dev/null || echo "{}" > "$RESULTS_DIR/metrics.json"

echo "Results saved to: $RESULTS_DIR/"
echo ""
echo "Review:"
echo "  Logs: $RESULTS_DIR/service.log"
echo "  Metrics: $RESULTS_DIR/metrics.json"
echo ""

# Cleanup happens automatically via trap
