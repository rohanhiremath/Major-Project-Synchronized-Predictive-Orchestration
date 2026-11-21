#!/usr/bin/env python3
"""
Synthetic Workload Generator: p99 200ms Latency Breach with Delta 1.8% PSI

Generates realistic synthetic data that simulates:
  1. p99 latency @ baseline: ~50ms (normal)
  2. p99 latency @ spike: ~200-300ms (SLO breach)
  3. Delta PSI (PSI change between 20s samples): ±1.8%
  4. Correlation: PSI spikes precede latency breaches

Configuration:
  - Duration: 4 hours (720 samples at 20s intervals)
  - Sample interval: 20s (matches real-time collection)
  - SLO threshold: 200ms
  - Delta PSI threshold: 1.8%
  - Train/Val/Test split: 50% / 25% / 25%

Output: CSV file with all metrics ready for validation
"""

import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from typing import Tuple, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

# ============================================================================
# CONFIGURATION
# ============================================================================

DURATION_HOURS = 4
SAMPLE_INTERVAL_SECONDS = 20
SLO_THRESHOLD_MS = 200.0
BASELINE_P99_MS = 50.0
SPIKE_P99_MS = 250.0

# PSI configuration
BASELINE_PSI = 0.5  # Baseline memory pressure in %
SPIKE_PSI_DELTA = 1.8  # Change in PSI when spike occurs

# Event configuration
SPIKE_EVENTS = 25  # Number of latency spike events to inject
SPIKE_DURATION_SAMPLES = 15  # ~5 minutes duration
SPIKE_RAMP_SAMPLES = 5  # Ramp-up time
SPIKE_DECAY_SAMPLES = 10  # Ramp-down time

# ============================================================================
# SYNTHETIC WORKLOAD GENERATOR
# ============================================================================

