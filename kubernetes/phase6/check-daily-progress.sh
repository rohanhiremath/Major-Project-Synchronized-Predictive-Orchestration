#!/bin/bash
#
# Daily Progress Check: Spikes and Scenario Coverage
#

echo "=========================================="
echo " Daily Progress Check"
echo "=========================================="
echo "Date: $(date)"
echo ""

# Check if services are running
echo "=== Service Status ==="
if ps aux | grep -q "[m]ulti-scenario-workload"; then
    echo "✅ Workload generation: Running"
else
    echo "❌ Workload generation: NOT RUNNING"
fi

if ps aux | grep -q "[p]rediction_service.py"; then
    echo "✅ Prediction service: Running"
else
    echo "❌ Prediction service: NOT RUNNING"
fi
echo ""

# Find latest logs
WORKLOAD_LOG=$(find workload-logs-* -name "workload-execution.log" 2>/dev/null | sort | tail -1)
PREDICTION_LOG=$(find prediction-logs-* -name "predictions.log" 2>/dev/null | sort | tail -1)

if [ -z "$WORKLOAD_LOG" ]; then
    echo "⚠️  No workload logs found"
    exit 1
fi

if [ -z "$PREDICTION_LOG" ]; then
    echo "⚠️  No prediction logs found"
    exit 1
fi

# Count predictions and spikes
TOTAL_PREDICTIONS=$(grep -c "Iteration" "$PREDICTION_LOG" 2>/dev/null || echo "0")
TOTAL_SPIKES=$(grep -c "Spike predicted: True" "$PREDICTION_LOG" 2>/dev/null || echo "0")

echo "=== Prediction Statistics ==="
echo "Total predictions: $TOTAL_PREDICTIONS"
echo "Spikes detected: $TOTAL_SPIKES"
echo ""

# Scenario coverage analysis
echo "=== Scenario Coverage ==="
echo ""
echo "Scenarios executed (by frequency):"
grep "▶ SCENARIO" "$WORKLOAD_LOG" | awk '{print $3, $4, $5}' | sort | uniq -c | sort -rn

echo ""
echo "Scenarios with spikes detected:"
echo ""

# For each scenario, count spikes during that time
declare -A scenario_spikes
scenario_names=("SCENARIO 1" "SCENARIO 2" "SCENARIO 3" "SCENARIO 4" "SCENARIO 5" "SCENARIO 6")

for scenario in "${scenario_names[@]}"; do
    count=$(grep "$scenario" "$WORKLOAD_LOG" | wc -l)
    if [ $count -gt 0 ]; then
        scenario_name=$(grep "$scenario" "$WORKLOAD_LOG" | head -1 | awk '{print $3, $4, $5}')
        echo "  $scenario_name: $count times"
    fi
done

echo ""
echo "=== Spike Distribution by Time ==="
if [ $TOTAL_SPIKES -gt 0 ]; then
    # Show spike timestamps
    grep "Spike predicted: True" "$PREDICTION_LOG" | head -1 | awk '{print "First spike: " $1, $2}'
    grep "Spike predicted: True" "$PREDICTION_LOG" | tail -1 | awk '{print "Last spike:  " $1, $2}'
    
    # Spikes per hour
    echo ""
    echo "Spikes by hour:"
    grep "Spike predicted: True" "$PREDICTION_LOG" | awk '{print $1, $2}' | cut -d: -f1 | sort | uniq -c
else
    echo "No spikes detected yet"
fi

echo ""
echo "=== Recommendations ==="
echo ""

# Scenario balance check
scenario_1=$(grep "SCENARIO 1" "$WORKLOAD_LOG" | wc -l)
scenario_2=$(grep "SCENARIO 2" "$WORKLOAD_LOG" | wc -l)
scenario_3=$(grep "SCENARIO 3" "$WORKLOAD_LOG" | wc -l)
scenario_4=$(grep "SCENARIO 4" "$WORKLOAD_LOG" | wc -l)
scenario_5=$(grep "SCENARIO 5" "$WORKLOAD_LOG" | wc -l)
scenario_6=$(grep "SCENARIO 6" "$WORKLOAD_LOG" | wc -l)

max_scenario=$(echo -e "$scenario_1\n$scenario_2\n$scenario_3\n$scenario_4\n$scenario_5\n$scenario_6" | sort -n | tail -1)
min_scenario=$(echo -e "$scenario_1\n$scenario_2\n$scenario_3\n$scenario_4\n$scenario_5\n$scenario_6" | sort -n | head -1)

if [ $((max_scenario - min_scenario)) -gt 2 ]; then
    echo "⚠️  Scenario imbalance detected (${max_scenario} vs ${min_scenario})"
    echo "   Consider adjusting rotation if continues"
else
    echo "✅ Scenarios are balanced"
fi

# Spike rate check
if [ $TOTAL_PREDICTIONS -gt 100 ]; then
    spike_rate=$(echo "scale=2; $TOTAL_SPIKES * 100 / $TOTAL_PREDICTIONS" | bc)
    echo "Spike rate: ${spike_rate}%"
    
    if [ "$(echo "$spike_rate < 1.0" | bc)" -eq 1 ]; then
        echo "⚠️  Low spike rate - workload may need to be more aggressive"
    elif [ "$(echo "$spike_rate > 10.0" | bc)" -eq 1 ]; then
        echo "⚠️  High spike rate - may be too aggressive"
    else
        echo "✅ Spike rate looks good"
    fi
fi

# Progress toward target
if [ $TOTAL_SPIKES -ge 200 ]; then
    echo ""
    echo "🎉 Excellent! 200+ spikes reached"
    echo "   Consider stopping collection and analyzing"
elif [ $TOTAL_SPIKES -ge 100 ]; then
    echo ""
    echo "✅ Good! 100+ spikes reached (minimum target)"
    echo "   Can continue or stop and analyze"
else
    remaining=$((100 - TOTAL_SPIKES))
    echo ""
    echo "⏳ Progress: $TOTAL_SPIKES/100 spikes"
    echo "   Need $remaining more for minimum target"
fi

echo ""
