import pandas as pd
import torch

from pytorch_forecasting import (
    TimeSeriesDataSet,
    TemporalFusionTransformer,
)
from pytorch_forecasting.metrics import QuantileLoss

from lightning.pytorch import Trainer
from lightning.pytorch.callbacks import EarlyStopping, ModelCheckpoint


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

# Start small because your VM has limited RAM
HIDDEN_SIZE = 8
ATTENTION_HEAD_SIZE = 2
DROPOUT = 0.1

LEARNING_RATE = 0.001

MAX_EPOCHS = 20


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
# 4. CREATE VALIDATION DATASET
# ============================================================

train_val_df = pd.concat(
    [train_df, val_df],
    ignore_index=True
)

train_val_df = train_val_df.sort_values(
    ["segment_id", "time_idx"]
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

    output_size=7,

    loss=QuantileLoss(),

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

early_stop_callback = EarlyStopping(

    monitor="val_loss",

    min_delta=0.001,

    patience=5,

    mode="min",
)


checkpoint_callback = ModelCheckpoint(

    dirpath="models",

    filename="tft-psi-{epoch:02d}-{val_loss:.4f}",

    monitor="val_loss",

    mode="min",

    save_top_k=1,
)


# ============================================================
# 8. CREATE TRAINER
# ============================================================

trainer = Trainer(

    max_epochs=MAX_EPOCHS,

    accelerator="cpu",

    devices=1,

    gradient_clip_val=0.1,

    callbacks=[
        early_stop_callback,
        checkpoint_callback,
    ],

    enable_model_summary=True,

    log_every_n_steps=1,

)


# ============================================================
# 9. TRAIN
# ============================================================

print("\n" + "=" * 60)
print("STARTING TFT TRAINING")
print("=" * 60)

trainer.fit(

    tft,

    train_dataloaders=train_dataloader,

    val_dataloaders=val_dataloader,
)


# ============================================================
# 10. SAVE FINAL MODEL
# ============================================================

trainer.save_checkpoint(MODEL_FILE)

print("\n" + "=" * 60)
print("TRAINING COMPLETE")
print("=" * 60)

print("\nModel saved to:")

print(MODEL_FILE)
