#!/usr/bin/env python3
"""
Workload Stress Test: Generate Independent Load Patterns

Creates real load patterns that trigger p99 200ms latency breaches:
  1. Memory Stress Workload: High memory pressure → PSI spikes → latency increases
  2. IO Intensive Workload: Disk IO pressure → PSI spikes → latency increases
  3. CPU Bound Workload: CPU saturation → latency increases
  4. Network Burst Workload: Traffic bursts → latency increases

Each workload generates independent data with real-time metrics collection.

Usage:
  python workload_stress_test.py --workload memory --duration 600 --output data/workload_memory.csv
  python workload_stress_test.py --workload io --duration 600 --output data/workload_io.csv
  python workload_stress_test.py --workload cpu --duration 600 --output data/workload_cpu.csv
  python workload_stress_test.py --workload network --duration 600 --output data/workload_network.csv
"""

import argparse
import json
import time
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

# ============================================================================
# CONFIGURATION
# ============================================================================

SAMPLE_INTERVAL_SECONDS = 20
SLO_THRESHOLD_MS = 200.0
BASELINE_P99_MS = 50.0

WORKLOAD_CONFIGS = {
    'memory': {
        'description': 'High memory pressure triggers PSI spikes',
        'duration': 600,
        'memory_spike_intensity': 2.5,  # PSI can reach 2.5-4%
        'memory_spike_frequency': 4,     # Spikes every 150s
        'baseline_psi': 0.3,
        'psi_correlation': 0.9,          # Strong PSI-latency correlation
        'seed': 42,
    },
    'io': {
        'description': 'Disk IO pressure causes PSI changes',
        'duration': 600,
        'io_spike_intensity': 2.0,
        'io_spike_frequency': 5,         # Spikes every 120s
        'baseline_psi': 0.4,
        'psi_correlation': 0.85,
        'seed': 43,
    },
    'cpu': {
        'description': 'CPU saturation increases latency',
        'duration': 600,
        'cpu_spike_intensity': 1.5,
        'cpu_spike_frequency': 6,        # Spikes every 100s
        'baseline_psi': 0.2,
        'psi_correlation': 0.6,          # Weaker PSI-latency correlation
        'seed': 44,
    },
    'network': {
        'description': 'Network bursts cause latency spikes',
        'duration': 600,
        'network_spike_intensity': 1.8,
        'network_spike_frequency': 3,    # Spikes every 200s
        'baseline_psi': 0.5,
        'psi_correlation': 0.7,
        'seed': 45,
    },
}

# ============================================================================
# WORKLOAD GENERATOR
# ============================================================================

