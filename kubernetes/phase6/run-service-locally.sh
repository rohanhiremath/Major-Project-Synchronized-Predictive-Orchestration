#!/bin/bash
#
# Run prediction service locally (without Docker/K8s)
# This is MUCH faster for testing
#

set -e

PROJECT_ROOT="/home/kesavan-p/Documents/major project/implementation/Major-Project-Synchronized-Predictive-Orchestration"

echo "=========================================="
echo " Phase 6: Local Prediction Service"
echo "=========================================="
echo ""
echo "Running service locally (no Docker needed!)"
echo ""

# Check if in project directory
cd "$PROJECT_ROOT"

# Activate virtual environment
echo "Step 1: Activating virtual environment..."
if [ ! -d ".venv" ]; then
    echo "❌ Virtual environment not found"
    exit 1
fi

source .venv/bin/activate
echo "✅ Virtual environment activated"
echo ""

# Check dependencies
echo "Step 2: Checking dependencies..."
python -c "import torch, pytorch_forecasting, flask, prometheus_client" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✅ All dependencies present"
else
    echo "⚠️  Installing missing dependencies..."
    pip install flask prometheus-client requests
fi
echo ""

# Set environment variables
export PROMETHEUS_URL="http://localhost:9090"
export MODEL_PATH="$PROJECT_ROOT/models/tft_psi_model.ckpt"
export SPIKE_THRESHOLD="1.80"
export PREDICTION_INTERVAL="20"
export LOG_LEVEL="INFO"

echo "Step 3: Configuration"
echo "  Prometheus URL: $PROMETHEUS_URL"
echo "  Model Path: $MODEL_PATH"
echo "  Spike Threshold: ${SPIKE_THRESHOLD}%"
echo "  Prediction Interval: ${PREDICTION_INTERVAL}s"
echo ""

# Port forward Prometheus (if in K8s)
echo "Step 4: Setting up Prometheus access..."
kubectl port-forward -n monitoring service/prometheus-operated 9090:9090 &
PORT_FORWARD_PID=$!
sleep 3

# Test Prometheus connectivity
if curl -s http://localhost:9090/-/healthy > /dev/null 2>&1; then
    echo "✅ Prometheus accessible"
else
    echo "⚠️  Prometheus not accessible - check if it's running"
    echo "   You may need to start it: kubectl port-forward -n monitoring service/prometheus-operated 9090:9090"
fi
echo ""

# Run the service
echo "=========================================="
echo " Starting Prediction Service"
echo "=========================================="
echo ""
echo "Service will run on:"
echo "  - Health/Metrics: http://localhost:8080"
echo "  - Prometheus metrics: http://localhost:9090"
echo ""
echo "Press Ctrl+C to stop"
echo ""

cd kubernetes/phase6

# Trap to cleanup on exit
cleanup() {
    echo ""
    echo "Stopping service..."
    kill $PORT_FORWARD_PID 2>/dev/null || true
    echo "✅ Cleanup complete"
}
trap cleanup EXIT

# Run the service
python prediction_service.py

