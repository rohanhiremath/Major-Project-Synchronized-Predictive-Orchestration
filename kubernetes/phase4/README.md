# Phase 4: Synthetic Workload Generation

## 📋 Overview

Phase 4 generates synthetic workloads to create PSI spike patterns matching the training data distribution. This validates that the model can predict real Kubernetes PSI spikes.

**Objectives:**
1. Generate I/O pressure using `fio` (Flexible I/O Tester)
2. Generate CPU/memory pressure using `stress-ng`
3. Create spike patterns matching training data (16.51% spike density at 1.5% threshold)
4. Monitor PSI metrics in real-time
5. Collect workload data for Phase 5 model evaluation

**Training Data Context:**
- Spike threshold: 1.5% (PSI full avg10)
- Training spike density: 12.78%
- Test spike density: 16.51%
- Target: Generate similar spike patterns in Kubernetes

---

## 🎯 Workload Strategy

### Workload Types

**1. I/O Stress (fio)**
- Sequential reads/writes to PVCs
- Random I/O with varying block sizes
- Creates I/O pressure → increases PSI I/O metrics
- Secondary effect on memory PSI

**2. CPU Stress (stress-ng)**
- CPU-bound computation
- Matrix operations
- Context switching stress
- Creates CPU pressure → increases PSI CPU metrics

**3. Memory Stress (stress-ng)**
- Memory allocation/deallocation
- Memory thrashing patterns
- Page fault generation
- Creates memory pressure → increases PSI memory metrics

### Spike Pattern Generation

**Spike Characteristics from Training Data:**
- Duration: Varies (few seconds to minutes)
- Intensity: PSI > 1.5% (can go up to 10%+)
- Distribution: ~16% of time in spike state
- Pattern: Bursty with idle periods

**Implementation:**
- Cyclical workload: burst → idle → burst
- Burst duration: 30-120 seconds
- Idle duration: 180-400 seconds
- Intensity: Variable (50-100% resource utilization during bursts)

---

## 📁 Files

| File | Purpose |
|------|---------|
| `README.md` | This file |
| `workload-fio.yaml` | I/O stress using fio |
| `workload-stress.yaml` | CPU/memory stress using stress-ng |
| `workload-patterns.yaml` | Coordinated spike pattern generator |
| `start-workloads.sh` | Deploy all workloads |
| `stop-workloads.sh` | Stop all workloads |
| `monitor-workloads.sh` | Monitor PSI metrics during workload |
| `collect-data.sh` | Export PSI data for model evaluation |

---

## 🚀 Quick Start

```bash
cd kubernetes/phase4

# Deploy all workloads
./start-workloads.sh

# Monitor PSI metrics (in another terminal)
./monitor-workloads.sh

# After 1-2 hours, collect data
./collect-data.sh

# Stop workloads
./stop-workloads.sh
```

---

## 📊 Workload Configurations

### 1. FIO (I/O Stress)

**Configuration:**
```yaml
Job: Sequential write then read
  - Block size: 4KB, 64KB, 1MB
  - I/O depth: 16
  - Runtime: 60s burst, 300s idle

Job: Random read/write
  - Block size: 4KB
  - Read/write mix: 70/30
  - I/O depth: 32
  - Runtime: 90s burst, 240s idle
```

**Targets:**
- Data PVC: `/data` (5Gi per pod)
- Logs PVC: `/var/log/app` (2Gi per pod)

**Expected PSI Impact:**
- I/O PSI: 1-5% during bursts
- Memory PSI: 0.5-2% (secondary effect)

---

### 2. Stress-ng (CPU/Memory)

**Configuration:**
```yaml
CPU Stress:
  - Workers: 2 (per pod)
  - Method: Matrix multiplication
  - Burst: 45s
  - Idle: 200s

Memory Stress:
  - Workers: 1
  - Method: Memory allocation + thrashing
  - Memory: 512MB allocations
  - Burst: 60s
  - Idle: 300s
```

**Expected PSI Impact:**
- CPU PSI: 0.5-3% during bursts
- Memory PSI: 2-8% during bursts

---

### 3. Pattern Generator

**Coordinated Workload:**
- Orchestrates fio + stress-ng
- Creates realistic spike patterns
- Targets 16% spike density (matching test data)
- Variable intensity and duration

**Pattern:**
```
Timeline:
0-60s:   I/O burst (high intensity)
60-360s: Idle
360-420s: CPU burst (medium intensity)
420-720s: Idle
720-800s: Memory burst (high intensity)
800-1200s: Idle
[repeat]
```

---

## 🔧 Deployment

### Step 1: Verify Current State

```bash
# Check workload pods are running
kubectl get pods -l app=workload

# Check current PSI baseline
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 &
# Query: rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m]) * 100
# Expected: < 0.5% (idle)
```

---

### Step 2: Deploy FIO Workload

```bash
# Deploy fio jobs
kubectl apply -f workload-fio.yaml

# Monitor
kubectl get jobs -l workload-type=fio
kubectl logs -l workload-type=fio -f
```

---

### Step 3: Deploy Stress-ng Workload

```bash
# Deploy stress-ng jobs
kubectl apply -f workload-stress.yaml

# Monitor
kubectl get jobs -l workload-type=stress
kubectl logs -l workload-type=stress -f
```

---

### Step 4: Deploy Pattern Generator

```bash
# Deploy coordinated pattern
kubectl apply -f workload-patterns.yaml

# Monitor
kubectl get cronjobs
kubectl get jobs -l workload-type=pattern
```

