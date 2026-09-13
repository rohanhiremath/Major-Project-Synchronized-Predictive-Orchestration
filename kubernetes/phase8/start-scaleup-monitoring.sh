#!/bin/bash

LOG_DIR="/home/kesavan-p/Documents/major project/implementation/Major-Project-Synchronized-Predictive-Orchestration/kubernetes/phase8/24hr-logs-scaleup"
mkdir -p "$LOG_DIR"

START_TIME=$(date '+%Y-%m-%d %H:%M:%S')
echo "12-Hour Scale-Up Test Started: $START_TIME"

# Record start state
echo "=== START: $START_TIME ===" > "$LOG_DIR/experiment-start.log"
kubectl get hpa workload-reactive-hpa -n default >> "$LOG_DIR/experiment-start.log"
kubectl get statefulset workload-app -n default >> "$LOG_DIR/experiment-start.log"

# Monitor HPA status (every 60s)
(while true; do
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') ===" >> "$LOG_DIR/hpa-status.log"
  kubectl get hpa workload-reactive-hpa -n default >> "$LOG_DIR/hpa-status.log" 2>&1
  kubectl get statefulset workload-app -n default >> "$LOG_DIR/hpa-status.log" 2>&1
  kubectl get pods -n default -l app=workload >> "$LOG_DIR/hpa-status.log" 2>&1
  sleep 60
done) &
HPA_PID=$!
echo $HPA_PID > "$LOG_DIR/hpa-monitor.pid"

# Monitor events (every 60s)
(while true; do
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') ===" >> "$LOG_DIR/hpa-events.log"
  kubectl get events -n default --sort-by='.lastTimestamp' | grep -E "HPA|Scaled|workload" | tail -20 >> "$LOG_DIR/hpa-events.log" 2>&1
  sleep 60
done) &
EVENT_PID=$!
echo $EVENT_PID > "$LOG_DIR/event-monitor.pid"

# Monitor PSI (every 30s)
(while true; do
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') ===" >> "$LOG_DIR/psi-metrics.log"
  kubectl get --raw "/apis/custom.metrics.k8s.io/v1beta1/namespaces/default/pods/*/node_pressure_memory_waiting" >> "$LOG_DIR/psi-metrics.log" 2>&1
  sleep 30
done) &
PSI_PID=$!
echo $PSI_PID > "$LOG_DIR/psi-monitor.pid"

# Monitor stress test (every 5 min)
(while true; do
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') ===" >> "$LOG_DIR/stress-test.log"
  kubectl get cronjob safe-psi-generator -n default >> "$LOG_DIR/stress-test.log" 2>&1
  kubectl get pods -l app=safe-psi-test -n default >> "$LOG_DIR/stress-test.log" 2>&1
  sleep 300
done) &
STRESS_PID=$!
echo $STRESS_PID > "$LOG_DIR/stress-monitor.pid"

echo ""
echo "✅ Monitoring started!"
echo ""
echo "PIDs:"
echo "  HPA Monitor: $HPA_PID"
echo "  Event Monitor: $EVENT_PID"
echo "  PSI Monitor: $PSI_PID"
echo "  Stress Monitor: $STRESS_PID"
echo ""
echo "Logs: $LOG_DIR"
echo ""
echo "Will run until: $(date -d '+12 hours' '+%Y-%m-%d %H:%M:%S')"
echo ""
