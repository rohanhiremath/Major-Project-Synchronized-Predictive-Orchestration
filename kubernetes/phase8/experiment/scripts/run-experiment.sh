#!/bin/bash
#
# Phase 9 Experiment Runner
# Runs comparative A/B test: Reactive HPA vs Predictive HPA
#

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
EXPERIMENT_DURATION_HOURS=${1:-24}
EXPERIMENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$EXPERIMENT_DIR/logs"
RESULTS_DIR="$EXPERIMENT_DIR/results"
WORKLOAD_DIR="$EXPERIMENT_DIR/workloads"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
EXPERIMENT_LOG="$LOG_DIR/experiment_$TIMESTAMP.log"

# Create log directories
mkdir -p "$LOG_DIR" "$RESULTS_DIR"

echo "╔═══════════════════════════════════════════════════════════════════════════════╗" | tee -a "$EXPERIMENT_LOG"
echo "║                                                                               ║" | tee -a "$EXPERIMENT_LOG"
echo "║                     PHASE 9: COMPARATIVE EXPERIMENT                           ║" | tee -a "$EXPERIMENT_LOG"
echo "║                   Reactive HPA vs Predictive HPA                              ║" | tee -a "$EXPERIMENT_LOG"
echo "║                                                                               ║" | tee -a "$EXPERIMENT_LOG"
echo "╚═══════════════════════════════════════════════════════════════════════════════╝" | tee -a "$EXPERIMENT_LOG"
echo "" | tee -a "$EXPERIMENT_LOG"

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$EXPERIMENT_LOG"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1" | tee -a "$EXPERIMENT_LOG"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" | tee -a "$EXPERIMENT_LOG"
}

info() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] INFO:${NC} $1" | tee -a "$EXPERIMENT_LOG"
}

# Step 1: Prerequisites Check
log "Step 1: Checking prerequisites..."

if ! kubectl cluster-info &>/dev/null; then
    error "Kubernetes cluster not accessible"
    exit 1
fi
log "✅ Kubernetes cluster accessible"

if ! kubectl get apiservice v1beta1.custom.metrics.k8s.io | grep -q "True"; then
    error "Custom Metrics API not available"
    exit 1
fi
log "✅ Custom Metrics API available"

if ! kubectl get pods -n monitoring -l app.kubernetes.io/name=prometheus-adapter | grep -q "Running"; then
    error "Prometheus Adapter not running"
    exit 1
fi
log "✅ Prometheus Adapter running"

# Step 2: Clean up any existing experiment
log "Step 2: Cleaning up existing experiment resources..."

kubectl delete namespace experiment-reactive experiment-predictive --ignore-not-found=true 2>/dev/null || true
sleep 5
log "✅ Previous experiment cleaned up"

# Step 3: Deploy Reactive Workload
log "Step 3: Deploying Reactive Workload (Baseline)..."

if [ ! -f "$WORKLOAD_DIR/workload-reactive.yaml" ]; then
    error "Reactive workload manifest not found"
    exit 1
fi

kubectl apply -f "$WORKLOAD_DIR/workload-reactive.yaml"
log "✅ Reactive workload deployed"

# Wait for reactive pods
log "Waiting for reactive workload pods..."
kubectl wait --for=condition=ready pod -l app=workload,hpa-type=reactive -n experiment-reactive --timeout=300s
log "✅ Reactive workload pods ready"

# Step 4: Deploy Predictive Workload
log "Step 4: Deploying Predictive Workload..."

if [ ! -f "$WORKLOAD_DIR/workload-predictive.yaml" ]; then
    error "Predictive workload manifest not found"
    exit 1
fi

kubectl apply -f "$WORKLOAD_DIR/workload-predictive.yaml"
log "✅ Predictive workload deployed"

# Wait for predictive pods
log "Waiting for predictive workload pods..."
kubectl wait --for=condition=ready pod -l app=workload,hpa-type=predictive -n experiment-predictive --timeout=300s
log "✅ Predictive workload pods ready"

# Step 5: Deploy Prediction Service
log "Step 5: Deploying Prediction Service..."

if [ ! -f "$WORKLOAD_DIR/prediction-service.yaml" ]; then
    warn "Prediction service manifest not found, skipping"
else
    kubectl apply -f "$WORKLOAD_DIR/prediction-service.yaml"
    log "✅ Prediction service deployed"
    
    # Wait for prediction service
    log "Waiting for prediction service..."
    kubectl wait --for=condition=ready pod -l app=prediction-service -n experiment-predictive --timeout=300s || warn "Prediction service not ready yet"
fi

# Step 6: Verify HPAs
log "Step 6: Verifying HPAs..."

sleep 10

info "Reactive HPA:"
kubectl get hpa -n experiment-reactive -o wide | tee -a "$EXPERIMENT_LOG"

