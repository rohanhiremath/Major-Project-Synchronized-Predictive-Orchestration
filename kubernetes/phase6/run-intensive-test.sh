#!/bin/bash
#
# Phase 6: Intensive Testing Script
# Runs workloads to generate realistic spike patterns for 2-3 hours
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
DURATION=${1:-120}  # Default 120 minutes (2 hours)
BURST_DURATION=300   # 5 minutes
IDLE_DURATION=180    # 3 minutes

echo "=========================================="
echo " Phase 6: Intensive Workload Testing"
echo "=========================================="
echo ""
echo "Duration: ${DURATION} minutes"
echo "Pattern: ${BURST_DURATION}s burst + ${IDLE_DURATION}s idle"
echo ""

# Check if prediction service is running
echo "Step 1: Checking prediction service..."
if ! kubectl get deployment prediction-service &> /dev/null; then
    echo -e "${RED}❌ Prediction service not found${NC}"
    echo "Deploy it first: cd kubernetes/phase6 && ./deploy.sh"
    exit 1
fi

POD_STATUS=$(kubectl get deployment prediction-service -o jsonpath='{.status.availableReplicas}')
if [ "$POD_STATUS" != "1" ]; then
    echo -e "${RED}❌ Prediction service not ready${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Prediction service running${NC}"
echo ""

# Check if workload pods exist
echo "Step 2: Checking workload pods..."
WORKLOAD_COUNT=$(kubectl get statefulset workload-app -o jsonpath='{.status.replicas}' 2>/dev/null || echo "0")

if [ "$WORKLOAD_COUNT" = "0" ]; then
    echo -e "${YELLOW}⚠️  No workload pods found${NC}"
    echo "Creating workload pods from Phase 2..."
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
echo "  Cycle: ${BURST_DURATION}s burst + ${IDLE_DURATION}s idle = ${CYCLE_DURATION}s"
echo "  Iterations: ${ITERATIONS} cycles"
echo "  Expected spikes: $((ITERATIONS * 3)) (approx)"
echo "  Expected predictions: $((DURATION * 3)) (approx)"
echo ""

read -p "Start test? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Test cancelled"
    exit 0
fi

echo ""
echo "=========================================="
echo " Starting Intensive Test"
echo "=========================================="
echo ""

START_TIME=$(date +%s)
ITERATION=0

# Function to run memory stress
run_memory_stress() {
    local POD=$1
    echo -e "${BLUE}[$(date +%H:%M:%S)]${NC} Starting memory stress on ${POD}..."
    
    kubectl exec ${POD} -c workload -- stress-ng \
        --vm 2 \
        --vm-bytes 80% \
        --timeout ${BURST_DURATION}s \
        &> /dev/null &
}

# Function to run CPU stress
run_cpu_stress() {
    local POD=$1
    echo -e "${BLUE}[$(date +%H:%M:%S)]${NC} Starting CPU stress on ${POD}..."
    
    kubectl exec ${POD} -c workload -- stress-ng \
        --cpu 2 \
        --timeout ${BURST_DURATION}s \
        &> /dev/null &
}

# Function to run mixed stress
run_mixed_stress() {
    local POD=$1
    echo -e "${BLUE}[$(date +%H:%M:%S)]${NC} Starting mixed stress on ${POD}..."
    
    kubectl exec ${POD} -c workload -- stress-ng \
        --vm 1 \
        --vm-bytes 70% \
        --cpu 1 \
        --io 1 \
        --timeout ${BURST_DURATION}s \
        &> /dev/null &
}

