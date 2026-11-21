# Real Data Collection & 200ms SLO Validation Guide

**Objective**: Collect real production data and validate PSI thresholds against actual 200ms SLO breaches

**Timeline**: 2-4 hours for data collection + analysis

---

## Quick Start

### Step 1: Collect Real Data (2+ hours)

```bash
cd /home/kesavan-p/Documents/major\ project/implementation/Major-Project-Synchronized-Predictive-Orchestration

# Set configuration in script, then run:
python collect_real_data_200ms_slo.py
```

**What it collects:**
- PSI metrics from `/proc/pressure/memory` in your pod
- Latency measurements from application or load generator
- Labels samples as SLO breach if latency > 200ms
- Outputs: CSV file with timestamp, PSI, latency, SLO breach flag

**Output example:**
```
real_data_200ms_slo_20261019_140000.csv
  ├─ timestamp: 2026-10-19T14:00:00
  ├─ psi_some_avg10: 0.5%
  ├─ psi_some_avg60: 0.3%
  ├─ psi_full_avg10: 0.2%
  ├─ latency_ms: 45.2
  └─ slo_breach: 0  (or 1 if latency > 200ms)
```

### Step 2: Validate PSI Thresholds

```bash
cd experiments/psi_threshold_validation

# Run validation against collected data:
python test_absolute_psi_real_data_slo.py \
  --data ../../data/real_data_200ms_slo_20261019_140000.csv
```

**Output:**
```
[STEP 1] Load real data
  ✓ 10,800 samples loaded

[STEP 2] Sweep PSI thresholds
  Results: T=0.5%, k=1 ✓ VIABLE
           T=1.0%, k=1 ✓ VIABLE
           T=1.8%, k=1 ✓ VIABLE

[STEP 3] Analysis
  SELECTED: T=1.8%, k=1
    Recall: 0.8341 (83.41%)
    FA/hr: 0.0000
    Precision: 1.0000
    
[STEP 4] Statistical Validation
  Recall 95% CI: [0.8075, 0.8577]
  FA/hr 95% CI: [0.0000, 0.0000]
  
  VERDICT: SUPPORTED ✓
```

---

## Detailed Instructions

### Configure Data Collection

Edit `collect_real_data_200ms_slo.py` and update these settings:

```python
# Configuration section at top of script
COLLECTION_DURATION_MINUTES = 120  # How long to collect (2+ hours recommended)
SAMPLE_INTERVAL_SECONDS = 20      # Match synthetic data: 20s bins
SLO_THRESHOLD_MS = 200.0          # Your SLO threshold
POD_NAME = "memory-intensive-app" # Your pod name
NAMESPACE = "default"              # Your Kubernetes namespace
```

### Prerequisites

#### Option A: Real Kubernetes Cluster Data

**Required:**
- Kubernetes cluster access via `kubectl`
- Pod with PSI metrics available at `/proc/pressure/memory`
- Latency metrics available (Prometheus, application endpoint, or logs)

**Setup:**
```bash
# Verify kubectl access
kubectl cluster-info

# Verify pod exists
kubectl get pods -n default | grep memory-intensive-app

# Verify metrics are available
kubectl exec -n default memory-intensive-app -- cat /proc/pressure/memory
```

#### Option B: Simulated Data (for testing)

If you don't have real Kubernetes infrastructure, the script will automatically use simulated data:

```
Note: Not running inside Kubernetes cluster
      Using simulated data for demonstration
```

The simulated data will:
- Generate realistic PSI patterns with occasional spikes
- Create latency data with 8% probability of exceeding 200ms SLO
- Provide enough SLO breaches for validation

**Simulated data is useful for:**
- Testing the validation framework
- Demonstrating the process
- Dry-running before deploying to production

### Run Data Collection

```bash
# Start collection
python collect_real_data_200ms_slo.py

# Monitor progress
# Output will show:
#   [  10.5%]   128 samples | SLO breaches:    2 | Last PSI:   0.50% | Last latency:   45.23ms
#   [  20.3%   256 samples | SLO breaches:    5 | Last PSI:   0.80% | Last latency:  245.67ms
#   [  30.1%]   384 samples | SLO breaches:   12 | Last PSI:   1.20% | Last latency:   52.14ms
# ...
```

**Expected duration:**
- 2 hours = 360 samples (20s intervals)
- 4 hours = 720 samples
- More data = better validation results

### Collect Multiple Sessions (Recommended)

Run collection multiple times to get more diverse data:

```bash
# Session 1: Normal workload
python collect_real_data_200ms_slo.py
# Output: real_data_200ms_slo_20261019_140000.csv

# Session 2: With memory pressure
python collect_real_data_200ms_slo.py
# Output: real_data_200ms_slo_20261019_150000.csv

# Session 3: With CPU stress
python collect_real_data_200ms_slo.py
# Output: real_data_200ms_slo_20261019_160000.csv

# Combine all data
cat data/real_data_200ms_slo_*.csv > data/real_data_combined.csv

# Validate against combined dataset
python experiments/psi_threshold_validation/test_absolute_psi_real_data_slo.py \
  --data data/real_data_combined.csv
```

### Run Threshold Validation

```bash
cd experiments/psi_threshold_validation

python test_absolute_psi_real_data_slo.py \
  --data ../../data/real_data_200ms_slo_20261019_140000.csv
```

### Interpret Results

#### Successful Validation (SUPPORTED)

```
VERDICT: SUPPORTED ✓

Meaning:
  ✓ T=1.8% PSI threshold reliably predicts 200ms SLO breaches
  ✓ 83% recall - catches most latency problems
  ✓ 100% precision - no false alarms
  ✓ Statistically significant (95% CI validates)

Action: Deploy T=1.8% PSI threshold to production
```

