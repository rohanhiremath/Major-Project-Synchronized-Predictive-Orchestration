#!/usr/bin/env python3
"""
Delta PSI Threshold Validation: Calibration Sweep

Tests whether CHANGE IN PSI (delta PSI) predicts latency degradation.

Instead of: PSI value > 1.8%
We test: CHANGE IN PSI > 1.8% (i.e., PSI jumps up by 1.8% or more)

Frozen parameters (adapted for delta):
  - DELTA_GRID: [0.5, 1.0, 1.5, 1.8, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0]
  - k_values: [1, 3]  # consecutive bins above threshold
  - Selection: max recall s.t. FA/hr <= 2.0
"""

import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

print("=" * 80)
print("DELTA PSI: CALIBRATION SWEEP")
print("=" * 80)
print()

# Load calibration data
train_df = pd.read_csv(DATA_DIR / "train.csv")
PILOT_ROWS = 60
cal_df = train_df.iloc[PILOT_ROWS:].copy()

print(f"[STEP 1] Load and prepare calibration data")
print("-" * 80)
print(f"Calibration rows: {len(cal_df):,}")
print()

# Compute breach label (frozen rule from absolute validation)
B = 60.34
THRESHOLD = 2 * B

latency = cal_df['latency_ms'].values
above_threshold = (latency > THRESHOLD).astype(int)

breach_label = np.zeros(len(above_threshold), dtype=int)
for i in range(len(above_threshold) - 1):
    if above_threshold[i] == 1 and above_threshold[i+1] == 1:
        breach_label[i] = 1
        breach_label[i+1] = 1

cal_df['breach_label'] = breach_label

breach_count = breach_label.sum()
print(f"Breach events (label): {breach_count:,} rows")
print()

# Compute PSI and Delta PSI
signal = cal_df['psi_some_avg10'].values

# Delta PSI = change from previous bin
delta_psi = np.zeros(len(signal))
delta_psi[0] = 0  # First bin has no previous value
for i in range(1, len(signal)):
    delta_psi[i] = signal[i] - signal[i-1]

cal_df['delta_psi'] = delta_psi

print(f"PSI statistics:")
print(f"  Min: {signal.min():.4f}%")
print(f"  Max: {signal.max():.4f}%")
print(f"  Mean: {signal.mean():.4f}%")
print()

print(f"Delta PSI statistics:")
print(f"  Min: {delta_psi.min():.4f}%")
print(f"  Max: {delta_psi.max():.4f}%")
print(f"  Mean: {delta_psi.mean():.4f}%")
print(f"  Median: {np.median(delta_psi):.4f}%")
print()

# Compute calm hours (for FA/hr calculation)
calm_mask = signal == 0.0
calm_bins = calm_mask.sum()
calm_hours = calm_bins * 20 / 3600

print(f"Calm periods: {calm_bins:,} bins = {calm_hours:.2f} hours")
print()

# Frozen parameters for delta PSI
DELTA_GRID = [0.5, 1.0, 1.5, 1.8, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0]
K_VALUES = [1, 3]

print(f"[STEP 2] Sweep all (DELTA, k) pairs")
print("-" * 80)
print(f"DELTA_grid: {DELTA_GRID}")
print(f"k_values: {K_VALUES}")
print()

sweep_results = []

for DELTA in DELTA_GRID:
    for k in K_VALUES:
        # Find alerts: delta_psi > DELTA for k consecutive bins
        # Interpretation: PSI jumps up by more than DELTA% for k consecutive bins
        above_delta = (delta_psi > DELTA).astype(int)
        
        # Consecutive alerts (k consecutive bins)
        alert_bins = np.zeros(len(above_delta), dtype=int)
        for i in range(len(above_delta) - (k - 1)):
            if np.sum(above_delta[i:i+k]) == k:
                alert_bins[i:i+k] = 1
        
        # Compute metrics
        tp = np.sum(alert_bins & breach_label)
        fa_total = np.sum(alert_bins & calm_mask)
        
        # Recall
        if breach_count > 0:
            recall = tp / breach_count
        else:
            recall = 0.0
        
        # FA/hr
        fa_per_hour = fa_total / calm_hours if calm_hours > 0 else 0.0
        
        # Precision
        total_alerts = np.sum(alert_bins)
        precision = tp / total_alerts if total_alerts > 0 else 0.0
        
        sweep_results.append({
            'DELTA': DELTA,
            'k': k,
            'tp': int(tp),
            'fa_total': int(fa_total),
            'fa_per_hour': fa_per_hour,
            'recall': recall,
            'precision': precision,
            'alerts': int(total_alerts),
            'meets_recall_threshold': recall >= 0.5,
            'meets_fa_threshold': fa_per_hour <= 2.0,
            'viable': (recall >= 0.5) and (fa_per_hour <= 2.0)
        })

