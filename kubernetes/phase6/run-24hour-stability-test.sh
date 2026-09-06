#!/bin/bash
#
# 24-Hour Stability Test - Production Validation
# Monitors natural PSI patterns, validates service reliability
# More realistic for paper than artificial spike generation
#

set -o pipefail

PROJECT_ROOT="/home/kesavan-p/Documents/major project/implementation/Major-Project-Synchronized-Predictive-Orchestration"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"

# Test configuration
TEST_DURATION_HOURS=24
PREDICTION_INTERVAL=20  # seconds

# Calculate expected predictions
TOTAL_PREDICTIONS=$((TEST_DURATION_HOURS * 3600 / PREDICTION_INTERVAL))

# Logging
TEST_START_TIME=$(date +"%Y%m%d_%H%M%S")
LOG_DIR="$PROJECT_ROOT/kubernetes/phase6/stability-test-${TEST_START_TIME}"
mkdir -p "$LOG_DIR"

MAIN_LOG="$LOG_DIR/test-execution.log"
SERVICE_LOG="$LOG_DIR/prediction-service.log"
METRICS_FILE="$LOG_DIR/metrics.json"
SUMMARY_FILE="$LOG_DIR/test-summary.txt"
HEALTH_LOG="$LOG_DIR/health-checks.log"

exec > >(tee -a "$MAIN_LOG") 2>&1

echo "=========================================="
echo " 24-Hour Stability & Production Validation"
echo "=========================================="
echo "Start Time: $(date)"
echo "Duration: ${TEST_DURATION_HOURS} hours"
echo "Expected Predictions: ~${TOTAL_PREDICTIONS}"
echo "Mode: Natural PSI monitoring (realistic)"
echo "Log Directory: ${LOG_DIR}"
echo ""

# Validation checks
echo "=== Pre-flight Checks ==="

if [ ! -f "$VENV_PYTHON" ]; then
    echo "❌ ERROR: Python venv not found"
    exit 1
fi
echo "✅ Python venv: $VENV_PYTHON"

if [ ! -f "$PROJECT_ROOT/models/tft_psi_model.ckpt" ]; then
    echo "❌ ERROR: Model file not found"
    exit 1
fi
echo "✅ Model file found"

if ! kubectl get pods -l app=workload &>/dev/null; then
    echo "❌ ERROR: Workload pods not found"
    exit 1
fi
WORKLOAD_PODS=$(kubectl get pods -l app=workload --no-headers | wc -l)
echo "✅ Workload pods: ${WORKLOAD_PODS}"

if ! kubectl get -n monitoring svc/prometheus-operated &>/dev/null; then
    echo "❌ ERROR: Prometheus not found"
    exit 1
fi
echo "✅ Prometheus found"

echo ""

# Cleanup
echo "=== Cleanup Previous Runs ==="
pkill -f "prediction_service.py" 2>/dev/null || true
pkill -f "port-forward.*9090" 2>/dev/null || true
sleep 3
echo "✅ Cleanup complete"
echo ""

# Start Prometheus port-forward with auto-restart
echo "=== Starting Prometheus Port-Forward ==="
(
  while true; do
    kubectl port-forward -n monitoring svc/prometheus-operated 9090:9090 2>&1 | tee -a "$LOG_DIR/prometheus-pf.log"
    echo "[$(date)] Port-forward died, restarting..." | tee -a "$LOG_DIR/prometheus-pf.log"
    sleep 5
  done
) &
PROM_PF_PID=$!
sleep 8

if ! curl -s http://localhost:9090/api/v1/query?query=up | grep -q "success"; then
    echo "❌ ERROR: Cannot reach Prometheus"
    kill $PROM_PF_PID 2>/dev/null
    exit 1
fi
echo "✅ Prometheus accessible on localhost:9090"
echo ""

# Configure service
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

if ! curl -s http://localhost:8080/health | grep -q "healthy"; then
    echo "❌ ERROR: Prediction service not healthy"
    tail -50 "$SERVICE_LOG"
    kill $SERVICE_PID $PROM_PF_PID 2>/dev/null
    exit 1
fi
echo "✅ Prediction service healthy (PID: $SERVICE_PID)"
echo ""

# Cleanup function
cleanup() {
    echo ""
    echo "=========================================="
    echo " Test Complete - Generating Report"
    echo "=========================================="
    
    # Get final metrics
    curl -s http://localhost:8080/metrics-summary > "$METRICS_FILE" 2>/dev/null || echo "{}" > "$METRICS_FILE"
    
    # Stop services
    echo "Stopping services..."
    kill $SERVICE_PID 2>/dev/null || true
    kill $PROM_PF_PID 2>/dev/null || true
    sleep 5
    
    # Generate summary
    TOTAL_PREDICTIONS=$(grep -c "Iteration" "$SERVICE_LOG" 2>/dev/null || echo "0")
    SPIKES_DETECTED=$(grep -c "Spike predicted: True" "$SERVICE_LOG" 2>/dev/null || echo "0")
    
    {
        echo "=========================================="
        echo " 24-Hour Stability Test Summary"
        echo "=========================================="
        echo "Start: $(date -d @$(stat -c %Y "$SERVICE_LOG" 2>/dev/null || echo $(date +%s)) '+%Y-%m-%d %H:%M:%S')"
        echo "End: $(date '+%Y-%m-%d %H:%M:%S')"
        echo ""
        echo "Predictions Made: $TOTAL_PREDICTIONS (target: $TOTAL_PREDICTIONS)"
        echo "Spikes Detected: $SPIKES_DETECTED"
        echo ""
        echo "Performance Metrics:"
        cat "$METRICS_FILE"
        echo ""
        echo "=========================================="
        echo "Success: Test completed"
        echo "=========================================="
    } | tee "$SUMMARY_FILE"
    
    echo ""
    echo "Results saved to: $LOG_DIR"
}