---

### Step 5: Monitor PSI Metrics

```bash
# Real-time monitoring
./monitor-workloads.sh

# Or manually in Prometheus:
# Query: rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m]) * 100
# Watch for spikes > 1.5%

# Or in Grafana:
kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3000:80
# Open: http://localhost:3000
# Dashboard: PSI Predictive HPA - Workload Monitoring
```

---

## 📈 Expected Results

### PSI Metrics During Workload

**Idle (baseline):**
- Memory PSI: 0.0% - 0.5%
- CPU PSI: 0.0% - 0.5%
- I/O PSI: 0.0% - 0.5%

**During I/O Burst:**
- Memory PSI: 0.5% - 2.0%
- CPU PSI: 0.2% - 0.8%
- I/O PSI: 1.0% - 5.0%

**During CPU Burst:**
- Memory PSI: 0.3% - 1.0%
- CPU PSI: 1.0% - 4.0%
- I/O PSI: 0.2% - 0.8%

**During Memory Burst:**
- Memory PSI: 2.0% - 10.0% ← **Target for spikes**
- CPU PSI: 0.5% - 2.0%
- I/O PSI: 0.5% - 2.0%

### Spike Detection

**Target:**
- 15-18% of samples above 1.5% threshold
- Average spike duration: 30-90 seconds
- Peak PSI: 2-10% during spikes

**Validation Queries:**
```promql
# Count spikes in last hour
count_over_time((rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m]) * 100 > 1.5)[1h:20s])

# Spike density (percentage of time)
(count_over_time((rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m]) * 100 > 1.5)[1h:20s]) / count_over_time(rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m])[1h:20s])) * 100

# Average PSI during spikes
avg_over_time((rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m]) * 100)[1h:20s] > 1.5)
```

---

## 📊 Data Collection

### Duration

**Recommended:** 1-2 hours of workload generation
- Provides enough spike samples
- Captures multiple workload cycles
- Sufficient for model evaluation

**Minimum:** 30 minutes

**Maximum:** Unlimited (for long-term testing)

### Collection Script

```bash
# Collect PSI data for model evaluation
./collect-data.sh --duration 7200  # 2 hours

# Output: workload_psi_data.csv
# Format matches training data:
#   timestamp, pod, psi_memory_some_avg10, psi_memory_full_avg10, ...
```

---

## 🛑 Stopping Workloads

```bash
# Stop all workload generation
./stop-workloads.sh

# Verify stopped
kubectl get jobs -l workload-type
kubectl get cronjobs -l workload-type

# PSI should return to baseline (< 0.5%) within 1-2 minutes
```

---

## ⚠️ Resource Limits

**Pod Resource Limits:**
- CPU: 2000m limit (allows bursts up to 2 cores)
- Memory: 1Gi limit
- Storage: 5Gi data + 2Gi logs per pod

**Workload respects limits:**
- FIO: Uses existing PVCs, no additional storage
- Stress-ng: CPU/memory within container limits
- No node-level resource exhaustion

**Safety:**
- Workloads target application pods only
- Node-exporter sidecars unaffected
- Prometheus/Grafana monitoring unaffected
- Can stop workloads anytime without data loss

---

## 🔍 Validation Checklist

- [ ] Baseline PSI measured before workload (< 0.5%)
- [ ] FIO workload deployed and running
- [ ] Stress-ng workload deployed and running
- [ ] Pattern generator coordinating bursts
- [ ] PSI spikes visible in Prometheus (> 1.5%)
- [ ] Spike density ~15-18% over 1-hour window
- [ ] Grafana dashboard shows real-time spikes
- [ ] No pod restarts or OOMKills
- [ ] Data collected for Phase 5 evaluation

---

## 🐛 Troubleshooting

### Workload Jobs Failing

```bash
# Check job status
kubectl describe job <job-name>

# Check logs
kubectl logs job/<job-name>

# Common issues:
# - PVC not mounted: Check pod describe
# - Resource limits: Increase in workload YAML
# - Image pull: Check network/registry
```

### No PSI Spikes Observed

```bash
# Verify workload is running
kubectl get jobs
kubectl logs -l workload-type=stress

# Increase workload intensity in YAML:
# - More stress-ng workers
# - Higher memory allocation
# - Longer burst duration

# Check if PSI is actually increasing (raw counters)
# Query: node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}
```

### PSI Too High (> 20%)

```bash
# Reduce workload intensity
kubectl delete job <job-name>
# Edit YAML: reduce workers, memory, or duration
# Redeploy with lower intensity
```

---

## ➡️ Next Steps

**After 1-2 hours of workload generation:**

**Phase 5:** Model Evaluation on Real Data
- Export collected PSI data to CSV
- Run model predictions on real Kubernetes data
- Compare predicted vs actual spikes
- Validate 94.65% recall holds on real workloads

**Commands:**
```bash
# Collect data
./collect-data.sh --duration 7200

# Move to Phase 5
cd ../phase5
# Follow Phase 5 README for evaluation
```

---

## 📚 References

- **FIO Documentation:** https://fio.readthedocs.io/
- **stress-ng Manual:** https://wiki.ubuntu.com/Kernel/Reference/stress-ng
- **PSI Documentation:** https://www.kernel.org/doc/html/latest/accounting/psi.html
- **Training Data:** `../../data/ptcs_training_data_full_psi.csv`
