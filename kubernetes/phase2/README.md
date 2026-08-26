# Phase 2: Kubernetes Workload Deployment - Complete Guide

## 📋 Overview

Phase 2 deploys a production-ready StatefulSet with integrated PSI (Pressure Stall Information) metrics collection, preparing the infrastructure for predictive autoscaling.

**Deployment:**
- 3 replica StatefulSet with anti-affinity
- 6 PVCs (2 per pod: data + logs)
- Node-exporter sidecars for PSI metrics
- Prometheus scraping at 20s intervals
- Model metadata in pod annotations

**Model Context:**
- Version: TFT-PSI Improved (Aug 24, 2026)
- Recall: **94.65%** (exceeds 90% automation gate ✅)
- Precision: 87.64%
- F1 Score: 91.01%
- Optimal Threshold: 1.5%
- Architecture: TFT with hidden_size=64, attention_heads=4

---

## 🚀 Quick Start

```bash
cd ~/Documents/major\ project/implementation/Major-Project-Synchronized-Predictive-Orchestration

# Option 1: Run automated deployment script
./kubernetes/phase2/COMMANDS.sh

# Option 2: Manual step-by-step
kubectl apply -f kubernetes/phase2/workload-statefulset.yaml
kubectl apply -f kubernetes/phase2/workload-service.yaml
./kubernetes/phase2/verify-phase2.sh
```

---

## 📁 Files

| File | Purpose |
|------|---------|
| `workload-statefulset.yaml` | StatefulSet definition with 3 replicas, PSI sidecars |
| `workload-service.yaml` | Headless Service, NodePort, ServiceMonitor |
| `verify-phase2.sh` | Automated verification script |
| `COMMANDS.sh` | One-command deployment |
| `DEPLOY.md` | Detailed step-by-step guide |
| `PROMETHEUS_QUERIES.md` | Sample queries for PSI metrics |
| `README.md` | This file |

---

## ✅ Prerequisites

1. **Kubernetes Cluster Running**
   ```bash
   kubectl cluster-info
   # Expected: Control plane and CoreDNS running
   ```

2. **Prometheus Operator Installed**
   ```bash
   kubectl get pods -n monitoring
   # Expected: prometheus, grafana, alertmanager, node-exporter pods
   ```

3. **PSI Kernel Support**
   ```bash
   cat /proc/pressure/memory
   # Expected: "some avg10=..." and "full avg10=..." metrics
   ```
   ✅ **Verified on your system:** PSI available with current values:
   - some avg10=0.10, avg60=0.36, avg300=0.43
   - full avg10=0.08, avg60=0.29, avg300=0.35

---

## 📊 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                       │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │             StatefulSet: workload-app                │  │
│  │                                                      │  │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐    │  │
│  │  │  Pod 0     │  │  Pod 1     │  │  Pod 2     │    │  │
│  │  │            │  │            │  │            │    │  │
│  │  │ ┌────────┐ │  │ ┌────────┐ │  │ ┌────────┐ │    │  │
│  │  │ │  app   │ │  │ │  app   │ │  │ │  app   │ │    │  │
│  │  │ │ :80    │ │  │ │ :80    │ │  │ │ :80    │ │    │  │
│  │  │ └────────┘ │  │ └────────┘ │  │ └────────┘ │    │  │
│  │  │            │  │            │  │            │    │  │
│  │  │ ┌────────┐ │  │ ┌────────┐ │  │ ┌────────┐ │    │  │
│  │  │ │node-exp│ │  │ │node-exp│ │  │ │node-exp│ │    │  │
│  │  │ │ :9100  │◄─┼──┼─┼ :9100  │◄─┼──┼─┼ :9100  │◄───┼──┐│
│  │  │ │(PSI)   │ │  │ │(PSI)   │ │  │ │(PSI)   │ │    │  ││
│  │  │ └────────┘ │  │ └────────┘ │  │ └────────┘ │    │  ││
│  │  │            │  │            │  │            │    │  ││
│  │  │ PVC: data  │  │ PVC: data  │  │ PVC: data  │    │  ││
│  │  │ PVC: logs  │  │ PVC: logs  │  │ PVC: logs  │    │  ││
│  │  └────────────┘  └────────────┘  └────────────┘    │  ││
│  └──────────────────────────────────────────────────────┘  ││
│                                                             ││
│  ┌──────────────────────────────────────────────────────┐  ││
│  │              Monitoring Namespace                    │  ││
│  │                                                      │  ││
│  │  ┌──────────────┐         ┌──────────────┐          │  ││
│  │  │  Prometheus  │◄────────┤ServiceMonitor│          │  ││
│  │  │              │ 20s     │ (workload)   │          │  ││
│  │  │  :9090       │ scrape  └──────────────┘          │  ││
│  │  └──────┬───────┘                                   │  ││
│  │         │                                           │  ││
│  │         ▼                                           │  ││
│  │  ┌──────────────┐                                   │  ││
│  │  │   Grafana    │                                   │  ││
│  │  │   :3000      │                                   │  ││
│  │  └──────────────┘                                   │  ││
│  └──────────────────────────────────────────────────────┘  ││
└─────────────────────────────────────────────────────────────┘│
                                                               │
                    Scrape PSI metrics every 20s ◄────────────┘
