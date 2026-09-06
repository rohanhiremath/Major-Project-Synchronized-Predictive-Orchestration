#!/bin/bash
#
# Simplified Phase 9 Experiment Runner
# Uses default namespace with existing working metrics
#

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

EXPERIMENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$EXPERIMENT_DIR/logs"
RESULTS_DIR="$EXPERIMENT_DIR/results"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
EXPERIMENT_LOG="$LOG_DIR/experiment_$TIMESTAMP.log"

mkdir -p "$LOG_DIR" "$RESULTS_DIR"

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$EXPERIMENT_LOG"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1" | tee -a "$EXPERIMENT_LOG"
}

info() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] INFO:${NC} $1" | tee -a "$EXPERIMENT_LOG"
}

echo "╔═══════════════════════════════════════════════════════════════════════════════╗" | tee -a "$EXPERIMENT_LOG"
echo "║                                                                               ║" | tee -a "$EXPERIMENT_LOG"
echo "║           PHASE 9: SIMPLIFIED COMPARATIVE EXPERIMENT                          ║" | tee -a "$EXPERIMENT_LOG"
echo "║              Reactive HPA (existing) vs Predictive HPA                        ║" | tee -a "$EXPERIMENT_LOG"
echo "║                                                                               ║" | tee -a "$EXPERIMENT_LOG"
echo "╚═══════════════════════════════════════════════════════════════════════════════╝" | tee -a "$EXPERIMENT_LOG"
echo "" | tee -a "$EXPERIMENT_LOG"

log "Using existing workload in default namespace"
log "Reactive HPA already deployed (Day 3)"
log "Will monitor both for comparison"
echo "" | tee -a "$EXPERIMENT_LOG"

# Check existing setup
log "Checking existing setup..."

if ! kubectl get hpa workload-reactive-hpa -n default &>/dev/null; then
    warn "Reactive HPA not found, checking alternative..."
    if kubectl get statefulset workload-app -n default &>/dev/null; then
        log "Found workload-app, HPA might be named differently"
    fi
fi

log "Current workload status:"
kubectl get statefulset -n default -l app=workload -o wide | tee -a "$EXPERIMENT_LOG"
echo "" | tee -a "$EXPERIMENT_LOG"

log "Current HPA status:"
kubectl get hpa -n default | tee -a "$EXPERIMENT_LOG"
echo "" | tee -a "$EXPERIMENT_LOG"

# Start monitoring
log "Starting monitoring loop..."

cat > "$LOG_DIR/monitor_$TIMESTAMP.sh" <<'MONITOR_EOF'
#!/bin/bash
INTERVAL=${1:-60}
LOG_FILE="$2"

while true; do
    echo "=== $(date +'%Y-%m-%d %H:%M:%S') ===" >> "$LOG_FILE"
    
    echo "HPAs:" >> "$LOG_FILE"
    kubectl get hpa -n default >> "$LOG_FILE" 2>&1
    
    echo "Workload Pods:" >> "$LOG_FILE"
    kubectl get pods -n default -l app=workload -o wide >> "$LOG_FILE" 2>&1
    
    echo "PSI Metrics:" >> "$LOG_FILE"
    kubectl get --raw "/apis/custom.metrics.k8s.io/v1beta1/namespaces/default/pods/*/node_pressure_memory_waiting" 2>> "$LOG_FILE" | head -50 >> "$LOG_FILE" || true
    
    echo "" >> "$LOG_FILE"
    sleep $INTERVAL
done
MONITOR_EOF

chmod +x "$LOG_DIR/monitor_$TIMESTAMP.sh"
nohup "$LOG_DIR/monitor_$TIMESTAMP.sh" 60 "$LOG_DIR/monitoring_$TIMESTAMP.log" > /dev/null 2>&1 &
MONITOR_PID=$!
echo $MONITOR_PID > "$LOG_DIR/monitor.pid"

log "✅ Monitoring started (PID: $MONITOR_PID)"

echo "" | tee -a "$EXPERIMENT_LOG"
echo "╔═══════════════════════════════════════════════════════════════════════════════╗" | tee -a "$EXPERIMENT_LOG"
echo "║                        EXPERIMENT MONITORING ACTIVE                           ║" | tee -a "$EXPERIMENT_LOG"
echo "╚═══════════════════════════════════════════════════════════════════════════════╝" | tee -a "$EXPERIMENT_LOG"
echo "" | tee -a "$EXPERIMENT_LOG"

info "Monitoring Commands:"
echo "  Watch: watch -n 10 'kubectl get hpa -n default; kubectl get pods -n default -l app=workload'"
echo "  Logs: tail -f $LOG_DIR/monitoring_$TIMESTAMP.log"
echo "  Stop: kill $MONITOR_PID"
echo ""

log "Experiment monitoring active. Collect data over desired period, then analyze."