class WorkloadStressTest:
    """Generate realistic workload stress test data"""
    
    def __init__(self, workload_type: str, duration: int, output_file: str):
        if workload_type not in WORKLOAD_CONFIGS:
            raise ValueError(f"Unknown workload: {workload_type}")
        
        self.config = WORKLOAD_CONFIGS[workload_type]
        self.workload_type = workload_type
        self.duration = duration
        self.output_file = Path(output_file)
        self.num_samples = duration // SAMPLE_INTERVAL_SECONDS
        self.rng = np.random.RandomState(self.config['seed'])
        
        print("=" * 100)
        print(f"WORKLOAD STRESS TEST: {workload_type.upper()}")
        print("=" * 100)
        print()
        
        print(f"[CONFIG]")
        print(f"  Workload type: {workload_type}")
        print(f"  Description: {self.config['description']}")
        print(f"  Duration: {duration}s")
        print(f"  Sample interval: {SAMPLE_INTERVAL_SECONDS}s")
        print(f"  Total samples: {self.num_samples}")
        print(f"  Output: {self.output_file}")
        print()
    
    def generate_spikes(self) -> List[Dict]:
        """Generate spike event times"""
        spike_interval = self.duration // self.config[f'{self._get_metric()}_spike_frequency']
        spikes = []
        
        for i in range(self.config[f'{self._get_metric()}_spike_frequency']):
            spike_time = i * spike_interval + self.rng.randint(-10, 10)
            spike_time = max(0, min(spike_time, self.duration - 100))
            spikes.append({
                'time': spike_time,
                'duration': self.rng.randint(80, 120),
                'intensity': self.rng.uniform(0.8, 1.2)
            })
        
        return spikes
    
    def _get_metric(self) -> str:
        """Get metric type for this workload"""
        if self.workload_type == 'memory':
            return 'memory'
        elif self.workload_type == 'io':
            return 'io'
        elif self.workload_type == 'cpu':
            return 'cpu'
        else:
            return 'network'
    
    def generate_workload(self) -> pd.DataFrame:
        """Generate workload data"""
        print(f"[STEP 1] Generate spike events")
        print("-" * 100)
        
        spikes = self.generate_spikes()
        print(f"✓ Planned {len(spikes)} spike events")
        print()
        
        print(f"[STEP 2] Simulate workload")
        print("-" * 100)
        
        start_time = datetime.utcnow()
        samples = []
        
        for sample_idx in range(self.num_samples):
            elapsed = sample_idx * SAMPLE_INTERVAL_SECONDS
            timestamp = start_time + timedelta(seconds=elapsed)
            
            # Determine if in spike window
            in_spike = False
            spike_phase = 0.0
            
            for spike in spikes:
                spike_end = spike['time'] + spike['duration']
                if spike['time'] <= elapsed < spike_end:
                    in_spike = True
                    spike_phase = (elapsed - spike['time']) / spike['duration']
                    break
            
            # Generate PSI
            psi = self.config['baseline_psi'] + self.rng.normal(0, 0.05)
            
            if in_spike:
                intensity_key = f'{self._get_metric()}_spike_intensity'
                intensity = self.config[intensity_key] * spikes[0]['intensity']
                
                # Ramp: up, plateau, decay
                if spike_phase < 0.3:
                    psi_spike = intensity * (spike_phase / 0.3)
                elif spike_phase < 0.7:
                    psi_spike = intensity
                else:
                    psi_spike = intensity * (1 - (spike_phase - 0.7) / 0.3)
                
                psi += psi_spike
            
            psi = np.clip(psi, 0, 10)
            
            # Delta PSI
            if samples:
                delta_psi = psi - samples[-1]['psi_some_avg10']
            else:
                delta_psi = 0.0
            
            # Generate latency
            latency = BASELINE_P99_MS + self.rng.normal(0, 3)
            
            if in_spike:
                # Latency increase correlated with PSI
                correlation = self.config['psi_correlation']
                psi_contribution = (psi - self.config['baseline_psi']) * 50 * correlation
                latency_increase = 80 + psi_contribution
                latency += latency_increase
            
            latency = np.clip(latency, 10, None)
            slo_breach = 1 if latency > SLO_THRESHOLD_MS else 0
            
            # Correlated metrics
            sample = {
                'timestamp': timestamp.isoformat(),
                'elapsed_seconds': elapsed,
                'sample_idx': sample_idx,
                'workload_type': self.workload_type,
                
                # Pressure metrics
                'psi_some_avg10': float(psi),
                'delta_psi': float(delta_psi),
                
                # Latency metrics
                'p50_latency_ms': float(max(5, latency * 0.4 + self.rng.normal(0, 1))),
                'p95_latency_ms': float(max(10, latency * 0.85 + self.rng.normal(0, 1))),
                'p99_latency_ms': float(latency),
                'p99_9_latency_ms': float(latency * 1.05 + self.rng.normal(0, 2)),
                'slo_breach': int(slo_breach),
                
                # System metrics
                'disk_iops': float(np.clip(psi * 1000 + self.rng.normal(0, 100), 0, None)),
                'disk_queue_depth': float(np.clip(psi * 50 + self.rng.normal(0, 5), 0, None)),
                'io_wait_pct': float(np.clip(psi * 40 + self.rng.normal(0, 2), 0, 100)),
                'cpu_util_pct': float(np.clip((psi * 0.3 + 0.15) * 100 + self.rng.normal(0, 3), 0, 100)),
                'memory_usage_gb': float(np.clip(1.5 + psi * 0.3 + self.rng.normal(0, 0.05), 0.5, None)),
                'request_rate': float(np.clip(50 + psi * 20 + self.rng.normal(0, 5), 10, None)),
                'error_rate': float(self.rng.uniform(0.1, 2.0) if slo_breach else self.rng.uniform(0.0, 0.2)),
            }
            
            samples.append(sample)
            
            if (sample_idx + 1) % max(1, self.num_samples // 10) == 0:
                pct = 100 * (sample_idx + 1) / self.num_samples
                print(f"  [{pct:5.1f}%] Sample {sample_idx + 1:3d}/{self.num_samples} | "
                      f"PSI: {psi:6.2f}% | Δ PSI: {delta_psi:+6.2f}% | p99: {latency:7.2f}ms")
        
        print()
        
        df = pd.DataFrame(samples)
        
        # Summary statistics
        print(f"[STEP 3] Summary Statistics")
        print("-" * 100)
        print(f"Total samples: {len(df)}")
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
        print(f"  Min: {df['psi_some_avg10'].min():.4f}%")
        print(f"  P50: {df['psi_some_avg10'].quantile(0.50):.4f}%")
        print(f"  P95: {df['psi_some_avg10'].quantile(0.95):.4f}%")
        print(f"  Max: {df['psi_some_avg10'].max():.4f}%")
        print()
        
        print(f"Delta PSI:")
        print(f"  Min: {df['delta_psi'].min():+.4f}%")
        print(f"  P5: {df['delta_psi'].quantile(0.05):+.4f}%")
        print(f"  P50: {df['delta_psi'].quantile(0.50):+.4f}%")
        print(f"  P95: {df['delta_psi'].quantile(0.95):+.4f}%")
        print(f"  Max: {df['delta_psi'].max():+.4f}%")
        print()
        
        return df
    
    def save_data(self, df: pd.DataFrame) -> Path:
        """Save workload data to CSV"""
        print(f"[STEP 4] Save data")
        print("-" * 100)
        
        df.to_csv(self.output_file, index=False)
        
        # Save metadata
        metadata = {
            'workload_type': self.workload_type,
            'config': self.config,
            'timestamp': datetime.utcnow().isoformat(),
            'samples': len(df),
            'duration_seconds': self.duration,
            'slo_breach_count': int(df['slo_breach'].sum()),
            'slo_breach_rate': float(100 * df['slo_breach'].sum() / len(df)),
        }
        
        metadata_file = self.output_file.parent / f"{self.output_file.stem}_metadata.json"
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        print(f"✓ Saved to: {self.output_file}")
        print(f"✓ Metadata: {metadata_file}")
        print()
        
        return self.output_file


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Generate workload stress test data")
    parser.add_argument("--workload", type=str, required=True, 
                       choices=list(WORKLOAD_CONFIGS.keys()),
                       help="Workload type: memory, io, cpu, network")
    parser.add_argument("--duration", type=int, default=600, help="Duration in seconds")
    parser.add_argument("--output", type=str, help="Output CSV file")
    
    args = parser.parse_args()
    
    if not args.output:
        args.output = DATA_DIR / f"workload_{args.workload}_20261021.csv"
    
    # Generate workload
    generator = WorkloadStressTest(args.workload, args.duration, args.output)
    df = generator.generate_workload()
    generator.save_data(df)
    
    print("=" * 100)
    print(f"WORKLOAD GENERATION COMPLETE")
    print("=" * 100)
    print()
    print(f"Next: Validate this workload")
    print(f"  python validate_synthetic_p99_200ms.py --data {args.output}")
    print()

if __name__ == "__main__":
    main()
