#!/bin/bash
# Phase 2: Quick Command Reference
# Copy-paste these commands in order

cd ~/Documents/major\ project/implementation/Major-Project-Synchronized-Predictive-Orchestration

echo "=========================================="
echo "PHASE 2: KUBERNETES DEPLOYMENT"
echo "Model: TFT-PSI (94.65% recall)"
echo "=========================================="

# STEP 1: Check prerequisites
echo ""
echo "Step 1: Checking prerequisites..."
kubectl cluster-info
kubectl get pods -n monitoring
cat /proc/pressure/memory || echo "⚠ PSI not available on this node"

# STEP 2: Deploy StatefulSet
echo ""
echo "Step 2: Deploying StatefulSet..."
kubectl apply -f kubernetes/phase2/workload-statefulset.yaml

# STEP 3: Deploy Services
echo ""
echo "Step 3: Deploying Services and ServiceMonitor..."
kubectl apply -f kubernetes/phase2/workload-service.yaml

# STEP 4: Wait for pods
echo ""
echo "Step 4: Waiting for pods to be ready..."
kubectl wait --for=condition=ready pod -l app=workload --timeout=120s

# STEP 5: Verify deployment
echo ""
echo "Step 5: Running verification..."
./kubernetes/phase2/verify-phase2.sh

# STEP 6: Check status
echo ""
echo "=========================================="
echo "DEPLOYMENT COMPLETE"
echo "=========================================="
echo ""
echo "Status:"
kubectl get statefulset workload-app
kubectl get pods -l app=workload
kubectl get pvc | grep workload
kubectl get svc | grep workload

echo ""
echo "Quick checks:"
echo "  1. PSI metrics:"
POD_NAME=$(kubectl get pods -l app=workload -o jsonpath='{.items[0].metadata.name}')
kubectl exec $POD_NAME -c node-exporter -- wget -qO- http://localhost:9100/metrics 2>/dev/null | grep -c "node_pressure" || echo "0"

echo "  2. Prometheus targets:"
PROM_POD=$(kubectl get pods -n monitoring -l app.kubernetes.io/name=prometheus -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n monitoring $PROM_POD -c prometheus -- wget -qO- 'http://localhost:9090/api/v1/targets' 2>/dev/null | grep -c "workload" || echo "0"

echo ""
echo "Access services:"
echo "  • Prometheus: kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090"
echo "  • Grafana: kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3000:80"
echo "  • Workload: kubectl port-forward svc/workload-nodeport 8080:80"
echo ""
echo "Grafana credentials: admin / prom-operator"
echo ""
