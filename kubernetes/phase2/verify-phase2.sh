#!/bin/bash
# Phase 2 Verification Script
# Checks StatefulSet deployment, PSI metrics collection, and Prometheus scraping

set -e

echo "============================================================"
echo "PHASE 2: VERIFICATION SCRIPT"
echo "Model: TFT-PSI (94.65% recall, threshold=1.5)"
echo "============================================================"
echo ""

# Check StatefulSet deployment
echo "1. Checking StatefulSet status..."
kubectl get statefulset workload-app -n default -o wide

echo ""
echo "2. Checking Pod status..."
kubectl get pods -l app=workload -n default -o wide

echo ""
echo "3. Checking PVC status (should have 6 total: 2 per pod)..."
kubectl get pvc -n default | grep workload-app || echo "No PVCs found"

echo ""
echo "4. Checking Services..."
kubectl get svc -n default | grep workload

echo ""
echo "5. Checking ServiceMonitor..."
kubectl get servicemonitor workload-psi-monitor -n default -o yaml | grep -E "(interval|prometheus)" || echo "ServiceMonitor not found"

echo ""
echo "6. Waiting for pods to be ready (timeout 120s)..."
kubectl wait --for=condition=ready pod -l app=workload -n default --timeout=120s

echo ""
echo "7. Checking PSI metrics from first pod..."
POD_NAME=$(kubectl get pods -l app=workload -n default -o jsonpath='{.items[0].metadata.name}')
echo "Testing metrics endpoint on pod: $POD_NAME"
kubectl exec -n default $POD_NAME -c node-exporter -- wget -qO- http://localhost:9100/metrics 2>/dev/null | grep -E "node_pressure_(cpu|memory|io)_" | head -10 || echo "⚠ PSI metrics not found (check kernel support)"

echo ""
echo "8. Checking if Prometheus is scraping workload targets..."
echo "   (Allow 20-40s for initial scrape)"
sleep 5
PROM_POD=$(kubectl get pods -n monitoring -l app.kubernetes.io/name=prometheus -o jsonpath='{.items[0].metadata.name}')
echo "   Querying Prometheus for workload targets..."
kubectl exec -n monitoring $PROM_POD -c prometheus -- wget -qO- 'http://localhost:9090/api/v1/targets' 2>/dev/null | grep -o "workload" | wc -l || echo "0" 
echo "   (Expected: 3 targets, one per pod)"

echo ""
echo "9. Sample PSI metrics query (if available)..."
kubectl exec -n monitoring $PROM_POD -c prometheus -- wget -qO- 'http://localhost:9090/api/v1/query?query=node_pressure_memory_stalled_seconds_total' 2>/dev/null | python3 -m json.tool 2>/dev/null | head -30 || echo "⚠ Query failed (wait for metrics collection)"

echo ""
echo "============================================================"
echo "PHASE 2 VERIFICATION COMPLETE"
echo "============================================================"
echo ""
echo "Next steps:"
echo "  • Access Grafana: kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3000:80"
echo "  • Default credentials: admin / prom-operator"
echo "  • Check PSI metrics: node_pressure_memory_stalled_seconds_total{pod=~\"workload-.*\"}"
echo "  • If PSI metrics missing, verify kernel CONFIG_PSI=y (check /proc/pressure/)"
echo ""
echo "Model metadata (from pod annotations):"
kubectl get pods -l app=workload -n default -o jsonpath='{.items[0].metadata.annotations}' | python3 -c "import sys, json; print(json.dumps({k:v for k,v in json.load(sys.stdin).items() if 'model.' in k}, indent=2))" 2>/dev/null || echo "Check pod annotations manually"
echo ""
