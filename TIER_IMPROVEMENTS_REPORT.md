# PreSync Tier 1, 2, and 3 Improvements - Implementation Report

## Executive Summary

Based on the **PreSync Mathematical Foundations & Spike Recall Remediation Report**, all three tiers of improvements have been implemented to address the recall bottleneck (60.2% → target 90%).

### Root Cause

<cite index="2-59,2-60,2-61,2-62,2-63,2-64">The model is under-predicting spike magnitude due to: insufficient model capacity (hidden_size=8, 2 heads), aggressive gradient clipping (max_norm=0.1) that throttles learning signals from spike examples, class imbalance without reweighting where the vast majority of loss comes from non-spike timesteps, and tight early stopping (patience=3) that halts training before tail-fitting behavior converges.</cite>

## Dataset Statistics

```
Training:   20,736 rows  →  2,651 spike timesteps (12.78%)
Validation:  2,592 rows  →    255 spike timesteps ( 9.84%)
Test:        2,592 rows  →    428 spike timesteps (16.51%)
```

**Key Finding:** <cite index="2-22,2-23">Test set has higher spike density than training, which could make the reported 60.2% recall result skewed</cite>.

---

## TIER 1: High-Confidence, Low-Risk Changes ✅ IMPLEMENTED

### 1. Loosen Gradient Clipping

**Change:** `max_norm`: 0.1 → **1.0**

**Rationale:** <cite index="2-35,2-36,2-37,2-38">max_norm=0.1 is roughly an order of magnitude tighter than typical values (1.0–5.0) used for TFT/LSTM training. Spikes are rare, high-magnitude events that naturally produce the largest gradients. Clipping this aggressively systematically suppresses the learning signal coming from the rare spike examples.</cite>

**Impact:** **HIGH** - Directly un-suppresses learning from spike examples

---

### 2. Increase Model Capacity

**Changes:**
- `hidden_size`: 8 → **64** (8x increase)
- `attention_head_size`: 2 → **4** (2x increase)
- Parameters: ~10,000 → **644,209** (64x increase)

**Rationale:** <cite index="2-25,2-26,2-27,2-28">This is a very small TFT. The reference implementation and published TFT results use hidden sizes in the 64–320 range for problems with far less nonlinear structure than a thresholded pressure-saturation curve. Hidden size 8 gives the model very little representational capacity to fit a function with a sharp kink at cpu = 0.62 and load = 0.85.</cite>

**Impact:** **HIGH** - Enables model to represent sharp nonlinear pressure kinks

---

### 3. Loss Reweighting for Spike Windows

**Change:** Apply **5.0x sample weight** to timesteps where PSI ≥ 2.0

**Implementation:**
```python
df.loc[df[TARGET] >= threshold, 'weight'] = 5.0
```

**Rationale:** <cite index="2-74,2-75,2-76">Apply a sample weight (e.g., 3–5×) to timesteps where the target horizon contains is_spike == True, so the optimizer can't "afford" to ignore them by amortizing loss over the majority-class background. pytorch-forecasting's TimeSeriesDataSet supports a weight column for exactly this purpose.</cite>

**Impact:** **MEDIUM** - Addresses class imbalance at the loss level

---

### 4. Relax Early Stopping

**Changes:**
- `patience`: 3 → **6** epochs
- `max_epochs`: 3 → **20** epochs

**Rationale:** <cite index="2-40,2-41">Patience of 3 is tight. Combined with a loss that's dominated numerically by the ~90%+ of non-spike timesteps, val_loss can plateau (triggering early stopping) well before the model has meaningfully improved its rare-event tail behavior.</cite>

**Impact:** **MEDIUM** - Allows more time for tail-fitting convergence

---

## TIER 2: Data-Side Changes ✅ IMPLEMENTED

### 5. Add Leading-Indicator Covariates

**Added derivative features:**
- `delta_cpu_usage`
- `delta_psi_some_avg10`
- `delta_request_rate`
- `delta_memory_usage`

**Implementation:**
```python
df[f'delta_{col}'] = df.groupby('series_id')[col].diff().fillna(0)
```

**Rationale:** <cite index="2-84,2-85,2-86">Give the model explicit slope/derivative features as known/observed inputs. Right now the model has to infer "pressure is about to cross the nonlinear kink" purely from raw levels; a derivative feature makes the onset of a spike much more linearly separable and easier for a small-to-medium model to pick up early.</cite>

**Impact:** **MEDIUM** - Makes spike onset more detectable

---

### 6. Audit Spike Distribution

**Implemented:** Spike count verification across train/val/test splits

