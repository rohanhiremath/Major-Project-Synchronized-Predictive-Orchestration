#!/usr/bin/env python3
"""
Step 2: Export all available historical PSI data from Prometheus
Based on retention check: 11 days available
"""

import requests
import pandas as pd
import json
from datetime import datetime, timedelta
import sys
from pathlib import Path

# Configuration
PROMETHEUS_URL = "http://localhost:9090"
RETENTION_DAYS = 11  # From Step 1
STEP_SECONDS = 20    # Native prediction interval
SPIKE_THRESHOLD = 1.80

def query_prometheus_range(query, start_ts, end_ts, step):
    """Query Prometheus range (single chunk)"""
    url = f"{PROMETHEUS_URL}/api/v1/query_range"
    params = {
        'query': query,
        'start': start_ts,
        'end': end_ts,
        'step': f'{step}s'
    }
    
    response = requests.get(url, params=params, timeout=300)
    
    if response.status_code != 200:
        print(f"    ⚠️  HTTP Error {response.status_code}: {response.text[:200]}")
        return None
    
    data = response.json()
    if data['status'] != 'success':
        print(f"    ⚠️  Query failed: {data}")
        return None
    
    return data['data']['result']

def query_prometheus_range_chunked(query, start_ts, end_ts, step, chunk_days=1):
    """Query Prometheus in chunks to avoid max resolution limit (11,000 points)"""
    print(f"Querying Prometheus in {chunk_days}-day chunks...")
    print(f"  Total range: {datetime.fromtimestamp(start_ts)} to {datetime.fromtimestamp(end_ts)}")
    print(f"  Total duration: {(end_ts - start_ts) / 86400:.1f} days")
    print(f"  Step: {step}s")
    print()
    
    # Collect unique time series
    all_series = {}
    
    current_start = start_ts
    chunk_seconds = chunk_days * 86400
    chunk_num = 0
    
    while current_start < end_ts:
        chunk_num += 1
        current_end = min(current_start + chunk_seconds, end_ts)
        
        print(f"  Chunk {chunk_num}: {datetime.fromtimestamp(current_start).strftime('%Y-%m-%d')} to {datetime.fromtimestamp(current_end).strftime('%Y-%m-%d')}")
        
        chunk_results = query_prometheus_range(query, current_start, current_end, step)
        if chunk_results:
            # Merge results by pod
            for result in chunk_results:
                pod = result['metric'].get('pod', 'unknown')
                if pod not in all_series:
                    all_series[pod] = {'metric': result['metric'], 'values': []}
                all_series[pod]['values'].extend(result['values'])
            print(f"    ✅ Retrieved {len(chunk_results)} series")
        else:
            print(f"    ⚠️  No data for this chunk")
        
        current_start = current_end
    
    # Convert back to results format
    results = [{'metric': series['metric'], 'values': series['values']} 
               for series in all_series.values()]
    
    print(f"\n✅ Total: {len(results)} time series merged")
    return results

def extract_timeseries_data(results):
    """Extract and structure time series data"""
    all_data = []
    
    for result in results:
        metric = result['metric']
        pod = metric.get('pod', 'unknown')
        job = metric.get('job', 'unknown')
        
        for timestamp, value in result['values']:
            try:
                psi_value = float(value)
                all_data.append({
                    'timestamp': datetime.fromtimestamp(timestamp),
                    'pod': pod,
                    'job': job,
                    'psi_percent': psi_value,
                    'is_spike': psi_value > SPIKE_THRESHOLD
                })
            except (ValueError, TypeError):
                continue
    
    return pd.DataFrame(all_data)

def analyze_spikes(df):
    """Analyze spike patterns in the data"""
    spikes = df[df['is_spike'] == True]
    
    # Group consecutive spikes
    spike_events = []
    if len(spikes) > 0:
        spikes_sorted = spikes.sort_values('timestamp')
        current_event = []
        
        for idx, row in spikes_sorted.iterrows():
            if not current_event:
                current_event = [row]
            else:
                # If within 1 minute of last spike, part of same event
                if (row['timestamp'] - current_event[-1]['timestamp']).total_seconds() < 60:
                    current_event.append(row)
                else:
                    # New event
                    spike_events.append(current_event)
                    current_event = [row]
        
        if current_event:
            spike_events.append(current_event)
    
    return spikes, spike_events

