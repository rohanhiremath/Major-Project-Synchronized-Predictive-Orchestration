#!/bin/bash
# Phase 4: Collect PSI Data for Model Evaluation

DURATION=${1:-3600}  # Default 1 hour
OUTPUT_DIR="workload_data"

set -e

echo "============================================================"
echo "PHASE 4: PSI DATA COLLECTION"
echo "Duration: ${DURATION} seconds ($((DURATION/60)) minutes)"
echo "============================================================"
echo ""

# Create output directory
mkdir -p "$OUTPUT_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Start port-forward
echo "Starting Prometheus port-forward..."
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090 > /dev/null 2>&1 &
PF_PID=$!
sleep 3

cleanup() {
    echo ""
    echo "Cleaning up..."
    kill $PF_PID 2>/dev/null || true
}
trap cleanup EXIT

START_TIME=$(date -u +%s)
END_TIME=$((START_TIME + DURATION))

echo "Collection started at: $(date -u -d @$START_TIME)"
echo "Collection will end at: $(date -u -d @$END_TIME)"
echo ""

# Collect PSI metrics
echo "Collecting PSI metrics from Prometheus..."

# Memory PSI (all types)
for metric in stalled waiting; do
    echo "  • node_pressure_memory_${metric}_seconds_total"
    curl -s "http://localhost:9090/api/v1/query_range?query=rate(node_pressure_memory_${metric}_seconds_total{pod=~\"workload-.*\"}[10s])*100&start=${START_TIME}&end=${END_TIME}&step=20s" > "$OUTPUT_DIR/memory_${metric}_${TIMESTAMP}.json"
done

# CPU PSI
for metric in stalled waiting; do
    echo "  • node_pressure_cpu_${metric}_seconds_total"
    curl -s "http://localhost:9090/api/v1/query_range?query=rate(node_pressure_cpu_${metric}_seconds_total{pod=~\"workload-.*\"}[10s])*100&start=${START_TIME}&end=${END_TIME}&step=20s" > "$OUTPUT_DIR/cpu_${metric}_${TIMESTAMP}.json"
done

# I/O PSI
for metric in stalled waiting; do
    echo "  • node_pressure_io_${metric}_seconds_total"
    curl -s "http://localhost:9090/api/v1/query_range?query=rate(node_pressure_io_${metric}_seconds_total{pod=~\"workload-.*\"}[10s])*100&start=${START_TIME}&end=${END_TIME}&step=20s" > "$OUTPUT_DIR/io_${metric}_${TIMESTAMP}.json"
done

echo ""
echo "✅ Raw data collected"
echo ""

# Convert to CSV format matching training data
echo "Converting to CSV format (matching training data)..."

python3 << 'EOFPY'
import json
import csv
import sys
from pathlib import Path
from datetime import datetime

output_dir = Path("workload_data")
timestamp = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y%m%d_%H%M%S")

# Load all metrics
metrics_data = {}

for metric_type in ['memory', 'cpu', 'io']:
    for variant in ['stalled', 'waiting']:
        filename = output_dir / f"{metric_type}_{variant}_{timestamp}.json"
        if filename.exists():
            with open(filename) as f:
                data = json.load(f)
                results = data.get('data', {}).get('result', [])
                for r in results:
                    pod = r['metric']['pod']
                    values = r['values']
                    
                    if pod not in metrics_data:
                        metrics_data[pod] = {}
                    
                    key = f'psi_{metric_type}_{variant}'
                    metrics_data[pod][key] = values

# Create CSV
csv_filename = output_dir / f"workload_psi_{timestamp}.csv"

