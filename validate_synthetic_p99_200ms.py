#!/usr/bin/env python3
"""
Validation: Synthetic p99 200ms Latency Breach with Delta 1.8% PSI

Tests the correlation between:
  - Delta PSI (PSI change): Signal (predictor)
  - p99 Latency > 200ms: Label (outcome)

Pre-registered criteria for SUCCESS:
  1. Recall >= 0.60 (catches 60%+ of SLO breaches)
  2. False Alarm Rate <= 2/hour
  3. Precision >= 0.50
  4. Lead time >= 20s (warning before breach)

Threshold tested: Delta PSI magnitude >= 1.8%
"""

import argparse
import json
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple, List
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parent
RESULTS_DIR = PROJECT_ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# ============================================================================
# CONFIGURATION
# ============================================================================

DELTA_PSI_THRESHOLD = 1.8  # % change per sample
SLO_THRESHOLD_MS = 200.0
SAMPLE_INTERVAL_SECONDS = 20
LEAD_TIME_SAMPLES = 1  # 20s minimum lead time

# Pre-registered validation criteria
RECALL_MIN = 0.60
FA_RATE_MAX = 2.0  # per hour
PRECISION_MIN = 0.50
LEAD_TIME_MIN_SECONDS = 20

# ============================================================================
# VALIDATION ENGINE
# ============================================================================

