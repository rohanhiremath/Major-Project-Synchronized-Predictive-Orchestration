#!/bin/bash
#
# Phase 6: Run prediction service locally (NO DOCKER NEEDED!)
# Much faster for testing - runs directly on your laptop
#

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo "=========================================="
echo " Phase 6: Local Testing (No Docker)"
echo "=========================================="
echo ""
echo "This will run the prediction service directly"
echo "on your laptop - much faster than Docker!"
echo ""

# Check if in project root
if [ ! -f "src/train_tft.py" ]; then
    echo "Please run from project root!"
    exit 1
fi

# Check if venv exists
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate venv
source .venv/bin/activate

# Check if packages are installed
echo "Step 1: Checking dependencies..."
if ! python -c "import torch" 2>/dev/null; then
    echo "Installing required packages..."
    pip install torch pytorch-lightning pytorch-forecasting pandas prometheus-client flask requests
fi
echo -e "${GREEN}✅ Dependencies OK${NC}"
echo ""

# Check if model exists
if [ ! -f "models/tft_psi_model.ckpt" ]; then
    echo -e "${YELLOW}⚠️  Model not found at models/tft_psi_model.ckpt${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Model found${NC}"
echo ""

# Check if Kubernetes cluster is running
if ! kubectl get nodes &>/dev/null; then
    echo -e "${YELLOW}⚠️  Kubernetes cluster not accessible${NC}"
    echo "Make sure your kind cluster is running"
    exit 1
fi
echo -e "${GREEN}✅ Kubernetes cluster accessible${NC}"
echo ""

# Set environment variables
export SPIKE_THRESHOLD=1.80
export PREDICTION_INTERVAL=20
export PROMETHEUS_URL="http://localhost:9090"
export MODEL_PATH="models/tft_psi_model.ckpt"

echo "=========================================="
echo " Starting Prediction Service"
echo "=========================================="
echo ""
echo "Configuration:"
echo "  Spike Threshold: ${SPIKE_THRESHOLD}%"
echo "  Prediction Interval: ${PREDICTION_INTERVAL}s"
echo "  Prometheus: ${PROMETHEUS_URL}"
echo "  Model: ${MODEL_PATH}"
echo ""
echo "The service will:"
echo "  1. Query Prometheus for PSI metrics"
echo "  2. Make predictions every 20 seconds"
echo "  3. Log spike predictions (shadow mode)"
echo "  4. Export metrics on http://localhost:8080/metrics"
echo ""
echo -e "${BLUE}Press Ctrl+C to stop${NC}"
echo ""

# Port-forward Prometheus in background
echo "Setting up Prometheus port-forward..."
kubectl port-forward -n monitoring svc/prometheus-operated 9090:9090 &>/dev/null &
PROM_PID=$!
sleep 3

# Run prediction service
cd kubernetes/phase6
python prediction_service.py

# Cleanup
kill $PROM_PID 2>/dev/null || true
