# Phase 3: Metrics Validation and Baseline Monitoring

## 📋 Overview

Phase 3 validates the PSI metrics collection infrastructure deployed in Phase 2 and establishes baseline monitoring before introducing synthetic workloads.

**Phase 2 Results (Verified ✅):**
- 3 pods running with 2/2 containers ready
- 6 PVCs bound (21Gi total storage)
- Prometheus scraping all 3 targets at **20s intervals**
- All PSI metrics being collected successfully
- Model metadata annotations present

**Phase 3 Objectives:**
1. Validate 20s scrape interval consistency
2. Check PSI metrics data quality (no gaps, correct labels)
3. Establish idle baseline PSI values
4. Create Grafana dashboards for real-time monitoring
5. Test queries matching training data format
6. Document expected vs actual metric behavior

---

## ✅ Phase 2 Verification Results

```
DEPLOYMENT STATUS: SUCCESS

PODS: 3/3 Running
  • workload-app-0: 2/2 containers ready
  • workload-app-1: 2/2 containers ready
  • workload-app-2: 2/2 containers ready

PROMETHEUS TARGETS: 3/3 UP
  • Health: UP on all targets
  • Scrape interval: 20s
  • Metrics endpoint: :9100/metrics

PSI METRICS: Available
  ✅ node_pressure_memory_stalled_seconds_total
  ✅ node_pressure_memory_waiting_seconds_total
  ✅ node_pressure_cpu_stalled_seconds_total
  ✅ node_pressure_cpu_waiting_seconds_total
  ✅ node_pressure_io_stalled_seconds_total
  ✅ node_pressure_io_waiting_seconds_total

MODEL METADATA: Annotated
  • Recall: 94.65%
  • Precision: 87.64%
  • F1: 91.01%
  • Threshold: 1.5%
```

---

## 🔍 Phase 3 Validation Tasks

### Task 1: Verify Scrape Interval Consistency

**Objective:** Confirm Prometheus is scraping every 20 seconds without gaps

**Commands:**
```bash
# Access Prometheus UI
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090

# Open browser: http://localhost:9090

# Run query to check scrape intervals
delta(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m])
```

**Expected:** Consistent 20s intervals, no missing data points

---

### Task 2: PSI Metrics Data Quality Check

**Objective:** Validate metric labels and data completeness

**Queries:**
```promql
# Check all PSI metrics are present
count(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"})
# Expected: 3 (one per pod)

# Check metric labels
node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}
# Should have: pod, node, namespace, app labels

# Verify monotonic increase (counter metric)
increase(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[5m])
# Should be >= 0
```

**Validation Script:** See `validate-metrics.sh`

---

### Task 3: Establish Idle Baseline

**Objective:** Record PSI values under idle conditions for comparison

**Why:** Training data has spike density of 12.78% (train) and 16.51% (test). Need to confirm idle Kubernetes PSI is similar to synthetic idle data.

**Baseline Queries:**
```promql
# Memory PSI rate (convert to percentage)
rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m]) * 100

# CPU PSI rate
rate(node_pressure_cpu_stalled_seconds_total{pod=~"workload-.*"}[1m]) * 100

# I/O PSI rate
rate(node_pressure_io_stalled_seconds_total{pod=~"workload-.*"}[1m]) * 100
```

**Expected Idle Values:**
- Memory PSI: 0.0% - 0.5%
- CPU PSI: 0.0% - 0.5%
- I/O PSI: 0.0% - 0.5%

**Baseline Script:** See `baseline-measurement.sh`

---

### Task 4: Create Grafana Dashboard

**Objective:** Real-time monitoring dashboard for PSI metrics

**Dashboard Panels:**
1. **PSI Memory Full (Time Series)**
   - Query: `rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m]) * 100`
   - Legend: `{{ pod }}`
   - Threshold: 1.5% (warning), 5% (critical)

2. **PSI CPU/IO/Memory (Multi-line)**
   - Memory: `rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m]) * 100`
   - CPU: `rate(node_pressure_cpu_stalled_seconds_total{pod=~"workload-.*"}[1m]) * 100`
   - I/O: `rate(node_pressure_io_stalled_seconds_total{pod=~"workload-.*"}[1m]) * 100`

3. **Spike Count (Stat Panel)**
   - Query: `count_over_time((rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m]) * 100 > 1.5)[1h:20s])`
   - Title: "Spikes Above 1.5% (Last Hour)"

4. **Pod Resource Usage**
   - CPU: `rate(container_cpu_usage_seconds_total{pod=~"workload-.*", container="app"}[1m]) * 100`
   - Memory: `container_memory_usage_bytes{pod=~"workload-.*", container="app"} / 1024 / 1024`

**Dashboard JSON:** See `grafana-dashboard.json`

---

### Task 5: Test Training Data Format Queries

**Objective:** Ensure queries match the format used in model training

**Training Data Columns:**
- `psi_memory_some_avg10`
- `psi_memory_full_avg10`
- `psi_memory_some_avg60`
- `psi_memory_full_avg60`
- `psi_memory_some_avg300`
- `psi_memory_full_avg300`

**Prometheus Equivalents:**
```promql
# avg10 (10-second average)
rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[10s]) * 100

# avg60 (60-second average)
rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m]) * 100

# avg300 (300-second average)
rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[5m]) * 100
```

