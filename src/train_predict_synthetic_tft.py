#!/usr/bin/env python3
"""
Train TemporalFusionTransformer on synthetic 7-day PSI data and evaluate
spike detection performance with threshold 1.8.

This script:
1. Loads train/val/test splits from data/synthetic/
2. Trains TFT model for spike prediction
3. Evaluates on test set with threshold 1.8
4. Reports recall, precision, and other metrics
5. Saves predictions and visualizations
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import matplotlib.pyplot as plt
from sklearn.metrics import recall_score, precision_score, f1_score, confusion_matrix

from pytorch_forecasting import TimeSeriesDataSet, TemporalFusionTransformer
from pytorch_forecasting.metrics import QuantileLoss
from pytorch_forecasting.data import GroupNormalizer

# ============================================================================
# CONFIGURATION
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "synthetic"
MODEL_DIR = PROJECT_ROOT / "models"

TRAIN_FILE = DATA_DIR / "train.csv"
VAL_FILE = DATA_DIR / "val.csv"
TEST_FILE = DATA_DIR / "test.csv"
METADATA_FILE = DATA_DIR / "metadata.json"

MODEL_FILE = MODEL_DIR / "tft_synthetic_psi_model.ckpt"
RESULTS_DIR = DATA_DIR / "results"

TARGET = "psi_io_some_avg10"
SPIKE_THRESHOLD = 1.8  # ← Key threshold for spike detection

MAX_ENCODER_LENGTH = 96  # ~24 minutes @ 15s
MAX_PREDICTION_LENGTH = 24  # ~6 minutes @ 15s

BATCH_SIZE = 32
HIDDEN_SIZE = 16
ATTENTION_HEAD_SIZE = 2
DROPOUT = 0.1
LEARNING_RATE = 0.001

MAX_EPOCHS = 50
EARLY_STOPPING_PATIENCE = 5

# ============================================================================
# UTILITIES
# ============================================================================

def setup_directories():
    """Create output directories"""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

def load_metadata():
    """Load metadata JSON"""
    with open(METADATA_FILE) as f:
        return json.load(f)

def print_header(title):
    """Print formatted section header"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)

# ============================================================================
# STEP 1: LOAD DATA
# ============================================================================

print_header("STEP 1: LOAD DATA")

metadata = load_metadata()
print(f"Metadata loaded: {metadata['data_origin']}")
print(f"  Seed: {metadata['seed']}")
print(f"  Spike threshold (metadata): {metadata['spike_threshold']}")
print(f"  Spike threshold (for detection): {SPIKE_THRESHOLD}")

train_df = pd.read_csv(TRAIN_FILE)
val_df = pd.read_csv(VAL_FILE)
test_df = pd.read_csv(TEST_FILE)

for df in [train_df, val_df, test_df]:
    df["timestamp"] = pd.to_datetime(df["timestamp"])

print(f"\nTrain: {len(train_df):,} rows")
print(f"Val:   {len(val_df):,} rows")
print(f"Test:  {len(test_df):,} rows")

# Data quality check
for split_name, split_df in [("train", train_df), ("val", val_df), ("test", test_df)]:
    nan_count = split_df.isna().sum().sum()
    spike_count = (split_df[TARGET] > SPIKE_THRESHOLD).sum()
    spike_pct = 100.0 * spike_count / len(split_df)
    print(f"\n{split_name}:")
    print(f"  NaNs: {nan_count}")
    print(f"  Spikes (>{SPIKE_THRESHOLD}): {spike_count:,} ({spike_pct:.2f}%)")

# ============================================================================
# STEP 2: PYTORCH INFO
# ============================================================================

print_header("STEP 2: PYTORCH SETUP")

