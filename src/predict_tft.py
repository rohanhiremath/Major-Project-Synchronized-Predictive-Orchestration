import pandas as pd
import numpy as np
import torch
import matplotlib.pyplot as plt

from pytorch_forecasting import TimeSeriesDataSet
from pytorch_forecasting import TemporalFusionTransformer


# ============================================================
# CONFIGURATION
# ============================================================

TRAIN_FILE = "data/train.csv"
VAL_FILE = "data/validation.csv"
TEST_FILE = "data/test.csv"

MODEL_FILE = "models/tft_psi_model.ckpt"

TARGET = "psi_some_avg10"

MAX_ENCODER_LENGTH = 24
MAX_PREDICTION_LENGTH = 6

BATCH_SIZE = 16


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

    group_ids=["segment_id"],

    max_encoder_length=MAX_ENCODER_LENGTH,

    max_prediction_length=MAX_PREDICTION_LENGTH,

    time_varying_known_reals=[
        "time_idx",
    ],

    time_varying_unknown_reals=[
        "cpu_usage",
        "memory_usage",
        "read_bytes_per_sec",
        "write_bytes_per_sec",

        "psi_some_avg10",
        "psi_some_avg60",
        "psi_some_avg300",

        "psi_full_avg10",
        "psi_full_avg60",
        "psi_full_avg300",
    ],
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
    ["segment_id", "time_idx"]
).reset_index(drop=True)


# ============================================================
# 4. CREATE TEST DATASET
# ============================================================

test_dataset = TimeSeriesDataSet.from_dataset(

    training_dataset,

    all_test_data,

    predict=True,

    stop_randomization=True,
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

predictions = model.predict(
    test_dataloader,
    mode="prediction"
)


print("Prediction shape:")
print(predictions.shape)


# ============================================================
# 8. CONVERT PREDICTIONS TO NUMPY
# ============================================================

if torch.is_tensor(predictions):
    predictions = predictions.detach().cpu().numpy()

predictions = np.asarray(predictions)

print("\nPrediction array:")
print(predictions)


# ============================================================
# 9. GET ACTUAL VALUES
# ============================================================

actual_values = []

for batch in test_dataloader:

    x, y = batch

    target = y[0]

    if torch.is_tensor(target):
        target = target.detach().cpu().numpy()

    actual_values.append(target)


actual_values = np.concatenate(
    actual_values,
    axis=0
)


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

    "actual_psi": actual_flat,

    "predicted_psi": pred_flat,

})

results.to_csv(
    "data/tft_predictions.csv",
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
    "data/tft_prediction_plot.png",
    dpi=150
)

plt.show()


print("\nPlot saved to:")
print("data/tft_prediction_plot.png")
