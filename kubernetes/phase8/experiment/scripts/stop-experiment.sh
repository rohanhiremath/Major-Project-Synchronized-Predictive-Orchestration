#!/bin/bash
#
# Stop Phase 9 Experiment
#

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

EXPERIMENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$EXPERIMENT_DIR/logs"

echo -e "${GREEN}Stopping Phase 9 Experiment...${NC}"
echo ""

# Stop monitoring
if [ -f "$LOG_DIR/monitor.pid" ]; then
    MONITOR_PID=$(cat "$LOG_DIR/monitor.pid")
    if kill -0 $MONITOR_PID 2>/dev/null; then
        echo "Stopping monitor (PID: $MONITOR_PID)..."
        kill $MONITOR_PID
        rm "$LOG_DIR/monitor.pid"
        echo -e "${GREEN}✅ Monitor stopped${NC}"
    else
        echo -e "${YELLOW}⚠️  Monitor not running${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  Monitor PID file not found${NC}"
fi

# Export final state
echo ""
echo "Exporting final state..."
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FINAL_STATE="$LOG_DIR/final_state_$TIMESTAMP.log"

{
    echo "=== FINAL STATE: $(date) ==="
    echo ""
    echo "Reactive HPA:"
    kubectl get hpa -n experiment-reactive -o wide
    echo ""
    echo "Predictive HPA:"
    kubectl get hpa -n experiment-predictive -o wide
    echo ""
    echo "Reactive Pods:"
    kubectl get pods -n experiment-reactive -l app=workload -o wide
    echo ""
    echo "Predictive Pods:"
    kubectl get pods -n experiment-predictive -l app=workload -o wide
    echo ""
    echo "HPA Events (Reactive):"
    kubectl get events -n experiment-reactive --sort-by='.lastTimestamp' | grep HPA | tail -20
    echo ""
    echo "HPA Events (Predictive):"
    kubectl get events -n experiment-predictive --sort-by='.lastTimestamp' | grep HPA | tail -20
} > "$FINAL_STATE"

echo -e "${GREEN}✅ Final state exported to: $FINAL_STATE${NC}"

# Ask before cleanup
echo ""
read -p "Delete experiment namespaces? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Deleting experiment namespaces..."
    kubectl delete namespace experiment-reactive experiment-predictive --ignore-not-found=true
    echo -e "${GREEN}✅ Experiment namespaces deleted${NC}"
else
    echo "Keeping experiment namespaces for analysis"
fi

echo ""
echo -e "${GREEN}╔═══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                                                               ║${NC}"
echo -e "${GREEN}║                  EXPERIMENT STOPPED                           ║${NC}"
echo -e "${GREEN}║                                                               ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "Logs saved to: $LOG_DIR"
echo "Final state: $FINAL_STATE"
echo ""
echo "Next steps:"
echo "  1. Export Prometheus data"
echo "  2. Analyze results"
echo "  3. Generate comparison table"
