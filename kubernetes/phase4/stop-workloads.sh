#!/bin/bash
# Phase 4: Stop All Workload Generation

set -e

echo "============================================================"
echo "PHASE 4: STOPPING WORKLOAD GENERATION"
echo "============================================================"
echo ""

echo "Stopping all workload jobs..."

# Delete all workload jobs
kubectl delete jobs -l workload-type=stress --ignore-not-found=true
kubectl delete jobs -l workload-type=fio --ignore-not-found=true

echo "✅ Workload jobs deleted"
echo ""

echo "Checking for remaining jobs..."
REMAINING=$(kubectl get jobs -l workload-type --no-headers 2>/dev/null | wc -l)

if [ "$REMAINING" -eq 0 ]; then
    echo "✅ All workload jobs stopped"
else
    echo "⚠ $REMAINING job(s) still running:"
    kubectl get jobs -l workload-type
fi

echo ""
echo "Waiting 30 seconds for PSI to return to baseline..."
sleep 30

# Check PSI returns to baseline
echo ""
echo "Checking PSI baseline..."
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 > /dev/null 2>&1 &
PF_PID=$!
sleep 3

CURRENT_PSI=$(curl -s 'http://localhost:9090/api/v1/query?query=avg(rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m])*100)' 2>/dev/null | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    result = data.get('data', {}).get('result', [])
    if result:
        value = float(result[0]['value'][1])
        print(f'{value:.4f}%')
        if value < 0.5:
            print('✅ PSI returned to baseline')
        else:
            print(f'⚠ PSI still elevated (> 0.5%)')
    else:
        print('N/A')
except:
    print('N/A')
" 2>/dev/null || echo "N/A")

kill $PF_PID 2>/dev/null || true

echo "   Current Memory PSI: $CURRENT_PSI"
echo ""

echo "============================================================"
echo "WORKLOADS STOPPED"
echo "============================================================"
echo ""
echo "If you collected data during workload generation:"
echo "  • Check: workload_data/ directory"
echo "  • Proceed to Phase 5 for model evaluation"
echo ""
echo "To restart workloads: ./start-workloads.sh"
echo ""
