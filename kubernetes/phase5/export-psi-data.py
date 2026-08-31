#!/usr/bin/env python3
"""
Phase 5: Export PSI Data from Prometheus for Model Evaluation
Exports data in format matching training data: ptcs_training_data_full_psi.csv
"""

import subprocess
import json
import csv
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

def run_port_forward():
    """Start kubectl port-forward in background"""
    print("Starting port-forward to Prometheus...")
    proc = subprocess.Popen(
        ['kubectl', 'port-forward', '-n', 'monitoring', 
         'svc/kube-prometheus-stack-prometheus', '9090:9090'],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    time.sleep(3)
    return proc

def query_prometheus(query, start, end, step='20s'):
    """Query Prometheus range data"""
    import urllib.request
    import urllib.parse
    
    # URL encode the query properly
    params = urllib.parse.urlencode({
        'query': query,
        'start': str(start),
        'end': str(end),
        'step': step
    }, quote_via=urllib.parse.quote)
    
    url = f"http://localhost:9090/api/v1/query_range?{params}"
    
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            data = json.loads(response.read())
            
            if data.get('status') == 'error':
                print(f"Query error: {data.get('error', 'unknown')}")
                return []
            
            return data.get('data', {}).get('result', [])
    except Exception as e:
        print(f"Query failed: {e}")
        return []

def export_psi_data(duration_hours=2):
    """Export PSI data from Prometheus (recent data only)"""
    
    # Start port-forward
    pf_proc = run_port_forward()
    
    try:
        # Calculate time range - use recent data
        end_time = int(time.time())
        start_time = end_time - (duration_hours * 3600)
        
        print(f"Exporting PSI data:")
        print(f"  Start: {datetime.fromtimestamp(start_time)}")
        print(f"  End:   {datetime.fromtimestamp(end_time)}")
        print(f"  Duration: {duration_hours} hour(s)")
        print(f"  Note: Using RECENT data (from Prometheus memory)")
        print()
        
        # Query all PSI metrics
        metrics = {}
        
        metric_queries = {
            'memory_full': 'rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[10s])*100',
            'memory_some': 'rate(node_pressure_memory_waiting_seconds_total{pod=~"workload-.*"}[10s])*100',
            'cpu_full': 'rate(node_pressure_cpu_stalled_seconds_total{pod=~"workload-.*"}[10s])*100',
            'cpu_some': 'rate(node_pressure_cpu_waiting_seconds_total{pod=~"workload-.*"}[10s])*100',
            'io_full': 'rate(node_pressure_io_stalled_seconds_total{pod=~"workload-.*"}[10s])*100',
            'io_some': 'rate(node_pressure_io_waiting_seconds_total{pod=~"workload-.*"}[10s])*100',
        }
        
        for metric_name, query in metric_queries.items():
            print(f"Querying {metric_name}...")
            results = query_prometheus(query, start_time, end_time)
            
            for result in results:
                pod = result['metric']['pod']
                values = result['values']
                
                if pod not in metrics:
                    metrics[pod] = {}
                
                metrics[pod][metric_name] = {ts: float(val) for ts, val in values}
        
        if not metrics:
            print("⚠ No data found! Workloads may not have generated PSI spikes.")
            print("Check Prometheus query manually:")
            print("  http://localhost:9090")
            return None
        
        # Write CSV
        output_dir = Path('kubernetes_psi_data')
        output_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        csv_file = output_dir / f'kubernetes_psi_{timestamp}.csv'
        
        print(f"\nWriting CSV: {csv_file}")
        
        with open(csv_file, 'w', newline='') as f:
            fieldnames = [
                'timestamp',
                'pod',
                'psi_memory_full_avg10',
                'psi_memory_some_avg10',
                'psi_cpu_full_avg10',
                'psi_cpu_some_avg10',
                'psi_io_full_avg10',
                'psi_io_some_avg10'
            ]
            
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            row_count = 0
            spike_count = 0
            
            # Get all unique timestamps across all pods
            all_timestamps = set()
            for pod_data in metrics.values():
                for metric_data in pod_data.values():
                    all_timestamps.update(metric_data.keys())
            
            # Write rows
            for pod in sorted(metrics.keys()):
                pod_data = metrics[pod]
                
                # Get timestamps from first metric
                if not pod_data:
                    continue
                
                timestamps = sorted(all_timestamps)
                
                for ts in timestamps:
                    row = {
                        'timestamp': datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S'),
                        'pod': pod,
                    }
                    
                    # Add PSI values
                    row['psi_memory_full_avg10'] = pod_data.get('memory_full', {}).get(ts, 0.0)
                    row['psi_memory_some_avg10'] = pod_data.get('memory_some', {}).get(ts, 0.0)
                    row['psi_cpu_full_avg10'] = pod_data.get('cpu_full', {}).get(ts, 0.0)
                    row['psi_cpu_some_avg10'] = pod_data.get('cpu_some', {}).get(ts, 0.0)
                    row['psi_io_full_avg10'] = pod_data.get('io_full', {}).get(ts, 0.0)
                    row['psi_io_some_avg10'] = pod_data.get('io_some', {}).get(ts, 0.0)
                    
                    writer.writerow(row)
                    row_count += 1
                    
                    # Count spikes (> 1.5% threshold)
                    if row['psi_memory_full_avg10'] > 1.5:
                        spike_count += 1
        
        # Statistics
        print(f"\n✅ Export complete!")
        print(f"  Rows: {row_count}")
        print(f"  Spikes (>1.5%): {spike_count}")
        if row_count > 0:
            spike_density = (spike_count / row_count) * 100
            print(f"  Spike density: {spike_density:.2f}%")
            print(f"  Target: ~16% (training data)")
            
            if spike_density >= 14 and spike_density <= 20:
                print(f"  Status: ✅ GOOD")
            elif spike_density < 14:
                print(f"  Status: ⚠ LOW (model may not see enough spikes)")
            else:
                print(f"  Status: ⚠ HIGH")
        
        return csv_file
        
    finally:
        # Stop port-forward
        pf_proc.terminate()
        pf_proc.wait()

if __name__ == '__main__':
    duration = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
    csv_file = export_psi_data(duration)
    
    if csv_file:
        print(f"\nNext: Run model evaluation with this data")
        print(f"  python3 kubernetes/phase5/evaluate-model.py {csv_file}")
