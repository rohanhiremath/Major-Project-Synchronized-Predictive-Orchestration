#!/usr/bin/env python3
"""
Delta PSI Threshold Validation with Real Data (200ms SLO)

Validates Delta PSI (PSI change) thresholds against real production data with 200ms SLO breach label.

Usage:
  python test_absolute_psi_real_data_slo.py --data <csv_file>
  
Example:
  python test_absolute_psi_real_data_slo.py --data ../../data/real_data_200ms_slo_20261019_120000.csv
"""

import sys
import json
import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

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

def validate_psi_thresholds(data_file: str):
    """Main validation function"""
    
    print("=" * 100)
    print("DELTA PSI THRESHOLD VALIDATION: REAL DATA (200ms SLO)")
    print("=" * 100)
    print()
    
    # Load real data
    print(f"[STEP 1] Load real data")
    print("-" * 100)
    
    try:
        df = pd.read_csv(data_file)
    except FileNotFoundError:
        print(f"ERROR: File not found: {data_file}")
        return False
    
    print(f"Loaded {len(df):,} samples from {data_file}")
    print()
    
    # Data should have: timestamp, delta_psi, latency_ms, slo_breach
    required_cols = ['delta_psi', 'latency_ms', 'slo_breach']
    missing_cols = [c for c in required_cols if c not in df.columns]
    
    if missing_cols:
        print(f"ERROR: Missing required columns: {missing_cols}")
        print(f"Available columns: {list(df.columns)}")
        return False
    
    # Prepare data using DELTA PSI instead of absolute PSI
    signal = df['delta_psi'].values  # Use delta_psi instead of psi_some_avg10
    breach_label = df['slo_breach'].values.astype(int)
    
    # Compute calm periods (original PSI == 0)
    psi_calm = df['psi_some_avg10'].values if 'psi_some_avg10' in df.columns else np.zeros(len(df))
    calm_mask = (psi_calm == 0.0).astype(int)
    calm_bins = calm_mask.sum()
    calm_hours = calm_bins * 20 / 3600
    
    breach_count = breach_label.sum()
    
    print(f"Data statistics:")
    print(f"  SLO breaches: {breach_count:,} ({100*breach_count/len(df):.2f}%)")
    print(f"  Calm periods: {calm_bins:,} bins = {calm_hours:.2f} hours")
    print()
    print(f"Delta PSI distribution:")
    print(f"  Min: {signal.min():.4f}%")
    print(f"  P5: {np.percentile(signal, 5):.4f}%")
    print(f"  P50: {np.percentile(signal, 50):.4f}%")
    print(f"  P95: {np.percentile(signal, 95):.4f}%")
    print(f"  Max: {signal.max():.4f}%")
    print()
    
    if breach_count == 0:
        print("ERROR: No SLO breaches in data!")
        print("       Cannot validate thresholds without breaches to detect")
        return False
    
    # Test different DELTA thresholds
    print(f"[STEP 2] Sweep Delta PSI thresholds")
    print("-" * 100)
    
    DELTA_GRID = [0.5, 1.0, 1.5, 1.8, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0]
    K_VALUES = [1, 3]
    
    sweep_results = []
    
    for DELTA in DELTA_GRID:
        for k in K_VALUES:
            # Create alert signal: delta_psi > DELTA
            above_delta = (signal > DELTA).astype(int)
            alert_bins = np.zeros(len(above_delta), dtype=int)
            
            for i in range(len(above_delta) - (k - 1)):
                if np.sum(above_delta[i:i+k]) == k:
                    alert_bins[i:i+k] = 1
            
            # Compute metrics
            tp = np.sum(alert_bins & breach_label)
            fa_total = np.sum(alert_bins & calm_mask)
            total_alerts = np.sum(alert_bins)
            
            recall = tp / breach_count if breach_count > 0 else 0.0
            fa_per_hour = fa_total / calm_hours if calm_hours > 0 else 0.0
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
                'viable': (recall >= 0.5) and (fa_per_hour <= 2.0)
            })
    
    # Print results
    print("Results (Delta PSI > DELTA%):")
    print(f"{'DELTA':<8} {'k':<3} {'Recall':<10} {'FA/hr':<10} {'Precision':<12} {'Viable':<8}")
    print("-" * 55)
    
    for r in sweep_results:
        viable_str = "✓" if r['viable'] else "✗"
        print(f"{r['DELTA']:<8.1f} {r['k']:<3} {r['recall']:<10.4f} {r['fa_per_hour']:<10.4f} "
              f"{r['precision']:<12.4f} {viable_str:<8}")
    
    print()
    
    # Find viable thresholds
    viable = [r for r in sweep_results if r['viable']]
    
    print(f"[STEP 3] Analysis")
    print("-" * 100)
    
    if len(viable) == 0:
        print("❌ NO VIABLE DELTA PSI THRESHOLDS FOUND")
        print()
        print("No (DELTA, k) pair meets both criteria:")
        print("  - Recall >= 0.50")
        print("  - FA/hr <= 2.0")
        print()
        print("Best candidates (highest recall):")
        recall_sorted = sorted(sweep_results, key=lambda r: -r['recall'])
        for i, r in enumerate(recall_sorted[:3], 1):
            print(f"  {i}. DELTA={r['DELTA']}%, k={r['k']}: recall={r['recall']:.4f}, FA/hr={r['fa_per_hour']:.4f}")
        return False
    
    # Select best viable threshold
    viable_sorted = sorted(viable, key=lambda r: (-r['recall'], r['fa_per_hour'], -r['DELTA']))
    selected = viable_sorted[0]
    
    print(f"✓ VIABLE DELTA PSI THRESHOLDS FOUND: {len(viable)} combinations")
    print()
    print(f"SELECTED: DELTA={selected['DELTA']}%, k={selected['k']}")
    print(f"  Recall: {selected['recall']:.4f} ({selected['recall']*100:.2f}%)")
    print(f"  FA/hr: {selected['fa_per_hour']:.4f}")
    print(f"  Precision: {selected['precision']:.4f}")
    print(f"  TP: {selected['tp']}, Alerts: {selected['alerts']}")
    print()
    
    # Compute confidence intervals
    print(f"[STEP 4] Statistical Validation (Wilson 95% CI)")
    print("-" * 100)
    print()
    
    delta_final = selected['DELTA']
    k_final = selected['k']
    
    recall_ci_lower = wilson_ci_lower(selected['tp'], breach_count)
    recall_ci_upper = wilson_ci_upper(selected['tp'], breach_count)
    
    fa_ci_lower = selected['fa_total'] / calm_hours - 1.96 * np.sqrt(selected['fa_total']) / calm_hours if selected['fa_total'] > 0 else 0.0
    fa_ci_upper = selected['fa_total'] / calm_hours + 1.96 * np.sqrt(selected['fa_total']) / calm_hours
    fa_ci_lower = max(0, fa_ci_lower)
    
    print(f"Threshold: DELTA={delta_final}%, k={k_final}")
    print(f"  Interpretation: Alert when PSI change > {delta_final}% for {k_final} consecutive bin(s)")
    print()
    print(f"Recall: {selected['recall']:.6f}")
    print(f"  95% CI: [{recall_ci_lower:.6f}, {recall_ci_upper:.6f}]")
    print()
    print(f"FA/hr: {selected['fa_per_hour']:.6f}")
    print(f"  95% CI: [{fa_ci_lower:.6f}, {fa_ci_upper:.6f}]")
    print()
    
    # Pass criteria
    criterion_1 = recall_ci_lower >= 0.60
    criterion_2 = fa_ci_upper <= 2.0
    
    print(f"Pass Criteria (Wilson 95%):")
    print(f"  Criterion 1 (recall CI lower >= 0.60): {criterion_1}")
    print(f"  Criterion 2 (FA CI upper <= 2.0): {criterion_2}")
    print()
    
    verdict = "SUPPORTED" if (criterion_1 and criterion_2) else "NOT_SUPPORTED"
    
    print(f"VERDICT: {verdict}")
    print()
    
    # Save results
    results = {
        'data_file': str(data_file),
        'slo_threshold_ms': 200.0,
        'signal_type': 'delta_psi',
        'selected_threshold': {
            'DELTA': delta_final,
            'k': k_final,
            'recall': selected['recall'],
            'recall_ci_lower': recall_ci_lower,
            'recall_ci_upper': recall_ci_upper,
            'fa_per_hour': selected['fa_per_hour'],
            'fa_ci_lower': fa_ci_lower,
            'fa_ci_upper': fa_ci_upper,
            'precision': selected['precision'],
            'tp': selected['tp'],
            'fa_total': selected['fa_total'],
            'alerts': selected['alerts'],
            'criterion_1_recall': criterion_1,
            'criterion_2_fa': criterion_2,
            'verdict': verdict
        },
        'all_results': sweep_results,
        'viable_count': len(viable)
    }
    
    output_file = PROJECT_ROOT / f"test_delta_psi_slo_results_{Path(data_file).stem}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"Results saved to {output_file}")
    print()
    print("=" * 100)
    
    return verdict == "SUPPORTED"

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate PSI thresholds against real data with 200ms SLO")
    parser.add_argument("--data", type=str, required=True, help="Path to real data CSV file")
    args = parser.parse_args()
    
    success = validate_psi_thresholds(args.data)
    sys.exit(0 if success else 1)