trap cleanup EXIT INT TERM

# Health monitoring function
monitor_health() {
    while true; do
        {
            echo "[$(date)] Health Check:"
            
            # Service health
            if curl -s http://localhost:8080/health 2>/dev/null | grep -q "healthy"; then
                echo "  ✅ Service: Healthy"
            else
                echo "  ⚠️  Service: Not responding"
            fi
            
            # Prometheus health
            if curl -s http://localhost:9090/-/healthy 2>/dev/null | grep -q "Prometheus"; then
                echo "  ✅ Prometheus: Healthy"
            else
                echo "  ⚠️  Prometheus: Not responding"
            fi
            
            # Workload pods
            PODS_READY=$(kubectl get pods -l app=workload --no-headers 2>/dev/null | grep "Running" | wc -l)
            echo "  ✅ Workload pods: $PODS_READY/3"
            
            # Current stats
            CURRENT_PREDS=$(grep -c "Iteration" "$SERVICE_LOG" 2>/dev/null || echo "0")
            CURRENT_SPIKES=$(grep -c "Spike predicted: True" "$SERVICE_LOG" 2>/dev/null || echo "0")
            echo "  📊 Predictions: $CURRENT_PREDS | Spikes: $CURRENT_SPIKES"
            
            echo ""
        } >> "$HEALTH_LOG"
        
        sleep 300  # Health check every 5 minutes
    done
}

# Start health monitoring in background
monitor_health &
HEALTH_PID=$!

# Main test loop - just wait and monitor
echo "=========================================="
echo " Test Running - Monitoring for ${TEST_DURATION_HOURS} Hours"
echo "=========================================="
echo ""
echo "Service is making predictions every ${PREDICTION_INTERVAL} seconds"
echo "Monitoring natural PSI patterns from workload pods"
echo "No artificial spike generation (realistic production scenario)"
echo ""
echo "Progress updates every hour..."
echo ""

TEST_START_EPOCH=$(date +%s)
HOUR_COUNT=0

while true; do
    CURRENT_EPOCH=$(date +%s)
    ELAPSED_SECONDS=$((CURRENT_EPOCH - TEST_START_EPOCH))
    ELAPSED_HOURS=$((ELAPSED_SECONDS / 3600))
    
    # Check if test duration reached
    if [ $ELAPSED_SECONDS -ge $((TEST_DURATION_HOURS * 3600)) ]; then
        echo ""
        echo "✅ 24-hour test duration completed!"
        break
    fi
    
    # Hourly progress update
    if [ $ELAPSED_HOURS -gt $HOUR_COUNT ]; then
        HOUR_COUNT=$ELAPSED_HOURS
        REMAINING_HOURS=$((TEST_DURATION_HOURS - ELAPSED_HOURS))
        
        CURRENT_PREDICTIONS=$(grep -c "Iteration" "$SERVICE_LOG" 2>/dev/null || echo "0")
        CURRENT_SPIKES=$(grep -c "Spike predicted: True" "$SERVICE_LOG" 2>/dev/null || echo "0")
        EXPECTED_PREDS=$((ELAPSED_HOURS * 3600 / PREDICTION_INTERVAL))
        
        echo "=========================================="
        echo " Hour ${ELAPSED_HOURS}/${TEST_DURATION_HOURS}"
        echo "=========================================="
        echo "Elapsed: ${ELAPSED_HOURS}h | Remaining: ${REMAINING_HOURS}h"
        echo "Predictions: ${CURRENT_PREDICTIONS}/${EXPECTED_PREDS} expected"
        echo "Spikes detected: ${CURRENT_SPIKES}"
        
        # Health check
        if curl -s http://localhost:8080/health 2>/dev/null | grep -q "healthy"; then
            echo "Status: ✅ Service healthy"
        else
            echo "Status: ⚠️  Service may be restarting"
        fi
        echo ""
    fi
    
    # Sleep 1 minute between checks
    sleep 60
done

# Stop health monitoring
kill $HEALTH_PID 2>/dev/null || true

echo ""
echo "=========================================="
echo " 24-Hour Test Complete!"
echo "=========================================="
echo "Total runtime: ${TEST_DURATION_HOURS} hours"
echo ""

# Cleanup will be called by trap
