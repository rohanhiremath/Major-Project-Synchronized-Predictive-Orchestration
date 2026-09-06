#!/bin/bash
#
# Phase 6: 24-Hour Production Validation Test
# Target: 50+ PSI spikes for paper submission
# Robust design with error recovery and monitoring
#

set -o pipefail

PROJECT_ROOT="/home/kesavan-p/Documents/major project/implementation/Major-Project-Synchronized-Predictive-Orchestration"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"

# Test configuration
TEST_DURATION_HOURS=24
SPIKE_TARGET=50

# Workload patterns (in seconds)
SPIKE_BURST_DURATION=180      # 3 minutes of high stress
SPIKE_RECOVERY_DURATION=300   # 5 minutes recovery
SPIKE_CYCLE=$((SPIKE_BURST_DURATION + SPIKE_RECOVERY_DURATION))  # 8 minutes per cycle

# Calculate required cycles for 50+ spikes
TOTAL_CYCLES=$((TEST_DURATION_HOURS * 3600 / SPIKE_CYCLE))
EXPECTED_SPIKES=$((TOTAL_CYCLES * 3 / 4))  # Conservative estimate (75% success rate)

# Logging
TEST_START_TIME=$(date +"%Y%m%d_%H%M%S")
LOG_DIR="$PROJECT_ROOT/kubernetes/phase6/test-results-${TEST_START_TIME}"
mkdir -p "$LOG_DIR"

MAIN_LOG="$LOG_DIR/test-execution.log"
SERVICE_LOG="$LOG_DIR/prediction-service.log"
METRICS_FILE="$LOG_DIR/metrics.json"
SUMMARY_FILE="$LOG_DIR/test-summary.txt"
SPIKES_LOG="$LOG_DIR/detected-spikes.log"

exec > >(tee -a "$MAIN_LOG") 2>&1

echo "=========================================="
echo " 24-Hour Production Validation Test"
echo "=========================================="
echo "Start Time: $(date)"
echo "Duration: ${TEST_DURATION_HOURS} hours"
echo "Target Spikes: ${SPIKE_TARGET}+"
echo "Expected Spikes: ~${EXPECTED_SPIKES}"
echo "Total Cycles: ${TOTAL_CYCLES}"
echo "Log Directory: ${LOG_DIR}"
echo ""

# Validation checks
echo "=== Pre-flight Checks ==="

# Check Python venv
if [ ! -f "$VENV_PYTHON" ]; then
    echo "❌ ERROR: Python venv not found at $VENV_PYTHON"
    exit 1
fi
echo "✅ Python venv found"

# Check model
if [ ! -f "$PROJECT_ROOT/models/tft_psi_model.ckpt" ]; then
    echo "❌ ERROR: Model file not found"
    exit 1
fi
echo "✅ Model file found"

# Check Kubernetes
if ! kubectl get pods -l app=workload &>/dev/null; then
    echo "❌ ERROR: Workload pods not found"
    exit 1
fi
WORKLOAD_PODS=$(kubectl get pods -l app=workload --no-headers | wc -l)
echo "✅ Workload pods: ${WORKLOAD_PODS}"

# Check Prometheus
if ! kubectl get -n monitoring svc/prometheus-operated &>/dev/null; then
    echo "❌ ERROR: Prometheus service not found"
    exit 1
fi
echo "✅ Prometheus found"

echo ""

# Cleanup any previous runs
echo "=== Cleanup ==="
pkill -f "prediction_service.py" 2>/dev/null || true
pkill -f "port-forward.*9090" 2>/dev/null || true
pkill -f "memory-eater" 2>/dev/null || true
sleep 3
echo "✅ Previous processes cleaned"
echo ""

# Start Prometheus port-forward with auto-restart
echo "=== Starting Prometheus Port-Forward ==="
(
  while true; do
    kubectl port-forward -n monitoring svc/prometheus-operated 9090:9090 2>&1 | tee -a "$LOG_DIR/prometheus-pf.log"
    echo "Port-forward died, restarting in 5s..." | tee -a "$LOG_DIR/prometheus-pf.log"
    sleep 5
  done
) &
PROM_PF_PID=$!
sleep 8

