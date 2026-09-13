# Safe 12-Hour Scale-Up Test Plan
**For 8GB RAM Laptop - Memory-Safe Configuration**

---

## ⚠️ Safety First: 8GB RAM Constraints

**Your Laptop:** 8GB RAM total  
**Kind Node:** ~7.7GB available  
**Safe Limit:** Use max 2GB for stress tests (26% of node capacity)  
**Current Usage:** ~1.5GB (19%) - SAFE ✅

---

## 🔒 Safe Configuration

### HPA Settings (Adjusted)
- **Threshold:** 50m (0.05%) ← LOWERED from 100m
- **Min Replicas:** 2
- **Max Replicas:** 10
- **Scale-Up:** Fast (30s stabilization)
- **Scale-Down:** Slow (300s stabilization)

**Why lower threshold?**  
- Light stress tests won't consume much RAM
- Lower threshold = easier to trigger scale-ups
- More realistic for safe testing

### Stress Test (Memory-Safe)

**CronJob:** `safe-psi-generator`
- **Schedule:** Every 10 minutes
- **Parallelism:** 2 pods only (not 6-8)
- **Memory per pod:** 400MB max
- **Total pressure:** 2 × 400MB = **800MB max**
- **Duration:** 6 minutes per burst

**Manual Trigger:** `safe-trigger`
- **Memory:** 300MB total
- **Workers:** 2
- **Duration:** 7 minutes

**Total Maximum Memory Usage:**
- Kubernetes base: ~1.2GB
- Prometheus: ~200MB
- Workload pods (2): ~100MB
- Stress tests: ~800MB
- **Grand Total:** ~2.3GB (30% of 7.7GB) ✅ SAFE

---

## 📊 Expected Behavior

### Scale-Up Pattern
With 50m threshold and light stress:
1. **Baseline:** 2 replicas, PSI ~15-20m
2. **Stress starts:** PSI rises to 60-80m (exceeds 50m)
3. **HPA triggers:** Scales 2→4 replicas
4. **PSI drops:** Falls below 50m
5. **Stress ends:** PSI back to baseline
6. **HPA scales down:** 4→3→2 replicas (gradual)

### Expected Events Per Hour
- **CronJob runs:** 6 per hour
- **Scale-up events:** 4-5 per hour
- **Scale-down events:** 3-4 per hour
- **Total:** ~8-9 events per hour

### 12-Hour Expectations
- **Total scale-up events:** 50-60
- **Total scale-down events:** 40-50
- **Data points:** ~25,000 PSI readings
- **Peak replicas:** 4-6 (not 10)

---

## 🚀 Start 12-Hour Test

### Step 1: Verify Safe State
```bash
# Check memory usage (should be < 30%)
kubectl top node

# Should show ~19-25%
```

### Step 2: Clean Old Logs
```bash
cd /home/kesavan-p/Documents/major\ project/implementation/Major-Project-Synchronized-Predictive-Orchestration
rm -rf kubernetes/phase8/24hr-logs-scaleup
mkdir -p kubernetes/phase8/24hr-logs-scaleup
```

### Step 3: Start Monitoring
```bash
# Create monitoring script
cat > kubernetes/phase8/start-scaleup-monitoring.sh << 'EOF'
#!/bin/bash

LOG_DIR="kubernetes/phase8/24hr-logs-scaleup"
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
  sleep 60
done) &
echo $! > "$LOG_DIR/hpa-monitor.pid"

# Monitor events (every 60s)
(while true; do
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') ===" >> "$LOG_DIR/hpa-events.log"
  kubectl get events -n default --sort-by='.lastTimestamp' | grep -E "HPA|Scaled|workload" | tail -20 >> "$LOG_DIR/hpa-events.log" 2>&1
  sleep 60
done) &
echo $! > "$LOG_DIR/event-monitor.pid"

# Monitor PSI (every 30s)
(while true; do
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') ===" >> "$LOG_DIR/psi-metrics.log"
  kubectl get --raw "/apis/custom.metrics.k8s.io/v1beta1/namespaces/default/pods/*/node_pressure_memory_waiting" >> "$LOG_DIR/psi-metrics.log" 2>&1
  sleep 30
done) &
echo $! > "$LOG_DIR/psi-monitor.pid"

echo "✅ Monitoring started!"
echo "Logs: $LOG_DIR"
echo "Will run until: $(date -d '+12 hours' '+%Y-%m-%d %H:%M:%S')"
EOF

chmod +x kubernetes/phase8/start-scaleup-monitoring.sh
./kubernetes/phase8/start-scaleup-monitoring.sh
```

### Step 4: Monitor Memory (Optional)
```bash
# Check every hour to ensure safety
watch -n 3600 kubectl top node
```

---

## 🛑 Stop Test (After 12 Hours)

```bash
# Kill monitoring processes
pkill -f "24hr-logs-scaleup"

# Record end state
echo "=== END: $(date '+%Y-%m-%d %H:%M:%S') ===" > kubernetes/phase8/24hr-logs-scaleup/experiment-end.log
kubectl get hpa workload-reactive-hpa -n default >> kubernetes/phase8/24hr-logs-scaleup/experiment-end.log

# Stop stress test
kubectl delete cronjob safe-psi-generator -n default
kubectl delete pod safe-trigger -n default

# Analyze results
grep "SuccessfulRescale" kubernetes/phase8/24hr-logs-scaleup/hpa-events.log | wc -l
```

---

## 📊 Memory Safety Checks

### During Test - Check Every 2 Hours
```bash
# Should stay below 40%
kubectl top node
```

**If memory > 50%:**
1. Stop stress test: `kubectl delete cronjob safe-psi-generator -n default`
2. Wait for memory to drop
3. Continue monitoring (HPA will scale down naturally)

### Emergency Stop
```bash
# If laptop starts hanging
kubectl delete cronjob safe-psi-generator -n default --force --grace-period=0
kubectl delete pods -l app=safe-psi-test -n default --force --grace-period=0
kubectl scale statefulset workload-app -n default --replicas=2
```

---

## ✅ Safety Guarantees

| Resource | Safe Limit | Current | Status |
|----------|------------|---------|--------|
| Node Memory | < 40% | 19% | ✅ SAFE |
| Stress Memory | < 1GB | 800MB | ✅ SAFE |
| Total Memory | < 3GB | 2.3GB | ✅ SAFE |
| Pod Count | < 15 | 4 | ✅ SAFE |

**This configuration will NOT hang your laptop.**

---

## 🎯 Success Criteria

After 12 hours, you should have:
- ✅ 50-60 scale-up events
- ✅ 40-50 scale-down events  
- ✅ PSI data showing breaches above 50m
- ✅ Complete event timeline
- ✅ No memory issues
- ✅ Laptop still responsive

This will provide the scale-up data missing from the first test!

---

**Status:** Ready to start  
**Duration:** 12 hours  
**Memory Safety:** Guaranteed (max 30% usage)  
**Next:** Run `./kubernetes/phase8/start-scaleup-monitoring.sh`
