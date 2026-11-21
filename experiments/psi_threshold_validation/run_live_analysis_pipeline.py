#!/usr/bin/env python3
"""
Live Data Analysis Pipeline (Tests 1–6)

Executes frozen pre-registration analysis on real host sessions.
Per PREREG_LIVE_FINAL.yaml
"""

import sys
import json
import math
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, roc_curve
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SESSIONS_DIR = PROJECT_ROOT / "experiments" / "psi_threshold_validation" / "session_logs"

print("=" * 80)
print("LIVE DATA ANALYSIS PIPELINE (Tests 1–6)")
print("=" * 80)
print()

# Load baseline
with open(SESSIONS_DIR.parent / "baseline_live.json") as f:
    baseline_data = json.load(f)

B = baseline_data['B_ms']
THRESHOLD_BREACH = baseline_data['threshold_2B_ms']

print(f"Baseline B: {B:.2f} ms")
print(f"Breach threshold (2*B): {THRESHOLD_BREACH:.2f} ms")
print()

# ===== Load all calibration and test data =====

cal_sessions = ["cal_calm_1", "cal_calm_2", "cal_calm_3", "cal_burst_1", "cal_ramp_1", "cal_step_1"]
test_sessions = ["test_calm_1", "test_calm_2", "test_burst_1", "test_ramp_1", "test_step_1"]

def load_sessions(session_list):
    data = []
    for session_name in session_list:
        session_dir = SESSIONS_DIR / session_name
        metrics_file = session_dir / "metrics.csv"
        if not metrics_file.exists():
            print(f"WARNING: {metrics_file} not found")
            continue
        df = pd.read_csv(metrics_file)
        df['session_name'] = session_name
        data.append(df)
    return pd.concat(data, ignore_index=True) if data else None

print("[LOADING DATA]")
cal_df = load_sessions(cal_sessions)
test_df = load_sessions(test_sessions)

print(f"Calibration: {len(cal_df):,} rows")
print(f"Test: {len(test_df):,} rows")
print()

# ===== Compute breach labels =====

def compute_breach_label(df, threshold):
    latency = df['p99_latency_ms'].values
    above_thresh = (latency > threshold).astype(int)
    
    breach_label = np.zeros(len(above_thresh), dtype=int)
    for i in range(len(above_thresh) - 1):
        if above_thresh[i] == 1 and above_thresh[i+1] == 1:
            breach_label[i] = 1
            breach_label[i+1] = 1
    
    return breach_label

cal_df['breach_label'] = compute_breach_label(cal_df, THRESHOLD_BREACH)
test_df['breach_label'] = compute_breach_label(test_df, THRESHOLD_BREACH)

cal_breach_events = cal_df['breach_label'].sum()
test_breach_events = test_df['breach_label'].sum()

print(f"[BREACH EVENTS]")
print(f"Calibration: {cal_breach_events:,} rows in breach")
print(f"Test: {test_breach_events:,} rows in breach")
print()

# ===== TEST 1: Signal Sanity (Stress Bins) =====

print("=" * 80)
print("TEST 1: SIGNAL SANITY (STRESS BINS)")
print("=" * 80)

signal = cal_df['pod_psi_some_avg10'].values
label = cal_df['breach_label'].values

# Extract stress bins only
stress_mask = signal > 0.0
signal_stress = signal[stress_mask]
label_stress = label[stress_mask]

try:
    auc_stress = roc_auc_score(label_stress, signal_stress)
    print(f"AUC (stress bins): {auc_stress:.6f}")
except Exception as e:
    auc_stress = np.nan
    print(f"AUC error: {e}")

print(f"Stress bins: {stress_mask.sum():,}")
print(f"Signal range: {signal_stress.min():.4f}–{signal_stress.max():.4f}%")
print()

test1_result = {'auc_stress': auc_stress, 'stress_bins': int(stress_mask.sum())}

# ===== TEST 2: Lag Analysis (Stress Bins) =====

print("=" * 80)
print("TEST 2: LAG ANALYSIS")
print("=" * 80)

# Normalize
signal_norm = (signal - signal.mean()) / (signal.std() + 1e-9)
latency = cal_df['p99_latency_ms'].values
latency_norm = (latency - latency.mean()) / (latency.std() + 1e-9)

print("Lag (sec) | Correlation")
print("-" * 30)

lags = [-60, -40, -20, 0, 20, 40, 60]
lag_corrs = []

for lag_sec in lags:
    lag_bins = lag_sec // 20
    
    if lag_bins < 0:
        sig_section = signal_norm[:-abs(lag_bins)]
        lat_section = latency_norm[abs(lag_bins):]
    elif lag_bins > 0:
        sig_section = signal_norm[lag_bins:]
        lat_section = latency_norm[:-lag_bins]
    else:
        sig_section = signal_norm
        lat_section = latency_norm
    
    corr = np.corrcoef(sig_section, lat_section)[0, 1]
    lag_corrs.append(corr)
    print(f"{lag_sec:+5d}   | {corr:+.6f}")

