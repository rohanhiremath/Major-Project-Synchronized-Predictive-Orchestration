#!/bin/bash
#
# Phase 6: Test with explicit venv (no conda interference)
#

set -e

PROJECT_ROOT="/home/kesavan-p/Documents/major project/implementation/Major-Project-Synchronized-Predictive-Orchestration"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
VENV_PIP="$PROJECT_ROOT/.venv/bin/pip"

DURATION=${1:-30}  # Default 30 minutes

echo "=========================================="
echo " Phase 6: Test with VENV"
echo "=========================================="
echo "Duration: ${DURATION} minutes"
echo ""

cd "$PROJECT_ROOT"

# Cleanup
echo "Cleaning up..."
pkill -f "prediction_service.py" 2>/dev/null || true
pkill -f "port-forward.*9090" 2>/dev/null || true
rm -f /tmp/prediction-service.log /tmp/prediction-metrics.json
sleep 2

# Verify venv Python exists
if [ ! -f "$VENV_PYTHON" ]; then
    echo "❌ venv Python not found at: $VENV_PYTHON"
    exit 1
fi

echo "Using Python: $VENV_PYTHON"
"$VENV_PYTHON" --version

# Check dependencies
echo "Checking dependencies..."
"$VENV_PYTHON" -c "import torch, pytorch_forecasting, flask, prometheus_client" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "Installing missing dependencies..."
    "$VENV_PIP" install flask prometheus-client requests
fi
echo "✅ Dependencies OK"
echo ""

# Check model
if [ ! -f "models/tft_psi_model.ckpt" ]; then
    echo "❌ Model not found!"
    exit 1
fi
echo "✅ Model found"
echo ""

# Port-forward Prometheus
echo "Setting up Prometheus port-forward..."
kubectl port-forward -n monitoring svc/prometheus-operated 9090:9090 > /dev/null 2>&1 &
PROM_PID=$!
sleep 5

if ! curl -s http://localhost:9090/-/healthy > /dev/null 2>&1; then
    echo "❌ Cannot connect to Prometheus"
    kill $PROM_PID 2>/dev/null || true
    exit 1
fi
echo "✅ Prometheus accessible"
echo ""

# Set environment variables
export PROMETHEUS_URL="http://localhost:9090"
export MODEL_PATH="$PROJECT_ROOT/models/tft_psi_model.ckpt"
export SPIKE_THRESHOLD="1.80"
export PREDICTION_INTERVAL="20"
export LOG_LEVEL="INFO"

# Start prediction service
echo "Starting prediction service..."
cd kubernetes/phase6
"$VENV_PYTHON" prediction_service.py > /tmp/prediction-service.log 2>&1 &
SERVICE_PID=$!
sleep 10

if ! ps -p $SERVICE_PID > /dev/null; then
    echo "❌ Service failed to start!"
    echo "Check logs: cat /tmp/prediction-service.log"
    kill $PROM_PID 2>/dev/null || true
    exit 1
fi

if curl -s http://localhost:8080/health > /dev/null 2>&1; then
    echo "✅ Prediction service running (PID: $SERVICE_PID)"
else
    echo "⚠️  Service running but health check failed"
fi
echo ""

# Cleanup function
cleanup() {
    echo ""
    echo "=========================================="
    echo " Stopping Services"
    echo "=========================================="
    
    # Save metrics
    curl -s http://localhost:8080/metrics-summary > /tmp/prediction-metrics.json 2>/dev/null || echo "{}" > /tmp/prediction-metrics.json
    
    # Stop services
    kill $SERVICE_PID 2>/dev/null || true
    kill $PROM_PID 2>/dev/null || true
    
    echo "✅ Services stopped"
    echo ""
    
    # Show results
    echo "=========================================="
    echo " Results"
    echo "=========================================="
    echo ""
    
    if [ -f /tmp/prediction-metrics.json ] && [ -s /tmp/prediction-metrics.json ]; then
        cat /tmp/prediction-metrics.json
    else
        echo "Metrics not available"
    fi
    
    echo ""
    echo "Logs: /tmp/prediction-service.log"
    echo "Metrics: /tmp/prediction-metrics.json"
    echo ""
}
trap cleanup EXIT INT TERM

# Check workload pods
echo "=========================================="
echo " Running Test"
echo "=========================================="
echo ""
WORKLOAD_COUNT=$(kubectl get pods -l app=workload --no-headers 2>/dev/null | wc -l)
if [ "$WORKLOAD_COUNT" -lt 3 ]; then
    echo "Creating workload pods..."
    kubectl apply -f "$PROJECT_ROOT/kubernetes/phase2/workload-statefulset.yaml"
    kubectl wait --for=condition=ready pod -l app=workload --timeout=180s
fi
echo "✅ Workload pods ready"
echo ""

# Test parameters
BURST_DURATION=180
IDLE_DURATION=120
CYCLE_DURATION=$((BURST_DURATION + IDLE_DURATION))
ITERATIONS=$((DURATION * 60 / CYCLE_DURATION))

echo "Test plan:"
echo "  Duration: ${DURATION} minutes"
echo "  Cycles: ${ITERATIONS}"
echo "  Pattern: ${BURST_DURATION}s burst + ${IDLE_DURATION}s idle"
echo ""

START_TIME=$(date +%s)

# Run test cycles
for i in $(seq 1 $ITERATIONS); do
    ELAPSED=$(($(date +%s) - START_TIME))
    REMAINING=$((DURATION * 60 - ELAPSED))
    
    echo "=========================================="
    echo " Cycle ${i}/${ITERATIONS}"
    echo " Elapsed: $((ELAPSED / 60))m | Remaining: $((REMAINING / 60))m"
    echo "=========================================="
    
    # BURST
    echo "▶ Generating PSI spikes..."
    kubectl exec workload-app-0 -c workload -- stress-ng --vm 2 --vm-bytes 80% --timeout ${BURST_DURATION}s &>/dev/null &
    kubectl exec workload-app-1 -c workload -- stress-ng --cpu 2 --timeout ${BURST_DURATION}s &>/dev/null &
    kubectl exec workload-app-2 -c workload -- stress-ng --vm 1 --vm-bytes 70% --cpu 1 --timeout ${BURST_DURATION}s &>/dev/null &
    
    sleep $BURST_DURATION
    echo "  Burst complete"
    
    PRED_COUNT=$(grep -c "prediction" /tmp/prediction-service.log 2>/dev/null || echo "0")
    echo "  Predictions logged: $PRED_COUNT"
    
    # IDLE
    echo "⏸  Recovery period..."
    sleep $IDLE_DURATION
    
    echo ""
done

# Test complete - cleanup via trap
echo "=========================================="
echo " Test Complete!"
echo "=========================================="
