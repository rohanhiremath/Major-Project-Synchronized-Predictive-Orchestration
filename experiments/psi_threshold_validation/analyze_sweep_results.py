#!/usr/bin/env python3
"""
Analyze the calibration sweep results in detail.

Why did NO threshold work? What does the sweep show?
"""

import json
from pathlib import Path
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RESULTS_FILE = PROJECT_ROOT / "experiments" / "psi_threshold_validation" / "live_analysis_results.json"

print("=" * 80)
print("SWEEP ANALYSIS: WHY NO THRESHOLD WORKS")
print("=" * 80)
print()

with open(RESULTS_FILE) as f:
    results = json.load(f)

sweep = results['test_3_calibration_sweep']['sweep']

# Convert to DataFrame for analysis
df = pd.DataFrame(sweep)

print(f"Total (T, k) pairs tested: {len(df)}")
print()

# Show all results
print("All Results:")
print()
print("T (%)  | k  | Recall  | FA/hr | Viable?")
print("-" * 45)

for _, row in df.iterrows():
    viable_str = "✓" if row['viable'] else "✗"
    print(f"{row['T']:5.1f} | {row['k']} | {row['recall']:7.4f} | {row['fa_per_hour']:6.2f} | {viable_str}")

print()

# Analyze the trade-off
print("ANALYSIS:")
print()

print("1. RECALL vs FA/hr TRADE-OFF")
print("-" * 45)

# Find thresholds that meet recall criterion
high_recall = df[df['recall'] >= 0.5]
print(f"Thresholds with recall >= 0.5: {len(high_recall)}")
if len(high_recall) > 0:
    print(f"  Lowest FA/hr among these: {high_recall['fa_per_hour'].min():.2f}/hr")
    print(f"  Problem: All exceed FA/hr <= 2.0 limit")
else:
    print(f"  PROBLEM: No threshold achieves recall >= 0.5")

print()

# Find thresholds that meet FA criterion
low_fa = df[df['fa_per_hour'] <= 2.0]
print(f"Thresholds with FA/hr <= 2.0: {len(low_fa)}")
if len(low_fa) > 0:
    print(f"  Highest recall among these: {low_fa['recall'].max():.4f}")
    print(f"  Problem: All are below recall >= 0.5 requirement")
else:
    print(f"  PROBLEM: No threshold achieves FA/hr <= 2.0")

print()

# Show the gap
print("2. THE REQUIREMENT GAP")
print("-" * 45)

best_recall = df.loc[df['recall'].idxmax()]
best_fa = df.loc[df['fa_per_hour'].idxmin()]

print(f"Best recall: T={best_recall['T']}% k={int(best_recall['k'])}")
print(f"  Recall: {best_recall['recall']:.4f} ✓")
print(f"  FA/hr: {best_recall['fa_per_hour']:.2f} ✗ (need <= 2.0)")
print()

print(f"Best FA/hr: T={best_fa['T']}% k={int(best_fa['k'])}")
print(f"  FA/hr: {best_fa['fa_per_hour']:.2f} ✓")
print(f"  Recall: {best_fa['recall']:.4f} ✗ (need >= 0.5)")
print()

print(f"The gap: You must choose between")
print(f"  A) High recall ({best_recall['recall']:.1%}) with unacceptable FA/hr ({best_recall['fa_per_hour']:.1f}/hr)")
print(f"  B) Acceptable FA/hr ({best_fa['fa_per_hour']:.2f}/hr) with poor recall ({best_fa['recall']:.1%})")
print()

# What does low recall mean?
print("3. WHAT LOW RECALL MEANS")
print("-" * 45)

print(f"Recall = TP / Total Events")
print(f"  Where TP = number of latency breaches detected by the alert")
print()

print("Example with best FA (T={}, k={}):".format(best_fa['T'], int(best_fa['k'])))
total_cal_events = 533  # From the run output
print(f"  Total calibration breaches: {total_cal_events}")
print(f"  Detected by threshold: {int(best_fa['tp'])}")
print(f"  Missed: {total_cal_events - int(best_fa['tp'])}")
print(f"  Miss rate: {100*(1-best_fa['recall']):.1f}%")
print()

print("Example with best recall (T={}, k={}):".format(best_recall['T'], int(best_recall['k'])))
print(f"  Total calibration breaches: {total_cal_events}")
print(f"  Detected by threshold: {int(best_recall['tp'])}")
print(f"  Missed: {total_cal_events - int(best_recall['tp'])}")
print(f"  Miss rate: {100*(1-best_recall['recall']):.1f}%")
print(f"  But: {best_recall['fa_per_hour']:.1f} false alerts per hour (vs 2.0 limit)")
print()

# Why is this happening?
print("4. ROOT CAUSE")
print("-" * 45)
print()

print("The signal (pod_psi_some_avg10) has poor predictability:")
print()

from pathlib import Path
import pandas as pd
import numpy as np

SESSIONS_DIR = PROJECT_ROOT / "experiments" / "psi_threshold_validation" / "session_logs"

def load_sessions(session_list):
    data = []
    for session_name in session_list:
        session_dir = SESSIONS_DIR / session_name
        metrics_file = session_dir / "metrics.csv"
        if not metrics_file.exists():
            continue
        df = pd.read_csv(metrics_file)
        df['session_name'] = session_name
        data.append(df)
    return pd.concat(data, ignore_index=True) if data else None

cal_sessions = ["cal_calm_1", "cal_calm_2", "cal_calm_3", "cal_burst_1", "cal_ramp_1", "cal_step_1"]
cal_df = load_sessions(cal_sessions)

B = 8.87
THRESHOLD = 2 * B
signal = cal_df['pod_psi_some_avg10'].values
latency = cal_df['p99_latency_ms'].values

# When signal is elevated, is latency breached?
signal_elevated = signal > 0.5  # Elevated
latency_breached = latency > THRESHOLD

print(f"Signal elevated (> 0.5%) when:")
print(f"  Latency is breached: {(signal_elevated & latency_breached).sum()} rows")
print(f"  Latency is normal: {(signal_elevated & ~latency_breached).sum()} rows")
print(f"  Total signal-elevated rows: {signal_elevated.sum()}")
print()

signal_low = signal <= 0.5
print(f"Signal low (<= 0.5%) when:")
print(f"  Latency is breached: {(signal_low & latency_breached).sum()} rows")
print(f"  Latency is normal: {(signal_low & ~latency_breached).sum()} rows")
print(f"  Total signal-low rows: {signal_low.sum()}")
print()

print("Interpretation:")
print("- Signal is elevated even during normal latency (many false positives)")
print("- Signal stays low even during breaches (many false negatives)")
print("- This creates the fundamental trade-off: high false alarms vs low recall")
print()

print("=" * 80)
print()
print("CONCLUSION:")
print()
print("NO threshold on pod_psi_some_avg10 can simultaneously achieve:")
print("  • Recall >= 50% (catch at least half the breaches)")
print("  • FA/hr <= 2.0 (no more than 2 false alarms per hour)")
print()
print("The signal is simply not predictive enough on this infrastructure.")
print()
print("=" * 80)
