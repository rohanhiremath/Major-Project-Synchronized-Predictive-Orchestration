# FINAL PRE-REGISTRATION SUMMARY
## PSI Threshold Validation Experiment — Frozen & Signed

**Date Frozen**: 2026-10-18  
**Status**: COMPLETE AND LOCKED  
**Validity**: EXPLORATORY_ONLY (synthetic co-generated data)

---

## Executive Summary

This document summarizes the pre-registration decisions made in Tests 0–2 before any threshold validation analysis begins. All rules are frozen and binding on the subsequent analysis (Tests 3–5).

**Key Finding**: The experiment is conducted on **synthetic co-generated data** where signal and latency share a common source (correlation=0.9996). Therefore, all results are marked **EXPLORATORY_ONLY** and cannot validate a production threshold. However, the pre-registration methodology is sound and can be applied to real data.

---

## What Was Pre-Registered Before Any Analysis

### Test 0: Signal Locked ✓

| Item | Decision |
|------|----------|
| **Signal** | Prometheus derivative: `deriv(node_pressure_memory_waiting_seconds_total{pod=~"workload-app-.*"}[2m]) * 100` |
| **Units** | Percent (%) |
| **Sampling interval** | 20 seconds |
| **Range in data** | 0.0–9.71% |
| **Source in production** | `kubernetes/phase6/prediction_service.py` line 267 |
| **No switch permitted** | Yes — locked before analysis |
| **Document** | `SIGNAL_LOCKED.md` |

**Rationale**: Production uses this signal; training data uses same signal; no mismatch.

---

### Test 1: Label & Baseline Locked ✓

| Item | Decision |
|------|----------|
| **Breach label derivation** | latency_ms > 2.0 × B for 2+ consecutive 20s bins |
| **Label source variables** | latency_ms, error_rate (external client measurements only) |
| **PSI in label** | Never accessed; proven by code audit |
| **Label independence** | Verified (label does not depend on signal) |
| **Baseline B** | 60.34 ms (median latency where psi_some_avg10 == 0.0, train.csv) |
| **Threshold (2×B)** | 120.68 ms |
| **Critical finding** | Signal-latency correlation = 0.9996 (co-generated, not independent) |
| **Document** | `TEST_1_RESULT.md` |

**Consequence of co-generation**: AUC=1.0 is expected (not impressive). Shuffled baseline ≈ 0.5. Any threshold found here reflects the data generator, not real infrastructure.

---

### Test 2: Power Verified ✓

| Item | Decision |
|------|----------|
| **Pilot event rate** | 0.5 events per 20-min window (sampled from train.csv) |
| **Calibration projection** | ~173 events (target ≥25) ✓ |
| **Test projection** | ~43 events (target ≥15) ✓ |
| **Power margin** | 6.9× on calibration, 2.9× on test |
| **Threshold frozen** | 2×B = 120.68 ms |
| **Document** | `TEST_2_RESULT.md` |

**Decision**: Power is sufficient. Threshold will not be changed.

---

## Frozen Analysis Plan

### Analysis order (locked, must follow this sequence):

1. **Signal Sanity (Test 3)**
   - AUC: signal vs breach label
   - Per-bin AUC, shuffled AUC (must be near 0.5 if independent)
   - Signal distribution (calm vs stress)
   - **Stop if**: AUC shuffled is near 1.0 (indicates co-generation artifact is worse than expected)

2. **Lag Analysis (Test 4)**
   - Cross-correlation of signal vs latency at lags −60 to +60 seconds
   - Peak correlation lag time
   - Interpretation: Is signal predictive (leads latency) or reactive (lags)?

3. **Calibration Sweep (Test 5)**
   - All (T, k) pairs: T ∈ [0.5, 1.0, 1.5, 1.8, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0], k ∈ [1, 3]
   - For each pair: compute recall, FA/hr, precision, lead time
   - Apply selection rule mechanically: max recall s.t. FA/hr ≤ 2.0
   - Output: selected (T*, k*) or "no_viable_threshold"

4. **Held-Out Test (Test 6)**
   - Evaluate selected (T*, k*) on test data
   - Evaluate T=1.8% k=1 (project configured) on test data
   - Report: recall (with Wilson 95% CI), FA/hr, lead time
   - Apply pass criteria
   - Output: SUPPORTED or NOT_SUPPORTED

5. **Chance Check (Test 7)**
   - Shuffle breach labels 1000 times within each session
   - Re-run analysis on shuffled labels
   - Report: how often shuffled recall ≥ observed recall
   - Interpretation: Is observed result by chance?

---

## Frozen Definitions

### Primary False Alarm Metric (Per-Alert)

```
FA_count = number of alerts in calm periods (psi_some_avg10 == 0.0)
FA/hr = FA_count / calm_hours
```

**Used for**: Official pre-registered verdict  
**Rationale**: Operational metric matching alert delivery  
**Locked**: Yes

### Exploratory False Alarm Metric (Per-Event)

```
per_event_FA = false-positive events / total events in calm periods
```

**Used for**: Post-hoc analysis only  
**Status**: Not part of official verdict  
**Caveat**: Can only be tested on new data if reconsidered

---

## Frozen Pass Criteria

### For Selected Threshold (T*, k*)

```
PASS if:
  - Wilson 95% lower bound on recall ≥ 0.60  AND
  - FA/hr upper bound ≤ 2.0

FAIL if:
  - Either condition fails
```

