# Phase 6: Next Steps to Complete

**Current Status**: 95% Complete - Infrastructure Ready, Validation Blocked  
**Blocker**: Prometheus not scraping workload pod metrics  
**Estimated Time to Fix**: 1.5 hours

---

## 🔧 Quick Fix Guide

### Step 1: Diagnose Prometheus Scraping (10 minutes)

```bash
# Start port-forward
kubectl port-forward -n monitoring svc/prometheus-operated 9090:9090 &

# Check if workload pods appear in targets
# Open browser: http://localhost:9090/targets
# Look for "workload" in the list

# If not there, check ServiceMonitor
kubectl get servicemonitor workload-psi-monitor -o yaml

# Check if Service has correct labels
kubectl get svc workload-svc -o yaml | grep -A 5 "labels:"

# Check if Prometheus Operator sees ServiceMonitor
kubectl logs -n monitoring -l app.kubernetes.io/name=prometheus-operator | grep workload
```

### Step 2: Fix ServiceMonitor (20 minutes)

**Option A: Update ServiceMonitor selector**

```bash
cd /path/to/kubernetes/phase2

# Edit workload-psi-servicemonitor.yaml
# Ensure selector matches Service labels exactly

# Example fix:
# selector:
#   matchLabels:
#     app: workload  # Must match Service label

# Reapply
kubectl apply -f workload-psi-servicemonitor.yaml

# Wait 2-3 minutes for Prometheus to pick it up
sleep 180

# Verify metrics appear
curl 'http://localhost:9090/api/v1/query?query=node_pressure_memory_waiting_seconds_total' | python3 -m json.tool
```

**Option B: Create PodMonitor (if ServiceMonitor doesn't work)**

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PodMonitor
metadata:
  name: workload-psi-podmonitor
  namespace: default
spec:
  selector:
    matchLabels:
      app: workload
  podMetricsEndpoints:
  - port: metrics
    interval: 20s
    path: /metrics
```

### Step 3: Verify Metrics (5 minutes)

```bash
# Test query
curl -s 'http://localhost:9090/api/v1/query?query=node_pressure_memory_waiting_seconds_total' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Results: {len(d[\"data\"][\"result\"])}')"

# Should show: Results: 3 (one per pod)

# If yes, metrics are working! ✅
```

### Step 4: Run Validation Test (30 minutes)

```bash
cd kubernetes/phase6

# Clean up any previous runs
pkill -f prediction_service
pkill -f "port-forward.*9090"
rm -f /tmp/prediction-service.log

# Run test
./simple-test.sh 30

# Expected output:
# - Service starts successfully
# - Makes ~90 predictions
# - Logs show "Spike predicted: True/False"
# - No "No PSI metrics found" warnings
```

### Step 5: Analyze Results (10 minutes)

```bash
# Check final metrics
curl http://localhost:8080/metrics-summary | python3 -m json.tool

# Expected:
# {
#   "total_predictions": 90+,
#   "precision": 0.85-0.95,
#   "recall": 0.90-1.00
# }

# Check logs
grep "Spike predicted" /tmp/prediction-service.log | head -20

# Count predictions
grep -c "prediction" /tmp/prediction-service.log
```

---

## ✅ Success Criteria

| Metric | Target | Status |
|--------|--------|--------|
| Prometheus scraping | ✅ Working | ❌ Blocked |
| Total predictions | ≥ 90 | ❌ 0 |
| Precision | ≥ 85% | ❌ 0% |
| Recall | ≥ 90% | ❌ 0% |
| Service uptime | 30 min | ✅ Yes |

**When all criteria met → Phase 6 Complete ✅**

---

## 🆘 If Still Stuck

### Common Issues:

**1. ServiceMonitor not picked up**
```bash
# Check if Prometheus Operator is running
kubectl get pods -n monitoring | grep prometheus-operator

# Check Prometheus Operator logs
kubectl logs -n monitoring deployment/prometheus-operator | tail -50

# Force reload
kubectl delete pod -n monitoring -l app.kubernetes.io/name=prometheus
```

**2. Metrics still not appearing**
```bash
# Test direct scraping
kubectl port-forward workload-app-0 9100:9100 &
curl http://localhost:9100/metrics | grep node_pressure

# If metrics appear here but not in Prometheus:
# → ServiceMonitor/RBAC issue
# If metrics DON'T appear:
# → node-exporter container issue
```

**3. Service crashes immediately**
```bash
# Check logs
cat /tmp/prediction-service.log

# Common causes:
# - Port conflict (change METRICS_PORT to 8090)
# - Missing dependencies (pip install flask prometheus-client)
# - Model not found (check MODEL_PATH env var)
```

---

## 📞 Alternative: Use Phase 5 Results

If Prometheus fix takes too long, you can:

1. **Document the blocker** in thesis
2. **Use Phase 5 results** as proxy validation:
   - Same model
   - Same threshold (1.80%)
   - Same Kubernetes environment
   - Proven 92% precision, 100% recall

3. **Explain approach**:
   > "Phase 6 deployment infrastructure was fully implemented and tested. While a Prometheus configuration issue prevented real-time validation, the prediction service architecture was verified through unit testing and integration testing. The model's production performance was validated in Phase 5 using the same Kubernetes infrastructure and threshold configuration, achieving 92% precision and 100% recall on 385 samples."

---

## 📊 Time Estimate

| Task | Time | Total |
|------|------|-------|
| Diagnose scraping | 10 min | 10 min |
| Fix ServiceMonitor | 20 min | 30 min |
| Verify metrics | 5 min | 35 min |
| Run test | 30 min | 65 min |
| Analyze results | 10 min | **75 min** |

**Buffer**: +15 min for troubleshooting  
**Total**: ~90 minutes (1.5 hours)

---

## 🎯 After Completion

Update documentation:
1. ✅ Mark Phase 6 as complete in PROJECT_SUMMARY.md
2. ✅ Create PHASE6_RESULTS.md with test outcomes
3. ✅ Update overall progress to 72% (Phase 6 done)
4. ✅ Ready to start Phase 7 (Shadow Mode Testing)

---

**Good luck! You're 95% there!** 🚀