# Verify Prometheus connectivity
if ! curl -s http://localhost:9090/api/v1/query?query=up | grep -q "success"; then
    echo "❌ ERROR: Cannot reach Prometheus"
    kill $PROM_PF_PID 2>/dev/null
    exit 1
fi
echo "✅ Prometheus accessible"
echo ""

# Configure prediction service
export PROMETHEUS_URL="http://localhost:9090"
export MODEL_PATH="$PROJECT_ROOT/models/tft_psi_model.ckpt"
export SPIKE_THRESHOLD="1.80"
export PREDICTION_INTERVAL="20"

# Start prediction service with auto-restart
echo "=== Starting Prediction Service ==="
cd "$PROJECT_ROOT/kubernetes/phase6"

(
  while true; do
    echo "[$(date)] Starting prediction service..." | tee -a "$SERVICE_LOG"
    "$VENV_PYTHON" prediction_service.py 2>&1 | tee -a "$SERVICE_LOG"
    EXIT_CODE=$?
    echo "[$(date)] Service exited with code $EXIT_CODE" | tee -a "$SERVICE_LOG"
    
    # Don't restart if manually stopped
    if [ $EXIT_CODE -eq 143 ] || [ $EXIT_CODE -eq 130 ]; then
        echo "Service stopped manually" | tee -a "$SERVICE_LOG"
        break
    fi
    
    echo "Service died, restarting in 10s..." | tee -a "$SERVICE_LOG"
    sleep 10
  done
) &
SERVICE_PID=$!
sleep 15

# Verify service is running
if ! curl -s http://localhost:8080/health | grep -q "healthy"; then
    echo "❌ ERROR: Prediction service not healthy"
    tail -50 "$SERVICE_LOG"
    kill $SERVICE_PID $PROM_PF_PID 2>/dev/null
    exit 1
fi
echo "✅ Prediction service healthy (PID: $SERVICE_PID)"
echo ""

# Graceful cleanup function
cleanup() {
    echo ""
    echo "=========================================="
    echo " Test Stopping - Generating Report"
    echo "=========================================="
    
    # Get final metrics
    curl -s http://localhost:8080/metrics-summary > "$METRICS_FILE" 2>/dev/null || echo "{}" > "$METRICS_FILE"
    
    # Stop services
    echo "Stopping prediction service..."
    kill $SERVICE_PID 2>/dev/null || true
    
    echo "Stopping Prometheus port-forward..."
    kill $PROM_PF_PID 2>/dev/null || true
    
    # Stop any lingering memory stress
    for POD in workload-app-0 workload-app-1 workload-app-2; do
        kubectl exec $POD -c app -- pkill -f "memory-eater" 2>/dev/null || true
    done
    
    sleep 5
    
    # Generate summary
    echo "=========================================="  | tee "$SUMMARY_FILE"
    echo " 24-Hour Test Summary"                       | tee -a "$SUMMARY_FILE"
    echo "=========================================="  | tee -a "$SUMMARY_FILE"
    echo "Start: $TEST_START_TIME"                    | tee -a "$SUMMARY_FILE"
    echo "End: $(date +"%Y%m%d_%H%M%S")"              | tee -a "$SUMMARY_FILE"
    echo ""                                            | tee -a "$SUMMARY_FILE"
    
    TOTAL_PREDICTIONS=$(grep -c "Iteration" "$SERVICE_LOG" 2>/dev/null || echo "0")
    SPIKES_DETECTED=$(grep -c "Spike predicted: True" "$SERVICE_LOG" 2>/dev/null || echo "0")
    
    echo "Predictions Made: $TOTAL_PREDICTIONS"       | tee -a "$SUMMARY_FILE"
    echo "Spikes Detected: $SPIKES_DETECTED"          | tee -a "$SUMMARY_FILE"
    echo "Target: ${SPIKE_TARGET}+"                   | tee -a "$SUMMARY_FILE"
    echo ""                                            | tee -a "$SUMMARY_FILE"
    
    if [ -f "$METRICS_FILE" ]; then
        echo "Performance Metrics:"                    | tee -a "$SUMMARY_FILE"
        cat "$METRICS_FILE"                            | tee -a "$SUMMARY_FILE"
        echo ""                                        | tee -a "$SUMMARY_FILE"
    fi
    
    # Extract spike details
    grep -B2 "Spike predicted: True" "$SERVICE_LOG" > "$SPIKES_LOG" 2>/dev/null || true
    SPIKE_LINES=$(wc -l < "$SPIKES_LOG" 2>/dev/null || echo "0")
    echo "Spike details: ${SPIKE_LINES} lines in $SPIKES_LOG" | tee -a "$SUMMARY_FILE"
    echo ""                                            | tee -a "$SUMMARY_FILE"
    
    echo "=========================================="  | tee -a "$SUMMARY_FILE"
    echo "Log files:"                                 | tee -a "$SUMMARY_FILE"
    echo "  Main log: $MAIN_LOG"                      | tee -a "$SUMMARY_FILE"
    echo "  Service log: $SERVICE_LOG"                | tee -a "$SUMMARY_FILE"
    echo "  Metrics: $METRICS_FILE"                   | tee -a "$SUMMARY_FILE"
    echo "  Spikes: $SPIKES_LOG"                      | tee -a "$SUMMARY_FILE"
    echo "=========================================="  | tee -a "$SUMMARY_FILE"
    
    # Success check
    if [ "$SPIKES_DETECTED" -ge "$SPIKE_TARGET" ]; then
        echo "✅ SUCCESS: Target achieved ($SPIKES_DETECTED >= $SPIKE_TARGET)" | tee -a "$SUMMARY_FILE"
    else
        echo "⚠️  Target not reached: $SPIKES_DETECTED < $SPIKE_TARGET" | tee -a "$SUMMARY_FILE"
    fi
    
    echo ""
    echo "Test complete. Results saved to: $LOG_DIR"
}

