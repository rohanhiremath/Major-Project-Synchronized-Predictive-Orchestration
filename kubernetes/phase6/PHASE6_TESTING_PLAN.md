# Phase 6: Complete Testing Plan

**Goal**: Validate the prediction service makes accurate real-time predictions matching Phase 5 performance (92% precision, 100% recall)

**Status**: Infrastructure ✅ Complete, Query ✅ Fixed, Ready for validation testing

---

## 🎯 Testing Strategy

Following Phase 5's validation approach, we need:
1. **Sufficient spike density** (15-18% target, minimum 40-60 spikes)
2. **Realistic workload patterns** (burst/idle cycles)
3. **Adequate duration** (30-120 minutes)
4. **Ground truth comparison** (actual PSI vs predictions)

---

## 📋 Test Plan: 30-Minute Validation Test

### Test Configuration

```bash
Duration: 30 minutes
Pattern: 5-minute burst + 3-minute idle (6 cycles)
Workloads: Memory stress (80%), CPU stress, Mixed stress
Expected predictions: ~90 (every 20 seconds)
Target spikes: 15-20 (16-20% density)
```

### Success Criteria (from Phase 5)

| Metric | Target | Status |
|--------|--------|--------|
| **Precision** | ≥ 85% | 🎯 Target: 92% |
| **Recall** | ≥ 90% | 🎯 Target: 100% |
| **F1 Score** | ≥ 87% | 🎯 Target: 95.8% |
| **Total Predictions** | ≥ 90 | - |
| **Spike Detection** | ≥ 15 | - |

---

## 🚀 How to Run Tests

### Test 1: Quick Validation (5 minutes)

**Purpose**: Verify service is working end-to-end

```bash
cd "/home/kesavan-p/Documents/major project/implementation/Major-Project-Synchronized-Predictive-Orchestration/kubernetes/phase6"

# Run 5-minute test
./run-test-venv.sh 5
```

**Expected Output**:
```
✅ Prediction service running
✅ Workload pods ready
▶ Generating PSI spikes...
  Predictions logged: 15
⏸  Recovery period...
Test Complete!
```

**Check Results**:
```bash
# View logs
tail -50 /tmp/prediction-service.log

# Should see iterations every 20 seconds
# No "No PSI metrics" warnings
```

**✅ Pass Criteria**: Service runs without errors, makes ~15 predictions

---

### Test 2: Full Validation (30 minutes) ⭐ **RECOMMENDED**

**Purpose**: Validate precision/recall matching Phase 5

```bash
cd "/home/kesavan-p/Documents/major project/implementation/Major-Project-Synchronized-Predictive-Orchestration/kubernetes/phase6"

# Run 30-minute test
./run-test-venv.sh 30
```

**What Happens**:
1. Service starts and loads model
2. Prometheus port-forward established
3. 6 cycles of burst/idle workloads
4. ~90 predictions made
5. Results collected at end

**Expected Duration**: 30 minutes

**Expected Output**:
```
==========================================
 Test Complete!
==========================================
Results:
{
  "total_predictions": 90,
  "true_positives": 45,
  "false_positives": 3,
  "false_negatives": 0,
  "precision": 0.92,
  "recall": 1.00
}
```

**✅ Pass Criteria**:
- Precision ≥ 85% (Target: 92%)
- Recall ≥ 90% (Target: 100%)
- Total predictions ≥ 85
- No service crashes

---

### Test 3: Extended Validation (2 hours)

**Purpose**: Long-duration stability and performance validation

```bash
cd "/home/kesavan-p/Documents/major project/implementation/Major-Project-Synchronized-Predictive-Orchestration/kubernetes/phase6"

# Run 2-hour test
./run-test-venv.sh 120
```

**Use Case**: If you want to match Phase 5's 44-minute data collection with even more samples

**Expected**: 360+ predictions, 60-80 spikes detected

---

## 📊 Analyzing Results

### Step 1: Check Service Logs

```bash
# View all predictions
cat /tmp/prediction-service.log

# Count iterations
grep -c "Iteration" /tmp/prediction-service.log

# Look for any errors
grep -E "ERROR|WARNING|Exception" /tmp/prediction-service.log
```

### Step 2: Check Metrics

```bash
# View JSON metrics (if service is still running)
curl http://localhost:8080/metrics-summary | python3 -m json.tool

# Or check saved file
cat /tmp/prediction-metrics.json | python3 -m json.tool
```

### Step 3: Calculate Performance

If the service doesn't automatically calculate precision/recall, do it manually:

```bash
# Extract predictions from logs
grep "Spike predicted" /tmp/prediction-service.log > predictions.txt

# Compare with actual PSI values from Prometheus
# (You can query Prometheus for the same time period)
```

---

## 🔍 What to Look For

### ✅ Good Signs

1. **No "No PSI metrics" warnings**
   - Query is working
   - Prometheus has data

2. **Iterations every 20 seconds**
   - Service running smoothly
   - No hangs or crashes

