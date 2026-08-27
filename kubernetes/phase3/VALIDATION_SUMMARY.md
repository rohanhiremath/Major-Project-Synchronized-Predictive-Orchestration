# Phase 3: Validation Summary

## Status: ✅ READY FOR VALIDATION

### Phase 2 Deployment: VERIFIED ✅

**Deployed Infrastructure:**
- ✅ Pods: 3/3 Running (workload-app-0, workload-app-1, workload-app-2)
- ✅ Containers: 2/2 ready per pod (app + node-exporter)
- ✅ PVCs: 6/6 Bound (21Gi total)
- ✅ Services: workload-svc (headless) + workload-nodeport
- ✅ ServiceMonitor: workload-psi-monitor (20s interval)

**Prometheus Scraping: CONFIRMED ✅**
- ✅ Targets discovered: 3/3 workload pods
- ✅ Target health: UP on all 3 targets
- ✅ Scrape URLs:
  - `http://10.244.0.13:9100/metrics` (workload-app-0)
  - `http://10.244.0.16:9100/metrics` (workload-app-1)
  - `http://10.244.0.19:9100/metrics` (workload-app-2)
- ✅ Scrape interval: 20s

**PSI Metrics: AVAILABLE ✅**
- ✅ Direct pod metrics: 15 PSI metrics per pod
- ✅ Prometheus collection: 3 time series per metric type
- ✅ Metrics types confirmed:
  - `node_pressure_memory_stalled_seconds_total`
  - `node_pressure_memory_waiting_seconds_total`
  - `node_pressure_cpu_stalled_seconds_total`
  - `node_pressure_cpu_waiting_seconds_total`
  - `node_pressure_io_stalled_seconds_total`
  - `node_pressure_io_waiting_seconds_total`

**Sample Data (at time of verification):**
```
workload-app-0: 40.57 seconds (total memory stalled time)
workload-app-1: 40.57 seconds (total memory stalled time)
workload-app-2: 40.57 seconds (total memory stalled time)
```

---

## Next Steps

### 1. Access Prometheus UI

```bash
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090
```

Then open: **http://localhost:9090**

**Test these queries:**

```promql
# Memory PSI rate (percentage)
rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m]) * 100

# CPU PSI rate
rate(node_pressure_cpu_stalled_seconds_total{pod=~"workload-.*"}[1m]) * 100

# I/O PSI rate
rate(node_pressure_io_stalled_seconds_total{pod=~"workload-.*"}[1m]) * 100

# Check all workload targets are UP
up{pod=~"workload-.*"}
```

**Expected results:**
- All queries return 3 time series (one per pod)
- Memory PSI rate: 0.0% - 0.5% (idle system)
- CPU PSI rate: 0.0% - 0.5%
- I/O PSI rate: 0.0% - 0.5%
- All targets: `up = 1`

---

### 2. Run Validation Scripts

```bash
cd kubernetes/phase3

# Full validation (includes 10-minute baseline measurement)
./validate-all.sh

# Or individual scripts:
./validate-metrics.sh              # Check scrape interval and data quality
./baseline-measurement.sh 600      # Collect 10-minute idle baseline
./create-dashboard.sh              # Import Grafana dashboard
```

---

### 3. Import Grafana Dashboard

```bash
# Start port-forward
kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3000:80
```

Then:
1. Open **http://localhost:3000**
2. Login: `admin` / `prom-operator`
3. Click **+** → **Import**
4. Upload: `kubernetes/phase3/grafana-dashboard.json`
5. Select Prometheus datasource
6. Click **Import**

**Dashboard includes:**
- Real-time PSI metrics (Memory, CPU, I/O)
- Spike detection (threshold: 1.5%)
- Resource usage (CPU, Memory)
- Active pods count
- Model threshold indicator

---

## Validation Checklist

### Infrastructure ✅
- [x] 3 pods running with 2/2 containers
- [x] 6 PVCs bound (2 per pod)
- [x] Services created and endpoints available
- [x] ServiceMonitor configured

### Prometheus ✅
- [x] All 3 targets discovered
- [x] All targets healthy (UP)
- [x] Scrape interval: 20s
- [x] PSI metrics being collected

### PSI Metrics ✅
- [x] Metrics available directly from pods
- [x] Metrics visible in Prometheus
- [x] 6 metric types × 3 pods = 18 time series

### Remaining Tasks
- [ ] Verify rate calculations work (need 1-2 min of data)
- [ ] Collect 10-minute idle baseline
- [ ] Import Grafana dashboard
- [ ] Compare baseline with training data expectations

---

## Troubleshooting

### Issue: Port-forward timeout in scripts

**Symptom:** Scripts fail with connection refused or timeout

**Solution:** Prometheus needs time to start accepting connections. Increase sleep time in scripts or run port-forward manually:

```bash
# Terminal 1: Keep port-forward running
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090

# Terminal 2: Run validation
cd kubernetes/phase3
./validate-metrics.sh
```

### Issue: Rate queries return empty

**Symptom:** `rate()` queries return no data

**Solution:** Need at least 1 minute of scraped data. Wait 1-2 minutes after ServiceMonitor is discovered, then retry.

### Issue: ServiceMonitor not discovered

**Symptom:** Targets don't appear in Prometheus

**Solution:** 
1. Check ServiceMonitor labels match Prometheus selector
2. Verify ServiceMonitor is in correct namespace (default)
3. Check Prometheus Operator logs
4. Wait 2-3 minutes for discovery

**This issue was resolved:** ServiceMonitor took ~20 minutes to be discovered, but is now working.

---

## Timeline

- **Phase 2 Deployment:** Completed ~25 minutes ago
- **ServiceMonitor Discovery:** ~20 minutes for Prometheus to pick it up
- **First Scrapes:** Confirmed at validation time
- **Rate Data Available:** 1-2 minutes after first scrapes

**Current Status:** All infrastructure ready, rate data should be available now or within next few minutes.

---

## Success Criteria - Current Status

| Criterion | Status | Notes |
|-----------|--------|-------|
| 3 pods running | ✅ PASS | All 2/2 containers ready |
| 6 PVCs bound | ✅ PASS | 21Gi total |
| Prometheus targets | ✅ PASS | 3/3 UP, 20s interval |
| PSI metrics in pods | ✅ PASS | 15 metrics per pod |
| PSI metrics in Prometheus | ✅ PASS | 18 time series total |
| Idle baseline < 0.5% | ⏳ PENDING | Need to run baseline-measurement.sh |
| Grafana dashboard | ⏳ PENDING | Need to import |
| Rate queries working | ⏳ PENDING | Wait 1-2 min, then test in UI |

---

## Recommended Next Action

**Option 1: Manual Verification (Fastest)**
```bash
# Access Prometheus UI
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090
# Open http://localhost:9090
# Run query: rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m]) * 100
# Verify: Should see 3 lines, values < 0.5%
```

**Option 2: Run Full Validation (Comprehensive)**
```bash
cd kubernetes/phase3
./validate-all.sh
```

**Option 3: Import Dashboard (Visual)**
```bash
cd kubernetes/phase3
./create-dashboard.sh
```

---

## Key Achievement

✅ **Phase 2 infrastructure is fully operational!**

- Kubernetes workload deployed successfully
- PSI metrics collection working
- Prometheus scraping at 20s intervals
- Ready for Phase 3 validation and Phase 4 workload generation

**All critical components verified and functioning correctly.** 🎉
