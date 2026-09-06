#!/usr/bin/env python3
"""
Generate 200,000+ prediction samples from historical Prometheus data
Much faster than real-time collection (hours vs weeks)
"""

import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import sys
from pathlib import Path

# Configuration
PROMETHEUS_URL = "http://localhost:9090"
POD_PATTERN = "workload-app-.*"
LOOKBACK_DAYS = 7  # How far back to query
STEP_SECONDS = 20  # Sample interval

def query_prometheus_range(query, start, end, step):
    """Query Prometheus for a time range"""
    url = f"{PROMETHEUS_URL}/api/v1/query_range"
    params = {
        'query': query,
        'start': start,
        'end': end,
        'step': f'{step}s'
    }
    
    response = requests.get(url, params=params)
    if response.status_code != 200:
        print(f"Error querying Prometheus: {response.status_code}")
        return None
    
    data = response.json()
    if data['status'] != 'success':
        print(f"Query failed: {data}")
        return None
    
    return data['data']['result']

def extract_timeseries(results):
    """Extract time series data from Prometheus results"""
    all_data = []
    
    for result in results:
        pod = result['metric'].get('pod', 'unknown')
        values = result['values']
        
        for timestamp, value in values:
            all_data.append({
                'timestamp': datetime.fromtimestamp(timestamp),
                'pod': pod,
                'psi': float(value)
            })
    
    return pd.DataFrame(all_data)

def main():
    print("=" * 70)
    print(" Historical Data Collection for Large-Scale Validation")
    print("=" * 70)
    print()
    
    # Calculate time range
    end_time = datetime.now()
    start_time = end_time - timedelta(days=LOOKBACK_DAYS)
    
    print(f"Collection parameters:")
    print(f"  Prometheus: {PROMETHEUS_URL}")
    print(f"  Time range: {start_time} to {end_time}")
    print(f"  Duration: {LOOKBACK_DAYS} days")
    print(f"  Sample interval: {STEP_SECONDS} seconds")
    print(f"  Pod pattern: {POD_PATTERN}")
    print()
    
    # Calculate expected samples
    total_seconds = LOOKBACK_DAYS * 24 * 3600
    samples_per_pod = total_seconds // STEP_SECONDS
    estimated_total = samples_per_pod * 3  # 3 pods
    
    print(f"Expected samples:")
    print(f"  Per pod: ~{samples_per_pod:,}")
    print(f"  Total (3 pods): ~{estimated_total:,}")
    print()
    
    if estimated_total < 200000:
        print(f"⚠️  Warning: Estimated {estimated_total:,} < 200,000 target")
        print(f"   Consider: Increasing lookback days or reducing step interval")
        print()
    
    # Query PSI metrics
    print("Querying Prometheus for historical PSI data...")
    query = f'deriv(node_pressure_memory_waiting_seconds_total{{pod=~"{POD_PATTERN}"}}[2m]) * 100'
    
    start_timestamp = int(start_time.timestamp())
    end_timestamp = int(end_time.timestamp())
    
    results = query_prometheus_range(query, start_timestamp, end_timestamp, STEP_SECONDS)
    
    if not results:
        print("❌ Failed to retrieve data from Prometheus")
        print("\nTroubleshooting:")
        print("1. Ensure Prometheus is accessible:")
        print("   kubectl port-forward -n monitoring svc/prometheus-operated 9090:9090")
        print("2. Check if workload pods have metrics:")
        print("   curl 'http://localhost:9090/api/v1/query?query=node_pressure_memory_waiting_seconds_total'")
        print("3. Verify retention period (may not have 7 days of data)")
        sys.exit(1)
    
    print(f"✅ Retrieved data from {len(results)} pod(s)")
    print()
    
    # Extract and process data
    print("Processing time series data...")
    df = extract_timeseries(results)
    
    if df.empty:
        print("❌ No data extracted")
        sys.exit(1)
    
    print(f"✅ Extracted {len(df):,} data points")
    print()
    
    # Statistics
    print("=" * 70)
    print(" Dataset Statistics")
    print("=" * 70)
    print(f"\nTotal samples: {len(df):,}")
    print(f"Time span: {df['timestamp'].min()} to {df['timestamp'].max()}")
    print(f"Duration: {(df['timestamp'].max() - df['timestamp'].min()).days} days")
    print(f"\nPods: {df['pod'].nunique()}")
    for pod in df['pod'].unique():
        pod_data = df[df['pod'] == pod]
        print(f"  {pod}: {len(pod_data):,} samples")
    
    print(f"\nPSI Statistics:")
    print(f"  Min: {df['psi'].min():.4f}%")
    print(f"  Max: {df['psi'].max():.4f}%")
    print(f"  Mean: {df['psi'].mean():.4f}%")
    print(f"  Median: {df['psi'].median():.4f}%")
    print(f"  Std Dev: {df['psi'].std():.4f}%")
    
    # Spike analysis
    threshold = 1.80
    spikes = df[df['psi'] > threshold]
    print(f"\nSpikes (PSI > {threshold}%):")
    print(f"  Count: {len(spikes):,}")
    print(f"  Percentage: {100 * len(spikes) / len(df):.2f}%")
    
    print()
    
    # Save dataset
    output_dir = Path("historical-dataset")
    output_dir.mkdir(exist_ok=True)
    
    csv_file = output_dir / f"psi_historical_{len(df)}_samples.csv"
    df.to_csv(csv_file, index=False)
    print(f"✅ Saved dataset: {csv_file}")
    
    # Save metadata
    metadata = {
        'collection_date': datetime.now().isoformat(),
        'prometheus_url': PROMETHEUS_URL,
        'lookback_days': LOOKBACK_DAYS,
        'step_seconds': STEP_SECONDS,
        'total_samples': len(df),
        'pods': df['pod'].unique().tolist(),
        'time_range': {
            'start': df['timestamp'].min().isoformat(),
            'end': df['timestamp'].max().isoformat()
        },
        'psi_stats': {
            'min': float(df['psi'].min()),
            'max': float(df['psi'].max()),
            'mean': float(df['psi'].mean()),
            'median': float(df['psi'].median()),
            'std': float(df['psi'].std())
        },
        'spikes': {
            'threshold': threshold,
            'count': len(spikes),
            'percentage': float(100 * len(spikes) / len(df))
        }
    }
    
    metadata_file = output_dir / "metadata.json"
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"✅ Saved metadata: {metadata_file}")
    
    print()
    print("=" * 70)
    print(" Next Steps")
    print("=" * 70)
    print("\n1. If samples < 200,000:")
    print("   - Increase LOOKBACK_DAYS (e.g., 14, 30)")
    print("   - Reduce STEP_SECONDS (e.g., 10, 5)")
    print("   - Edit this script and re-run")
    print("\n2. Run batch predictions on this dataset:")
    print("   python3 batch-predict-large.py historical-dataset/psi_historical_*.csv")
    print("\n3. Analyze results for your paper")
    print()
    
    if len(df) >= 200000:
        print("🎉 SUCCESS: Collected 200,000+ samples!")
    else:
        print(f"⚠️  Collected {len(df):,} samples (target: 200,000)")
        print(f"   Need {200000 - len(df):,} more samples")
        
        # Suggest adjustment
        needed_ratio = 200000 / len(df)
        new_days = int(LOOKBACK_DAYS * needed_ratio) + 1
        print(f"\n💡 Suggestion: Set LOOKBACK_DAYS = {new_days} to reach target")

if __name__ == '__main__':
    main()
