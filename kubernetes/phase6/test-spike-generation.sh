#!/bin/bash
#
# Test script to validate memory spike generation works
# Run this BEFORE the 24-hour test to ensure spikes can be created
#

echo "=========================================="
echo " Testing Memory Spike Generation"
echo "=========================================="
echo ""

# Test on one pod
POD="workload-app-0"
MEMORY_MB=500
DURATION=60

echo "Test parameters:"
echo "  Pod: $POD"
echo "  Memory: ${MEMORY_MB}MB"
echo "  Duration: ${DURATION}s"
echo ""

# Check pod exists
if ! kubectl get pod $POD &>/dev/null; then
    echo "❌ Pod $POD not found"
    exit 1
fi
echo "✅ Pod found"

# Get baseline PSI
echo ""
echo "=== Baseline PSI (before stress) ==="
kubectl port-forward -n monitoring svc/prometheus-operated 9090:9090 &>/dev/null &
PF_PID=$!
sleep 5

BASELINE=$(curl -s 'http://localhost:9090/api/v1/query?query=deriv(node_pressure_memory_waiting_seconds_total{pod="'$POD'"}[2m])*100' | python3 -c "
import json, sys
data = json.load(sys.stdin)
results = data.get('data', {}).get('result', [])
if results:
    print(float(results[0]['value'][1]))
else:
    print('0.0')
" 2>/dev/null || echo "0.0")

echo "Current PSI: ${BASELINE}%"

# Start memory stress
echo ""
echo "=== Starting memory stress ==="
kubectl exec $POD -c app -- sh -c "
    # Kill any existing stress
    pkill -f 'memory-eater' 2>/dev/null || true
    pkill dd 2>/dev/null || true
    rm -f /tmp/mem_* 2>/dev/null || true
    
    # Start memory allocation
    (
        exec -a memory-eater sh -c '
            echo Starting memory allocation...
            for i in \$(seq 1 ${MEMORY_MB}); do
                dd if=/dev/zero of=/tmp/mem_\$i bs=1M count=1 2>/dev/null &
            done
            echo Memory allocated, holding for ${DURATION}s...
            sleep ${DURATION}
            echo Cleaning up...
            rm -f /tmp/mem_* 2>/dev/null
            pkill dd 2>/dev/null
            echo Done
        ' &
    ) &
" &

echo "✅ Memory stress started"
echo ""
echo "Waiting 30 seconds for PSI to build up..."
sleep 30

# Check PSI during stress
echo ""
echo "=== PSI during stress ==="
for i in {1..6}; do
    PSI=$(curl -s 'http://localhost:9090/api/v1/query?query=deriv(node_pressure_memory_waiting_seconds_total{pod="'$POD'"}[2m])*100' | python3 -c "
import json, sys
data = json.load(sys.stdin)
results = data.get('data', {}).get('result', [])
if results:
    print(float(results[0]['value'][1]))
else:
    print('0.0')
" 2>/dev/null || echo "0.0")
    
    echo "[$i/6] Current PSI: ${PSI}%"
    
    # Check if spike detected
    if [ "$(echo "$PSI > 1.80" | bc 2>/dev/null)" -eq 1 ]; then
        echo "  ✅ SPIKE! PSI above 1.80% threshold"
    fi
    
    sleep 10
done

# Cleanup
echo ""
echo "=== Cleanup ==="
kubectl exec $POD -c app -- sh -c "pkill -f 'memory-eater' 2>/dev/null; pkill dd 2>/dev/null; rm -f /tmp/mem_* 2>/dev/null" &>/dev/null || true
kill $PF_PID 2>/dev/null || true

echo "✅ Cleanup complete"
echo ""

# Check final PSI
sleep 30
kubectl port-forward -n monitoring svc/prometheus-operated 9090:9090 &>/dev/null &
PF_PID=$!
sleep 5

FINAL=$(curl -s 'http://localhost:9090/api/v1/query?query=deriv(node_pressure_memory_waiting_seconds_total{pod="'$POD'"}[2m])*100' | python3 -c "
import json, sys
data = json.load(sys.stdin)
results = data.get('data', {}).get('result', [])
if results:
    print(float(results[0]['value'][1]))
else:
    print('0.0')
" 2>/dev/null || echo "0.0")

echo "=== Recovery PSI (after stress) ==="
echo "Current PSI: ${FINAL}%"

kill $PF_PID 2>/dev/null || true

echo ""
echo "=========================================="
echo " Test Summary"
echo "=========================================="
echo "Baseline PSI: ${BASELINE}%"
echo "Max PSI observed: Check values above"
echo "Final PSI: ${FINAL}%"
echo ""

# Determine success
if [ "$(echo "$BASELINE < 1.0" | bc 2>/dev/null)" -eq 1 ]; then
    echo "✅ Baseline normal (< 1.0%)"
else
    echo "⚠️  Baseline elevated (>= 1.0%)"
fi

echo ""
echo "Review the PSI values above:"
echo "  - If PSI increased above 1.80%, spike generation works ✅"
echo "  - If PSI stayed near 0%, spike generation failed ❌"
echo ""
echo "If spikes work, proceed with: ./run-24hour-test.sh"