**Findings:**
```
Train:  12.78% spikes
Val:     9.84% spikes  
Test:   16.51% spikes  ← Higher than training!
```

**Rationale:** <cite index="2-82,2-83">Since splitting is chronological per-segment, explicitly count spikes-per-split (not just rows-per-split) to make sure recall isn't being measured on an unrepresentative test slice.</cite>

**Impact:** **LOW** - Diagnostic, reveals test set has harder spike distribution

---

## TIER 3: Post-Hoc Calibration ✅ IMPLEMENTED

### 7. Conformalized Quantile Regression (CQR)

**Implementation:**
```python
nonconformity_scores = y_actual - y_pred_q90
cqr_offset = np.quantile(nonconformity_scores, 0.10)
q90_calibrated = q90 + cqr_offset
```

**Rationale:** <cite index="2-87,2-88,2-89,2-90">After training, calibrate q90 on a held-out calibration split by adding a learned/estimated offset so that empirical coverage matches the 80% target. This is a standard technique specifically for the "coverage is systematically off" failure mode (68.8% vs 80%), and it requires no retraining — just a post-processing step. This alone could meaningfully close the recall gap.</cite>

**Impact:** **MEDIUM-HIGH** - Can fix magnitude calibration without retraining

---

### 8. Re-Tune Fixed Threshold Empirically

**Implementation:** Sweep thresholds [1.5, 1.8, 2.0, 2.2, 2.5] on validation data

**Rationale:** <cite index="2-91,2-92,2-93,2-94">PSI_threshold = 2.0 is currently fixed. Consider sweeping the threshold on validation data to find the value that maximizes recall at an acceptable precision floor (e.g., ≥85%), rather than assuming 2.0 is optimal for your trained model's q90 output distribution. This is the cheapest possible experiment — no retraining required.</cite>

**Impact:** **LOW-MEDIUM** - Quick diagnostic, may reveal better threshold

---

## Implementation Files

### Training Scripts
- **Original:** `src/train_tft.py`
- **Improved:** `src/train_tft_improved.py` ✅
  - All Tier 1 improvements
  - All Tier 2 improvements
  - Spike distribution audit

### Prediction & Evaluation
- **Original:** `src/predict_tft.py`
- **Improved:** `src/predict_tft_improved.py` ✅
  - CQR calibration (Tier 3)
  - Threshold sweep (Tier 3)
  - Comprehensive metrics

### Utilities
- **Comparison:** `src/compare_models.py` ✅
  - Side-by-side configuration comparison
  - Dataset statistics
  - Progress tracking

---

## Expected Results

### Current Metrics (Original Model)
| Metric | Value | Target |
|--------|-------|--------|
| Recall | 60.2% | ≥ 90% |
| Precision | 96.9% | ≥ 85% |
| Interval Coverage | 68.8% | ~80% |
| F1 Score | 74.3% | - |

### Expected Improvements

Based on the root cause analysis:

| Metric | Original | Expected | Reason |
|--------|----------|----------|--------|
| **Recall** | 60.2% | **85-95%** | Larger capacity + relaxed gradient clip + spike weighting |
| **Precision** | 96.9% | **90-97%** | Should maintain (model already understands timing/shape) |
| **Coverage** | 68.8% | **75-82%** | Larger model + CQR calibration |
| **F1 Score** | 74.3% | **87-95%** | Better precision/recall balance |

---

## Execution Plan

### Recommended Order (Per Remediation Report)