3. **Model predictions made**
   - Should see "Spike predicted: True/False" in logs
   - PSI values logged

4. **Metrics collected**
   - `/tmp/prediction-metrics.json` exists
   - Contains precision/recall data

### ❌ Problems to Watch For

1. **"No PSI metrics found"**
   - Query issue (should be fixed now)
   - Prometheus not accessible

2. **Service crashes**
   - Check logs for exceptions
   - Model loading failures

3. **No predictions logged**
   - Insufficient data in buffer (need 30+ samples)
   - Model not making predictions

4. **All predictions are False**
   - No spikes detected (workload too light)
   - Need more aggressive stress testing

---

## 📝 Documentation Requirements

After successful test, document:

### 1. Test Configuration
```
Duration: 30 minutes
Cycles: 6 (5min burst + 3min idle)
Predictions: 90
Spikes detected: 18
Threshold: 1.80%
```

### 2. Performance Results
```
Precision: 91.2%
Recall: 97.8%
F1 Score: 94.4%
True Positives: 43
False Positives: 4
False Negatives: 1
```

### 3. Service Stability
```
Uptime: 30 minutes
Errors: 0
Avg prediction latency: <50ms
Memory usage: Stable at ~500MB
```

---

## 🎓 For Your Thesis

### Validation Methodology

> "The prediction service was validated through a 30-minute intensive testing period, generating controlled workload patterns in a Kubernetes cluster. The service queried Prometheus every 20 seconds for real-time PSI metrics from three workload pods, making 90 predictions over the test duration. The validation employed the same model (11,884 parameters) and threshold (1.80%) optimized in Phase 5, achieving [X%] precision and [Y%] recall on real-time production data."

### Comparison with Phase 5

| Aspect | Phase 5 (Batch) | Phase 6 (Real-time) |
|--------|-----------------|---------------------|
| **Data Source** | CSV file | Live Prometheus |
| **Prediction Mode** | Batch (post-hoc) | Streaming (real-time) |
| **Samples** | 385 | 90-360 |
| **Duration** | 44 minutes | 30-120 minutes |
| **Precision** | 92.0% | [Test Result] |
| **Recall** | 100.0% | [Test Result] |
| **Latency** | N/A | <100ms per prediction |

---

## 🔄 If Results Don't Match Phase 5

### Scenario 1: Lower Precision (e.g., 80%)

**Cause**: More false positives in real-time data  
**Solution**: Increase threshold from 1.80% to 2.00%

```bash
# Update threshold
export SPIKE_THRESHOLD="2.00"
./run-test-venv.sh 30
```

### Scenario 2: Lower Recall (e.g., 85%)

**Cause**: Missing spikes (false negatives)  
**Solution**: Decrease threshold to 1.50% or 1.60%

### Scenario 3: No Spikes Detected

**Cause**: Workload not generating enough PSI pressure  
**Solution**: 
- Increase stress-ng intensity
- Run longer burst periods
- Add more stress types simultaneously

---

## ✅ Final Validation Checklist

Before marking Phase 6 complete:

- [ ] Service runs without errors for 30+ minutes
- [ ] Makes 90+ predictions  
- [ ] Detects 15+ spikes
- [ ] Precision ≥ 85%
- [ ] Recall ≥ 90%
- [ ] No "No PSI metrics" warnings
- [ ] Logs saved and analyzed
- [ ] Results documented
- [ ] Performance matches Phase 5 (within 5%)

---

## 🎯 Recommended Next Steps

### Step 1: Run 30-Minute Test NOW
```bash
cd kubernetes/phase6
./run-test-venv.sh 30
```

### Step 2: While Test Runs (in another terminal)

Monitor progress:
```bash
# Watch iterations
watch -n 5 'tail -5 /tmp/prediction-service.log'

# Check Prometheus
kubectl port-forward -n monitoring svc/prometheus-operated 9090:9090
# Open: http://localhost:9090/graph
# Query: irate(node_pressure_memory_waiting_seconds_total[1m])*100
```

### Step 3: After Test Completes

```bash
# Analyze results
cat /tmp/prediction-metrics.json

# Save results
mkdir -p phase6-results-$(date +%Y%m%d)
cp /tmp/prediction-service.log phase6-results-$(date +%Y%m%d)/
cp /tmp/prediction-metrics.json phase6-results-$(date +%Y%m%d)/
```

### Step 4: Document and Update

Update `PROJECT_SUMMARY.md` with Phase 6 results.

---

## 🚀 Ready to Start?

**Run the 30-minute validation test:**

```bash
cd "/home/kesavan-p/Documents/major project/implementation/Major-Project-Synchronized-Predictive-Orchestration/kubernetes/phase6"
./run-test-venv.sh 30
```

**Estimated time**: 30 minutes  
**Expected outcome**: Phase 6 validation complete ✅

---

*All issues fixed, query working, venv configured correctly. Ready for final validation!*
