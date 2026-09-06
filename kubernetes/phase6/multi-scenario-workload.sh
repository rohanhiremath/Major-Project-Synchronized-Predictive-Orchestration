#!/bin/bash
#
# Step 3: Multi-Scenario Workload Generation
# Cycles through different load patterns to generate diverse PSI spikes
# Runs unattended for multiple days
#

set -o pipefail

# Configuration
TOTAL_DURATION_HOURS=${1:-120}  # Default: 5 days
SCENARIO_DURATION_HOURS=4       # Each scenario runs 4 hours
CYCLES=$((TOTAL_DURATION_HOURS / SCENARIO_DURATION_HOURS))

# Logging
LOG_DIR="workload-logs-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$LOG_DIR"
MAIN_LOG="$LOG_DIR/workload-execution.log"

exec > >(tee -a "$MAIN_LOG") 2>&1

echo "=========================================="
echo " Step 3: Multi-Scenario Workload Generation"
echo "=========================================="
echo "Start: $(date)"
echo "Total duration: ${TOTAL_DURATION_HOURS} hours ($((TOTAL_DURATION_HOURS / 24)) days)"
echo "Scenario duration: ${SCENARIO_DURATION_HOURS} hours each"
echo "Total cycles: ${CYCLES}"
echo "Log directory: ${LOG_DIR}"
echo ""

# Verify pods
if ! kubectl get pods -l app=workload &>/dev/null; then
    echo "❌ ERROR: Workload pods not found"
    exit 1
fi

PODS=$(kubectl get pods -l app=workload -o name)
echo "✅ Workload pods:"
echo "$PODS"
echo ""

# Helper function: Execute command in pod
exec_in_pod() {
    local pod=$1
    local cmd=$2
    kubectl exec $pod -c app -- sh -c "$cmd" &>/dev/null &
}

# Helper function: Kill all stress processes
kill_all_stress() {
    echo "  Stopping all stress processes..."
    for pod in $(kubectl get pods -l app=workload -o name); do
        kubectl exec $pod -c app -- pkill -f "stress-scenario" 2>/dev/null || true
        kubectl exec $pod -c app -- rm -f /tmp/mem_* 2>/dev/null || true
    done
    sleep 5
}

# Scenario 1: Step Pattern - Gradual load increase
scenario_step() {
    echo "▶ SCENARIO 1: Step Pattern (gradual increase)"
    echo "  3 steps: Low → Medium → High"
    
    local duration=$((SCENARIO_DURATION_HOURS * 3600))
    local step_duration=$((duration / 3))
    
    # Step 1: Low (20% memory)
    echo "  Step 1/3: Low load (20% memory)"
    for pod in $(kubectl get pods -l app=workload -o name); do
        exec_in_pod $pod "exec -a stress-scenario sh -c 'i=0; while [ \$i -lt 200 ]; do dd if=/dev/zero bs=1M count=1 2>/dev/null | base64 > /dev/null; i=\$((i+1)); done; sleep $step_duration'"
    done
    sleep $step_duration
    kill_all_stress
    
    # Step 2: Medium (50% memory)
    echo "  Step 2/3: Medium load (50% memory)"
    for pod in $(kubectl get pods -l app=workload -o name); do
        exec_in_pod $pod "exec -a stress-scenario sh -c 'i=0; while [ \$i -lt 500 ]; do dd if=/dev/zero bs=1M count=1 2>/dev/null | base64 > /dev/null; i=\$((i+1)); done; sleep $step_duration'"
    done
    sleep $step_duration
    kill_all_stress
    
    # Step 3: High (80% memory)
    echo "  Step 3/3: High load (80% memory)"
    for pod in $(kubectl get pods -l app=workload -o name); do
        exec_in_pod $pod "exec -a stress-scenario sh -c 'i=0; while [ \$i -lt 800 ]; do dd if=/dev/zero bs=1M count=1 2>/dev/null | base64 > /dev/null; i=\$((i+1)); done; sleep $step_duration'"
    done
    sleep $step_duration
    kill_all_stress
}

