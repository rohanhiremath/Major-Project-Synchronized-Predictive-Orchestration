import pandas as pd

from pytorch_forecasting import TimeSeriesDataSet


# ============================================================
# CONFIGURATION
# ============================================================

TRAIN_FILE = "data/train.csv"
VAL_FILE = "data/validation.csv"
TEST_FILE = "data/test.csv"

TARGET = "psi_some_avg10"

MAX_ENCODER_LENGTH = 24
MAX_PREDICTION_LENGTH = 6


# ============================================================
# 1. LOAD THE DATA
# ============================================================

train_df = pd.read_csv(TRAIN_FILE)
val_df = pd.read_csv(VAL_FILE)
test_df = pd.read_csv(TEST_FILE)

# Convert timestamps
train_df["timestamp"] = pd.to_datetime(train_df["timestamp"])
val_df["timestamp"] = pd.to_datetime(val_df["timestamp"])
test_df["timestamp"] = pd.to_datetime(test_df["timestamp"])


print("=" * 60)
print("DATA LOADED")
print("=" * 60)

print("Training:", train_df.shape)
print("Validation:", val_df.shape)
print("Test:", test_df.shape)


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


print("\n" + "=" * 60)
print("TRAINING DATASET")
print("=" * 60)

print(training_dataset)

print("\nTraining samples:")
print(len(training_dataset))


# ============================================================
# 3. CREATE TRAINING DATALOADER
# ============================================================

train_dataloader = training_dataset.to_dataloader(
    train=True,
    batch_size=32,
    num_workers=0,
)

print("\nTraining DataLoader created.")


# ============================================================
# 4. CREATE VALIDATION DATASET
# ============================================================

# Combine training + validation.
#
# Why?
#
# Validation predictions need historical observations
# from the end of the training period.

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


print("\n" + "=" * 60)
print("VALIDATION DATASET")
print("=" * 60)

print(validation_dataset)

print("\nValidation samples:")
print(len(validation_dataset))


# ============================================================
# 5. CREATE VALIDATION DATALOADER
# ============================================================

val_dataloader = validation_dataset.to_dataloader(
    train=False,
    batch_size=32,
    num_workers=0,
)

print("\nValidation DataLoader created.")


# ============================================================
# 6. CREATE TEST DATASET
# ============================================================

# Combine training + validation + test.
#
# This gives the test examples the historical context
# they need.

train_val_test_df = pd.concat(
    [train_df, val_df, test_df],
    ignore_index=True
)

train_val_test_df = train_val_test_df.sort_values(
    ["segment_id", "time_idx"]
).reset_index(drop=True)


test_dataset = TimeSeriesDataSet.from_dataset(
    training_dataset,
    train_val_test_df,
    predict=True,
    stop_randomization=True,
)


print("\n" + "=" * 60)
print("TEST DATASET")
print("=" * 60)

print(test_dataset)

print("\nTest samples:")
print(len(test_dataset))


# ============================================================
# 7. CREATE TEST DATALOADER
# ============================================================

test_dataloader = test_dataset.to_dataloader(
    train=False,
    batch_size=32,
    num_workers=0,
)

print("\nTest DataLoader created.")


# ============================================================
# 8. TEST ALL DATALOADERS
# ============================================================

print("\n" + "=" * 60)
print("TESTING DATALOADERS")
print("=" * 60)

train_batch = next(iter(train_dataloader))
val_batch = next(iter(val_dataloader))
test_batch = next(iter(test_dataloader))

print("\nTraining batch loaded successfully.")
print("Validation batch loaded successfully.")
print("Test batch loaded successfully.")

print("\n" + "=" * 60)
print("SUCCESS")
print("=" * 60)
