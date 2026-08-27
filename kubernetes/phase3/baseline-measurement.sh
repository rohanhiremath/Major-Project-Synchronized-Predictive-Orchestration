#!/bin/bash
# Phase 3: Baseline PSI Measurement
# Collects idle PSI values for comparison with training data

DURATION=${1:-600}  # Default 10 minutes
OUTPUT_DIR="baseline_data"

set -e

echo "============================================================"
echo "PHASE 3: BASELINE PSI MEASUREMENT"
echo "Duration: ${DURATION} seconds ($((DURATION/60)) minutes)"
echo "============================================================"
echo ""

# Create output directory
mkdir -p "$OUTPUT_DIR"

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

echo "Collecting baseline PSI metrics..."
echo ""

START_TIME=$(date -u +%s)
END_TIME=$((START_TIME + DURATION))

# Query baseline PSI rates
echo "Querying PSI rates over ${DURATION}s window..."

curl -s "http://localhost:9090/api/v1/query_range?query=rate(node_pressure_memory_stalled_seconds_total{pod=~\"workload-.*\"}[1m])*100&start=${START_TIME}&end=${END_TIME}&step=20s" | python3 << 'EOF' > "$OUTPUT_DIR/memory_psi_baseline.json"
import json, sys
data = json.load(sys.stdin)
json.dump(data, sys.stdout, indent=2)
EOF

curl -s "http://localhost:9090/api/v1/query_range?query=rate(node_pressure_cpu_stalled_seconds_total{pod=~\"workload-.*\"}[1m])*100&start=${START_TIME}&end=${END_TIME}&step=20s" | python3 << 'EOF' > "$OUTPUT_DIR/cpu_psi_baseline.json"
import json, sys
data = json.load(sys.stdin)
json.dump(data, sys.stdout, indent=2)
EOF

curl -s "http://localhost:9090/api/v1/query_range?query=rate(node_pressure_io_stalled_seconds_total{pod=~\"workload-.*\"}[1m])*100&start=${START_TIME}&end=${END_TIME}&step=20s" | python3 << 'EOF' > "$OUTPUT_DIR/io_psi_baseline.json"
import json, sys
data = json.load(sys.stdin)
json.dump(data, sys.stdout, indent=2)
EOF

echo "✅ Data collected and saved to $OUTPUT_DIR/"
echo ""

# Analyze baseline
echo "============================================================"
echo "BASELINE ANALYSIS"
echo "============================================================"
echo ""

python3 << 'EOF'
import json
import statistics

def analyze_metric(filename, metric_name):
    with open(filename, 'r') as f:
        data = json.load(f)
    
    results = data.get('data', {}).get('result', [])
    
    print(f"{metric_name} PSI:")
    all_values = []
    
    for r in results:
        pod = r['metric']['pod']
        values = [float(v[1]) for v in r['values']]
        all_values.extend(values)
        
        if values:
            avg = statistics.mean(values)
            std = statistics.stdev(values) if len(values) > 1 else 0
            max_val = max(values)
            min_val = min(values)
            
            print(f"  {pod}:")
            print(f"    Mean: {avg:.4f}%")
            print(f"    Std:  {std:.4f}%")
            print(f"    Min:  {min_val:.4f}%")
            print(f"    Max:  {max_val:.4f}%")
    
    if all_values:
        overall_mean = statistics.mean(all_values)
        overall_std = statistics.stdev(all_values) if len(all_values) > 1 else 0
        
        print(f"  Overall:")
        print(f"    Mean: {overall_mean:.4f}% ± {overall_std:.4f}%")
        print(f"    Samples: {len(all_values)}")
        
        # Check against thresholds
        if overall_mean < 0.5:
            print(f"    Status: ✅ PASS (< 0.5%)")
        else:
            print(f"    Status: ⚠ WARNING (> 0.5%)")
    print()

analyze_metric('baseline_data/memory_psi_baseline.json', 'Memory')
analyze_metric('baseline_data/cpu_psi_baseline.json', 'CPU')
analyze_metric('baseline_data/io_psi_baseline.json', 'I/O')
EOF

echo "============================================================"
echo "COMPARISON WITH TRAINING DATA"
echo "============================================================"
echo ""

echo "Training data idle characteristics:"
echo "  • Dataset: ptcs_training_data_full_psi.csv"
echo "  • Spike threshold: 1.5%"
echo "  • Spike density: 12.78% (training), 16.51% (test)"
echo "  • Expected idle PSI: 0.0% - 0.5%"
echo ""

echo "Baseline measurement complete!"
echo "Files saved to: $OUTPUT_DIR/"
echo ""
echo "Next steps:"
echo "  1. Review baseline statistics above"
echo "  2. Compare with training data: python3 compare-baseline.py"
echo "  3. If baseline looks good, proceed to Phase 4"
echo ""
EOF

chmod +x "$OUTPUT_DIR/baseline-measurement.sh" 2>/dev/null || true
