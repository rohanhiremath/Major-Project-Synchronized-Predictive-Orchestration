# Phase 2: Kubernetes Workload Deployment with PSI Metrics

## Overview
Deploys a 3-replica StatefulSet with PSI (Pressure Stall Information) metrics collection integrated with Prometheus monitoring at 20s intervals.

**Model Context:**
- Model: TFT-PSI Improved (trained Aug 24, 2026)
- Recall: 94.65% (exceeds 90% automation gate)
- Precision: 87.64%
- F1 Score: 91.01%
- Optimal Threshold: 1.5
- Architecture: hidden_size=64, attention_heads=4, gradient_clip=1.0

## Prerequisites
✅ Kubernetes cluster running (verified: `kubectl cluster-info`)
✅ Prometheus Operator installed (verified: monitoring namespace exists)
✅ Kernel PSI support (check: `cat /proc/pressure/memory`)

## Step-by-Step Deployment

### Step 1: Verify Prerequisites

```bash
# Check cluster
kubectl cluster-info

# Check Prometheus
kubectl get pods -n monitoring

# Check PSI support on host
cat /proc/pressure/memory
cat /proc/pressure/cpu
cat /proc/pressure/io
```

**Expected output:** Files exist and show PSI metrics like:
```
some avg10=0.00 avg60=0.00 avg300=0.00 total=12345
full avg10=0.00 avg60=0.00 avg300=0.00 total=6789
```

If files don't exist, PSI is not enabled in kernel (requires CONFIG_PSI=y).

---

### Step 2: Deploy StatefulSet

```bash
cd ~/Documents/major\ project/implementation/Major-Project-Synchronized-Predictive-Orchestration

# Apply StatefulSet
kubectl apply -f kubernetes/phase2/workload-statefulset.yaml
```

**What this creates:**
- StatefulSet `workload-app` with 3 replicas
- Each pod has:
  - Main container: `nginx:1.25-alpine` (placeholder app)
  - Sidecar: `node-exporter` with PSI collector enabled
  - 2 PVCs: `data-volume` (5Gi) + `logs-volume` (2Gi)
- Total: 3 pods, 6 PVCs
- Model metadata in pod annotations (recall, threshold, etc.)

**Verify:**
```bash
kubectl get statefulset workload-app
kubectl get pods -l app=workload -w
```

Wait for all 3 pods to reach `Running` status (2/2 containers ready).

---

### Step 3: Deploy Services

```bash
# Apply services and ServiceMonitor
kubectl apply -f kubernetes/phase2/workload-service.yaml
```

**What this creates:**
1. **Headless Service** (`workload-svc`): For StatefulSet DNS
2. **NodePort Service** (`workload-nodeport`): External access on port 30080
3. **ServiceMonitor** (`workload-psi-monitor`): Prometheus scraping config
   - Interval: 20s
   - Metrics endpoint: `:9100/metrics`
   - Filters: Only PSI and essential node metrics

**Verify:**
```bash
kubectl get svc | grep workload
kubectl get servicemonitor workload-psi-monitor
```

---

### Step 4: Verify Deployment

```bash
# Run automated verification script
./kubernetes/phase2/verify-phase2.sh
```

**What it checks:**
1. StatefulSet status
2. Pod readiness (all 3 pods)
3. PVC creation (6 total)
4. Service endpoints
5. ServiceMonitor configuration
6. PSI metrics availability
7. Prometheus target scraping
8. Model metadata annotations

---

### Step 5: Check PSI Metrics

```bash
# Get first pod name
POD_NAME=$(kubectl get pods -l app=workload -o jsonpath='{.items[0].metadata.name}')

# Check metrics endpoint
kubectl exec $POD_NAME -c node-exporter -- wget -qO- http://localhost:9100/metrics | grep node_pressure

# Expected metrics:
# node_pressure_cpu_waiting_seconds_total
# node_pressure_cpu_stalled_seconds_total
# node_pressure_memory_waiting_seconds_total
# node_pressure_memory_stalled_seconds_total
# node_pressure_io_waiting_seconds_total
# node_pressure_io_stalled_seconds_total
```

---

### Step 6: Verify Prometheus Scraping

```bash
# Port-forward to Prometheus
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &

# Open browser to http://localhost:9090
# Query: node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}
```

