#!/bin/bash
#
# Step 4: Run Prediction Service Continuously
# Native 20-second interval, shadow mode, runs for days
# Designed to run in parallel with Step 3 workload generation
#

set -o pipefail

PROJECT_ROOT="/home/kesavan-p/Documents/major project/implementation/Major-Project-Synchronized-Predictive-Orchestration"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"

# Configuration
DURATION_DAYS=${1:-5}  # Default: 5 days
PREDICTION_INTERVAL=20  # Native interval - DO NOT COMPRESS

# Logging
RUN_ID="continuous-$(date +%Y%m%d_%H%M%S)"
LOG_DIR="$PROJECT_ROOT/kubernetes/phase6/prediction-logs-${RUN_ID}"
mkdir -p "$LOG_DIR"

MAIN_LOG="$LOG_DIR/execution.log"
SERVICE_LOG="$LOG_DIR/predictions.log"
HEALTH_LOG="$LOG_DIR/health.log"
METRICS_FILE="$LOG_DIR/metrics.json"

exec > >(tee -a "$MAIN_LOG") 2>&1

echo "=========================================="
echo " Step 4: Continuous Prediction Service"
echo "=========================================="
echo "Start: $(date)"
echo "Duration: ${DURATION_DAYS} days"
echo "Prediction interval: ${PREDICTION_INTERVAL} seconds (native)"
echo "Mode: Shadow (logging only)"
echo "Log directory: ${LOG_DIR}"
echo ""

# Pre-flight checks
echo "=== Pre-flight Checks ==="

if [ ! -f "$VENV_PYTHON" ]; then
    echo "❌ Python venv not found"
    exit 1
fi
echo "✅ Python venv"

if [ ! -f "$PROJECT_ROOT/models/tft_psi_model.ckpt" ]; then
    echo "❌ Model not found"
    exit 1
fi
echo "✅ Model file"

if ! kubectl get pods -l app=workload &>/dev/null; then
    echo "❌ Workload pods not found"
    exit 1
fi
echo "✅ Workload pods"

if ! kubectl get -n monitoring svc/prometheus-operated &>/dev/null; then
    echo "❌ Prometheus not found"
    exit 1
fi
echo "✅ Prometheus"

echo ""

# Cleanup previous runs
echo "=== Cleanup ==="
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
    echo "❌ Cannot reach Prometheus"
    kill $PROM_PF_PID 2>/dev/null
    exit 1
fi
echo "✅ Prometheus accessible"
echo ""

# Configure service
export PROMETHEUS_URL="http://localhost:9090"
export MODEL_PATH="$PROJECT_ROOT/models/tft_psi_model.ckpt"
export SPIKE_THRESHOLD="1.80"
export PREDICTION_INTERVAL="$PREDICTION_INTERVAL"

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
    echo "❌ Service not healthy"
    tail -50 "$SERVICE_LOG"
    kill $SERVICE_PID $PROM_PF_PID 2>/dev/null
    exit 1
fi
echo "✅ Service healthy (PID: $SERVICE_PID)"
echo ""

# Cleanup function
cleanup() {
    echo ""
    echo "=========================================="
    echo " Stopping Services"
    echo "=========================================="
    
    curl -s http://localhost:8080/metrics-summary > "$METRICS_FILE" 2>/dev/null || echo "{}" > "$METRICS_FILE"
    
    kill $SERVICE_PID 2>/dev/null || true
    kill $PROM_PF_PID 2>/dev/null || true
    kill $HEALTH_PID 2>/dev/null || true
    
    sleep 5
    
    # Generate summary
    TOTAL_PREDS=$(grep -c "Iteration" "$SERVICE_LOG" 2>/dev/null || echo "0")
    TOTAL_SPIKES=$(grep -c "Spike predicted: True" "$SERVICE_LOG" 2>/dev/null || echo "0")
    
    {
        echo "=========================================="
        echo " Continuous Service Run Summary"
        echo "=========================================="
        echo "Run ID: $RUN_ID"
        echo "Start: $(head -1 "$MAIN_LOG" | grep -oP '\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}' || echo "Unknown")"
        echo "End: $(date)"
        echo ""
        echo "Total predictions: $TOTAL_PREDS"
        echo "Spikes detected: $TOTAL_SPIKES"
        echo ""
        echo "Performance metrics:"
        cat "$METRICS_FILE"
        echo ""
        echo "Logs: $LOG_DIR"
        echo "=========================================="
    } | tee "$LOG_DIR/summary.txt"
    
    echo ""
    echo "✅ Service stopped cleanly"
}

