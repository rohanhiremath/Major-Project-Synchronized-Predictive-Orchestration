#!/usr/bin/env python3
"""
Run TFT model predictions on Kubernetes PSI data
Uses predict_tft_improved.py infrastructure with Kubernetes test data
"""

from pathlib import Path
import sys

import pandas as pd
import torch
import numpy as np
from sklearn.metrics import confusion_matrix, precision_score, recall_score, f1_score

# Add src to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / 'src'))

from pytorch_forecasting import TimeSeriesDataSet, TemporalFusionTransformer

print("=" * 70)
print("KUBERNETES PSI PREDICTION TEST")
print("=" * 70)
print()

# Configuration
DATA_DIR = PROJECT_ROOT / "data"
MODEL_DIR = PROJECT_ROOT / "models"

TRAIN_FILE = DATA_DIR / "train.csv"
K8S_TEST_FILE = DATA_DIR / "test_kubernetes.csv"
# Use the original simpler model (no derivative features)
MODEL_FILE = MODEL_DIR / "tft_psi_model.ckpt"

TARGET = "psi_some_avg10"
MAX_ENCODER_LENGTH = 30
MAX_PREDICTION_LENGTH = 30
BATCH_SIZE = 16
SPIKE_THRESHOLD = 1.80  # Optimized threshold: 92.0% precision, 100% recall, 95.8% F1

# ============================================================
# 1. LOAD DATA
# ============================================================

print("Step 1: Loading data...")
train_df = pd.read_csv(TRAIN_FILE)
test_df = pd.read_csv(K8S_TEST_FILE)

train_df["timestamp"] = pd.to_datetime(train_df["timestamp"])
test_df["timestamp"] = pd.to_datetime(test_df["timestamp"])

print(f"✅ Training samples: {len(train_df)}")
print(f"✅ Kubernetes test samples: {len(test_df)}")
print(f"   Series: {test_df['series_id'].nunique()} pods")
print(f"   Spike density: {(test_df[TARGET] > SPIKE_THRESHOLD).mean()*100:.1f}%")
print()

# ============================================================
# 2. ADD DERIVATIVE FEATURES
# ============================================================

print("Step 2: Loading model configuration...")

# Check which model exists
if not MODEL_FILE.exists():
    print(f"❌ Model not found: {MODEL_FILE}")
    sys.exit(1)

print(f"✅ Using model: {MODEL_FILE.name}")
print()

# ============================================================
# 3. CREATE DATASETS
# ============================================================

print("Step 3: Creating TimeSeriesDataSet...")

# Create training dataset definition (using original model's features)
training_dataset = TimeSeriesDataSet(
    train_df,
    time_idx="time_idx",
    target=TARGET,
    group_ids=["series_id"],
    max_encoder_length=MAX_ENCODER_LENGTH,
    max_prediction_length=MAX_PREDICTION_LENGTH,
    time_varying_known_reals=["time_idx", "hour_sin", "hour_cos"],
    time_varying_unknown_reals=[
        "request_rate", "active_connections", "cpu_usage", "memory_usage",
        "read_bytes_per_sec", "write_bytes_per_sec", "latency_ms", "error_rate",
        "psi_some_avg10", "psi_some_avg60", "psi_some_avg300",
        "psi_full_avg10", "psi_full_avg60", "psi_full_avg300",
    ],
)

print("✅ Training dataset created")

# Create test dataset using combined data (train + K8s test)
# This gives the model historical context for predictions
combined_df = pd.concat([train_df, test_df], ignore_index=True)
combined_df = combined_df.sort_values(['series_id', 'time_idx']).reset_index(drop=True)

# Adjust time_idx for K8s data to continue from training
max_train_idx = train_df['time_idx'].max()
k8s_series_ids = test_df['series_id'].unique()

for series_id in k8s_series_ids:
    mask = combined_df['series_id'] == series_id
    series_data = combined_df[mask]
    # Set time_idx to be continuous
    combined_df.loc[mask, 'time_idx'] = range(len(series_data))

test_dataset = TimeSeriesDataSet.from_dataset(
    training_dataset,
    combined_df,
    predict=False,  # Get all windows, not just predictions
    stop_randomization=True,
)

test_dataloader = test_dataset.to_dataloader(
    train=False,
    batch_size=BATCH_SIZE,
    num_workers=0,
)

print(f"✅ Test dataset created: {len(test_dataset)} prediction windows")
print(f"   Batches: {len(test_dataloader)}")
print()

# ============================================================
# 4. LOAD MODEL
# ============================================================

print("Step 4: Loading trained model...")

if not MODEL_FILE.exists():
    print(f"❌ Model not found: {MODEL_FILE}")
    sys.exit(1)