class DeltaPSIValidator:
    """Validate delta PSI threshold against synthetic data"""
    
    def __init__(self, data_file: str):
        self.data_file = data_file
        self.results = {}
        
        print("=" * 100)
        print("DELTA PSI THRESHOLD VALIDATION: p99 200ms SLO BREACH")
        print("=" * 100)
        print()
        
        print(f"[CONFIG]")
        print(f"  Delta PSI threshold: >= {DELTA_PSI_THRESHOLD}%")
        print(f"  SLO threshold: {SLO_THRESHOLD_MS}ms")
        print(f"  Sample interval: {SAMPLE_INTERVAL_SECONDS}s")
        print()
    
    def load_data(self) -> pd.DataFrame:
        """Load synthetic data"""
        print(f"[STEP 1] Load synthetic data")
        print("-" * 100)
        
        df = pd.read_csv(self.data_file)
        print(f"✓ Loaded {len(df)} samples from {Path(self.data_file).name}")
        print(f"  Columns: {', '.join(df.columns[:10])}...")
        print(f"  Time range: {df['timestamp'].min()} to {df['timestamp'].max()}")
        print()
        
        return df
    
    def generate_alerts(self, df: pd.DataFrame) -> np.ndarray:
        """
        Generate alerts where delta PSI magnitude exceeds threshold
        
        Alert logic:
          - Alert when |delta_psi| >= DELTA_PSI_THRESHOLD
          - Count consecutive alerts as single event (no alert spam)
        """
        abs_delta_psi = np.abs(df['delta_psi'].values)
        raw_alerts = abs_delta_psi >= DELTA_PSI_THRESHOLD
        
        # Group consecutive alerts into single events (no spam)
        alerts = np.zeros_like(raw_alerts, dtype=bool)
        in_alert = False
        
        for i in range(len(raw_alerts)):
            if raw_alerts[i] and not in_alert:
                # Start of new alert event
                alerts[i] = True
                in_alert = True
            elif not raw_alerts[i]:
                # End of alert event
                in_alert = False
        
        return alerts.astype(int)
    
    def identify_slo_breaches(self, df: pd.DataFrame) -> List[Dict]:
        """
        Identify SLO breach events
        
        A breach event is:
          - One or more consecutive samples with p99 > 200ms
        """
        slo_breach = (df['p99_latency_ms'].values > SLO_THRESHOLD_MS).astype(bool)
        
        # Group consecutive breaches into events
        breach_events = []
        in_breach = False
        breach_start = None
        
        for i in range(len(slo_breach)):
            if slo_breach[i] and not in_breach:
                # Start of breach
                breach_start = i
                in_breach = True
            elif not slo_breach[i] and in_breach:
                # End of breach
                breach_events.append({
                    'start_idx': breach_start,
                    'end_idx': i - 1,
                    'duration_samples': i - breach_start,
                    'peak_latency_ms': df['p99_latency_ms'].iloc[breach_start:i].max(),
                    'mean_latency_ms': df['p99_latency_ms'].iloc[breach_start:i].mean(),
                })
                in_breach = False
        
        # Handle breach that extends to end of data
        if in_breach:
            breach_events.append({
                'start_idx': breach_start,
                'end_idx': len(slo_breach) - 1,
                'duration_samples': len(slo_breach) - breach_start,
                'peak_latency_ms': df['p99_latency_ms'].iloc[breach_start:].max(),
                'mean_latency_ms': df['p99_latency_ms'].iloc[breach_start:].mean(),
            })
        
        return breach_events
    
    def calculate_metrics(self, df: pd.DataFrame, alerts: np.ndarray, breach_events: List[Dict]) -> Dict:
        """
        Calculate validation metrics
        
        Returns:
          {
            'recall': % of breaches with prior alert,
            'precision': % of alerts that preceded breach,
            'fa_rate': false alerts per hour,
            'lead_time_mean': average time from alert to breach,
            'detected_breaches': number of breaches with alert,
            'missed_breaches': number of breaches without alert,
          }
        """
        metrics = {}
        
        # Count total breaches
        total_breaches = len(breach_events)
        
        # For each breach, check if there was an alert in the preceding LEAD_TIME_SAMPLES
        detected_breaches = 0
        lead_times = []
        
        for breach in breach_events:
            breach_start = breach['start_idx']
            lookback_start = max(0, breach_start - 10)  # Look back 200s
            
            # Find last alert before breach
            alert_indices = np.where(alerts[lookback_start:breach_start])[0]
            
            if len(alert_indices) > 0:
                detected_breaches += 1
                last_alert_idx = alert_indices[-1] + lookback_start
                lead_time_samples = breach_start - last_alert_idx
                lead_times.append(lead_time_samples * SAMPLE_INTERVAL_SECONDS)
        
        missed_breaches = total_breaches - detected_breaches
        
        # Recall: % of breaches with prior alert
        recall = detected_breaches / total_breaches if total_breaches > 0 else 0
        
        # False alarms: alerts not followed by breach
        num_alerts = alerts.sum()
        true_alerts = 0
        
        for alert_idx in np.where(alerts)[0]:
            # Check if breach occurs within 300s (15 samples) after alert
            lookahead = min(alert_idx + 15, len(df))
            if (df['p99_latency_ms'].iloc[alert_idx:lookahead] > SLO_THRESHOLD_MS).any():
                true_alerts += 1
        
        false_alarms = num_alerts - true_alerts
        
        # False alarm rate: per hour
        total_seconds = len(df) * SAMPLE_INTERVAL_SECONDS
        total_hours = total_seconds / 3600
        fa_rate = false_alarms / total_hours if total_hours > 0 else 0
        
        # Precision
        precision = true_alerts / num_alerts if num_alerts > 0 else 0
        
        # Mean lead time
        mean_lead_time = np.mean(lead_times) if lead_times else 0
        
        metrics['total_breaches'] = total_breaches
        metrics['detected_breaches'] = detected_breaches
        metrics['missed_breaches'] = missed_breaches
        metrics['recall'] = recall
        metrics['num_alerts'] = num_alerts
        metrics['true_alerts'] = true_alerts
        metrics['false_alarms'] = false_alarms
        metrics['fa_rate'] = fa_rate
        metrics['precision'] = precision
        metrics['mean_lead_time_s'] = mean_lead_time
        metrics['lead_times_s'] = lead_times
        metrics['total_hours'] = total_hours
        
        return metrics
    
    def validate(self, df: pd.DataFrame) -> Dict:
        """Run full validation"""
        print(f"[STEP 2] Generate alerts from delta PSI")
        print("-" * 100)
        
        alerts = self.generate_alerts(df)
        num_alerts = alerts.sum()
        alert_rate = 100 * num_alerts / len(df)
        
        print(f"✓ Generated alerts using |delta_psi| >= {DELTA_PSI_THRESHOLD}%")
        print(f"  Total alerts: {num_alerts}")
        print(f"  Alert rate: {alert_rate:.2f}% ({100*num_alerts/len(df):.3f}%)")
        print()
        
        print(f"[STEP 3] Identify SLO breach events")
        print("-" * 100)
        
        breach_events = self.identify_slo_breaches(df)
        total_breaches = len(breach_events)
        total_breach_samples = sum(b['duration_samples'] for b in breach_events)
        breach_rate = 100 * total_breach_samples / len(df)
        
        print(f"✓ Identified {total_breaches} SLO breach events (p99 > {SLO_THRESHOLD_MS}ms)")
        print(f"  Total samples in breaches: {total_breach_samples} ({breach_rate:.2f}%)")
        
        if breach_events:
            durations = [b['duration_samples'] for b in breach_events]
            print(f"  Breach duration: min={min(durations)}, mean={np.mean(durations):.1f}, max={max(durations)}")
            
            peak_latencies = [b['peak_latency_ms'] for b in breach_events]
            print(f"  Peak latency: min={min(peak_latencies):.2f}ms, mean={np.mean(peak_latencies):.2f}ms, max={max(peak_latencies):.2f}ms")
        print()
        
        print(f"[STEP 4] Calculate metrics")
        print("-" * 100)
        
        metrics = self.calculate_metrics(df, alerts, breach_events)
        
        print(f"✓ Calculated validation metrics")
        print()
        
        print(f"Detection Performance:")
        print(f"  Recall (detected breaches / total): {metrics['recall']:.4f} ({metrics['recall']*100:.2f}%)")
        print(f"    - Detected: {metrics['detected_breaches']}/{metrics['total_breaches']}")
        print(f"    - Missed: {metrics['missed_breaches']}/{metrics['total_breaches']}")
        print()
        print(f"False Alarm Performance:")
        print(f"  True alerts: {metrics['true_alerts']}/{metrics['num_alerts']}")
        print(f"  False alarms: {metrics['false_alarms']}/{metrics['num_alerts']}")
        print(f"  FA rate: {metrics['fa_rate']:.2f} per hour")
        print(f"  Precision: {metrics['precision']:.4f} ({metrics['precision']*100:.2f}%)")
        print()
        print(f"Lead Time:")
        print(f"  Mean: {metrics['mean_lead_time_s']:.1f}s")
        if metrics['lead_times_s']:
            print(f"  Min: {min(metrics['lead_times_s']):.1f}s")
            print(f"  P50: {np.median(metrics['lead_times_s']):.1f}s")
            print(f"  Max: {max(metrics['lead_times_s']):.1f}s")
        print()
        
        return metrics
    
    def check_criteria(self, metrics: Dict) -> Dict:
        """Check against pre-registered criteria"""
        print(f"[STEP 5] Check pre-registered criteria")
        print("-" * 100)
        
        criteria = {
            'recall': {
                'requirement': f">= {RECALL_MIN}",
                'value': metrics['recall'],
                'pass': metrics['recall'] >= RECALL_MIN
            },
            'fa_rate': {
                'requirement': f"<= {FA_RATE_MAX}/hour",
                'value': f"{metrics['fa_rate']:.2f}/hour",
                'pass': metrics['fa_rate'] <= FA_RATE_MAX
            },
            'precision': {
                'requirement': f">= {PRECISION_MIN}",
                'value': metrics['precision'],
                'pass': metrics['precision'] >= PRECISION_MIN
            }
        }
        
        print()
        all_pass = True
        for criterion_name, criterion in criteria.items():
            status = "✓ PASS" if criterion['pass'] else "✗ FAIL"
            print(f"{status} {criterion_name:20s}: {criterion['value']:>15} (requirement: {criterion['requirement']})")
            if not criterion['pass']:
                all_pass = False
        
        print()
        
        if all_pass:
            print("VERDICT: ✓ SUPPORTED")
            print("  Delta PSI >= 1.8% is a viable threshold for predicting p99 > 200ms SLO breaches")
        else:
            print("VERDICT: ✗ NOT_SUPPORTED")
            print("  Delta PSI >= 1.8% does not meet all validation criteria")
        
        print()
        
        metrics['criteria'] = criteria
        metrics['verdict'] = 'SUPPORTED' if all_pass else 'NOT_SUPPORTED'
        
        return metrics
    
    def save_results(self, df: pd.DataFrame, metrics: Dict) -> Path:
        """Save validation results"""
        print(f"[STEP 6] Save results")
        print("-" * 100)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        results_file = RESULTS_DIR / f"p99_200ms_validation_results_{timestamp}.json"
        
        results = {
            'timestamp': timestamp,
            'data_file': str(self.data_file),
            'config': {
                'delta_psi_threshold': DELTA_PSI_THRESHOLD,
                'slo_threshold_ms': SLO_THRESHOLD_MS,
                'sample_interval_seconds': SAMPLE_INTERVAL_SECONDS,
                'recall_min': RECALL_MIN,
                'fa_rate_max': FA_RATE_MAX,
                'precision_min': PRECISION_MIN,
            },
            'dataset_stats': {
                'total_samples': len(df),
                'duration_hours': len(df) * SAMPLE_INTERVAL_SECONDS / 3600,
                'psi_min': float(df['psi_some_avg10'].min()),
                'psi_p50': float(df['psi_some_avg10'].quantile(0.50)),
                'psi_p95': float(df['psi_some_avg10'].quantile(0.95)),
                'psi_max': float(df['psi_some_avg10'].max()),
                'delta_psi_min': float(df['delta_psi'].min()),
                'delta_psi_p50': float(df['delta_psi'].quantile(0.50)),
                'delta_psi_p95': float(df['delta_psi'].quantile(0.95)),
                'delta_psi_max': float(df['delta_psi'].max()),
                'latency_p99_min': float(df['p99_latency_ms'].min()),
                'latency_p99_p50': float(df['p99_latency_ms'].quantile(0.50)),
                'latency_p99_p95': float(df['p99_latency_ms'].quantile(0.95)),
                'latency_p99_max': float(df['p99_latency_ms'].max()),
            },
            'metrics': {
                'total_breaches': int(metrics['total_breaches']),
                'detected_breaches': int(metrics['detected_breaches']),
                'missed_breaches': int(metrics['missed_breaches']),
                'recall': float(metrics['recall']),
                'num_alerts': int(metrics['num_alerts']),
                'true_alerts': int(metrics['true_alerts']),
                'false_alarms': int(metrics['false_alarms']),
                'fa_rate': float(metrics['fa_rate']),
                'precision': float(metrics['precision']),
                'mean_lead_time_s': float(metrics['mean_lead_time_s']),
            },
            'criteria': {
                'recall': {
                    'requirement': RECALL_MIN,
                    'value': float(metrics['recall']),
                    'pass': bool(metrics['criteria']['recall']['pass'])
                },
                'fa_rate': {
                    'requirement': FA_RATE_MAX,
                    'value': float(metrics['fa_rate']),
                    'pass': bool(metrics['criteria']['fa_rate']['pass'])
                },
                'precision': {
                    'requirement': PRECISION_MIN,
                    'value': float(metrics['precision']),
                    'pass': bool(metrics['criteria']['precision']['pass'])
                }
            },
            'verdict': metrics['verdict']
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
        description="Validate delta PSI >= 1.8% threshold against synthetic p99 200ms latency data"
    )
    parser.add_argument("--data", type=str, required=True, help="Path to synthetic CSV file")
    args = parser.parse_args()
    
    # Run validation
    validator = DeltaPSIValidator(args.data)
    
    # Load data
    df = validator.load_data()
    
    # Run validation
    metrics = validator.validate(df)
    
    # Check criteria
    metrics = validator.check_criteria(metrics)
    
    # Save results
    validator.save_results(df, metrics)
    
    print("=" * 100)
    print(f"VALIDATION COMPLETE")
    print("=" * 100)
    print()

if __name__ == "__main__":
    main()
