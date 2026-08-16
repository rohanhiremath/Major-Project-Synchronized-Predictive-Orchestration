import pandas as pd

from pytorch_forecasting import TimeSeriesDataSet


# ============================================================
# 1. LOAD PROCESSED DATA
# ============================================================

DATA_FILE = "data/processed_ptcs.csv"

df = pd.read_csv(DATA_FILE)

df["timestamp"] = pd.to_datetime(df["timestamp"])

print("=" * 60)
print("LOADED DATA")
print("=" * 60)

print("Shape:", df.shape)

print("\nColumns:")
print(df.columns.tolist())


# ============================================================
# 2. TFT CONFIGURATION
# ============================================================

# Your data arrives every 5 seconds.
#
# 24 observations × 5 seconds = 120 seconds = 2 minutes
MAX_ENCODER_LENGTH = 24

# 6 observations × 5 seconds = 30 seconds
MAX_PREDICTION_LENGTH = 6

# Target we want to predict
TARGET = "psi_some_avg10"


# ============================================================
# 3. CREATE TFT DATASET
# ============================================================

tft_dataset = TimeSeriesDataSet(

    df,

    # Sequential time index
    time_idx="time_idx",

    # What TFT should predict
    target=TARGET,

    # Treat each continuous segment as a separate series
    group_ids=["segment_id"],

    # How much historical information TFT sees
    max_encoder_length=MAX_ENCODER_LENGTH,

    # How far into the future TFT predicts
    max_prediction_length=MAX_PREDICTION_LENGTH,

    # Variables whose future values are known
    time_varying_known_reals=[
        "time_idx",
    ],

    # Variables whose future values are unknown
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
# 4. DISPLAY INFORMATION
# ============================================================

print("\n" + "=" * 60)
print("TFT DATASET CREATED")
print("=" * 60)

print("\nNumber of samples:")
print(len(tft_dataset))

print("\nTFT dataset:")
print(tft_dataset)


# ============================================================
# 5. CREATE DATALOADER
# ============================================================

train_dataloader = tft_dataset.to_dataloader(
    train=True,
    batch_size=32,
    num_workers=0,
)

print("\n" + "=" * 60)
print("DATALOADER CREATED")
print("=" * 60)

# Test that a batch can actually be loaded
batch = next(iter(train_dataloader))

print("\nSuccessfully loaded one batch.")

print("\nBatch type:")
print(type(batch))