```

---

## 🔧 Deployment Steps

### 1. Deploy StatefulSet
```bash
kubectl apply -f kubernetes/phase2/workload-statefulset.yaml
```

**Creates:**
- StatefulSet `workload-app` (3 replicas)
- Each pod: nginx app + node-exporter sidecar
- 6 PVCs: `data-volume-workload-app-{0,1,2}` and `logs-volume-workload-app-{0,1,2}`

### 2. Deploy Services
```bash
kubectl apply -f kubernetes/phase2/workload-service.yaml
```

**Creates:**
- Headless service: `workload-svc` (internal DNS)
- NodePort service: `workload-nodeport` (port 30080)
- ServiceMonitor: `workload-psi-monitor` (20s scrape interval)

### 3. Verify Deployment
```bash
./kubernetes/phase2/verify-phase2.sh
```

**Checks:**
- ✅ Pods running (2/2 containers ready)
- ✅ PVCs bound
- ✅ Services created
- ✅ PSI metrics exposed
- ✅ Prometheus scraping
- ✅ Model metadata annotations

---

## 📈 Monitoring

### Access Prometheus
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090
# Open: http://localhost:9090
```

**Sample Query:**
```promql
rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m]) * 100
```

### Access Grafana
```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3000:80
# Open: http://localhost:3000
# Login: admin / prom-operator
```

**Dashboard Queries:** See `PROMETHEUS_QUERIES.md`

---

## 🎯 Model Integration

Pod annotations include model metadata for Phase 8 integration:

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

**Usage:**
- Predictive HPA controller (Phase 8) reads these annotations
- Loads correct model checkpoint: `models/tft_psi_model_improved.ckpt`
- Applies threshold 1.5% for spike detection
- Expects 94.65% recall (5.35% false negative rate)

---

## 🔍 Verification Commands

```bash
# Check pod status
kubectl get pods -l app=workload

# Check PSI metrics from first pod
POD_NAME=$(kubectl get pods -l app=workload -o jsonpath='{.items[0].metadata.name}')
kubectl exec $POD_NAME -c node-exporter -- wget -qO- http://localhost:9100/metrics | grep node_pressure

# Check Prometheus targets
kubectl get servicemonitor workload-psi-monitor -o yaml

# Query Prometheus
PROM_POD=$(kubectl get pods -n monitoring -l app.kubernetes.io/name=prometheus -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n monitoring $PROM_POD -c prometheus -- \
  wget -qO- 'http://localhost:9090/api/v1/query?query=node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}' | python3 -m json.tool
```

---

## 🐛 Troubleshooting

### Pods Stuck in Pending
```bash
kubectl describe pod <pod-name>
# Check: PVC binding, resource requests
```

### PSI Metrics Missing
```bash
# Check kernel support
cat /proc/pressure/memory

# Check node-exporter logs
kubectl logs <pod-name> -c node-exporter
```

### Prometheus Not Scraping
```bash
# Check ServiceMonitor labels
kubectl get servicemonitor workload-psi-monitor -o yaml | grep -A 5 labels

# Verify Prometheus config
kubectl exec -n monitoring prometheus-kube-prometheus-stack-prometheus-0 -c prometheus -- \
  wget -qO- http://localhost:9090/api/v1/targets | grep workload
```

---

## 📦 Resource Requirements

**Per Pod:**
- CPU: 150m request, 2.2 limit
- Memory: 192Mi request, 1.128Gi limit
- Storage: 7Gi (5Gi data + 2Gi logs)

**Total (3 pods):**
- CPU: 450m request, 6.6 limit
- Memory: 576Mi request, 3.384Gi limit
- Storage: 21Gi

---

## 🗑️ Clean Up

```bash
# Delete all resources
kubectl delete -f kubernetes/phase2/workload-service.yaml
kubectl delete -f kubernetes/phase2/workload-statefulset.yaml

# Verify PVCs deleted
kubectl get pvc

# Force delete if stuck
kubectl delete pvc --all --force --grace-period=0
```

---

## ➡️ Next Steps

1. **Phase 3:** Validate 20s Prometheus scraping interval
2. **Phase 4:** Generate synthetic workloads (fio, stress-ng)
3. **Phase 5:** Compare real Kubernetes PSI data with training data
4. **Phase 6:** Implement predictive scaling decision logic
5. **Phase 7:** Deploy shadow mode (predict without scaling)
6. **Phase 8:** Integrate with Kubernetes HPA custom metrics
7. **Phase 9:** Compare reactive vs predictive HPA performance

---

## 📚 References

- [Kubernetes StatefulSets](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/)
- [Prometheus Operator](https://github.com/prometheus-operator/prometheus-operator)
- [Linux PSI Documentation](https://www.kernel.org/doc/html/latest/accounting/psi.html)
- [Node Exporter](https://github.com/prometheus/node_exporter)

---

## ✨ Key Achievements

- ✅ **94.65% recall** (exceeds 90% automation gate)
- ✅ All Tier 1/2/3 improvements implemented
- ✅ Production-ready architecture with 3 replicas
- ✅ PSI metrics collection at 20s intervals
- ✅ Model metadata integrated for Phase 8
- ✅ Automated verification and deployment scripts
- ✅ Comprehensive monitoring queries documented

**Status:** Ready for Phase 3 validation and Phase 4 workload generation! 🚀
