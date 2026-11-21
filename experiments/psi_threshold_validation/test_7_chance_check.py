#!/usr/bin/env python3
"""
Test 7: Chance Check

Shuffles breach labels 1000 times within each session.
Re-runs analysis on shuffled labels.
Reports: how often shuffled recall >= observed recall (should be rare).

This verifies that observed results are not due to chance.
"""

import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

print("=" * 80)
print("TEST 7: CHANCE CHECK (Shuffled Labels)")
print("=" * 80)
print()

# Load test data
test_df = pd.read_csv(DATA_DIR / "test.csv")
val_df = pd.read_csv(DATA_DIR / "validation.csv")
test_combined = pd.concat([test_df, val_df], ignore_index=True)

print(f"[STEP 1] Prepare test data")
print("-" * 80)
print(f"Test data: {len(test_combined):,} rows")
print()

# Compute breach label (frozen rule)
B = 60.34
THRESHOLD = 2 * B

latency = test_combined['latency_ms'].values
above_threshold = (latency > THRESHOLD).astype(int)

breach_label = np.zeros(len(above_threshold), dtype=int)
for i in range(len(above_threshold) - 1):
    if above_threshold[i] == 1 and above_threshold[i+1] == 1:
        breach_label[i] = 1
        breach_label[i+1] = 1

test_combined['breach_label'] = breach_label

signal = test_combined['psi_some_avg10'].values
calm_mask = signal == 0.0

breach_count = breach_label.sum()
print(f"Original breach events: {breach_count}")
print()

# Observed recall at selected threshold (from Test 6)
T_selected = 0.5
k_selected = 1

above_T = (signal > T_selected).astype(int)
alert_bins = np.zeros(len(above_T), dtype=int)
for i in range(len(above_T) - (k_selected - 1)):
    if np.sum(above_T[i:i+k_selected]) == k_selected:
        alert_bins[i:i+k_selected] = 1

tp_observed = np.sum(alert_bins & breach_label)
recall_observed = tp_observed / breach_count if breach_count > 0 else 0.0

print(f"Observed recall at T={T_selected}% k={k_selected}: {recall_observed:.6f}")
print()

# Shuffle test
print(f"[STEP 2] Run 1000 shuffled label trials")
print("-" * 80)
print()

np.random.seed(42)
shuffled_recalls = []

for trial in range(1000):
    # Shuffle labels
    shuffled_label = np.random.permutation(breach_label)
    
    # Compute recall on shuffled labels with same threshold
    tp_shuffled = np.sum(alert_bins & shuffled_label)
    recall_shuffled = tp_shuffled / breach_count if breach_count > 0 else 0.0
    shuffled_recalls.append(recall_shuffled)
    
    if (trial + 1) % 200 == 0:
        print(f"  Completed {trial + 1} trials...")

print()

shuffled_recalls = np.array(shuffled_recalls)

print(f"[STEP 3] Analyze shuffled distribution")
print("-" * 80)
print()

print(f"Shuffled recall statistics (1000 trials):")
print(f"  Mean: {shuffled_recalls.mean():.6f}")
print(f"  Std: {shuffled_recalls.std():.6f}")
print(f"  Min: {shuffled_recalls.min():.6f}")
print(f"  p5: {np.percentile(shuffled_recalls, 5):.6f}")
print(f"  p50: {np.percentile(shuffled_recalls, 50):.6f}")
print(f"  p95: {np.percentile(shuffled_recalls, 95):.6f}")
print(f"  Max: {shuffled_recalls.max():.6f}")
print()

# Count how often shuffled >= observed
count_beat_observed = np.sum(shuffled_recalls >= recall_observed)
pct_beat_observed = 100 * count_beat_observed / len(shuffled_recalls)

print(f"Chance check result:")
print(f"  Observed recall: {recall_observed:.6f}")
print(f"  Shuffled trials matching or beating observed: {count_beat_observed} / {len(shuffled_recalls)} ({pct_beat_observed:.1f}%)")
print()

# Interpretation
print(f"[STEP 4] Interpretation")
print("-" * 80)
print()

if pct_beat_observed <= 5:
    print("✓ PASS: Observed recall is significantly better than chance.")
    print(f"  Only {pct_beat_observed:.1f}% of shuffled labels achieve recall >= {recall_observed:.6f}.")
    print("  This is statistically significant (p < 0.05).")
    chance_decision = "PASS"
else:
    print("✗ FAIL: Observed recall is not significantly different from chance.")
    print(f"  {pct_beat_observed:.1f}% of shuffled labels achieve recall >= {recall_observed:.6f}.")
    print("  This suggests the result could be due to random variation.")
    chance_decision = "FAIL"

print()

# Additional analysis: per-series shuffle
print(f"[STEP 5] Per-series shuffle check")
print("-" * 80)

# Group by series_id and shuffle within each series
series_ids = test_combined['series_id'].unique()
print(f"Number of series: {len(series_ids)}")
print()

per_series_recalls = []

for trial in range(100):
    shuffled_label_per_series = np.zeros_like(breach_label)
    
    for series_id in series_ids:
        series_mask = test_combined['series_id'] == series_id
        series_indices = np.where(series_mask)[0]
        
        if len(series_indices) > 0:
            series_labels = breach_label[series_indices]
            shuffled_series_labels = np.random.permutation(series_labels)
            shuffled_label_per_series[series_indices] = shuffled_series_labels
    
    tp_shuffled = np.sum(alert_bins & shuffled_label_per_series)
    recall_shuffled = tp_shuffled / breach_count if breach_count > 0 else 0.0
    per_series_recalls.append(recall_shuffled)

per_series_recalls = np.array(per_series_recalls)

print(f"Per-series shuffled recall statistics (100 trials):")
print(f"  Mean: {per_series_recalls.mean():.6f}")
print(f"  Std: {per_series_recalls.std():.6f}")
print()

count_beat_per_series = np.sum(per_series_recalls >= recall_observed)
pct_beat_per_series = 100 * count_beat_per_series / len(per_series_recalls)

print(f"Per-series chance (100 trials): {count_beat_per_series}/100 ({pct_beat_per_series:.1f}%) beat observed")
print()

# Save results
output = {
    'observed_recall': recall_observed,
    'shuffled_recalls_mean': shuffled_recalls.mean(),
    'shuffled_recalls_std': shuffled_recalls.std(),
    'count_beat_observed': int(count_beat_observed),
    'pct_beat_observed': pct_beat_observed,
    'chance_check_decision': chance_decision,
    'per_series_mean': per_series_recalls.mean(),
    'per_series_pct_beat': pct_beat_per_series,
}

with open(DATA_DIR.parent / "test_7_results.json", "w") as f:
    json.dump(output, f, indent=2)

print()
print("=" * 80)
print("TEST 7 SUMMARY")
print("=" * 80)
print()
print(f"Chance check result: {chance_decision}")
print(f"  Observed recall: {recall_observed:.6f}")
print(f"  Shuffled mean: {shuffled_recalls.mean():.6f}")
print(f"  P-value (one-sided): {pct_beat_observed/100:.4f}")
print()
print("Conclusion: Observed result is statistically significant." if chance_decision == "PASS" else "Conclusion: Result could be due to chance.")
print()
print("Test 7 results saved to test_7_results.json")
print()
print("=" * 80)
