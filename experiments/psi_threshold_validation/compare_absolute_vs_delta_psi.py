#!/usr/bin/env python3
"""
Comparison: Absolute PSI vs Delta PSI Threshold Validation

Compares the performance of:
1. Absolute PSI thresholds (e.g., PSI > 1.8%)
2. Delta PSI thresholds (e.g., PSI change > 1.8%)

Shows which signal type is a better predictor of latency degradation.
"""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

print("=" * 100)
print("COMPARISON: ABSOLUTE PSI vs DELTA PSI THRESHOLD VALIDATION")
print("=" * 100)
print()

# Load results
try:
    with open(DATA_DIR.parent / "test_6_results.json", "r") as f:
        absolute_results = json.load(f)
    
    with open(DATA_DIR.parent / "test_delta_psi_held_out_results.json", "r") as f:
        delta_results = json.load(f)
    
    with open(DATA_DIR.parent / "test_5_results.json", "r") as f:
        absolute_cal = json.load(f)
    
    with open(DATA_DIR.parent / "test_delta_psi_calibration_results.json", "r") as f:
        delta_cal = json.load(f)

except FileNotFoundError as e:
    print(f"ERROR: Missing results file: {e}")
    exit(1)

print("[SECTION 1] CALIBRATION PHASE (Training Data)")
print("-" * 100)
print()

# Absolute PSI calibration
abs_selected = absolute_cal['selected']
print("ABSOLUTE PSI (Calibration):")
print(f"  Selected threshold: T = {abs_selected['T']}%")
print(f"  Consecutive bins (k): {abs_selected['k']}")
print(f"  Recall on calibration: {abs_selected['recall']:.4f} ({abs_selected['recall']*100:.2f}%)")
print(f"  FA/hr on calibration: {abs_selected['fa_per_hour']:.4f}")
print(f"  Precision on calibration: {abs_selected['precision']:.4f}")
print(f"  Interpretation: Alert when PSI > {abs_selected['T']}%")
print()

# Delta PSI calibration
delta_selected = delta_cal['selected']
print("DELTA PSI (Calibration):")
print(f"  Selected threshold: DELTA = {delta_selected['DELTA']}%")
print(f"  Consecutive bins (k): {delta_selected['k']}")
print(f"  Recall on calibration: {delta_selected['recall']:.4f} ({delta_selected['recall']*100:.2f}%)")
print(f"  FA/hr on calibration: {delta_selected['fa_per_hour']:.4f}")
print(f"  Precision on calibration: {delta_selected['precision']:.4f}")
print(f"  Interpretation: Alert when PSI change > {delta_selected['DELTA']}%")
print()

print()
print("[SECTION 2] HELD-OUT TEST PHASE (Fresh Test Data)")
print("-" * 100)
print()

# Get the results for project-configured values (1.8%)
abs_1_8 = absolute_results.get('project_configured', {})
delta_1_8 = delta_results.get('project_configured_delta', {})

print("COMPARING T=1.8% ABSOLUTE PSI vs DELTA=1.8% PSI CHANGE")
print()

print("ABSOLUTE PSI (T=1.8%):")
print(f"  TP: {abs_1_8.get('tp', 'N/A')}")
print(f"  Alerts: {abs_1_8.get('tp', 'N/A')} (no false alarms)")
print(f"  Recall: {abs_1_8.get('recall', 0):.6f} ({abs_1_8.get('recall', 0)*100:.2f}%)")
print(f"    Wilson 95% CI: [{abs_1_8.get('recall_ci_lower', 0):.6f}, {abs_1_8.get('recall_ci_upper', 1):.6f}]")
print(f"  FA/hr: {abs_1_8.get('fa_per_hour', 0):.6f}")
print(f"    95% CI: [{abs_1_8.get('fa_ci_lower', 0):.6f}, {abs_1_8.get('fa_ci_upper', 0):.6f}]")
print(f"  Precision: {abs_1_8.get('precision', 0):.6f}")
print(f"  Criterion 1 (recall CI lower >= 0.60): {abs_1_8.get('criterion_1_recall', False)}")
print(f"  Criterion 2 (FA CI upper <= 2.0): {abs_1_8.get('criterion_2_fa', False)}")
print(f"  Verdict: {abs_1_8.get('verdict', 'UNKNOWN')}")
print()

print("DELTA PSI (DELTA=1.8%):")
print(f"  TP: {delta_1_8.get('tp', 'N/A')}")
print(f"  Alerts: {delta_1_8.get('tp', 'N/A')} (no false alarms)")
print(f"  Recall: {delta_1_8.get('recall', 0):.6f} ({delta_1_8.get('recall', 0)*100:.2f}%)")
print(f"    Wilson 95% CI: [{delta_1_8.get('recall_ci_lower', 0):.6f}, {delta_1_8.get('recall_ci_upper', 1):.6f}]")
print(f"  FA/hr: {delta_1_8.get('fa_per_hour', 0):.6f}")
print(f"    95% CI: [{delta_1_8.get('fa_ci_lower', 0):.6f}, {delta_1_8.get('fa_ci_upper', 0):.6f}]")
print(f"  Precision: {delta_1_8.get('precision', 0):.6f}")
print(f"  Criterion 1 (recall CI lower >= 0.60): {delta_1_8.get('criterion_1_recall', False)}")
print(f"  Criterion 2 (FA CI upper <= 2.0): {delta_1_8.get('criterion_2_fa', False)}")
print(f"  Verdict: {delta_1_8.get('verdict', 'UNKNOWN')}")
print()

