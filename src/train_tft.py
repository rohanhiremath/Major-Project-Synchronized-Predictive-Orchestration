from pathlib import Path

import pandas as pd
import torch

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

TRAIN_FILE = DATA_DIR / "train.csv"
VAL_FILE = DATA_DIR / "validation.csv"
TEST_FILE = DATA_DIR / "test.csv"

MODEL_FILE = MODEL_DIR / "tft_psi_model.ckpt"

TARGET = "psi_some_avg10"

MAX_ENCODER_LENGTH = 30  # 10 minutes of 20-second history
MAX_PREDICTION_LENGTH = 30  # 10-minute forecast horizon

BATCH_SIZE = 16

# Start small because your VM has limited RAM
HIDDEN_SIZE = 8
ATTENTION_HEAD_SIZE = 2
DROPOUT = 0.1

LEARNING_RATE = 0.001

MAX_EPOCHS = 3
EARLY_STOPPING_PATIENCE = 3


# ============================================================
# 1. CHECK PYTORCH
# ============================================================

print("=" * 60)
print("PYTORCH INFORMATION")
print("=" * 60)

print("PyTorch version:", torch.__version__)
print("CUDA available:", torch.cuda.is_available())

if torch.cuda.is_available():
    print("GPU:", torch.cuda.get_device_name(0))
else:
    print("Training will use CPU.")


# ============================================================
# 2. LOAD DATA
# ============================================================

train_df = pd.read_csv(TRAIN_FILE)
val_df = pd.read_csv(VAL_FILE)
test_df = pd.read_csv(TEST_FILE)

train_df["timestamp"] = pd.to_datetime(train_df["timestamp"])
val_df["timestamp"] = pd.to_datetime(val_df["timestamp"])
test_df["timestamp"] = pd.to_datetime(test_df["timestamp"])

print("\n" + "=" * 60)
print("DATA")
print("=" * 60)

print("Training rows:", len(train_df))
print("Validation rows:", len(val_df))
print("Test rows:", len(test_df))


# ============================================================
# 3. CREATE TRAINING DATASET
# ============================================================

training_dataset = TimeSeriesDataSet(

    train_df,

    time_idx="time_idx",

    target=TARGET,

    group_ids=["series_id"],

    max_encoder_length=MAX_ENCODER_LENGTH,

    max_prediction_length=MAX_PREDICTION_LENGTH,

    time_varying_known_reals=[
        "time_idx",
        "hour_sin",
        "hour_cos",
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
    ],
)


# ============================================================
# 4. CREATE VALIDATION DATASET
# ============================================================

train_val_df = pd.concat(
    [train_df, val_df],
    ignore_index=True
)

train_val_df = train_val_df.sort_values(
    ["series_id", "time_idx"]
).reset_index(drop=True)


validation_dataset = TimeSeriesDataSet.from_dataset(
    training_dataset,
    train_val_df,
    predict=True,
    stop_randomization=True,
)


# ============================================================
# 5. CREATE DATALOADERS
# ============================================================

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


print("\n" + "=" * 60)
print("DATALOADERS")
print("=" * 60)

print("Training samples:", len(training_dataset))
print("Validation samples:", len(validation_dataset))


# ============================================================
# 6. CREATE TFT MODEL
# ============================================================

print("\n" + "=" * 60)
print("CREATING TEMPORAL FUSION TRANSFORMER")
print("=" * 60)


tft = TemporalFusionTransformer.from_dataset(

    training_dataset,

    learning_rate=LEARNING_RATE,

    hidden_size=HIDDEN_SIZE,

    attention_head_size=ATTENTION_HEAD_SIZE,

    dropout=DROPOUT,

    hidden_continuous_size=HIDDEN_SIZE,

    output_size=3,

    loss=QuantileLoss(quantiles=[0.1, 0.5, 0.9]),

    log_interval=10,

    reduce_on_plateau_patience=3,
)


print(tft)

print("\nNumber of parameters:")

print(
    sum(
        p.numel()
        for p in tft.parameters()
    )
)


# ============================================================
# 7. CALLBACKS
# ============================================================

# ============================================================
# 8. TRAIN WITHOUT DISTRIBUTED RUNTIME
# ============================================================

print("\n" + "=" * 60)
print("STARTING TFT TRAINING")
print("=" * 60)

optimizer = torch.optim.Adam(tft.parameters(), lr=LEARNING_RATE)
best_val_loss = float("inf")
epochs_without_improvement = 0

for epoch in range(1, MAX_EPOCHS + 1):
    tft.train()
    train_loss_total = 0.0
    train_batches = 0

    for x, y in train_dataloader:
        optimizer.zero_grad()
        output = tft(x)
        loss = tft.loss(output["prediction"], y)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(tft.parameters(), max_norm=0.1)
        optimizer.step()
        train_loss_total += float(loss.detach())
        train_batches += 1

    tft.eval()
    val_loss_total = 0.0
    val_batches = 0
    with torch.no_grad():
        for x, y in val_dataloader:
            output = tft(x)
            val_loss_total += float(tft.loss(output["prediction"], y))
            val_batches += 1

    train_loss = train_loss_total / max(train_batches, 1)
    val_loss = val_loss_total / max(val_batches, 1)
    print(f"Epoch {epoch:02d}: train_loss={train_loss:.6f}, val_loss={val_loss:.6f}")

    if val_loss < best_val_loss - 0.001:
        best_val_loss = val_loss
        epochs_without_improvement = 0
        torch.save(
            {
                "state_dict": tft.state_dict(),
                "hyper_parameters": dict(tft.hparams),
                "pytorch-lightning_version": "2.6.5",
                "__special_save__": {
                    "loss": tft.loss,
                    "logging_metrics": tft.logging_metrics,
                },
            },
            MODEL_FILE,
        )
    else:
        epochs_without_improvement += 1
        if epochs_without_improvement >= EARLY_STOPPING_PATIENCE:
            print("Early stopping triggered.")
            break


# ============================================================
# 9. SAVE FINAL MODEL
# ============================================================

if not MODEL_FILE.exists():
    torch.save(
        {
            "state_dict": tft.state_dict(),
            "hyper_parameters": dict(tft.hparams),
            "pytorch-lightning_version": "2.6.5",
            "__special_save__": {
                "loss": tft.loss,
                "logging_metrics": tft.logging_metrics,
            },
        },
        MODEL_FILE,
    )

print("\n" + "=" * 60)
print("TRAINING COMPLETE")
print("=" * 60)

print("\nModel saved to:")

print(MODEL_FILE)
