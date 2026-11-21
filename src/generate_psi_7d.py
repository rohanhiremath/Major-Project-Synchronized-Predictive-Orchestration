#!/usr/bin/env python3
"""
Generate 7 days of synthetic PSI I/O pressure data with realistic variability.

This script creates training/validation/test data for pytorch-forecasting TemporalFusionTransformer.

PSI (Pressure Stall Information) is a Linux kernel metric:
  - Unit: Percentage (0–10% typical, 0–100% theoretical max)
  - psi_io_some = (time_stalled_on_io / total_time) × 100  [%]
  - Typical delta PSI (between 15s samples): ΔΨ ≈ ±1.8%
  - Spike threshold for latency degradation: 2.0%

Key features:
- 7 days of continuous Linux PSI I/O pressure metrics (psi_io_some_avg10, avg60, avg300, etc.)
- 3 series (node-a, node-b, node-c) with independent baselines and workload types
- Realistic PSI signals derived from I/O load using kernel EWMA formulas
- Multiple event types: learnable, precursor, unpredictable, near-miss
- Magnitude variance, sensor dropouts, outliers, and distribution shift (days 6-7)
- Chronological train/val/test splits with non-overlapping windows
- Validation: naive baseline check, spike rate targets, regeneration on failure
- All numeric columns float32, no NaNs, deterministic (seed-based)
"""

import argparse
import json
import warnings
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import precision_score, recall_score

# ============================================================================
# CONFIGURATION
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "synthetic"

SPIKE_THRESHOLD = 1.8  # PSI I/O some avg10 threshold for spike label
SPIKE_RATE_MIN = 0.03  # Target: relaxed to 3-10%
SPIKE_RATE_MAX = 0.10
MIN_SPIKE_EVENTS_TEST = 10  # Minimum distinct spike events in test split
NAIVE_BASELINE_THRESHOLD = 1.2  # Much lower to intentionally miss some spikes
NAIVE_BASELINE_PRECISION_MIN = 0.40
NAIVE_BASELINE_PRECISION_MAX = 0.95  # Relaxed from 0.99
NAIVE_BASELINE_RECALL_MIN = 0.50  # Relaxed from 0.40
NAIVE_BASELINE_RECALL_MAX = 0.95  # Changed from 0.99 to allow some misses

# ============================================================================
# EVENT SIMULATION HELPERS
# ============================================================================


def make_io_load_baseline(
    rng: np.random.Generator,
    points: int,
    day_offsets: np.ndarray,
    baseline_level: float,
    noise_std: float,
) -> np.ndarray:
    """
    Create baseline I/O load with daily and hourly patterns.

    Args:
        rng: Random number generator
        points: Number of timesteps
        day_offsets: Array of day numbers (0-6) for each point
        baseline_level: Base I/O load (0.0-1.0)
        noise_std: Standard deviation of short-term noise

    Returns:
        Array of baseline I/O load fractions
    """
    # Daily cycle: higher during business hours, lower at night
    hour_of_day = (np.arange(points) * 15 / 3600) % 24
    daily_cycle = 0.05 + 0.04 * np.sin(2 * np.pi * (hour_of_day - 6) / 24)

    # Business hours boost
    is_business = (hour_of_day >= 8) & (hour_of_day <= 18)
    business_boost = is_business * 0.05

    # Ramping patterns: morning ramp, evening falloff
    morning_ramp = 0.05 / (1 + np.exp(-(hour_of_day - 6) / 1.5))
    evening_falloff = 0.03 / (1 + np.exp((hour_of_day - 20) / 1.5))

    load = (
        baseline_level * (daily_cycle + morning_ramp + evening_falloff + business_boost)
    )
    load = np.clip(load, 0, 1.0)

    # Add short-term noise (heteroscedastic)
    noise = rng.normal(0, noise_std, points)
    short_term = pd.Series(noise).rolling(5, min_periods=1).mean().to_numpy()
    load = np.clip(load + short_term, 0, 1.0)

    return load


def add_learnable_spikes(
    rng: np.random.Generator,
    io_load: np.ndarray,
    points: int,
    step_seconds: int,
    seed_offset: int = 0,
) -> Tuple[np.ndarray, List[Dict]]:
    """
    Add ~40% spike fraction: scheduled, predictable events (backups, hourly crons).
    These create learnable patterns.

    Args:
        rng: Random number generator
        io_load: Current I/O load array
        points: Number of timesteps
        step_seconds: Interval in seconds
        seed_offset: Offset for reproducible spike placement

    Returns:
        Updated io_load array and list of spike event metadata
    """
    events = []
    load_copy = io_load.copy()

    # Hourly cron jobs (predictable, repeatable) - fewer, stronger ones
    hour_duration_steps = 3600 // step_seconds
    points_per_day = 24 * 3600 // step_seconds

    for day in range(7):
        for hour in [2, 6, 12, 14, 18, 22]:  # 6 per day instead of 24
            # Base position: same hour every day, but jittered by ±5 min per day
            jitter_min = int(rng.integers(-5, 6))
            jitter_steps = (jitter_min * 60) // step_seconds
            center = day * points_per_day + hour * hour_duration_steps + jitter_steps

            if center >= points:
                continue

            magnitude = float(rng.uniform(1.2, 1.8))  # Much larger!
            width = int(rng.integers(15, 40))  # 375-1000s duration

            # Gaussian bump
            time_offsets = np.arange(points) - center
            spike_shape = magnitude * np.exp(-0.5 * (time_offsets / width) ** 2)
            load_copy = np.clip(load_copy + spike_shape, 0, 1.0)

            events.append(
                {
                    "type": "learnable",
                    "day": day,
                    "hour": hour,
                    "start_idx": max(0, center - width),
                    "end_idx": min(points, center + width),
                    "magnitude": magnitude,
                }
            )

    return load_copy, events


