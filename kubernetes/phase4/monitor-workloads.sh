#!/bin/bash
# Phase 4: Real-time Workload Monitoring

echo "============================================================"
echo "PHASE 4: REAL-TIME PSI MONITORING"
echo "Press Ctrl+C to stop"
echo "============================================================"
echo ""

# Start port-forward
echo "Starting Prometheus port-forward..."
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 > /dev/null 2>&1 &
PF_PID=$!
sleep 3

cleanup() {
    echo ""
    echo "Stopping monitoring..."
    kill $PF_PID 2>/dev/null || true
    exit 0
}
trap cleanup EXIT INT TERM

# Monitor loop
ITERATION=0
SPIKE_COUNT=0
TOTAL_SAMPLES=0

while true; do
    ITERATION=$((ITERATION+1))
    TOTAL_SAMPLES=$((TOTAL_SAMPLES+3))  # 3 pods
    
    clear
    echo "============================================================"
    echo "PHASE 4: REAL-TIME PSI MONITORING"
    echo "Iteration: $ITERATION | Samples: $TOTAL_SAMPLES | Spikes: $SPIKE_COUNT"
    echo "============================================================"
    echo ""
    
    date +"Current time: %Y-%m-%d %H:%M:%S"
    echo ""
    
    # Query Memory PSI
    echo "┌────────────────────────────────────────────────────────────┐"
    echo "│ Memory PSI (Full)                                          │"
    echo "└────────────────────────────────────────────────────────────┘"
    
    curl -s 'http://localhost:9090/api/v1/query?query=rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m])*100' 2>/dev/null | python3 << 'EOF'
import json, sys
data = json.load(sys.stdin)
results = data.get('data', {}).get('result', [])
if results:
    for r in sorted(results, key=lambda x: x['metric']['pod']):
        pod = r['metric']['pod']
        value = float(r['value'][1])
        bar_len = int(value * 5)  # Scale for display
        bar = '█' * min(bar_len, 50)
        status = '🔴 SPIKE' if value > 1.5 else '🟢 IDLE'
        print(f'{pod:20} {value:6.2f}% {bar:50} {status}')
else:
    print('No data available yet')
EOF
    
    echo ""
    
    # Query CPU PSI
    echo "┌────────────────────────────────────────────────────────────┐"
    echo "│ CPU PSI                                                    │"
    echo "└────────────────────────────────────────────────────────────┘"
    
    curl -s 'http://localhost:9090/api/v1/query?query=rate(node_pressure_cpu_stalled_seconds_total{pod=~"workload-.*"}[1m])*100' 2>/dev/null | python3 << 'EOF'
import json, sys
data = json.load(sys.stdin)
results = data.get('data', {}).get('result', [])
if results:
    for r in sorted(results, key=lambda x: x['metric']['pod']):
        pod = r['metric']['pod']
        value = float(r['value'][1])
        bar_len = int(value * 5)
        bar = '█' * min(bar_len, 50)
        status = '🔴 HIGH' if value > 2.0 else '🟢 NORM'
        print(f'{pod:20} {value:6.2f}% {bar:50} {status}')
else:
    print('No data available yet')
EOF
    
    echo ""
    
    # Query I/O PSI
    echo "┌────────────────────────────────────────────────────────────┐"
    echo "│ I/O PSI                                                    │"
    echo "└────────────────────────────────────────────────────────────┘"
    
    curl -s 'http://localhost:9090/api/v1/query?query=rate(node_pressure_io_stalled_seconds_total{pod=~"workload-.*"}[1m])*100' 2>/dev/null | python3 << 'EOF'
import json, sys
data = json.load(sys.stdin)
results = data.get('data', {}).get('result', [])
if results:
    for r in sorted(results, key=lambda x: x['metric']['pod']):
        pod = r['metric']['pod']
        value = float(r['value'][1])
        bar_len = int(value * 5)
        bar = '█' * min(bar_len, 50)
        status = '🔴 HIGH' if value > 2.0 else '🟢 NORM'
        print(f'{pod:20} {value:6.2f}% {bar:50} {status}')
else:
    print('No data available yet')
EOF
    
    echo ""
    
    # Count current spikes
    CURRENT_SPIKES=$(curl -s 'http://localhost:9090/api/v1/query?query=count(rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m])*100>1.5)' 2>/dev/null | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    result = data.get('data', {}).get('result', [])
    print(int(float(result[0]['value'][1])) if result else 0)
except:
    print(0)
" 2>/dev/null || echo "0")
    
    SPIKE_COUNT=$((SPIKE_COUNT + CURRENT_SPIKES))
    
    # Calculate spike density
    if [ $TOTAL_SAMPLES -gt 0 ]; then
        SPIKE_DENSITY=$(echo "scale=2; $SPIKE_COUNT * 100 / $TOTAL_SAMPLES" | bc 2>/dev/null || echo "N/A")
    else
        SPIKE_DENSITY="N/A"
    fi
    
    echo "┌────────────────────────────────────────────────────────────┐"
    echo "│ Statistics                                                 │"
    echo "└────────────────────────────────────────────────────────────┘"
    echo "Current spikes (>1.5%): $CURRENT_SPIKES pods"
    echo "Total spike samples:    $SPIKE_COUNT"
    echo "Total samples:          $TOTAL_SAMPLES"
    echo "Spike density:          ${SPIKE_DENSITY}% (target: ~16%)"
    echo ""
    
    # Workload job status
    echo "┌────────────────────────────────────────────────────────────┐"
    echo "│ Workload Job Status                                        │"
    echo "└────────────────────────────────────────────────────────────┘"
    kubectl get jobs -l workload-type --no-headers 2>/dev/null | awk '{print $1, $2}' | while read name status; do
        echo "  $name: $status"
    done
    
    echo ""
    echo "Refreshing in 5 seconds... (Ctrl+C to stop)"
    sleep 5
done
