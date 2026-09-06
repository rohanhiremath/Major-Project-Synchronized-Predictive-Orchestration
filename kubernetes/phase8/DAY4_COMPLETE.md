# Day 4: Experiment Setup - COMPLETE ✅

**Date**: September 6, 2026  
**Duration**: ~2 hours  
**Status**: READY FOR 24-HOUR EXPERIMENT

---

## 🎯 Objectives Achieved

### ✅ 1. Workload Configurations Created
```bash
✅ workload-reactive.yaml - Baseline (experiment-reactive namespace)
✅ workload-predictive.yaml - PreSync (experiment-predictive namespace)
✅ prediction-service.yaml - Prediction service for predictive namespace
```

### ✅ 2. Experiment Infrastructure
```bash
✅ Separate namespaces for isolation
✅ Identical workloads (only HPA differs)
✅ ServiceMonitors for Prometheus scraping
✅ ConfigMaps for experiment configuration
```

### ✅ 3. Orchestration Scripts
```bash
✅ run-experiment.sh - Start 24-hour experiment
✅ stop-experiment.sh - Stop and export final state
✅ export-prometheus-data.sh - Export metrics for analysis
✅ analyze-results.py - Generate comparison table
```

### ✅ 4. Documentation
```bash
✅ QUICK_START.md - Step-by-step guide
✅ Directory structure created
✅ All scripts executable
```

---

## 📁 Files Created

### Workload Manifests (experiment/workloads/)
1. **workload-reactive.yaml** (184 lines)
   - Namespace: experiment-reactive
   - StatefulSet with 2 initial replicas
   - Node-exporter sidecar for PSI metrics
   - HPA using node_pressure_memory_waiting
   - 30s stabilization window

2. **workload-predictive.yaml** (184 lines)
   - Namespace: experiment-predictive
   - Identical to reactive except HPA
   - HPA using predicted_psi_confirmed
   - 0s stabilization (immediate scaling)

3. **prediction-service.yaml** (106 lines)
   - Deployed to experiment-predictive namespace
   - Uses Phase 6 prediction service code
   - Prometheus metrics export on port 8090
   - ServiceMonitor for auto-discovery

### Orchestration Scripts (experiment/scripts/)
1. **run-experiment.sh** (235 lines)
   - Prerequisites check
   - Deploy both workloads
   - Deploy prediction service
   - Start background monitoring
   - Log everything

2. **stop-experiment.sh** (82 lines)
   - Stop monitoring
   - Export final state
   - Optional cleanup
   - Save logs

3. **export-prometheus-data.sh** (135 lines)
   - Export PSI metrics
   - Export replica counts
   - Export HPA events
   - Query last 24 hours

4. **analyze-results.py** (193 lines)
   - Parse Prometheus exports
   - Calculate scale-up latency (p95)
   - Calculate breach metrics
   - Calculate pod-hours
   - Generate comparison table

### Documentation
1. **QUICK_START.md** (267 lines)
   - Complete usage guide
   - Troubleshooting section
   - Commands reference
   - Timeline and success criteria

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     EXPERIMENT ARCHITECTURE                      │
└─────────────────────────────────────────────────────────────────┘

                         ┌─────────────────┐
                         │   Prometheus    │
                         │   + Adapter     │
                         └────────┬────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │                           │
        ┌───────────▼──────────┐   ┌──────────▼──────────┐
        │ experiment-reactive  │   │ experiment-predictive│
        └──────────────────────┘   └─────────────────────┘
        │                      │   │                      │
        │ Workload (StatefulSet)   │ Workload (StatefulSet)
        │   ├─ app (nginx)     │   │   ├─ app (nginx)    │
        │   └─ node-exporter   │   │   └─ node-exporter  │
        │                      │   │                      │
        │ HPA (Reactive)       │   │ Prediction Service  │
        │   Metric: current PSI│   │   └─ Export metrics │
        │   Stabilization: 30s │   │                      │
        └──────────────────────┘   │ HPA (Predictive)    │
                                   │   Metric: predicted │
                                   │   Stabilization: 0s │
                                   └─────────────────────┘

Monitoring Loop (60s interval):
  - HPA status
  - Pod counts
  - Scaling events
  └─> logs/monitoring_*.log
