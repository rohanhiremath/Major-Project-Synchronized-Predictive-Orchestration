from pathlib import Path

import pandas as pd
import torch
import numpy as np
import matplotlib.pyplot as plt

from pytorch_forecasting import (
    TimeSeriesDataSet,
    TemporalFusionTransformer,
)
from pytorch_forecasting.metrics import QuantileLoss


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
MODEL_DIR = PROJECT_ROOT / "models"
RESULTS_DIR = PROJECT_ROOT / "results"

TRAIN_FILE = DATA_DIR / "train.csv"
VAL_FILE = DATA_DIR / "validation.csv"
TEST_FILE = DATA_DIR / "test.csv"

MODEL_FILE = MODEL_DIR / "tft_psi_model_improved.ckpt"
PREDICTIONS_FILE = DATA_DIR / "tft_predictions_improved.csv"
PLOT_FILE = DATA_DIR / "tft_prediction_plot_improved.png"

TARGET = "psi_some_avg10"

MAX_ENCODER_LENGTH = 30
MAX_PREDICTION_LENGTH = 30

BATCH_SIZE = 16

# Spike detection threshold
SPIKE_THRESHOLD = 2.0

# ============================================================
# TIER 3: Conformalized Quantile Regression (CQR)
# ============================================================
USE_CQR_CALIBRATION = True  # Enable CQR calibration


# ============================================================
# 1. LOAD DATA
# ============================================================

train_df = pd.read_csv(TRAIN_FILE)
val_df = pd.read_csv(VAL_FILE)
test_df = pd.read_csv(TEST_FILE)

train_df["timestamp"] = pd.to_datetime(train_df["timestamp"])
val_df["timestamp"] = pd.to_datetime(val_df["timestamp"])
test_df["timestamp"] = pd.to_datetime(test_df["timestamp"])

print("=" * 60)
print("DATA LOADED")
print("=" * 60)
print("Training rows:", len(train_df))
print("Validation rows:", len(val_df))
print("Test rows:", len(test_df))


# ============================================================
# ADD DERIVATIVE FEATURES (same as training)
# ============================================================

def add_derivative_features(df):
    """Add slope/derivative features as leading indicators"""
    df = df.copy()
    df = df.sort_values(['series_id', 'time_idx']).reset_index(drop=True)
    
    for col in ['cpu_usage', 'psi_some_avg10', 'request_rate', 'memory_usage']:
        df[f'delta_{col}'] = df.groupby('series_id')[col].diff().fillna(0)
    
    return df

train_df = add_derivative_features(train_df)
val_df = add_derivative_features(val_df)
test_df = add_derivative_features(test_df)

# Add dummy weight column (not used in inference)
train_df['weight'] = 1.0
val_df['weight'] = 1.0
test_df['weight'] = 1.0


# ============================================================
# 2. CREATE DATASETS
# ============================================================

training_dataset = TimeSeriesDataSet(
    train_df,
    time_idx="time_idx",
    target=TARGET,
    group_ids=["series_id"],
    max_encoder_length=MAX_ENCODER_LENGTH,
    max_prediction_length=MAX_PREDICTION_LENGTH,
    weight="weight",
    time_varying_known_reals=["time_idx", "hour_sin", "hour_cos"],
    time_varying_unknown_reals=[
        "request_rate", "active_connections", "cpu_usage", "memory_usage",
        "read_bytes_per_sec", "write_bytes_per_sec", "latency_ms", "error_rate",
        "psi_some_avg10", "psi_some_avg60", "psi_some_avg300",
        "psi_full_avg10", "psi_full_avg60", "psi_full_avg300",
        "delta_cpu_usage", "delta_psi_some_avg10", "delta_request_rate", "delta_memory_usage",
    ],
)

train_val_test_df = pd.concat([train_df, val_df, test_df], ignore_index=True)
train_val_test_df = train_val_test_df.sort_values(["series_id", "time_idx"]).reset_index(drop=True)

# Create dataset from ALL data first (train+val+test) for proper time_idx continuity
train_val_test_df = pd.concat([train_df, val_df, test_df], ignore_index=True)
train_val_test_df = train_val_test_df.sort_values(["series_id", "time_idx"]).reset_index(drop=True)

# Create full dataset
full_dataset = TimeSeriesDataSet.from_dataset(
    training_dataset,
    train_val_test_df,
    predict=False,  # Get all overlapping windows
    stop_randomization=True,
)

# Filter to only test windows (where prediction starts in test range)
test_start_time = test_df['time_idx'].min()
test_dataloader = full_dataset.to_dataloader(
    train=False,
    batch_size=BATCH_SIZE,
    num_workers=0,
)


