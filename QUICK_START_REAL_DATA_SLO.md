# Quick Start: Real Data Collection & 200ms SLO Validation

## TL;DR - 3 Commands

```bash
# 1. Collect real data (2-4 hours)
python collect_real_data_200ms_slo.py

# 2. Validate PSI threshold
python experiments/psi_threshold_validation/test_absolute_psi_real_data_slo.py \
  --data data/real_data_200ms_slo_*.csv

# 3. Deploy if SUPPORTED
# Update your alerting with T=1.8% PSI threshold
```

---

## What Gets Collected

| Field | Example | Purpose |
|-------|---------|---------|
| timestamp | 2026-10-19T14:00:00 | Sample time |
| psi_some_avg10 | 0.5 | **PSI signal** to validate |
| latency_ms | 45.2 | Service latency measurement |
| slo_breach | 0 or 1 | **Label**: 1 if latency > 200ms |

---

## What Gets Validated

```
Threshold: T = 1.8% PSI
Question: Does PSI > 1.8% predict latency > 200ms?

Result: SUPPORTED if:
  ✓ Recall >= 60% (catches most breaches)
  ✓ FA/hr <= 2.0 (not too many false alarms)
  ✓ Both criteria statistically significant
```

---

## Expected Output

### Successful Validation
```
✓ SELECTED: T=1.8%, k=1
  Recall: 0.8341 (83% catch rate)
  FA/hr: 0.0000 (no false alarms)
  Precision: 1.0000 (100% accurate)

VERDICT: SUPPORTED ✓
→ Deploy to production
```

### Failed Validation
```
❌ NO VIABLE THRESHOLDS FOUND

Best candidate:
  T=1.8%, k=1: recall=0.45, FA/hr=0.5
  
VERDICT: NOT_SUPPORTED ✗
→ Collect more data or adjust threshold
```

---

## Configuration

Edit `collect_real_data_200ms_slo.py`:

```python
COLLECTION_DURATION_MINUTES = 120    # 2 hours (increase for more SLO breaches)
SAMPLE_INTERVAL_SECONDS = 20         # Leave as-is
SLO_THRESHOLD_MS = 200.0             # Your SLO (200ms = example)
POD_NAME = "memory-intensive-app"    # Your pod
NAMESPACE = "default"                # Your namespace
```

---

## Minimum Requirements

- **At least 10 SLO breaches** in collected data (latency > 200ms)
- **2+ hours of collection** (at minimum)
- **kubectl access** (or simulated data mode)

If insufficient breaches:
```
⚠ WARNING: Very few SLO breaches collected (<10)
→ Run collection longer or add load stress
```

---

## Files Involved

```
Input:
  collect_real_data_200ms_slo.py
  
Output:
  data/real_data_200ms_slo_TIMESTAMP.csv  ← Use this for validation
  
Validation:
  experiments/psi_threshold_validation/test_absolute_psi_real_data_slo.py
  
Results:
  test_real_data_slo_results_*.json       ← Check for SUPPORTED/NOT_SUPPORTED
```

---

## Typical Results (Examples)

### Case 1: Real Production Data (SUPPORTED)
```
Threshold: T=1.8%
  Recall: 0.834 (83.4%)
  FA/hr: 0.000
  95% CI: [0.807, 0.858]
  VERDICT: SUPPORTED ✓
```

### Case 2: Limited SLO Breaches (NOT_SUPPORTED)
```
Threshold: T=1.8%
  Recall: 0.450 (45.0%)
  FA/hr: 0.000
  95% CI: [0.350, 0.550]
  VERDICT: NOT_SUPPORTED ✗
  → Need more SLO breaches in data
```

### Case 3: Too Many False Alarms (NOT_SUPPORTED)
```
Threshold: T=0.5%
  Recall: 0.900 (90.0%)
  FA/hr: 3.500  ← Too high!
  VERDICT: NOT_SUPPORTED ✗
  → Try T=1.8% instead
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `kubectl not found` | Script uses simulated data (still works for testing) |
| `No SLO breaches` | Increase collection time or add load stress |
| `Very few SLO breaches` | Run collection 4+ hours instead of 2 |
| `NOT_SUPPORTED verdict` | Collect more data or try lower threshold |
| `Data file not found` | Use correct path: `data/real_data_*.csv` |

---

## After Validation Succeeds

1. **Update alerting**:
   ```
   Alert when: psi_some_avg10 > 1.8%
   Severity: Warning
   Message: "Memory pressure high, SLO breach likely"
   ```

2. **Deploy monitoring**:
   - Add to Prometheus rules
   - Connect to PagerDuty/Slack
   - Add to dashboards

3. **Document threshold**:
   - Add to runbooks
   - Record validation date (20261019)
   - Note confidence level (95% CI)

---

## Time Estimate

| Step | Time |
|------|------|
| Setup & config | 5-10 min |
| Collect data | 2-4 hours |
| Run validation | 1-2 min |
| **Total** | **~2-4 hours** |

---

## Success Indicators

✅ Collection completes with output showing SLO breaches  
✅ Validation script runs without errors  
✅ Results show `VERDICT: SUPPORTED`  
✅ Recall >= 60% and FA/hr <= 2.0  
✅ Ready to deploy to production

---

## Next: What To Do With Results

```
IF validation = SUPPORTED:
  → Deploy T=1.8% PSI threshold to monitoring
  → Update alert rules
  → Document in runbooks
  
IF validation = NOT_SUPPORTED:
  → Collect more data (run again)
  → Try different threshold
  → Check data quality
```

---

**For detailed instructions**, see: `REAL_DATA_200MS_SLO_VALIDATION_GUIDE.md`