```

---

## 🔬 Experiment Design

### Comparison Setup

| Aspect | Reactive (Baseline) | Predictive (PreSync) |
|--------|---------------------|----------------------|
| **Namespace** | experiment-reactive | experiment-predictive |
| **Workload** | StatefulSet (identical) | StatefulSet (identical) |
| **Initial Replicas** | 2 | 2 |
| **Max Replicas** | 10 | 10 |
| **HPA Metric** | node_pressure_memory_waiting | predicted_psi_confirmed |
| **Threshold** | 1800m (1.80%) | 1800m (1.80%) |
| **Stabilization** | 30 seconds | 0 seconds |
| **Scale Policy** | 50% or +2 pods per 30s | 50% or +2 pods per 15s |

### Metrics to Collect

1. **Scale-up Latency**
   - Time from PSI threshold breach to new pods ready
   - Measured at p50, p95, p99

2. **PSI Breach Metrics**
   - Total breach count
   - Mean breach duration
   - Max breach duration

3. **Resource Utilization**
   - Total pod-hours
   - Cost overhead vs baseline

4. **Prediction Accuracy (Predictive only)**
   - False positive count
   - False positive rate
   - True positive count

### Success Criteria

- ✅ Both workloads run for 24 hours
- ✅ At least 20 PSI spike events captured
- ✅ No HPA errors or failures
- ✅ Prediction service uptime >95%
- ✅ Complete metrics exported
- ✅ Analysis produces comparison table

---

## 🚀 How to Run

### Smoke Test (5 minutes) - RECOMMENDED FIRST

```bash
cd experiment/scripts

# Run 5-minute test
./run-experiment.sh 0.083  # 5 minutes = 0.083 hours

# Monitor
kubectl get hpa -A | grep experiment

# Generate artificial spike (in another terminal)
kubectl exec -n experiment-reactive workload-reactive-0 -c app -- \
  sh -c "stress-ng --vm 1 --vm-bytes 200M --timeout 60s"

kubectl exec -n experiment-predictive workload-predictive-0 -c app -- \
  sh -c "stress-ng --vm 1 --vm-bytes 200M --timeout 60s"

# Watch scaling happen
watch -n 5 'kubectl get hpa -n experiment-reactive; echo ""; kubectl get hpa -n experiment-predictive'

# Stop test after 5 minutes
./stop-experiment.sh
```

### Full 24-Hour Experiment

```bash
cd experiment/scripts

# Start experiment (Sunday evening recommended)
./run-experiment.sh 24

# Monitor progress
tail -f ../logs/monitoring_*.log

# Check after 2 hours (smoke check)
kubectl get hpa -A | grep experiment
kubectl get events -n experiment-reactive --sort-by='.lastTimestamp' | head -20

# Let run overnight...

# Stop experiment next morning
./stop-experiment.sh

# Export data
./export-prometheus-data.sh

# Analyze (Day 6)
python3 analyze-results.py ../results/reactive_*.json ../results/predictive_*.json
```

---

## 📊 Expected Results

Based on Phase 6 validation (107 spikes, 666 predictions, 3.7 hours):

### Prediction Performance
- ✅ **Raw Predictions**: 94.69% precision, 100% recall
- ✅ **Gated (Production)**: 100% precision, 88.79% recall
- ✅ **Confirmation Rate**: 84.1% (95 of 113 singles confirmed)

### Projected Improvements
1. **Scale-up Latency**
   - Reactive: ~60-90s (detection + stabilization + provisioning)
   - Predictive: ~20-40s (no detection lag, immediate scaling)
   - Expected: **50-60% faster**

2. **PSI Breach Duration**
   - Reactive: Spikes fully develop before scaling starts
   - Predictive: Scaling completes before/during spike onset
   - Expected: **60-70% shorter breaches**

3. **Breach Count**
   - Reactive: All spikes cause breaches
   - Predictive: Early scaling may prevent some breaches
   - Expected: **20-40% fewer breaches**

4. **Resource Overhead**
   - Predictive may scale up slightly early
   - Expected: **5-15% more pod-hours** (acceptable for gains)

---

## 🔍 Monitoring Points

### During Experiment

**Check every 2-4 hours**:
```bash
# HPA status
kubectl get hpa -A | grep experiment

# Pod counts
kubectl get pods -n experiment-reactive -l app=workload
kubectl get pods -n experiment-predictive -l app=workload

# Recent scaling events
kubectl get events -n experiment-reactive --sort-by='.lastTimestamp' | grep Scale | tail -10
kubectl get events -n experiment-predictive --sort-by='.lastTimestamp' | grep Scale | tail -10