# Print sweep results
print("Sweep results (all DELTA, k pairs):")
print()
print("DELTA  k  Recall  FA/hr  Precision  Viable")
print("-" * 50)

for r in sweep_results:
    viable_str = "✓" if r['viable'] else "✗"
    print(f"{r['DELTA']:.1f}%  {r['k']}  {r['recall']:.4f}  {r['fa_per_hour']:.2f}   {r['precision']:.4f}      {viable_str}")

print()

# Find viable thresholds
viable_results = [r for r in sweep_results if r['viable']]

print(f"[STEP 3] Apply selection rule")
print("-" * 80)
print(f"Frozen rule: maximize recall subject to FA/hr <= 2.0")
print()
print(f"Viable (DELTA, k) pairs: {len(viable_results)}")
print()

if len(viable_results) > 0:
    # Sort by recall (descending), then by FA (ascending), then by DELTA (descending)
    viable_results_sorted = sorted(
        viable_results,
        key=lambda r: (-r['recall'], r['fa_per_hour'], -r['DELTA'])
    )
    
    selected = viable_results_sorted[0]
    
    print(f"✓ SELECTED: DELTA={selected['DELTA']}%, k={selected['k']}")
    print(f"  Recall: {selected['recall']:.4f}")
    print(f"  FA/hr: {selected['fa_per_hour']:.4f}")
    print(f"  Precision: {selected['precision']:.4f}")
    print(f"  True Positives: {selected['tp']}")
    print()
    
    # Show top 5 candidates
    print("Top 5 viable candidates:")
    for i, r in enumerate(viable_results_sorted[:5], 1):
        print(f"  {i}. DELTA={r['DELTA']}%, k={r['k']}: recall={r['recall']:.4f}, FA/hr={r['fa_per_hour']:.4f}")
    
    selection_status = "selected"
else:
    print("✗ NO VIABLE THRESHOLD FOUND")
    print()
    print("No (DELTA, k) pair satisfies both:")
    print("  - Recall >= 0.5")
    print("  - FA/hr <= 2.0")
    print()
    
    # Find closest candidates
    print("Closest candidates (sorted by recall, largest first):")
    recall_sorted = sorted(sweep_results, key=lambda r: -r['recall'])
    for r in recall_sorted[:3]:
        print(f"  DELTA={r['DELTA']}%, k={r['k']}: recall={r['recall']:.4f}, FA/hr={r['fa_per_hour']:.4f}")
    
    selected = None
    selection_status = "no_viable_threshold"

print()
print(f"[STEP 4] Summary")
print("-" * 80)
print()
print(f"STATUS: {selection_status.upper()}")
print()

if selected is not None:
    print(f"Selected delta PSI threshold (per pre-registration selection rule):")
    print(f"  DELTA* = {selected['DELTA']}%")
    print(f"  k* = {selected['k']}")
    print(f"  Recall = {selected['recall']:.6f}")
    print(f"  FA/hr = {selected['fa_per_hour']:.6f}")
else:
    print("No threshold selected. Analysis stops here.")

print()

# Save full sweep results
output = {
    'status': selection_status,
    'sweep_results': sweep_results,
    'viable_count': len(viable_results),
    'selected': selected,
    'data_type': 'delta_psi',
    'interpretation': 'DELTA > X% means PSI change (jump) exceeds X% in single or consecutive bins'
}

with open(DATA_DIR.parent / "test_delta_psi_calibration_results.json", "w") as f:
    json.dump(output, f, indent=2, default=str)

print("Delta PSI calibration results saved to test_delta_psi_calibration_results.json")
print()
print("=" * 80)