def main():
    print("=" * 70)
    print(" Step 2: Export Historical PSI Data from Prometheus")
    print("=" * 70)
    print()
    
    # Calculate time range (full retention window)
    end_time = datetime.now()
    start_time = end_time - timedelta(days=RETENTION_DAYS)
    
    print(f"Configuration:")
    print(f"  Retention window: {RETENTION_DAYS} days (from Step 1)")
    print(f"  Start: {start_time}")
    print(f"  End: {end_time}")
    print(f"  Sample interval: {STEP_SECONDS}s")
    print(f"  Spike threshold: {SPIKE_THRESHOLD}%")
    print()
    
    # Expected samples
    expected_samples_per_pod = (RETENTION_DAYS * 86400) // STEP_SECONDS
    expected_total = expected_samples_per_pod * 3  # 3 pods
    print(f"Expected samples: ~{expected_total:,} ({expected_samples_per_pod:,} per pod)")
    print()
    
    # Start port-forward check
    print("Checking Prometheus connectivity...")
    try:
        response = requests.get(f"{PROMETHEUS_URL}/api/v1/query?query=up", timeout=5)
        if response.status_code == 200:
            print("✅ Prometheus accessible")
        else:
            print("❌ Prometheus not accessible")
            print("\nStart port-forward first:")
            print("  kubectl port-forward -n monitoring svc/prometheus-operated 9090:9090")
            sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"❌ Cannot reach Prometheus: {e}")
        print("\nStart port-forward first:")
        print("  kubectl port-forward -n monitoring svc/prometheus-operated 9090:9090")
        sys.exit(1)
    
    print()
    
    # Query historical data
    print("=" * 70)
    print(" Querying Historical PSI Data")
    print("=" * 70)
    print()
    
    query = 'deriv(node_pressure_memory_waiting_seconds_total{pod=~"workload-app-.*"}[2m]) * 100'
    start_ts = int(start_time.timestamp())
    end_ts = int(end_time.timestamp())
    
    results = query_prometheus_range_chunked(query, start_ts, end_ts, STEP_SECONDS, chunk_days=1)
    
    if not results:
        print("❌ No data returned from Prometheus")
        sys.exit(1)
    
    print(f"✅ Retrieved data from {len(results)} time series")
    print()
    
    # Extract data
    print("Processing time series data...")
    df = extract_timeseries_data(results)
    
    if df.empty:
        print("❌ No data points extracted")
        sys.exit(1)
    
    print(f"✅ Extracted {len(df):,} data points")
    print()
    
    # Statistics
    print("=" * 70)
    print(" Dataset Statistics")
    print("=" * 70)
    print()
    
    print(f"Total samples: {len(df):,}")
    print(f"Time span: {df['timestamp'].min()} to {df['timestamp'].max()}")
    duration = (df['timestamp'].max() - df['timestamp'].min()).days
    print(f"Actual duration: {duration} days")
    print()
    
    print("Samples by pod:")
    for pod in sorted(df['pod'].unique()):
        pod_count = len(df[df['pod'] == pod])
        print(f"  {pod}: {pod_count:,}")
    print()
    
    print("PSI Statistics:")
    print(f"  Min:    {df['psi_percent'].min():.4f}%")
    print(f"  Max:    {df['psi_percent'].max():.4f}%")
    print(f"  Mean:   {df['psi_percent'].mean():.4f}%")
    print(f"  Median: {df['psi_percent'].median():.4f}%")
    print(f"  Std:    {df['psi_percent'].std():.4f}%")
    print()
    
    # Spike analysis
    print("=" * 70)
    print(f" Spike Analysis (Threshold: {SPIKE_THRESHOLD}%)")
    print("=" * 70)
    print()
    
    spikes, spike_events = analyze_spikes(df)
    
    print(f"Total spike samples: {len(spikes):,}")
    print(f"Percentage: {100 * len(spikes) / len(df):.2f}%")
    print(f"Distinct spike events: {len(spike_events)}")
    print()
    
    if len(spike_events) > 0:
        print("Spike event details:")
        for i, event in enumerate(spike_events[:10], 1):  # Show first 10
            event_df = pd.DataFrame(event)
            start = event_df['timestamp'].min()
            end = event_df['timestamp'].max()
            duration_sec = (end - start).total_seconds()
            max_psi = event_df['psi_percent'].max()
            pods = event_df['pod'].unique()
            
            print(f"  Event {i}:")
            print(f"    Time: {start}")
            print(f"    Duration: {duration_sec:.0f}s")
            print(f"    Max PSI: {max_psi:.2f}%")
            print(f"    Pods: {', '.join(pods)}")
        
        if len(spike_events) > 10:
            print(f"  ... and {len(spike_events) - 10} more events")
    else:
        print("⚠️  No spike events found above {SPIKE_THRESHOLD}% threshold")
        print("This is expected if workload has been idle")
    
    print()
    
    # Save dataset
    output_dir = Path("historical-data")
    output_dir.mkdir(exist_ok=True)
    
    csv_file = output_dir / f"psi_historical_{len(df)}_samples_{RETENTION_DAYS}days.csv"
    df.to_csv(csv_file, index=False)
    print(f"✅ Saved dataset: {csv_file}")
    
    # Save spike events
    if len(spike_events) > 0:
        spike_summary = []
        for i, event in enumerate(spike_events, 1):
            event_df = pd.DataFrame(event)
            spike_summary.append({
                'event_id': i,
                'start_time': event_df['timestamp'].min(),
                'end_time': event_df['timestamp'].max(),
                'duration_seconds': (event_df['timestamp'].max() - event_df['timestamp'].min()).total_seconds(),
                'max_psi': event_df['psi_percent'].max(),
                'avg_psi': event_df['psi_percent'].mean(),
                'sample_count': len(event_df),
                'pods_affected': ', '.join(event_df['pod'].unique())
            })
        
        spike_df = pd.DataFrame(spike_summary)
        spike_file = output_dir / f"spike_events_{len(spike_events)}_events.csv"
        spike_df.to_csv(spike_file, index=False)
        print(f"✅ Saved spike events: {spike_file}")
    
    # Save metadata
    metadata = {
        'collection_date': datetime.now().isoformat(),
        'retention_days': RETENTION_DAYS,
        'step_seconds': STEP_SECONDS,
        'spike_threshold': SPIKE_THRESHOLD,
        'total_samples': len(df),
        'time_range': {
            'start': df['timestamp'].min().isoformat(),
            'end': df['timestamp'].max().isoformat(),
            'duration_days': duration
        },
        'pods': df['pod'].unique().tolist(),
        'psi_stats': {
            'min': float(df['psi_percent'].min()),
            'max': float(df['psi_percent'].max()),
            'mean': float(df['psi_percent'].mean()),
            'median': float(df['psi_percent'].median()),
            'std': float(df['psi_percent'].std())
        },
        'spikes': {
            'total_samples': len(spikes),
            'percentage': float(100 * len(spikes) / len(df)),
            'distinct_events': len(spike_events)
        }
    }
    
    metadata_file = output_dir / "metadata.json"
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"✅ Saved metadata: {metadata_file}")
    
    print()
    print("=" * 70)
    print(" Summary")
    print("=" * 70)
    print()
    print(f"✅ Step 2 Complete!")
    print(f"   Collected: {len(df):,} samples from {duration} days")
    print(f"   Spikes: {len(spike_events)} distinct events")
    print(f"   Files: historical-data/")
    print()
    
    print("Progress toward 200k target:")
    print(f"  Historical data: {len(df):,}")
    print(f"  Remaining: {200000 - len(df):,}")
    if len(df) >= 140000:
        print(f"  ✅ Good progress! Need ~2-3 days real-time for 200k")
    else:
        print(f"  ⚠️  May need longer real-time collection")
    print()
    
    print("=" * 70)
    print(" Next Step")
    print("=" * 70)
    print()
    print("➡️  Step 3: Set up multi-scenario workload generation")
    print("   See: STEP3_WORKLOAD_SCENARIOS.md")
    print()

if __name__ == '__main__':
    main()
