#!/usr/bin/env python3
"""
Phase 9 Experiment Analysis
Analyzes comparative results between reactive and predictive HPA
"""

import json
import sys
from datetime import datetime
from pathlib import Path
import statistics

def parse_prometheus_export(filepath):
    """Parse Prometheus export JSON"""
    with open(filepath, 'r') as f:
        return json.load(f)

def calculate_scale_up_latency(events):
    """Calculate time from PSI breach to scale completion"""
    latencies = []
    
    for event in events:
        if 'scale_start' in event and 'scale_complete' in event:
            start = datetime.fromisoformat(event['scale_start'])
            end = datetime.fromisoformat(event['scale_complete'])
            latency = (end - start).total_seconds()
            latencies.append(latency)
    
    if not latencies:
        return None
    
    return {
        'mean': statistics.mean(latencies),
        'median': statistics.median(latencies),
        'p95': sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) > 20 else max(latencies),
        'min': min(latencies),
        'max': max(latencies),
        'count': len(latencies)
    }

def calculate_breach_metrics(psi_data, threshold=1.80):
    """Calculate PSI breach duration and count"""
    breaches = []
    in_breach = False
    breach_start = None
    
    for point in psi_data:
        timestamp = datetime.fromisoformat(point['timestamp'])
        value = point['value']
        
        if value > threshold and not in_breach:
            # Breach started
            in_breach = True
            breach_start = timestamp
        elif value <= threshold and in_breach:
            # Breach ended
            in_breach = False
            duration = (timestamp - breach_start).total_seconds()
            breaches.append(duration)
    
    if not breaches:
        return {'count': 0, 'total_duration': 0, 'mean_duration': 0}
    
    return {
        'count': len(breaches),
        'total_duration': sum(breaches),
        'mean_duration': statistics.mean(breaches),
        'max_duration': max(breaches)
    }

def calculate_pod_hours(replica_data):
    """Calculate total pod-hours"""
    total_hours = 0
    
    for i in range(len(replica_data) - 1):
        replicas = replica_data[i]['replicas']
        start = datetime.fromisoformat(replica_data[i]['timestamp'])
        end = datetime.fromisoformat(replica_data[i + 1]['timestamp'])
        duration_hours = (end - start).total_seconds() / 3600
        total_hours += replicas * duration_hours
    
    return total_hours

def generate_comparison_table(reactive_results, predictive_results):
    """Generate comparison table for paper"""
    
    print("=" * 80)
    print("PHASE 9: COMPARATIVE RESULTS")
    print("Reactive HPA vs Predictive HPA (PreSync)")
    print("=" * 80)
    print()
    
    # Table header
    print(f"{'Metric':<40} {'Reactive':<15} {'Predictive':<15} {'Improvement':<15}")
    print("-" * 80)
    
    # Scale-up latency
    if reactive_results['scale_latency'] and predictive_results['scale_latency']:
        reactive_lat = reactive_results['scale_latency']['p95']
        predictive_lat = predictive_results['scale_latency']['p95']
        improvement = ((reactive_lat - predictive_lat) / reactive_lat) * 100
        
        print(f"{'Scale-up Latency (p95)':<40} {reactive_lat:<15.2f} {predictive_lat:<15.2f} {improvement:<15.1f}%")
    
    # PSI breach duration
    reactive_breach = reactive_results['breach_metrics']['mean_duration']
    predictive_breach = predictive_results['breach_metrics']['mean_duration']
    improvement = ((reactive_breach - predictive_breach) / reactive_breach) * 100
    
    print(f"{'Mean PSI Breach Duration (s)':<40} {reactive_breach:<15.2f} {predictive_breach:<15.2f} {improvement:<15.1f}%")
    
    # Breach count
    reactive_count = reactive_results['breach_metrics']['count']
    predictive_count = predictive_results['breach_metrics']['count']
    reduction = ((reactive_count - predictive_count) / reactive_count) * 100
    
    print(f"{'PSI Breach Count':<40} {reactive_count:<15} {predictive_count:<15} {reduction:<15.1f}%")
    
    # Pod-hours
    reactive_pod_hours = reactive_results['pod_hours']
    predictive_pod_hours = predictive_results['pod_hours']
    overhead = ((predictive_pod_hours - reactive_pod_hours) / reactive_pod_hours) * 100
    
    print(f"{'Total Pod-Hours':<40} {reactive_pod_hours:<15.2f} {predictive_pod_hours:<15.2f} {overhead:<15.1f}%")
    
    # False positives (predictive only)
    if 'false_positives' in predictive_results:
        fp_count = predictive_results['false_positives']['count']
        fp_rate = predictive_results['false_positives']['rate']
        print(f"{'False Positive Predictions':<40} {'N/A':<15} {fp_count:<15} {'-':<15}")
        print(f"{'False Positive Rate':<40} {'N/A':<15} {fp_rate:<14.1f}% {'-':<15}")
    
    print("-" * 80)
    print()
    
    # Summary
    print("SUMMARY:")
    print(f"  • PreSync reduces scale-up latency by {improvement:.1f}%")
    print(f"  • PreSync reduces PSI breach duration by {((reactive_breach - predictive_breach) / reactive_breach) * 100:.1f}%")
    print(f"  • PreSync reduces breach count by {reduction:.1f}%")
    print(f"  • Resource overhead: {overhead:.1f}% more pod-hours")
    print()

def main():
    if len(sys.argv) < 3:
        print("Usage: analyze-results.py <reactive_data.json> <predictive_data.json>")
        sys.exit(1)
    
    reactive_file = Path(sys.argv[1])
    predictive_file = Path(sys.argv[2])
    
    if not reactive_file.exists() or not predictive_file.exists():
        print("Error: Data files not found")
        sys.exit(1)
    
    print("Loading experiment data...")
    reactive_data = parse_prometheus_export(reactive_file)
    predictive_data = parse_prometheus_export(predictive_file)
    
    print("Analyzing reactive HPA results...")
    reactive_results = {
        'scale_latency': calculate_scale_up_latency(reactive_data.get('events', [])),
        'breach_metrics': calculate_breach_metrics(reactive_data.get('psi_data', [])),
        'pod_hours': calculate_pod_hours(reactive_data.get('replica_data', []))
    }
    
    print("Analyzing predictive HPA results...")
    predictive_results = {
        'scale_latency': calculate_scale_up_latency(predictive_data.get('events', [])),
        'breach_metrics': calculate_breach_metrics(predictive_data.get('psi_data', [])),
        'pod_hours': calculate_pod_hours(predictive_data.get('replica_data', [])),
        'false_positives': {
            'count': predictive_data.get('false_positives', 0),
            'rate': (predictive_data.get('false_positives', 0) / len(predictive_data.get('events', []))) * 100
        }
    }
    
    print()
    generate_comparison_table(reactive_results, predictive_results)
    
    # Save results
    output_file = Path('results/comparison_results.json')
    output_file.parent.mkdir(exist_ok=True)
    
    with open(output_file, 'w') as f:
        json.dump({
            'reactive': reactive_results,
            'predictive': predictive_results,
            'timestamp': datetime.now().isoformat()
        }, f, indent=2)
    
    print(f"Results saved to: {output_file}")

if __name__ == '__main__':
    main()
