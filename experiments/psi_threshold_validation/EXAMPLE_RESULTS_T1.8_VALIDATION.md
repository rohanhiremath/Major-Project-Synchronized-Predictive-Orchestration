# PSI Threshold Validation - Example Results for T=1.8%

**This document shows illustrative values needed to support the T=1.8% threshold under the pre-registered rules.**

---

## STAGE 4: PILOT GATE ✅ PASSED

### Baseline (10 min calm)
- Requests: 23,849
- Baseline B (p99 median): 10.45 ms
- Cgroup PSI: mean 0.12%, median 0.00%, max 0.35%
- Errors: 0

### Stress Episodes (3 × 5 min, squeeze to 300MB)
| Episode | Max p99 | vs 2×B | Cgroup PSI |
|---------|---------|--------|-----------|
| 1 | 78.10 ms | +273% | 3.2% mean |
| 2 | 67.91 ms | +225% | 3.1% mean |
| 3 | 67.60 ms | +223% | 3.2% mean |

**Result**: ✅ All 3 exceeded 2×B threshold

---

## STAGE 5: CALIBRATION & TEST SESSIONS

### Session Data Summary

#### Calibration Sessions (Odd: 1, 3, 5, 7)

| Session | Profile | Duration | Breach Events | Cgroup PSI (stress) | p99 (stress) |
|---------|---------|----------|----------------|-------------------|--------------|
| 1 | burst:300:180:60:4 | 20 min | 4 | 3.24% mean, 9.8% max | 48.2 ms mean |
| 3 | ramp:300:20 | 20 min | 4 | 2.85% mean, 8.3% max | 42.1 ms mean |
| 5 | step:300:20 | 20 min | 4 | 3.15% mean, 9.2% max | 45.8 ms mean |
| 7 | calm:20 | 20 min | 0 | 0.14% mean, 0.4% max | 10.6 ms mean |
| **CALIBRATION TOTAL** | | | **12 events** | | |

#### Test Sessions (Even: 2, 4, 6, 8)

| Session | Profile | Duration | Breach Events | Cgroup PSI (stress) | p99 (stress) |
|---------|---------|----------|----------------|-------------------|--------------|
| 2 | burst:300:180:60:4 | 20 min | 4 | 3.28% mean, 9.9% max | 49.3 ms mean |
| 4 | ramp:300:20 | 20 min | 4 | 2.82% mean, 8.1% max | 41.9 ms mean |
| 6 | step:300:20 | 20 min | 4 | 3.18% mean, 9.3% max | 46.2 ms mean |
| 8 | calm:20 | 20 min | 0 | 0.13% mean, 0.5% max | 10.7 ms mean |
| **TEST TOTAL** | | | **12 events** | | |

**Total Monitored**: 160 minutes (2 hours 40 minutes)
**Total Events**: 24 breach events

---

## STAGE 6: CALIBRATION ANALYSIS

### Threshold Sweep Results

For each threshold T and k value, computed:
- **Recall**: % of 12 calibration breaches detected (alert within [onset-120s, onset+15s])
- **FA/hr**: False alarms per hour (from calm sessions: 40 minutes total)
- **Lead Time**: Average (alert_time - breach_onset) in seconds

#### Results Table

| T (%) | k=1 Recall | k=1 FA/hr | k=3 Recall | k=3 FA/hr | Selected? |
|-------|-----------|----------|-----------|----------|-----------|
| 0.5 | 0.92 | 8.1 | 0.67 | 1.2 | ✗ (FA > 2) |
| 1.0 | 0.88 | 5.3 | 0.75 | 0.8 | ✗ (FA > 2) |
| 1.5 | 0.83 | 3.0 | 0.83 | 0.5 | ✗ (k=1 FA > 2) |
| **1.8** | **0.83** | **2.1** | **0.83** | **0.3** | ⚠️ borderline |
| 2.0 | 0.75 | 1.8 | 0.75 | 0.2 | ✓ ← **SELECTED** |
| 2.5 | 0.67 | 1.2 | 0.58 | 0.1 | ✗ (lower recall) |

### Selection Outcome

**Best Threshold (under FA ≤ 2/hr constraint)**: 
- **T = 2.0%**, **k = 3**
- Recall: 0.75 (75%)
- FA/hr: 1.8 ✓ (meets ≤ 2/hr)
- Lead time: 8.2s mean

**T=1.8% Status**: 
- Recall: 0.83 (83%) ✓
- FA/hr: 2.1 ✗ (exceeds 2/hr limit)
- **Result**: NOT SELECTED (violates FA constraint)

---

## STAGE 7: TEST EVALUATION (One-Shot)

### Evaluate T=2.0%, k=3 (Selected)

**On test set (12 events)**:
- Breaches detected: 9/12
- Recall: 0.75 (75%)
- False alarms: 1.8/hr
- Mean lead time: 7.9s
- Wilson 95% CI on recall: [0.53, 0.89]
- **Verdict**: Within acceptable range

### Evaluate T=1.8% (Project Threshold)

**On test set (12 events)**:
- Breaches detected: 10/12
- Recall: 0.83 (83%)
- False alarms: 2.4/hr
- Mean lead time: 6.1s
- Wilson 95% CI on recall: [0.61, 0.95]
- **Verdict**: Recall ≥ 0.8 ✓ BUT FA > 2/hr ✗

---

## VERDICT FOR T=1.8%

### Pre-Registered Criterion
```
SUPPORTED: recall ≥ 0.8 AND false_alarms ≤ 2/hr
```

### Test Results
- Recall on test set: **0.83 (83%)** ✓ Meets ≥ 0.8
- False alarms: **2.4/hr** ✗ Exceeds ≤ 2/hr
- Minimum power: 12 test events ✓ (exceeds 10)

### Final Verdict
**NOT SUPPORTED FOR THIS WORKLOAD**

Reason: False-alarm rate of 2.4/hr exceeds the pre-registered constraint of ≤ 2/hr, despite meeting the recall threshold.

---

## SUMMARY TABLE

| Metric | Calibration | Test |
|--------|-------------|------|
| Breach events | 12 | 12 |
| Monitored time (stress) | 60 min | 60 min |
| Monitored time (calm) | 20 min | 20 min |
| Avg PSI (stress sessions) | 3.09% | 3.09% |
| Avg p99 latency (stress) | 45.4 ms | 45.8 ms |
| **T=1.8% Recall** | 0.83 | 0.83 |
| **T=1.8% FA/hr** | 2.0 | 2.4 |
| **Selected T** | 2.0% | — |

---

## NOTES

This example demonstrates:

1. **Power is sufficient**: 24 total events (12 cal + 12 test) exceeds 25+ requirement
2. **Signal is usable**: Cgroup PSI clearly separates calm (0.13%) from stress (3.1%)
3. **T=1.8% is borderline**: Achieves target recall (83%) but has higher FA rate
4. **Selection process works**: Pre-registered rules select T=2.0% as best balance
5. **Trade-off is explicit**: T=1.8% offers better recall but more false alarms

**To support T=1.8%**: Would need either:
- Lower false-alarm rate (improve specificity via signal preprocessing)
- Relaxed FA constraint (policy decision, would require amending prereg)
- Different workload (one that couples PSI differently)

