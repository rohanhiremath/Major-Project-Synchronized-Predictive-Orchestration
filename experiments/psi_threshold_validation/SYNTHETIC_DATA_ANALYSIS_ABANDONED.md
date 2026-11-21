# SYNTHETIC DATA ANALYSIS — OFFICIALLY ABANDONED

**Date**: 2026-10-18  
**Files affected**: train.csv, test.csv, validation.csv  
**Status**: CSV-based threshold validation is DISCONTINUED  
**Reason**: Data is co-generated; any threshold found validates the generator, not the system

---

## What Was Done (Now Invalidated)

Tests 3–7 were executed on synthetic CSVs:

| Test | Result | Status |
|------|--------|--------|
| Test 3 | AUC=0.9998 | Invalidated |
| Test 4 | Flat lag profile | Invalidated |
| Test 5 | Selected T=0.5% | Invalidated |
| Test 6 | Both T pass criteria | Invalidated |
| Test 7 | Chance check PASS | Invalidated |

All results show what the data generator produces, not what real infrastructure does.

---

## Why These Results Are Invalid

### 1. Co-Generation Proof

**Correlation in stress bins**: 0.9996–0.9998

This is not a property of real systems. Real independent measurements:
- Random measurement noise has correlation < 0.5
- Even correlated phenomena rarely exceed 0.95
- 0.9996 means the variables are almost perfectly determined by each other

**Source**: Both variables generated from same synthetic model (`generate_server_data.py` line 95)

### 2. Flat Lag Profile Proof

**Lag scan** from −60s to +60s:
- All lags show correlation ≈ 0.99–1.0
- No peak at any particular lag
- Slight roll-off only at extremes (±60s)

**What this means**:
- Real reactive signal: Would peak at a specific lag (e.g., "signal lags outcome by 10s")
- Real predictive signal: Would peak at negative lag (e.g., "signal leads outcome by 5s")
- This data: Flat across all lags → no timing relationship, just co-generation

### 3. Perfect Results Expected

When signal and outcome are co-generated:
- AUC=1.0 is expected (trivial to predict)
- Recall=1.0 at low thresholds is expected (signal covers all outcomes)
- FA/hr=0 is expected (signal matches generator's breach events)

These results prove the methodology works; they do NOT prove the threshold is useful.

---

## What Tests 3–7 Actually Showed

✓ **Methodology is sound**: 
  - Pre-registration before analysis
  - Frozen rules applied mechanically
  - Pass criteria stated upfront
  - Chance check performed
  - Reproducible code

✗ **Threshold validation is invalid**:
  - Data validates the generator, not the system
  - 0.9996 correlation is synthetic
  - Flat lag profile means no real timing
  - No claim about production can be made

---

## What These Files Are Kept For

**train.csv, test.csv, validation.csv remain valid for**:
1. **Forecasting pipeline training**: TFT model can be trained on this synthetic data
2. **Methodology testing**: Code can be tested end-to-end
3. **As reference data**: Shows what "perfect separation" looks like

**They are NOT valid for**:
1. **Threshold validation**: Cannot claim any threshold is production-ready
2. **Signal quality assessment**: 0.9996 correlation is not a signal quality metric
3. **Real-world predictions**: Results do not generalize to real infrastructure

---

## The Core Problem

The data generator (`generate_server_data.py`) creates:

```python
latency_ms = 45 + 28*load + 75*psi_some_avg10 + noise
psi_some_avg10 = np.clip(pressure*0.75 + noise, ...)
pressure = ... (depends on load)
```

**Both latency and psi_some_avg10 depend on the same `load` variable.**

This is a synthetic model, not a measurement. You cannot validate a threshold by testing the formula against itself.

---

## Why This Matters for Production

A production threshold must predict real latency from real PSI.

**In this synthetic data**:
- "Real latency" = formula output (deterministic, no real variability)
- "Real PSI" = formula output (deterministic, no real variability)
- Correlation = 1.0 (by construction)

**In production**:
- Real latency = actual response times (variable, noisy, depends on many factors)
- Real PSI = actual kernel measurement (variable, depends on memory pressure)
- Correlation = unknown (could be 0.1, 0.5, 0.9, or anything)

**Any threshold validated on synthetic data may fail catastrophically in production.**

---

## What Happens to Previous Results

| File/Result | Status | Disposition |
|------------|--------|-------------|
| test_3_results.json | Invalidated | Keep for reference; do not cite as validation |
| test_4_results.json | Invalidated | Keep for reference; do not cite as validation |
| test_5_results.json | Invalidated | Keep for reference; do not cite as validation |
| test_6_results.json | Invalidated | Keep for reference; do not cite as validation |
| test_7_results.json | Invalidated | Keep for reference; do not cite as validation |
| FINAL_VERDICT.md | Invalidated | Archive; create new verdict based on live data |
| PREREG_FROZEN.yaml | Invalidated | Archive; create new pre-registration for live data |

---

## What's Required Now

### Only Valid Data Source: Live Host Sessions

Earlier experiments ran live PSI threshold tests on a host. Those sessions produced:
- Real client measurements (latency from load generator on the same host)
- Real PSI readings (from cgroup or Prometheus)
- Real breach labels (from actual p99 latency degradation)

**These sessions are the only valid foundation for threshold validation.**

### Required Analysis on Live Data

1. **Label independence verification**:
   - Derive breach label from external p99 only
   - Compute correlation(signal, latency) on live sessions
   - Compute lag profile
   - **Expected findings**: If correlation is 0.2–0.7 and lag profile peaks at +5 to +30s, the signal is reactive but measurable

2. **Pre-register new study** with frozen rules:
   - Signal definition (must be from live measurement, not synthetic)
   - Frozen baseline B (from live calm sessions)
   - Frozen threshold rule
   - Two FA definitions (per-alert primary, per-event exploratory)
   - Pass criteria (Wilson 95%)
   - Session assignments

3. **Run new analysis** on live calibration and test sessions

---

## Summary

**Synthetic CSV analysis**: ❌ ABANDONED  
**Reason**: Data is co-generated; validates generator, not system  
**Threshold validation**: Must use live host sessions only  
**Timeline**: Next phase depends on availability of live session data  

---

## Commitment

No threshold will be recommended or deployed based on analysis of train.csv, test.csv, or validation.csv.

Any future threshold recommendation will be based on:
1. Real measurements from live infrastructure
2. Proper pre-registration before analysis
3. Separation of calibration and test data
4. Frozen pass criteria
5. Chance check or reproducibility test

---

**SYNTHETIC DATA ANALYSIS OFFICIALLY CLOSED**  
Date: 2026-10-18  
Next: Await live session data for proper validation  
