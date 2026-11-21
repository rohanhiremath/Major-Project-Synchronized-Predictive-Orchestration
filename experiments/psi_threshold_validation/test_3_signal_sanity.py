#!/usr/bin/env python3
"""
Test 3: Signal Sanity

Evaluates signal quality:
1. AUC on breach label (per-bin classification)
2. Signal distribution (calm vs stress)
3. Shuffled AUC (baseline for independence)
4. Conclusion: pass or fail based on shuffled AUC

Frozen parameters (PREREG_FROZEN.yaml):
  - Signal: psi_some_avg10 (Prometheus deriv)
  - Label: breach = latency > 120.68 ms for 2+ consecutive bins
  - Baseline B: 60.34 ms
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, roc_curve
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

print("=" * 80)
print("TEST 3: SIGNAL SANITY CHECK")
print("=" * 80)
print()

# Load training data (calibration only, per pre-reg)
train_df = pd.read_csv(DATA_DIR / "train.csv")

# Exclude pilot data (rows 0-59)
PILOT_ROWS = 60
cal_df = train_df.iloc[PILOT_ROWS:].copy()

print(f"[STEP 1] Load calibration data")
print("-" * 80)
print(f"Calibration data: {len(cal_df):,} rows from train.csv (excluding pilot {PILOT_ROWS} rows)")
print()

# Step 2: Compute breach label (from Test 1 frozen rule)
B = 60.34
THRESHOLD = 2 * B

print(f"[STEP 2] Compute breach label")
print("-" * 80)
print(f"Frozen rule: latency > {THRESHOLD:.2f} ms for 2+ consecutive bins")
print()

latency = cal_df['latency_ms'].values
above_threshold = (latency > THRESHOLD).astype(int)

# Mark bins that are part of breach events (2+ consecutive)
breach_label = np.zeros(len(above_threshold), dtype=int)
for i in range(len(above_threshold) - 1):
    if above_threshold[i] == 1 and above_threshold[i+1] == 1:
        breach_label[i] = 1
        breach_label[i+1] = 1

cal_df['breach_label'] = breach_label

breach_count = breach_label.sum()
breach_pct = 100 * breach_count / len(breach_label)

print(f"Breach events: {breach_count:,} rows ({breach_pct:.1f}%)")
print(f"Non-breach: {len(breach_label) - breach_count:,} rows ({100-breach_pct:.1f}%)")
print()

# Step 3: Extract signal
print(f"[STEP 3] Extract signal")
print("-" * 80)

signal = cal_df['psi_some_avg10'].values

print(f"Signal (psi_some_avg10) statistics:")
print(f"  Min: {signal.min():.6f}%")
print(f"  p50: {np.median(signal):.6f}%")
print(f"  p90: {np.percentile(signal, 90):.6f}%")
print(f"  p95: {np.percentile(signal, 95):.6f}%")
print(f"  p99: {np.percentile(signal, 99):.6f}%")
print(f"  Max: {signal.max():.6f}%")
print()

# Separate calm and stress
calm_mask = signal == 0.0
stress_mask = signal > 0.0

calm_signal = signal[calm_mask]
calm_label = breach_label[calm_mask]
stress_signal = signal[stress_mask]
stress_label = breach_label[stress_mask]

print(f"Calm bins (signal == 0.0): {len(calm_signal):,} ({100*len(calm_signal)/len(signal):.1f}%)")
print(f"  Breach events in calm: {calm_label.sum()}")
print(f"  False alarms in calm: {(1 - calm_label).sum()}")
print()

print(f"Stress bins (signal > 0.0): {len(stress_signal):,} ({100*len(stress_signal)/len(signal):.1f}%)")
print(f"  Breach events in stress: {stress_label.sum()}")
print(f"  Non-breach in stress: {(1 - stress_label).sum()}")
print()

# Step 4: Compute AUC
print(f"[STEP 4] Compute AUC")
print("-" * 80)

try:
    auc = roc_auc_score(breach_label, signal)
    print(f"AUC (signal vs breach label): {auc:.6f}")
    print()
except Exception as e:
    print(f"AUC computation error: {e}")
    auc = np.nan

# Get ROC curve points
fpr, tpr, thresholds = roc_curve(breach_label, signal)
print(f"ROC curve: {len(fpr)} points")
print(f"  FPR range: {fpr.min():.6f} to {fpr.max():.6f}")
print(f"  TPR range: {tpr.min():.6f} to {tpr.max():.6f}")
print()

# Step 5: Compute shuffled AUC baseline
print(f"[STEP 5] Compute shuffled AUC (baseline)")
print("-" * 80)
print("Shuffling breach labels 1000 times within calibration data...")
print()

np.random.seed(42)
shuffled_aucs = []

for i in range(1000):
    shuffled_label = np.random.permutation(breach_label)
    try:
        shuffled_auc = roc_auc_score(shuffled_label, signal)
        shuffled_aucs.append(shuffled_auc)
    except:
        pass

shuffled_aucs = np.array(shuffled_aucs)

print(f"Shuffled AUC statistics (1000 resamples):")
print(f"  Mean: {shuffled_aucs.mean():.6f}")
print(f"  Std: {shuffled_aucs.std():.6f}")
print(f"  p5: {np.percentile(shuffled_aucs, 5):.6f}")
print(f"  p50: {np.percentile(shuffled_aucs, 50):.6f}")
print(f"  p95: {np.percentile(shuffled_aucs, 95):.6f}")
print()

if not np.isnan(auc):
    zscore = (auc - shuffled_aucs.mean()) / (shuffled_aucs.std() + 1e-9)
    print(f"Observed AUC vs shuffled mean: {auc:.6f} vs {shuffled_aucs.mean():.6f}")
    print(f"Z-score: {zscore:.2f} sigma")
    print()

# Step 6: Decision
print(f"[STEP 6] Sanity Check Decision")
print("-" * 80)
print()

if np.isnan(auc):
    print("✗ FAIL: AUC computation failed")
    decision = "FAIL"
elif shuffled_aucs.mean() > 0.55:
    print("✗ FAIL: Shuffled AUC > 0.55 (suggests data issue)")
    print(f"  Shuffled mean: {shuffled_aucs.mean():.6f}")
    decision = "FAIL"
elif auc < 0.55:
    print("✗ FAIL: AUC < 0.55 (signal has no discriminative power)")
    print(f"  AUC: {auc:.6f}")
    decision = "FAIL"
elif auc > 0.99 and shuffled_aucs.mean() < 0.55:
    print("⚠️  WARNING: AUC nearly perfect (likely co-generation artifact)")
    print(f"  AUC: {auc:.6f}")
    print(f"  Shuffled mean: {shuffled_aucs.mean():.6f}")
    print()
    print("  This suggests signal and label share a common source (expected for synthetic data).")
    print("  Results will be marked EXPLORATORY_ONLY per pre-registration.")
    print()
    decision = "PASS (with co-generation artifact detected)"
else:
    print(f"✓ PASS: AUC = {auc:.6f}, shuffled mean = {shuffled_aucs.mean():.6f}")
    decision = "PASS"

print()
print(f"TEST 3 DECISION: {decision}")
print()

# Step 7: Summary
print(f"[STEP 7] Summary")
print("-" * 80)
print()
print("SIGNAL SANITY CHECK RESULTS:")
print(f"  AUC (observed): {auc:.6f}")
print(f"  AUC (shuffled mean): {shuffled_aucs.mean():.6f}")
print(f"  Difference: {auc - shuffled_aucs.mean():.6f}")
print()
print(f"Signal distribution:")
print(f"  Calm bins: {len(calm_signal):,} (all signal == 0.0)")
print(f"  Stress bins: {len(stress_signal):,} (signal > 0.0)")
print()
print(f"Label distribution:")
print(f"  Breach events: {breach_count:,}")
print(f"  Non-breach: {len(breach_label) - breach_count:,}")
print()
print(f"STATUS: {decision}")
print()
print("=" * 80)

# Save results
test_3_results = {
    'auc': auc,
    'shuffled_auc_mean': shuffled_aucs.mean(),
    'shuffled_auc_std': shuffled_aucs.std(),
    'decision': decision,
    'calm_bins': len(calm_signal),
    'stress_bins': len(stress_signal),
    'breach_events': int(breach_count),
}

import json
with open(DATA_DIR.parent / "test_3_results.json", "w") as f:
    json.dump(test_3_results, f, indent=2)

print("Test 3 results saved to test_3_results.json")