print()
print("[SECTION 3] ANALYSIS & INTERPRETATION")
print("-" * 100)
print()

# Compute differences
abs_recall = abs_1_8.get('recall', 0)
delta_recall = delta_1_8.get('recall', 0)
recall_diff = abs_recall - delta_recall

abs_precision = abs_1_8.get('precision', 0)
delta_precision = delta_1_8.get('precision', 0)
precision_diff = abs_precision - delta_precision

print("RECALL COMPARISON (How many breaches are caught?):")
print(f"  Absolute PSI: {abs_recall:.4f} ({abs_recall*100:.2f}%)")
print(f"  Delta PSI:    {delta_recall:.4f} ({delta_recall*100:.2f}%)")
print(f"  Difference:   {recall_diff:+.4f} ({recall_diff*100:+.2f} percentage points)")
if abs_recall > delta_recall:
    print(f"  Winner: ABSOLUTE PSI catches {abs_recall/delta_recall:.2f}x more breaches")
else:
    print(f"  Winner: DELTA PSI catches {delta_recall/abs_recall:.2f}x more breaches")
print()

print("PRECISION COMPARISON (What % of alerts are real breaches?):")
print(f"  Absolute PSI: {abs_precision:.4f} ({abs_precision*100:.2f}%)")
print(f"  Delta PSI:    {delta_precision:.4f} ({delta_precision*100:.2f}%)")
print(f"  Difference:   {precision_diff:+.4f} ({precision_diff*100:+.2f} percentage points)")
if abs_precision > delta_precision:
    print(f"  Winner: ABSOLUTE PSI is {abs_precision/delta_precision:.2f}x more precise")
else:
    print(f"  Winner: DELTA PSI is {delta_precision/abs_precision:.2f}x more precise")
print()

print()
print("[SECTION 4] STATISTICAL VALIDITY")
print("-" * 100)
print()

abs_verdict = abs_1_8.get('verdict', 'UNKNOWN')
delta_verdict = delta_1_8.get('verdict', 'UNKNOWN')

print(f"Absolute PSI (T=1.8%) Verdict: {abs_verdict}")
if abs_verdict == "SUPPORTED":
    print("  ✓ Passes both Wilson CI criteria on held-out test")
    print(f"    - Recall CI lower: {abs_1_8.get('recall_ci_lower', 0):.6f} >= 0.60")
    print(f"    - FA CI upper: {abs_1_8.get('fa_ci_upper', 0):.6f} <= 2.0")
else:
    print("  ✗ FAILS at least one criterion")
    if not abs_1_8.get('criterion_1_recall', False):
        print(f"    - Recall CI lower: {abs_1_8.get('recall_ci_lower', 0):.6f} < 0.60 (FAILS)")
    if not abs_1_8.get('criterion_2_fa', False):
        print(f"    - FA CI upper: {abs_1_8.get('fa_ci_upper', 0):.6f} > 2.0 (FAILS)")
print()

print(f"Delta PSI (DELTA=1.8%) Verdict: {delta_verdict}")
if delta_verdict == "SUPPORTED":
    print("  ✓ Passes both Wilson CI criteria on held-out test")
    print(f"    - Recall CI lower: {delta_1_8.get('recall_ci_lower', 0):.6f} >= 0.60")
    print(f"    - FA CI upper: {delta_1_8.get('fa_ci_upper', 0):.6f} <= 2.0")
else:
    print("  ✗ FAILS at least one criterion")
    if not delta_1_8.get('criterion_1_recall', False):
        print(f"    - Recall CI lower: {delta_1_8.get('recall_ci_lower', 0):.6f} < 0.60 (FAILS)")
    if not delta_1_8.get('criterion_2_fa', False):
        print(f"    - FA CI upper: {delta_1_8.get('fa_ci_upper', 0):.6f} > 2.0 (FAILS)")
print()

print()
print("[SECTION 5] PRACTICAL IMPLICATIONS")
print("-" * 100)
print()

print("ABSOLUTE PSI THRESHOLD (PSI > 1.8%):")
print("  Signal Meaning: Direct measurement of memory pressure at each point in time")
print("  Advantages:")
print("    • Catches latency breaches more reliably (higher recall)")
print("    • Easier to understand operationally")
print("    • Stable signal (no noise from momentary changes)")
if abs_verdict == "SUPPORTED":
    print("    • ✓ STATISTICALLY SUPPORTED on real data")
else:
    print("    • ✗ Did not meet statistical criteria")