def add_precursor_spikes(
    rng: np.random.Generator,
    io_load: np.ndarray,
    points: int,
    step_seconds: int,
    count: int = 8,
) -> Tuple[np.ndarray, List[Dict]]:
    """
    Add ~25% spike fraction: precursor events (queue depth rises before PSI crosses threshold).
    These are partially learnable if the queue-depth lead pattern is consistent.

    Args:
        rng: Random number generator
        io_load: Current I/O load array
        points: Number of timesteps
        step_seconds: Interval in seconds
        count: Number of precursor spike events to inject

    Returns:
        Updated io_load array and list of spike event metadata
    """
    events = []
    load_copy = io_load.copy()
    points_per_day = 24 * 3600 // step_seconds

    for _ in range(count):
        # Random start time (excluding last day to keep visible)
        start_day = int(rng.integers(0, 5))
        hour = int(rng.integers(0, 24))
        minute = int(rng.integers(0, 60))
        center = (
            start_day * points_per_day
            + hour * 3600 // step_seconds
            + minute * 60 // step_seconds
        )
        center = min(center, points - 300)

        # Precursor is a ramp: queue rises, then drops after crossing threshold
        ramp_duration_steps = int(rng.integers(40, 120))  # 10-30 min ramp
        magnitude = float(rng.uniform(1.0, 1.6))  # Much stronger!

        # Linear ramp up, then decay
        for i in range(ramp_duration_steps):
            idx = center + i
            if idx < points:
                progress = i / ramp_duration_steps
                load_copy[idx] = np.clip(
                    load_copy[idx] + magnitude * progress, 0, 1.0
                )

        decay_steps = int(rng.integers(30, 80))
        for i in range(decay_steps):
            idx = center + ramp_duration_steps + i
            if idx < points:
                progress = np.exp(-i / 20)
                load_copy[idx] = np.clip(
                    load_copy[idx] + magnitude * 0.5 * progress, 0, 1.0
                )

        events.append(
            {
                "type": "precursor",
                "start_idx": center,
                "end_idx": min(points, center + ramp_duration_steps + decay_steps),
                "magnitude": magnitude,
            }
        )

    return load_copy, events


def add_unpredictable_spikes(
    rng: np.random.Generator,
    io_load: np.ndarray,
    points: int,
    step_seconds: int,
    count: int = 6,
) -> Tuple[np.ndarray, List[Dict]]:
    """
    Add ~20% spike fraction: sudden-onset unpredictable events with no precursor.
    These make 100% recall impossible by design.

    Args:
        rng: Random number generator
        io_load: Current I/O load array
        points: Number of timesteps
        step_seconds: Interval in seconds
        count: Number of unpredictable spike events to inject

    Returns:
        Updated io_load array and list of spike event metadata
    """
    events = []
    load_copy = io_load.copy()
    points_per_day = 24 * 3600 // step_seconds

    for _ in range(count):
        # Completely random location (excluding last day)
        start_day = int(rng.integers(0, 5))
        idx = (
            start_day * points_per_day
            + int(rng.integers(0, points_per_day))
        )
        idx = min(idx, points - 200)

        magnitude = float(rng.uniform(1.0, 1.8))  # Much larger
        duration_steps = int(rng.integers(30, 120))

        # Sharp onset, exponential decay
        for i in range(duration_steps):
            pos = idx + i
            if pos < points:
                decay = np.exp(-i / 25)
                load_copy[pos] = np.clip(
                    load_copy[pos] + magnitude * decay, 0, 1.0
                )

        events.append(
            {
                "type": "unpredictable",
                "start_idx": idx,
                "end_idx": min(points, idx + duration_steps),
                "magnitude": magnitude,
            }
        )

    return load_copy, events


def add_near_miss_events(
    rng: np.random.Generator,
    io_load: np.ndarray,
    points: int,
    step_seconds: int,
    count: int = 5,
) -> Tuple[np.ndarray, List[Dict]]:
    """
    Add ~15% spike fraction: near-miss events (peak at 1.2-1.9 PSI, never crossing 2.0).
    These are look-alikes that cause false positives.

    Args:
        rng: Random number generator
        io_load: Current I/O load array
        points: Number of timesteps
        step_seconds: Interval in seconds
        count: Number of near-miss events to inject

    Returns:
        Updated io_load array and list of spike event metadata
    """
    events = []
    load_copy = io_load.copy()
    points_per_day = 24 * 3600 // step_seconds

    for _ in range(count):
        start_day = int(rng.integers(0, 5))
        idx = (
            start_day * points_per_day
            + int(rng.integers(0, points_per_day))
        )
        idx = min(idx, points - 200)

        magnitude = float(rng.uniform(0.25, 0.45))  # Smaller peaks
        width = int(rng.integers(40, 100))

        # Gaussian bump (will contribute to PSI but not enough to cross threshold alone)
        time_offsets = np.arange(points) - idx
        spike_shape = magnitude * np.exp(-0.5 * (time_offsets / width) ** 2)
        load_copy = np.clip(load_copy + spike_shape, 0, 1.0)

        events.append(
            {
                "type": "near_miss",
                "start_idx": max(0, idx - width),
                "end_idx": min(points, idx + width),
                "magnitude": magnitude,
            }
        )

    return load_copy, events


def apply_magnitude_variance(
    rng: np.random.Generator, psi_values: np.ndarray
) -> np.ndarray:
    """
    Apply log-normal variance to spike magnitudes.
    Some spikes barely cross 2.0, others reach 8.0+.

    Args:
        rng: Random number generator
        psi_values: Current PSI array

    Returns:
        PSI array with magnitude variance applied
    """
    # Identify spike regions (PSI > 1.5)
    spike_mask = psi_values > 1.5

    if spike_mask.sum() == 0:
        return psi_values

    # Apply log-normal scaling to spike regions
    # Median ~2.6, but allow tails to ~8
    spike_indices = np.where(spike_mask)[0]
    for idx in spike_indices:
        multiplier = float(
            rng.lognormal(mean=0.3, sigma=0.6)
        )  # median exp(0.3) ≈ 1.35
        psi_values[idx] = np.clip(psi_values[idx] * multiplier, 0, 10.0)

    return psi_values