print(f"PyTorch version: {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    device = "cuda"
else:
    print("Using CPU")
    device = "cpu"

# ============================================================================
# STEP 3: CREATE TRAINING DATASET
# ============================================================================

print_header("STEP 3: CREATE TRAINING TIMESERIESDATASET")

column_roles = metadata["column_roles"]

training_dataset = TimeSeriesDataSet(
    train_df,
    time_idx="time_idx",
    target=TARGET,
    group_ids=column_roles["group_ids"],  # ["node_id"]
    max_encoder_length=MAX_ENCODER_LENGTH,
    max_prediction_length=MAX_PREDICTION_LENGTH,
    static_categoricals=column_roles["static_categoricals"],
    time_varying_known_reals=column_roles["time_varying_known_reals"],
    time_varying_unknown_reals=column_roles["time_varying_unknown_reals"],
    target_normalizer=GroupNormalizer(groups=column_roles["group_ids"]),
    add_relative_time_idx=False,
    add_target_scales=True,
    allow_missing_timesteps=False,
)

print(f"Training dataset: {len(training_dataset):,} samples")

# ============================================================================
# STEP 4: CREATE VALIDATION DATASET
# ============================================================================

print_header("STEP 4: CREATE VALIDATION TIMESERIESDATASET")

train_val_df = pd.concat([train_df, val_df], ignore_index=True).sort_values(
    ["node_id", "time_idx"]
).reset_index(drop=True)

validation_dataset = TimeSeriesDataSet.from_dataset(
    training_dataset,
    train_val_df,
    predict=True,
    stop_randomization=True,
    allow_missing_timesteps=True,  # Allow gap between splits
)

print(f"Validation dataset: {len(validation_dataset):,} samples")

# ============================================================================
# STEP 5: CREATE DATALOADERS
# ============================================================================

print_header("STEP 5: CREATE DATALOADERS")

train_dataloader = training_dataset.to_dataloader(
    train=True,
    batch_size=BATCH_SIZE,
    num_workers=0,
)

val_dataloader = validation_dataset.to_dataloader(
    train=False,
    batch_size=BATCH_SIZE,
    num_workers=0,
)

print(f"Train dataloader: {len(train_dataloader)} batches")
print(f"Val dataloader:   {len(val_dataloader)} batches")

# ============================================================================
# STEP 6: CREATE & TRAIN MODEL
# ============================================================================

print_header("STEP 6: CREATE TEMPORAL FUSION TRANSFORMER")

tft = TemporalFusionTransformer.from_dataset(
    training_dataset,
    learning_rate=LEARNING_RATE,
    hidden_size=HIDDEN_SIZE,
    attention_head_size=ATTENTION_HEAD_SIZE,
    dropout=DROPOUT,
    hidden_continuous_size=HIDDEN_SIZE,
    output_size=3,
    loss=QuantileLoss(quantiles=[0.1, 0.5, 0.9]),
    log_interval=50,
)

total_params = sum(p.numel() for p in tft.parameters())
print(f"Model parameters: {total_params:,}")
print(f"Hidden size: {HIDDEN_SIZE}")
print(f"Attention heads: {ATTENTION_HEAD_SIZE}")
print(f"Dropout: {DROPOUT}")

# ============================================================================
# STEP 7: TRAINING LOOP
# ============================================================================

print_header("STEP 7: TRAINING")

tft = tft.to(device)
optimizer = torch.optim.Adam(tft.parameters(), lr=LEARNING_RATE)
best_val_loss = float("inf")
epochs_without_improvement = 0
training_history = []

for epoch in range(1, MAX_EPOCHS + 1):
    # Train
    tft.train()
    train_loss_total = 0.0
    train_batches = 0

    for x, y in train_dataloader:
        # Move to device
        if isinstance(x, dict):
            x = {k: v.to(device) if isinstance(v, torch.Tensor) else v for k, v in x.items()}
        
        # y is a tuple (target, weight)
        if isinstance(y, tuple):
            y = (y[0].to(device), y[1].to(device) if y[1] is not None else None)
        else:
            y = y.to(device)

        optimizer.zero_grad()
        output = tft(x)
        loss = tft.loss(output["prediction"], y)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(tft.parameters(), max_norm=0.1)
        optimizer.step()

        train_loss_total += float(loss.detach())
        train_batches += 1

    # Validate
    tft.eval()
    val_loss_total = 0.0
    val_batches = 0

    with torch.no_grad():
        for x, y in val_dataloader:
            if isinstance(x, dict):
                x = {k: v.to(device) if isinstance(v, torch.Tensor) else v for k, v in x.items()}
            
            # y is a tuple (target, weight)
            if isinstance(y, tuple):
                y = (y[0].to(device), y[1].to(device) if y[1] is not None else None)
            else:
                y = y.to(device)

            output = tft(x)
            val_loss_total += float(tft.loss(output["prediction"], y))
            val_batches += 1

    train_loss = train_loss_total / max(train_batches, 1)
    val_loss = val_loss_total / max(val_batches, 1)

    training_history.append({
        "epoch": epoch,
        "train_loss": train_loss,
        "val_loss": val_loss,
    })

    print(f"Epoch {epoch:02d}/{MAX_EPOCHS}: train_loss={train_loss:.6f}, val_loss={val_loss:.6f}", end="")

    if val_loss < best_val_loss - 0.001:
        best_val_loss = val_loss
        epochs_without_improvement = 0
        torch.save(
            {
                "state_dict": tft.state_dict(),
                "hyper_parameters": dict(tft.hparams),
            },
            MODEL_FILE,
        )
        print(" ✓ (saved)")
    else:
        epochs_without_improvement += 1
        print()
        if epochs_without_improvement >= EARLY_STOPPING_PATIENCE:
            print(f"\n✓ Early stopping at epoch {epoch}")
            break

print(f"\n✓ Training complete. Best val_loss: {best_val_loss:.6f}")

# Save training history
history_df = pd.DataFrame(training_history)
history_df.to_csv(RESULTS_DIR / "training_history.csv", index=False)

# ============================================================================
# STEP 8: LOAD BEST MODEL & PREPARE TEST DATA
# ============================================================================

print_header("STEP 8: PREPARE TEST PREDICTIONS")

tft.load_state_dict(torch.load(MODEL_FILE)["state_dict"])
tft.eval()

# Combine all data for test predictions
all_test_data = pd.concat([train_df, val_df, test_df], ignore_index=True).sort_values(
    ["node_id", "time_idx"]
).reset_index(drop=True)

test_dataset = TimeSeriesDataSet.from_dataset(
    training_dataset,
    all_test_data,
    predict=False,
    stop_randomization=True,
    allow_missing_timesteps=True,
)

test_dataloader = test_dataset.to_dataloader(
    train=False,
    batch_size=BATCH_SIZE,
    num_workers=0,
)

print(f"Test dataset: {len(test_dataset):,} samples")
print(f"Test dataloader: {len(test_dataloader)} batches")

# ============================================================================
# STEP 9: MAKE PREDICTIONS
# ============================================================================

print_header("STEP 9: MAKE TEST PREDICTIONS")

quantile_batches = []
actual_batches = []
test_start_idx = int(train_df["time_idx"].max()) + val_df.shape[0] + 1  # After gap

with torch.no_grad():
    for x, y in test_dataloader:
        # Move to device
        if isinstance(x, dict):
            x = {k: v.to(device) if isinstance(v, torch.Tensor) else v for k, v in x.items()}
        
        # y is a tuple (target, weight)
        if isinstance(y, tuple):
            y = (y[0].to(device), y[1].to(device) if y[1] is not None else None)
        else:
            y = y.to(device)

        # Filter to test period only
        test_window = x["decoder_time_idx"][:, 0] >= test_start_idx
        if not test_window.any():
            continue

        output = tft(x)
        quantiles = tft.to_quantiles(output)[test_window].cpu()
        quantile_batches.append(quantiles)

        if isinstance(y, tuple):
            actual_batches.append(y[0][test_window].cpu())
        else:
            actual_batches.append(y[test_window].cpu())

quantile_predictions = torch.cat(quantile_batches, dim=0).numpy()
actual_values = torch.cat(actual_batches, dim=0).numpy()
q10 = quantile_predictions[:, :, 0]
q50 = quantile_predictions[:, :, 1]
q90 = quantile_predictions[:, :, 2]

print(f"Predictions shape: {q50.shape}")
print(f"Actual shape: {actual_values.shape}")

# ============================================================================
# STEP 10: EVALUATE SPIKE DETECTION
# ============================================================================

print_header("STEP 10: SPIKE DETECTION EVALUATION")

# Define spikes based on max value in prediction window
spike_actual = np.max(actual_values, axis=1) >= SPIKE_THRESHOLD
spike_pred_q50 = np.max(q50, axis=1) >= SPIKE_THRESHOLD
spike_pred_q90 = np.max(q90, axis=1) >= SPIKE_THRESHOLD

# Evaluation metrics
tp_q50 = np.sum(spike_actual & spike_pred_q50)
fp_q50 = np.sum(~spike_actual & spike_pred_q50)
fn_q50 = np.sum(spike_actual & ~spike_pred_q50)
tn_q50 = np.sum(~spike_actual & ~spike_pred_q50)

tp_q90 = np.sum(spike_actual & spike_pred_q90)
fp_q90 = np.sum(~spike_actual & spike_pred_q90)
fn_q90 = np.sum(spike_actual & ~spike_pred_q90)
tn_q90 = np.sum(~spike_actual & ~spike_pred_q90)

print(f"\nThreshold: {SPIKE_THRESHOLD} PSI")
print(f"True positives (actual spikes): {spike_actual.sum():,}")
print(f"Predicted spikes (q50): {spike_pred_q50.sum():,}")
print(f"Predicted spikes (q90): {spike_pred_q90.sum():,}")

print(f"\nQ50 Predictions:")
print(f"  TP: {tp_q50}, FP: {fp_q50}, FN: {fn_q50}, TN: {tn_q50}")
recall_q50 = recall_score(spike_actual, spike_pred_q50, zero_division=0)
precision_q50 = precision_score(spike_actual, spike_pred_q50, zero_division=0)
f1_q50 = f1_score(spike_actual, spike_pred_q50, zero_division=0)
print(f"  Recall: {recall_q50:.3%}")
print(f"  Precision: {precision_q50:.3%}")
print(f"  F1: {f1_q50:.3f}")

print(f"\nQ90 Predictions:")
print(f"  TP: {tp_q90}, FP: {fp_q90}, FN: {fn_q90}, TN: {tn_q90}")
recall_q90 = recall_score(spike_actual, spike_pred_q90, zero_division=0)
precision_q90 = precision_score(spike_actual, spike_pred_q90, zero_division=0)
f1_q90 = f1_score(spike_actual, spike_pred_q90, zero_division=0)
print(f"  Recall: {recall_q90:.3%}")
print(f"  Precision: {precision_q90:.3%}")
print(f"  F1: {f1_q90:.3f}")

# ============================================================================
# STEP 11: CONTINUOUS VALUE METRICS
# ============================================================================

print_header("STEP 11: CONTINUOUS VALUE METRICS")

pred_flat = q50.reshape(-1)
actual_flat = actual_values.reshape(-1)

mae = np.mean(np.abs(actual_flat - pred_flat))
rmse = np.sqrt(np.mean((actual_flat - pred_flat) ** 2))
mape = np.mean(np.abs((actual_flat - pred_flat) / np.maximum(actual_flat, 0.01))) * 100

coverage = np.mean((actual_values >= q10) & (actual_values <= q90))
interval_width = np.mean(q90 - q10)

print(f"MAE:  {mae:.6f}")
print(f"RMSE: {rmse:.6f}")
print(f"MAPE: {mape:.2f}%")
print(f"\nQuantile Coverage (q10-q90): {coverage:.3%}")
print(f"Average Interval Width: {interval_width:.6f}")

# Pinball loss
def pinball_loss(actual, predicted, quantile):
    error = actual - predicted
    return np.mean(np.maximum(quantile * error, (quantile - 1) * error))

q10_loss = pinball_loss(actual_values, q10, 0.1)
q50_loss = pinball_loss(actual_values, q50, 0.5)
q90_loss = pinball_loss(actual_values, q90, 0.9)

print(f"\nPinball Loss:")
print(f"  q10: {q10_loss:.6f}")
print(f"  q50: {q50_loss:.6f}")
print(f"  q90: {q90_loss:.6f}")

# ============================================================================
# STEP 12: SAVE RESULTS
# ============================================================================

print_header("STEP 12: SAVE RESULTS")

# Save predictions
predictions_df = pd.DataFrame({
    "window_id": np.repeat(np.arange(len(actual_values)), MAX_PREDICTION_LENGTH),
    "horizon_step": np.tile(np.arange(1, MAX_PREDICTION_LENGTH + 1), len(actual_values)),
    "actual": actual_flat,
    "q10": q10.reshape(-1),
    "q50": q50.reshape(-1),
    "q90": q90.reshape(-1),
})

predictions_df.to_csv(RESULTS_DIR / "predictions.csv", index=False)
print(f"✓ Saved predictions to: {RESULTS_DIR / 'predictions.csv'}")

# Save evaluation metrics
metrics_df = pd.DataFrame({
    "Metric": [
        "Threshold",
        "MAE",
        "RMSE",
        "MAPE",
        "Q50_Recall",
        "Q50_Precision",
        "Q50_F1",
        "Q90_Recall",
        "Q90_Precision",
        "Q90_F1",
        "Quantile_Coverage",
        "Interval_Width",
    ],
    "Value": [
        SPIKE_THRESHOLD,
        mae,
        rmse,
        mape,
        recall_q50,
        precision_q50,
        f1_q50,
        recall_q90,
        precision_q90,
        f1_q90,
        coverage,
        interval_width,
    ],
})

metrics_df.to_csv(RESULTS_DIR / "metrics.csv", index=False)
print(f"✓ Saved metrics to: {RESULTS_DIR / 'metrics.csv'}")

# ============================================================================
# STEP 13: VISUALIZATIONS
# ============================================================================

print_header("STEP 13: CREATE VISUALIZATIONS")

# Plot 1: Predictions vs Actual
fig, ax = plt.subplots(figsize=(14, 6))
ax.plot(actual_flat, label="Actual", linewidth=1, alpha=0.8)
ax.plot(pred_flat, label="Q50 Prediction", linewidth=1, alpha=0.8)
ax.fill_between(np.arange(len(q10.reshape(-1))), q10.reshape(-1), q90.reshape(-1), alpha=0.2, label="Q10-Q90 Interval")
ax.axhline(SPIKE_THRESHOLD, color="red", linestyle="--", linewidth=1, label=f"Spike Threshold ({SPIKE_THRESHOLD})")
ax.set_xlabel("Prediction Step")
ax.set_ylabel("psi_io_some_avg10")
ax.set_title("TFT Predictions vs Actual PSI Values (Threshold 1.8)")
ax.legend()
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(RESULTS_DIR / "predictions_plot.png", dpi=150)
plt.close()
print(f"✓ Saved plot: {RESULTS_DIR / 'predictions_plot.png'}")

# Plot 2: Spike Detection Confusion Matrix
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))

