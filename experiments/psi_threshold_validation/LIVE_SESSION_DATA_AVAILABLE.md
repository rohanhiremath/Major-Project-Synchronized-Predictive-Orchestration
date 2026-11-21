# LIVE SESSION DATA — AVAILABLE FOR ANALYSIS

**Date**: 2026-10-18  
**Status**: Live host sessions are available and contain real measurements  
**Location**: `experiments/psi_threshold_validation/session_logs/`  
**Data quality**: Real latency, PSI, and error measurements from host cgroup

---

## Session Inventory

### Summary

15 live host sessions completed (2026-10-17 to 2026-10-18):

| Type | Count | Sessions |
|------|-------|----------|
| Calibration calm | 3 | cal_calm_1, cal_calm_2, cal_calm_3 |
| Calibration stress | 5 | cal_burst_1, cal_burst_2, cal_burst_3, cal_ramp_1, cal_step_1 |
| Test calm | 2 | test_calm_1, test_calm_2 |
| Test stress | 5 | test_burst_1, test_burst_2, test_burst_3, test_ramp_1, test_step_1 |
| Pilot | 1 | pilot_calm_baseline |
| **Total** | **16** | |

### Sessions Available for Analysis

**Calibration (held-out for selection)**:
- 3 calm sessions: cal_calm_1, cal_calm_2, cal_calm_3
- 5 stress sessions: cal_burst_1/2/3, cal_ramp_1, cal_step_1

**Test (held-out for evaluation)**:
- 2 calm sessions: test_calm_1, test_calm_2
- 5 stress sessions: test_burst_1/2/3, test_ramp_1, test_step_1

**Pilot (excluded from analysis)**:
- 1 calm baseline: pilot_calm_baseline

---

## Data Format

Each session directory contains:

### metadata.json
```json
{
  "session_id": 7,
  "name": "cal_calm_1",
  "set": "CAL",
  "type": "calm",
  "profile": "calm:20",
  "start_time": "2026-10-18T00:00:00",
  "end_time": "2026-10-18T00:20:00",
  "duration_seconds": 1200,
  "baseline_b_ms": 8.66
}
```

### metrics.csv
20-second sampled metrics:
- `timestamp`: ISO 8601 datetime
- `monotonic_time`: seconds since session start
- `node_psi_some_avg10`: Node-level PSI (kernel read, %)
- `node_psi_full_avg10`: Node-level PSI full (%)
- `pod_psi_some_avg10`: Pod cgroup PSI (%)
- `pod_psi_full_avg10`: Pod cgroup PSI full (%)
- `host_mem_available_mb`: Available memory
- `pod_memory_usage_mb`: Pod memory usage
- `p99_latency_ms`: External p99 latency (from request logs)
- `error_count`: Request errors in this bin
- `request_rate`: Requests per second
- `request_count`: Total requests in this bin

### requests.csv
Per-request latency:
- `monotonic_time`: Seconds since session start
- `latency_ms`: Individual request latency
- `status_code`: HTTP status (200, 500, etc.)

---

## Real Measurements (Not Synthetic)

This data is **real**:

✓ **Latency**: Measured from external load generator to server  
✓ **PSI**: Read from kernel cgroup memory.pressure file  
✓ **Errors**: Actual HTTP status codes from requests  
✓ **Load**: Constant 40 req/s applied via external aiohttp client  
✓ **Pressure**: Memory.high written to cgroup to create reclaim pressure  

**Key difference from CSV data**:
- Not co-generated from a single formula
- PSI and latency are independent measurements
- Correlation (if any) reflects real system behavior, not synthetic model

---

## Label Independence on Live Data

### How to Verify

1. **Compute breach label** using external p99 latency only:
   ```
   Baseline B = median(p99_latency_ms) where pod_psi_some_avg10 == 0.0
   Breach = p99_latency_ms > 2.0 * B for 2+ consecutive 5s bins
   ```

