# Phase 4: Quick Start Guide

## 🚀 30-Second Start

```bash
cd kubernetes/phase4
./start-workloads.sh
```

That's it! Workloads are now running.

---

## 📊 Monitor in Real-time

```bash
# Option 1: Terminal monitoring
./monitor-workloads.sh

# Option 2: Prometheus
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090
# Open: http://localhost:9090
# Query: rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m]) * 100

# Option 3: Grafana
kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3000:80
# Open: http://localhost:3000 (admin / prom-operator)
```

---

## ⏱️ Timeline

**Workload Duration:** ~1-2 hours (auto-completes)

**Cycles:**
- Memory stress: 10 cycles (60s burst + 300s idle = 6 minutes per cycle = 60 min total)
- CPU stress: 15 cycles (45s burst + 200s idle = 4 min per cycle = 60 min total)
- Combined stress: 8 cycles (90s burst + 400s idle = 8 min per cycle = 64 min total)
- I/O stress: Various patterns

**Expected PSI Patterns:**
- Most of the time: < 0.5% (idle)
- During bursts: 1.5% - 10% (spikes)
- Overall spike density: 15-18%

---

## 🎯 What to Look For

**In Monitor Script:**
```
Memory PSI (Full)
workload-app-0        2.34% ██████████ 🔴 SPIKE   <- Good!
workload-app-1        0.12% ░          🟢 IDLE
workload-app-2        3.56% ████████████████ 🔴 SPIKE   <- Good!

Spike density: 16.2% (target: ~16%)   <- Perfect!
```

**In Grafana Dashboard:**
- Memory PSI graph should show bursts above 1.5% threshold (yellow line)
- "Spikes (Last Hour)" panel should show 40-60 spikes
- Bursts should alternate with idle periods

---

## 📦 Collect Data (After 1 Hour)

```bash
# Collect 1 hour of data
./collect-data.sh 3600

# Or collect 2 hours
./collect-data.sh 7200
```

**Output:** `workload_data/workload_psi_YYYYMMDD_HHMMSS.csv`

---

## 🛑 Stop Workloads

```bash
./stop-workloads.sh
```

PSI should return to < 0.5% within 1-2 minutes.

---

## ❓ Troubleshooting

### No Spikes Observed

**Check workload status:**
```bash
kubectl get jobs -l workload-type
kubectl logs -l workload-type=stress --tail=50
```

**Possible causes:**
- Jobs failed to start (check logs)
- Resource limits too restrictive (increase in YAML)
- Not enough time elapsed (wait 5-10 minutes)

**Solution:** Increase intensity in workload YAML and restart.

---

### Spike Density Too Low (< 14%)

**Solution:** Increase workload intensity:
1. Stop current workloads: `./stop-workloads.sh`
2. Edit `workload-stress.yaml`:
   - Increase `--vm-bytes` (e.g., 400M → 600M)
   - Add more workers (e.g., `--vm 2` → `--vm 3`)
   - Reduce idle time (e.g., 300s → 200s)
3. Restart: `./start-workloads.sh`

---

### Spike Density Too High (> 20%)

**Solution:** Decrease workload intensity:
1. Stop current workloads: `./stop-workloads.sh`
2. Edit `workload-stress.yaml`:
   - Decrease `--vm-bytes` (e.g., 400M → 300M)
   - Reduce workers
   - Increase idle time (e.g., 300s → 400s)
3. Restart: `./start-workloads.sh`

---

### FIO Jobs Failing

**Error:** `Cannot open PVC`

**Solution:** FIO jobs need per-pod PVC configuration. The start script attempts to configure this automatically, but you may need to manually create separate job files for each pod with the correct PVC names.

**Check PVC names:**
```bash
kubectl get pvc | grep workload
```

**Workaround:** Focus on stress-ng workloads (CPU/memory) which are sufficient to generate PSI spikes. FIO (I/O) is optional.

---

## ✅ Success Criteria

- [ ] Workload jobs running (3-6 jobs active)
- [ ] PSI spikes visible in Prometheus (> 1.5%)
- [ ] Spike density 14-20% over 1-hour window
- [ ] No pod restarts or OOMKills
- [ ] Data collected in CSV format

---

## ➡️ Next: Phase 5

Once you have 1-2 hours of data with ~16% spike density:

```bash
cd ../phase5
# Follow Phase 5 README for model evaluation
```

Phase 5 will:
- Run model predictions on collected Kubernetes PSI data
- Compare predicted vs actual spikes
- Validate 94.65% recall on real data
- Generate evaluation report