# Scenario 2: Ramp Pattern - Linear increase
scenario_ramp() {
    echo "▶ SCENARIO 2: Ramp Pattern (linear increase)"
    echo "  Memory increases from 10% to 90% over time"
    
    local duration=$((SCENARIO_DURATION_HOURS * 3600))
    local steps=10
    local step_duration=$((duration / steps))
    
    for step in $(seq 1 $steps); do
        local mem_percent=$((10 + step * 8))  # 10% to 90%
        echo "  Step $step/$steps: ${mem_percent}% memory"
        
        for pod in $(kubectl get pods -l app=workload -o name); do
            exec_in_pod $pod "exec -a stress-scenario sh -c 'i=0; while [ \$i -lt $((mem_percent * 10)) ]; do dd if=/dev/zero bs=1M count=1 2>/dev/null | base64 > /dev/null; i=\$((i+1)); done; sleep $step_duration'"
        done
        
        sleep $step_duration
        kill_all_stress
    done
}

# Scenario 3: Periodic Pattern - Repeated bursts
scenario_periodic() {
    echo "▶ SCENARIO 3: Periodic Pattern (repeated bursts)"
    echo "  Sine wave: 5min burst + 5min idle, repeating"
    
    local duration=$((SCENARIO_DURATION_HOURS * 3600))
    local cycle_duration=600  # 10 minutes per cycle
    local burst_duration=300  # 5 minutes burst
    local idle_duration=300   # 5 minutes idle
    local cycles=$((duration / cycle_duration))
    
    for cycle in $(seq 1 $cycles); do
        echo "  Cycle $cycle/$cycles: Burst phase"
        
        # High load burst
        for pod in $(kubectl get pods -l app=workload -o name); do
            exec_in_pod $pod "exec -a stress-scenario sh -c 'i=0; while [ \$i -lt 700 ]; do dd if=/dev/zero bs=1M count=1 2>/dev/null | base64 > /dev/null; i=\$((i+1)); done; sleep $burst_duration'"
        done
        
        sleep $burst_duration
        kill_all_stress
        
        echo "  Cycle $cycle/$cycles: Idle phase"
        sleep $idle_duration
    done
}

# Scenario 4: Sustained Pattern - Constant high load
scenario_sustained() {
    echo "▶ SCENARIO 4: Sustained Pattern (constant high load)"
    echo "  Maintains 75% memory for entire duration"
    
    local duration=$((SCENARIO_DURATION_HOURS * 3600))
    
    for pod in $(kubectl get pods -l app=workload -o name); do
        exec_in_pod $pod "exec -a stress-scenario sh -c 'while true; do i=0; while [ \$i -lt 750 ]; do dd if=/dev/zero bs=1M count=1 2>/dev/null | base64 > /dev/null; i=\$((i+1)); done; sleep 60; done' &"
    done
    
    echo "  Running sustained load for ${SCENARIO_DURATION_HOURS} hours..."
    sleep $duration
    kill_all_stress
}

# Scenario 5: Flash Pattern - Sudden spikes
scenario_flash() {
    echo "▶ SCENARIO 5: Flash Pattern (sudden spikes)"
    echo "  Random sudden spikes: 30s burst every 10-20 minutes"
    
    local duration=$((SCENARIO_DURATION_HOURS * 3600))
    local elapsed=0
    
    while [ $elapsed -lt $duration ]; do
        # Random wait between spikes (10-20 minutes)
        local wait_time=$((600 + RANDOM % 600))
        echo "  Waiting ${wait_time}s until next spike..."
        sleep $wait_time
        elapsed=$((elapsed + wait_time))
        
        if [ $elapsed -ge $duration ]; then
            break
        fi
        
        # Sudden spike
        echo "  ⚡ FLASH SPIKE!"
        for pod in $(kubectl get pods -l app=workload -o name); do
            exec_in_pod $pod "exec -a stress-scenario sh -c 'i=0; while [ \$i -lt 900 ]; do dd if=/dev/zero bs=1M count=1 2>/dev/null | base64 > /dev/null; i=\$((i+1)); done; sleep 30'"
        done
        
        sleep 30
        kill_all_stress
        elapsed=$((elapsed + 30))
    done
}

