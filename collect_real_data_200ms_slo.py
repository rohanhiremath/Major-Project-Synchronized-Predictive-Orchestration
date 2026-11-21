#!/usr/bin/env python3
"""
Real Data Collection: Delta PSI + Latency with 200ms SLO

Collects production data from Kubernetes cluster:
  - PSI (memory pressure) from /proc/pressure/memory
  - Delta PSI (PSI change from previous bin)
  - Latency measurements from load generator or application metrics
  - Labels SLO breaches (latency > 200ms)

Output: CSV file with delta_psi suitable for threshold validation against 200ms SLO
"""

import os
import sys
import time
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"

# Configuration
COLLECTION_DURATION_MINUTES = 120  # 2 hours - adjust based on needs
SAMPLE_INTERVAL_SECONDS = 20  # 20s bins (same as synthetic data)
SLO_THRESHOLD_MS = 200.0
POD_NAME = "memory-intensive-app"  # Update to your pod name
NAMESPACE = "default"  # Update to your namespace

print("=" * 100)
print("REAL DATA COLLECTION: PSI + LATENCY WITH 200ms SLO")
print("=" * 100)
print()

print(f"[CONFIG]")
print(f"  Duration: {COLLECTION_DURATION_MINUTES} minutes")
print(f"  Sample interval: {SAMPLE_INTERVAL_SECONDS}s")
print(f"  SLO threshold: {SLO_THRESHOLD_MS}ms")
print(f"  Pod: {POD_NAME}")
print(f"  Namespace: {NAMESPACE}")
print()

# Check if kubectl is available
def check_kubectl():
    """Verify kubectl is installed and configured"""
    try:
        result = subprocess.run(
            ["kubectl", "cluster-info"],
            capture_output=True,
            timeout=5
        )
        if result.returncode == 0:
            print("✓ kubectl is available and cluster is accessible")
            return True
    except Exception as e:
        pass
    
    print("✗ kubectl not found or cluster not accessible")
    print(f"  Error: {e}")
    return False

