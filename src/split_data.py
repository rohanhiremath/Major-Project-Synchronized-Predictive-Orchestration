from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_FILE = PROJECT_ROOT / "data" / "processed_server_telemetry.csv"

TRAIN_FILE = PROJECT_ROOT / "data" / "train.csv"
VAL_FILE = PROJECT_ROOT / "data" / "validation.csv"
TEST_FILE = PROJECT_ROOT / "data" / "test.csv"

df = pd.read_csv(INPUT_FILE)

df["timestamp"] = pd.to_datetime(df["timestamp"])

# Make sure data is sorted
df = df.sort_values(
    ["series_id", "time_idx"]
).reset_index(drop=True)


# ============================================================
# Split EACH continuous segment chronologically
# ============================================================

train_parts = []
val_parts = []
test_parts = []

for series_id, segment in df.groupby("series_id"):

    n = len(segment)

    # 70 / 15 / 15 split
    train_end = int(n * 0.80)
    val_end = int(n * 0.90)

    train = segment.iloc[:train_end]
    val = segment.iloc[train_end:val_end]
    test = segment.iloc[val_end:]

    train_parts.append(train)
    val_parts.append(val)
    test_parts.append(test)

    print("=" * 60)
    print(f"SERIES {series_id}")
    print("=" * 60)

    print(f"Total:      {len(segment)}")
    print(f"Train:      {len(train)}")
    print(f"Validation: {len(val)}")
    print(f"Test:       {len(test)}")

    print("\nTrain:")
    print(train["timestamp"].min(), "->", train["timestamp"].max())

    print("\nValidation:")
    print(val["timestamp"].min(), "->", val["timestamp"].max())

    print("\nTest:")
    print(test["timestamp"].min(), "->", test["timestamp"].max())


# Combine segments back together

train_df = pd.concat(train_parts).reset_index(drop=True)
val_df = pd.concat(val_parts).reset_index(drop=True)
test_df = pd.concat(test_parts).reset_index(drop=True)


# ============================================================
# Save
# ============================================================

train_df.to_csv(TRAIN_FILE, index=False)
val_df.to_csv(VAL_FILE, index=False)
test_df.to_csv(TEST_FILE, index=False)


print("\n" + "=" * 60)
print("FINAL SPLIT")
print("=" * 60)

print("\nTraining rows:", len(train_df))
print("Validation rows:", len(val_df))
print("Test rows:", len(test_df))

print("\nSaved:")
print(TRAIN_FILE)
print(VAL_FILE)
print(TEST_FILE)
