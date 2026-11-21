#!/usr/bin/env python3
"""
Delta PSI Threshold Validation with SLO: Held-Out Test Evaluation

Evaluates selected DELTA* threshold on held-out test data using SLO criterion.
Applies frozen pass criteria and reports verdicts.

SLO Criterion: latency_ms > 200
Pass Criteria: Wilson 95% CI lower bound >= 0.60 AND FA/hr upper bound <= 2.0
"""

import sys
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

print("=" * 80)
print("DELTA PSI WITH SLO: HELD-OUT TEST EVALUATION")
print("=" * 80)
print()

# Load test data (held out, never used before)
test_df = pd.read_csv(DATA_DIR / "test.csv")
val_df = pd.read_csv(DATA_DIR / "validation.csv")
test_combined = pd.concat([test_df, val_df], ignore_index=True)

print(f"[STEP 1] Load held-out test data")
print("-" * 80)
print(f"Test data: {len(test_df):,} rows from test.csv")
print(f"Validation data: {len(val_df):,} rows from validation.csv")
print(f"Combined: {len(test_combined):,} rows")
print()

# Compute breach label using SLO (latency > 200ms)
SLO_THRESHOLD = 200.0

latency = test_combined['latency_ms'].values
above_slo = (latency > SLO_THRESHOLD).astype(int)

breach_label = np.zeros(len(above_slo), dtype=int)
for i in range(len(above_slo) - 1):
    if above_slo[i] == 1 and above_slo[i+1] == 1:
        breach_label[i] = 1
        breach_label[i+1] = 1

test_combined['breach_label'] = breach_label

breach_count = breach_label.sum()
signal = test_combined['psi_some_avg10'].values

# Compute delta PSI
delta_psi = np.zeros(len(signal))
delta_psi[0] = 0
for i in range(1, len(signal)):
    delta_psi[i] = signal[i] - signal[i-1]

test_combined['delta_psi'] = delta_psi

calm_mask = signal == 0.0
calm_bins = calm_mask.sum()
calm_hours = calm_bins * 20 / 3600

print(f"SLO Breach events (latency > {SLO_THRESHOLD}ms): {breach_count:,} rows")
print(f"Percentage of data: {100*breach_count/len(test_combined):.2f}%")
print(f"Calm periods: {calm_bins:,} bins = {calm_hours:.2f} hours")
print()

# Wilson CI function
def wilson_ci_lower(successes, n, confidence=0.95):
    """Compute Wilson score interval lower bound"""
    if n == 0:
        return 0.0
    
    z = 1.96  # 95% confidence
    p_hat = successes / n
    
    denominator = 1 + z**2 / n
    centre_adjusted = (p_hat + z**2 / (2*n)) / denominator
    adjustment = z * math.sqrt((p_hat * (1 - p_hat) + z**2 / (4*n)) / n) / denominator
    
    lower = centre_adjusted - adjustment
    return max(0, lower)

def wilson_ci_upper(successes, n, confidence=0.95):
    """Compute Wilson score interval upper bound"""
    if n == 0:
        return 1.0
    
    z = 1.96
    p_hat = successes / n
    
    denominator = 1 + z**2 / n
    centre_adjusted = (p_hat + z**2 / (2*n)) / denominator
    adjustment = z * math.sqrt((p_hat * (1 - p_hat) + z**2 / (4*n)) / n) / denominator
    
    upper = centre_adjusted + adjustment
    return min(1, upper)

# Load calibration results to get selected threshold
try:
    with open(DATA_DIR.parent / "test_delta_psi_calibration_slo_results.json", "r") as f:
        cal_results = json.load(f)
    
    if cal_results['selected'] is None:
        print("ERROR: No viable delta PSI threshold selected in calibration")
        print("       Analysis stops here.")
        sys.exit(1)
    
    selected_delta = cal_results['selected']['DELTA']
    selected_k = cal_results['selected']['k']
    
    print(f"[STEP 2] Load selected threshold from calibration")
    print("-" * 80)
    print(f"Selected: DELTA={selected_delta}%, k={selected_k}")
    print()
    
except FileNotFoundError:
    print("ERROR: test_delta_psi_calibration_slo_results.json not found")
    print("       Please run test_delta_psi_calibration_slo.py first")
    sys.exit(1)

# Test both the selected threshold and 1.8% for comparison
thresholds_to_test = [
    {'DELTA': selected_delta, 'k': selected_k, 'name': 'selected'},
    {'DELTA': 1.8, 'k': 1, 'name': 'project_configured_delta'}
]

results_all = {}

print(f"[STEP 3] Evaluate delta PSI thresholds on held-out test data")
print("-" * 80)
print()

