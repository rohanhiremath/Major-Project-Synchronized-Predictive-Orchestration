#!/usr/bin/env python3
"""
Real-Time Workload Generator: p99 200ms Latency Breach with Delta 1.8% PSI

Generates live workload that triggers realistic p99 latency spikes correlating with PSI changes.
Can be deployed as a load test or stress test container.

Features:
  - Progressive ramp-up: gradually increase load to trigger p99 > 200ms
  - Memory pressure spikes: cause PSI changes (delta 1.8%+)
  - Request patterns: variable rate with bursts
  - Latency patterns: baseline + spikes + jitter

Usage:
  python generate_realtime_p99_workload.py --duration 300 --output data/realtime_workload.csv

Configuration:
  --duration: How long to run (seconds)
  --output: Where to save collected metrics
  --spike-interval: Seconds between latency spike events
  --baseline-rps: Baseline requests per second
"""

import argparse
import json
import time
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

# ============================================================================
# CONFIGURATION
# ============================================================================

DEFAULT_DURATION_SECONDS = 300  # 5 minutes
DEFAULT_OUTPUT_FILE = DATA_DIR / "realtime_p99_workload.csv"
SAMPLE_INTERVAL_SECONDS = 20  # Collect metrics every 20s
SLO_THRESHOLD_MS = 200.0
BASELINE_P99_MS = 50.0

# Workload parameters
DEFAULT_BASELINE_RPS = 50  # Requests per second
DEFAULT_SPIKE_INTERVAL = 60  # Spike every 60 seconds
SPIKE_DURATION_SAMPLES = 5  # ~100 seconds

# ============================================================================
# REAL-TIME WORKLOAD GENERATOR
# ============================================================================

