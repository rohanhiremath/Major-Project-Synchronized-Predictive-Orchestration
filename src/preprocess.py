import pandas as pd

INPUT_FILE = "data/ptcs_training_data_full_psi.csv"
OUTPUT_FILE = "data/processed_ptcs.csv"

# Load dataset
df = pd.read_csv(INPUT_FILE)

# Convert timestamp
df["timestamp"] = pd.to_datetime(df["timestamp"])

# Sort chronologically
df = df.sort_values("timestamp").reset_index(drop=True)

# Calculate time difference
df["time_diff_seconds"] = (
    df["timestamp"].diff().dt.total_seconds()
)

# A normal observation is every 5 seconds.
# A gap larger than 5 seconds starts a new segment.
df["segment_id"] = (
    df["time_diff_seconds"].fillna(5) > 5
).cumsum()

# Create time index inside each segment
df["time_idx"] = df.groupby("segment_id").cumcount()

# Remove temporary column
df = df.drop(columns=["time_diff_seconds"])

# Display information
print("=" * 60)
print("PROCESSED DATASET")
print("=" * 60)

print("\nShape:", df.shape)

print("\nSegments:")

for segment_id, group in df.groupby("segment_id"):
    print(
        f"Segment {segment_id}: "
        f"{group['timestamp'].min()} -> "
        f"{group['timestamp'].max()} "
        f"({len(group)} rows)"
    )

# Save
df.to_csv(OUTPUT_FILE, index=False)

print("\nSaved to:")
print(OUTPUT_FILE)