<cite index="2-95,2-96,2-97,2-98,2-99">1. Run the threshold sweep (Tier 3, #9) on your current trained model — free diagnostic, takes minutes.
2. Apply CQR calibration (Tier 3, #8) on the current model — also free, no retraining.
3. If recall is still short, retrain with Tier 1 changes (#1–#4) together, since they're cheap and reinforce each other.
4. If still short, move to Tier 2 (#5–#7), which requires touching the synthetic data generator and re-running the full pipeline.</cite>

### Current Status

✅ **All tiers implemented in code**
⏳ **Improved model training required** (~30-45 minutes on CPU)
⏳ **Evaluation pending**

### Commands

```bash
# 1. Train improved model
python src/train_tft_improved.py

# 2. Evaluate with Tier 3 calibrations
python src/predict_tft_improved.py

# 3. Compare results
python src/compare_models.py
```

---

## Mathematical Changes Summary

### Quantile Loss (Unchanged, but Weighted)

```python
ρ_τ(e) = τ × e         if e ≥ 0 (under-prediction)
       = (τ - 1) × e   if e < 0 (over-prediction)

L_τ = mean(ρ_τ(y - ŷ))
L_total = L_0.1 + L_0.5 + L_0.9
```

**Now with sample weights:**
```python
L_total_weighted = Σ weight[i] × L[i] / Σ weight[i]
```

Where `weight = 5.0` for spike timesteps, `1.0` otherwise.

---

### CQR Calibration Formula

```python
# Compute non-conformity scores on validation set
nonconformity = y_actual - y_pred_q90

# Find offset that gives us target coverage
cqr_offset = quantile(nonconformity, α)  # α = 0.10 for 90th percentile

# Apply to test predictions
q90_calibrated = q90_test + cqr_offset
```

This ensures that the calibrated q90 has the desired empirical coverage.

---

### Model Architecture Comparison

| Component | Original | Improved | Ratio |
|-----------|----------|----------|-------|
| Hidden Size | 8 | 64 | 8x |
| Attention Heads | 2 | 4 | 2x |
| Total Parameters | ~10K | 644K | 64x |
| Input Features | 17 | 21 | +4 derivatives |

---

## Root Cause → Remedy Mapping

<cite index="2-102,2-103,2-104">Precision (96.9%) tells you the model understands spike timing and shape. Recall (60.2%) and interval coverage (68.8%) together tell you it isn't forecasting spikes tall enough to cross the fixed threshold. That's a magnitude/calibration problem, most likely driven by the very small hidden size and the unusually tight gradient clip — both cheap to test — with post-hoc CQR calibration as the fastest possible experiment to confirm the diagnosis before any retraining.</cite>

| Root Cause | Symptom | Remedy | Tier |
|------------|---------|--------|------|
| Hidden size = 8 | Can't represent nonlinear kinks | Increase to 64 | 1 |
| Gradient clip = 0.1 | Suppresses spike learning | Relax to 1.0 | 1 |
| No sample weighting | Spikes ignored in loss | 5x weight for spikes | 1 |
| Patience = 3 | Stops before tail convergence | Increase to 6 | 1 |
| No derivatives | Spike onset hard to detect | Add Δ features | 2 |
| Coverage = 68.8% | Quantiles too narrow | CQR calibration | 3 |
| Threshold = 2.0 fixed | May be sub-optimal | Sweep thresholds | 3 |

---

## Success Criteria

### Automation Gate (From Original Report)

<cite index="1-5">The model runs and produces quantile forecasts, but it is not yet accurate enough to drive automated scaling — it only catches about 60% of pressure spikes against a 90% target.</cite>

**Target:** Spike recall ≥ **90%** on test set

### Additional Metrics

- Precision ≥ 85% (avoid false scale-ups)
- q10-q90 coverage ≈ 80% (proper uncertainty quantification)
- F1 score ≥ 87% (balanced performance)

---

## Next Steps After Training

1. **Evaluate Improved Model**
   ```bash
   python src/predict_tft_improved.py
   ```
   - Check recall on test set
   - Review threshold sweep results
   - Assess CQR calibration impact

2. **If Recall ≥ 90%:** ✅ **Proceed to Phase 6**
   - Implement decision logic
   - Build shadow mode
   - Plan Kubernetes actuation

3. **If Recall < 90%:** Additional iterations
   - Try `hidden_size = 128` or `256`
   - Increase encoder length to 45 steps
   - Generate more spike-dense training data
   - Consider ensemble methods

---

## Files Created

```
src/train_tft_improved.py          ← Tier 1 & 2 training
src/predict_tft_improved.py        ← Tier 3 evaluation
src/compare_models.py               ← Utility comparison
IMPROVEMENTS_SUMMARY.md             ← Quick reference
TIER_IMPROVEMENTS_REPORT.md         ← This document
```

---

## Conclusion

All three tiers of improvements from the remediation report have been successfully implemented:

- **Tier 1** (High-confidence): Model capacity, gradient clipping, early stopping, sample weighting ✅
- **Tier 2** (Data-side): Derivative features, spike distribution audit ✅  
- **Tier 3** (Post-hoc): CQR calibration, threshold sweep ✅

The improved model is ready for training. Expected training time is 30-45 minutes on CPU. Based on the root cause analysis, these changes should increase recall from 60.2% to the 85-95% range, potentially meeting or exceeding the 90% automation gate.

---

## References

1. Original Progress Report: `presync-progress.pdf`
2. Remediation Report: `PreSync-Math-and-Recall-Report.pdf`
3. Original Training Script: `src/train_tft.py`
4. Original Prediction Script: `src/predict_tft.py`
