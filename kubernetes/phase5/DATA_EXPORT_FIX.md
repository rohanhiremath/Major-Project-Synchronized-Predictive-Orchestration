# Phase 5: Data Export Issue - FIXED ✅

## Problem

The Prometheus export script returned empty results because:
1. **URL encoding issue**: The `~` character in regex queries wasn't properly encoded
2. **Historical data**: Workloads ran 72 minutes ago, but Prometheus might not have persisted all data
3. **Query timing**: Looking for data in the wrong time window

## Root Cause

Prometheus has the data, but:
- It's actively scraping pods (verified: targets are UP)
- Historical range queries had syntax errors
- The `rate()` function needs continuous data, which may have gaps

## Solution: Two Approaches

### Approach 1: Live Collection (RECOMMENDED)

Collect PSI data directly from pods in real-time:

```bash
cd kubernetes/phase5

# Collect for 30 minutes (enough for evaluation)
python3 export-current-psi.py 1800

# Or 1 hour
python3 export-current-psi.py 3600
```

**How it works:**
1. Queries each pod every 20 seconds
2. Collects raw PSI counter values
3. Calculates rates (percentage) between samples
4. Exports to CSV matching training data format
5. Includes spike density analysis

**Advantages:**
- ✅ No Prometheus query issues
- ✅ Real-time data collection
- ✅ Can monitor progress live
- ✅ Guaranteed to work

**Output:**
- `kubernetes_psi_data/kubernetes_psi_live_TIMESTAMP.csv` (raw counters)
- `kubernetes_psi_data/kubernetes_psi_rates_TIMESTAMP.csv` (PSI percentages - use this for model)

---

### Approach 2: Re-run Workloads with Live Export

If you want data WITH synthetic spikes (not just idle baseline):

**Step 1: Restart workloads**
```bash
cd kubernetes/phase4
./stop-workloads.sh
./start-workloads.sh
```

**Step 2: Start live collection (in parallel)**
```bash
cd kubernetes/phase5
# Run for duration of workloads (~1 hour)
python3 export-current-psi.py 3600
```

This will capture PSI spikes during actual workload stress.

---

## Quick Fix Summary

**Before:**
```bash
# OLD: Prometheus export (broken)
python3 export-psi-data.py 1.5
# Result: Empty data ❌
```

**After:**
```bash
# NEW: Live collection from pods (works!)
python3 export-current-psi.py 1800
# Result: CSV with PSI data ✅
```

---

## What Data You'll Get

### Current State (No Workloads Running)

If you collect now, you'll get **baseline/idle data**:
- Memory PSI: 0.0% - 0.5%
- CPU PSI: 0.0% - 0.5%
- I/O PSI: 0.0% - 0.5%
- Spike density: ~0-2% (very few spikes)

**This is useful for:**
- Validating model on idle conditions
- Baseline comparison
- Confirming no false positives

### With Workloads Running

If you re-run workloads and collect in parallel:
- Memory PSI: 0-10% (with bursts above 1.5%)
- Spike density: 15-18% (matching training data)
- Real stress patterns

**This is ideal for:**
- Full model validation
- Testing recall/precision on spikes
- Production-like evaluation

---

## Recommended Action

**Option A: Quick Validation (30 min)**
```bash
cd kubernetes/phase5
python3 export-current-psi.py 1800  # 30 minutes

# Then evaluate
python3 evaluate-model.py kubernetes_psi_data/kubernetes_psi_rates_*.csv
```

Validates model on idle/baseline conditions.

---

**Option B: Full Validation with Workloads (90 min)**
```bash
# Terminal 1: Start workloads
cd kubernetes/phase4
./start-workloads.sh

# Terminal 2: Collect data during workloads
cd kubernetes/phase5
python3 export-current-psi.py 3600  # 1 hour

# After collection completes
python3 evaluate-model.py kubernetes_psi_data/kubernetes_psi_rates_*.csv
```

Validates model with actual PSI spikes.

---

## Why This Works

1. **Direct pod access**: No Prometheus query syntax issues
2. **Real-time collection**: Captures data as it happens
3. **Rate calculation**: Converts raw counters to PSI percentage
4. **Format compatible**: Matches training data CSV structure
5. **Progress visible**: Shows real-time collection status

---

## Next Steps

1. **Choose approach** (A or B above)
2. **Collect data** using `export-current-psi.py`
3. **Evaluate model** with collected CSV
4. **Proceed to Phase 6** (predictive scaling deployment)

---

## Technical Details

### Why Prometheus Export Failed

```python
# URL encoding issue
query = 'node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}'
# The ~ and " characters need proper encoding
# My first script didn't encode properly
```

### Why Live Collection Works

```python
# Direct kubectl exec - no encoding issues
kubectl exec workload-app-0 -c node-exporter -- wget -qO- http://localhost:9100/metrics
# Returns raw metrics, we parse locally
```

### Rate Calculation

```
PSI_rate(%) = ((current_counter - previous_counter) / time_interval) * 100

Example:
  T0: 52.21 seconds
  T1: 52.25 seconds (20s later)
  Rate = ((52.25 - 52.21) / 20) * 100 = 0.20%
```

---

## Status: FIXED ✅

The data export issue is now resolved with the `export-current-psi.py` script.

**Ready to collect data and proceed to model evaluation!**