trap cleanup EXIT INT TERM

# Memory stress function using shell memory allocation
# This method holds actual data in memory (not just files)
generate_memory_spike() {
    local POD=$1
    local MEMORY_MB=$2
    local DURATION=$3
    
    # Create actual memory pressure by holding data in shell variables
    kubectl exec $POD -c app -- sh -c "
        # Kill any existing stress
        pkill -f 'memory-stress' 2>/dev/null || true
        rm -f /tmp/mem-stress.sh 2>/dev/null || true
        
        # Create memory stress script
        cat > /tmp/mem-stress.sh << 'EOFSCRIPT'
#!/bin/sh
# Hold memory in shell variables
i=0
target=${MEMORY_MB}
while [ \$i -lt \$target ]; do
    # Create 1MB data blocks in memory
    data=\$(dd if=/dev/zero bs=1024 count=1024 2>/dev/null | base64)
    eval \"mem_\$i=\\\"\$data\\\"\"
    i=\$((i + 1))
    
    # Progress every 100MB
    if [ \$((i % 100)) -eq 0 ]; then
        echo \"Allocated \${i}MB...\" >&2
    fi
done
echo \"Holding \${target}MB for ${DURATION}s...\" >&2
sleep ${DURATION}
echo \"Releasing memory...\" >&2
EOFSCRIPT
        
        chmod +x /tmp/mem-stress.sh
        
        # Run in background with memory target
        (
            exec -a memory-stress sh -c \"MEMORY_MB=${MEMORY_MB} /tmp/mem-stress.sh\" &
        ) &
        
        echo \"Started memory stress on ${POD}: ${MEMORY_MB}MB for ${DURATION}s\"
    " &>/dev/null &
}

# Start test loop
echo "=========================================="
echo " Starting 24-Hour Test Loop"
echo "=========================================="
echo ""

TEST_START_EPOCH=$(date +%s)
CYCLE_COUNT=0

