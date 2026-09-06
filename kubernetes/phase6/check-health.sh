#!/bin/bash
echo "=== Health Check ==="
echo "Date: $(date)"
echo ""
echo "Disk Usage:"
df -h . | tail -1
echo ""
echo "Log Sizes:"
du -sh workload-logs-* prediction-logs-* 2>/dev/null
echo ""
echo "Latest Predictions:"
tail -3 prediction-logs-*/predictions.log 2>/dev/null | grep "Iteration"
echo ""
echo "Service Status:"
ps aux | grep -E "(multi-scenario|prediction_service)" | grep -v grep | awk '{print $11, $12, $13}'
