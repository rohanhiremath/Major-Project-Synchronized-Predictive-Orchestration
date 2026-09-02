#!/bin/bash
#
# Phase 6: Intensive Testing with LOCAL prediction service
# NO DOCKER NEEDED - runs directly on your laptop
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

DURATION=${1:-120}  # Default 120 minutes
BURST_DURATION=300   # 5 minutes
IDLE_DURATION=180    # 3 minutes

echo "=========================================="
echo " Phase 6: LOCAL Intensive Test"
echo "=========================================="
echo ""
echo "Duration: ${DURATION} minutes"
echo "Service: Running locally (no Docker)"
echo ""

# Check if workload pods exist
echo "Step 1: Checking workload pods..."
WORKLOAD_COUNT=$(kubectl get statefulset workload-app -o jsonpath='{.status.replicas}' 2>/dev/null || echo "0")

if [ "$WORKLOAD_COUNT" = "0" ]; then
    echo -e "${YELLOW}⚠️  No workload pods found${NC}"
    echo "Creating workload pods..."
    kubectl apply -f ../phase2/workload-statefulset.yaml
    kubectl wait --for=condition=ready pod -l app=workload --timeout=180s
    echo -e "${GREEN}✅ Workload pods created${NC}"
else
    echo -e "${GREEN}✅ Found ${WORKLOAD_COUNT} workload pods${NC}"
fi
echo ""

# Calculate iterations
CYCLE_DURATION=$((BURST_DURATION + IDLE_DURATION))
ITERATIONS=$((DURATION * 60 / CYCLE_DURATION))

echo "Test Plan:"
echo "  Total duration: ${DURATION} minutes"
echo "  Cycle: ${BURST_DURATION}s burst + ${IDLE_DURATION}s idle"
echo "  Iterations: ${ITERATIONS} cycles"
echo "  Expected predictions: $((DURATION * 3))"
echo ""

read -p "Start test? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 0
fi

echo ""
echo "=========================================="
echo " Starting Test"
echo "=========================================="
echo ""
echo -e "${YELLOW}NOTE: Make sure prediction service is running!${NC}"
echo "In another terminal, run:"
echo "  cd kubernetes/phase6"
echo "  ./run-local-test.sh"
echo ""
read -p "Is the prediction service running? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 0
fi

START_TIME=$(date +%s)
ITERATION=0

# Functions for stress testing
run_memory_stress() {
    local POD=$1
    kubectl exec ${POD} -c workload -- stress-ng \
        --vm 2 --vm-bytes 80% --timeout ${BURST_DURATION}s &> /dev/null &
}

run_cpu_stress() {
    local POD=$1
    kubectl exec ${POD} -c workload -- stress-ng \
        --cpu 2 --timeout ${BURST_DURATION}s &> /dev/null &
}

run_mixed_stress() {
    local POD=$1
    kubectl exec ${POD} -c workload -- stress-ng \
        --vm 1 --vm-bytes 70% --cpu 1 --io 1 --timeout ${BURST_DURATION}s &> /dev/null &
}

# Main test loop
while [ $ITERATION -lt $ITERATIONS ]; do
    ITERATION=$((ITERATION + 1))
    ELAPSED=$(($(date +%s) - START_TIME))
    REMAINING=$((DURATION * 60 - ELAPSED))
    
    echo ""
    echo "=========================================="
    echo " Iteration ${ITERATION}/${ITERATIONS}"
    echo " Elapsed: $((ELAPSED / 60))m | Remaining: $((REMAINING / 60))m"
    echo "=========================================="
    
    # BURST PHASE
    echo -e "${GREEN}▶ BURST PHASE (${BURST_DURATION}s)${NC}"
    STRESS_TYPE=$((ITERATION % 3))
    
    case $STRESS_TYPE in
        0) echo "  Pattern: Memory stress"
           run_memory_stress "workload-app-0"
           run_memory_stress "workload-app-1"
           run_memory_stress "workload-app-2" ;;
        1) echo "  Pattern: CPU stress"
           run_cpu_stress "workload-app-0"
           run_cpu_stress "workload-app-1"
           run_cpu_stress "workload-app-2" ;;
        2) echo "  Pattern: Mixed stress"
           run_mixed_stress "workload-app-0"
           run_mixed_stress "workload-app-1"
           run_mixed_stress "workload-app-2" ;;
    esac
    
    sleep $BURST_DURATION
    echo -e "  ${GREEN}Burst complete${NC}"
    
    # IDLE PHASE
    echo -e "${YELLOW}⏸  IDLE PHASE (${IDLE_DURATION}s)${NC}"
    
    # Show current metrics
    METRICS=$(curl -s http://localhost:8080/metrics-summary 2>/dev/null || echo "{}")
    if [ "$METRICS" != "{}" ]; then
        PRECISION=$(echo $METRICS | jq -r '.precision * 100' 2>/dev/null | cut -c1-5)
        RECALL=$(echo $METRICS | jq -r '.recall * 100' 2>/dev/null | cut -c1-5)
        echo "  Current: Precision=${PRECISION}%, Recall=${RECALL}%"
    fi
    
    sleep $IDLE_DURATION
done

# Test complete
echo ""
echo "=========================================="
echo " Test Complete"
echo "=========================================="
echo ""

FINAL_METRICS=$(curl -s http://localhost:8080/metrics-summary 2>/dev/null || echo "{}")

if [ "$FINAL_METRICS" != "{}" ]; then
    echo "$FINAL_METRICS" | jq '.'
    
    PRECISION=$(echo $FINAL_METRICS | jq -r '.precision * 100' 2>/dev/null | cut -c1-5)
    RECALL=$(echo $FINAL_METRICS | jq -r '.recall * 100' 2>/dev/null | cut -c1-5)
    
    echo ""
    echo "Final Results:"
    echo "  Precision: ${PRECISION}%"
    echo "  Recall:    ${RECALL}%"
    echo ""
    
    # Check if passing
    PASS=$(echo "$PRECISION >= 85 && $RECALL >= 90" | bc -l 2>/dev/null || echo "0")
    if [ "$PASS" = "1" ]; then
        echo -e "${GREEN}✅ TEST PASSED - Ready for Phase 7!${NC}"
    else
        echo -e "${YELLOW}⚠️  Results below target${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  Could not fetch metrics${NC}"
fi

echo ""
echo "Check the prediction service terminal for detailed logs"
echo ""
