# Phase 9 Experiment: Quick Start Guide

## Overview

This experiment compares **Reactive HPA** (baseline) vs **Predictive HPA** (PreSync) over a 24-hour period.

## Prerequisites ✅

- Kubernetes cluster running
- Custom Metrics API configured
- Prometheus + Prometheus Adapter installed
- Workload manifests prepared

## Quick Start (5 minutes)

### 1. Start Experiment

```bash
cd experiment/scripts
./run-experiment.sh 24  # 24-hour experiment
```

This will:
- ✅ Clean up any previous experiment
- ✅ Deploy reactive workload (namespace: experiment-reactive)
- ✅ Deploy predictive workload (namespace: experiment-predictive)
- ✅ Deploy prediction service
- ✅ Start background monitoring
- ✅ Verify HPAs are working

### 2. Monitor Progress

```bash
# Watch HPAs (updates every 10 seconds)
watch -n 10 'kubectl get hpa -n experiment-reactive; echo ""; kubectl get hpa -n experiment-predictive'

# Watch pods
watch -n 10 'kubectl get pods -n experiment-reactive -l app=workload; echo ""; kubectl get pods -n experiment-predictive -l app=workload'

# View monitoring log
tail -f ../logs/monitoring_*.log

# Check HPA events
kubectl get events -n experiment-reactive --sort-by='.lastTimestamp' | grep HPA
kubectl get events -n experiment-predictive --sort-by='.lastTimestamp' | grep HPA
```

### 3. Stop Experiment (After 24 hours)

```bash
./stop-experiment.sh
```

This will:
- Stop background monitoring
- Export final state
- Optionally cleanup namespaces

### 4. Export Data

```bash
./export-prometheus-data.sh
```

This exports:
- PSI metrics over time
- Replica counts
- HPA events
- Prediction service metrics

### 5. Analyze Results

```bash
python3 analyze-results.py ../results/reactive_processed.json ../results/predictive_processed.json
```

Generates comparison table with:
- Scale-up latency (p95)
- PSI breach duration
- Breach count
- Pod-hours cost
- False positive rate

## Expected Results

Based on Phase 6 validation:

| Metric | Reactive | Predictive | Improvement |
|--------|----------|------------|-------------|
| Scale-up Latency (p95) | ~72s | ~28s | **61% faster** |
| PSI Breach Duration | ~156s | ~52s | **67% reduction** |
| Breach Count | Baseline | Lower | **Fewer breaches** |
| False Positive Rate | N/A | <5% | **High precision** |

## Troubleshooting

### HPA showing "unknown"

Check if metrics are available:
```bash
kubectl get --raw /apis/custom.metrics.k8s.io/v1beta1/namespaces/experiment-reactive/pods/*/node_pressure_memory_waiting
```

### Prediction service not running

Check logs:
```bash
kubectl logs -n experiment-predictive -l app=prediction-service
```

Common issues:
- Model file not found (check volume mounts)
- Prometheus connection failed (check service URL)
- Missing dependencies (check requirements.txt)

### No scaling happening

Check workload is generating load:
```bash
kubectl exec -n experiment-reactive workload-reactive-0 -c app -- stress-ng --vm 1 --vm-bytes 200M --timeout 60s
```

## Directory Structure

```
experiment/
├── workloads/              # Kubernetes manifests
│   ├── workload-reactive.yaml
│   ├── workload-predictive.yaml
│   └── prediction-service.yaml
├── scripts/                # Orchestration scripts
│   ├── run-experiment.sh
│   ├── stop-experiment.sh
│   ├── export-prometheus-data.sh
│   └── analyze-results.py
├── logs/                   # Experiment logs
│   ├── experiment_*.log
│   ├── monitoring_*.log
│   └── final_state_*.log
└── results/                # Analysis results
    ├── reactive_data_*.json
    ├── predictive_data_*.json
    └── comparison_results.json
```

## Timeline

### Day 4 (Today): Setup ✅
- [x] Create workload manifests
- [x] Create orchestration scripts
- [x] Create analysis tools
- [ ] Run smoke test (5 minutes)
- [ ] Start 24-hour experiment

### Day 5: Monitor
- Morning: Check experiment health (2 hours in)
- Evening: Check progress (12 hours in)
- Overnight: Let run
- Next morning: Stop experiment (24 hours)

### Day 6: Analysis
- Export Prometheus data
- Calculate metrics
- Generate comparison table
- Write paper results section

## Commands Reference

### Start experiment
```bash
./run-experiment.sh 24
```

### Check status
```bash
kubectl get hpa -A
kubectl get pods -A | grep experiment
```

### View logs
```bash
tail -f ../logs/monitoring_*.log
kubectl logs -n experiment-predictive -l app=prediction-service -f
```

### Stop experiment
```bash
./stop-experiment.sh
```

### Export & analyze
```bash
./export-prometheus-data.sh
python3 analyze-results.py ../results/reactive_*.json ../results/predictive_*.json
```

## Success Criteria

- ✅ Both HPAs deployed and active
- ✅ Monitoring running for 24 hours
- ✅ At least 20 spike events captured
- ✅ Prediction service uptime >95%
- ✅ No HPA failures or errors
- ✅ Complete dataset exported

## Next Steps After Experiment

1. **Analyze results** - Generate comparison metrics
2. **Create visualizations** - Plot scale-up latency, PSI over time
3. **Write paper section** - Table 3, Figure 5, Results section
4. **Document findings** - Update PROJECT_SUMMARY.md
5. **Prepare presentation** - Key metrics and improvements

---

**Ready to start!** Run `./run-experiment.sh 24` when you're prepared for the 24-hour experiment.
