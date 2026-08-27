#!/bin/bash
# Phase 3: Quick Test - Verify everything is working

set -e

echo "============================================================"
echo "PHASE 3: QUICK TEST"
echo "============================================================"
echo ""

echo "1. Checking pod status..."
kubectl get pods -l app=workload
echo ""

echo "2. Checking PVCs..."
kubectl get pvc | grep workload | wc -l
echo "   Expected: 6 PVCs"
echo ""

echo "3. Testing PSI metrics from first pod..."
POD_NAME=$(kubectl get pods -l app=workload -o jsonpath='{.items[0].metadata.name}')
echo "   Pod: $POD_NAME"
PSI_COUNT=$(kubectl exec $POD_NAME -c node-exporter -- wget -qO- http://localhost:9100/metrics 2>/dev/null | grep "node_pressure.*seconds_total" | wc -l)
echo "   PSI metrics found: $PSI_COUNT"
if [ "$PSI_COUNT" -ge 6 ]; then
    echo "   ✅ PASS"
else
    echo "   ⚠ FAIL (expected >= 6)"
fi
echo ""

echo "4. Checking Prometheus targets..."
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 > /dev/null 2>&1 &
PF_PID=$!
sleep 3

TARGET_COUNT=$(curl -s 'http://localhost:9090/api/v1/query?query=up{pod=~"workload-.*"}' 2>/dev/null | grep -o "workload-app" | wc -l)
echo "   Workload targets scraped: $TARGET_COUNT"
if [ "$TARGET_COUNT" -eq 3 ]; then
    echo "   ✅ PASS"
else
    echo "   ⚠ FAIL (expected 3)"
fi

kill $PF_PID 2>/dev/null || true
echo ""

echo "5. Sample PSI query (Memory)..."
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 > /dev/null 2>&1 &
PF_PID=$!
sleep 3

curl -s 'http://localhost:9090/api/v1/query?query=rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m])*100' | python3 -c "
import json, sys
data = json.load(sys.stdin)
results = data.get('data', {}).get('result', [])
print(f'   Found {len(results)} time series')
for r in results:
    pod = r['metric']['pod']
    value = float(r['value'][1])
    print(f'   • {pod}: {value:.4f}%')
if results:
    print('   ✅ PASS')
else:
    print('   ⚠ FAIL (no data)')
" 2>/dev/null || echo "   ⚠ Query failed"

kill $PF_PID 2>/dev/null || true
echo ""

echo "============================================================"
echo "QUICK TEST COMPLETE"
echo "============================================================"
echo ""
echo "If all tests passed, you're ready to run full validation:"
echo "  ./validate-all.sh"
echo ""