class SyntheticWorkloadGenerator:
    """Generate synthetic workload data with controlled latency spikes"""
    
    def __init__(self, duration_hours: int, sample_interval_seconds: int, seed: int = 42):
        self.duration_hours = duration_hours
        self.sample_interval_seconds = sample_interval_seconds
        self.seed = seed
        self.rng = np.random.RandomState(seed)
        
        # Calculate total samples
        self.total_seconds = duration_hours * 3600
        self.num_samples = self.total_seconds // sample_interval_seconds
        
        print(f"[CONFIG]")
        print(f"  Duration: {duration_hours} hours")
        print(f"  Sample interval: {sample_interval_seconds}s")
        print(f"  Total samples: {self.num_samples}")
        print()
    
    def generate_baseline_psi(self) -> np.ndarray:
        """Generate baseline PSI with daily/hourly patterns"""
        psi = np.zeros(self.num_samples)
        
        # Daily cycle: higher during business hours
        for i in range(self.num_samples):
            hours_elapsed = (i * self.sample_interval_seconds) / 3600
            hour_of_day = hours_elapsed % 24
            
            # Business hours boost (8am-6pm)
            is_business = (8 <= hour_of_day <= 18)
            business_boost = 0.3 if is_business else 0.0
            
            # Morning ramp and evening falloff
            morning_ramp = 0.2 * (1 / (1 + np.exp(-(hour_of_day - 6) / 2)))
            evening_falloff = 0.15 * (1 / (1 + np.exp((hour_of_day - 20) / 2)))
            
            # Combine with baseline
            psi[i] = BASELINE_PSI + business_boost + morning_ramp + evening_falloff
            
            # Add daily noise
            psi[i] += self.rng.normal(0, 0.05)
        
        # Smooth with rolling window
        psi = pd.Series(psi).rolling(window=5, min_periods=1, center=True).mean().values
        psi = np.clip(psi, 0, 10)
        
        return psi
    
    def generate_delta_psi(self, psi: np.ndarray) -> np.ndarray:
        """Calculate delta PSI (change from previous sample)"""
        delta_psi = np.zeros(self.num_samples)
        delta_psi[0] = 0  # First sample has no delta
        
        for i in range(1, self.num_samples):
            delta_psi[i] = psi[i] - psi[i-1]
        
        return delta_psi
    
    def inject_spike_events(self, psi: np.ndarray) -> Tuple[np.ndarray, np.ndarray, List[Dict]]:
        """
        Inject latency spike events with corresponding PSI changes
        
        Returns:
          - Modified PSI array
          - Latency array
          - List of spike event metadata
        """
        latency = np.ones(self.num_samples) * BASELINE_P99_MS
        latency += self.rng.normal(0, 5, self.num_samples)  # Add noise
        latency = np.clip(latency, 10, None)
        
        spike_events = []
        
        # Generate random spike event times
        spike_start_indices = sorted(
            self.rng.choice(
                range(100, self.num_samples - SPIKE_DURATION_SAMPLES - 100),
                size=SPIKE_EVENTS,
                replace=False
            )
        )
        
        for spike_idx, start_idx in enumerate(spike_start_indices):
            # Spike shape: ramp up -> plateau -> decay
            spike_psi_increase = SPIKE_PSI_DELTA
            
            # Ramp-up phase: PSI increases, latency starts to rise
            for i in range(SPIKE_RAMP_SAMPLES):
                pos = start_idx + i
                if pos < self.num_samples:
                    progress = i / SPIKE_RAMP_SAMPLES
                    psi[pos] += spike_psi_increase * progress
                    latency[pos] += (SPIKE_P99_MS - BASELINE_P99_MS) * (progress ** 0.8)
            
            # Plateau phase: High PSI and latency
            for i in range(SPIKE_RAMP_SAMPLES, SPIKE_RAMP_SAMPLES + SPIKE_DURATION_SAMPLES):
                pos = start_idx + i
                if pos < self.num_samples:
                    psi[pos] += spike_psi_increase
                    latency[pos] += (SPIKE_P99_MS - BASELINE_P99_MS)
            
            # Decay phase: Both return to baseline
            for i in range(SPIKE_DURATION_SAMPLES, SPIKE_DURATION_SAMPLES + SPIKE_DECAY_SAMPLES):
                pos = start_idx + SPIKE_RAMP_SAMPLES + i
                if pos < self.num_samples:
                    progress = 1 - (i / SPIKE_DECAY_SAMPLES)
                    psi[pos] += spike_psi_increase * (progress ** 0.8)
                    latency[pos] += (SPIKE_P99_MS - BASELINE_P99_MS) * (progress ** 0.8)
            
            spike_events.append({
                'spike_id': spike_idx + 1,
                'start_sample': start_idx,
                'end_sample': start_idx + SPIKE_RAMP_SAMPLES + SPIKE_DURATION_SAMPLES + SPIKE_DECAY_SAMPLES,
                'peak_psi_increase': spike_psi_increase,
                'peak_latency_increase': SPIKE_P99_MS - BASELINE_P99_MS
            })
        
        # Clip values
        psi = np.clip(psi, 0, 10)
        latency = np.clip(latency, 10, None)
        
        return psi, latency, spike_events
    
    def generate_correlated_metrics(self, psi: np.ndarray, latency: np.ndarray) -> Dict[str, np.ndarray]:
        """Generate correlated metrics based on PSI and latency"""
        metrics = {}
        
        # Disk IOPS: correlated with PSI
        metrics['disk_iops'] = np.clip(
            psi * 1000 + self.rng.normal(0, 100, self.num_samples),
            0,
            None
        )
        
        # Disk queue depth: precedes PSI
        metrics['disk_queue_depth'] = np.clip(
            np.roll(psi * 50, 2) + self.rng.normal(0, 5, self.num_samples),
            0,
            None
        )
        
        # IO wait %: strongly correlated with PSI
        metrics['io_wait_pct'] = np.clip(
            psi * 40 + self.rng.normal(0, 2, self.num_samples),
            0,
            100
        )
        
        # CPU util %: moderately correlated
        metrics['cpu_util_pct'] = np.clip(
            (psi * 0.3 + 0.15) * 100 + self.rng.normal(0, 3, self.num_samples),
            0,
            100
        )
        
        # Memory usage: baseline with spikes
        metrics['memory_usage_gb'] = np.clip(
            1.5 + psi * 0.3 + self.rng.normal(0, 0.05, self.num_samples),
            0.5,
            None
        )
        
        # Pod count: baseline
        metrics['pod_count'] = np.round(
            np.clip(20 + psi * 5 + self.rng.normal(0, 2, self.num_samples), 1, 100)
        ).astype(int)
        
        # Request rate: baseline with variation
        metrics['request_rate'] = np.clip(
            50 + psi * 20 + self.rng.normal(0, 5, self.num_samples),
            10,
            None
        )
        
        # Error rate: increases during high latency
        error_rate = np.zeros(self.num_samples)
        for i in range(self.num_samples):
            if latency[i] > SLO_THRESHOLD_MS:
                error_rate[i] = self.rng.uniform(0.1, 2.0)
            else:
                error_rate[i] = self.rng.uniform(0.0, 0.2)
        metrics['error_rate'] = error_rate
        
        # P50 latency
        metrics['p50_latency_ms'] = latency * 0.4 + self.rng.normal(0, 1, self.num_samples)
        metrics['p50_latency_ms'] = np.clip(metrics['p50_latency_ms'], 5, None)
        
        # P95 latency
        metrics['p95_latency_ms'] = latency * 0.85 + self.rng.normal(0, 1, self.num_samples)
        metrics['p95_latency_ms'] = np.clip(metrics['p95_latency_ms'], 10, None)
        
        # P99.9 latency
        metrics['p99_9_latency_ms'] = latency * 1.05 + self.rng.normal(0, 2, self.num_samples)
        metrics['p99_9_latency_ms'] = np.clip(metrics['p99_9_latency_ms'], latency, None)
        
        return metrics
    
    def generate_dataset(self) -> pd.DataFrame:
        """Generate complete synthetic dataset"""
        print(f"[STEP 1] Generate baseline PSI")
        print("-" * 80)
        psi = self.generate_baseline_psi()
        print(f"✓ Generated baseline PSI")
        print(f"  Min: {psi.min():.4f}%")
        print(f"  P50: {np.median(psi):.4f}%")
        print(f"  P99: {np.percentile(psi, 99):.4f}%")
        print(f"  Max: {psi.max():.4f}%")
        print()
        
        print(f"[STEP 2] Inject {SPIKE_EVENTS} spike events")
        print("-" * 80)
        psi, latency, spike_events = self.inject_spike_events(psi)
        print(f"✓ Injected {len(spike_events)} spike events")
        print(f"  Spike duration: {SPIKE_DURATION_SAMPLES * SAMPLE_INTERVAL_SECONDS}s (~{SPIKE_DURATION_SAMPLES * SAMPLE_INTERVAL_SECONDS / 60:.1f} min)")
        print()
        
        print(f"[STEP 3] Calculate delta PSI")
        print("-" * 80)
        delta_psi = self.generate_delta_psi(psi)
        print(f"✓ Calculated delta PSI (sample-to-sample change)")
        print(f"  Min: {delta_psi.min():+.4f}%")
        print(f"  P5: {np.percentile(delta_psi, 5):+.4f}%")
        print(f"  P50: {np.median(delta_psi):+.4f}%")
        print(f"  P95: {np.percentile(delta_psi, 95):+.4f}%")
        print(f"  Max: {delta_psi.max():+.4f}%")
        print()
        
        print(f"[STEP 4] Generate timestamps and metadata")
        print("-" * 80)
        start_time = pd.Timestamp("2026-10-21 00:00:00")
        timestamps = pd.date_range(
            start=start_time,
            periods=self.num_samples,
            freq=f"{SAMPLE_INTERVAL_SECONDS}s"
        )
        print(f"✓ Generated {len(timestamps)} timestamps")
        print(f"  From: {timestamps[0]}")
        print(f"  To: {timestamps[-1]}")
        print()
        
        print(f"[STEP 5] Generate correlated metrics")
        print("-" * 80)
        metrics = self.generate_correlated_metrics(psi, latency)
        print(f"✓ Generated {len(metrics)} correlated metrics")
        for metric_name in sorted(metrics.keys()):
            values = metrics[metric_name]
            print(f"  {metric_name:25s}: min={np.min(values):8.2f}, p50={np.median(values):8.2f}, max={np.max(values):8.2f}")
        print()
        
        print(f"[STEP 6] Create DataFrame")
        print("-" * 80)
        
        # Create SLO breach labels
        slo_breach = (latency > SLO_THRESHOLD_MS).astype(int)
        
        # Time-based features
        hour_of_day = timestamps.hour.values
        day_of_week = timestamps.dayofweek.values
        minute = timestamps.hour.values * 60 + timestamps.minute.values
        minute_sin = np.sin(2 * np.pi * minute / (24 * 60))
        minute_cos = np.cos(2 * np.pi * minute / (24 * 60))
        is_business_hours = ((hour_of_day >= 8) & (hour_of_day <= 18)).astype(int)
        
        # Combine into DataFrame
        df = pd.DataFrame({
            'timestamp': timestamps,
            'time_idx': np.arange(self.num_samples),
            
            # Pressure metrics (main signals)
            'psi_some_avg10': psi.astype(np.float32),
            'delta_psi': delta_psi.astype(np.float32),
            
            # Latency metrics (labels)
            'p50_latency_ms': metrics['p50_latency_ms'].astype(np.float32),
            'p95_latency_ms': metrics['p95_latency_ms'].astype(np.float32),
            'p99_latency_ms': latency.astype(np.float32),
            'p99_9_latency_ms': metrics['p99_9_latency_ms'].astype(np.float32),
            'slo_breach': slo_breach.astype(np.int32),  # 1 if p99 > 200ms, 0 otherwise
            
            # System metrics
            'disk_iops': metrics['disk_iops'].astype(np.float32),
            'disk_queue_depth': metrics['disk_queue_depth'].astype(np.float32),
            'io_wait_pct': metrics['io_wait_pct'].astype(np.float32),
            'cpu_util_pct': metrics['cpu_util_pct'].astype(np.float32),
            'memory_usage_gb': metrics['memory_usage_gb'].astype(np.float32),
            'pod_count': metrics['pod_count'].astype(np.int32),
            'request_rate': metrics['request_rate'].astype(np.float32),
            'error_rate': metrics['error_rate'].astype(np.float32),
            
            # Time features
            'hour_of_day': hour_of_day,
            'day_of_week': day_of_week,
            'minute_sin': minute_sin.astype(np.float32),
            'minute_cos': minute_cos.astype(np.float32),
            'is_business_hours': is_business_hours,
        })
        
        print(f"✓ Created DataFrame with shape: {df.shape}")
        print()
        
        # Print summary statistics
        print(f"[STEP 7] Summary Statistics")
        print("-" * 80)
        print(f"Total samples: {len(df)}")
        print(f"Duration: {DURATION_HOURS} hours")
        print()
        
        print(f"Latency (p99):")
        print(f"  Min: {df['p99_latency_ms'].min():.2f}ms")
        print(f"  P50: {df['p99_latency_ms'].quantile(0.50):.2f}ms")
        print(f"  P95: {df['p99_latency_ms'].quantile(0.95):.2f}ms")
        print(f"  P99: {df['p99_latency_ms'].quantile(0.99):.2f}ms")
        print(f"  Max: {df['p99_latency_ms'].max():.2f}ms")
        print()
        
        print(f"SLO Breaches (p99 > {SLO_THRESHOLD_MS}ms):")
        num_breaches = df['slo_breach'].sum()
        breach_rate = 100 * num_breaches / len(df)
        print(f"  Total breaches: {num_breaches}")
        print(f"  Breach rate: {breach_rate:.2f}%")
        print()
        
        print(f"PSI metrics:")
        print(f"  Absolute PSI:")
        print(f"    Min: {df['psi_some_avg10'].min():.4f}%")
        print(f"    P50: {df['psi_some_avg10'].quantile(0.50):.4f}%")
        print(f"    P95: {df['psi_some_avg10'].quantile(0.95):.4f}%")
        print(f"    Max: {df['psi_some_avg10'].max():.4f}%")
        print()
        print(f"  Delta PSI (sample-to-sample change):")
        print(f"    Min: {df['delta_psi'].min():+.4f}%")
        print(f"    P5: {df['delta_psi'].quantile(0.05):+.4f}%")
        print(f"    P50: {df['delta_psi'].quantile(0.50):+.4f}%")
        print(f"    P95: {df['delta_psi'].quantile(0.95):+.4f}%")
        print(f"    Max: {df['delta_psi'].max():+.4f}%")
        print()
        
        # Store spike events metadata
        self.spike_events = spike_events
        
        return df
    
    def save_dataset(self, df: pd.DataFrame) -> Path:
        """Save dataset to CSV"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = DATA_DIR / f"synthetic_p99_200ms_{timestamp}.csv"
        
        df.to_csv(output_file, index=False)
        
        # Also save spike events metadata
        metadata_file = DATA_DIR / f"synthetic_p99_200ms_{timestamp}_metadata.json"
        with open(metadata_file, 'w') as f:
            # Convert numpy types to native Python types
            spike_events_serializable = []
            for event in self.spike_events:
                spike_events_serializable.append({
                    'spike_id': int(event['spike_id']),
                    'start_sample': int(event['start_sample']),
                    'end_sample': int(event['end_sample']),
                    'peak_psi_increase': float(event['peak_psi_increase']),
                    'peak_latency_increase': float(event['peak_latency_increase'])
                })
            
            json.dump({
                'dataset_file': str(output_file),
                'timestamp': timestamp,
                'config': {
                    'duration_hours': int(self.duration_hours),
                    'sample_interval_seconds': int(SAMPLE_INTERVAL_SECONDS),
                    'num_samples': int(self.num_samples),
                    'slo_threshold_ms': float(SLO_THRESHOLD_MS),
                    'spike_events': len(self.spike_events),
                    'baseline_p99_ms': float(BASELINE_P99_MS),
                    'spike_p99_ms': float(SPIKE_P99_MS),
                    'spike_psi_delta': float(SPIKE_PSI_DELTA),
                },
                'spike_events': spike_events_serializable,
            }, f, indent=2)
        
        return output_file
    
    def split_dataset(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Split into train/val/test (50%/25%/25%)"""
        n_train = int(0.50 * len(df))
        n_val = int(0.25 * len(df))
        
        train_df = df.iloc[:n_train].copy()
        val_df = df.iloc[n_train:n_train+n_val].copy()
        test_df = df.iloc[n_train+n_val:].copy()
        
        return train_df, val_df, test_df


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("SYNTHETIC WORKLOAD GENERATOR: p99 200ms Latency Breach with Delta 1.8% PSI")
    print("=" * 80)
    print()
    
    # Generate dataset
    generator = SyntheticWorkloadGenerator(
        duration_hours=DURATION_HOURS,
        sample_interval_seconds=SAMPLE_INTERVAL_SECONDS,
        seed=42
    )
    
    df = generator.generate_dataset()
    
    print(f"[STEP 8] Save dataset")
    print("-" * 80)
    output_file = generator.save_dataset(df)
    print(f"✓ Saved to: {output_file}")
    print()
    
    # Split dataset
    print(f"[STEP 9] Split dataset")
    print("-" * 80)
    train_df, val_df, test_df = generator.split_dataset(df)
    print(f"✓ Train: {len(train_df)} samples ({100*len(train_df)/len(df):.1f}%)")
    print(f"✓ Val:   {len(val_df)} samples ({100*len(val_df)/len(df):.1f}%)")
    print(f"✓ Test:  {len(test_df)} samples ({100*len(test_df)/len(df):.1f}%)")
    print()
    
    print(f"✓ Dataset generation complete!")
    print()
    print(f"Output files:")
    print(f"  - Dataset: {output_file}")
    print(f"  - Metadata: {output_file.parent / (output_file.stem + '_metadata.json')}")
    print()
    print(f"Next steps:")
    print(f"  python validate_synthetic_p99_200ms.py --data {output_file}")
    print()