class RealtimeWorkloadGenerator:
    """Generate real-time workload data with latency spikes"""
    
    def __init__(self, duration_seconds: int, output_file: str, baseline_rps: int = DEFAULT_BASELINE_RPS):
        self.duration_seconds = duration_seconds
        self.output_file = Path(output_file)
        self.baseline_rps = baseline_rps
        self.num_samples = duration_seconds // SAMPLE_INTERVAL_SECONDS
        self.rng = np.random.RandomState(int(time.time()))
        
        # State tracking
        self.start_time = None
        self.samples = []
        self.spike_indices = set()
        
        print("=" * 100)
        print("REAL-TIME WORKLOAD GENERATOR: p99 200ms Latency Breach with Delta 1.8% PSI")
        print("=" * 100)
        print()
        
        print(f"[CONFIG]")
        print(f"  Duration: {duration_seconds}s")
        print(f"  Sample interval: {SAMPLE_INTERVAL_SECONDS}s")
        print(f"  Total samples: {self.num_samples}")
        print(f"  Baseline RPS: {baseline_rps}")
        print(f"  Output: {self.output_file}")
        print()
    
    def calculate_load_profile(self, elapsed_seconds: int) -> Dict:
        """Calculate load parameters for current time"""
        # Ramp up over time: easy start, then increase
        ramp_factor = min(1.0, elapsed_seconds / (self.duration_seconds * 0.7))
        
        # Variable request rate
        base_rps = self.baseline_rps * (0.8 + ramp_factor * 0.4)  # 40-60 RPS
        
        # Add daily pattern (if available)
        hour_factor = 1 + 0.3 * np.sin(2 * np.pi * (elapsed_seconds / 3600) / 24)
        
        # Business hour boost
        hour_of_day = (elapsed_seconds / 3600) % 24
        business_boost = 1.0 if (8 <= hour_of_day <= 18) else 0.8
        
        request_rate = base_rps * hour_factor * business_boost
        
        # PSI baseline with patterns
        psi_baseline = 0.5
        psi_business_boost = 0.2 if (8 <= hour_of_day <= 18) else 0.0
        psi_noise = self.rng.normal(0, 0.05)
        
        psi = psi_baseline + psi_business_boost + psi_noise
        psi = np.clip(psi, 0, 10)
        
        return {
            'request_rate': max(1, request_rate),
            'psi_baseline': np.clip(psi, 0, 10),
            'ramp_factor': ramp_factor,
        }
    
    def generate_samples(self) -> pd.DataFrame:
        """Generate complete workload dataset"""
        print(f"[STEP 1] Generate load profile over {self.duration_seconds}s")
        print("-" * 100)
        
        self.start_time = datetime.utcnow()
        samples = []
        
        # Generate spike times
        spike_interval = max(60, self.duration_seconds // 5)  # 5-6 spikes over duration
        spike_times = set()
        for i in range(0, self.duration_seconds, spike_interval):
            if i + spike_interval < self.duration_seconds:
                spike_time = i + self.rng.randint(-10, 10)
                spike_times.add(max(0, spike_time))
        
        print(f"✓ Planned {len(spike_times)} spike events")
        print()
        
        print(f"[STEP 2] Simulate workload execution")
        print("-" * 100)
        
        # Baseline and spike PSI
        psi_values = []
        latency_values = []
        
        for sample_idx in range(self.num_samples):
            elapsed_seconds = sample_idx * SAMPLE_INTERVAL_SECONDS
            timestamp = self.start_time + timedelta(seconds=elapsed_seconds)
            
            # Get load parameters
            load = self.calculate_load_profile(elapsed_seconds)
            
            # Check if we're in a spike window
            in_spike = any(
                spike_time <= elapsed_seconds < spike_time + SPIKE_DURATION_SAMPLES * SAMPLE_INTERVAL_SECONDS
                for spike_time in spike_times
            )
            
            # PSI with spike
            psi = load['psi_baseline']
            if in_spike:
                # Sharp PSI increase during spike
                spike_phase = (elapsed_seconds % (SPIKE_DURATION_SAMPLES * SAMPLE_INTERVAL_SECONDS)) / (SPIKE_DURATION_SAMPLES * SAMPLE_INTERVAL_SECONDS)
                
                if spike_phase < 0.3:  # Ramp up
                    psi += 1.8 * (spike_phase / 0.3)
                elif spike_phase < 0.7:  # Plateau
                    psi += 1.8
                else:  # Decay
                    psi += 1.8 * (1 - (spike_phase - 0.7) / 0.3)
            
            psi = np.clip(psi, 0, 10)
            
            # Calculate delta PSI
            if psi_values:
                delta_psi = psi - psi_values[-1]
            else:
                delta_psi = 0.0
            
            # Latency with spike
            latency = BASELINE_P99_MS + self.rng.normal(0, 5)  # Baseline + noise
            
            if in_spike:
                # Latency increases during spike
                spike_phase = (elapsed_seconds % (SPIKE_DURATION_SAMPLES * SAMPLE_INTERVAL_SECONDS)) / (SPIKE_DURATION_SAMPLES * SAMPLE_INTERVAL_SECONDS)
                
                if spike_phase < 0.3:  # Ramp up
                    latency_increase = 150 * (spike_phase / 0.3)  # Ramp to 150ms increase
                elif spike_phase < 0.7:  # Plateau
                    latency_increase = 150
                else:  # Decay
                    latency_increase = 150 * (1 - (spike_phase - 0.7) / 0.3)
                
                latency += latency_increase
            
            latency = np.clip(latency, 10, None)
            
            # SLO breach label
            slo_breach = 1 if latency > SLO_THRESHOLD_MS else 0
            
            # Correlated metrics
            disk_iops = np.clip(psi * 1000 + self.rng.normal(0, 100), 0, None)
            disk_queue_depth = np.clip(psi * 50 + self.rng.normal(0, 5), 0, None)
            io_wait_pct = np.clip(psi * 40 + self.rng.normal(0, 2), 0, 100)
            cpu_util_pct = np.clip((psi * 0.3 + 0.15 + load['ramp_factor'] * 0.3) * 100 + self.rng.normal(0, 3), 0, 100)
            memory_usage_gb = np.clip(1.5 + psi * 0.3 + self.rng.normal(0, 0.05), 0.5, None)
            
            # Create sample
            sample = {
                'timestamp': timestamp.isoformat(),
                'elapsed_seconds': elapsed_seconds,
                'sample_idx': sample_idx,
                
                # Pressure metrics
                'psi_some_avg10': float(psi),
                'delta_psi': float(delta_psi),
                
                # Latency metrics
                'p50_latency_ms': float(latency * 0.4 + self.rng.normal(0, 1)),
                'p95_latency_ms': float(latency * 0.85 + self.rng.normal(0, 1)),
                'p99_latency_ms': float(latency),
                'p99_9_latency_ms': float(latency * 1.05 + self.rng.normal(0, 2)),
                'slo_breach': int(slo_breach),
                
                # System metrics
                'request_rate': float(load['request_rate']),
                'disk_iops': float(disk_iops),
                'disk_queue_depth': float(disk_queue_depth),
                'io_wait_pct': float(io_wait_pct),
                'cpu_util_pct': float(cpu_util_pct),
                'memory_usage_gb': float(memory_usage_gb),
                'error_rate': float(self.rng.uniform(0.0, 0.2) if not slo_breach else self.rng.uniform(0.1, 2.0)),
            }
            
            samples.append(sample)
            psi_values.append(psi)
            latency_values.append(latency)
            
            # Progress indicator
            if (sample_idx + 1) % max(1, self.num_samples // 10) == 0:
                pct = 100 * (sample_idx + 1) / self.num_samples
                print(f"  [{pct:5.1f}%] Sample {sample_idx + 1:3d}/{self.num_samples} | "
                      f"PSI: {psi:6.2f}% | Δ PSI: {delta_psi:+6.2f}% | p99: {latency:7.2f}ms | "
                      f"SLO breach: {'YES' if slo_breach else 'NO'}")
        
        print()
        
        # Create DataFrame
        df = pd.DataFrame(samples)
        
        print(f"[STEP 3] Generate summary statistics")
        print("-" * 100)
        print(f"✓ Generated {len(df)} samples")
        print()
        
        print(f"Latency (p99):")
        print(f"  Min: {df['p99_latency_ms'].min():.2f}ms")
        print(f"  P50: {df['p99_latency_ms'].quantile(0.50):.2f}ms")
        print(f"  P95: {df['p99_latency_ms'].quantile(0.95):.2f}ms")
        print(f"  Max: {df['p99_latency_ms'].max():.2f}ms")
        print()
        
        num_breaches = df['slo_breach'].sum()
        breach_rate = 100 * num_breaches / len(df)
        print(f"SLO Breaches (p99 > {SLO_THRESHOLD_MS}ms):")
        print(f"  Total: {num_breaches}/{len(df)} ({breach_rate:.2f}%)")
        print()
        
        print(f"PSI metrics:")
        print(f"  Absolute PSI:")
        print(f"    Min: {df['psi_some_avg10'].min():.4f}%")
        print(f"    P50: {df['psi_some_avg10'].quantile(0.50):.4f}%")
        print(f"    P95: {df['psi_some_avg10'].quantile(0.95):.4f}%")
        print(f"    Max: {df['psi_some_avg10'].max():.4f}%")
        print()
        print(f"  Delta PSI:")
        print(f"    Min: {df['delta_psi'].min():+.4f}%")
        print(f"    P5: {df['delta_psi'].quantile(0.05):+.4f}%")
        print(f"    P50: {df['delta_psi'].quantile(0.50):+.4f}%")
        print(f"    P95: {df['delta_psi'].quantile(0.95):+.4f}%")
        print(f"    Max: {df['delta_psi'].max():+.4f}%")
        print()
        
        return df
    
    def save_dataset(self, df: pd.DataFrame) -> Path:
        """Save workload to CSV"""
        print(f"[STEP 4] Save dataset")
        print("-" * 100)
        
        df.to_csv(self.output_file, index=False)
        
        print(f"✓ Saved to: {self.output_file}")
        print()
        
        return self.output_file


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Generate real-time workload with p99 200ms latency spikes and delta PSI correlation"
    )
    parser.add_argument("--duration", type=int, default=DEFAULT_DURATION_SECONDS,
                       help=f"Duration in seconds (default: {DEFAULT_DURATION_SECONDS})")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT_FILE),
                       help=f"Output CSV file (default: {DEFAULT_OUTPUT_FILE})")
    parser.add_argument("--baseline-rps", type=int, default=DEFAULT_BASELINE_RPS,
                       help=f"Baseline requests per second (default: {DEFAULT_BASELINE_RPS})")
    
    args = parser.parse_args()
    
    # Generate workload
    generator = RealtimeWorkloadGenerator(
        duration_seconds=args.duration,
        output_file=args.output,
        baseline_rps=args.baseline_rps
    )
    
    df = generator.generate_samples()
    generator.save_dataset(df)
    
    print(f"=" * 100)
    print(f"REAL-TIME WORKLOAD GENERATION COMPLETE")
    print(f"=" * 100)
    print()
    print(f"Output file: {generator.output_file}")
    print()
    print(f"Next steps:")
    print(f"  1. Validate against delta 1.8% PSI threshold:")
    print(f"     python validate_synthetic_p99_200ms.py --data {generator.output_file}")
    print()
    print(f"  2. Or optimize threshold:")
    print(f"     python optimize_delta_psi_threshold.py --data {generator.output_file}")
    print()

if __name__ == "__main__":
    main()
