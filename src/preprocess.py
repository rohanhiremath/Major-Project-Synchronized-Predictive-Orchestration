from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_FILE = PROJECT_ROOT / "data" / "server_telemetry_1day_20s.csv"
OUTPUT_FILE = PROJECT_ROOT / "data" / "processed_server_telemetry.csv"

# Load dataset
df = pd.read_csv(INPUT_FILE)

# Convert timestamp
df["timestamp"] = pd.to_datetime(df["timestamp"])

# Sort chronologically
df = df.sort_values(["server_id", "timestamp"]).reset_index(drop=True)

# Calculate time difference
df["time_diff_seconds"] = df.groupby("server_id")["timestamp"].diff().dt.total_seconds()

# A normal observation is every 5 seconds.
# A gap larger than 5 seconds starts a new segment.
df["segment_id"] = (
    df["time_diff_seconds"].fillna(20) > 20
).groupby(df["server_id"]).cumsum()
df["series_id"] = df["server_id"] + "_segment_" + df["segment_id"].astype(str)

# Create time index inside each segment
df["time_idx"] = df.groupby("series_id").cumcount()

# Calendar features are known in advance and can help anticipate recurring
# traffic patterns without exposing future server measurements.
seconds_since_midnight = (
    df["timestamp"].dt.hour * 3600
    + df["timestamp"].dt.minute * 60
    + df["timestamp"].dt.second
)
df["hour_sin"] = np.sin(2 * np.pi * seconds_since_midnight / 86400)
df["hour_cos"] = np.cos(2 * np.pi * seconds_since_midnight / 86400)

# Remove temporary column
df = df.drop(columns=["time_diff_seconds"])

# Display information
print("=" * 60)
print("PROCESSED DATASET")
print("=" * 60)

print("\nShape:", df.shape)

print("\nSegments:")

for series_id, group in df.groupby("series_id"):
    print(
        f"Series {series_id}: "
        f"{group['timestamp'].min()} -> "
        f"{group['timestamp'].max()} "
        f"({len(group)} rows)"
    )

# Save
df.to_csv(OUTPUT_FILE, index=False)

print("\nSaved to:")
print(OUTPUT_FILE)