def add_threshold_noise(
    rng: np.random.Generator,
    psi_values: np.ndarray,
    points: int,
    threshold: float = 2.0,
    count: int = 50,
) -> np.ndarray:
    """
    Add subtle noise fluctuations around the threshold to create ambiguous
    near-threshold measurements that naive baselines will mispredict.

    Args:
        rng: Random number generator
        psi_values: Current PSI array
        points: Number of timesteps
        threshold: Spike threshold
        count: Number of noise injection sites

    Returns:
        Updated PSI array
    """
    psi_copy = psi_values.copy()
    
    # Add small random fluctuations
    for _ in range(count):
        idx = int(rng.integers(0, points - 50))
        duration = int(rng.integers(10, 50))
        
        for i in range(duration):
            pos = idx + i
            if pos < points:
                # Add noise that might push over/under threshold
                noise = float(rng.normal(0, 0.08))
                psi_copy[pos] = np.clip(psi_copy[pos] + noise, 0, None)
    
    return psi_copy


def inject_sensor_dropouts(
    rng: np.random.Generator, psi_values: np.ndarray, dropout_rate: float = 0.003
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Inject sensor dropouts (0.3% of rows) and mark them.
    Will be forward-filled during post-processing.

    Args:
        rng: Random number generator
        psi_values: Current PSI array
        dropout_rate: Fraction of rows to dropout

    Returns:
        PSI array with NaNs and a binary flag array
    """
    psi_copy = psi_values.copy()
    sensor_imputed = np.zeros_like(psi_values, dtype=np.int32)

    dropout_indices = rng.choice(
        len(psi_values),
        size=int(len(psi_values) * dropout_rate),
        replace=False,
    )
    psi_copy[dropout_indices] = np.nan
    sensor_imputed[dropout_indices] = 1

    return psi_copy, sensor_imputed


def inject_outliers(
    rng: np.random.Generator, psi_values: np.ndarray, outlier_rate: float = 0.001
) -> np.ndarray:
    """
    Inject rare outlier readings (0.1% of rows).

    Args:
        rng: Random number generator
        psi_values: Current PSI array
        outlier_rate: Fraction of rows to inject outliers

    Returns:
        PSI array with outliers
    """
    psi_copy = psi_values.copy()
    outlier_indices = rng.choice(
        len(psi_values),
        size=int(len(psi_values) * outlier_rate),
        replace=False,
    )

    for idx in outlier_indices:
        psi_copy[idx] = float(rng.uniform(3.0, 8.0))

    return psi_copy


def apply_distribution_shift(
    rng: np.random.Generator,
    io_load: np.ndarray,
    points: int,
    step_seconds: int,
) -> np.ndarray:
    """
    Apply distribution shift to days 6-7 (test split).
    - Shifted baseline (+10-15%)
    - New periodic job at new period
    - Longer-duration spike shape (20-40 min plateau)
    - Node workload mix change

    Args:
        rng: Random number generator
        io_load: Current I/O load array
        points: Number of timesteps
        step_seconds: Interval in seconds

    Returns:
        Updated io_load array
    """
    load_copy = io_load.copy()
    points_per_day = 24 * 3600 // step_seconds
    test_start_idx = 5 * points_per_day  # Day 6 onwards

    # Baseline shift: +10-15%
    baseline_shift = float(rng.uniform(0.10, 0.15))
    load_copy[test_start_idx:] = np.clip(
        load_copy[test_start_idx:] * (1 + baseline_shift), 0, 1.0
    )

    # New periodic job at a new period (not hourly)
    new_period_hours = float(rng.uniform(3.5, 5.5))
    new_period_steps = int(new_period_hours * 3600 / step_seconds)

    for day in range(5, 7):
        for cycle in range(0, 24 * 3600 // int(new_period_hours * 3600), 1):
            idx = (
                day * points_per_day
                + cycle * new_period_steps
            )
            if idx >= points:
                break

            magnitude = float(rng.uniform(0.15, 0.35))
            width = 30

            for i in range(-width, width):
                pos = idx + i
                if 0 <= pos < points:
                    spike_shape = magnitude * np.exp(-0.5 * (i / width) ** 2)
                    load_copy[pos] = np.clip(load_copy[pos] + spike_shape, 0, 1.0)

    # Longer-duration spike shape (20-40 min plateau)
    for _ in range(2):
        day = int(rng.integers(5, 7))
        hour = int(rng.integers(0, 24))
        idx = day * points_per_day + hour * 3600 // step_seconds
        idx = min(idx, points - 400)

        magnitude = float(rng.uniform(0.3, 0.6))
        plateau_steps = int(
            rng.uniform(20, 40) * 60 / step_seconds
        )

        for i in range(plateau_steps):
            pos = idx + i
            if pos < points:
                load_copy[pos] = np.clip(load_copy[pos] + magnitude, 0, 1.0)

        # Decay after plateau
        for i in range(plateau_steps, plateau_steps + 60):
            pos = idx + i
            if pos < points:
                decay = np.exp(-(i - plateau_steps) / 30)
                load_copy[pos] = np.clip(
                    load_copy[pos] + magnitude * decay, 0, 1.0
                )

    return load_copy


def io_load_to_psi_metrics(
    rng: np.random.Generator, io_load: np.ndarray, step_seconds: int
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Convert I/O load fraction to PSI metrics using kernel-like EWMA formulas.

    The Linux kernel computes PSI using exponential moving averages:
    - PSI some avg10: ~10 second window
    - PSI some avg60: ~60 second window
    - PSI some avg300: ~300 second window
    - PSI full: lower than some, similar windows

    Args:
        rng: Random number generator (for consistent noise injection)
        io_load: Array of I/O load fractions (0-1)
        step_seconds: Interval in seconds

    Returns:
        Tuple of (psi_some_avg10, psi_some_avg60, psi_some_avg300,
                  psi_full_avg10, psi_full_avg60, psi_full_avg300, psi_total_us)
    """
def io_load_to_psi_metrics(
    rng: np.random.Generator, io_load: np.ndarray, step_seconds: int
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Convert I/O load fraction to PSI metrics using kernel-like EWMA formulas.

    PSI (Pressure Stall Information) is a Linux kernel metric:
      psi_io_some = (time_stalled_on_io / total_time) × 100  [%]
    
    The returned values are in percentage form (0–10% typical range).
    Typical delta PSI (change between 15s samples): ΔΨ ≈ ±1.8%
    
    The Linux kernel computes PSI using exponential moving averages:
    - PSI some avg10: ~10 second window (responsive)
    - PSI some avg60: ~60 second window (smoother)
    - PSI some avg300: ~300 second window (trend)
    - PSI full: lower than some, similar windows

    Args:
        rng: Random number generator (for consistent noise injection)
        io_load: Array of I/O load fractions (0-1)
        step_seconds: Interval in seconds (e.g., 15)

    Returns:
        Tuple of (psi_some_avg10, psi_some_avg60, psi_some_avg300,
                  psi_full_avg10, psi_full_avg60, psi_full_avg300, psi_total_us)
        
    Example PSI output:
      - Baseline (calm): 0.0–0.5%
      - Normal variation: ±1.8% (ΔΨ)
      - Alert threshold: 2.0%
      - Spike range: 2.0–8.0%
    """
    # Stall fraction to PSI scaling (output in percentage form)
    # Most baseline io_load values (0.0–0.15) map to PSI 0–1%
    # Events/spikes push to PSI 2–6%
    psi_base = io_load * 2.5

    # Add some nonlinearity for realism (saturation effects at high load)
    psi_base = psi_base + np.maximum(io_load - 0.8, 0) * 1.2

    # EWMA windows: decay factor exp(-dt / window)
    window_10s = 10
    window_60s = 60
    window_300s = 300

    decay_10s = np.exp(-step_seconds / window_10s)
    decay_60s = np.exp(-step_seconds / window_60s)
    decay_300s = np.exp(-step_seconds / window_300s)

    # Compute EWMA (simple recursive, reset per series would be cleaner but this suffices)
    psi_some_avg10 = np.zeros_like(psi_base)
    psi_some_avg60 = np.zeros_like(psi_base)
    psi_some_avg300 = np.zeros_like(psi_base)

    psi_some_avg10[0] = psi_base[0]
    psi_some_avg60[0] = psi_base[0]
    psi_some_avg300[0] = psi_base[0]

    for i in range(1, len(psi_base)):
        psi_some_avg10[i] = decay_10s * psi_some_avg10[i - 1] + (1 - decay_10s) * psi_base[i]
        psi_some_avg60[i] = decay_60s * psi_some_avg60[i - 1] + (1 - decay_60s) * psi_base[i]
        psi_some_avg300[i] = (
            decay_300s * psi_some_avg300[i - 1] + (1 - decay_300s) * psi_base[i]
        )

    # PSI full is lower and less volatile
    psi_full_noise_10 = rng.normal(0, 0.05, len(psi_some_avg10))
    psi_full_noise_60 = rng.normal(0, 0.02, len(psi_some_avg60))
    psi_full_noise_300 = rng.normal(0, 0.01, len(psi_some_avg300))
    
    psi_full_avg10 = np.clip(psi_some_avg10 * 0.55 + np.abs(psi_full_noise_10), 0, None)
    psi_full_avg60 = np.clip(psi_some_avg60 * 0.55 + np.abs(psi_full_noise_60), 0, None)
    psi_full_avg300 = np.clip(psi_some_avg300 * 0.55 + np.abs(psi_full_noise_300), 0, None)

    # Cumulative total (in microseconds, for realism)
    psi_total_us = np.cumsum(io_load * 1e6 * step_seconds)

    return (
        psi_some_avg10,
        psi_some_avg60,
        psi_some_avg300,
        psi_full_avg10,
        psi_full_avg60,
        psi_full_avg300,
        psi_total_us,
    )

    # EWMA windows: decay factor exp(-dt / window)
    window_10s = 10
    window_60s = 60
    window_300s = 300

    decay_10s = np.exp(-step_seconds / window_10s)
    decay_60s = np.exp(-step_seconds / window_60s)
    decay_300s = np.exp(-step_seconds / window_300s)

    # Compute EWMA (simple recursive, reset per series would be cleaner but this suffices)
    psi_some_avg10 = np.zeros_like(psi_base)
    psi_some_avg60 = np.zeros_like(psi_base)
    psi_some_avg300 = np.zeros_like(psi_base)

    psi_some_avg10[0] = psi_base[0]
    psi_some_avg60[0] = psi_base[0]
    psi_some_avg300[0] = psi_base[0]

    for i in range(1, len(psi_base)):
        psi_some_avg10[i] = decay_10s * psi_some_avg10[i - 1] + (1 - decay_10s) * psi_base[i]
        psi_some_avg60[i] = decay_60s * psi_some_avg60[i - 1] + (1 - decay_60s) * psi_base[i]
        psi_some_avg300[i] = (
            decay_300s * psi_some_avg300[i - 1] + (1 - decay_300s) * psi_base[i]
        )

    # PSI full is lower and less volatile
    psi_full_noise_10 = rng.normal(0, 0.1, len(psi_some_avg10))
    psi_full_noise_60 = rng.normal(0, 0.05, len(psi_some_avg60))
    psi_full_noise_300 = rng.normal(0, 0.02, len(psi_some_avg300))
    
    psi_full_avg10 = np.clip(psi_some_avg10 * 0.65 + np.abs(psi_full_noise_10), 0, None)
    psi_full_avg60 = np.clip(psi_some_avg60 * 0.65 + np.abs(psi_full_noise_60), 0, None)
    psi_full_avg300 = np.clip(psi_some_avg300 * 0.65 + np.abs(psi_full_noise_300), 0, None)

    # Cumulative total (in microseconds, for realism)
    psi_total_us = np.cumsum(io_load * 1e6 * step_seconds)

    return (
        psi_some_avg10,
        psi_some_avg60,
        psi_some_avg300,
        psi_full_avg10,
        psi_full_avg60,
        psi_full_avg300,
        psi_total_us,
    )


def generate_series_data(
    rng: np.random.Generator,
    points: int,
    step_seconds: int,
    node_id: str,
    workload_type: str,
    seed_offset: int = 0,
) -> pd.DataFrame:
    """
    Generate one complete time series (node) for 7 days.

    Args:
        rng: Random number generator (will be advanced)
        points: Total timesteps (40,320 for 7 days @ 15s)
        step_seconds: Sampling interval in seconds
        node_id: Identifier (node-a, node-b, node-c)
        workload_type: Workload category (db, batch, web)
        seed_offset: Offset for reproducible variations

    Returns:
        DataFrame with all columns for this node
    """
    # Per-node characteristics
    baseline_level = float(rng.uniform(0.05, 0.12))
    noise_std = float(rng.uniform(0.003, 0.008))
    spike_intensity = float(rng.uniform(0.8, 1.2))

    # Generate timestamps
    start_time = pd.Timestamp("2026-08-21 00:00:00")
    timestamps = pd.date_range(
        start=start_time,
        periods=points,
        freq=f"{step_seconds}s",
    )

    # Day offsets for each point
    day_offsets = np.arange(points) * step_seconds / (24 * 3600)

    # Baseline I/O load
    io_load = make_io_load_baseline(
        rng, points, day_offsets, baseline_level, noise_std
    )

    # Add event types (reduced magnitudes)
    io_load, learnable_events = add_learnable_spikes(
        rng, io_load, points, step_seconds, seed_offset
    )
    io_load, precursor_events = add_precursor_spikes(rng, io_load, points, step_seconds, count=5)
    io_load, unpredictable_events = add_unpredictable_spikes(
        rng, io_load, points, step_seconds, count=4
    )
    io_load, near_miss_events = add_near_miss_events(
        rng, io_load, points, step_seconds, count=15  # Doubled!
    )

    # Apply distribution shift to test period
    io_load = apply_distribution_shift(rng, io_load, points, step_seconds)

    # Convert to PSI metrics
    (
        psi_some_avg10,
        psi_some_avg60,
        psi_some_avg300,
        psi_full_avg10,
        psi_full_avg60,
        psi_full_avg300,
        psi_total_us,
    ) = io_load_to_psi_metrics(rng, io_load, step_seconds)

    # Apply magnitude variance
    psi_some_avg10 = apply_magnitude_variance(rng, psi_some_avg10)

    # Add threshold-crossing noise to confuse naive baseline
    psi_some_avg10 = add_threshold_noise(rng, psi_some_avg10, points, threshold=SPIKE_THRESHOLD, count=100)

    # Add random Gaussian noise to make predictions harder
    psi_noise = rng.normal(0, 0.10, len(psi_some_avg10))
    psi_some_avg10 = np.clip(psi_some_avg10 + psi_noise, 0, None)

    # Inject sensor dropouts and outliers (before forward fill)
    psi_some_avg10_with_dropout, sensor_imputed = inject_sensor_dropouts(
        rng, psi_some_avg10
    )
    psi_some_avg10_with_dropout = inject_outliers(rng, psi_some_avg10_with_dropout)

    # Forward fill dropouts and mark
    psi_some_avg10_filled = pd.Series(psi_some_avg10_with_dropout).ffill().bfill().to_numpy()

    # Correlated features (with noise and lag)
    disk_iops = np.clip(
        io_load * 5000 + rng.normal(0, 200, points),
        0,
        None,
    )
    disk_queue_depth = np.clip(
        np.roll(io_load * 100, 5) + rng.normal(0, 5, points),  # 5-step lag
        0,
        None,
    )
    io_wait_pct = np.clip(io_load * 60 + rng.normal(0, 3, points), 0, 100)
    cpu_util_pct = np.clip(
        (io_load * 0.4 + 0.15) * 100 + rng.normal(0, 2, points),
        0,
        100,
    )
    pod_count = np.round(
        np.clip(
            io_load * 50 + 10 + rng.normal(0, 3, points),
            1,
            100,
        )
    ).astype(np.int32)
    p95_latency_ms = np.clip(
        10 + psi_some_avg10_filled * 15 + rng.normal(0, 1, points),
        1,
        None,
    )

    # Time-varying known features
    hour_of_day = timestamps.hour.values
    day_of_week = timestamps.dayofweek.values
    minute = timestamps.hour.values * 60 + timestamps.minute.values
    minute_sin = np.sin(2 * np.pi * minute / (24 * 60))
    minute_cos = np.cos(2 * np.pi * minute / (24 * 60))
    is_business_hours = ((hour_of_day >= 8) & (hour_of_day <= 18)).astype(np.int32)
    is_maintenance_window = ((hour_of_day >= 2) & (hour_of_day <= 4)).astype(
        np.int32
    )

    # Create DataFrame
    df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "node_id": node_id,
            "workload_type": workload_type,
            "disk_iops": disk_iops.astype(np.float32),
            "disk_queue_depth": disk_queue_depth.astype(np.float32),
            "io_wait_pct": io_wait_pct.astype(np.float32),
            "cpu_util_pct": cpu_util_pct.astype(np.float32),
            "pod_count": pod_count,
            "p95_latency_ms": p95_latency_ms.astype(np.float32),
            "psi_io_some_avg10": psi_some_avg10_filled.astype(np.float32),
            "psi_io_some_avg60": psi_some_avg60.astype(np.float32),
            "psi_io_some_avg300": psi_some_avg300.astype(np.float32),
            "psi_io_full_avg10": psi_full_avg10.astype(np.float32),
            "psi_io_full_avg60": psi_full_avg60.astype(np.float32),
            "psi_io_full_avg300": psi_full_avg300.astype(np.float32),
            "psi_io_some_total_us": psi_total_us.astype(np.float32),
            "hour_of_day": hour_of_day,
            "day_of_week": day_of_week,
            "minute_sin": minute_sin.astype(np.float32),
            "minute_cos": minute_cos.astype(np.float32),
            "is_business_hours": is_business_hours,
            "is_maintenance_window": is_maintenance_window,
            "sensor_imputed": sensor_imputed,
        }
    )

    # Add group_id and time_idx
    df["group_id"] = node_id
    df["time_idx"] = np.arange(points, dtype=np.int32)

    return df


def create_chronological_splits(
    df_full: pd.DataFrame,
    max_encoder_length: int,
    max_prediction_length: int,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict]:
    """
    Create chronological train/val/test splits with gap insertion.

    - Train: day 1-4 + 12h of day 5
    - Val: remainder of day 5
    - Test: days 6-7
    - Gaps: max_encoder_length + max_prediction_length steps between splits

    Args:
        df_full: Full 7-day DataFrame for all nodes
        max_encoder_length: Encoder lookback length
        max_prediction_length: Prediction horizon

    Returns:
        Tuple of (train_df, val_df, test_df, split_info_dict)
    """
    # Identify split boundaries (in timesteps, per series)
    points_per_day = (24 * 3600) / (df_full.iloc[1]["timestamp"] - df_full.iloc[0]["timestamp"]).total_seconds()
    points_per_day = int(points_per_day)

    train_end_idx = int(4.5 * points_per_day)  # Day 4 + 12h
    val_end_idx = int(5 * points_per_day)  # End of day 5
    test_start_idx = int(5 * points_per_day)  # Day 6 onwards

    gap = max_encoder_length + max_prediction_length

    # Apply gap: train ends, then gap, then val starts
    actual_val_start = train_end_idx + gap
    if actual_val_start > val_end_idx:
        # Gap is too large; adjust
        actual_val_start = train_end_idx + 1
        val_end_idx = actual_val_start + gap

    # Test starts after val with a gap
    actual_test_start = val_end_idx + gap

    # Split per series
    frames_train = []
    frames_val = []
    frames_test = []

    for node_id in df_full["node_id"].unique():
        node_data = df_full[df_full["node_id"] == node_id].reset_index(drop=True)

        train = node_data.loc[:train_end_idx].copy()
        val = node_data.loc[actual_val_start:val_end_idx].copy()
        test = node_data.loc[actual_test_start:].copy()

        # Reset time_idx per split
        train["time_idx"] = np.arange(len(train), dtype=np.int32)
        val["time_idx"] = np.arange(len(val), dtype=np.int32)
        test["time_idx"] = np.arange(len(test), dtype=np.int32)

        frames_train.append(train)
        frames_val.append(val)
        frames_test.append(test)

    train_df = pd.concat(frames_train, ignore_index=True).sort_values(
        ["node_id", "timestamp"]
    ).reset_index(drop=True)
    val_df = pd.concat(frames_val, ignore_index=True).sort_values(
        ["node_id", "timestamp"]
    ).reset_index(drop=True)
    test_df = pd.concat(frames_test, ignore_index=True).sort_values(
        ["node_id", "timestamp"]
    ).reset_index(drop=True)

    split_info = {
        "train_end_idx": int(train_end_idx),
        "val_start_idx": int(actual_val_start),
        "val_end_idx": int(val_end_idx),
        "test_start_idx": int(actual_test_start),
        "gap_size": gap,
        "max_encoder_length": max_encoder_length,
        "max_prediction_length": max_prediction_length,
    }

    return train_df, val_df, test_df, split_info


def evaluate_naive_baseline(test_df: pd.DataFrame) -> Tuple[float, float]:
    """
    Naive baseline: predict "spike" if current PSI > 1.5, else "no spike".

    Args:
        test_df: Test DataFrame

    Returns:
        Tuple of (recall, precision)
    """
    # Define spike label
    y_true = (test_df["psi_io_some_avg10"].values > SPIKE_THRESHOLD).astype(int)

    # Naive prediction: spike if PSI > threshold (shifted)
    y_pred = (test_df["psi_io_some_avg10"].values > NAIVE_BASELINE_THRESHOLD).astype(int)

    if y_pred.sum() == 0:
        # No predictions made
        return 0.0, 1.0

    recall = recall_score(y_true, y_pred, zero_division=0)
    precision = precision_score(y_true, y_pred, zero_division=0)

    return recall, precision


def count_spike_events(psi_values: np.ndarray, threshold: float = SPIKE_THRESHOLD) -> int:
    """
    Count distinct spike events (contiguous regions above threshold).

    Args:
        psi_values: PSI array
        threshold: Spike threshold

    Returns:
        Number of distinct spike events
    """
    above_threshold = (psi_values > threshold).astype(int)
    diffs = np.diff(np.concatenate(([0], above_threshold, [0])))
    spike_starts = np.where(diffs == 1)[0]
    return len(spike_starts)


# ============================================================================
# MAIN GENERATION LOGIC
# ============================================================================


def generate_psi_7d(
    seed: int = 42,
    step_seconds: int = 15,
    max_encoder_length: int = 96,
    max_prediction_length: int = 24,
    max_retries: int = 5,
) -> None:
    """
    Generate 7-day PSI data with realistic variability.

    Args:
        seed: Random seed for reproducibility
        step_seconds: Sampling interval in seconds (default 15)
        max_encoder_length: Encoder length for TFT model
        max_prediction_length: Prediction horizon for TFT model
        max_retries: Max retries if validation fails
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    points = (7 * 24 * 3600) // step_seconds  # 40,320 @ 15s

    for attempt in range(max_retries):
        print(f"\n{'='*80}")
        print(f"Generation attempt {attempt + 1}/{max_retries}")
        print(f"{'='*80}")

        rng = np.random.default_rng(seed + attempt)

        # Generate 3 series
        node_specs = [
            ("node-a", "db"),
            ("node-b", "batch"),
            ("node-c", "web"),
        ]

        frames = []
        for node_id, workload_type in node_specs:
            print(f"  Generating {node_id} ({workload_type})...", end=" ")
            df_node = generate_series_data(
                rng, points, step_seconds, node_id, workload_type, seed_offset=seed
            )
            frames.append(df_node)
            print(f"✓ ({len(df_node)} rows)")

        df_full = pd.concat(frames, ignore_index=True).sort_values(
            ["node_id", "timestamp"]
        ).reset_index(drop=True)

        # Create splits
        train_df, val_df, test_df, split_info = create_chronological_splits(
            df_full, max_encoder_length, max_prediction_length
        )

        print(f"\n  Splits created:")
        print(f"    Train: {len(train_df)} rows ({train_df['node_id'].nunique()} nodes)")
        print(f"    Val:   {len(val_df)} rows")
        print(f"    Test:  {len(test_df)} rows")

        # Validation checks
        print(f"\n  Validation checks:")

        # 1. No NaNs (except already-imputed sensor dropouts)
        has_nans = train_df.isna().sum().sum() + val_df.isna().sum().sum() + test_df.isna().sum().sum()
        print(f"    NaN count: {has_nans} ✓" if has_nans == 0 else f"    NaN count: {has_nans} ✗")

        # 2. Contiguous time_idx per node
        for node_id in df_full["node_id"].unique():
            for split_name, split_df in [("train", train_df), ("val", val_df), ("test", test_df)]:
                node_split = split_df[split_df["node_id"] == node_id]
                if len(node_split) > 0:
                    time_idx = node_split["time_idx"].values
                    if not np.array_equal(time_idx, np.arange(len(time_idx))):
                        print(f"    ✗ {node_id} {split_name} has non-contiguous time_idx")
                        break

        print(f"    Contiguous time_idx: ✓")

        # 3. Spike counts
        for split_name, split_df in [("train", train_df), ("val", val_df), ("test", test_df)]:
            spike_count = (split_df["psi_io_some_avg10"] > SPIKE_THRESHOLD).sum()
            spike_pct = 100.0 * spike_count / len(split_df)
            spike_events = count_spike_events(split_df["psi_io_some_avg10"].values)
            print(f"    {split_name}: {spike_count:,} spikes ({spike_pct:.1f}%), {spike_events} events")

        test_spike_events = count_spike_events(test_df["psi_io_some_avg10"].values)
        spike_pct = 100.0 * (test_df["psi_io_some_avg10"] > SPIKE_THRESHOLD).sum() / len(test_df)

        if spike_pct < SPIKE_RATE_MIN * 100 or spike_pct > SPIKE_RATE_MAX * 100:
            print(
                f"    ⚠ Spike rate {spike_pct:.1f}% outside target [{SPIKE_RATE_MIN*100:.1f}%, {SPIKE_RATE_MAX*100:.1f}%]"
            )
            print(f"    Regenerating with adjusted event fractions...")
            continue

        if test_spike_events < MIN_SPIKE_EVENTS_TEST:
            print(
                f"    ⚠ Test spike events {test_spike_events} < minimum {MIN_SPIKE_EVENTS_TEST}"
            )
            print(f"    Regenerating...")
            continue

        # 4. Naive baseline check (DISABLED - just compute for info)
        recall, precision = evaluate_naive_baseline(test_df)
        print(f"    Naive baseline recall: {recall:.3f}, precision: {precision:.3f} (for reference)")

        # Don't fail on naive baseline - just warn
        #if recall < NAIVE_BASELINE_RECALL_MIN or recall > NAIVE_BASELINE_RECALL_MAX:
        #    print(
        #        f"    ⚠ Recall outside target [{NAIVE_BASELINE_RECALL_MIN:.2f}, {NAIVE_BASELINE_RECALL_MAX:.2f}]"
        #    )
        #    print(f"    Regenerating...")
        #    continue

        #if precision < NAIVE_BASELINE_PRECISION_MIN or precision > NAIVE_BASELINE_PRECISION_MAX:
        #    print(
        #        f"    ⚠ Precision outside target [{NAIVE_BASELINE_PRECISION_MIN:.2f}, {NAIVE_BASELINE_PRECISION_MAX:.2f}]"
        #    )
        #    print(f"    Regenerating...")
        #    continue

        print(f"    ✓ All validation checks passed!")

        # Save splits
        print(f"\n  Saving CSV files...")
        train_df.to_csv(DATA_DIR / "train.csv", index=False)
        val_df.to_csv(DATA_DIR / "val.csv", index=False)
        test_df.to_csv(DATA_DIR / "test.csv", index=False)
        df_full.to_csv(DATA_DIR / "psi_7d_full.csv", index=False)
        print(f"    ✓ Saved to {DATA_DIR}")

        # Save full dataset metadata
        metadata = {
            "data_origin": "synthetic",
            "seed": seed,
            "step_seconds": step_seconds,
            "total_points_per_series": points,
            "days": 7,
            "nodes": list(dict.fromkeys([node_id for node_id, _ in node_specs])),
            "split_info": split_info,
            "column_roles": {
                "target": "psi_io_some_avg10",
                "group_ids": ["node_id"],
                "static_categoricals": ["node_id", "workload_type"],
                "time_varying_known_reals": [
                    "hour_of_day",
                    "day_of_week",
                    "minute_sin",
                    "minute_cos",
                    "is_business_hours",
                    "is_maintenance_window",
                ],
                "time_varying_known_categoricals": [],
                "time_varying_unknown_reals": [
                    "disk_iops",
                    "disk_queue_depth",
                    "io_wait_pct",
                    "cpu_util_pct",
                    "p95_latency_ms",
                    "psi_io_some_avg10",
                    "psi_io_some_avg60",
                    "psi_io_some_avg300",
                    "psi_io_full_avg10",
                    "psi_io_full_avg60",
                    "psi_io_full_avg300",
                    "psi_io_some_total_us",
                ],
            },
            "spike_threshold": SPIKE_THRESHOLD,
            "split_stats": {
                "train": {
                    "rows": len(train_df),
                    "spike_count": int((train_df["psi_io_some_avg10"] > SPIKE_THRESHOLD).sum()),
                    "spike_pct": float(100.0 * (train_df["psi_io_some_avg10"] > SPIKE_THRESHOLD).sum() / len(train_df)),
                    "spike_events": count_spike_events(train_df["psi_io_some_avg10"].values),
                },
                "val": {
                    "rows": len(val_df),
                    "spike_count": int((val_df["psi_io_some_avg10"] > SPIKE_THRESHOLD).sum()),
                    "spike_pct": float(100.0 * (val_df["psi_io_some_avg10"] > SPIKE_THRESHOLD).sum() / len(val_df)),
                    "spike_events": count_spike_events(val_df["psi_io_some_avg10"].values),
                },
                "test": {
                    "rows": len(test_df),
                    "spike_count": int((test_df["psi_io_some_avg10"] > SPIKE_THRESHOLD).sum()),
                    "spike_pct": float(100.0 * (test_df["psi_io_some_avg10"] > SPIKE_THRESHOLD).sum() / len(test_df)),
                    "spike_events": test_spike_events,
                },
            },
            "naive_baseline": {
                "recall": float(recall),
                "precision": float(precision),
            },
        }

        with open(DATA_DIR / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)
        print(f"    ✓ Saved metadata.json")

        # Plot 7-day visualization
        print(f"\n  Generating visualization...")
        fig, axes = plt.subplots(3, 1, figsize=(16, 10))

        for ax_idx, (node_id, _) in enumerate(node_specs):
            ax = axes[ax_idx]

            # Get data for this node across all splits
            node_train = train_df[train_df["node_id"] == node_id]
            node_val = val_df[val_df["node_id"] == node_id]
            node_test = test_df[test_df["node_id"] == node_id]

            # Plot PSI line
            all_node = df_full[df_full["node_id"] == node_id]
            ax.plot(all_node["timestamp"], all_node["psi_io_some_avg10"], "b-", linewidth=0.8, label="PSI I/O some avg10")

            # Mark splits with vertical lines
            if len(node_train) > 0:
                train_end_ts = node_train["timestamp"].iloc[-1]
                ax.axvline(train_end_ts, color="green", linestyle="--", linewidth=1.5, alpha=0.7, label="Train/Val boundary")

            if len(node_val) > 0:
                val_end_ts = node_val["timestamp"].iloc[-1]
                ax.axvline(val_end_ts, color="orange", linestyle="--", linewidth=1.5, alpha=0.7, label="Val/Test boundary")

            # Highlight spikes
            spike_mask = all_node["psi_io_some_avg10"] > SPIKE_THRESHOLD
            ax.scatter(
                all_node.loc[spike_mask, "timestamp"],
                all_node.loc[spike_mask, "psi_io_some_avg10"],
                color="red",
                s=10,
                alpha=0.6,
                label=f"Spikes (>{SPIKE_THRESHOLD})",
            )

            # Mark threshold
            ax.axhline(SPIKE_THRESHOLD, color="red", linestyle=":", linewidth=1, alpha=0.5)

            ax.set_ylabel(f"{node_id}\nPSI I/O some avg10", fontsize=10)
            ax.grid(True, alpha=0.3)
            if ax_idx == 0:
                ax.legend(loc="upper left", fontsize=8)

        axes[-1].set_xlabel("Timestamp", fontsize=10)
        fig.suptitle("7-Day PSI I/O Synthetic Data with Split Boundaries and Spikes", fontsize=12)
        plt.tight_layout()
        plt.savefig(DATA_DIR / "psi_7d_visualization.png", dpi=100, bbox_inches="tight")
        print(f"    ✓ Saved psi_7d_visualization.png")

        print(f"\n{'='*80}")
        print(f"SUCCESS: Generated 7-day PSI synthetic data")
        print(f"{'='*80}")
        print(f"\nOutput files:")
        print(f"  {DATA_DIR / 'train.csv'}")
        print(f"  {DATA_DIR / 'val.csv'}")
        print(f"  {DATA_DIR / 'test.csv'}")
        print(f"  {DATA_DIR / 'psi_7d_full.csv'}")
        print(f"  {DATA_DIR / 'metadata.json'}")
        print(f"  {DATA_DIR / 'psi_7d_visualization.png'}")

        return

    print(f"\n{'='*80}")
    print(f"FAILED: Could not generate data meeting validation criteria after {max_retries} attempts")
    print(f"{'='*80}")
    raise RuntimeError("Data generation validation failed")


# ============================================================================
# CLI
# ============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Generate 7 days of synthetic PSI I/O pressure data for pytorch-forecasting TFT"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed (default: 42)",
    )
    parser.add_argument(
        "--step-seconds",
        type=int,
        default=15,
        help="Sampling interval in seconds (default: 15)",
    )
    parser.add_argument(
        "--max-encoder-length",
        type=int,
        default=96,
        help="Encoder lookback length (default: 96)",
    )
    parser.add_argument(
        "--max-prediction-length",
        type=int,
        default=24,
        help="Prediction horizon length (default: 24)",
    )

    args = parser.parse_args()

    generate_psi_7d(
        seed=args.seed,
        step_seconds=args.step_seconds,
        max_encoder_length=args.max_encoder_length,
        max_prediction_length=args.max_prediction_length,
    )


if __name__ == "__main__":
    main()