info "Predictive HPA:"
kubectl get hpa -n experiment-predictive -o wide | tee -a "$EXPERIMENT_LOG"

# Step 7: Start Monitoring
log "Step 7: Starting monitoring..."

# Create monitoring script
cat > "$LOG_DIR/monitor_$TIMESTAMP.sh" <<'EOF'
#!/bin/bash
INTERVAL=${1:-60}
LOG_FILE="$2"

while true; do
    echo "=== $(date +'%Y-%m-%d %H:%M:%S') ===" >> "$LOG_FILE"
    
    echo "Reactive HPA:" >> "$LOG_FILE"
    kubectl get hpa -n experiment-reactive -o wide >> "$LOG_FILE" 2>&1
    
    echo "Predictive HPA:" >> "$LOG_FILE"
    kubectl get hpa -n experiment-predictive -o wide >> "$LOG_FILE" 2>&1
    
    echo "Reactive Pods:" >> "$LOG_FILE"
    kubectl get pods -n experiment-reactive -l app=workload >> "$LOG_FILE" 2>&1
    
    echo "Predictive Pods:" >> "$LOG_FILE"
    kubectl get pods -n experiment-predictive -l app=workload >> "$LOG_FILE" 2>&1
    
    echo "" >> "$LOG_FILE"
    sleep $INTERVAL
done
EOF

chmod +x "$LOG_DIR/monitor_$TIMESTAMP.sh"

# Start background monitoring
nohup "$LOG_DIR/monitor_$TIMESTAMP.sh" 60 "$LOG_DIR/monitoring_$TIMESTAMP.log" > /dev/null 2>&1 &
MONITOR_PID=$!
echo $MONITOR_PID > "$LOG_DIR/monitor.pid"

log "✅ Monitoring started (PID: $MONITOR_PID)"

# Step 8: Summary
echo "" | tee -a "$EXPERIMENT_LOG"
echo "╔═══════════════════════════════════════════════════════════════════════════════╗" | tee -a "$EXPERIMENT_LOG"
echo "║                                                                               ║" | tee -a "$EXPERIMENT_LOG"
echo "║                        EXPERIMENT STARTED                                     ║" | tee -a "$EXPERIMENT_LOG"
echo "║                                                                               ║" | tee -a "$EXPERIMENT_LOG"
echo "╚═══════════════════════════════════════════════════════════════════════════════╝" | tee -a "$EXPERIMENT_LOG"
echo "" | tee -a "$EXPERIMENT_LOG"

info "Experiment Details:" | tee -a "$EXPERIMENT_LOG"
echo "  Duration: $EXPERIMENT_DURATION_HOURS hours" | tee -a "$EXPERIMENT_LOG"
echo "  Start Time: $(date)" | tee -a "$EXPERIMENT_LOG"
echo "  End Time: $(date -d "+$EXPERIMENT_DURATION_HOURS hours")" | tee -a "$EXPERIMENT_LOG"
echo "  Log File: $EXPERIMENT_LOG" | tee -a "$EXPERIMENT_LOG"
echo "  Monitoring Log: $LOG_DIR/monitoring_$TIMESTAMP.log" | tee -a "$EXPERIMENT_LOG"
echo "  Monitor PID: $MONITOR_PID" | tee -a "$EXPERIMENT_LOG"
echo "" | tee -a "$EXPERIMENT_LOG"

info "Namespaces:" | tee -a "$EXPERIMENT_LOG"
echo "  Reactive: experiment-reactive" | tee -a "$EXPERIMENT_LOG"
echo "  Predictive: experiment-predictive" | tee -a "$EXPERIMENT_LOG"
echo "" | tee -a "$EXPERIMENT_LOG"

info "Monitoring Commands:" | tee -a "$EXPERIMENT_LOG"
echo "  Watch HPAs: watch -n 10 'kubectl get hpa -n experiment-reactive; kubectl get hpa -n experiment-predictive'" | tee -a "$EXPERIMENT_LOG"
echo "  Watch Pods: watch -n 10 'kubectl get pods -n experiment-reactive; kubectl get pods -n experiment-predictive'" | tee -a "$EXPERIMENT_LOG"
echo "  View Logs: tail -f $LOG_DIR/monitoring_$TIMESTAMP.log" | tee -a "$EXPERIMENT_LOG"
echo "  Stop Monitor: kill $MONITOR_PID" | tee -a "$EXPERIMENT_LOG"
echo "" | tee -a "$EXPERIMENT_LOG"

info "To stop experiment:" | tee -a "$EXPERIMENT_LOG"
echo "  ./stop-experiment.sh" | tee -a "$EXPERIMENT_LOG"
echo "" | tee -a "$EXPERIMENT_LOG"

log "Experiment is now running. Monitor progress with the commands above."
