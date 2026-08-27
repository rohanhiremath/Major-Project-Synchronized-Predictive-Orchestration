#!/bin/bash
# Phase 4: Start Synthetic Workload Generation

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo "PHASE 4: STARTING SYNTHETIC WORKLOAD GENERATION"
echo "Target: 16% spike density (matching training data)"
echo "============================================================"
echo ""

# Check prerequisites
echo "Checking prerequisites..."
POD_COUNT=$(kubectl get pods -l app=workload --no-headers 2>/dev/null | wc -l)
if [ "$POD_COUNT" -ne 3 ]; then
    echo "⚠ Warning: Expected 3 workload pods, found $POD_COUNT"
    echo "   Continuing anyway..."
fi

echo "✅ Prerequisites checked"
echo ""

# Measure baseline PSI
echo "Measuring baseline PSI (10 seconds)..."
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 > /dev/null 2>&1 &
PF_PID=$!
sleep 3

BASELINE=$(curl -s 'http://localhost:9090/api/v1/query?query=avg(rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m])*100)' 2>/dev/null | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    result = data.get('data', {}).get('result', [])
    if result:
        print(f\"{float(result[0]['value'][1]):.4f}%\")
    else:
        print('N/A')
except:
    print('N/A')
" 2>/dev/null || echo "N/A")

kill $PF_PID 2>/dev/null || true

echo "   Baseline Memory PSI: $BASELINE"
echo ""

# Deploy stress workloads
echo "┌────────────────────────────────────────────────────────────┐"
echo "│ Step 1: Deploying CPU/Memory Stress Workloads             │"
echo "└────────────────────────────────────────────────────────────┘"
echo ""

kubectl apply -f workload-stress.yaml

echo "✅ Stress workloads deployed:"
kubectl get jobs -l workload-type=stress
echo ""

# Wait a bit before deploying I/O
echo "Waiting 10 seconds before deploying I/O workloads..."
sleep 10

# Deploy FIO workloads
echo "┌────────────────────────────────────────────────────────────┐"
echo "│ Step 2: Deploying FIO I/O Stress Workloads                │"
echo "└────────────────────────────────────────────────────────────┘"
echo ""

echo "Note: FIO jobs require PVC access. Adjusting PVC names..."

# Update FIO YAML with actual PVC names
for i in 0 1 2; do
    sed "s/data-volume-workload-app-0/data-volume-workload-app-$i/g" workload-fio.yaml > /tmp/fio-$i.yaml
    kubectl apply -f /tmp/fio-$i.yaml 2>/dev/null || echo "⚠ FIO job for pod $i skipped (may need manual PVC configuration)"
done

echo ""
echo "✅ FIO workloads deployed (check status below)"
echo ""

# Show all workload jobs
echo "============================================================"
echo "WORKLOAD STATUS"
echo "============================================================"
echo ""
kubectl get jobs -l workload-type

echo ""
echo "============================================================"
echo "MONITORING"
echo "============================================================"
echo ""
echo "Workloads are now generating PSI spikes!"
echo ""
echo "Monitor PSI metrics:"
echo "  Option 1: ./monitor-workloads.sh"
echo "  Option 2: Prometheus UI (http://localhost:9090)"
echo "    Query: rate(node_pressure_memory_stalled_seconds_total{pod=~\"workload-.*\"}[1m]) * 100"
echo "  Option 3: Grafana dashboard (http://localhost:3000)"
echo ""
echo "Expected spike patterns:"
echo "  • Memory PSI: 2-10% during memory bursts"
echo "  • CPU PSI: 1-4% during CPU bursts"
echo "  • I/O PSI: 1-5% during I/O bursts"
echo "  • Spike density: ~15-18% over 1 hour"
echo ""
echo "Workload timeline (approximate):"
echo "  • Memory bursts: 60s burst, 300s idle (10 cycles)"
echo "  • CPU bursts: 45s burst, 200s idle (15 cycles)"
echo "  • Combined bursts: 90s burst, 400s idle (8 cycles)"
echo "  • I/O bursts: Various patterns, 30-90s bursts"
echo ""
echo "Total runtime: ~1-2 hours (jobs will complete automatically)"
echo ""
echo "To stop workloads: ./stop-workloads.sh"
echo "To collect data: ./collect-data.sh"
echo ""
