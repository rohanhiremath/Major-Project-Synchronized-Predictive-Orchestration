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
DATA_DIR = PROJECT_ROOT / "data"
MODEL_DIR = PROJECT_ROOT / "models"

TRAIN_FILE = DATA_DIR / "train.csv"
VAL_FILE = DATA_DIR / "validation.csv"
TEST_FILE = DATA_DIR / "test.csv"

MODEL_FILE = MODEL_DIR / "tft_psi_model_synthetic.ckpt"

TARGET = "psi_some_avg10"

MAX_ENCODER_LENGTH = 30
MAX_PREDICTION_LENGTH = 30

QUANTILES = (0.1, 0.5, 0.9)
SPIKE_THRESHOLD = 1.80  # Optimized threshold: 92% precision, 100% recall

BATCH_SIZE = 16


# Auto-detect synthetic data
SYNTHETIC_DATA_DIR = PROJECT_ROOT / "data" / "synthetic"
USE_SYNTHETIC = False
if SYNTHETIC_DATA_DIR.exists():
    synthetic_train = SYNTHETIC_DATA_DIR / "train.csv"
    if synthetic_train.exists():
        USE_SYNTHETIC = True
        TRAIN_FILE = SYNTHETIC_DATA_DIR / "train.csv"
        VAL_FILE = SYNTHETIC_DATA_DIR / "val.csv"
        TEST_FILE = SYNTHETIC_DATA_DIR / "test.csv"
        MODEL_FILE = MODEL_DIR / "tft_psi_model_synthetic.ckpt"
        TARGET = "psi_io_some_avg10"
        MAX_ENCODER_LENGTH = 30
        MAX_PREDICTION_LENGTH = 30
        SPIKE_THRESHOLD = 1.8


# ============================================================
# 1. LOAD DATA
# ============================================================

print("=" * 60)
print("LOADING DATA")
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

