#!/bin/bash
#
# Stop 24-Hour Monitoring
#

LOG_DIR="/home/kesavan-p/Documents/major project/implementation/Major-Project-Synchronized-Predictive-Orchestration/kubernetes/phase8/24hr-logs"

echo "Stopping 24-hour monitoring..."

# Kill monitoring processes
if [ -f "$LOG_DIR/hpa-monitor.pid" ]; then
  kill $(cat "$LOG_DIR/hpa-monitor.pid") 2>/dev/null && echo "✅ Stopped HPA monitor"
fi

if [ -f "$LOG_DIR/event-monitor.pid" ]; then
  kill $(cat "$LOG_DIR/event-monitor.pid") 2>/dev/null && echo "✅ Stopped event monitor"
fi

if [ -f "$LOG_DIR/psi-monitor.pid" ]; then
  kill $(cat "$LOG_DIR/psi-monitor.pid") 2>/dev/null && echo "✅ Stopped PSI monitor"
fi

if [ -f "$LOG_DIR/spike-monitor.pid" ]; then
  kill $(cat "$LOG_DIR/spike-monitor.pid") 2>/dev/null && echo "✅ Stopped spike monitor"
fi

# Create end marker
END_TIME=$(date '+%Y-%m-%d %H:%M:%S')
echo "=== 24-HOUR MONITORING END ===" > "$LOG_DIR/experiment-end.log"
echo "End Time: $END_TIME" >> "$LOG_DIR/experiment-end.log"
echo "" >> "$LOG_DIR/experiment-end.log"

# Final state
kubectl get hpa workload-reactive-hpa -n default -o wide >> "$LOG_DIR/experiment-end.log"
kubectl get statefulset workload-app -n default -o wide >> "$LOG_DIR/experiment-end.log"
kubectl get pods -n default -l app=workload -o wide >> "$LOG_DIR/experiment-end.log"
kubectl get jobs -l job-name=psi-spike-generator >> "$LOG_DIR/experiment-end.log"

echo ""
echo "✅ Monitoring stopped"
echo "End Time: $END_TIME"
echo ""
echo "Logs saved in: $LOG_DIR"
echo ""
echo "Next steps:"
echo "  1. Analyze logs: wc -l $LOG_DIR/*.log"
echo "  2. Count spike events: grep 'spike-generator' $LOG_DIR/spike-generator.log | wc -l"
echo "  3. Export Prometheus data"
echo "  4. Calculate metrics"