# Scenario 6: Mixed Pattern - Combination
scenario_mixed() {
    echo "▶ SCENARIO 6: Mixed Pattern (chaotic combination)"
    echo "  Random mix of all patterns"
    
    local duration=$((SCENARIO_DURATION_HOURS * 3600))
    local elapsed=0
    
    while [ $elapsed -lt $duration ]; do
        local pattern=$((RANDOM % 4))
        local segment_duration=900  # 15 minutes per segment
        
        case $pattern in
            0)
                echo "  Segment: Light load"
                for pod in $(kubectl get pods -l app=workload -o name); do
                    exec_in_pod $pod "exec -a stress-scenario sh -c 'i=0; while [ \$i -lt 300 ]; do dd if=/dev/zero bs=1M count=1 2>/dev/null | base64 > /dev/null; i=\$((i+1)); done; sleep $segment_duration'"
                done
                ;;
            1)
                echo "  Segment: Medium burst"
                for pod in $(kubectl get pods -l app=workload -o name); do
                    exec_in_pod $pod "exec -a stress-scenario sh -c 'i=0; while [ \$i -lt 600 ]; do dd if=/dev/zero bs=1M count=1 2>/dev/null | base64 > /dev/null; i=\$((i+1)); done; sleep $segment_duration'"
                done
                ;;
            2)
                echo "  Segment: Heavy spike"
                for pod in $(kubectl get pods -l app=workload -o name); do
                    exec_in_pod $pod "exec -a stress-scenario sh -c 'i=0; while [ \$i -lt 850 ]; do dd if=/dev/zero bs=1M count=1 2>/dev/null | base64 > /dev/null; i=\$((i+1)); done; sleep $segment_duration'"
                done
                ;;
            3)
                echo "  Segment: Idle recovery"
                # No load
                ;;
        esac
        
        sleep $segment_duration
        kill_all_stress
        elapsed=$((elapsed + segment_duration))
    done
}

# Main execution loop
echo "=========================================="
echo " Starting Scenario Cycles"
echo "=========================================="
echo ""

START_TIME=$(date +%s)

for cycle in $(seq 1 $CYCLES); do
    ELAPSED=$(($(date +%s) - START_TIME))
    ELAPSED_HOURS=$((ELAPSED / 3600))
    REMAINING_HOURS=$((TOTAL_DURATION_HOURS - ELAPSED_HOURS))
    
    echo "=========================================="
    echo " Cycle $cycle/$CYCLES"
    echo " Elapsed: ${ELAPSED_HOURS}h | Remaining: ${REMAINING_HOURS}h"
    echo "=========================================="
    echo ""
    
    # Cycle through scenarios
    scenario=$((((cycle - 1) % 6) + 1))
    
    case $scenario in
        1) scenario_step ;;
        2) scenario_ramp ;;
        3) scenario_periodic ;;
        4) scenario_sustained ;;
        5) scenario_flash ;;
        6) scenario_mixed ;;
    esac
    
    echo ""
    echo "✅ Scenario $scenario complete"
    echo ""
    
    # Check if we should stop
    if [ $ELAPSED -ge $((TOTAL_DURATION_HOURS * 3600)) ]; then
        break
    fi
done

# Final cleanup
kill_all_stress

echo "=========================================="
echo " Step 3: Complete"
echo "=========================================="
echo "End: $(date)"
echo "Total runtime: $(($(date +%s) - START_TIME)) seconds"
echo "Logs: $LOG_DIR"
echo ""
echo "✅ Multi-scenario workload generation complete"
echo ""
echo "Next: Check spike count with count-spikes.sh"