# Q50
cm_q50 = confusion_matrix(spike_actual, spike_pred_q50)
ax1.imshow(cm_q50, cmap="Blues", aspect="auto")
ax1.set_xlabel("Predicted")
ax1.set_ylabel("Actual")
ax1.set_title(f"Q50 Spike Detection (Recall: {recall_q50:.1%}, Precision: {precision_q50:.1%})")
ax1.set_xticks([0, 1])
ax1.set_yticks([0, 1])
ax1.set_xticklabels(["No Spike", "Spike"])
ax1.set_yticklabels(["No Spike", "Spike"])
for i in range(2):
    for j in range(2):
        ax1.text(j, i, str(cm_q50[i, j]), ha="center", va="center", color="white", fontsize=12)

# Q90
cm_q90 = confusion_matrix(spike_actual, spike_pred_q90)
ax2.imshow(cm_q90, cmap="Blues", aspect="auto")
ax2.set_xlabel("Predicted")
ax2.set_ylabel("Actual")
ax2.set_title(f"Q90 Spike Detection (Recall: {recall_q90:.1%}, Precision: {precision_q90:.1%})")
ax2.set_xticks([0, 1])
ax2.set_yticks([0, 1])
ax2.set_xticklabels(["No Spike", "Spike"])
ax2.set_yticklabels(["No Spike", "Spike"])
for i in range(2):
    for j in range(2):
        ax2.text(j, i, str(cm_q90[i, j]), ha="center", va="center", color="white", fontsize=12)