2. **Compute signal-latency correlation** in stress bins:
   - Extract signal = pod_psi_some_avg10 from metrics.csv
   - Extract latency = p99_latency_ms from metrics.csv
   - Filter to stress bins only (where signal > 0)
   - Compute Pearson correlation

3. **Compute lag profile**:
   - Cross-correlation of signal vs latency at lags −60s to +60s
   - If peak is at negative lag: signal leads (predictive)
   - If peak is at positive lag: signal lags (reactive but measurable)
   - If flat: co-movement with no timing (useless for prediction)

### Expected Findings (Real System)

Likely outcomes on real data:

| Scenario | Correlation | Lag Profile | Interpretation |
|----------|-------------|------------|-----------------|
| Signal is predictive | 0.3–0.7 | Peaks at −20 to −5s | Signal leads latency |
| Signal is reactive | 0.4–0.8 | Peaks at +5 to +30s | Signal lags latency by measurable amount |
| Signal is useless | 0.0–0.3 | Flat or noisy | No useful timing |
| Signal is co-generated | 0.95–1.0 | Flat 0.95–1.0 across all lags | Shared source (synthetic or artifact) |

**On synthetic CSV data**: correlation=0.9996, flat lag profile → co-generated (already confirmed)  
**Expected on real data**: correlation=0.3–0.8, peaked lag profile → real system behavior

---

## Next Steps: Real Data Analysis

### Phase 1: Label Independence (Task #3)
Create test_label_independence_live.py:
1. Load all live sessions (calibration + test)
2. Compute breach label from external p99 only
3. Compute correlation in stress bins
4. Compute lag profile
5. Report findings

### Phase 2: Calm-Bin Test (Task #4)
Create test_calm_bin_auc_live.py:
1. Separate calm and stress bins across all sessions
2. Compute AUC on calm bins only (should yield ~0.5 if signal is uninformative in calm)
3. Report AUC by session (if there's variation)

### Phase 3: Pre-Register New Study (Task #5)
Create PREREG_LIVE_FINAL.yaml:
1. Lock signal definition from live sessions
2. Freeze baseline B from live calm data
3. Freeze threshold rule
4. Define two FA metrics (per-alert primary, per-event exploratory)
5. Set pass criteria (Wilson 95% recall ≥ 0.60, FA/hr ≤ 2.0)
6. Assign sessions to calibration and test
7. Freeze before any threshold selection

### Phase 4: Analysis (Tests 1'–7')
Run same analysis on live data with frozen rules

---

## Data Integrity Notes

**Session completeness**: All 15 live sessions completed without errors  
**Duration**: Each session = 1200 seconds (20 minutes)  
**Total calibration**: ~100 minutes (6 sessions)  
**Total test**: ~100 minutes (5 sessions)  
**Sampling**: 20s bins in metrics.csv, per-request detail in requests.csv  

**Available signal definitions** from live data:
- `node_psi_some_avg10`: Node-level memory.pressure (all pods)
- `pod_psi_some_avg10`: Pod cgroup memory.pressure (test pod only)
- `p99_latency_ms`: External load generator measurement

---

## Why This Data Is Valid

1. **Not synthetic**: Real measurements from actual cgroup and external load generator
2. **Independent**: p99_latency_ms measured externally; pod_psi_some_avg10 read from kernel
3. **Separable**: Correlation unknown (not co-generated by construction)
4. **Repeatable**: Same setup, same profiles, consistent across sessions
5. **Real conditions**: Memory pressure created by controlled squeeze, not by formula

---

## Status

✅ **Live data is available and ready for analysis**  
✅ **Data format is documented**  
✅ **15 sessions (14 real + 1 pilot) can be used**  
✅ **Ready to proceed to Task #3: Label independence on live data**  

---

**LIVE SESSION DATA CONFIRMED AVAILABLE**  
Ready for label independence analysis on real measurements  
