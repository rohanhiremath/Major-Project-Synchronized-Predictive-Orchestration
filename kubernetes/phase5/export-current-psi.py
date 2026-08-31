#!/usr/bin/env python3
"""
Phase 5: Export CURRENT PSI Data from Pods
Since Prometheus historical data has issues, collect directly from pods
"""

import subprocess
import csv
import time
from datetime import datetime
from pathlib import Path

def get_psi_from_pod(pod_name):
    """Get PSI metrics directly from pod"""
    try:
        cmd = [
            'kubectl', 'exec', pod_name, '-c', 'node-exporter', '--',
            'wget', '-qO-', 'http://localhost:9100/metrics'
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if result.returncode != 0:
            return None
        
        metrics = {}
        for line in result.stdout.split('\n'):
            if line.startswith('node_pressure') and 'seconds_total' in line and not line.startswith('#'):
                parts = line.split()
                if len(parts) >= 2:
                    metric_name = parts[0]
                    value = float(parts[1])
                    metrics[metric_name] = value
        
        return metrics
    except Exception as e:
        print(f"Error getting PSI from {pod_name}: {e}")
        return None

def collect_psi_samples(duration_seconds=3600, interval_seconds=20):
    """Collect PSI samples over time"""
    
    print(f"🔍 Collecting PSI data from pods")
    print(f"   Duration: {duration_seconds}s ({duration_seconds//60} minutes)")
    print(f"   Interval: {interval_seconds}s")
    print(f"   Expected samples: {duration_seconds//interval_seconds} per pod")
    print()
    
    pods = ['workload-app-0', 'workload-app-1', 'workload-app-2']
    
    output_dir = Path('kubernetes_psi_data')
    output_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    csv_file = output_dir / f'kubernetes_psi_live_{timestamp}.csv'
    
    # CSV writer
    with open(csv_file, 'w', newline='') as f:
        fieldnames = [
            'timestamp',
            'pod',
            'psi_memory_full_total',
            'psi_memory_some_total',
            'psi_cpu_full_total',
            'psi_cpu_some_total',
            'psi_io_full_total',
            'psi_io_some_total'
        ]
        
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        start_time = time.time()
        sample_count = 0
        
        print(f"Starting collection... (Ctrl+C to stop early)")
        print()
        
        try:
            while (time.time() - start_time) < duration_seconds:
                iteration_start = time.time()
                current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                for pod in pods:
                    metrics = get_psi_from_pod(pod)
                    
                    if metrics:
                        row = {
                            'timestamp': current_time,
                            'pod': pod,
                            'psi_memory_full_total': metrics.get('node_pressure_memory_stalled_seconds_total', 0),
                            'psi_memory_some_total': metrics.get('node_pressure_memory_waiting_seconds_total', 0),
                            'psi_cpu_full_total': metrics.get('node_pressure_cpu_stalled_seconds_total', 0),
                            'psi_cpu_some_total': metrics.get('node_pressure_cpu_waiting_seconds_total', 0),
                            'psi_io_full_total': metrics.get('node_pressure_io_stalled_seconds_total', 0),
                            'psi_io_some_total': metrics.get('node_pressure_io_waiting_seconds_total', 0),
                        }
                        
                        writer.writerow(row)
                        f.flush()  # Flush to disk
                        sample_count += 1
                
                elapsed = time.time() - start_time
                remaining = duration_seconds - elapsed
                progress = (elapsed / duration_seconds) * 100
                
                print(f"\r[{progress:5.1f}%] Samples: {sample_count:4d} | Remaining: {int(remaining):4d}s", end='', flush=True)
                
                # Sleep for remaining interval time
                iteration_time = time.time() - iteration_start
                sleep_time = max(0, interval_seconds - iteration_time)
                time.sleep(sleep_time)
        
        except KeyboardInterrupt:
            print(f"\n\n⚠ Collection interrupted by user")
    
    print(f"\n\n✅ Collection complete!")
    print(f"   Samples collected: {sample_count}")
    print(f"   File: {csv_file}")
    print()
    
    # Calculate rates from raw counters
    print("Converting to rate (PSI percentage)...")
    rate_csv = output_dir / f'kubernetes_psi_rates_{timestamp}.csv'
    
    with open(csv_file, 'r') as infile, open(rate_csv, 'w', newline='') as outfile:
        reader = csv.DictReader(infile)
        
        fieldnames_out = [
            'timestamp',
            'pod',
            'psi_memory_full_avg10',
            'psi_memory_some_avg10',
            'psi_cpu_full_avg10',
            'psi_cpu_some_avg10',
            'psi_io_full_avg10',
            'psi_io_some_avg10'
        ]
        
        writer_out = csv.DictWriter(outfile, fieldnames=fieldnames_out)
        writer_out.writeheader()
        
        rows = list(reader)
        
        # Calculate rates (difference between consecutive samples)
        for pod in pods:
            pod_rows = [r for r in rows if r['pod'] == pod]
            
            for i in range(1, len(pod_rows)):
                prev = pod_rows[i-1]
                curr = pod_rows[i]
                
                # Time difference (assuming 20s interval)
                time_diff = interval_seconds
                
                # Calculate rates (percentage)
                row_out = {
                    'timestamp': curr['timestamp'],
                    'pod': curr['pod'],
                }
                
                for metric_type in ['memory_full', 'memory_some', 'cpu_full', 'cpu_some', 'io_full', 'io_some']:
                    total_key = f'psi_{metric_type}_total'
                    avg_key = f'psi_{metric_type}_avg10'
                    
                    prev_val = float(prev.get(total_key, 0))
                    curr_val = float(curr.get(total_key, 0))
                    
                    # Rate = (current - previous) / time_diff * 100
                    rate = ((curr_val - prev_val) / time_diff) * 100
                    row_out[avg_key] = max(0, rate)  # Ensure non-negative
                
                writer_out.writerow(row_out)
    
    print(f"✅ Rates calculated: {rate_csv}")
    print()
    
    # Analyze spike density
    with open(rate_csv, 'r') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        
        if rows:
            spike_count = sum(1 for r in rows if float(r['psi_memory_full_avg10']) > 1.5)
            total = len(rows)
            spike_density = (spike_count / total) * 100
            
            print(f"📊 Analysis:")
            print(f"   Total samples: {total}")
            print(f"   Spikes (>1.5%): {spike_count}")
            print(f"   Spike density: {spike_density:.2f}% (target: ~16%)")
            
            if spike_density >= 14 and spike_density <= 20:
                print(f"   Status: ✅ GOOD")
            elif spike_density < 14:
                print(f"   Status: ⚠ LOW")
            else:
                print(f"   Status: ⚠ HIGH")
    
    return rate_csv

if __name__ == '__main__':
    import sys
    
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 1800  # Default 30 minutes
    interval = int(sys.argv[2]) if len(sys.argv) > 2 else 20    # Default 20s
    
    print(f"=" * 60)
    print("PHASE 5: LIVE PSI DATA COLLECTION")
    print(f"=" * 60)
    print()
    
    csv_file = collect_psi_samples(duration, interval)
    
    print()
    print(f"Next: Evaluate model on this data")
    print(f"  python3 kubernetes/phase5/evaluate-model.py {csv_file}")
