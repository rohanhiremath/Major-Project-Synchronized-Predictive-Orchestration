#!/bin/bash
# Phase 3: Create Grafana Dashboard

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DASHBOARD_FILE="$SCRIPT_DIR/grafana-dashboard.json"

echo "============================================================"
echo "PHASE 3: GRAFANA DASHBOARD DEPLOYMENT"
echo "============================================================"
echo ""

# Get Grafana credentials
echo "Grafana credentials:"
echo "  Username: admin"
echo "  Password: prom-operator"
echo ""

# Start port-forward
echo "Starting Grafana port-forward..."
kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3000:80 > /dev/null 2>&1 &
PF_PID=$!
sleep 3

cleanup() {
    echo ""
    echo "Cleaning up port-forward..."
    kill $PF_PID 2>/dev/null || true
}
trap cleanup EXIT

echo "Grafana is now accessible at: http://localhost:3000"
echo ""
echo "Dashboard options:"
echo ""
echo "Option 1: Import via UI (Recommended)"
echo "  1. Open http://localhost:3000"
echo "  2. Login with admin / prom-operator"
echo "  3. Click '+' → Import"
echo "  4. Upload file: $DASHBOARD_FILE"
echo "  5. Select Prometheus datasource"
echo "  6. Click Import"
echo ""
echo "Option 2: Import via API"
echo "  (Requires API key or direct auth)"
echo ""

read -p "Press Enter to continue (will open browser if available)..."

# Try to open browser
if command -v xdg-open &> /dev/null; then
    xdg-open http://localhost:3000 &
elif command -v open &> /dev/null; then
    open http://localhost:3000 &
fi

echo ""
echo "Dashboard JSON location: $DASHBOARD_FILE"
echo ""
echo "After importing, you should see 10 panels:"
echo "  1. Memory PSI Full (with thresholds at 1.5% and 5%)"
echo "  2. CPU PSI"
echo "  3. I/O PSI"
echo "  4. PSI Comparison (all types)"
echo "  5. Spike count (last hour)"
echo "  6. Current Memory PSI (stat)"
echo "  7. Active pods count"
echo "  8. Model threshold (1.5%)"
echo "  9. CPU usage (app container)"
echo "  10. Memory usage (app container)"
echo ""
echo "Press Ctrl+C to stop port-forward when done."
echo ""

# Keep port-forward running
wait $PF_PID
