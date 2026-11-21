#!/usr/bin/env python3
"""
Test 2: Pilot Design with Frozen Breach Rule

This script:
1. Takes a single session (20 min) of data from train.csv
2. Applies the frozen breach rule (latency > 2*B for 2+ consecutive bins)
3. Counts breach events
4. Reports event rate and decides if design needs adjustment

Pilot data is EXCLUDED from calibration and test.
This is strictly a sanity check on the frozen rule before running the full experiment.

FROZEN BREACH RULE (from Test 1):
  - B = 60.34 ms (median latency in calm rows)
  - Threshold = 2*B = 120.68 ms
  - Event = 2+ consecutive bins above threshold
  - Data source: train.csv rows (20s intervals)
  - Duration: pilot session = 1200s = 60 rows at 20s interval
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

print("=" * 70)
print("TEST 2: PILOT DESIGN WITH FROZEN BREACH RULE")
print("=" * 70)
print()

# Load training data (pilot will be a slice of this)
print("[STEP 1] Load training data")
print("-" * 70)

train_df = pd.read_csv(DATA_DIR / "train.csv")
print(f"Train data loaded: {len(train_df):,} rows")
print(f"Duration: {len(train_df) * 20 / 3600:.1f} hours")
print()

# Frozen parameters from Test 1
B = 60.34  # ms
THRESHOLD = 2 * B  # 120.68 ms

print(f"Frozen baseline B: {B:.2f} ms")
print(f"Frozen threshold (2*B): {THRESHOLD:.2f} ms")
print()

# Select pilot data: first 60 rows = 1200 seconds = 20 minutes
# (exclude rows with special segment/series boundaries)
print("[STEP 2] Extract pilot session (first 1200s = 20 min)")
print("-" * 70)

PILOT_ROWS = 60  # 60 rows * 20s = 1200s
pilot_df = train_df.iloc[:PILOT_ROWS].copy()

print(f"Pilot session: {len(pilot_df)} rows, {len(pilot_df)*20}s = {len(pilot_df)*20/60:.1f} min")
print(f"Timestamp range: {pilot_df['timestamp'].iloc[0]} to {pilot_df['timestamp'].iloc[-1]}")
print()

# Check what we have
print(f"Signal (psi_some_avg10) range:")
print(f"  Min: {pilot_df['psi_some_avg10'].min():.4f}%")
print(f"  Mean: {pilot_df['psi_some_avg10'].mean():.4f}%")
print(f"  Max: {pilot_df['psi_some_avg10'].max():.4f}%")
print()

print(f"Latency (latency_ms) range:")
print(f"  Min: {pilot_df['latency_ms'].min():.2f} ms")
print(f"  Mean: {pilot_df['latency_ms'].mean():.2f} ms")
print(f"  Max: {pilot_df['latency_ms'].max():.2f} ms")
print()

# Apply frozen breach rule
print("[STEP 3] Apply frozen breach rule")
print("-" * 70)
print(f"Rule: latency_ms > {THRESHOLD:.2f} ms for 2+ consecutive bins")
print()

# Mark which bins are above threshold
latency = pilot_df['latency_ms'].values
above_threshold = (latency > THRESHOLD).astype(int)

print(f"Bins above threshold: {above_threshold.sum()} / {len(latency)}")
print()

# Find consecutive groups (breach events)
breach_events = []
in_breach = False
breach_start_idx = None

for i in range(len(above_threshold)):
    if above_threshold[i] == 1:
        if not in_breach:
            # Start of a potential breach
            breach_start_idx = i
            in_breach = True
    else:
        if in_breach:
            # End of breach
            breach_end_idx = i - 1
            # Check if breach lasted at least 2 consecutive bins
            duration_bins = breach_end_idx - breach_start_idx + 1
            if duration_bins >= 2:
                breach_events.append({
                    'start_idx': breach_start_idx,
                    'end_idx': breach_end_idx,
                    'duration_bins': duration_bins,
                    'duration_sec': duration_bins * 20,
                    'peak_latency_ms': latency[breach_start_idx:breach_end_idx+1].max()
                })
            in_breach = False

# Handle case where breach extends to end of session
if in_breach:
    breach_end_idx = len(above_threshold) - 1
    duration_bins = breach_end_idx - breach_start_idx + 1
    if duration_bins >= 2:
        breach_events.append({
            'start_idx': breach_start_idx,
            'end_idx': breach_end_idx,
            'duration_bins': duration_bins,
            'duration_sec': duration_bins * 20,
            'peak_latency_ms': latency[breach_start_idx:breach_end_idx+1].max()
        })

print(f"Breach events detected: {len(breach_events)}")
print()

if len(breach_events) > 0:
    for idx, event in enumerate(breach_events, 1):
        print(f"Event {idx}:")
        print(f"  Bins: [{event['start_idx']}, {event['end_idx']}]")
        print(f"  Duration: {event['duration_bins']} bins = {event['duration_sec']} sec")
        print(f"  Peak latency: {event['peak_latency_ms']:.2f} ms")
        print()
else:
    print("No breach events detected.")
    print()

# Step 4: Event rate analysis
print("[STEP 4] Event rate and power analysis")
print("-" * 70)

pilot_duration_hours = len(pilot_df) * 20 / 3600
events_per_hour = len(breach_events) / pilot_duration_hours if pilot_duration_hours > 0 else 0

print(f"Pilot session duration: {pilot_duration_hours:.2f} hours")
print(f"Breach events: {len(breach_events)}")
print(f"Event rate: {events_per_hour:.2f} events/hour")
print()

# Power projection
CALIBRATION_HOURS = 115.2  # train.csv duration
TEST_HOURS = 28.8  # test.csv + validation.csv combined
TOTAL_HOURS = CALIBRATION_HOURS + TEST_HOURS

cal_events_projected = events_per_hour * CALIBRATION_HOURS
test_events_projected = events_per_hour * TEST_HOURS

print(f"Power projection (if rate continues):")
print(f"  Calibration ({CALIBRATION_HOURS:.1f}h): {cal_events_projected:.0f} events (target >= 25)")
print(f"  Test ({TEST_HOURS:.1f}h): {test_events_projected:.0f} events (target >= 15)")
print(f"  Total: {cal_events_projected + test_events_projected:.0f} events")
print()

# Decision
print("[STEP 5] Pilot Decision")
print("-" * 70)
print()

if len(breach_events) == 0:
    print("⚠️  WARNING: No breach events detected in pilot session!")
    print()
    print("Possible causes:")
    print("  1. First 20 minutes of data are too calm")
    print("  2. Threshold is too high (120.68 ms may be too stringent)")
    print("  3. Event rate is genuinely low in this workload")
    print()
    print("Recommendation:")
    print("  - Proceed to full experiment anyway (calibration uses full train.csv)")
    print("  - If full calibration also shows zero events, increase session duration")
    print("  - Or lower threshold (but only if justified by data)")
    print()
    decision = "PROCEED (but monitor)"
else:
    if cal_events_projected < 25 or test_events_projected < 15:
        print("⚠️  WARNING: Projected power is below target!")
        print()
        print("Recommendation:")
        print("  - Consider extending session duration")
        print("  - Or lowering threshold slightly")
        print()
        decision = "PROCEED WITH CAUTION"
    else:
        print("✓ PASS: Event rate is sufficient for power targets")
        print()
        decision = "PROCEED"

print()
print(f"PILOT DECISION: {decision}")
print()

# Summary table
print("[STEP 6] Summary")
print("-" * 70)
print()
print("FROZEN PARAMETERS:")
print(f"  Baseline B: {B:.2f} ms")
print(f"  Threshold (2*B): {THRESHOLD:.2f} ms")
print(f"  Event rule: 2+ consecutive bins above threshold")
print()
print("PILOT RESULTS:")
print(f"  Session duration: {pilot_duration_hours:.2f} hours")
print(f"  Breach events: {len(breach_events)}")
print(f"  Event rate: {events_per_hour:.2f} events/hour")
print()
print("POWER PROJECTION:")
print(f"  Calibration: {cal_events_projected:.0f} events (target 25+)")
print(f"  Test: {test_events_projected:.0f} events (target 15+)")
print()
print("NEXT STEPS:")
print("  1. If power is sufficient: proceed to full experiment")
print("  2. If power is low: adjust threshold or session duration (document deviation)")
print("  3. Freeze all decisions in prereg before running calibration/test sessions")
print()
print("=" * 70)

# Save pilot results
pilot_results = {
    'session_duration_hours': pilot_duration_hours,
    'breach_events': len(breach_events),
    'event_rate_per_hour': events_per_hour,
    'projected_calibration_events': cal_events_projected,
    'projected_test_events': test_events_projected,
    'decision': decision
}

print()
print("Pilot results computed. Ready for prereg freeze.")
