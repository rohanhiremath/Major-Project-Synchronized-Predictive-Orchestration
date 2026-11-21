# TASK #5 COMPLETION: Pre-Registration for Live Data Study

**Date**: 2026-10-18  
**Status**: COMPLETE  
**Document**: PREREG_LIVE_FINAL.yaml

---

## What Was Created

Complete frozen pre-registration for threshold validation on real live host sessions:

### Key Locked Parameters

| Parameter | Value |
|-----------|-------|
| **Data source** | Real live host sessions (15 sessions, 6 calibration + 5 test + 1 pilot) |
| **Signal** | pod_psi_some_avg10 (cgroup memory.pressure, kernel read) |
| **Baseline B** | To be computed from calm sessions |
| **Breach rule** | p99_latency_ms > 2*B for 2+ consecutive bins |
| **Primary FA** | per_alert (alerts/hour in calm periods) |
| **Pass criteria** | Wilson 95%: recall ≥ 0.60, FA/hr ≤ 2.0 |
| **Selection rule** | max recall s.t. FA/hr ≤ 2.0 |

### Frozen Analysis Pipeline

1. **Signal sanity**: AUC on stress bins
2. **Lag analysis**: Cross-correlation at −60 to +60s lags
3. **Calibration sweep**: All (T, k) pairs
4. **Selection**: Apply selection rule mechanically
5. **Held-out test**: Evaluate on test data
6. **Chance check**: Shuffle labels 1000 times

### Data Assignments (Frozen)

**Calibration** (held-out for selection):
- cal_calm_1, cal_calm_2, cal_calm_3 (3 calm)
- cal_burst_1, cal_ramp_1, cal_step_1 (3 stress)

**Test** (held-out for evaluation):
- test_calm_1, test_calm_2 (2 calm)
- test_burst_1, test_ramp_1, test_step_1 (3 stress)

**Pilot** (excluded):
- pilot_calm_baseline (baseline only)

---

## Why This Is Different from Previous Study

### Previous Study (ABANDONED)

- **Data**: Synthetic CSVs (train.csv, test.csv, validation.csv)
- **Signal**: Both psi_some_avg10 and latency_ms from same generator
- **Correlation**: 0.9996 (co-generated)
- **Lag profile**: Flat across all lags (no timing)
- **Result**: Tests 3–7 outputs invalidated
- **Verdict**: Cannot claim any threshold is validated

### New Study (LIVE)

- **Data**: Real live host sessions from actual cgroup and load generator
- **Signal**: pod_psi_some_avg10 (kernel measurement) vs p99_latency_ms (external measurement)
- **Correlation**: Unknown (to be measured)
- **Lag profile**: To be measured (expected peak if reactive)
- **Result**: Can claim threshold is validated if pass criteria met
- **Verdict**: Based on real measurements, not synthetic model

---

## Pre-Registration Principles Applied

✅ **Frozen before analysis**: All rules locked 2026-10-18 before threshold selection  
✅ **Signal locked**: pod_psi_some_avg10 defined and frozen  
✅ **Label frozen**: Breach rule defined and frozen  
✅ **Data splits frozen**: Calibration and test sessions assigned and locked  
✅ **Pass criteria frozen**: Wilson 95% thresholds set upfront  
✅ **Selection rule frozen**: Mechanical max-recall rule defined  
✅ **Stop rules frozen**: Conditions for stopping documented  
✅ **Two FA definitions**: Primary (per_alert) for verdict, exploratory (per_event) for investigation  
✅ **Analysis pipeline frozen**: Tests 1–6 sequence defined  

---

## What Happens Next

### Before Threshold Selection

1. Compute baseline B from calibration calm sessions
2. Verify power: count breach events in calibration and test
3. If underpowered, report and stop (no selection)

### Threshold Selection (Calibration)

1. Sweep all (T, k) pairs on calibration data
2. Apply selection rule mechanically
3. If no viable threshold, report and stop
4. If viable, lock selected (T*, k*)

### Threshold Evaluation (Test)

1. Evaluate selected (T*, k*) on test data
2. Evaluate T=1.8% (project configured) on test data
3. Apply pass criteria (both must pass)
4. Report verdict for each

### Robustness Checks

1. Chance check: shuffle labels, re-run 1000 times
2. Per-session analysis: show results by session
3. Lag profile interpretation: describe signal timing

---

## Commitment to Process

This pre-registration binds the analysis to:
- **No data peeking** before completing calibration analysis
- **No retroactive rule changes** based on observed results
- **Mechanical application** of selection and pass criteria
- **Transparent reporting** of all findings, including negative results
- **Honest interpretation** of lag profile and signal quality

If results do not pass criteria, the conclusion is "NOT_SUPPORTED" — not "let's try a different threshold."

---

## How to Use This Pre-Registration

1. **Read PREREG_LIVE_FINAL.yaml**: This is the authoritative frozen specification
2. **Follow the pipeline order**: Tests 1–6 in sequence, no skipping
3. **Implement each test**: Create test_N_live_*.py for each test
4. **Output frozen artifacts**: test_N_live_*.json files for each result
5. **Compute final verdict**: Based on pass criteria, not judgment

---

## Status Summary

✅ **Pre-registration complete**: PREREG_LIVE_FINAL.yaml frozen  
✅ **All 5 correction tasks done**:
  1. Test 1 retracted (NaN is undefined, not evidence)
  2. Synthetic analysis abandoned (co-generated data)
  3. Live data confirmed available (15 real sessions)
  4. Calm-bin AUC corrected (0.5 is correct)
  5. New pre-registration written (live data study)

✅ **Ready to proceed**: Analysis can begin with frozen rules

---

## Expected Outcome

On real live data, the study will either:

1. **SUPPORTED**: Find a threshold that passes Wilson 95% criteria on real measurements
2. **NOT_SUPPORTED**: Find that no threshold meets criteria (signal not informative enough)
3. **NO_VIABLE_THRESHOLD**: Find that no (T, k) pair meets calibration criteria
4. **UNDERPOWERED**: Find insufficient breach events in test data

All outcomes are valid scientific results when properly pre-registered.

---

**TASK #5 COMPLETE**  
All corrections implemented. New pre-registration frozen on real live data.  
Ready to execute analysis pipeline with proper methodology.
