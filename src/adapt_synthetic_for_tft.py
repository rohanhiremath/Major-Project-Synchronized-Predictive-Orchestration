#!/usr/bin/env python3
"""
Adapt synthetic PSI data to match the format expected by existing TFT train/predict scripts.

Maps:
- psi_io_some_avg10 → psi_some_avg10
- psi_io_some_avg60 → psi_some_avg60
- psi_io_some_avg300 → psi_some_avg300
- psi_io_full_avg10 → psi_full_avg10
- psi_io_full_avg60 → psi_full_avg60
- psi_io_full_avg300 → psi_full_avg300
- node_id → series_id
- disk_iops → request_rate
- disk_queue_depth → active_connections
- io_wait_pct → cpu_usage (use as proxy)
- p95_latency_ms → latency_ms
- (others as constants or derived)

Output: data/train.csv, data/validation.csv, data/test.csv in TFT-compatible format
"""

from pathlib import Path

import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SYNTHETIC_DIR = PROJECT_ROOT / "data" / "synthetic"
DATA_DIR = PROJECT_ROOT / "data"

SYNTHETIC_TRAIN = SYNTHETIC_DIR / "train.csv"
SYNTHETIC_VAL = SYNTHETIC_DIR / "val.csv"
SYNTHETIC_TEST = SYNTHETIC_DIR / "test.csv"

OUTPUT_TRAIN = DATA_DIR / "train.csv"
OUTPUT_VAL = DATA_DIR / "validation.csv"
OUTPUT_TEST = DATA_DIR / "test.csv"


def adapt_dataframe(df):
    """Rename and map columns to TFT-expected format."""
    df = df.copy()
    
    # Map PSI columns
    df["psi_some_avg10"] = df["psi_io_some_avg10"]
    df["psi_some_avg60"] = df["psi_io_some_avg60"]
    df["psi_some_avg300"] = df["psi_io_some_avg300"]
    df["psi_full_avg10"] = df["psi_io_full_avg10"]
    df["psi_full_avg60"] = df["psi_io_full_avg60"]
    df["psi_full_avg300"] = df["psi_io_full_avg300"]
    
    # Map node to series_id
    df["series_id"] = df["node_id"]
    
    # Map I/O metrics to expected names
    df["request_rate"] = df["disk_iops"]
    df["active_connections"] = df["disk_queue_depth"]
    df["cpu_usage"] = df["io_wait_pct"] / 100.0  # Normalize to 0-1
    df["memory_usage"] = 2.0e9  # Constant 2GB
    df["read_bytes_per_sec"] = df["disk_iops"] * 4096.0  # Assume 4KB per I/O
    df["write_bytes_per_sec"] = df["disk_iops"] * 4096.0
    df["latency_ms"] = df["p95_latency_ms"]
    df["error_rate"] = 0.001  # Constant low error rate
    
    # Keep hour_sin and hour_cos, add if missing
    if "hour_sin" not in df.columns:
        df["hour_sin"] = np.sin(2 * np.pi * df["hour_of_day"] / 24)
    if "hour_cos" not in df.columns:
        df["hour_cos"] = np.cos(2 * np.pi * df["hour_of_day"] / 24)
    
    # Select final columns in expected order
    final_columns = [
        "timestamp",
        "series_id",
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
        "time_idx",
        "hour_sin",
        "hour_cos",
    ]
    
    return df[final_columns]


def main():
    print("=" * 80)
    print("ADAPTING SYNTHETIC DATA FOR TFT COMPATIBILITY")
    print("=" * 80)
    
    # Load synthetic data
    print("\nLoading synthetic data...")
    train_df = pd.read_csv(SYNTHETIC_TRAIN)
    val_df = pd.read_csv(SYNTHETIC_VAL)
    test_df = pd.read_csv(SYNTHETIC_TEST)
    
    print(f"  Train: {len(train_df)} rows")
    print(f"  Val:   {len(val_df)} rows")
    print(f"  Test:  {len(test_df)} rows")
    
    # Adapt each split
    print("\nAdapting columns...")
    train_adapted = adapt_dataframe(train_df)
    val_adapted = adapt_dataframe(val_df)
    test_adapted = adapt_dataframe(test_df)
    
    # Save to standard data directory
    print(f"\nSaving adapted data to {DATA_DIR}...")
    train_adapted.to_csv(OUTPUT_TRAIN, index=False)
    val_adapted.to_csv(OUTPUT_VAL, index=False)
    test_adapted.to_csv(OUTPUT_TEST, index=False)
    
    print(f"  ✓ {OUTPUT_TRAIN}")
    print(f"  ✓ {OUTPUT_VAL}")
    print(f"  ✓ {OUTPUT_TEST}")
    
    print("\n" + "=" * 80)
    print("ADAPTATION COMPLETE")
    print("=" * 80)
    print("\nYou can now run:")
    print("  python3 src/train_tft.py")
    print("  python3 src/predict_tft.py")


if __name__ == "__main__":
    main()
