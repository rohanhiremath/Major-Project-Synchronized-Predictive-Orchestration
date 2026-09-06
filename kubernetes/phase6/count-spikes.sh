#!/bin/bash
#
# Step 5: Count Spikes - Track progress toward 100-200 spike target
# Run this daily to check progress
#

echo "=========================================="
echo " Step 5: Spike Count Progress"
echo "=========================================="
echo "Date: $(date)"
echo ""

# Target
TARGET_MIN=100
TARGET_MAX=200

# Count historical spikes
HISTORICAL_DIR="historical-data"
if [ -f "$HISTORICAL_DIR/spike_events_53_events.csv" ]; then
    HISTORICAL_SPIKES=53
    echo "✅ Historical spikes (Step 2): $HISTORICAL_SPIKES"
elif [ -f "$HISTORICAL_DIR/metadata.json" ]; then
    HISTORICAL_SPIKES=$(python3 -c "import json; print(json.load(open('$HISTORICAL_DIR/metadata.json'))['spikes']['distinct_events'])" 2>/dev/null || echo 0)
    echo "✅ Historical spikes (Step 2): $HISTORICAL_SPIKES"
else
    HISTORICAL_SPIKES=0
    echo "⚠️  No historical data found (will be collected)"
fi

# Count new spikes from prediction service
NEW_SPIKES=0
PREDICTION_LOGS=$(find prediction-logs-* -name "predictions.log" 2>/dev/null | sort)

if [ -z "$PREDICTION_LOGS" ]; then
    echo "⚠️  No prediction service logs found yet"
    echo "   Start service with: ./run-continuous-prediction-service.sh"
else
    for log in $PREDICTION_LOGS; do
        spikes=$(grep -c "Spike predicted: True" "$log" 2>/dev/null || echo "0")
        NEW_SPIKES=$((NEW_SPIKES + spikes))
        
        run_id=$(basename $(dirname "$log"))
        predictions=$(grep -c "Iteration" "$log" 2>/dev/null || echo "0")
        echo "  $run_id: $spikes spikes ($predictions predictions)"
    done
    echo "✅ New spikes (Step 4): $NEW_SPIKES"
fi

# Total
TOTAL_SPIKES=$((HISTORICAL_SPIKES + NEW_SPIKES))

echo ""
echo "=========================================="
echo " Total Spike Count"
echo "=========================================="
echo ""
echo "Historical (Step 2):  $HISTORICAL_SPIKES"
echo "New (Step 4):         $NEW_SPIKES"
echo "─────────────────────────────────────────"
echo "TOTAL:                $TOTAL_SPIKES"
echo ""
echo "Target range:         $TARGET_MIN - $TARGET_MAX"
echo ""

# Progress bar
PROGRESS=$((TOTAL_SPIKES * 100 / TARGET_MAX))
PROGRESS_BAR=""
for i in $(seq 1 50); do
    if [ $((i * 2)) -le $PROGRESS ]; then
        PROGRESS_BAR="${PROGRESS_BAR}█"
    else
        PROGRESS_BAR="${PROGRESS_BAR}░"
    fi
done

echo "Progress: [$PROGRESS_BAR] ${PROGRESS}%"
echo ""

# Status
if [ $TOTAL_SPIKES -ge $TARGET_MAX ]; then
    echo "🎉 EXCELLENT: Exceeded target! ($TOTAL_SPIKES >= $TARGET_MAX)"
    echo "   You can stop collection and proceed to analysis."
elif [ $TOTAL_SPIKES -ge $TARGET_MIN ]; then
    echo "✅ SUCCESS: Target reached! ($TOTAL_SPIKES >= $TARGET_MIN)"
    echo "   Can stop now or continue for stronger results."
else
    REMAINING=$((TARGET_MIN - TOTAL_SPIKES))
    echo "⏳ IN PROGRESS: $REMAINING more spikes needed for minimum target"
    echo "   Keep running workload generation and prediction service."
fi

echo ""
echo "=========================================="
echo " Scenario Diversity Check"
echo "=========================================="

# Check workload logs for scenario coverage
WORKLOAD_LOGS=$(find workload-logs-* -name "workload-execution.log" 2>/dev/null | head -1)

if [ -f "$WORKLOAD_LOGS" ]; then
    echo ""
    echo "Scenarios executed:"
    grep "▶ SCENARIO" "$WORKLOAD_LOGS" | awk '{print $3, $4, $5}' | sort | uniq -c | while read count scenario; do
        echo "  $scenario: $count times"
    done
else
    echo "⚠️  No workload logs found"
    echo "   Start with: ./multi-scenario-workload.sh"
fi

echo ""
echo "=========================================="
echo " Recommendations"
echo "=========================================="
echo ""

if [ $TOTAL_SPIKES -lt $TARGET_MIN ]; then
    echo "📋 Actions:"
    echo "1. Keep prediction service running"
    echo "2. Keep workload scenarios running"
    echo "3. Run this script daily: ./count-spikes.sh"
    echo "4. Check logs: tail -f prediction-logs-*/predictions.log"
elif [ $TOTAL_SPIKES -lt $TARGET_MAX ]; then
    echo "📋 Options:"
    echo "1. Stop now ($TOTAL_SPIKES spikes is sufficient for paper)"
    echo "2. Continue to $TARGET_MAX for stronger results"
    echo "3. Proceed to analysis: ./analyze-all-results.sh"
else
    echo "📋 Next steps:"
    echo "1. Stop workload generation (Ctrl+C in that terminal)"
    echo "2. Stop prediction service (Ctrl+C in that terminal)"
    echo "3. Analyze results: ./analyze-all-results.sh"
    echo "4. Proceed to Step 7: Generate paper tables"
fi

echo ""

# Save progress to file
PROGRESS_FILE="spike-progress.txt"
{
    echo "Date: $(date)"
    echo "Historical: $HISTORICAL_SPIKES"
    echo "New: $NEW_SPIKES"
    echo "Total: $TOTAL_SPIKES"
    echo "Target: $TARGET_MIN-$TARGET_MAX"
    echo "Status: $((PROGRESS))%"
} >> "$PROGRESS_FILE"

echo "Progress logged to: $PROGRESS_FILE"
echo ""
