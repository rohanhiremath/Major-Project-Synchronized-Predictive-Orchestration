#!/bin/bash
# Phase 3: Run All Validation Tasks

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo "PHASE 3: COMPREHENSIVE VALIDATION"
echo "============================================================"
echo ""

echo "Running validation tasks..."
echo ""

# Task 1-2: Metrics validation
echo "┌────────────────────────────────────────────────────────────┐"
echo "│ TASK 1-2: Metrics Validation                              │"
echo "└────────────────────────────────────────────────────────────┘"
echo ""
./validate-metrics.sh

echo ""
echo "Press Enter to continue to baseline measurement..."
read

# Task 3: Baseline measurement
echo "┌────────────────────────────────────────────────────────────┐"
echo "│ TASK 3: Baseline Measurement (10 minutes)                 │"
echo "└────────────────────────────────────────────────────────────┘"
echo ""
./baseline-measurement.sh 600

echo ""
echo "============================================================"
echo "PHASE 3 VALIDATION: COMPLETE"
echo "============================================================"
echo ""
echo "Summary:"
echo "  ✅ Metrics validation completed"
echo "  ✅ Baseline PSI measurements collected"
echo ""
echo "Next steps:"
echo "  1. Review baseline data in baseline_data/"
echo "  2. Create Grafana dashboard: ./create-dashboard.sh"
echo "  3. Proceed to Phase 4: Synthetic workload generation"
echo ""
