#!/bin/bash
#
# Day 3: HPA Testing Script
# Tests both reactive and predictive HPAs
#

set -e

echo "╔═══════════════════════════════════════════════════════════════════════════════╗"
echo "║                                                                               ║"
echo "║                      DAY 3: HPA DEPLOYMENT TEST                               ║"
echo "║                                                                               ║"
echo "╚═══════════════════════════════════════════════════════════════════════════════╝"
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

cd "$(dirname "$0")"

echo "=== Step 1: Verify Prerequisites ==="
echo ""

echo "Checking Custom Metrics API..."
if kubectl get apiservice v1beta1.custom.metrics.k8s.io | grep -q "True"; then
    echo -e "${GREEN}✅ Custom Metrics API available${NC}"
else
    echo -e "${RED}❌ Custom Metrics API not available${NC}"
    exit 1
fi

echo "Checking Prometheus Adapter..."
if kubectl get pods -n monitoring -l app.kubernetes.io/name=prometheus-adapter | grep -q "Running"; then
    echo -e "${GREEN}✅ Prometheus Adapter running${NC}"
else
    echo -e "${RED}❌ Prometheus Adapter not running${NC}"
    exit 1
fi

echo "Checking workload pods..."
WORKLOAD_PODS=$(kubectl get pods -l app=workload --no-headers | wc -l)
if [ "$WORKLOAD_PODS" -ge 1 ]; then
    echo -e "${GREEN}✅ Workload pods running ($WORKLOAD_PODS pods)${NC}"
else
    echo -e "${RED}❌ No workload pods found${NC}"
    exit 1
fi

echo ""
echo "=== Step 2: Check Available Metrics ==="
echo ""

echo "Querying custom metrics API..."
AVAILABLE_METRICS=$(kubectl get --raw /apis/custom.metrics.k8s.io/v1beta1 2>/dev/null | python3 -c "import sys, json; data=json.load(sys.stdin); print(len(data.get('resources', [])))" 2>/dev/null || echo "0")
echo "Available metrics: $AVAILABLE_METRICS"

# Check for our specific metrics
echo ""
echo "Checking for predicted_psi metrics..."
if kubectl get --raw /apis/custom.metrics.k8s.io/v1beta1 2>/dev/null | grep -q "predicted_psi"; then
    echo -e "${GREEN}✅ predicted_psi metrics found${NC}"
    HAS_PREDICTED_METRICS=true
else
    echo -e "${YELLOW}⚠️  predicted_psi metrics not found (prediction service may not be running)${NC}"
    HAS_PREDICTED_METRICS=false
fi

echo ""
echo "=== Step 3: Deploy Reactive HPA (Baseline) ==="
echo ""

if [ -f "workload-reactive-hpa.yaml" ]; then
    echo "Applying reactive HPA..."
    kubectl apply -f workload-reactive-hpa.yaml
    echo -e "${GREEN}✅ Reactive HPA deployed${NC}"
else
    echo -e "${RED}❌ workload-reactive-hpa.yaml not found${NC}"
    exit 1
fi

sleep 3

echo ""
echo "=== Step 4: Check Reactive HPA Status ==="
echo ""

kubectl get hpa workload-reactive-hpa -o wide 2>/dev/null || echo "HPA not ready yet..."
echo ""
kubectl describe hpa workload-reactive-hpa 2>/dev/null | grep -A 10 "Conditions:" || true

echo ""
echo "=== Step 5: Deploy Predictive HPA ==="
echo ""

if [ "$HAS_PREDICTED_METRICS" = true ]; then
    echo "Applying predictive HPA..."
    kubectl apply -f workload-predictive-hpa.yaml
    echo -e "${GREEN}✅ Predictive HPA deployed${NC}"
    
    sleep 3
    
    echo ""
    echo "=== Step 6: Check Predictive HPA Status ==="
    echo ""
    
    kubectl get hpa workload-predictive-hpa -o wide 2>/dev/null || echo "HPA not ready yet..."
    echo ""
    kubectl describe hpa workload-predictive-hpa 2>/dev/null | grep -A 10 "Conditions:" || true
else
    echo -e "${YELLOW}⚠️  Skipping predictive HPA (metrics not available)${NC}"
    echo "To enable predictive HPA:"
    echo "  1. Start prediction service"
    echo "  2. Configure Prometheus scraping"
    echo "  3. Wait for metrics to appear in custom metrics API"
    echo "  4. Re-run this script"
fi

echo ""
echo "=== Step 7: Summary ==="
echo ""

echo "HPAs deployed:"
kubectl get hpa 2>/dev/null || echo "No HPAs found"

echo ""
echo "Current workload replicas:"
kubectl get statefulset workload-app -o wide 2>/dev/null || kubectl get deployment workload-app -o wide 2>/dev/null || echo "Workload not found"

echo ""
echo "╔═══════════════════════════════════════════════════════════════════════════════╗"
echo "║                                                                               ║"
echo "║                        DAY 3 TEST COMPLETE                                    ║"
echo "║                                                                               ║"
echo "╚═══════════════════════════════════════════════════════════════════════════════╝"
echo ""

if [ "$HAS_PREDICTED_METRICS" = true ]; then
    echo -e "${GREEN}✅ Both HPAs deployed successfully${NC}"
    echo ""
    echo "Next steps:"
    echo "  - Monitor HPA behavior: kubectl get hpa --watch"
    echo "  - Check scaling events: kubectl get events --sort-by='.lastTimestamp'"
    echo "  - View HPA details: kubectl describe hpa <name>"
else
    echo -e "${YELLOW}⚠️  Reactive HPA deployed, Predictive HPA pending${NC}"
    echo ""
    echo "To complete setup:"
    echo "  1. Deploy prediction service"
    echo "  2. Verify metrics appear in custom metrics API"
    echo "  3. Deploy predictive HPA"
fi

echo ""
