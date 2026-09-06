#!/bin/bash
#
# Monitor 24-hour test progress
# Run this in a separate terminal while test is running
#

# Find latest test results directory
PROJECT_ROOT="/home/kesavan-p/Documents/major project/implementation/Major-Project-Synchronized-Predictive-Orchestration"
LATEST_TEST_DIR=$(ls -td "$PROJECT_ROOT/kubernetes/phase6/test-results-"* 2>/dev/null | head -1)

if [ -z "$LATEST_TEST_DIR" ]; then
    echo "❌ No active test found"
    echo "Start the test first: ./run-24hour-test.sh"
    exit 1
fi

SERVICE_LOG="$LATEST_TEST_DIR/prediction-service.log"
MAIN_LOG="$LATEST_TEST_DIR/test-execution.log"

echo "=========================================="
echo " 24-Hour Test Monitor"
echo "=========================================="
echo "Test directory: $LATEST_TEST_DIR"
echo "Press Ctrl+C to stop monitoring (test continues)"
echo ""

# Initial check
if [ ! -f "$SERVICE_LOG" ]; then
    echo "⚠️  Service log not found yet, waiting..."
    while [ ! -f "$SERVICE_LOG" ]; do
        sleep 5
    done
fi

echo "✅ Monitoring active test..."
echo ""

# Track previous values
PREV_PREDICTIONS=0
PREV_SPIKES=0
MONITOR_START=$(date +%s)

while true; do
    clear
    
    echo "=========================================="
    echo " 24-Hour Test - Live Monitor"
    echo "=========================================="
    echo "Monitoring since: $(date -d @$MONITOR_START '+%H:%M:%S')"
    echo "Current time: $(date '+%Y-%m-%d %H:%M:%S')"
    echo ""
    
    # Get current counts
    PREDICTIONS=$(grep -c "Iteration" "$SERVICE_LOG" 2>/dev/null || echo "0")
    SPIKES=$(grep -c "Spike predicted: True" "$SERVICE_LOG" 2>/dev/null || echo "0")
    
    # Calculate rates
    NEW_PREDICTIONS=$((PREDICTIONS - PREV_PREDICTIONS))
    NEW_SPIKES=$((SPIKES - PREV_SPIKES))
    
    echo "📊 Overall Statistics:"
    echo "  Total Predictions: $PREDICTIONS (+$NEW_PREDICTIONS in last 30s)"
    echo "  Spikes Detected: $SPIKES (+$NEW_SPIKES in last 30s)"
    echo "  Target: 50 spikes"
    echo "  Progress: $(echo "scale=1; $SPIKES * 100 / 50" | bc)%"
    echo ""
    
    # Prediction rate
    if [ $PREDICTIONS -gt 0 ]; then
        RATE=$(echo "scale=1; $PREDICTIONS / (($(date +%s) - $(stat -c %Y "$SERVICE_LOG")) / 60)" | bc 2>/dev/null || echo "N/A")
        echo "  Prediction rate: ~$RATE per minute"
    fi
    
    # Estimate completion
    if [ $SPIKES -gt 5 ]; then
        ELAPSED=$(($(date +%s) - $(stat -c %Y "$SERVICE_LOG")))
        RATE=$(echo "scale=4; $SPIKES / ($ELAPSED / 3600)" | bc)
        if [ "$(echo "$RATE > 0" | bc)" -eq 1 ]; then
            REMAINING_SPIKES=$((50 - SPIKES))
            ETA_HOURS=$(echo "scale=1; $REMAINING_SPIKES / $RATE" | bc)
            echo "  Spike rate: $RATE per hour"
            echo "  ETA to 50 spikes: ~${ETA_HOURS} hours"
        fi
    fi
    
    echo ""
    echo "=========================================="
    echo "📈 Recent Activity (last 10 predictions):"
    echo "=========================================="
    tail -50 "$SERVICE_LOG" | grep -A 4 "Iteration" | tail -40 | while read line; do
        if echo "$line" | grep -q "Iteration"; then
            echo ""
            echo "$line"
        elif echo "$line" | grep -q "Pod workload"; then
            echo "  $line"
        elif echo "$line" | grep -q "Spike predicted: True"; then
            echo "  🔔 $line"
        elif echo "$line" | grep -q "Spike predicted: False"; then
            echo "  $line"
        fi
    done | tail -50
    
    echo ""
    echo "=========================================="
    echo "🔍 Latest Spikes Detected:"
    echo "=========================================="
    grep -B 3 "Spike predicted: True" "$SERVICE_LOG" 2>/dev/null | tail -20 | while read line; do
        if echo "$line" | grep -q "Pod workload"; then
            echo "  $line"
        elif echo "$line" | grep -q "Current PSI"; then
            echo "    $line"
        elif echo "$line" | grep -q "Predicted"; then
            echo "    $line"
        elif echo "$line" | grep -q "Spike predicted: True"; then
            echo "    ✅ $line"
            echo ""
        fi
    done | tail -40
    
    echo ""
    echo "=========================================="
    echo "💻 System Health:"
    echo "=========================================="
    
    # Check service health
    if curl -s http://localhost:8080/health 2>/dev/null | grep -q "healthy"; then
        echo "  ✅ Prediction service: Healthy"
    else
        echo "  ⚠️  Prediction service: Not responding"
    fi
    
    # Check Prometheus
    if curl -s http://localhost:9090/-/healthy 2>/dev/null | grep -q "Prometheus"; then
        echo "  ✅ Prometheus: Healthy"
    else
        echo "  ⚠️  Prometheus: Not responding"
    fi
    
    # Check pods
    PODS_READY=$(kubectl get pods -l app=workload --no-headers 2>/dev/null | grep "Running" | wc -l)
    echo "  ✅ Workload pods: $PODS_READY/3 running"
    
    # Check recent errors
    ERROR_COUNT=$(tail -100 "$SERVICE_LOG" 2>/dev/null | grep -i "error\|exception\|failed" | wc -l)
    if [ $ERROR_COUNT -gt 0 ]; then
        echo "  ⚠️  Recent errors: $ERROR_COUNT (check logs)"
    else
        echo "  ✅ No recent errors"
    fi
    
    echo ""
    echo "=========================================="
    echo "Press Ctrl+C to stop monitoring"
    echo "Test continues in background..."
    echo "Refreshing in 30 seconds..."
    echo "=========================================="
    
    # Update previous values
    PREV_PREDICTIONS=$PREDICTIONS
    PREV_SPIKES=$SPIKES
    
    # Wait before next refresh
    sleep 30
done