while true; do
    CURRENT_EPOCH=$(date +%s)
    ELAPSED_SECONDS=$((CURRENT_EPOCH - TEST_START_EPOCH))
    ELAPSED_HOURS=$((ELAPSED_SECONDS / 3600))
    ELAPSED_MINUTES=$(((ELAPSED_SECONDS % 3600) / 60))
    
    # Check if 24 hours elapsed
    if [ $ELAPSED_SECONDS -ge $((TEST_DURATION_HOURS * 3600)) ]; then
        echo "✅ 24-hour test duration completed!"
        break
    fi
    
    CYCLE_COUNT=$((CYCLE_COUNT + 1))
    REMAINING_SECONDS=$((TEST_DURATION_HOURS * 3600 - ELAPSED_SECONDS))
    REMAINING_HOURS=$((REMAINING_SECONDS / 3600))
    REMAINING_MINUTES=$(((REMAINING_SECONDS % 3600) / 60))
    
    # Get current stats
    CURRENT_PREDICTIONS=$(grep -c "Iteration" "$SERVICE_LOG" 2>/dev/null || echo "0")
    CURRENT_SPIKES=$(grep -c "Spike predicted: True" "$SERVICE_LOG" 2>/dev/null || echo "0")
    
    echo "=========================================="
    echo " Cycle ${CYCLE_COUNT}/${TOTAL_CYCLES}"
    echo " Elapsed: ${ELAPSED_HOURS}h ${ELAPSED_MINUTES}m | Remaining: ${REMAINING_HOURS}h ${REMAINING_MINUTES}m"
    echo " Predictions: ${CURRENT_PREDICTIONS} | Spikes: ${CURRENT_SPIKES}/${SPIKE_TARGET}"
    echo "=========================================="
    
    # Health check
    if ! curl -s http://localhost:8080/health | grep -q "healthy"; then
        echo "⚠️  Service health check failed - may be restarting..."
        sleep 10
        continue
    fi
    
    # SPIKE PHASE - Generate high memory pressure
    echo "▶ SPIKE: Generating memory pressure (${SPIKE_BURST_DURATION}s)..."
    
    # Stagger pod stress to create varied patterns
    generate_memory_spike "workload-app-0" 800 $SPIKE_BURST_DURATION
    sleep 5
    generate_memory_spike "workload-app-1" 600 $SPIKE_BURST_DURATION
    sleep 5
    generate_memory_spike "workload-app-2" 700 $SPIKE_BURST_DURATION
    
    echo "  Memory stress initiated on all 3 pods"
    echo "  Monitoring for ${SPIKE_BURST_DURATION}s..."
    
    # Monitor during burst
    for i in $(seq 1 $((SPIKE_BURST_DURATION / 30))); do
        sleep 30
        NEW_SPIKES=$(grep -c "Spike predicted: True" "$SERVICE_LOG" 2>/dev/null || echo "0")
        if [ "$NEW_SPIKES" -gt "$CURRENT_SPIKES" ]; then
            echo "  🔔 SPIKE DETECTED! (Total: $NEW_SPIKES)"
            CURRENT_SPIKES=$NEW_SPIKES
        fi
    done
    
    # RECOVERY PHASE
    echo "⏸  RECOVERY: Cooling down (${SPIKE_RECOVERY_DURATION}s)..."
    
    # Ensure cleanup
    for POD in workload-app-0 workload-app-1 workload-app-2; do
        kubectl exec $POD -c app -- sh -c "pkill -f 'memory-eater' 2>/dev/null; rm -f /tmp/mem_* 2>/dev/null" &>/dev/null || true
    done
    
    # Wait for recovery with progress updates
    for i in $(seq 1 $((SPIKE_RECOVERY_DURATION / 60))); do
        sleep 60
        echo "  Recovery: $((i * 60))/${SPIKE_RECOVERY_DURATION}s"
    done
    
    # Status update
    FINAL_PREDICTIONS=$(grep -c "Iteration" "$SERVICE_LOG" 2>/dev/null || echo "0")
    FINAL_SPIKES=$(grep -c "Spike predicted: True" "$SERVICE_LOG" 2>/dev/null || echo "0")
    echo "  Cycle complete: Predictions=${FINAL_PREDICTIONS}, Spikes=${FINAL_SPIKES}"
    echo ""
    
    # Check if we hit target early
    if [ "$FINAL_SPIKES" -ge "$SPIKE_TARGET" ]; then
        echo "🎉 Target of ${SPIKE_TARGET} spikes reached!"
        echo "   Continuing test to gather more data..."
    fi
done

echo ""
echo "=========================================="
echo " 24-Hour Test Complete!"
echo "=========================================="
echo "Total cycles executed: $CYCLE_COUNT"
echo ""

# Cleanup will be called by trap