# Main test loop
while [ $ITERATION -lt $ITERATIONS ]; do
    ITERATION=$((ITERATION + 1))
    ELAPSED=$(($(date +%s) - START_TIME))
    REMAINING=$((DURATION * 60 - ELAPSED))
    
    echo ""
    echo "=========================================="
    echo " Iteration ${ITERATION}/${ITERATIONS}"
    echo " Elapsed: $((ELAPSED / 60))m ${((ELAPSED % 60))}s"
    echo " Remaining: $((REMAINING / 60))m ${((REMAINING % 60))}s"
    echo "=========================================="
    echo ""
    
    # BURST PHASE
    echo -e "${GREEN}▶ BURST PHASE (${BURST_DURATION}s)${NC}"
    echo ""
    
    # Rotate stress types across pods for variety
    STRESS_TYPE=$((ITERATION % 3))
    
    case $STRESS_TYPE in
        0)
            echo "  Pattern: Memory-intensive"
            run_memory_stress "workload-app-0"
            run_memory_stress "workload-app-1"
            run_memory_stress "workload-app-2"
            ;;
        1)
            echo "  Pattern: CPU-intensive"
            run_cpu_stress "workload-app-0"
            run_cpu_stress "workload-app-1"
            run_cpu_stress "workload-app-2"
            ;;
        2)
            echo "  Pattern: Mixed workload"
            run_mixed_stress "workload-app-0"
            run_mixed_stress "workload-app-1"
            run_mixed_stress "workload-app-2"
            ;;
    esac
    
    # Wait for burst to complete
    echo "  Generating PSI spikes..."
    
    # Show live predictions during burst
    sleep 10
    PRED_COUNT=$(kubectl logs deployment/prediction-service --tail=50 | grep -c "Spike predicted" || echo "0")
    echo "  Predictions so far: ${PRED_COUNT}"
    
    sleep $((BURST_DURATION - 10))
    
    echo -e "  ${GREEN}Burst complete${NC}"
    
    # IDLE PHASE
    echo ""
    echo -e "${YELLOW}⏸  IDLE PHASE (${IDLE_DURATION}s)${NC}"
    echo "  Allowing recovery..."
    
    # Show metrics during idle
    sleep 10
    
    # Quick metrics check
    if command -v curl &> /dev/null; then
        kubectl port-forward service/prediction-service 8080:8080 &> /dev/null &
        PORT_FORWARD_PID=$!
        sleep 2
        
        METRICS=$(curl -s http://localhost:8080/metrics-summary 2>/dev/null || echo "{}")
        if [ "$METRICS" != "{}" ]; then
            PRECISION=$(echo $METRICS | jq -r '.precision' 2>/dev/null || echo "N/A")
            RECALL=$(echo $METRICS | jq -r '.recall' 2>/dev/null || echo "N/A")
            echo "  Current metrics: Precision=${PRECISION}, Recall=${RECALL}"
        fi
        
        kill $PORT_FORWARD_PID 2>/dev/null || true
    fi
    
    sleep $((IDLE_DURATION - 10))
    
    echo -e "  ${YELLOW}Idle complete${NC}"
done

# Test complete
echo ""
echo "=========================================="
echo " Test Complete"
echo "=========================================="
echo ""

TOTAL_TIME=$(($(date +%s) - START_TIME))
echo "Duration: $((TOTAL_TIME / 60))m $((TOTAL_TIME % 60))s"
echo ""

# Show final statistics
echo "Collecting final results..."
echo ""

# Port-forward for metrics
kubectl port-forward service/prediction-service 8080:8080 &> /dev/null &
PORT_FORWARD_PID=$!
sleep 3

echo "=========================================="
echo " Final Results"
echo "=========================================="
echo ""

FINAL_METRICS=$(curl -s http://localhost:8080/metrics-summary 2>/dev/null || echo "{}")

if [ "$FINAL_METRICS" != "{}" ]; then
    echo "$FINAL_METRICS" | jq '.'
    echo ""
    
    PRECISION=$(echo $FINAL_METRICS | jq -r '.precision')
    RECALL=$(echo $FINAL_METRICS | jq -r '.recall')
    
    echo "Summary:"
    echo "  Precision: $(echo "$PRECISION * 100" | bc -l | cut -c1-5)%"
    echo "  Recall:    $(echo "$RECALL * 100" | bc -l | cut -c1-5)%"
    
    # Check if passing
    PREC_PASS=$(echo "$PRECISION >= 0.85" | bc -l)
    REC_PASS=$(echo "$RECALL >= 0.90" | bc -l)
    
    echo ""
    if [ "$PREC_PASS" = "1" ] && [ "$REC_PASS" = "1" ]; then
        echo -e "${GREEN}✅ TEST PASSED - Ready for Phase 7!${NC}"
    else
        echo -e "${YELLOW}⚠️  Results below target - Review needed${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  Could not fetch metrics${NC}"
    echo "Check manually: kubectl logs deployment/prediction-service"
fi

kill $PORT_FORWARD_PID 2>/dev/null || true

echo ""
echo "Next steps:"
echo "  1. Review logs: kubectl logs deployment/prediction-service > phase6-logs.txt"
echo "  2. Generate report: ./collect-phase6-results.sh"
echo "  3. If passed, proceed to Phase 7"
echo ""
