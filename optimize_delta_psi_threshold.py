#!/usr/bin/env python3
"""
Optimize Delta PSI Threshold for p99 200ms SLO Breach Detection

Tests multiple delta PSI thresholds and finds optimal balance between:
  - Recall: % of breaches caught
  - False alarm rate: alerts per hour
  - Precision: % of alerts that are true breaches
"""

import argparse
import json
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent
RESULTS_DIR = PROJECT_ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# ============================================================================
# CONFIGURATION
# ============================================================================

SLO_THRESHOLD_MS = 200.0
SAMPLE_INTERVAL_SECONDS = 20

# Test thresholds
TEST_THRESHOLDS = [0.5, 0.8, 1.0, 1.2, 1.5, 1.8, 2.0, 2.5, 3.0]

# Validation criteria
RECALL_MIN = 0.60
FA_RATE_MAX = 2.0  # per hour
PRECISION_MIN = 0.50

# ============================================================================
# THRESHOLD OPTIMIZER
# ============================================================================

class ThresholdOptimizer:
    """Find optimal delta PSI threshold"""
    
    def __init__(self, data_file: str):
        self.data_file = data_file
        self.df = None
        self.breach_events = []
        
        print("=" * 100)
        print("DELTA PSI THRESHOLD OPTIMIZATION: p99 200ms SLO BREACH")
        print("=" * 100)
        print()
    
    def load_data(self) -> pd.DataFrame:
        """Load synthetic data"""
        print(f"[STEP 1] Load synthetic data")
        print("-" * 100)
        
        self.df = pd.read_csv(self.data_file)
        print(f"✓ Loaded {len(self.df)} samples from {Path(self.data_file).name}")
        print(f"  Time range: {self.df['timestamp'].min()} to {self.df['timestamp'].max()}")
        print()
        
        return self.df
    
    def identify_breach_events(self):
        """Identify all SLO breach events"""
        print(f"[STEP 2] Identify SLO breach events")
        print("-" * 100)
        
        slo_breach = (self.df['p99_latency_ms'].values > SLO_THRESHOLD_MS).astype(bool)
        
        # Group consecutive breaches into events
        self.breach_events = []
        in_breach = False
        breach_start = None
        
        for i in range(len(slo_breach)):
            if slo_breach[i] and not in_breach:
                breach_start = i
                in_breach = True
            elif not slo_breach[i] and in_breach:
                self.breach_events.append({
                    'start_idx': breach_start,
                    'end_idx': i - 1,
                    'duration_samples': i - breach_start,
                    'peak_latency_ms': self.df['p99_latency_ms'].iloc[breach_start:i].max(),
                })
                in_breach = False
        
        if in_breach:
            self.breach_events.append({
                'start_idx': breach_start,
                'end_idx': len(slo_breach) - 1,
                'duration_samples': len(slo_breach) - breach_start,
                'peak_latency_ms': self.df['p99_latency_ms'].iloc[breach_start:].max(),
            })
        
        print(f"✓ Identified {len(self.breach_events)} SLO breach events")
        print()
    
    def test_threshold(self, threshold: float) -> Dict:
        """Test a specific delta PSI threshold"""
        # Generate alerts
        abs_delta_psi = np.abs(self.df['delta_psi'].values)
        raw_alerts = abs_delta_psi >= threshold
        
        # Group consecutive alerts
        alerts = np.zeros_like(raw_alerts, dtype=bool)
        in_alert = False
        
        for i in range(len(raw_alerts)):
            if raw_alerts[i] and not in_alert:
                alerts[i] = True
                in_alert = True
            elif not raw_alerts[i]:
                in_alert = False
        
        # Calculate metrics
        detected_breaches = 0
        lead_times = []
        
        for breach in self.breach_events:
            breach_start = breach['start_idx']
            lookback_start = max(0, breach_start - 10)
            
            alert_indices = np.where(alerts[lookback_start:breach_start])[0]
            
            if len(alert_indices) > 0:
                detected_breaches += 1
                last_alert_idx = alert_indices[-1] + lookback_start
                lead_time_samples = breach_start - last_alert_idx
                lead_times.append(lead_time_samples * SAMPLE_INTERVAL_SECONDS)
        
        # Recall
        recall = detected_breaches / len(self.breach_events) if len(self.breach_events) > 0 else 0
        
        # False alarms
        num_alerts = alerts.sum()
        true_alerts = 0
        
        for alert_idx in np.where(alerts)[0]:
            lookahead = min(alert_idx + 15, len(self.df))
            if (self.df['p99_latency_ms'].iloc[alert_idx:lookahead] > SLO_THRESHOLD_MS).any():
                true_alerts += 1
        
        false_alarms = num_alerts - true_alerts
        total_hours = len(self.df) * SAMPLE_INTERVAL_SECONDS / 3600
        fa_rate = false_alarms / total_hours if total_hours > 0 else 0
        
        # Precision
        precision = true_alerts / num_alerts if num_alerts > 0 else 0
        
        mean_lead_time = np.mean(lead_times) if lead_times else 0
        
        return {
            'threshold': threshold,
            'num_alerts': int(num_alerts),
            'true_alerts': int(true_alerts),
            'false_alarms': int(false_alarms),
            'fa_rate': fa_rate,
            'recall': recall,
            'precision': precision,
            'detected_breaches': int(detected_breaches),
            'missed_breaches': int(len(self.breach_events) - detected_breaches),
            'mean_lead_time_s': mean_lead_time,
            'meets_criteria': (recall >= RECALL_MIN and fa_rate <= FA_RATE_MAX and precision >= PRECISION_MIN)
        }
    
    def optimize(self):
        """Test all thresholds and find optimal"""
        print(f"[STEP 3] Test {len(TEST_THRESHOLDS)} threshold values")
        print("-" * 100)
        print()
        
        results = []
        
        for threshold in TEST_THRESHOLDS:
            metrics = self.test_threshold(threshold)
            results.append(metrics)
        
        # Print results table
        print(f"{'Threshold':>10} {'Alerts':>8} {'True':>6} {'False':>6} {'FA/hr':>8} {'Recall':>8} {'Prec':>8} {'Status':>15}")
        print("-" * 100)
        
        for metrics in results:
            status = "✓ MEETS" if metrics['meets_criteria'] else "✗ FAIL"
            print(f"{metrics['threshold']:>10.1f}% {metrics['num_alerts']:>8d} {metrics['true_alerts']:>6d} {metrics['false_alarms']:>6d} "
                  f"{metrics['fa_rate']:>8.2f} {metrics['recall']:>8.2%} {metrics['precision']:>8.2%} {status:>15}")
        
        print()
        
        # Find best threshold
        viable_results = [r for r in results if r['meets_criteria']]
        
        if viable_results:
            # Sort by recall (descending), then FA rate (ascending)
            best = sorted(viable_results, key=lambda x: (-x['recall'], x['fa_rate']))[0]
            
            print(f"[STEP 4] Analysis")
            print("-" * 100)
            print(f"✓ OPTIMAL THRESHOLD FOUND: {best['threshold']:.1f}%")
            print()
            print(f"  Metrics for T={best['threshold']:.1f}%:")
            print(f"    Recall: {best['recall']:.4f} ({best['detected_breaches']}/{len(self.breach_events)} breaches detected)")
            print(f"    FA rate: {best['fa_rate']:.2f}/hour ({best['false_alarms']}/{best['num_alerts']} alerts)")
            print(f"    Precision: {best['precision']:.4f}")
            print(f"    Mean lead time: {best['mean_lead_time_s']:.1f}s")
            print()
            print(f"  Meets all criteria:")
            print(f"    ✓ Recall >= {RECALL_MIN}: {best['recall']:.4f} >= {RECALL_MIN}")
            print(f"    ✓ FA rate <= {FA_RATE_MAX}/hr: {best['fa_rate']:.2f} <= {FA_RATE_MAX}")
            print(f"    ✓ Precision >= {PRECISION_MIN}: {best['precision']:.4f} >= {PRECISION_MIN}")
            print()
            
            return best
        else:
            print(f"[STEP 4] Analysis")
            print("-" * 100)
            print(f"✗ NO VIABLE THRESHOLD FOUND")
            print(f"  No threshold meets all criteria:")
            print(f"    - Recall >= {RECALL_MIN}")
            print(f"    - FA rate <= {FA_RATE_MAX}/hr")
            print(f"    - Precision >= {PRECISION_MIN}")
            print()
            
            # Recommend closest threshold
            print(f"  Recommendations:")
            print(f"    1. Lower RECALL_MIN requirement (e.g., 0.40)")
            print(f"    2. Increase FA_RATE_MAX tolerance (e.g., 3.0/hr)")
            print(f"    3. Lower PRECISION_MIN requirement (e.g., 0.30)")
            print(f"    4. Adjust spike event generation parameters")
            print()
            
            # Show best recall
            best_recall = sorted(results, key=lambda x: -x['recall'])[0]
            print(f"  Best recall: T={best_recall['threshold']:.1f}% gives {best_recall['recall']:.2%} recall")
            print()
            
            # Show best FA rate
            best_fa = sorted(results, key=lambda x: x['fa_rate'])[0]
            print(f"  Best FA rate: T={best_fa['threshold']:.1f}% gives {best_fa['fa_rate']:.2f}/hr")
            print()
            
            return sorted(results, key=lambda x: (-x['recall'], x['fa_rate']))[0]
    
    def save_results(self, all_results: List[Dict], best_result: Dict) -> Path:
        """Save optimization results"""
        print(f"[STEP 5] Save results")
        print("-" * 100)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        results_file = RESULTS_DIR / f"p99_200ms_threshold_optimization_{timestamp}.json"
        
        results = {
            'timestamp': timestamp,
            'data_file': str(self.data_file),
            'config': {
                'slo_threshold_ms': SLO_THRESHOLD_MS,
                'sample_interval_seconds': SAMPLE_INTERVAL_SECONDS,
                'recall_min': RECALL_MIN,
                'fa_rate_max': FA_RATE_MAX,
                'precision_min': PRECISION_MIN,
                'thresholds_tested': TEST_THRESHOLDS,
            },
            'dataset_stats': {
                'total_samples': len(self.df),
                'duration_hours': len(self.df) * SAMPLE_INTERVAL_SECONDS / 3600,
                'total_breach_events': len(self.breach_events),
            },
            'threshold_sweep': [
                {
                    'threshold': float(r['threshold']),
                    'num_alerts': int(r['num_alerts']),
                    'true_alerts': int(r['true_alerts']),
                    'false_alarms': int(r['false_alarms']),
                    'fa_rate': float(r['fa_rate']),
                    'recall': float(r['recall']),
                    'precision': float(r['precision']),
                    'detected_breaches': int(r['detected_breaches']),
                    'missed_breaches': int(r['missed_breaches']),
                    'mean_lead_time_s': float(r['mean_lead_time_s']),
                    'meets_criteria': bool(r['meets_criteria'])
                }
                for r in all_results
            ],
            'optimal_threshold': {
                'threshold': float(best_result['threshold']),
                'num_alerts': int(best_result['num_alerts']),
                'true_alerts': int(best_result['true_alerts']),
                'false_alarms': int(best_result['false_alarms']),
                'fa_rate': float(best_result['fa_rate']),
                'recall': float(best_result['recall']),
                'precision': float(best_result['precision']),
                'detected_breaches': int(best_result['detected_breaches']),
                'missed_breaches': int(best_result['missed_breaches']),
                'mean_lead_time_s': float(best_result['mean_lead_time_s']),
                'meets_criteria': bool(best_result['meets_criteria'])
            }
        }
        
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"✓ Saved results to: {results_file}")
        print()
        
        return results_file


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Optimize delta PSI threshold for p99 200ms latency breach detection"
    )
    parser.add_argument("--data", type=str, required=True, help="Path to synthetic CSV file")
    args = parser.parse_args()
    
    optimizer = ThresholdOptimizer(args.data)
    optimizer.load_data()
    optimizer.identify_breach_events()
    
    # Test all thresholds
    all_results = []
    for threshold in TEST_THRESHOLDS:
        metrics = optimizer.test_threshold(threshold)
        all_results.append(metrics)
    
    # Print summary
    print(f"[STEP 3] Test {len(TEST_THRESHOLDS)} threshold values")
    print("-" * 100)
    print()
    
    print(f"{'Threshold':>10} {'Alerts':>8} {'True':>6} {'False':>6} {'FA/hr':>8} {'Recall':>8} {'Prec':>8} {'Status':>15}")
    print("-" * 100)
    
    for metrics in all_results:
        status = "✓ MEETS" if metrics['meets_criteria'] else "✗ FAIL"
        print(f"{metrics['threshold']:>10.1f}% {metrics['num_alerts']:>8d} {metrics['true_alerts']:>6d} {metrics['false_alarms']:>6d} "
              f"{metrics['fa_rate']:>8.2f} {metrics['recall']:>8.2%} {metrics['precision']:>8.2%} {status:>15}")
    
    print()
    
    # Find best
    viable_results = [r for r in all_results if r['meets_criteria']]
    
    print(f"[STEP 4] Analysis")
    print("-" * 100)
    
    if viable_results:
        best = sorted(viable_results, key=lambda x: (-x['recall'], x['fa_rate']))[0]
        print(f"✓ OPTIMAL THRESHOLD FOUND: {best['threshold']:.1f}%")
        print()
        print(f"  Metrics for T={best['threshold']:.1f}%:")
        print(f"    Recall: {best['recall']:.4f} ({best['detected_breaches']}/{len(optimizer.breach_events)} breaches)")
        print(f"    FA rate: {best['fa_rate']:.2f}/hour")
        print(f"    Precision: {best['precision']:.4f}")
        print(f"    Lead time: {best['mean_lead_time_s']:.1f}s")
    else:
        best = sorted(all_results, key=lambda x: (-x['recall'], x['fa_rate']))[0]
        print(f"✗ NO PERFECT THRESHOLD, but best tradeoff:")
        print(f"  T={best['threshold']:.1f}%: Recall={best['recall']:.2%}, FA={best['fa_rate']:.2f}/hr, Prec={best['precision']:.2%}")
    
    print()
    
    # Save results
    optimizer.save_results(all_results, best)
    
    print("=" * 100)
    print(f"OPTIMIZATION COMPLETE")
    print("=" * 100)
    print()

if __name__ == "__main__":
    main()