print()

peak_lag_idx = np.argmax(np.abs(lag_corrs))
peak_lag = lags[peak_lag_idx]
peak_corr = lag_corrs[peak_lag_idx]

print(f"Peak correlation: {peak_corr:.6f} at lag {peak_lag}s")
print()

if abs(peak_corr) < 0.7 and peak_lag != 0:
    print(f"Signal lags outcome by ~{abs(peak_lag)}s (reactive)")
elif abs(peak_corr) < 0.7 and max(abs(c) for c in lag_corrs) < 0.7:
    print("Signal shows weak correlation; likely not predictive")
else:
    print(f"Signal and outcome are highly correlated across all lags")

print()

test2_result = {'peak_correlation': peak_corr, 'peak_lag_sec': peak_lag}

# ===== TEST 3: Calibration Sweep =====

print("=" * 80)
print("TEST 3: CALIBRATION SWEEP")
print("=" * 80)

T_GRID = [0.5, 1.0, 1.5, 1.8, 2.0, 2.5, 3.0, 4.0, 5.0]
K_VALUES = [1, 3]

# Calm hours
calm_mask = signal == 0.0
calm_bins = calm_mask.sum()
calm_hours = calm_bins * 20 / 3600

breach_count = cal_df['breach_label'].sum()

sweep_results = []

for T in T_GRID:
    for k in K_VALUES:
        above_T = (signal > T).astype(int)
        
        alert_bins = np.zeros(len(above_T), dtype=int)
        for i in range(len(above_T) - (k - 1)):
            if np.sum(above_T[i:i+k]) == k:
                alert_bins[i:i+k] = 1
        
        tp = np.sum(alert_bins & cal_df['breach_label'].values)
        fa = np.sum(alert_bins & calm_mask)
        
        recall = tp / breach_count if breach_count > 0 else 0.0
        fa_per_hour = fa / calm_hours if calm_hours > 0 else 0.0
        
        viable = (recall >= 0.5) and (fa_per_hour <= 2.0)
        
        sweep_results.append({
            'T': T, 'k': k, 'recall': recall, 'fa_per_hour': fa_per_hour,
            'tp': int(tp), 'fa': int(fa), 'viable': viable
        })

# Find selected threshold
viable_results = [r for r in sweep_results if r['viable']]

if viable_results:
    selected = sorted(viable_results, key=lambda r: (-r['recall'], r['fa_per_hour'], -r['T']))[0]
    selection_status = "selected"
    print(f"SELECTED: T={selected['T']}%, k={selected['k']}")
    print(f"  Recall: {selected['recall']:.4f}")
    print(f"  FA/hr: {selected['fa_per_hour']:.4f}")
else:
    selected = None
    selection_status = "no_viable"
    print("NO VIABLE THRESHOLD")

print()

test3_result = {'sweep': sweep_results, 'selected': selected, 'status': selection_status}

# ===== TEST 4: Held-Out Test (on Test Data) =====

print("=" * 80)
print("TEST 4: HELD-OUT TEST EVALUATION")
print("=" * 80)

test_signal = test_df['pod_psi_some_avg10'].values
test_label = test_df['breach_label'].values
test_latency = test_df['p99_latency_ms'].values

test_breach_count = test_label.sum()
test_calm_mask = test_signal == 0.0
test_calm_bins = test_calm_mask.sum()
test_calm_hours = test_calm_bins * 20 / 3600

test_results = {}

if selected:
    T_sel, k_sel = selected['T'], selected['k']
    
    above_T = (test_signal > T_sel).astype(int)
    alert_bins = np.zeros(len(above_T), dtype=int)
    for i in range(len(above_T) - (k_sel - 1)):
        if np.sum(above_T[i:i+k_sel]) == k_sel:
            alert_bins[i:i+k_sel] = 1
    
    tp = np.sum(alert_bins & test_label)
    fa = np.sum(alert_bins & test_calm_mask)
    
    recall = tp / test_breach_count if test_breach_count > 0 else 0.0
    fa_per_hour = fa / test_calm_hours if test_calm_hours > 0 else 0.0
    
    # Wilson CI
    ci_lower = max(0.0, recall - 1.96 * np.sqrt(recall * (1 - recall) / test_breach_count)) if test_breach_count > 0 else 0.0
    ci_upper = min(1.0, recall + 1.96 * np.sqrt(recall * (1 - recall) / test_breach_count)) if test_breach_count > 0 else 1.0
    
    crit1 = ci_lower >= 0.60
    crit2 = fa_per_hour <= 2.0
    
    print(f"Selected T={T_sel}%, k={k_sel}:")
    print(f"  Recall: {recall:.4f} [CI: {ci_lower:.4f}, {ci_upper:.4f}]")
    print(f"  FA/hr: {fa_per_hour:.4f}")
    print(f"  Pass: {crit1 and crit2}")
    
    test_results['selected'] = {
        'T': T_sel, 'k': k_sel, 'recall': recall, 'fa_per_hour': fa_per_hour,
        'ci_lower': ci_lower, 'criterion_1': crit1, 'criterion_2': crit2,
        'verdict': 'SUPPORTED' if (crit1 and crit2) else 'NOT_SUPPORTED'
    }
    
    print()

