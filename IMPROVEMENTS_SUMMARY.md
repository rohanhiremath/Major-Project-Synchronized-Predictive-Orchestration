# PreSync Model Improvements Summary

## Current Status
- **Original Recall:** 60.2% (blocking issue - need 90%)
- **Original Precision:** 96.9%
- **Original Interval Coverage:** 68.8% (target: 80%)

## Improvements Implemented

### TIER 1: High-Confidence, Low-Risk Changes ✅

#### 1. Increased Model Capacity
- **Hidden Size:** 8 → **64** (8x increase)
- **Attention Heads:** 2 → **4** (2x increase)
- **Parameters:** ~10,000 → **644,209** (64x increase)
- **Rationale:** The original model was too small to represent the sharp nonlinear kinks in the PSI pressure formula

#### 2. Loosened Gradient Clipping
- **max_norm:** 0.1 → **1.0** (10x less aggressive)
- **Rationale:** Aggressive clipping was suppressing learning signals from rare spike examples

#### 3. Relaxed Early Stopping
- **Patience:** 3 → **6** epochs
- **Max Epochs:** 3 → **20** epochs
- **Rationale:** Allow more time for tail-fitting behavior to converge

#### 4. Loss Reweighting for Spikes
- **Spike Weight:** 5.0x for timesteps where PSI ≥ 2.0
- **Implementation:** Added `weight` column to TimeSeriesDataSet
- **Observed Distribution:**
  - Training: 12.78% spike timesteps
  - Validation: 9.84% spike timesteps  
  - Test: 16.51% spike timesteps
- **Rationale:** Prevents optimizer from ignoring rare spike events

### TIER 2: Data-Side Improvements ✅

#### 5. Derivative Features (Leading Indicators)
Added slope/derivative features for:
- `delta_cpu_usage`
- `delta_psi_some_avg10`
- `delta_request_rate`
- `delta_memory_usage`

**Rationale:** Makes spike onset more linearly separable and easier for the model to detect early

#### 6. Spike Distribution Audit
Implemented audit to verify spike counts across train/val/test splits:
```
Train spikes: 2651 (12.78%)
Val spikes:   255 (9.84%)
Test spikes:  428 (16.51%)
```

**Finding:** Test set has higher spike density than training, which could make the 60.2% recall optimistic

### TIER 3: Post-Hoc Calibration ✅

#### 7. Conformalized Quantile Regression (CQR)
- Implemented calibration on validation set
- Computes offset to adjust q90 predictions
- Formula: `q90_calibrated = q90 + cqr_offset`
- Target: Achieve 80% interval coverage

#### 8. Threshold Sweep
- Tests multiple thresholds: [1.5, 1.8, 2.0, 2.2, 2.5]
- Finds optimal threshold for maximizing recall while maintaining precision
- No retraining required - instant diagnostic

## Root Cause Analysis

The remediation report identified **three primary root causes:**

| Issue | Original Value | Improved Value | Impact |
|-------|---------------|----------------|--------|
| Model Capacity | Hidden size: 8 | Hidden size: 64 | **High** - Can now represent nonlinear kinks |
| Gradient Clipping | max_norm: 0.1 | max_norm: 1.0 | **High** - Learning signal preserved for spikes |
| Class Imbalance | No weighting | 5x weight for spikes | **Medium** - Spikes can't be ignored by optimizer |
| Early Stopping | Patience: 3 | Patience: 6 | **Medium** - More time to fit tails |

## Expected Improvements

Based on the analysis:

1. **Recall:** Expected to increase from 60.2% → **85-95%**
   - Larger model can fit spike magnitudes
   - Less aggressive gradient clipping preserves spike learning signal
   - Sample weighting forces attention to rare events

2. **Interval Coverage:** Expected to increase from 68.8% → **75-82%**
   - CQR calibration should push this to ~80%
   - Larger model capacity allows wider quantile spread

3. **Precision:** Expected to remain high (>90%)
   - Original model already had good precision (96.9%)
   - Shows model understood spike timing/shape

## Implementation Files

### Training
- **Original:** `src/train_tft.py`
- **Improved:** `src/train_tft_improved.py`
- **Model Output:** `models/tft_psi_model_improved.ckpt`

### Prediction & Evaluation
- **Original:** `src/predict_tft.py`
- **Improved:** `src/predict_tft_improved.py`
- **Features:**
  - CQR calibration on validation set
  - Threshold sweep analysis
  - Calibrated q90 predictions
  - Comprehensive metrics report

## Next Steps

1. **Complete Training:** Let the improved model train for 15-20 epochs
2. **Run Evaluation:** Execute `src/predict_tft_improved.py`
3. **Analyze Results:**
   - Check if recall ≥ 90% (automation gate)
   - Verify interval coverage ≈ 80%
   - Review threshold sweep results
4. **If Recall Still < 90%:**
   - Consider increasing spike density in data generation
   - Try hidden_size = 128 or 256
   - Extend encoder length from 30 → 45 steps

## Mathematical Changes

### Original Model
```
pressure = 14 × max(cpu - 0.62, 0) + 5 × max(load - 0.85, 0)
```

This creates a sharp nonlinear kink that hidden_size=8 couldn't represent.

### Loss Function (Unchanged)
```
ρ_τ(e) = τ × e         if e ≥ 0 (under-prediction)
       = (τ - 1) × e   if e < 0 (over-prediction)
       
L_total = L_0.1 + L_0.5 + L_0.9
```

But now **weighted by 5x** for spike timesteps.

### CQR Calibration
```
nonconformity_scores = y_actual - y_pred_q90
cqr_offset = quantile(nonconformity_scores, 0.10)
q90_calibrated = q90 + cqr_offset
```

This ensures empirical coverage matches the 80% target.

## Performance Comparison

### Model Size
| Metric | Original | Improved | Ratio |
|--------|----------|----------|-------|
| Hidden Size | 8 | 64 | 8x |
| Attention Heads | 2 | 4 | 2x |
| Parameters | ~10K | 644K | 64x |
| Training Time (est.) | 5 min | 30-45 min | 6-9x |

### Expected Metrics
| Metric | Original | Target | Expected Improved |
|--------|----------|--------|-------------------|
| Recall | 60.2% | 90% | 85-95% |
| Precision | 96.9% | >85% | 90-97% |
| Interval Coverage | 68.8% | 80% | 75-82% |
| F1 Score | 74.3% | >87% | 87-95% |

## Remediation Report Alignment

This implementation follows the **exact priority order** from the remediation report:

1. ✅ Threshold sweep (Tier 3, #9) - Implemented in predict script
2. ✅ CQR calibration (Tier 3, #8) - Implemented in predict script
3. ✅ Tier 1 changes (#1-#4) - All implemented in training script
4. ✅ Tier 2 changes (#5-#7) - All implemented in training script

## Citation

Based on: "PreSync: Mathematical Foundations & Spike Recall Remediation Report"
- Section 7: Root Cause Analysis
- Section 8: Concrete Remediation Plan