for threshold_info in thresholds_to_test:
    DELTA = threshold_info['DELTA']
    k = threshold_info['k']
    name = threshold_info['name']
    
    print(f"Delta PSI Threshold: DELTA={DELTA}% k={k} ({name})")
    print(f"  Interpretation: Alert when PSI change > {DELTA}% for {k} consecutive bin(s)")
    print()
    
    # Find alerts
    above_delta = (delta_psi > DELTA).astype(int)
    alert_bins = np.zeros(len(above_delta), dtype=int)
    for i in range(len(above_delta) - (k - 1)):
        if np.sum(above_delta[i:i+k]) == k:
            alert_bins[i:i+k] = 1
    
    # Metrics
    tp = np.sum(alert_bins & breach_label)
    fa_total = np.sum(alert_bins & calm_mask)
    total_alerts = np.sum(alert_bins)
    
    # Recall
    recall = tp / breach_count if breach_count > 0 else 0.0
    
    # FA/hr
    fa_per_hour = fa_total / calm_hours if calm_hours > 0 else 0.0
    
    # Precision
    precision = tp / total_alerts if total_alerts > 0 else 0.0
    
    # Wilson CI
    recall_ci_lower = wilson_ci_lower(tp, breach_count)
    recall_ci_upper = wilson_ci_upper(tp, breach_count)
    
    # FA/hr CI (using poisson approximation)
    fa_ci_lower = fa_total / calm_hours - 1.96 * np.sqrt(fa_total) / calm_hours if fa_total > 0 else 0.0
    fa_ci_upper = fa_total / calm_hours + 1.96 * np.sqrt(fa_total) / calm_hours
    
    fa_ci_lower = max(0, fa_ci_lower)
    
    print(f"  Alerts: {total_alerts:,}")
    print(f"  True positives: {tp}")
    print(f"  False alarms: {fa_total} in {calm_hours:.2f} hours")
    print()
    print(f"  Recall: {recall:.6f}")
    print(f"    Wilson 95% CI: [{recall_ci_lower:.6f}, {recall_ci_upper:.6f}]")
    print(f"  FA/hr: {fa_per_hour:.6f}")
    print(f"    95% CI: [{fa_ci_lower:.6f}, {fa_ci_upper:.6f}]")
    print(f"  Precision: {precision:.6f}")
    print()
    
    # Apply pass criteria
    criterion_1 = recall_ci_lower >= 0.60
    criterion_2 = fa_ci_upper <= 2.0
    
    print(f"  Pass criteria (Wilson 95%):")
    print(f"    Criterion 1 (recall CI lower >= 0.60): {criterion_1}")
    print(f"    Criterion 2 (FA CI upper <= 2.0): {criterion_2}")
    print()
    
    if criterion_1 and criterion_2:
        verdict = "SUPPORTED"
    else:
        verdict = "NOT_SUPPORTED"
    
    print(f"  VERDICT: {verdict}")
    print()
    print("-" * 40)
    print()
    
    results_all[name] = {
        'DELTA': DELTA,
        'k': k,
        'tp': int(tp),
        'fa_total': int(fa_total),
        'fa_per_hour': fa_per_hour,
        'fa_ci_lower': fa_ci_lower,
        'fa_ci_upper': fa_ci_upper,
        'recall': recall,
        'recall_ci_lower': recall_ci_lower,
        'recall_ci_upper': recall_ci_upper,
        'precision': precision,
        'criterion_1_recall': criterion_1,
        'criterion_2_fa': criterion_2,
        'verdict': verdict,
        'slo_threshold_ms': SLO_THRESHOLD
    }

print(f"[STEP 4] Summary")
print("-" * 80)
print()
print("DELTA PSI (SLO) TEST RESULTS:")
print()
for name, results in results_all.items():
    print(f"{name.upper()}:")
    print(f"  DELTA={results['DELTA']}%, k={results['k']}")
    print(f"  Recall: {results['recall']:.6f} [CI: {results['recall_ci_lower']:.6f}, {results['recall_ci_upper']:.6f}]")
    print(f"  FA/hr: {results['fa_per_hour']:.6f} [CI: {results['fa_ci_lower']:.6f}, {results['fa_ci_upper']:.6f}]")
    print(f"  Verdict: {results['verdict']}")
    print()

# Save results
with open(DATA_DIR.parent / "test_delta_psi_held_out_slo_results.json", "w") as f:
    json.dump(results_all, f, indent=2, default=str)

print("Delta PSI (SLO) held-out test results saved to test_delta_psi_held_out_slo_results.json")
print()
print("=" * 80)