# Test T=1.8%
T_proj, k_proj = 1.8, 1

above_T = (test_signal > T_proj).astype(int)
alert_bins = np.zeros(len(above_T), dtype=int)
for i in range(len(above_T) - (k_proj - 1)):
    if np.sum(above_T[i:i+k_proj]) == k_proj:
        alert_bins[i:i+k_proj] = 1

tp = np.sum(alert_bins & test_label)
fa = np.sum(alert_bins & test_calm_mask)

recall = tp / test_breach_count if test_breach_count > 0 else 0.0
fa_per_hour = fa / test_calm_hours if test_calm_hours > 0 else 0.0

ci_lower = max(0.0, recall - 1.96 * np.sqrt(recall * (1 - recall) / test_breach_count)) if test_breach_count > 0 else 0.0
ci_upper = min(1.0, recall + 1.96 * np.sqrt(recall * (1 - recall) / test_breach_count)) if test_breach_count > 0 else 1.0

crit1 = ci_lower >= 0.60
crit2 = fa_per_hour <= 2.0

print(f"Project T={T_proj}%, k={k_proj}:")
print(f"  Recall: {recall:.4f} [CI: {ci_lower:.4f}, {ci_upper:.4f}]")
print(f"  FA/hr: {fa_per_hour:.4f}")
print(f"  Pass: {crit1 and crit2}")

test_results['project'] = {
    'T': T_proj, 'k': k_proj, 'recall': recall, 'fa_per_hour': fa_per_hour,
    'ci_lower': ci_lower, 'criterion_1': crit1, 'criterion_2': crit2,
    'verdict': 'SUPPORTED' if (crit1 and crit2) else 'NOT_SUPPORTED'
}

print()

# ===== TEST 5: Chance Check =====

print("=" * 80)
print("TEST 5: CHANCE CHECK (Shuffled Labels)")
print("=" * 80)

np.random.seed(42)

# Use selected threshold if available
if selected:
    T_check, k_check = selected['T'], selected['k']
else:
    T_check, k_check = 1.8, 1

print(f"Testing T={T_check}%, k={k_check} with shuffled labels (1000 trials)")
print()

above_T_check = (test_signal > T_check).astype(int)
alert_bins_check = np.zeros(len(above_T_check), dtype=int)
for i in range(len(above_T_check) - (k_check - 1)):
    if np.sum(above_T_check[i:i+k_check]) == k_check:
        alert_bins_check[i:i+k_check] = 1

tp_observed = np.sum(alert_bins_check & test_label)
recall_observed = tp_observed / test_breach_count if test_breach_count > 0 else 0.0

shuffled_recalls = []
for trial in range(1000):
    shuffled_label = np.random.permutation(test_label)
    tp_shuffled = np.sum(alert_bins_check & shuffled_label)
    recall_shuffled = tp_shuffled / test_breach_count
    shuffled_recalls.append(recall_shuffled)

shuffled_recalls = np.array(shuffled_recalls)
count_beat = np.sum(shuffled_recalls >= recall_observed)
pct_beat = 100 * count_beat / len(shuffled_recalls)

print(f"Observed recall: {recall_observed:.6f}")
print(f"Shuffled mean: {shuffled_recalls.mean():.6f}")
print(f"Trials beating observed: {count_beat}/1000 ({pct_beat:.1f}%)")
print()

chance_verdict = "PASS" if pct_beat <= 5 else "FAIL"
print(f"Chance check: {chance_verdict}")
print()

# ===== Save Results =====

final_results = {
    'baseline': baseline_data,
    'test_1_signal_sanity': test1_result,
    'test_2_lag_analysis': test2_result,
    'test_3_calibration_sweep': test3_result,
    'test_4_held_out_evaluation': test_results,
    'test_5_chance_check': {
        'observed_recall': recall_observed,
        'shuffled_mean': float(shuffled_recalls.mean()),
        'count_beat': int(count_beat),
        'pct_beat': pct_beat,
        'verdict': chance_verdict
    }
}

with open(SESSIONS_DIR.parent / "live_analysis_results.json", "w") as f:
    json.dump(final_results, f, indent=2, default=str)

print("=" * 80)
print("RESULTS SAVED: live_analysis_results.json")
print("=" * 80)
