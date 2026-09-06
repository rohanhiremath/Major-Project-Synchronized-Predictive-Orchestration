#!/bin/bash
#
# 24-Hour Reactive HPA Monitoring
# Started: September 6, 2026 @ 6:35 PM IST
# End: September 7, 2026 @ 6:35 PM IST
#

LOG_DIR="/home/kesavan-p/Documents/major project/implementation/Major-Project-Synchronized-Predictive-Orchestration/kubernetes/phase8/24hr-logs"
mkdir -p "$LOG_DIR"

START_TIME=$(date '+%Y-%m-%d %H:%M:%S')
echo "24-Hour Monitoring Started: $START_TIME"
echo "Log directory: $LOG_DIR"

# Create start marker
echo "=== 24-HOUR MONITORING START ===" > "$LOG_DIR/experiment-start.log"
echo "Start Time: $START_TIME" >> "$LOG_DIR/experiment-start.log"
echo "HPA: workload-reactive-hpa" >> "$LOG_DIR/experiment-start.log"
echo "Namespace: default" >> "$LOG_DIR/experiment-start.log"
echo "" >> "$LOG_DIR/experiment-start.log"

# Initial state
kubectl get hpa workload-reactive-hpa -n default -o wide >> "$LOG_DIR/experiment-start.log"
kubectl get statefulset workload-app -n default -o wide >> "$LOG_DIR/experiment-start.log"

echo "Starting background monitoring..."

# Monitor HPA status every minute
(while true; do
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') ===" >> "$LOG_DIR/hpa-status.log"
  kubectl get hpa workload-reactive-hpa -n default -o wide >> "$LOG_DIR/hpa-status.log" 2>&1
  kubectl get statefulset workload-app -n default -o wide >> "$LOG_DIR/hpa-status.log" 2>&1
  kubectl get pods -n default -l app=workload -o wide >> "$LOG_DIR/hpa-status.log" 2>&1
  echo "" >> "$LOG_DIR/hpa-status.log"
  sleep 60
done) &
HPA_MON_PID=$!
echo $HPA_MON_PID > "$LOG_DIR/hpa-monitor.pid"

# Monitor HPA events every minute
(while true; do
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') ===" >> "$LOG_DIR/hpa-events.log"
  kubectl get events -n default --sort-by='.lastTimestamp' | grep -E "HPA|Scaled|workload" | tail -10 >> "$LOG_DIR/hpa-events.log" 2>&1
  echo "" >> "$LOG_DIR/hpa-events.log"
  sleep 60
done) &
EVENT_MON_PID=$!
echo $EVENT_MON_PID > "$LOG_DIR/event-monitor.pid"

# Monitor PSI metrics every 30 seconds
(while true; do
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') ===" >> "$LOG_DIR/psi-metrics.log"
  kubectl get --raw "/apis/custom.metrics.k8s.io/v1beta1/namespaces/default/pods/*/node_pressure_memory_waiting" 2>> "$LOG_DIR/psi-metrics.log" | python3 -m json.tool >> "$LOG_DIR/psi-metrics.log" 2>&1 || echo "Metric query failed" >> "$LOG_DIR/psi-metrics.log"
  echo "" >> "$LOG_DIR/psi-metrics.log"
  sleep 30
done) &
PSI_MON_PID=$!
echo $PSI_MON_PID > "$LOG_DIR/psi-monitor.pid"

# Check spike generator
(while true; do
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') ===" >> "$LOG_DIR/spike-generator.log"
  kubectl get cronjob psi-spike-generator -o wide >> "$LOG_DIR/spike-generator.log" 2>&1
  kubectl get jobs -l job-name=psi-spike-generator --sort-by='.status.startTime' | tail -5 >> "$LOG_DIR/spike-generator.log" 2>&1
  echo "" >> "$LOG_DIR/spike-generator.log"
  sleep 300  # Every 5 minutes
done) &
SPIKE_MON_PID=$!
echo $SPIKE_MON_PID > "$LOG_DIR/spike-monitor.pid"

echo ""
echo "✅ Monitoring started!"
echo ""
echo "PIDs:"
echo "  HPA Monitor: $HPA_MON_PID"
echo "  Event Monitor: $EVENT_MON_PID"
echo "  PSI Monitor: $PSI_MON_PID"
echo "  Spike Monitor: $SPIKE_MON_PID"
echo ""
echo "Logs:"
echo "  HPA Status: $LOG_DIR/hpa-status.log"
echo "  HPA Events: $LOG_DIR/hpa-events.log"
echo "  PSI Metrics: $LOG_DIR/psi-metrics.log"
echo "  Spike Generator: $LOG_DIR/spike-generator.log"
echo ""
echo "To stop monitoring (after 24 hours):"
echo "  kill $HPA_MON_PID $EVENT_MON_PID $PSI_MON_PID $SPIKE_MON_PID"
echo "  Or run: ./stop-24hr-monitoring.sh"
echo ""
echo "Experiment will run until: $(date -d '+24 hours' '+%Y-%m-%d %H:%M:%S')"