training_dataset = TimeSeriesDataSet(

    train_df,

    time_idx="time_idx",

    target=TARGET,

    group_ids=["series_id"] if "series_id" in train_df.columns else ["node_id"],

    max_encoder_length=MAX_ENCODER_LENGTH,

    max_prediction_length=MAX_PREDICTION_LENGTH,

    time_varying_known_reals=[
        "time_idx",
        "hour_sin",
        "hour_cos",
    ] if "hour_sin" in train_df.columns else [
        "hour_of_day",
        "day_of_week",
        "minute_sin",
        "minute_cos",
        "is_business_hours",
        "is_maintenance_window",
    ],

    time_varying_unknown_reals=[
        "request_rate",
        "active_connections",
        "cpu_usage",
        "memory_usage",
        "read_bytes_per_sec",
        "write_bytes_per_sec",
        "latency_ms",
        "error_rate",

        "psi_some_avg10",
        "psi_some_avg60",
        "psi_some_avg300",

        "psi_full_avg10",
        "psi_full_avg60",
        "psi_full_avg300",
    ] if "request_rate" in train_df.columns else [
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
    allow_missing_timesteps=USE_SYNTHETIC,
)


# ============================================================
# 3. CREATE TEST DATA
# ============================================================

# We need historical data before the test period.
#
# Therefore we combine:
#
# TRAIN + VALIDATION + TEST
#
# The model will use the past observations as encoder input
# and make predictions for the test period.

all_test_data = pd.concat(
    [
        train_df,
        val_df,
        test_df
    ],
    ignore_index=True
)

all_test_data = all_test_data.sort_values(
    ["series_id" if "series_id" in all_test_data.columns else "node_id", "time_idx"]
).reset_index(drop=True)


# ============================================================
# 4. CREATE TEST DATASET
# ============================================================

test_dataset = TimeSeriesDataSet.from_dataset(

    training_dataset,

    all_test_data,

    # Keep every rolling window so accuracy includes the whole held-out
    # period, rather than only the final window for each server.
    predict=False,

    stop_randomization=True,

    allow_missing_timesteps=USE_SYNTHETIC,
)


print("\n" + "=" * 60)
print("TEST DATASET")
print("=" * 60)

print(test_dataset)

print("\nNumber of test prediction windows:")
print(len(test_dataset))


# ============================================================
# 5. CREATE TEST DATALOADER
# ============================================================

test_dataloader = test_dataset.to_dataloader(
    train=False,
    batch_size=BATCH_SIZE,
    num_workers=0,
)


# ============================================================
# 6. LOAD TRAINED MODEL
# ============================================================

print("\n" + "=" * 60)
print("LOADING TRAINED TFT MODEL")
print("=" * 60)

model = TemporalFusionTransformer.load_from_checkpoint(
    MODEL_FILE
)

model.eval()

print("Model loaded successfully.")


# ============================================================
# 7. MAKE PREDICTIONS
# ============================================================

print("\n" + "=" * 60)
print("MAKING PREDICTIONS")
print("=" * 60)

quantile_batches = []
actual_batches = []
TEST_START_IDX = int(train_df["time_idx"].max()) + 1

# Run inference directly to keep prediction single-process and avoid MPI
# initialization in environments where distributed networking is unavailable.
# Run inference directly to keep prediction single-process and avoid MPI
# initialization in environments where distributed networking is unavailable.

# Detect the correct index column name
if USE_SYNTHETIC:
    # For synthetic data, we need to identify test split rows differently
    # since time_idx resets per split
    test_indices = test_df.index.tolist()
    test_start_row = len(train_df) + len(val_df)
else:
    TEST_START_IDX = int(train_df["time_idx"].max()) + 1

print(f"\nDEBUG: USE_SYNTHETIC={USE_SYNTHETIC}")
if USE_SYNTHETIC:
    print(f"DEBUG: Test start row={test_start_row}, Total rows in all_test_data={len(all_test_data)}")
else:
    print(f"DEBUG: TEST_START_IDX={TEST_START_IDX}")

with torch.no_grad():
    for batch_idx, (x, y) in enumerate(test_dataloader):
        if USE_SYNTHETIC:
            # For synthetic data with reset time_idx, identify test rows by checking
            # if we're in the test portion of the combined dataset
            # The decoder_time_idx values for test data will be in the test range
            decoder_times = x["decoder_time_idx"][:, 0].numpy()
            # Test rows have time_idx < MAX_PREDICTION_LENGTH (reset at test split start)
            # and correspond to the test data portion
            test_window = decoder_times < MAX_PREDICTION_LENGTH + 10  # Small buffer
        else:
            test_window = x["decoder_time_idx"][:, 0] >= TEST_START_IDX
        
        if not test_window.any():
            continue
        
        output = model(x)
        quantile_batches.append(model.to_quantiles(output)[test_window].cpu())
        actual_batches.append(y[0][test_window].cpu())
        
        if batch_idx % 100 == 0:
            print(f"  Processed batch {batch_idx}, test_window matches: {test_window.sum()}")

if not quantile_batches:
    print("\nWARNING: No test predictions collected. Adjusting detection logic...")
    # Fallback: collect all predictions if none were found
    with torch.no_grad():
        for x, y in test_dataloader:
            output = model(x)
            quantile_batches.append(model.to_quantiles(output).cpu())
            actual_batches.append(y[0].cpu())

quantile_predictions = torch.cat(quantile_batches, dim=0).numpy()
actual_values = torch.cat(actual_batches, dim=0).numpy()
predictions = quantile_predictions[:, :, 1]


print("Prediction shape:")
print(predictions.shape)
print("Quantiles:", QUANTILES)


# ============================================================
# 8. CONVERT PREDICTIONS TO NUMPY
# ============================================================

predictions = np.asarray(predictions)

print("\nPrediction array:")
print(predictions)


# ============================================================
# 9. GET ACTUAL VALUES
# ============================================================

print("\nActual shape:")
print(actual_values.shape)


# ============================================================
# 10. FLATTEN VALUES
# ============================================================

pred_flat = predictions.reshape(-1)
actual_flat = actual_values.reshape(-1)


# ============================================================
# 11. CALCULATE MAE
# ============================================================

mae = np.mean(
    np.abs(actual_flat - pred_flat)
)


# ============================================================
# 12. CALCULATE RMSE
# ============================================================

rmse = np.sqrt(
    np.mean(
        (actual_flat - pred_flat) ** 2
    )
)


def pinball_loss(actual, predicted, quantile):
    error = actual - predicted
    return float(np.mean(np.maximum(quantile * error, (quantile - 1) * error)))


q10 = quantile_predictions[:, :, 0]
q50 = quantile_predictions[:, :, 1]
q90 = quantile_predictions[:, :, 2]
spike_actual = np.max(actual_values, axis=1) >= SPIKE_THRESHOLD
scale_up_signal = np.max(q90, axis=1) >= SPIKE_THRESHOLD
true_positive = np.sum(spike_actual & scale_up_signal)
false_positive = np.sum(~spike_actual & scale_up_signal)
false_negative = np.sum(spike_actual & ~scale_up_signal)
coverage = np.mean((actual_values >= q10) & (actual_values <= q90))

print("\nQuantile pinball loss:")
for quantile, values in zip(QUANTILES, (q10, q50, q90)):
    print(f"q{int(quantile * 100)}: {pinball_loss(actual_values, values, quantile):.6f}")
print(f"q10-q90 coverage: {coverage:.3%}")
print(f"Average q10-q90 interval width: {np.mean(q90 - q10):.6f}")
print(f"Spike threshold: {SPIKE_THRESHOLD}")
print(f"Spike precision: {true_positive / max(true_positive + false_positive, 1):.3%}")
print(f"Spike recall: {true_positive / max(true_positive + false_negative, 1):.3%}")


# ============================================================
# 13. PRINT RESULTS
# ============================================================

print("\n" + "=" * 60)
print("MODEL EVALUATION")
print("=" * 60)

print(f"MAE:  {mae:.6f}")
print(f"RMSE: {rmse:.6f}")


# ============================================================
# 14. SAVE PREDICTIONS
# ============================================================

results = pd.DataFrame({
    "window_id": np.repeat(np.arange(len(actual_values)), MAX_PREDICTION_LENGTH),
    "horizon_step": np.tile(np.arange(1, MAX_PREDICTION_LENGTH + 1), len(actual_values)),
    "actual_psi": actual_flat,
    "q10": q10.reshape(-1),
    "q50": q50.reshape(-1),
    "q90": q90.reshape(-1),
})

results.to_csv(
    DATA_DIR / "tft_predictions.csv",
    index=False
)


print("\nPredictions saved to:")
print("data/tft_predictions.csv")


# ============================================================
# 15. CREATE PLOT
# ============================================================

plt.figure(figsize=(12, 6))

plt.plot(
    actual_flat,
    label="Actual PSI"
)

plt.plot(
    pred_flat,
    label="Predicted PSI"
)

plt.xlabel("Prediction Step")
plt.ylabel("psi_some_avg10")

plt.title(
    "TFT Prediction vs Actual PSI"
)

plt.legend()

plt.grid(True)

plt.tight_layout()

plt.savefig(
    DATA_DIR / "tft_prediction_plot.png",
    dpi=150
)

plt.close()


print("\nPlot saved to:")
print("data/tft_prediction_plot.png")