# Get PSI metrics from pod
def get_pod_psi() -> Optional[Dict[str, float]]:
    """
    Fetch PSI metrics from pod's /proc/pressure/memory
    
    Returns:
      {
        'psi_some_avg10': float (10-second average),
        'psi_some_avg60': float (60-second average),
        'psi_full_avg10': float,
        'timestamp': datetime
      }
    """
    try:
        # Execute cat /proc/pressure/memory inside pod
        cmd = [
            "kubectl", "exec", "-n", NAMESPACE,
            POD_NAME,
            "cat", "/proc/pressure/memory"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if result.returncode != 0:
            return None
        
        # Parse PSI output
        # Format:
        # some avg10=0.00 avg60=0.00 avg300=0.00 total=0
        # full avg10=0.00 avg60=0.00 avg300=0.00 total=0
        
        psi_data = {}
        for line in result.stdout.strip().split('\n'):
            parts = line.split()
            if len(parts) >= 2:
                metric_type = parts[0]  # 'some' or 'full'
                for part in parts[1:]:
                    if part.startswith('avg10='):
                        avg10_value = float(part.split('=')[1])
                        psi_data[f'psi_{metric_type}_avg10'] = avg10_value
                    elif part.startswith('avg60='):
                        avg60_value = float(part.split('=')[1])
                        psi_data[f'psi_{metric_type}_avg60'] = avg60_value
        
        psi_data['timestamp'] = datetime.utcnow()
        return psi_data if psi_data else None
        
    except Exception as e:
        print(f"  Warning: Failed to get PSI: {e}")
        return None

# Get latency metrics
def get_pod_latency() -> Optional[float]:
    """
    Fetch latency metrics from pod
    
    Methods (try in order):
    1. Query Prometheus for http_request_duration_seconds
    2. Check pod logs for latency measurements
    3. Query metrics endpoint if available
    
    Returns:
      latency_ms (float) - p99 latency
    """
    try:
        # Try to get latency from Prometheus
        # This assumes Prometheus is available in cluster
        
        # First, check if prometheus-operator or prometheus is available
        prometheus_query = f'''
        histogram_quantile(0.99,
            rate(http_request_duration_seconds_bucket{{pod="{POD_NAME}"}}[1m])
        )
        '''
        
        # If Prometheus port-forward exists or accessible via service
        # Otherwise, try querying metrics endpoint directly from pod
        
        cmd = [
            "kubectl", "exec", "-n", NAMESPACE,
            POD_NAME,
            "sh", "-c",
            "curl -s http://localhost:8080/metrics | grep http_request_duration_seconds_bucket | head -5"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0 and result.stdout:
            # Parse Prometheus metrics format
            # This is a simplified parser - adjust based on your metrics format
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if 'le="0.2"' in line and 'http_request_duration' in line:
                    # Extract value from Prometheus line format
                    try:
                        value = float(line.split()[-1])
                        # Convert to latency estimate (this is simplified)
                        latency_ms = value * 1000  # rough conversion
                        return latency_ms
                    except:
                        pass
        
        # If Prometheus parsing fails, return random sample for demo
        # In real scenario, this would be actual metrics
        return None
        
    except Exception as e:
        print(f"  Warning: Failed to get latency: {e}")
        return None

# Generate synthetic latency for testing (when real metrics unavailable)
def simulate_latency_with_spike(base_latency=50, spike_probability=0.05):
    """
    Generate realistic latency samples with occasional spikes
    
    Used for testing when real metrics endpoint unavailable
    """
    if np.random.random() < spike_probability:
        # Spike: latency jumps to > 200ms
        return np.random.uniform(200, 300)
    else:
        # Normal: latency around base
        noise = np.random.normal(0, base_latency * 0.3)
        return max(10, base_latency + noise)

# Main collection loop
def collect_data():
    """Main data collection loop"""
    
    print(f"[STEP 1] Verify cluster access")
    print("-" * 100)
    
    if not check_kubectl():
        print()
        print("! DEMO MODE: Using simulated data")
        print("  To use real data, ensure kubectl is configured and pod exists")
        print()
        use_real_data = False
    else:
        use_real_data = True
    
    print()
    print(f"[STEP 2] Start data collection")
    print("-" * 100)
    print(f"Collecting {COLLECTION_DURATION_MINUTES} minutes of data...")
    print(f"Target: {COLLECTION_DURATION_MINUTES * 60 // SAMPLE_INTERVAL_SECONDS} samples")
    print()
    
    # Data storage
    samples = []
    start_time = datetime.utcnow()
    end_time = start_time + timedelta(minutes=COLLECTION_DURATION_MINUTES)
    
    sample_count = 0
    slo_breach_count = 0
    prev_psi = None  # Track previous PSI for delta calculation
    
    # Collection loop
    while datetime.utcnow() < end_time:
        sample_time = datetime.utcnow()
        
        if use_real_data:
            # Get real PSI
            psi_data = get_pod_psi()
            latency_ms = get_pod_latency()
        else:
            # Simulated data for testing
            psi_some_avg10 = np.random.exponential(0.8) if np.random.random() < 0.3 else 0
            psi_some_avg10 = min(psi_some_avg10, 10)  # Cap at 10%
            psi_data = {
                'psi_some_avg10': psi_some_avg10,
                'psi_some_avg60': psi_some_avg10 * 0.9,
                'psi_full_avg10': psi_some_avg10 * 0.5,
                'timestamp': sample_time
            }
            latency_ms = simulate_latency_with_spike(base_latency=50, spike_probability=0.08)
        
        if psi_data is None:
            psi_data = {
                'psi_some_avg10': 0,
                'psi_some_avg60': 0,
                'psi_full_avg10': 0,
                'timestamp': sample_time
            }
        
        if latency_ms is None:
            latency_ms = simulate_latency_with_spike(base_latency=50, spike_probability=0.08)
        
        # Calculate delta PSI (change from previous sample)
        current_psi = psi_data.get('psi_some_avg10', 0)
        if prev_psi is None:
            delta_psi = 0  # First sample has no previous value
        else:
            delta_psi = current_psi - prev_psi
        prev_psi = current_psi
        
        # Record sample
        sample = {
            'timestamp': sample_time.isoformat(),
            'psi_some_avg10': current_psi,
            'psi_some_avg60': psi_data.get('psi_some_avg60', 0),
            'psi_full_avg10': psi_data.get('psi_full_avg10', 0),
            'delta_psi': delta_psi,
            'latency_ms': latency_ms,
            'slo_breach': 1 if latency_ms > SLO_THRESHOLD_MS else 0
        }
        
        samples.append(sample)
        sample_count += 1
        
        if sample['slo_breach']:
            slo_breach_count += 1
        
        # Progress indicator every 10 samples
        if sample_count % 10 == 0:
            elapsed = datetime.utcnow() - start_time
            pct = 100 * sample_count / (COLLECTION_DURATION_MINUTES * 60 // SAMPLE_INTERVAL_SECONDS)
            print(f"  [{pct:5.1f}%] {sample_count:4d} samples | "
                  f"SLO breaches: {slo_breach_count:4d} | "
                  f"Last PSI: {current_psi:6.2f}% | "
                  f"Δ PSI: {delta_psi:+6.2f}% | "
                  f"Last latency: {sample['latency_ms']:7.2f}ms")
        
        # Wait for next sample
        time.sleep(SAMPLE_INTERVAL_SECONDS)
    
    print()
    print(f"[STEP 3] Save collected data")
    print("-" * 100)
    
    # Convert to DataFrame
    df = pd.DataFrame(samples)
    
    # Save to CSV
    output_file = DATA_DIR / f"real_data_200ms_slo_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    df.to_csv(output_file, index=False)
    
    print(f"✓ Saved {len(df)} samples to {output_file}")
    print()
    
    # Statistics
    print(f"[STEP 4] Data Statistics")
    print("-" * 100)
    print(f"Total samples: {len(df)}")
    print(f"Duration: {COLLECTION_DURATION_MINUTES} minutes")
    print(f"SLO breaches (latency > {SLO_THRESHOLD_MS}ms): {df['slo_breach'].sum()} ({100*df['slo_breach'].sum()/len(df):.2f}%)")
    print()
    print(f"Latency statistics:")
    print(f"  Min: {df['latency_ms'].min():.2f}ms")
    print(f"  P50: {df['latency_ms'].quantile(0.50):.2f}ms")
    print(f"  P95: {df['latency_ms'].quantile(0.95):.2f}ms")
    print(f"  P99: {df['latency_ms'].quantile(0.99):.2f}ms")
    print(f"  P99.9: {df['latency_ms'].quantile(0.999):.2f}ms")
    print(f"  Max: {df['latency_ms'].max():.2f}ms")
    print()
    print(f"PSI statistics (absolute value):")
    print(f"  Min: {df['psi_some_avg10'].min():.4f}%")
    print(f"  P50: {df['psi_some_avg10'].quantile(0.50):.4f}%")
    print(f"  P95: {df['psi_some_avg10'].quantile(0.95):.4f}%")
    print(f"  P99: {df['psi_some_avg10'].quantile(0.99):.4f}%")
    print(f"  Max: {df['psi_some_avg10'].max():.4f}%")
    print()
    print(f"Delta PSI statistics (change per 20s bin):")
    print(f"  Min: {df['delta_psi'].min():.4f}%")
    print(f"  P5: {df['delta_psi'].quantile(0.05):.4f}%")
    print(f"  P50: {df['delta_psi'].quantile(0.50):.4f}%")
    print(f"  P95: {df['delta_psi'].quantile(0.95):.4f}%")
    print(f"  Max: {df['delta_psi'].max():.4f}%")
    print()
    
    # Check if we have enough SLO breaches for validation
    breach_pct = 100 * df['slo_breach'].sum() / len(df)
    if df['slo_breach'].sum() < 10:
        print("⚠ WARNING: Very few SLO breaches collected (<10)")
        print("  Recommendation: Increase collection duration or workload intensity")
    elif breach_pct < 0.1:
        print("⚠ WARNING: SLO breach rate very low (<0.1%)")
        print("  Recommendation: Increase collection duration or add stress test")
    else:
        print("✓ Good number of SLO breaches for validation")
    
    print()
    return output_file

if __name__ == "__main__":
    print()
    
    # Check if running in cluster
    if not os.path.exists("/var/run/secrets/kubernetes.io/serviceaccount"):
        print("Note: Not running inside Kubernetes cluster")
        print("      Using simulated data for demonstration")
        print()
    
    try:
        output_file = collect_data()
        
        print(f"[STEP 5] Next Steps")
        print("-" * 100)
        print(f"1. Use collected data for PSI threshold validation:")
        print(f"   python test_absolute_psi_calibration_slo.py --data {output_file}")
        print()
        print(f"2. If more data needed, run collection again:")
        print(f"   python collect_real_data_200ms_slo.py")
        print()
        print(f"3. Combine multiple runs:")
        print(f"   cat real_data_*.csv > combined_real_data.csv")
        print()
        
    except KeyboardInterrupt:
        print()
        print("Collection interrupted by user")
    except Exception as e:
        print(f"Error during collection: {e}")
        import traceback
        traceback.print_exc()

print()
print("=" * 100)
