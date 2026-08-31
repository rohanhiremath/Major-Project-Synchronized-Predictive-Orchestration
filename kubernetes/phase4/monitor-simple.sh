#!/bin/bash
# Phase 4: Simple Monitoring (No Port-forward Required)

echo "============================================================"
echo "PHASE 4: SIMPLE PSI MONITORING"
echo "Press Ctrl+C to stop"
echo "============================================================"
echo ""

while true; do
    clear
    echo "============================================================"
    echo "PHASE 4: PSI MONITORING - $(date '+%H:%M:%S')"
    echo "============================================================"
    echo ""
    
    # Check workload job status
    echo "Workload Jobs:"
    kubectl get jobs -l workload-type --no-headers 2>/dev/null | awk '{printf "  %-30s %s\n", $1, $2}' || echo "  No jobs found"
    echo ""
    
    # Check PSI metrics from first pod
    echo "PSI Metrics (from workload-app-0):"
    echo ""
    
    POD_NAME="workload-app-0"
    
    if kubectl get pod $POD_NAME > /dev/null 2>&1; then
        # Get all PSI metrics
        METRICS=$(kubectl exec $POD_NAME -c node-exporter -- wget -qO- http://localhost:9100/metrics 2>/dev/null | grep "^node_pressure.*stalled_seconds_total " | grep -v "#")
        
        if [ -n "$METRICS" ]; then
            echo "$METRICS" | while read line; do
                METRIC_NAME=$(echo "$line" | awk '{print $1}')
                VALUE=$(echo "$line" | awk '{print $2}')
                
                # Extract type (memory, cpu, io)
                if [[ $METRIC_NAME == *"memory"* ]]; then
                    TYPE="Memory"
                elif [[ $METRIC_NAME == *"cpu"* ]]; then
                    TYPE="CPU   "
                elif [[ $METRIC_NAME == *"io"* ]]; then
                    TYPE="I/O   "
                fi
                
                printf "  %s PSI: %12.2f seconds (total stalled)\n" "$TYPE" "$VALUE"
            done
        else
            echo "  ⚠ No PSI metrics found"
        fi
    else
        echo "  ⚠ Pod $POD_NAME not found"
    fi
    
    echo ""
    echo "────────────────────────────────────────────────────────────"
    echo ""
    
    # Pod resource usage
    echo "Pod Resource Usage:"
    kubectl top pods -l app=workload 2>/dev/null || echo "  Metrics not available"
    
    echo ""
    echo "Tip: For real-time rate() queries, use Prometheus UI:"
    echo "  kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090"
    echo "  Then open: http://localhost:9090"
    echo ""
    echo "Refreshing in 10 seconds... (Ctrl+C to stop)"
    
    sleep 10
done
