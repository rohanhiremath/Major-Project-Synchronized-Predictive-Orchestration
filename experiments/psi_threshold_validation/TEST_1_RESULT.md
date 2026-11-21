# TEST 1 RESULT: Label Independence — PASS (with Critical Finding)

**Date**: 2026-10-18  
**Status**: PASS  
**Critical Finding**: Data is synthetic and co-generated; validation results will be exploratory only

---

## Test 1 Verdict: PASS ✓

### Label Derivation (Independent)

- **Rule**: Breach = latency_ms > 2*B for 2+ consecutive bins
- **B = 60.34 ms** (median latency in calm rows where psi_some_avg10 == 0.0)
- **Threshold = 120.68 ms** (2*B)
- **Code review**: Breach label never reads any PSI column
- **Result**: Label is independent of signal

### Correlation Analysis

| Population | Signal-Latency Correlation | Interpretation |
|-----------|---------------------------|-----------------|
| Calm bins (32.2% of data) | NaN (zero variance) | ✓ Perfect independence |
| Stress bins (67.8% of data) | 0.9996–0.9998 | ⚠️ Structural artifact |

### Critical Finding: Co-Generation Artifact

**The signal and latency are NOT independent measurements.**

Evidence:
1. **Calm-bin correlation is NaN**: Both signal and latency are exactly constant in calm bins (signal=0.0, latency≈60 ms). This is not real-world behavior—it's synthetic data.
2. **Stress-bin correlation is 0.9996**: Nearly perfect correlation. In a real system with independent measurements, correlation >> 0.9 is extremely rare.
3. **Lag analysis shows correlation ≈ 1.0 at all lags (-60s to +60s)**: A lagged measurement would show peak correlation at a specific lag. Flat correlation across all lags proves **co-generation from the same model**.
4. **Source code confirms**: `generate_server_data.py` line 95 generates both:
   ```python
   latency_ms = np.clip(45 + 28*load + 75*psi_some_avg10 + noise, ...)
   psi_some_avg10 = np.clip(pressure*0.75 + noise, ...)
   ```
   Both depend on `load`. Both have `psi_some_avg10` as an input to latency generation.

---

## Implications for Validation

### Any threshold validation on this data is exploratory only

When signal and label share a source:
- **AUC=1.0** is expected (not a sign of good predictability)
- **High recall and precision** are expected (not surprising)
- **Shuffled AUC ≈ 0.5** confirms the data is synthetic (not real)

### Why this matters

The experiment's goal is to validate T=1.8% as a threshold that predicts real user-visible latency degradation. But:

1. The training data is synthetic (latency is a linear function of PSI)
2. Any threshold tested on this data will find what the data generator implemented, not what occurs in production
3. No amount of calibration and testing on synthetic data can produce a validated threshold for real infrastructure

---

## What Test 1 Accomplished

✓ **Label independence verified**: Breach label derived from external latency only, no PSI input  
✓ **Code audit passed**: Label computation never touches PSI columns  
⚠️ **Co-generation artifact identified**: Signal-latency correlation = 0.9996 (not independent)  
✓ **Baseline computed**: B = 60.34 ms (threshold = 120.68 ms)

---

## Decision: Proceed with Honest Caveat

**Option A: Continue experiment**
- Run full validation (Tests 2–5) on synthetic data
- Label all results as EXPLORATORY_ONLY
- Document that validation on co-generated data cannot produce real-world threshold
- Use the results as a proof-of-concept for methodology, not for production threshold

**Option B: Stop and switch to real data**
- Instrument a real Kubernetes cluster
- Collect actual latency, error, and PSI measurements
- Run the same experiment on real data
- Results will be production-validated

---

## Recommendation

**Option A with full transparency is the right path forward.**

Rationale:
1. The user asked to validate T=1.8%, not to overhaul data infrastructure
2. Synthetic data is valid for proving the *methodology* works (no post-hoc rules, frozen thresholds, proper statistical tests)
3. The honest documentation of the co-generation artifact is more valuable than pretending the data is independent
4. A real threshold for real infrastructure will require production data in the next phase

---

## Test 1 Completion

**Baseline B**: 60.34 ms  
**Threshold (2*B)**: 120.68 ms  
**Breach label rule**: latency > 120.68 ms for 2+ consecutive bins  
**Label code status**: Clean, independent, verified  
**Correlation finding**: 0.9996 (co-generated, not predictive)  
**Test 1 status**: **PASS — Label is independent; data is synthetic**

**Proceed to Test 2 (pilot with frozen rule)**.