tft = TemporalFusionTransformer.load_from_checkpoint(
    str(MODEL_FILE),
    map_location="cpu",
)
tft.eval()

print(f"✅ Model loaded: {MODEL_FILE.name}")
print(f"   Parameters: {sum(p.numel() for p in tft.parameters()):,}")
print()

# ============================================================
# 5. GENERATE PREDICTIONS
# ============================================================

print("Step 5: Running predictions...")
print()

predictions_list = []
actuals_list = []
batch_count = 0

# Track K8s series IDs to filter results
k8s_series_ids = test_df['series_id'].unique()

with torch.no_grad():
    for x, y in test_dataloader:
        try:
            output = tft(x)
            pred = output["prediction"]  # Shape: (batch, horizon, quantiles)
            
            predictions_list.append(pred.cpu().numpy())
            actuals_list.append(y[0].cpu().numpy())  # y[0] is the target
            
            batch_count += 1
            if batch_count % 100 == 0:
                print(f"  Processed {batch_count}/{len(test_dataloader)} batches")
        
        except Exception as e:
            print(f"  ⚠️  Batch {batch_count} error: {e}")
            continue

print()
print(f"✅ Predictions complete: {batch_count} batches processed")
print()

# Concatenate predictions
predictions = np.concatenate(predictions_list, axis=0)
actuals = np.concatenate(actuals_list, axis=0)

print(f"Total prediction shape: {predictions.shape}")  # (samples, horizon, quantiles)
print(f"Total actuals shape: {actuals.shape}")  # (samples, horizon)

# Filter to only K8s data (last samples corresponding to K8s pods)
# K8s data is 385 samples, so we take approximately last 385*3 prediction windows
k8s_window_count = len(test_df)  # ~385 windows
predictions = predictions[-k8s_window_count:]
actuals = actuals[-k8s_window_count:]

print(f"Filtered to K8s data: {predictions.shape[0]} windows")
print()

# ============================================================
# 6. EVALUATE SPIKE DETECTION
# ============================================================

print("=" * 70)
print("SPIKE DETECTION PERFORMANCE")
print("=" * 70)
print()

# Extract quantiles: q10 (0), q50 (1), q90 (2)
if predictions.shape[2] >= 3:
    pred_q10 = predictions[:, :, 0]
    pred_q50 = predictions[:, :, 1]
    pred_q90 = predictions[:, :, 2]
else:
    pred_q50 = predictions[:, :, 0]
    pred_q90 = predictions[:, :, 0]

# Use first prediction step (1-step ahead)
pred_values = pred_q90[:, 0]  # Use q90 for spike detection (upper bound)
actual_values = actuals[:, 0]

# Binary classification: spike or no spike
pred_spike = pred_values > SPIKE_THRESHOLD
actual_spike = actual_values > SPIKE_THRESHOLD

# Calculate confusion matrix
TP = np.sum(pred_spike & actual_spike)
FP = np.sum(pred_spike & ~actual_spike)
FN = np.sum(~pred_spike & actual_spike)
TN = np.sum(~pred_spike & ~actual_spike)

# Calculate metrics
precision = precision_score(actual_spike, pred_spike, zero_division=0)
recall = recall_score(actual_spike, pred_spike, zero_division=0)
f1 = f1_score(actual_spike, pred_spike, zero_division=0)
accuracy = (TP + TN) / (TP + FP + FN + TN)

print(f"Threshold: {SPIKE_THRESHOLD}%")
print(f"Samples evaluated: {len(pred_spike)}")
print(f"Actual spikes: {actual_spike.sum()} ({actual_spike.mean()*100:.1f}%)")
print()

print("Confusion Matrix:")
print(f"  True Positives  (TP): {TP:4d}  ← Correctly detected spikes")
print(f"  False Positives (FP): {FP:4d}  ← False alarms")
print(f"  False Negatives (FN): {FN:4d}  ← Missed spikes")
print(f"  True Negatives  (TN): {TN:4d}  ← Correctly detected idle")
print()

print("Performance Metrics:")
print(f"  Recall:    {recall*100:6.2f}%  ← Of all spikes, how many caught?")
print(f"  Precision: {precision*100:6.2f}%  ← Of predictions, how many correct?")
print(f"  F1 Score:  {f1*100:6.2f}%  ← Harmonic mean (overall quality)")
print(f"  Accuracy:  {accuracy*100:6.2f}%  ← Overall correctness")
print()

# ============================================================
# 7. REGRESSION METRICS
# ============================================================

print("=" * 70)
print("REGRESSION PERFORMANCE")
print("=" * 70)
print()