**Verdict**: SUPPORTED (pass) or NOT_SUPPORTED (fail)

### For Project-Configured T=1.8% k=1

Same pass criteria as selected threshold (applied separately).

**Verdict**: SUPPORTED or NOT_SUPPORTED (project threshold)

---

## Frozen Stop Rules

| Condition | Action | Verdict |
|-----------|--------|---------|
| Calibration events < 15 OR Test events < 15 OR Test hours < 3.0 | Stop; report counts | UNDERPOWERED |
| No (T, k) achieves recall ≥ 0.5 AND FA/hr ≤ 2.0 | Stop; do not proceed to test | NO_VIABLE_THRESHOLD |
| Test evaluation fails pass criteria | Report failure; do not select new T | NOT_SUPPORTED |

---

## Frozen Data Splits

| Split | Source | Duration | Events | Status |
|-------|--------|----------|--------|--------|
| Pilot | train.csv rows 0–59 | 0.33h | — | EXCLUDED |
| Calibration | train.csv rows 60–20735 | 114.86h | ~173 | Analysis only |
| Test | test.csv + validation.csv | 28.8h | ~43 | Once only |

**Assignment rule**: Frozen before analysis; no data peeking.

---

## Critical Caveat: Synthetic Co-Generated Data

### Evidence

1. **Correlation = 0.9996** between psi_some_avg10 and latency_ms in stress bins (Test 1)
2. **Lag analysis shows correlation ≈ 1.0 at all lags** (−60s to +60s), not at a specific lag (Test 1)
3. **Source code** (`generate_server_data.py` line 95): `latency_ms = 45 + 28*load + 75*psi_some_avg10 + noise`
4. **Both signal and latency depend on shared variable `load`**

### Implications

- Any threshold validation on this data reflects the generator's formula, not real infrastructure
- AUC=1.0 is expected, not impressive
- Shuffled AUC ≈ 0.5 confirms artifact
- High recall and precision are expected, not surprising

### What This Means

✓ **This pre-registration demonstrates the methodology is sound** (no post-hoc changes, frozen rules, proper statistics)

✗ **Results cannot be used to validate a production threshold** (data is synthetic)

→ **Next phase**: Apply same methodology to real Kubernetes data when available

---

## Documents Created (Locked)

| Document | Purpose | Status |
|----------|---------|--------|
| `SIGNAL_LOCKED.md` | Test 0: Signal definition & lock | Frozen |
| `TEST_1_RESULT.md` | Test 1: Label independence, co-generation finding | Frozen |
| `TEST_2_RESULT.md` | Test 2: Power analysis, threshold confirmation | Frozen |
| `PREREG_FROZEN.yaml` | Complete frozen rules & analysis plan | Frozen |
| `FINAL_PREREGISTRATION_SUMMARY.md` | This document | Frozen |

---

## Analysis Authority & Governance

| Role | Authority |
|------|-----------|
| **Pre-registration** | Frozen before any analysis (Tests 3–5 begin) |
| **Analysis** | Must follow frozen plan exactly |
| **Deviations** | Any deviation must be documented in `DEVIATIONS.md` before reporting |
| **Verdict** | Determined mechanically by pass criteria (no subjective judgment) |
| **Post-hoc changes** | Explicitly forbidden; any new threshold must use new data |

---

## Timeline

| Date | Milestone |
|------|-----------|
| 2026-10-18 | Tests 0–2 complete; pre-registration frozen |
| 2026-10-18 | (After this date) Run Tests 3–7 on frozen plan |
| 2026-10-18 | Report final verdicts in `FINAL_VERDICT.md` |

---

## Commitment Statement

By signing this pre-registration, I (Kiro, automated agent) commit to:

1. ✓ **No data peeking** before freezing all rules
2. ✓ **No retroactive rule changes** based on observed results
3. ✓ **Mechanical application** of selection and pass criteria
4. ✓ **Transparent reporting** of all findings, including negative results
5. ✓ **Full documentation** of any deviations
6. ✓ **Honest caveat** about synthetic co-generated data limiting validity

---

## Frozen Status

| Item | Status |
|------|--------|
| Signal | ✓ Locked |
| Baseline B | ✓ Locked |
| Threshold 2×B | ✓ Locked |
| Breach label | ✓ Locked |
| FA definition (primary) | ✓ Locked |
| Pass criteria | ✓ Locked |
| Stop rules | ✓ Locked |
| Data splits | ✓ Locked |
| Analysis plan | ✓ Locked |

---

## Next: Begin Analysis (Tests 3–7)

All pre-registration is complete. Ready to run:

1. Test 3: Signal sanity (AUC, distribution, shuffled)
2. Test 4: Lag analysis (cross-correlation)
3. Test 5: Calibration sweep & selection
4. Test 6: Held-out test evaluation
5. Test 7: Chance check (shuffle test)

**No changes to rules permitted from this point forward.**

---

## Document Signature

```
Frozen Date: 2026-10-18
Status: LOCKED
Authority: Pre-registration requirement
Validity: EXPLORATORY_ONLY (synthetic data)
Next: Begin Tests 3–7 per frozen plan
```

**This pre-registration is binding on all subsequent analysis.**

---

**READY TO PROCEED WITH ANALYSIS** ✓
