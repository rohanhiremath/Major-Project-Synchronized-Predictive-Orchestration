#!/usr/bin/env python3
"""
Predict on synthetic PSI data using the trained TFT model.
Uses the model saved at: models/tft_psi_model_synthetic.ckpt
"""

from pathlib import Path

import pandas as pd
import numpy as np
import torch
import matplotlib.pyplot as plt

from pytorch_forecasting import TimeSeriesDataSet
from pytorch_forecasting import TemporalFusionTransformer


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "synthetic"
MODEL_DIR = PROJECT_ROOT / "models"

TRAIN_FILE = DATA_DIR / "train.csv"
VAL_FILE = DATA_DIR / "val.csv"
TEST_FILE = DATA_DIR / "test.csv"

MODEL_FILE = MODEL_DIR / "tft_psi_model_synthetic.ckpt"

TARGET = "psi_io_some_avg10"

MAX_ENCODER_LENGTH = 96
MAX_PREDICTION_LENGTH = 24

QUANTILES = (0.1, 0.5, 0.9)
SPIKE_THRESHOLD = 2.0  # Synthetic data spike threshold

BATCH_SIZE = 32


# ============================================================
# 1. LOAD DATA
# ============================================================

print("=" * 60)
print("LOADING SYNTHETIC DATA")
print("=" * 60)

train_df = pd.read_csv(TRAIN_FILE)
val_df = pd.read_csv(VAL_FILE)
test_df = pd.read_csv(TEST_FILE)

train_df["timestamp"] = pd.to_datetime(train_df["timestamp"])
val_df["timestamp"] = pd.to_datetime(val_df["timestamp"])
test_df["timestamp"] = pd.to_datetime(test_df["timestamp"])


print("Training rows:", len(train_df))
print("Validation rows:", len(val_df))
print("Test rows:", len(test_df))


# ============================================================
# 2. CREATE TRAINING DATASET
# ============================================================

print("\n" + "=" * 60)
print("CREATE TRAINING DATASET")
print("=" * 60)

training_dataset = TimeSeriesDataSet(

    train_df,

    time_idx="time_idx",

    target=TARGET,

    group_ids=["node_id"],

    max_encoder_length=MAX_ENCODER_LENGTH,

    max_prediction_length=MAX_PREDICTION_LENGTH,

    static_categoricals=["node_id", "workload_type"],

    time_varying_known_reals=[
        "hour_of_day",
        "day_of_week",
        "minute_sin",
        "minute_cos",
        "is_business_hours",
        "is_maintenance_window",
    ],

    time_varying_unknown_reals=[
        "disk_iops",
        "disk_queue_depth",
        "io_wait_pct",
        "cpu_util_pct",
        "p95_latency_ms",
        "psi_io_some_avg10",
        "psi_io_some_avg60",
        "psi_io_some_avg300",
        "psi_io_full_avg10",
        "psi_io_full_avg60",
        "psi_io_full_avg300",
        "psi_io_some_total_us",
    ],

    add_target_scales=True,
    allow_missing_timesteps=False,
)

print("Training dataset created")
print(f"  Samples: {len(training_dataset)}")


# ============================================================
# 3. CREATE TEST DATASET
# ============================================================

print("\n" + "=" * 60)
print("CREATE TEST DATASET")
print("=" * 60)

# Combine all data for test predictions (need historical context)
all_test_data = pd.concat(
    [
        train_df,
        val_df,
        test_df
    ],
    ignore_index=True
)

all_test_data = all_test_data.sort_values(
    ["node_id", "time_idx"]
).reset_index(drop=True)


test_dataset = TimeSeriesDataSet.from_dataset(
    training_dataset,
    all_test_data,
    predict=False,
    stop_randomization=True,
    allow_missing_timesteps=True,  # Allow gaps between splits
)

print("Test dataset created")
print(f"  Samples: {len(test_dataset)}")


# ============================================================
# 4. CREATE TEST DATALOADER
# ============================================================

test_dataloader = test_dataset.to_dataloader(
    train=False,
    batch_size=BATCH_SIZE,
    num_workers=0,
)


# ============================================================
# 5. LOAD TRAINED MODEL
# ============================================================

print("\n" + "=" * 60)
print("LOAD TRAINED MODEL")
print("=" * 60)

model = TemporalFusionTransformer.load_from_checkpoint(
    str(MODEL_FILE)
)

model.eval()

print(f"Model loaded from: {MODEL_FILE}")


# ============================================================
# 6. MAKE PREDICTIONS
# ============================================================

print("\n" + "=" * 60)
print("MAKING PREDICTIONS")
print("=" * 60)

quantile_batches = []
actual_batches = []

# Test data starts after training + validation
TEST_START_IDX = int(len(train_df) + len(val_df))

with torch.no_grad():
    for batch_idx, (x, y) in enumerate(test_dataloader):
        # Check if this batch contains test period data
        test_window = x["decoder_time_idx"][:, 0] >= TEST_START_IDX
        if not test_window.any():
            continue
        
        output = model(x)
        quantile_batches.append(model.to_quantiles(output)[test_window].cpu())
        
        # y is a tuple (target, weight)
        if isinstance(y, tuple):
            actual_batches.append(y[0][test_window].cpu())
        else:
            actual_batches.append(y[test_window].cpu())

if quantile_batches:
    quantile_predictions = torch.cat(quantile_batches, dim=0).numpy()
    actual_values = torch.cat(actual_batches, dim=0).numpy()
    predictions = quantile_predictions[:, :, 1]  # Median (q50)
else:
    print("Warning: No test window data found")
    exit(1)