**Or via CLI:**
```bash
PROM_POD=$(kubectl get pods -n monitoring -l app.kubernetes.io/name=prometheus -o jsonpath='{.items[0].metadata.name}')

kubectl exec -n monitoring $PROM_POD -c prometheus -- \
  wget -qO- 'http://localhost:9090/api/v1/query?query=node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}' | python3 -m json.tool
```

You should see 3 time series (one per pod) with current PSI values.

---

### Step 7: Access Grafana Dashboard

```bash
# Port-forward to Grafana
kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3000:80 &

# Open browser to http://localhost:3000
# Login: admin / prom-operator
```

**Create PSI Dashboard:**
1. Go to Dashboards → New → New Dashboard
2. Add panel with queries:
   - `rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m])`
   - `rate(node_pressure_cpu_stalled_seconds_total{pod=~"workload-.*"}[1m])`
   - `rate(node_pressure_io_stalled_seconds_total{pod=~"workload-.*"}[1m])`

---

## Verification Checklist

- [ ] Cluster accessible (`kubectl cluster-info`)
- [ ] 3 pods running with 2/2 containers ready
- [ ] 6 PVCs bound (2 per pod)
- [ ] Services created (headless + NodePort)
- [ ] ServiceMonitor created
- [ ] PSI metrics visible in pod metrics endpoint
- [ ] Prometheus scraping 3 targets at 20s interval
- [ ] Model metadata visible in pod annotations

---

## Troubleshooting

### Pods stuck in Pending
```bash
kubectl describe pod <pod-name>
# Check: PVC binding, resource availability
```

### PSI metrics missing
```bash
# Check kernel support
cat /proc/pressure/memory

# If missing, PSI not enabled in kernel
# Workaround: Use host node-exporter in DaemonSet mode
```

### Prometheus not scraping
```bash
# Check ServiceMonitor labels match Prometheus selector
kubectl get prometheus -n monitoring -o yaml | grep serviceMonitorSelector

# Ensure ServiceMonitor has label: release=kube-prometheus-stack
kubectl get servicemonitor workload-psi-monitor -o yaml | grep labels -A 5
```

### Container exec fails (cat not found)
This is expected - node-exporter uses minimal image. Use HTTP metrics endpoint:
```bash
kubectl exec $POD_NAME -c node-exporter -- wget -qO- http://localhost:9100/metrics
```

---

## Expected Resource Usage

**Per Pod:**
- CPU: 150m request, 2.2 CPU limit
- Memory: 192Mi request, 1.128Gi limit
- Storage: 7Gi (5Gi data + 2Gi logs)

**Total (3 pods):**
- CPU: 450m request, 6.6 CPU limit
- Memory: 576Mi request, 3.384Gi limit
- Storage: 21Gi

---

## Next Steps

**Phase 3:** Validate PSI metrics collection at 20s intervals
**Phase 4:** Generate synthetic workloads (fio, stress-ng)
**Phase 5:** Re-evaluate model on real Kubernetes PSI data
**Phase 6:** Implement predictive scaling decision logic
**Phase 7:** Shadow mode deployment
**Phase 8:** Kubernetes HPA integration with custom metrics
**Phase 9:** Compare reactive vs predictive HPA performance

---

## Model Integration Notes

The StatefulSet includes model metadata as pod annotations:
```yaml
annotations:
  model.predictive-hpa.io/version: "improved-tft-psi"
  model.predictive-hpa.io/recall: "94.65"
  model.predictive-hpa.io/precision: "87.64"
  model.predictive-hpa.io/f1: "91.01"
  model.predictive-hpa.io/threshold: "1.5"
  model.predictive-hpa.io/architecture: "tft-hidden64-heads4"
  model.predictive-hpa.io/training-date: "2026-08-24"
```

This metadata will be used by the predictive HPA controller (Phase 8) to:
1. Load the correct model checkpoint
2. Apply the optimal threshold (1.5)
3. Interpret predictions with 94.65% expected recall
4. Track model version for A/B testing

---

## Clean Up (if needed)

```bash
# Delete everything
kubectl delete -f kubernetes/phase2/workload-service.yaml
kubectl delete -f kubernetes/phase2/workload-statefulset.yaml

# Verify PVCs deleted
kubectl get pvc
# If stuck, force delete:
kubectl delete pvc --all --force --grace-period=0
```