trap cleanup EXIT INT TERM

# Health monitoring
monitor_health() {
    while true; do
        {
            echo "[$(date)] Health Check:"
            
            if curl -s http://localhost:8080/health 2>/dev/null | grep -q "healthy"; then
                echo "  ✅ Service: Healthy"
            else
                echo "  ⚠️  Service: Not responding"
            fi
            
            if curl -s http://localhost:9090/-/healthy 2>/dev/null | grep -q "Prometheus"; then
                echo "  ✅ Prometheus: Healthy"
            else
                echo "  ⚠️  Prometheus: Not responding"
            fi
            
            PODS_READY=$(kubectl get pods -l app=workload --no-headers 2>/dev/null | grep "Running" | wc -l)
            echo "  ✅ Workload pods: $PODS_READY/3"
            
            PREDS=$(grep -c "Iteration" "$SERVICE_LOG" 2>/dev/null || echo "0")
            SPIKES=$(grep -c "Spike predicted: True" "$SERVICE_LOG" 2>/dev/null || echo "0")
            echo "  📊 Predictions: $PREDS | Spikes: $SPIKES"
            
            echo ""
        } >> "$HEALTH_LOG"
        
        sleep 300  # Check every 5 minutes
    done
}

monitor_health &
HEALTH_PID=$!

# Main monitoring loop
echo "=========================================="
echo " Service Running"
echo "=========================================="
echo ""
echo "Duration: ${DURATION_DAYS} days"
echo "Prediction interval: ${PREDICTION_INTERVAL} seconds"
echo "Expected predictions: ~$((DURATION_DAYS * 24 * 3600 / PREDICTION_INTERVAL))"
echo ""
echo "Monitor logs:"
echo "  Predictions: tail -f $SERVICE_LOG"
echo "  Health: tail -f $HEALTH_LOG"
echo ""
echo "Hourly progress updates..."
echo ""

START_TIME=$(date +%s)
HOUR_COUNT=0

while true; do
    ELAPSED=$(($(date +%s) - START_TIME))
    ELAPSED_HOURS=$((ELAPSED / 3600))
    
    # Check if duration reached
    if [ $ELAPSED -ge $((DURATION_DAYS * 86400)) ]; then
        echo ""
        echo "✅ ${DURATION_DAYS}-day duration completed!"
        break
    fi
    
    # Hourly update
    if [ $ELAPSED_HOURS -gt $HOUR_COUNT ]; then
        HOUR_COUNT=$ELAPSED_HOURS
        REMAINING_HOURS=$((DURATION_DAYS * 24 - ELAPSED_HOURS))
        
        CURRENT_PREDS=$(grep -c "Iteration" "$SERVICE_LOG" 2>/dev/null || echo "0")
        CURRENT_SPIKES=$(grep -c "Spike predicted: True" "$SERVICE_LOG" 2>/dev/null || echo "0")
        EXPECTED_PREDS=$((ELAPSED / PREDICTION_INTERVAL))
        
        echo "=========================================="
        echo " Hour ${ELAPSED_HOURS}/${DURATION_DAYS}d ($(($DURATION_DAYS * 24))h total)"
        echo "=========================================="
        echo "Elapsed: ${ELAPSED_HOURS}h | Remaining: ${REMAINING_HOURS}h"
        echo "Predictions: ${CURRENT_PREDS}/${EXPECTED_PREDS} expected"
        echo "Spikes: ${CURRENT_SPIKES}"
        
        if curl -s http://localhost:8080/health 2>/dev/null | grep -q "healthy"; then
            echo "Status: ✅ Healthy"
        else
            echo "Status: ⚠️  May be restarting"
        fi
        echo ""
    fi
    
    sleep 60
done

# Cleanup will be called by trap
echo ""
echo "=========================================="
echo " ${DURATION_DAYS}-Day Run Complete"
echo "=========================================="