with open(csv_filename, 'w', newline='') as csvfile:
    fieldnames = [
        'timestamp',
        'pod',
        'psi_memory_full_avg10',  # stalled = full
        'psi_memory_some_avg10',  # waiting = some
        'psi_cpu_full_avg10',
        'psi_cpu_some_avg10',
        'psi_io_full_avg10',
        'psi_io_some_avg10'
    ]
    
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()
    
    # Combine all pod data
    all_timestamps = set()
    for pod_data in metrics_data.values():
        for metric_values in pod_data.values():
            for ts, val in metric_values:
                all_timestamps.add(ts)
    
    # Write rows
    for pod, pod_data in sorted(metrics_data.items()):
        # Get timestamps from first available metric
        if not pod_data:
            continue
        
        first_metric = list(pod_data.values())[0]
        
        for ts, _ in first_metric:
            row = {
                'timestamp': datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S'),
                'pod': pod
            }
            
            # Map metrics to CSV columns
            mapping = {
                'psi_memory_stalled': 'psi_memory_full_avg10',
                'psi_memory_waiting': 'psi_memory_some_avg10',
                'psi_cpu_stalled': 'psi_cpu_full_avg10',
                'psi_cpu_waiting': 'psi_cpu_some_avg10',
                'psi_io_stalled': 'psi_io_full_avg10',
                'psi_io_waiting': 'psi_io_some_avg10'
            }
            
            for metric_key, csv_col in mapping.items():
                if metric_key in pod_data:
                    # Find value for this timestamp
                    for metric_ts, metric_val in pod_data[metric_key]:
                        if metric_ts == ts:
                            row[csv_col] = float(metric_val)
                            break
                else:
                    row[csv_col] = 0.0
            
            writer.writerow(row)

print(f"✅ CSV created: {csv_filename}")
EOFPY $TIMESTAMP

echo ""

# Analyze collected data
echo "============================================================"
echo "DATA ANALYSIS"
echo "============================================================"
echo ""

python3 << 'EOFPY'
import json
import statistics
from pathlib import Path
from datetime import datetime

output_dir = Path("workload_data")
timestamp = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y%m%d_%H%M%S")

# Analyze memory PSI (stalled = full)
filename = output_dir / f"memory_stalled_{timestamp}.json"
if filename.exists():
    with open(filename) as f:
        data = json.load(f)
        results = data.get('data', {}).get('result', [])
        
        print("Memory PSI (Full) Analysis:")
        all_values = []
        spike_count = 0
        total_samples = 0
        
        for r in results:
            pod = r['metric']['pod']
            values = [float(v[1]) for v in r['values']]
            all_values.extend(values)
            total_samples += len(values)
            pod_spikes = sum(1 for v in values if v > 1.5)
            spike_count += pod_spikes
            
            if values:
                print(f"  {pod}:")
                print(f"    Mean: {statistics.mean(values):.4f}%")
                print(f"    Max:  {max(values):.4f}%")
                print(f"    Spikes (>1.5%): {pod_spikes} / {len(values)} ({pod_spikes/len(values)*100:.1f}%)")
        
        if all_values:
            spike_density = (spike_count / total_samples) * 100
            print(f"  Overall:")
            print(f"    Mean: {statistics.mean(all_values):.4f}%")
            print(f"    Max:  {max(all_values):.4f}%")
            print(f"    Spike density: {spike_density:.2f}% (target: ~16%)")
            
            if spike_density >= 14 and spike_density <= 20:
                print(f"    Status: ✅ GOOD (within target range)")
            elif spike_density < 14:
                print(f"    Status: ⚠ LOW (increase workload intensity)")
            else:
                print(f"    Status: ⚠ HIGH (decrease workload intensity)")
else:
    print("⚠ No memory PSI data found")
EOFPY $TIMESTAMP

echo ""
echo "============================================================"
echo "COLLECTION COMPLETE"
echo "============================================================"
echo ""
echo "Files saved to: $OUTPUT_DIR/"
echo ""
ls -lh "$OUTPUT_DIR/"*${TIMESTAMP}* 2>/dev/null || echo "No files found"
echo ""
echo "CSV file for model evaluation:"
echo "  • workload_data/workload_psi_${TIMESTAMP}.csv"
echo ""
echo "Next steps:"
echo "  1. Review spike density (should be ~16%)"
echo "  2. If too low, increase workload intensity and re-collect"
echo "  3. If good, proceed to Phase 5 for model evaluation"
echo ""