**Note:** Training data used `node_pressure_memory_stalled_seconds_total` (PSI full), not "some". Validate this matches.

---

### Task 6: Compare Idle vs Training Data

**Objective:** Verify idle Kubernetes PSI resembles synthetic idle data

**Analysis:**
```bash
# Collect 10 minutes of idle PSI data
./baseline-measurement.sh --duration 600

# Compare with training data statistics
python3 compare-baseline.py
```

**Expected:** Idle PSI should be < 0.5%, similar to synthetic data idle periods

---

## 📊 Success Criteria

- [ ] All 3 targets scraped at 20s intervals for 10+ minutes
- [ ] No missing data points or scrape failures
- [ ] PSI metrics have correct labels (pod, node, namespace, app)
- [ ] Idle baseline PSI < 0.5% on all pods
- [ ] Grafana dashboard displays real-time metrics
- [ ] Training data format queries return expected results
- [ ] Baseline comparison shows < 20% difference from synthetic idle data

---

## 🚀 Quick Start

```bash
cd ~/Documents/major\ project/implementation/Major-Project-Synchronized-Predictive-Orchestration/kubernetes/phase3

# Run all validation tasks
./validate-all.sh

# Or run individual tasks
./validate-metrics.sh          # Task 1-2: Scrape interval and data quality
./baseline-measurement.sh      # Task 3: Establish baseline
./create-dashboard.sh          # Task 4: Deploy Grafana dashboard
./test-training-queries.sh     # Task 5: Test query formats
./compare-baseline.py          # Task 6: Compare with training data
```

---

## 📁 Files

| File | Purpose |
|------|---------|
| `README.md` | This file |
| `validate-all.sh` | Run all validation tasks |
| `validate-metrics.sh` | Check scrape interval and data quality |
| `baseline-measurement.sh` | Collect idle baseline PSI values |
| `create-dashboard.sh` | Deploy Grafana dashboard |
| `grafana-dashboard.json` | Dashboard configuration |
| `test-training-queries.sh` | Test query compatibility |
| `compare-baseline.py` | Compare idle baseline with training data |

---

## 📈 Expected Outputs

### Validation Report
```
PHASE 3 VALIDATION REPORT
========================

Scrape Interval: ✅ PASS
  • Consistent 20s intervals
  • No gaps detected in 10-minute window

Data Quality: ✅ PASS
  • All 6 PSI metrics present
  • Labels correct: pod, node, namespace, app
  • Counter monotonicity verified

Idle Baseline:
  • Memory PSI: 0.12% ± 0.05%
  • CPU PSI: 0.08% ± 0.03%
  • I/O PSI: 0.15% ± 0.08%
  Status: ✅ PASS (all < 0.5%)

Training Query Compatibility: ✅ PASS
  • avg10, avg60, avg300 queries working
  • Results match expected format

Baseline Comparison: ✅ PASS
  • Kubernetes idle: 0.12% memory PSI
  • Training idle: 0.09% memory PSI
  • Difference: 3% (< 20% threshold)

Overall: ✅ READY FOR PHASE 4
```

---

## ⚠️ Troubleshooting

### High Idle PSI (> 0.5%)
```bash
# Check pod resource usage
kubectl top pods -l app=workload

# Check node pressure
kubectl describe node presync-control-plane | grep -A 10 "Conditions:"

# Possible causes:
# - Background processes in nginx container
# - PVC I/O operations
# - Kubernetes scheduler overhead
```

### Missing Data Points
```bash
# Check Prometheus targets
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090
# Visit: http://localhost:9090/targets

# Check ServiceMonitor
kubectl get servicemonitor workload-psi-monitor -o yaml

# Check node-exporter logs
kubectl logs workload-app-0 -c node-exporter
```

### Query Returns No Data
```bash
# Verify metrics exist in pod
POD_NAME=$(kubectl get pods -l app=workload -o jsonpath='{.items[0].metadata.name}')
kubectl exec $POD_NAME -c node-exporter -- wget -qO- http://localhost:9100/metrics | grep node_pressure

# Check Prometheus config
kubectl get prometheus -n monitoring kube-prometheus-stack-prometheus -o yaml | grep serviceMonitorSelector
```

---

## ➡️ Next Steps

**After Phase 3 validation passes:**

**Phase 4:** Generate synthetic workloads
- Deploy fio for I/O stress
- Deploy stress-ng for CPU/memory stress
- Create spike patterns matching training data (16.51% density)
- Validate PSI metrics respond correctly to workload

**Phase 5:** Model evaluation on real data
- Collect 1-2 hours of workload PSI data
- Export to CSV matching training format
- Run model predictions on real Kubernetes data
- Compare predicted vs actual spikes

**Phase 6:** Implement predictive scaling logic
- Create decision service that consumes model predictions
- Define scaling thresholds and cooldown periods
- Implement shadow mode (predict but don't scale)

---

## 📚 References

- Phase 2 deployment: `../phase2/README.md`
- Prometheus queries: `../phase2/PROMETHEUS_QUERIES.md`
- Training data format: `../../data/ptcs_training_data_full_psi.csv`
- Model metrics: `../../src/predict_tft_improved.py`