#### Validation Failed (NOT_SUPPORTED)

```
VERDICT: NOT_SUPPORTED ✗

Reasons might be:
  ✗ Recall CI lower < 0.60 (not catching enough breaches)
  ✗ FA/hr CI upper > 2.0 (too many false alarms)
  ✗ Insufficient SLO breach data

Next Steps:
  1. Collect more data (run longer collection)
  2. Try lower threshold (e.g., T=1.0% instead of 1.8%)
  3. Verify PSI metrics are correctly captured
  4. Check for data quality issues
```

---

## Expected Data Characteristics

### For Successful Validation

You need:
- **At least 10-20 SLO breaches** in collected data
- **3-5% SLO breach rate** or higher (depends on your workload)
- **Varied PSI levels** (mix of calm and high-pressure periods)

### Data Quality Checks

The collection script will warn you:

```
✓ Good number of SLO breaches for validation
  (when SLO breach count >= 10)

⚠ WARNING: Very few SLO breaches collected (<10)
  Recommendation: Increase collection duration or workload intensity

⚠ WARNING: SLO breach rate very low (<0.1%)
  Recommendation: Increase collection duration or add stress test
```

### If Not Enough SLO Breaches

**Options:**
1. **Extend collection time** - run for 4+ hours instead of 2
2. **Add load stress** - increase traffic to generate breaches
3. **Add memory pressure** - intentionally stress the pod
4. **Combine multiple sessions** - collect data under different conditions

---

## Files Created During Process

```
Data Collection:
  data/real_data_200ms_slo_20261019_140000.csv  ← Raw collected data
  
Validation Scripts:
  collect_real_data_200ms_slo.py                 ← Data collection
  experiments/psi_threshold_validation/
    test_absolute_psi_real_data_slo.py           ← Validation runner
  
Results:
  test_real_data_slo_results_real_data_*.json    ← Validation results
```

---

## Advanced: Validate Both Absolute and Delta PSI

After validating absolute PSI, test delta PSI:

```bash
# First, validate absolute PSI (see above)
python test_absolute_psi_real_data_slo.py --data real_data.csv

# Then create delta PSI validator (similar structure)
# Compare: which signal better predicts 200ms SLO breaches?
```

---

## Troubleshooting

### Problem: "kubectl not found or cluster not accessible"

**Solution:**
- The script will automatically switch to simulated data
- Or install kubectl and configure cluster access

### Problem: "No SLO breaches in data"

**Meaning:** No latency measurements exceeded 200ms

**Solutions:**
1. Increase collection duration (run 4+ hours)
2. Add load stress to generate latency spikes
3. Verify latency measurements are being captured correctly
4. Check if 200ms SLO is realistic for your service (may need adjustment)

### Problem: "Very few SLO breaches (<10)"

**Solutions:**
1. Extend collection time
2. Add intentional memory pressure to the pod
3. Increase traffic/load to trigger degradation
4. Combine multiple collection sessions

### Problem: Validation returns "NOT_SUPPORTED"

**Meaning:** PSI threshold doesn't reliably predict SLO breaches

**Next Steps:**
1. Try lower thresholds (T=1.0%, T=0.5%)
2. Collect more diverse data
3. Verify PSI metrics are correctly correlated with latency
4. Check for data quality or measurement issues

---

## Expected Timeline

| Step | Duration | Action |
|------|----------|--------|
| Setup | 15 min | Configure pod names, namespaces, SLO |
| Collection | 2-4 hrs | Run data collection script |
| Validation | 5 min | Run threshold validation |
| Analysis | 15 min | Interpret results |
| **Total** | **2-4 hrs** | **Full cycle** |

---

## Deployment After Validation

Once validation succeeds with real data:

### 1. Update Monitoring Rules

```yaml
Alert Rules:
  - name: "PSI Exceeds Threshold"
    condition: psi_some_avg10 > 1.8%
    severity: "warning"
    description: "Memory pressure exceeded safe threshold, SLO breach likely"
```

### 2. Deploy PSI Monitoring

```python
# In your monitoring/alerting system:
if psi_some_avg10 > 1.8:
    trigger_alert("High memory pressure detected")
    # Can trigger autoscaling, capacity alerts, etc.
```

### 3. Document Threshold

Add to runbooks:
```markdown
## Memory Pressure SLO Alert

**Threshold**: PSI > 1.8% predicts latency > 200ms
**Validation**: Tested against real production data (20261019)
**Reliability**: 83% recall, 100% precision
**Confidence**: 95% CI validated via Wilson score
```

---

## Success Criteria

✅ **Validation is successful when:**
- Absolute PSI (T=1.8%) verdict is **SUPPORTED**
- Recall is **>= 60%** (catches most breaches)
- False alarm rate is **<= 2/hour**
- Both criteria pass statistical tests

✅ **Ready for production deployment**

---

## Next Steps After Validation

1. **Deploy monitoring**: Update Prometheus/Grafana rules
2. **Update alerting**: Connect to PagerDuty, Slack, etc.
3. **Document**: Add to SLO runbooks and playbooks
4. **Monitor**: Track accuracy in production
5. **Iterate**: Adjust threshold based on real-world performance

---

## Contact & Support

If you encounter issues:
1. Check troubleshooting section above
2. Review collected data for anomalies
3. Verify PSI metrics are being captured correctly
4. Consider alternative thresholds or signals

---

**Status**: Ready for real data collection  
**SLO Target**: 200ms latency  
**Expected Result**: Validated PSI threshold for production deployment
