from pathlib import Path

import pandas as pd
import torch
import numpy as np

from pytorch_forecasting import (
    TimeSeriesDataSet,
    TemporalFusionTransformer,
)
from pytorch_forecasting.metrics import QuantileLoss



# ============================================================
# CONFIGURATION - TIER 1 & 2 IMPROVEMENTS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
MODEL_DIR = PROJECT_ROOT / "models"

TRAIN_FILE = DATA_DIR / "train.csv"
VAL_FILE = DATA_DIR / "validation.csv"
TEST_FILE = DATA_DIR / "test.csv"

MODEL_FILE = MODEL_DIR / "tft_psi_model_improved.ckpt"

TARGET = "psi_some_avg10"

MAX_ENCODER_LENGTH = 30  # 10 minutes of 20-second history
MAX_PREDICTION_LENGTH = 30  # 10-minute forecast horizon

BATCH_SIZE = 16

# ============================================================
# TIER 1 IMPROVEMENTS:
# - Increased hidden_size from 8 → 64 (capacity improvement)
# - Increased attention_head_size from 2 → 4
# - Gradient clipping from 0.1 → 1.0 (less aggressive)
# - Patience from 3 → 6 (allow more training)
# ============================================================
HIDDEN_SIZE = 64  # Was 8
ATTENTION_HEAD_SIZE = 4  # Was 2
DROPOUT = 0.1

LEARNING_RATE = 0.001
GRADIENT_CLIP_NORM = 1.0  # Was 0.1

MAX_EPOCHS = 20  # Increased from 3
EARLY_STOPPING_PATIENCE = 6  # Was 3

# ============================================================
# TIER 2: Sample weighting for spike windows
# ============================================================
SPIKE_THRESHOLD = 2.0
SPIKE_WEIGHT = 5.0  # Weight for spike timesteps


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
# TIER 2: ADD DERIVATIVE FEATURES (Leading indicators)
# ============================================================

def add_derivative_features(df):
    """Add slope/derivative features as leading indicators"""
    df = df.copy()
    
    # Sort by series and time
    df = df.sort_values(['series_id', 'time_idx']).reset_index(drop=True)
    
    # Calculate derivatives (differences) for key metrics
    for col in ['cpu_usage', 'psi_some_avg10', 'request_rate', 'memory_usage']:
        df[f'delta_{col}'] = df.groupby('series_id')[col].diff().fillna(0)
    
    return df

print("\nAdding derivative features (Tier 2)...")
train_df = add_derivative_features(train_df)
val_df = add_derivative_features(val_df)
test_df = add_derivative_features(test_df)


# ============================================================
# TIER 2: ADD SAMPLE WEIGHTS FOR SPIKE WINDOWS
# ============================================================

def add_spike_weights(df, threshold=SPIKE_THRESHOLD, weight=SPIKE_WEIGHT):
    """Add sample weights - higher for spike windows"""
    df = df.copy()
    df['weight'] = 1.0
    
    # Mark spike timesteps with higher weight
    df.loc[df[TARGET] >= threshold, 'weight'] = weight
    
    spike_count = (df['weight'] > 1.0).sum()
    total_count = len(df)
    
    print(f"  Spike timesteps: {spike_count} ({100*spike_count/total_count:.2f}%)")
    print(f"  Normal timesteps: {total_count - spike_count} ({100*(total_count-spike_count)/total_count:.2f}%)")
    
    return df

print("\nAdding sample weights (Tier 2)...")
train_df = add_spike_weights(train_df)
val_df = add_spike_weights(val_df)


# ============================================================
# TIER 2: AUDIT SPIKE DISTRIBUTION
# ============================================================

def audit_spike_distribution(train_df, val_df, test_df, threshold=SPIKE_THRESHOLD):
    """Audit spike distribution across splits"""
    train_spikes = (train_df[TARGET] >= threshold).sum()
    val_spikes = (val_df[TARGET] >= threshold).sum()
    test_spikes = (test_df[TARGET] >= threshold).sum()
    
    print("\n" + "=" * 60)
    print("SPIKE DISTRIBUTION AUDIT (Tier 2)")
    print("=" * 60)
    print(f"Train spikes: {train_spikes} ({100*train_spikes/len(train_df):.2f}%)")
    print(f"Val spikes:   {val_spikes} ({100*val_spikes/len(val_df):.2f}%)")
    print(f"Test spikes:  {test_spikes} ({100*test_spikes/len(test_df):.2f}%)")

audit_spike_distribution(train_df, val_df, test_df)


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
    
    # TIER 2: Add sample weights
    weight="weight",

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
        
        # TIER 2: Add derivative features
        "delta_cpu_usage",
        "delta_psi_some_avg10",
        "delta_request_rate",
        "delta_memory_usage",
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
print("CREATING IMPROVED TEMPORAL FUSION TRANSFORMER")
print("=" * 60)
print(f"TIER 1 IMPROVEMENTS:")
print(f"  - Hidden size: {HIDDEN_SIZE} (was 8)")
print(f"  - Attention heads: {ATTENTION_HEAD_SIZE} (was 2)")
print(f"  - Gradient clip: {GRADIENT_CLIP_NORM} (was 0.1)")
print(f"  - Patience: {EARLY_STOPPING_PATIENCE} (was 3)")
print(f"TIER 2 IMPROVEMENTS:")
print(f"  - Sample weighting: {SPIKE_WEIGHT}x for spikes")
print(f"  - Derivative features added")
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
num_params = sum(p.numel() for p in tft.parameters())
print(f"{num_params:,}")


# ============================================================
# 7. TRAIN WITH TIER 1 IMPROVEMENTS
# ============================================================

print("\n" + "=" * 60)
print("STARTING IMPROVED TFT TRAINING")
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
        # TIER 1: Increased gradient clip from 0.1 to 1.0
        torch.nn.utils.clip_grad_norm_(tft.parameters(), max_norm=GRADIENT_CLIP_NORM)
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

    # TIER 1: Increased patience from 3 to 6
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
        print(f"  → Saved checkpoint (val_loss improved)")
    else:
        epochs_without_improvement += 1
        if epochs_without_improvement >= EARLY_STOPPING_PATIENCE:
            print(f"Early stopping triggered after {epoch} epochs.")
            break


# ============================================================
# 8. SAVE FINAL MODEL
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

print("\nImproved model saved to:")
print(MODEL_FILE)