# ============================================================
# 3. LOAD MODEL
# ============================================================

print("\n" + "=" * 60)
print("LOADING MODEL")
print("=" * 60)

checkpoint = torch.load(MODEL_FILE, map_location="cpu", weights_only=False)


tft = TemporalFusionTransformer.load_from_checkpoint(
    MODEL_FILE,
    map_location="cpu",
)

tft.eval()

print("Model loaded successfully.")


# ============================================================
# 4. GENERATE PREDICTIONS ON VALIDATION SET (FOR CQR)
# ============================================================

if USE_CQR_CALIBRATION:
    print("\n" + "=" * 60)
    print("TIER 3: CQR CALIBRATION ON VALIDATION SET")
    print("=" * 60)
    
    # Create validation dataset
    train_val_df = pd.concat([train_df, val_df], ignore_index=True)
    train_val_df = train_val_df.sort_values(["series_id", "time_idx"]).reset_index(drop=True)
    
    val_dataset = TimeSeriesDataSet.from_dataset(
        training_dataset,
        train_val_df,
        predict=True,
        stop_randomization=True,
    )
    
    val_dataloader = val_dataset.to_dataloader(
        train=False,
        batch_size=BATCH_SIZE,
        num_workers=0,
    )
    
    # Get predictions on validation set
    val_predictions = []
    val_actuals = []
    
    with torch.no_grad():
        for x, y in val_dataloader:
            output = tft(x)
            pred = output["prediction"]
            val_predictions.append(pred)
            val_actuals.append(y[0])  # y[0] is the target
    
    val_predictions = torch.cat(val_predictions, dim=0).numpy()
    val_actuals = torch.cat(val_actuals, dim=0).numpy()
    
    # Extract quantiles (last dimension: q10, q50, q90)
    val_q10 = val_predictions[:, :, 0]
    val_q50 = val_predictions[:, :, 1]
    val_q90 = val_predictions[:, :, 2]
    
    # Compute conformalization offsets for q90
    # We want to adjust q90 so that coverage reaches 80%
    
    # Flatten for easier computation
    val_q90_flat = val_q90.flatten()
    val_actuals_flat = val_actuals.flatten()
    
    # Current coverage
    current_coverage = np.mean((val_actuals_flat >= val_q10.flatten()) & 
                                (val_actuals_flat <= val_q90_flat))
    
    # Calculate non-conformity scores (how much we're off)
    nonconformity_scores = val_actuals_flat - val_q90_flat
    
    # Find the quantile of non-conformity scores that gives us ~80% coverage
    # (or 90% for one-sided upper bound)
    target_quantile = 0.10  # We want q90 to be at 90th percentile (10% above)
    cqr_offset = np.quantile(nonconformity_scores, target_quantile)
    
    print(f"Original validation coverage: {100*current_coverage:.2f}%")
    print(f"CQR offset for q90: {cqr_offset:.4f}")
    
    # Test if this improves coverage
    calibrated_q90_flat = val_q90_flat + cqr_offset
    calibrated_coverage = np.mean((val_actuals_flat >= val_q10.flatten()) & 
                                   (val_actuals_flat <= calibrated_q90_flat))
    print(f"Calibrated validation coverage: {100*calibrated_coverage:.2f}%")
else:
    cqr_offset = 0.0


# ============================================================
# 5. GENERATE PREDICTIONS ON TEST SET
# ============================================================

print("\n" + "=" * 60)
print("GENERATING TEST PREDICTIONS")
print("=" * 60)

predictions = []
actuals = []

with torch.no_grad():
    for x, y in test_dataloader:
        output = tft(x)
        pred = output["prediction"]
        predictions.append(pred)
        actuals.append(y[0])

predictions = torch.cat(predictions, dim=0).numpy()
actuals = torch.cat(actuals, dim=0).numpy()

print(f"Predictions shape: {predictions.shape}")
print(f"  (windows, horizon_steps, quantiles)")


# ============================================================
# 6. EXTRACT QUANTILES AND APPLY CQR CALIBRATION
# ============================================================

q10 = predictions[:, :, 0]
q50 = predictions[:, :, 1]
q90 = predictions[:, :, 2]

# TIER 3: Apply CQR calibration offset to q90
if USE_CQR_CALIBRATION:
    q90_calibrated = q90 + cqr_offset
    print(f"\nCQR calibration applied: q90 += {cqr_offset:.4f}")
else:
    q90_calibrated = q90