print(f"Predictions made: {predictions.shape}")
print(f"Actual values shape: {actual_values.shape}")


# ============================================================
# 7. CALCULATE METRICS
# ============================================================

print("\n" + "=" * 60)
print("METRICS")
print("=" * 60)

# Flatten for overall metrics
pred_flat = predictions.reshape(-1)
actual_flat = actual_values.reshape(-1)

mae = np.mean(np.abs(actual_flat - pred_flat))
rmse = np.sqrt(np.mean((actual_flat - pred_flat) ** 2))

print(f"MAE:  {mae:.6f}")
print(f"RMSE: {rmse:.6f}")


# ============================================================
# 8. SPIKE DETECTION METRICS
# ============================================================

def pinball_loss(actual, predicted, quantile):
    error = actual - predicted
    return float(np.mean(np.maximum(quantile * error, (quantile - 1) * error)))


q10 = quantile_predictions[:, :, 0]
q50 = quantile_predictions[:, :, 1]
q90 = quantile_predictions[:, :, 2]

# Spike detection: any timestep in prediction window crosses threshold
spike_actual = np.max(actual_values, axis=1) >= SPIKE_THRESHOLD
scale_up_signal = np.max(q90, axis=1) >= SPIKE_THRESHOLD

true_positive = np.sum(spike_actual & scale_up_signal)
false_positive = np.sum(~spike_actual & scale_up_signal)
false_negative = np.sum(spike_actual & ~scale_up_signal)

precision = true_positive / max(true_positive + false_positive, 1)
recall = true_positive / max(true_positive + false_negative, 1)

coverage = np.mean((actual_values >= q10) & (actual_values <= q90))

print("\nQuantile Analysis:")
print(f"  q10-q90 coverage: {coverage:.3%}")
print(f"  Average q10-q90 interval width: {np.mean(q90 - q10):.6f}")

print(f"\nSpike Detection (threshold={SPIKE_THRESHOLD}):")
print(f"  True Positives: {true_positive}")
print(f"  False Positives: {false_positive}")
print(f"  False Negatives: {false_negative}")
print(f"  Precision: {precision:.3%}")
print(f"  Recall: {recall:.3%}")

print("\nQuantile Pinball Loss:")
for quantile, values in zip(QUANTILES, (q10, q50, q90)):
    loss = pinball_loss(actual_values, values, quantile)
    print(f"  q{int(quantile * 100)}: {loss:.6f}")


# ============================================================
# 9. SAVE PREDICTIONS
# ============================================================

print("\n" + "=" * 60)
print("SAVE PREDICTIONS")
print("=" * 60)

results = pd.DataFrame({
    "window_id": np.repeat(np.arange(len(actual_values)), MAX_PREDICTION_LENGTH),
    "horizon_step": np.tile(np.arange(1, MAX_PREDICTION_LENGTH + 1), len(actual_values)),
    "actual_psi": actual_flat,
    "q10": q10.reshape(-1),
    "q50": q50.reshape(-1),
    "q90": q90.reshape(-1),
})

output_file = DATA_DIR / "tft_predictions_synthetic.csv"
results.to_csv(output_file, index=False)
print(f"Predictions saved to: {output_file}")


# ============================================================
# 10. CREATE PLOT
# ============================================================

print("\n" + "=" * 60)
print("CREATE PLOT")
print("=" * 60)

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))

# Plot 1: Time series
ax1.plot(actual_flat, label="Actual PSI", linewidth=1.0, alpha=0.8)
ax1.plot(pred_flat, label="Predicted PSI (q50)", linewidth=0.8, alpha=0.7)
ax1.fill_between(
    range(len(actual_flat)),
    q10.reshape(-1),
    q90.reshape(-1),
    alpha=0.2,
    label="q10-q90 interval"
)
ax1.axhline(y=SPIKE_THRESHOLD, color="r", linestyle="--", linewidth=1, alpha=0.5, label=f"Spike threshold ({SPIKE_THRESHOLD})")
ax1.set_ylabel("psi_io_some_avg10")
ax1.set_title("TFT Predictions on Synthetic Test Data")
ax1.legend(loc="upper right")
ax1.grid(True, alpha=0.3)

# Plot 2: Error distribution
errors = actual_flat - pred_flat
ax2.hist(errors, bins=50, edgecolor="black", alpha=0.7)
ax2.axvline(x=0, color="r", linestyle="--", linewidth=1)
ax2.set_xlabel("Prediction Error (Actual - Predicted)")
ax2.set_ylabel("Frequency")
ax2.set_title(f"Error Distribution (MAE={mae:.4f}, RMSE={rmse:.4f})")
ax2.grid(True, alpha=0.3, axis="y")

plt.tight_layout()
plot_file = DATA_DIR / "tft_prediction_plot_synthetic.png"
plt.savefig(plot_file, dpi=150, bbox_inches="tight")
print(f"Plot saved to: {plot_file}")
plt.close()


# ============================================================
# 11. SUMMARY
# ============================================================

print("\n" + "=" * 60)
print("PREDICTION COMPLETE")
print("=" * 60)

print(f"\nModel: {MODEL_FILE}")
print(f"Test samples: {len(test_df):,}")
print(f"Prediction windows: {len(actual_values)}")
print(f"\nResults:")
print(f"  MAE: {mae:.6f}")
print(f"  RMSE: {rmse:.6f}")
print(f"  Spike Precision: {precision:.2%}")
print(f"  Spike Recall: {recall:.2%}")
print(f"  Q10-Q90 Coverage: {coverage:.2%}")
print(f"\nOutputs:")
print(f"  Predictions: {output_file}")
print(f"  Plot: {plot_file}")
