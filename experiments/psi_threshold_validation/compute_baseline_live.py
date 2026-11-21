#!/usr/bin/env python3
"""
Compute Baseline B from Live Calibration Calm Sessions

Frozen rule: B = median(p99_latency_ms) where pod_psi_some_avg10 == 0.0
"""

import sys
from pathlib import Path
import json

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SESSIONS_DIR = PROJECT_ROOT / "experiments" / "psi_threshold_validation" / "session_logs"

print("=" * 80)
print("COMPUTE BASELINE B (LIVE CALM SESSIONS)")
print("=" * 80)
print()

# Load calibration calm sessions
cal_calm_sessions = ["cal_calm_1", "cal_calm_2", "cal_calm_3"]

all_calm_data = []

for session_name in cal_calm_sessions:
    session_dir = SESSIONS_DIR / session_name
    metrics_file = session_dir / "metrics.csv"
    
    if not metrics_file.exists():
        print(f"ERROR: {metrics_file} not found")
        sys.exit(1)
    
    df = pd.read_csv(metrics_file)
    all_calm_data.append(df)
    print(f"Loaded {session_name}: {len(df)} rows")

calm_df = pd.concat(all_calm_data, ignore_index=True)
print()
print(f"Total calm data: {len(calm_df):,} rows")
print()

# Filter to rows where pod_psi_some_avg10 == 0.0 (true calm)
calm_psi_mask = calm_df['pod_psi_some_avg10'] == 0.0
calm_psi_df = calm_df[calm_psi_mask]

print(f"Rows where pod_psi_some_avg10 == 0.0: {len(calm_psi_df):,}")
print()

# Compute baseline B
latency_calm = calm_psi_df['p99_latency_ms'].values

B = np.median(latency_calm)

print(f"Baseline B (median p99_latency_ms in true calm): {B:.2f} ms")
print()
print(f"Latency statistics (true calm rows):")
print(f"  Min: {latency_calm.min():.2f} ms")
print(f"  p25: {np.percentile(latency_calm, 25):.2f} ms")
print(f"  p50: {np.percentile(latency_calm, 50):.2f} ms")
print(f"  p75: {np.percentile(latency_calm, 75):.2f} ms")
print(f"  p95: {np.percentile(latency_calm, 95):.2f} ms")
print(f"  Max: {latency_calm.max():.2f} ms")
print(f"  Std: {latency_calm.std():.2f} ms")
print()

# Threshold
THRESHOLD = 2.0 * B

print(f"Degradation threshold (2*B): {THRESHOLD:.2f} ms")
print()

# Save baseline
baseline_data = {
    'B_ms': B,
    'threshold_2B_ms': THRESHOLD,
    'calm_bins': len(calm_psi_df),
    'calm_sessions': cal_calm_sessions,
    'latency_stats': {
        'min': float(latency_calm.min()),
        'p25': float(np.percentile(latency_calm, 25)),
        'p50': float(np.percentile(latency_calm, 50)),
        'p75': float(np.percentile(latency_calm, 75)),
        'p95': float(np.percentile(latency_calm, 95)),
        'max': float(latency_calm.max()),
        'std': float(latency_calm.std()),
    }
}

with open(PROJECT_ROOT / "experiments" / "psi_threshold_validation" / "baseline_live.json", "w") as f:
    json.dump(baseline_data, f, indent=2)

print("Baseline saved to baseline_live.json")
print()
print("=" * 80)
