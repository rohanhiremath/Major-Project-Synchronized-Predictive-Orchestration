#!/usr/bin/env python3
"""
Prepare synthetic PSI data for use with existing predict_tft.py script.
Maps synthetic column names to expected names without modifying predict_tft.py.
"""

from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SYNTHETIC_DIR = DATA_DIR / "synthetic"

# Column mapping: synthetic_name -> expected_name
COLUMN_MAPPING = {
    "psi_io_some_avg10": "psi_some_avg10",
    "psi_io_some_avg60": "psi_some_avg60",
    "psi_io_some_avg300": "psi_some_avg300",
    "psi_io_full_avg10": "psi_full_avg10",
    "psi_io_full_avg60": "psi_full_avg60",
    "psi_io_full_avg300": "psi_full_avg300",
    "node_id": "series_id",
    "disk_iops": "request_rate",
    "disk_queue_depth": "active_connections",
    "io_wait_pct": "cpu_usage",
    "cpu_util_pct": "memory_usage",
    "p95_latency_ms": "read_bytes_per_sec",
    "is_business_hours": "write_bytes_per_sec",
    "is_maintenance_window": "latency_ms",
}

def prepare_synthetic_data():
    """Convert synthetic data to format expected by predict_tft.py"""
    
    print("Preparing synthetic data for prediction...")
    
    # Load synthetic data
    train_df = pd.read_csv(SYNTHETIC_DIR / "train.csv")
    val_df = pd.read_csv(SYNTHETIC_DIR / "val.csv")
    test_df = pd.read_csv(SYNTHETIC_DIR / "test.csv")
    
    # Rename columns
    for df in [train_df, val_df, test_df]:
        for synthetic_col, expected_col in COLUMN_MAPPING.items():
            if synthetic_col in df.columns:
                df.rename(columns={synthetic_col: expected_col}, inplace=True)
    
    # Add missing columns with placeholder values
    missing_cols = [
        "request_rate", "active_connections", "cpu_usage", "memory_usage",
        "read_bytes_per_sec", "write_bytes_per_sec", "latency_ms", "error_rate"
    ]
    
    for df in [train_df, val_df, test_df]:
        for col in missing_cols:
            if col not in df.columns:
                df[col] = 0.0
        # Add hour_sin and hour_cos if not present
        if "hour_sin" not in df.columns:
            df["hour_sin"] = 0.0
        if "hour_cos" not in df.columns:
            df["hour_cos"] = 1.0
    
    # Save to data/ directory (where predict_tft.py looks)
    train_df.to_csv(DATA_DIR / "train.csv", index=False)
    val_df.to_csv(DATA_DIR / "validation.csv", index=False)
    test_df.to_csv(DATA_DIR / "test.csv", index=False)
    
    print(f"✓ Prepared train.csv ({len(train_df)} rows)")
    print(f"✓ Prepared validation.csv ({len(val_df)} rows)")
    print(f"✓ Prepared test.csv ({len(test_df)} rows)")
    print(f"\nData ready for predict_tft.py")

if __name__ == "__main__":
    prepare_synthetic_data()