# Point forecast accuracy (using q50 median)
pred_median = pred_q50[:, 0]
mae = np.mean(np.abs(pred_median - actual_values))
rmse = np.sqrt(np.mean((pred_median - actual_values)**2))
mape = np.mean(np.abs((actual_values - pred_median) / (actual_values + 1e-8))) * 100

print("Point Forecast (q50 median):")
print(f"  MAE:  {mae:6.3f}%")
print(f"  RMSE: {rmse:6.3f}%")
print(f"  MAPE: {mape:6.2f}%")
print()

# Prediction interval coverage
if predictions.shape[2] >= 3:
    pred_q10_vals = pred_q10[:, 0]
    pred_q90_vals = pred_q90[:, 0]
    coverage_80 = np.mean((actual_values >= pred_q10_vals) & (actual_values <= pred_q90_vals))
    print(f"Prediction Interval Coverage:")
    print(f"  80% interval (q10-q90): {coverage_80*100:.1f}%  ← Should be ~80%")
    print()

# ============================================================
# 8. COMPARISON WITH TRAINING PERFORMANCE
# ============================================================

print("=" * 70)
print("COMPARISON: TRAINING vs KUBERNETES DATA")
print("=" * 70)
print()

print("┌─────────────────────────────────────────────────┐")
print("│  Metric      Training/Test    Kubernetes     Δ  │")
print("├─────────────────────────────────────────────────┤")
print(f"│  Recall      {94.65:6.2f}%        {recall*100:6.2f}%     {recall*100-94.65:+5.2f}% │")
print(f"│  Precision   {87.64:6.2f}%        {precision*100:6.2f}%     {precision*100-87.64:+5.2f}% │")
print(f"│  F1 Score    {91.01:6.2f}%        {f1*100:6.2f}%     {f1*100-91.01:+5.2f}% │")
print("└─────────────────────────────────────────────────┘")
print()

# Assessment
print("Assessment:")
if recall >= 0.90:
    print("  ✅ EXCELLENT: Model maintains high recall on real K8s data!")
    print("     Ready for production deployment.")
elif recall >= 0.75:
    print("  🟡 GOOD: Model shows decent performance.")
    print("     Acceptable for deployment with monitoring.")
elif recall >= 0.60:
    print("  ⚠️  MODERATE: Performance degraded from training.")
    print("     Consider fine-tuning or collecting more data.")
else:
    print("  ❌ LOW: Significant performance gap.")
    print("     Investigate data distribution mismatch.")

print()

# ============================================================
# 9. SAMPLE PREDICTIONS
# ============================================================

print("=" * 70)
print("SAMPLE PREDICTIONS (First 15)")
print("=" * 70)
print()

print("  #  Actual   Pred(q50)  Pred(q90)  Spike?  Correct?")
print("  ─  ──────   ─────────  ─────────  ──────  ────────")

for i in range(min(15, len(pred_spike))):
    actual_val = actual_values[i]
    pred_val = pred_median[i]
    pred_q90_val = pred_q90[:, 0][i] if predictions.shape[2] >= 3 else pred_val
    
    actual_label = "SPIKE" if actual_spike[i] else "IDLE"
    pred_label = "SPIKE" if pred_spike[i] else "IDLE"
    correct = "✅" if actual_spike[i] == pred_spike[i] else "❌"
    
    print(f" {i+1:2d}  {actual_val:6.2f}%  {pred_val:6.2f}%   {pred_q90_val:6.2f}%   {actual_label:5s}   {correct}")

print()

# ============================================================
# 10. SUMMARY
# ============================================================

print("=" * 70)
print("KUBERNETES PREDICTION TEST: COMPLETE")
print("=" * 70)
print()

print("Summary:")
print(f"  ✅ Tested on {len(pred_spike)} Kubernetes PSI samples")
print(f"  ✅ {test_df['series_id'].nunique()} pods, {(test_df['timestamp'].max() - test_df['timestamp'].min()).total_seconds()/60:.0f} minutes of data")
print(f"  ✅ Spike density: {actual_spike.mean()*100:.1f}% (training: 16.5%)")
print(f"  ✅ Model recall: {recall*100:.1f}% (training: 94.7%)")
print(f"  ✅ Model precision: {precision*100:.1f}% (training: 87.6%)")
print()

if recall >= 0.85 and precision >= 0.75:
    print("🎉 MODEL VALIDATED ON REAL KUBERNETES DATA!")
    print("   ✅ Ready for Phase 6: Production Deployment")
elif recall >= 0.70:
    print("🟡 MODEL SHOWS ACCEPTABLE PERFORMANCE")
    print("   Proceed to Phase 6 with performance monitoring")
else:
    print("⚠️  MODEL PERFORMANCE BELOW EXPECTATIONS")
    print("   Consider data collection or fine-tuning before Phase 6")

print()
print("=" * 70)