plt.tight_layout()
plt.savefig(RESULTS_DIR / "spike_detection_confusion_matrix.png", dpi=150)
plt.close()
print(f"✓ Saved plot: {RESULTS_DIR / 'spike_detection_confusion_matrix.png'}")

# Plot 3: Training History
fig, ax = plt.subplots(figsize=(10, 6))
ax.plot(history_df["epoch"], history_df["train_loss"], marker="o", label="Train Loss", linewidth=2)
ax.plot(history_df["epoch"], history_df["val_loss"], marker="s", label="Val Loss", linewidth=2)
ax.set_xlabel("Epoch")
ax.set_ylabel("Loss")
ax.set_title("TFT Training History")
ax.legend()
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(RESULTS_DIR / "training_history.png", dpi=150)
plt.close()
print(f"✓ Saved plot: {RESULTS_DIR / 'training_history.png'}")

# ============================================================================
# FINAL SUMMARY
# ============================================================================

print_header("FINAL SUMMARY")

print(f"\n{'Metric':<30} {'Value':<15}")
print("-" * 45)
print(f"{'Spike Threshold':<30} {SPIKE_THRESHOLD:<15}")
print(f"{'Test Samples':<30} {len(actual_values):,}")
print(f"{'Actual Spikes':<30} {spike_actual.sum():,}")
print(f"{'MAE':<30} {mae:.6f}")
print(f"{'RMSE':<30} {rmse:.6f}")
print(f"{'MAPE':<30} {mape:.2f}%")
print(f"\n{'Q50 Recall':<30} {recall_q50:.3%}")
print(f"{'Q50 Precision':<30} {precision_q50:.3%}")
print(f"{'Q50 F1':<30} {f1_q50:.3f}")
print(f"\n{'Q90 Recall':<30} {recall_q90:.3%}")
print(f"{'Q90 Precision':<30} {precision_q90:.3%}")
print(f"{'Q90 F1':<30} {f1_q90:.3f}")
print(f"\n{'Output Files':<30}")
print(f"  - {RESULTS_DIR / 'predictions.csv'}")
print(f"  - {RESULTS_DIR / 'metrics.csv'}")
print(f"  - {RESULTS_DIR / 'training_history.csv'}")
print(f"  - {RESULTS_DIR / 'predictions_plot.png'}")
print(f"  - {RESULTS_DIR / 'spike_detection_confusion_matrix.png'}")
print(f"  - {RESULTS_DIR / 'training_history.png'}")

print("\n" + "=" * 80)
print("✓ COMPLETE")
print("=" * 80)
