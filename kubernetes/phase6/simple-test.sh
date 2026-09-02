#!/bin/bash
#
# Simple Phase 6 Test - All-in-one script
# Starts service and runs test automatically
#

set -e

PROJECT_ROOT="/home/kesavan-p/Documents/major project/implementation/Major-Project-Synchronized-Predictive-Orchestration"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

DURATION=${1:-30}  # Default 30 minutes

echo "=========================================="
echo " Phase 6: Simple All-in-One Test"
echo "=========================================="
echo ""
echo "Duration: ${DURATION} minutes"
echo ""

cd "$PROJECT_ROOT"

# Cleanup any previous runs
echo "Cleaning up previous runs..."
pkill -f "prediction_service.py" 2>/dev/null || true
pkill -f "port-forward.*9090" 2>/dev/null || true
rm -f /tmp/prediction-service.log /tmp/prediction-metrics.json
sleep 2

# Activate venv
echo "Activating virtual environment..."
source .venv/bin/activate

# Check dependencies
echo "Checking dependencies..."
python -c "import torch, pytorch_forecasting, flask, prometheus_client" 2>/dev/null
if [ $? -ne 0 ]; then
    echo -e "${RED}Missing dependencies! Installing...${NC}"
    pip install flask prometheus-client requests > /dev/null 2>&1
fi

# Check model
if [ ! -f "models/tft_psi_model.ckpt" ]; then
    echo -e "${RED}Model not found!${NC}"
    exit 1
fi

echo -e "${GREEN}✅ All prerequisites OK${NC}"
echo ""

# Port-forward Prometheus
echo "Setting up Prometheus port-forward..."
kubectl port-forward -n monitoring svc/prometheus-operated 9090:9090 > /dev/null 2>&1 &
PROM_PID=$!
sleep 5

# Test Prometheus
if ! curl -s http://localhost:9090/-/healthy > /dev/null 2>&1; then
    echo -e "${RED}Cannot connect to Prometheus${NC}"
    kill $PROM_PID 2>/dev/null || true
    exit 1
fi
echo -e "${GREEN}✅ Prometheus accessible${NC}"
echo ""

# Set environment variables
export PROMETHEUS_URL="http://localhost:9090"
export MODEL_PATH="$PROJECT_ROOT/models/tft_psi_model.ckpt"
export SPIKE_THRESHOLD="1.80"
export PREDICTION_INTERVAL="20"
export LOG_LEVEL="INFO"

# Start prediction service in background
echo "Starting prediction service..."
cd kubernetes/phase6
python prediction_service.py > /tmp/prediction-service.log 2>&1 &
SERVICE_PID=$!
sleep 10

# Check if service started
if ! ps -p $SERVICE_PID > /dev/null; then
    echo -e "${RED}Service failed to start!${NC}"
    echo "Check logs: cat /tmp/prediction-service.log"
    kill $PROM_PID 2>/dev/null || true
    exit 1
fi

# Test service health
if curl -s http://localhost:8080/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Prediction service running (PID: $SERVICE_PID)${NC}"
else
    echo -e "${YELLOW}⚠️  Service running but health check failed${NC}"
fi
echo ""

# Cleanup function
cleanup() {
    echo ""
    echo "=========================================="
    echo " Stopping Services"
    echo "=========================================="
    
    # Save final metrics
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
        cat /tmp/prediction-metrics.json | jq '.' 2>/dev/null || cat /tmp/prediction-metrics.json
    else
        echo "Metrics not available"
    fi
    
    echo ""
    echo "Logs saved to: /tmp/prediction-service.log"
    echo "Metrics saved to: /tmp/prediction-metrics.json"
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
    kubectl apply -f ../phase2/workload-statefulset.yaml
    kubectl wait --for=condition=ready pod -l app=workload --timeout=180s
fi
echo -e "${GREEN}✅ Workload pods ready${NC}"
echo ""

# Calculate test parameters
BURST_DURATION=180  # 3 minutes
IDLE_DURATION=120   # 2 minutes
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
    
    # BURST PHASE
    echo -e "${GREEN}▶ Generating PSI spikes...${NC}"
    
    # Memory stress on pod 0
    kubectl exec workload-app-0 -c workload -- stress-ng --vm 2 --vm-bytes 80% --timeout ${BURST_DURATION}s &>/dev/null &
    
    # CPU stress on pod 1
    kubectl exec workload-app-1 -c workload -- stress-ng --cpu 2 --timeout ${BURST_DURATION}s &>/dev/null &
    
    # Mixed stress on pod 2
    kubectl exec workload-app-2 -c workload -- stress-ng --vm 1 --vm-bytes 70% --cpu 1 --timeout ${BURST_DURATION}s &>/dev/null &
    
    sleep $BURST_DURATION
    echo -e "  ${GREEN}Burst complete${NC}"
    
    # Check predictions
    PRED_COUNT=$(grep -c "prediction" /tmp/prediction-service.log 2>/dev/null || echo "0")
    echo "  Predictions logged: $PRED_COUNT"
    
    # IDLE PHASE
    echo -e "${YELLOW}⏸  Recovery period...${NC}"
    sleep $IDLE_DURATION
    
    echo ""
done

# Test complete - cleanup will run automatically via trap
echo "=========================================="
echo " Test Complete!"
echo "=========================================="