# Prediction service health
kubectl logs -n experiment-predictive -l app=prediction-service --tail=20
```

**Health Indicators**:
- ✅ Both HPAs showing numeric targets (not "unknown")
- ✅ Prediction service running (check pod status)
- ✅ Monitoring log growing (~1 entry per minute)
- ✅ Some scaling events observed (4-6 per hour expected)

**Warning Signs**:
- ❌ HPA showing "unknown" for >5 minutes
- ❌ Prediction service restarting repeatedly
- ❌ No scaling events after 6 hours
- ❌ Monitoring log stopped growing

---

## 🐛 Troubleshooting

### Issue: HPA shows "unknown"

**Cause**: Metric not available in custom metrics API

**Fix**:
```bash
# Check if metric exists
kubectl get --raw /apis/custom.metrics.k8s.io/v1beta1 | grep -i pressure

# For reactive HPA
kubectl get --raw "/apis/custom.metrics.k8s.io/v1beta1/namespaces/experiment-reactive/pods/*/node_pressure_memory_waiting"

# For predictive HPA
kubectl get --raw "/apis/custom.metrics.k8s.io/v1beta1/namespaces/experiment-predictive/pods/*/predicted_psi_confirmed"

# If missing, check Prometheus Adapter
kubectl logs -n monitoring -l app.kubernetes.io/name=prometheus-adapter
```

### Issue: Prediction service not running

**Check**:
```bash
kubectl get pods -n experiment-predictive -l app=prediction-service
kubectl describe pod -n experiment-predictive -l app=prediction-service
kubectl logs -n experiment-predictive -l app=prediction-service
```

**Common Issues**:
1. Volume mounts (hostPath needs correct paths)
2. Python dependencies missing
3. Model file not found
4. Prometheus connection failed

**Fix**:
Update prediction-service.yaml volumes section with correct absolute paths.

### Issue: No scaling happening

**Check workload is under load**:
```bash
# Manual spike
kubectl exec -n experiment-reactive workload-reactive-0 -c app -- \
  sh -c "stress-ng --vm 1 --vm-bytes 200M --timeout 120s"

# Check PSI metric
kubectl exec -n experiment-reactive workload-reactive-0 -c node-exporter -- \
  curl -s localhost:9100/metrics | grep pressure_memory_waiting
```

---

## 📝 Checklist for Day 4

- [x] Create experiment directory structure
- [x] Create reactive workload manifest
- [x] Create predictive workload manifest
- [x] Create prediction service deployment
- [x] Create run-experiment.sh script
- [x] Create stop-experiment.sh script
- [x] Create export-prometheus-data.sh script
- [x] Create analyze-results.py script
- [x] Make all scripts executable
- [x] Create QUICK_START.md guide
- [x] Document architecture
- [ ] **Run smoke test (5 minutes)** ← NEXT
- [ ] **Start 24-hour experiment** ← AFTER SMOKE TEST

---

## 🎯 Next Steps

### Immediate (Today - Evening)

1. **Smoke Test** (5 minutes)
   ```bash
   cd experiment/scripts
   ./run-experiment.sh 0.083
   # Verify both HPAs work
   ./stop-experiment.sh
   ```

2. **Start 24-Hour Experiment** (if smoke test passes)
   ```bash
   ./run-experiment.sh 24
   ```

### Tomorrow (Day 5)

1. **Morning check** (after 8-10 hours)
   - Verify experiment still running
   - Check for any errors
   - Look at scaling events

2. **Evening check** (after 18-20 hours)
   - Confirm data collection working
   - Check prediction service uptime
   - Review monitoring log

3. **Next morning** (24 hours)
   - Stop experiment
   - Export data
   - Quick validation

### Day 6 (Analysis)

1. Export Prometheus data
2. Process and analyze metrics
3. Generate comparison table
4. Create visualizations
5. Write paper results section

---

## ✅ Day 4: COMPLETE

**Status**: 🟢 **READY FOR EXPERIMENT** 🟢

**Created**:
- ✅ 3 workload manifests (reactive, predictive, prediction-service)
- ✅ 4 orchestration scripts (run, stop, export, analyze)
- ✅ Complete documentation
- ✅ Directory structure

**Time**: ~2 hours (faster than estimated 4-6 hours)

**Next**: Run smoke test, then start 24-hour experiment

---

*Last Updated: September 6, 2026 @ 5:25 PM IST*  
*Next Session: Smoke test + Day 5 monitoring*