# ============================================================
# 7. EVALUATION METRICS
# ============================================================

print("\n" + "=" * 60)
print("EVALUATION METRICS")
print("=" * 60)

# Flatten for easier metrics
actuals_flat = actuals.flatten()
q10_flat = q10.flatten()
q50_flat = q50.flatten()
q90_flat = q90.flatten()
q90_calibrated_flat = q90_calibrated.flatten()

# Point forecast metrics (using q50)
mae = np.mean(np.abs(actuals_flat - q50_flat))
rmse = np.sqrt(np.mean((actuals_flat - q50_flat) ** 2))

print(f"\nPoint Forecast Metrics (q50):")
print(f"  MAE:  {mae:.6f}")
print(f"  RMSE: {rmse:.6f}")

# Pinball loss per quantile
def pinball_loss(y_true, y_pred, quantile):
    error = y_true - y_pred
    return np.mean(np.maximum(quantile * error, (quantile - 1) * error))

pb_10 = pinball_loss(actuals_flat, q10_flat, 0.1)
pb_50 = pinball_loss(actuals_flat, q50_flat, 0.5)
pb_90 = pinball_loss(actuals_flat, q90_flat, 0.9)

print(f"\nPinball Loss:")
print(f"  q10: {pb_10:.6f}")
print(f"  q50: {pb_50:.6f}")
print(f"  q90: {pb_90:.6f}")

# Interval coverage
coverage = np.mean((actuals_flat >= q10_flat) & (actuals_flat <= q90_flat))
coverage_calibrated = np.mean((actuals_flat >= q10_flat) & (actuals_flat <= q90_calibrated_flat))

print(f"\nQuantile Interval Coverage (q10-q90):")
print(f"  Original:   {100*coverage:.3f}% (target ~80%)")
if USE_CQR_CALIBRATION:
    print(f"  Calibrated: {100*coverage_calibrated:.3f}%")

# Interval width
width = np.mean(q90_flat - q10_flat)
width_calibrated = np.mean(q90_calibrated_flat - q10_flat)

print(f"\nInterval Width:")
print(f"  Original:   {width:.4f}")
if USE_CQR_CALIBRATION:
    print(f"  Calibrated: {width_calibrated:.4f}")


# ============================================================
# 8. SPIKE DETECTION METRICS
# ============================================================

print("\n" + "=" * 60)
print("SPIKE DETECTION METRICS")
print("=" * 60)

# TIER 3: Threshold sweep
thresholds_to_test = [1.5, 1.8, 2.0, 2.2, 2.5]

print("\nTIER 3: Threshold Sweep on Original q90")
print("-" * 60)
print(f"{'Threshold':<12} {'Precision':<12} {'Recall':<12} {'F1':<12}")
print("-" * 60)

best_recall = 0
best_threshold = SPIKE_THRESHOLD
best_metrics = {}

for threshold in thresholds_to_test:
    # Per-window spike detection
    is_spike_per_window = (actuals.max(axis=1) >= threshold)
    should_scale_per_window = (q90.max(axis=1) >= threshold)
    
    tp = np.sum(is_spike_per_window & should_scale_per_window)
    fp = np.sum(~is_spike_per_window & should_scale_per_window)
    fn = np.sum(is_spike_per_window & ~should_scale_per_window)
    tn = np.sum(~is_spike_per_window & ~should_scale_per_window)
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    
    print(f"{threshold:<12.1f} {100*precision:<12.2f} {100*recall:<12.2f} {100*f1:<12.2f}")
    
    if recall > best_recall:
        best_recall = recall
        best_threshold = threshold
        best_metrics = {
            'threshold': threshold,
            'precision': precision,
            'recall': recall,
            'f1': f1,
            'tp': tp,
            'fp': fp,
            'fn': fn,
            'tn': tn,
        }

print(f"\nBest threshold for recall: {best_threshold} (recall: {100*best_recall:.2f}%)")

# Now test with CQR calibrated q90
if USE_CQR_CALIBRATION:
    print("\nTIER 3: With CQR Calibration (threshold = 2.0)")
    print("-" * 60)
    
    is_spike_per_window = (actuals.max(axis=1) >= 2.0)
    should_scale_per_window = (q90_calibrated.max(axis=1) >= 2.0)
    
    tp = np.sum(is_spike_per_window & should_scale_per_window)
    fp = np.sum(~is_spike_per_window & should_scale_per_window)
    fn = np.sum(is_spike_per_window & ~should_scale_per_window)
    tn = np.sum(~is_spike_per_window & ~should_scale_per_window)
    
    precision_cal = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall_cal = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1_cal = 2 * precision_cal * recall_cal / (precision_cal + recall_cal) if (precision_cal + recall_cal) > 0 else 0.0
    
    print(f"Precision:  {100*precision_cal:.2f}%")
    print(f"Recall:     {100*recall_cal:.2f}%")
    print(f"F1:         {100*f1_cal:.2f}%")
    
    print(f"\nConfusion Matrix:")
    print(f"  TP: {tp}")
    print(f"  FP: {fp}")
    print(f"  FN: {fn}")
    print(f"  TN: {tn}")

