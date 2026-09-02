#!/bin/bash
#
# Phase 6: Aggressive Testing (generates more PSI spikes)
# More robust - continues even if some stress commands fail
#

PROJECT_ROOT="/home/kesavan-p/Documents/major project/implementation/Major-Project-Synchronized-Predictive-Orchestration"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"

DURATION=${1:-30}

echo "=========================================="
echo " Phase 6: Aggressive Spike Test"
echo "=========================================="
echo "Duration: ${DURATION} minutes"
echo "More aggressive workloads for higher PSI"
echo ""

cd "$PROJECT_ROOT"

# Cleanup
pkill -f "prediction_service.py" 2>/dev/null || true
pkill -f "port-forward.*9090" 2>/dev/null || true
rm -f /tmp/prediction-service.log /tmp/prediction-metrics.json
sleep 2

# Start Prometheus port-forward
kubectl port-forward -n monitoring svc/prometheus-operated 9090:9090 > /dev/null 2>&1 &
PROM_PID=$!
sleep 5

# Set environment
export PROMETHEUS_URL="http://localhost:9090"
export MODEL_PATH="$PROJECT_ROOT/models/tft_psi_model.ckpt"
export SPIKE_THRESHOLD="1.80"
export PREDICTION_INTERVAL="20"

# Start prediction service
cd kubernetes/phase6
"$VENV_PYTHON" prediction_service.py > /tmp/prediction-service.log 2>&1 &
SERVICE_PID=$!
sleep 10

if ! ps -p $SERVICE_PID > /dev/null 2>&1; then
    echo "❌ Service failed to start - check logs"
    echo "Recent logs:"
    tail -20 /tmp/prediction-service.log
    kill $PROM_PID 2>/dev/null || true
    exit 1
fi

echo "✅ Prediction service running (PID: $SERVICE_PID)"
echo ""

# Cleanup function
cleanup() {
    echo ""
    echo "Stopping services..."
    curl -s http://localhost:8080/metrics-summary > /tmp/prediction-metrics.json 2>/dev/null || echo "{}" > /tmp/prediction-metrics.json
    kill $SERVICE_PID 2>/dev/null || true
    kill $PROM_PID 2>/dev/null || true
    
    echo "=========================================="
    echo " Results"
    echo "=========================================="
    cat /tmp/prediction-metrics.json
    echo ""
    echo "Predictions: $(grep -c 'Iteration' /tmp/prediction-service.log)"
    echo "Spikes detected: $(grep -c 'Spike predicted: True' /tmp/prediction-service.log)"
    echo "Logs: /tmp/prediction-service.log"
}
trap cleanup EXIT INT TERM

echo "=========================================="
echo " Running Aggressive Test"
echo "=========================================="
echo ""

# More aggressive stress parameters
BURST_DURATION=240  # 4 minutes (longer)
IDLE_DURATION=60    # 1 minute (shorter)
CYCLE_DURATION=$((BURST_DURATION + IDLE_DURATION))
ITERATIONS=$((DURATION * 60 / CYCLE_DURATION))

echo "Test plan:"
echo "  Cycles: ${ITERATIONS}"
echo "  Pattern: ${BURST_DURATION}s burst + ${IDLE_DURATION}s idle"
echo "  Stress: 90% memory, full CPU"
echo ""

START_TIME=$(date +%s)

for i in $(seq 1 $ITERATIONS); do
    ELAPSED=$(($(date +%s) - START_TIME))
    REMAINING=$((DURATION * 60 - ELAPSED))
    
    echo "=========================================="
    echo " Cycle ${i}/${ITERATIONS}"
    echo " Elapsed: $((ELAPSED / 60))m | Remaining: $((REMAINING / 60))m"
    echo "=========================================="
    
    # AGGRESSIVE BURST - all pods simultaneously
    echo "▶ AGGRESSIVE: High memory + CPU stress..."
    
    # Pod 0: Very high memory stress
    kubectl exec workload-app-0 -c workload -- stress-ng --vm 3 --vm-bytes 90% --timeout ${BURST_DURATION}s &>/dev/null &
    STRESS_PID_0=$!
    
    # Pod 1: Full CPU + some memory
    kubectl exec workload-app-1 -c workload -- stress-ng --cpu 4 --vm 1 --vm-bytes 70% --timeout ${BURST_DURATION}s &>/dev/null &
    STRESS_PID_1=$!
    
    # Pod 2: Mixed heavy stress
    kubectl exec workload-app-2 -c workload -- stress-ng --vm 2 --vm-bytes 85% --cpu 2 --io 2 --timeout ${BURST_DURATION}s &>/dev/null &
    STRESS_PID_2=$!
    
    echo "  Stress workloads started (PIDs: $STRESS_PID_0 $STRESS_PID_1 $STRESS_PID_2)"
    
    # Let burst run
    echo "  Running burst for ${BURST_DURATION}s..."
    sleep $BURST_DURATION
    
    # Wait for stress to finish
    wait $STRESS_PID_0 2>/dev/null || echo "  Pod 0 stress completed"
    wait $STRESS_PID_1 2>/dev/null || echo "  Pod 1 stress completed"
    wait $STRESS_PID_2 2>/dev/null || echo "  Pod 2 stress completed"
    
    PRED_COUNT=$(grep -c "Iteration" /tmp/prediction-service.log 2>/dev/null || echo "0")
    SPIKE_COUNT=$(grep -c "Spike predicted: True" /tmp/prediction-service.log 2>/dev/null || echo "0")
    echo "  Predictions: $PRED_COUNT | Spikes: $SPIKE_COUNT"
    
    # Short recovery
    echo "⏸  Recovery for ${IDLE_DURATION}s..."
    sleep $IDLE_DURATION
    
    echo ""
done

echo "Test complete!"
