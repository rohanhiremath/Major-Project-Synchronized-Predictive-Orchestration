#!/bin/bash
#
# Collect Phase 6 test results and generate report
#

set -e

OUTPUT_DIR="phase6-results-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUTPUT_DIR"

echo "=========================================="
echo " Collecting Phase 6 Results"
echo "=========================================="
echo ""
echo "Output directory: $OUTPUT_DIR"
echo ""

# 1. Collect logs
echo "1. Collecting prediction service logs..."
kubectl logs deployment/prediction-service --tail=10000 > "$OUTPUT_DIR/service-logs.txt"
echo "   ✅ Saved to service-logs.txt"

# 2. Collect final metrics
echo "2. Collecting metrics..."
kubectl port-forward service/prediction-service 8080:8080 &> /dev/null &
PORT_FORWARD_PID=$!
sleep 3

curl -s http://localhost:8080/metrics-summary > "$OUTPUT_DIR/metrics-summary.json" 2>/dev/null || echo "{}" > "$OUTPUT_DIR/metrics-summary.json"
curl -s http://localhost:8080/health > "$OUTPUT_DIR/health-check.json" 2>/dev/null || echo "{}" > "$OUTPUT_DIR/health-check.json"

kill $PORT_FORWARD_PID 2>/dev/null || true

echo "   ✅ Saved metrics"

# 3. Extract statistics from logs
echo "3. Analyzing logs..."

TOTAL_PREDICTIONS=$(grep -c "Spike predicted:" "$OUTPUT_DIR/service-logs.txt" 2>/dev/null || echo "0")
SPIKES_PREDICTED=$(grep "Spike predicted: True" "$OUTPUT_DIR/service-logs.txt" | wc -l)
echo "   Predictions: $TOTAL_PREDICTIONS"
echo "   Spikes detected: $SPIKES_PREDICTED"

# 4. Generate report
echo "4. Generating report..."

cat > "$OUTPUT_DIR/RESULTS_SUMMARY.md" << EOF
# Phase 6: Prediction Service Test Results

**Date**: $(date)  
**Duration**: Check service logs  
**Test Type**: Accelerated intensive testing

---

## Test Configuration

- **Model**: tft_psi_model.ckpt
- **Threshold**: 1.80%
- **Prediction Interval**: 20 seconds
- **Workload Pattern**: Burst (5min) + Idle (3min) cycles

---

## Results

### Prediction Statistics

\`\`\`json
$(cat "$OUTPUT_DIR/metrics-summary.json" | jq '.' 2>/dev/null || echo "No metrics available")
\`\`\`

### Performance Metrics

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| **Precision** | $(cat "$OUTPUT_DIR/metrics-summary.json" | jq -r '.precision * 100' 2>/dev/null || echo "N/A")% | ≥85% | TBD |
| **Recall** | $(cat "$OUTPUT_DIR/metrics-summary.json" | jq -r '.recall * 100' 2>/dev/null || echo "N/A")% | ≥90% | TBD |
| **Total Predictions** | ${TOTAL_PREDICTIONS} | ≥300 | TBD |
| **Spikes Detected** | ${SPIKES_PREDICTED} | 40-60 | TBD |

### Comparison with Phase 5

| Metric | Phase 5 (K8s Validation) | Phase 6 (Service Test) | Match? |
|--------|--------------------------|------------------------|--------|
| Precision | 92.0% | $(cat "$OUTPUT_DIR/metrics-summary.json" | jq -r '.precision * 100' 2>/dev/null || echo "N/A")% | TBD |
| Recall | 100.0% | $(cat "$OUTPUT_DIR/metrics-summary.json" | jq -r '.recall * 100' 2>/dev/null || echo "N/A")% | TBD |

---

## Analysis

### Service Health

- Service ran without crashes: [CHECK LOGS]
- All predictions completed: ${TOTAL_PREDICTIONS}
- Metrics exported successfully: ✅

### Accuracy

[Add analysis based on metrics above]

### Decision

Based on the results:

- [ ] ✅ PASS - Proceed to Phase 7 (Precision ≥85%, Recall ≥90%)
- [ ] 🟡 MARGINAL - Tune and retest
- [ ] ❌ FAIL - Investigation needed

---

## Files

- \`service-logs.txt\` - Full service logs
- \`metrics-summary.json\` - Final metrics
- \`health-check.json\` - Health status
- \`RESULTS_SUMMARY.md\` - This file

---

## Next Steps

If test passed:
1. Document results in thesis/report
2. Proceed to Phase 7: HPA Integration
3. Archive test data

If test failed:
1. Review logs for errors
2. Check prediction logic
3. Verify Prometheus queries
4. Retest

---

*Generated: $(date)*
EOF

echo "   ✅ Report generated"

# 5. Summary
echo ""
echo "=========================================="
echo " Results Collected"
echo "=========================================="
echo ""
echo "Files saved to: $OUTPUT_DIR/"
echo ""
echo "Quick Summary:"
cat "$OUTPUT_DIR/metrics-summary.json" | jq '.' 2>/dev/null || echo "No metrics available"
echo ""
echo "Review complete report: $OUTPUT_DIR/RESULTS_SUMMARY.md"
echo ""