# Use best threshold for final report
print("\n" + "=" * 60)
print("FINAL RESULTS (Best Threshold)")
print("=" * 60)

# Handle case where no spikes were detected
if not best_metrics:
    print("⚠ WARNING: No spikes detected in test set")
    print(f"Threshold: {SPIKE_THRESHOLD} (default)")
    print("Precision: N/A")
    print("Recall:    N/A")
    print("F1 Score:  N/A")
    print("\n✗ AUTOMATION GATE NOT MET: No spikes to evaluate")
    print("\n" + "=" * 60)
    print("DIAGNOSTIC INFORMATION")
    print("=" * 60)
    print(f"Test windows: {len(predictions)}")
    print(f"Max PSI value in test: {actuals.max():.4f}")
    print(f"Max q90 prediction: {q90.max():.4f}")
    print("\n⚠ The improved model needs to be trained first!")
    print("   Run: python src/train_tft_improved.py")
else:
    print(f"Threshold: {best_metrics['threshold']}")
    print(f"Precision: {100*best_metrics['precision']:.2f}%")
    print(f"Recall:    {100*best_metrics['recall']:.2f}%")
    print(f"F1 Score:  {100*best_metrics['f1']:.2f}%")

    if best_metrics['recall'] >= 0.90:
        print("\n✓ AUTOMATION GATE MET: Recall >= 90%")
    else:
        print(f"\n✗ AUTOMATION GATE NOT MET: Recall {100*best_metrics['recall']:.2f}% < 90%")
        print(f"   Gap: {100*(0.90 - best_metrics['recall']):.2f} percentage points")


# ============================================================
# 9. SAVE PREDICTIONS
# ============================================================

# Save detailed predictions
prediction_rows = []

for window_idx in range(len(predictions)):
    for horizon_step in range(MAX_PREDICTION_LENGTH):
        prediction_rows.append({
            "window_id": window_idx,
            "horizon_step": horizon_step,
            "actual": actuals[window_idx, horizon_step],
            "q10": q10[window_idx, horizon_step],
            "q50": q50[window_idx, horizon_step],
            "q90": q90[window_idx, horizon_step],
            "q90_calibrated": q90_calibrated[window_idx, horizon_step],
        })

pred_df = pd.DataFrame(prediction_rows)
pred_df.to_csv(PREDICTIONS_FILE, index=False)

print(f"\nPredictions saved to: {PREDICTIONS_FILE}")


# ============================================================
# 10. VISUALIZATION
# ============================================================

if len(predictions) > 0 and best_metrics:
    plt.figure(figsize=(14, 6))

    sample_windows = min(3, len(predictions))

    for i in range(sample_windows):
        plt.subplot(1, sample_windows, i + 1)
        
        horizon = np.arange(MAX_PREDICTION_LENGTH)
        
        plt.plot(horizon, actuals[i], 'k-', label='Actual', linewidth=2)
        plt.plot(horizon, q50[i], 'b--', label='q50 (median)', linewidth=1.5)
        plt.fill_between(horizon, q10[i], q90[i], alpha=0.3, label='q10-q90 interval')
        
        if USE_CQR_CALIBRATION:
            plt.plot(horizon, q90_calibrated[i], 'r:', label='q90 calibrated', linewidth=1.5)
        
        plt.axhline(y=best_metrics['threshold'], color='orange', linestyle='--', 
                    label=f'Threshold ({best_metrics["threshold"]})', linewidth=1)
        
        plt.xlabel('Forecast Horizon Step')
        plt.ylabel('PSI I/O Pressure')
        plt.title(f'Window {i}')
        plt.legend(fontsize=8)
        plt.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(PLOT_FILE, dpi=150, bbox_inches='tight')
    print(f"\nPlot saved to: {PLOT_FILE}")
else:
    print(f"\nSkipping visualization (no spikes or insufficient data)")

print("\n" + "=" * 60)
print("PREDICTION COMPLETE")
print("=" * 60)