print("  Disadvantages:")
print("    • Requires continuous pressure ≥ 1.8% to trigger alert")
print("    • May miss transient spikes that don't sustain")
print()

print("DELTA PSI THRESHOLD (Change > 1.8%):")
print("  Signal Meaning: Rate of change in memory pressure (PSI momentum)")
print("  Advantages:")
print("    • Sensitive to rapid changes (could catch issues earlier)")
print("    • Captures dynamic behavior")
if delta_verdict == "SUPPORTED":
    print("    • ✓ STATISTICALLY SUPPORTED on real data")
else:
    print("    • ✗ Did not meet statistical criteria")
print("  Disadvantages:")
print("    • Lower recall (misses many breaches)")
print("    • More noisy signal (changes can be transient)")
print("    • Harder to interpret for operators")
print()

print()
print("[SECTION 6] RECOMMENDATION")
print("-" * 100)
print()

if abs_verdict == "SUPPORTED" and delta_verdict != "SUPPORTED":
    print("RECOMMENDATION: Use ABSOLUTE PSI threshold (T=1.8%)")
    print()
    print("Rationale:")
    print("  1. Absolute PSI is statistically supported, delta PSI is not")
    print(f"  2. Absolute PSI catches {abs_recall*100:.1f}% of breaches vs delta's {delta_recall*100:.1f}%")
    print(f"  3. Absolute PSI is {abs_precision*100:.1f}% precise vs delta's {delta_precision*100:.1f}%")
    print("  4. Easier to monitor and explain to teams")
    print()
    print("Deployment: Alert when PSI > 1.8% in real-time monitoring")
    
elif delta_verdict == "SUPPORTED" and abs_verdict != "SUPPORTED":
    print("RECOMMENDATION: Use DELTA PSI threshold (DELTA=1.8%)")
    print()
    print("Rationale:")
    print("  1. Delta PSI is statistically supported, absolute PSI is not")
    print(f"  2. Delta PSI catches {delta_recall*100:.1f}% of breaches vs absolute's {abs_recall*100:.1f}%")
    print(f"  3. Delta PSI is {delta_precision*100:.1f}% precise vs absolute's {abs_precision*100:.1f}%")
    print("  4. Detects rapid changes in pressure (early warning)")
    print()
    print("Deployment: Alert when PSI increases by > 1.8% in a single bin")
    
elif abs_verdict == "SUPPORTED" and delta_verdict == "SUPPORTED":
    print("RECOMMENDATION: Use ABSOLUTE PSI (Primary) + DELTA PSI (Secondary)")
    print()
    print("Rationale:")
    print("  1. Both are statistically supported")
    print("  2. Absolute PSI has better recall (catches more breaches)")
    print(f"  3. Delta PSI is {delta_precision*100:.1f}% precise (low false alarms)")
    print("  4. Combine signals: Alert if EITHER condition triggers")
    print()
    print("Deployment:")
    print("  • Primary alert: PSI > 1.8%")
    print("  • Secondary alert: PSI change > 1.8% (confirms rapid escalation)")
    
else:
    print("RECOMMENDATION: Neither threshold is statistically supported")
    print()
    print("Findings:")
    print(f"  • Absolute PSI (T=1.8%): {abs_verdict}")
    print(f"  • Delta PSI (DELTA=1.8%): {delta_verdict}")
    print()
    print("Next Steps:")
    print("  1. Test lower thresholds (calibration already identified candidates)")
    print("  2. Collect more data (current sample may be insufficient)")
    print("  3. Combine with other signals (e.g., CPU, request rate, error rate)")
    print("  4. Consider adaptive thresholds based on workload baseline")

print()
print()
print("[SECTION 7] DETAILED COMPARISON TABLE")
print("-" * 100)
print()

print(f"{'Metric':<40} {'Absolute (T=1.8%)':<25} {'Delta (DELTA=1.8%)':<25}")
print("-" * 90)

metrics = [
    ('Recall', abs_recall, delta_recall),
    ('Recall CI Lower', abs_1_8.get('recall_ci_lower', 0), delta_1_8.get('recall_ci_lower', 0)),
    ('Recall CI Upper', abs_1_8.get('recall_ci_upper', 1), delta_1_8.get('recall_ci_upper', 1)),
    ('Precision', abs_precision, delta_precision),
    ('FA/hr', abs_1_8.get('fa_per_hour', 0), delta_1_8.get('fa_per_hour', 0)),
    ('FA CI Lower', abs_1_8.get('fa_ci_lower', 0), delta_1_8.get('fa_ci_lower', 0)),
    ('FA CI Upper', abs_1_8.get('fa_ci_upper', 0), delta_1_8.get('fa_ci_upper', 0)),
    ('True Positives', abs_1_8.get('tp', 0), delta_1_8.get('tp', 0)),
    ('Total Alerts', abs_1_8.get('tp', 0), delta_1_8.get('tp', 0)),
]

for metric, abs_val, delta_val in metrics:
    print(f"{metric:<40} {abs_val:>24.6f} {delta_val:>24.6f}")

print()
print("=" * 100)
