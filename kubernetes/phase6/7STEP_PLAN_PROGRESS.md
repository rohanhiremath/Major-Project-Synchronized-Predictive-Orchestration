# 7-Step Plan for 200k Samples - Progress Tracker

## Overview

Following the user's excellent 7-step plan for comprehensive validation.

**Key Insight from Steps 1-2**: We have **53 real spike events** from history!  
**New Target**: 100-200 total spike events (not 200k samples)

---

## Progress

### ✅ Step 1: Check Prometheus Retention - COMPLETE

**Results**:
- Retention window: **11 days**
- Data available: August 26 - September 6, 2026
- Expected samples: ~142,560 (at 20s interval)

**Files**: `STEP1_RETENTION_CHECK.md`

---

### ✅ Step 2: Pull Historical Spikes - COMPLETE

**Results**:
- **Samples collected**: 26,830 (9 days actual data)
- **Spike events found**: **53 real events** ⭐
- **Max PSI**: 52.61%
- **Files**: `historical-data/` directory

**Key Achievement**: 53 real production spike events!

**Files**: 
- `historical-data/psi_historical_26830_samples_11days.csv`
- `historical-data/spike_events_53_events.csv`
- `STEP2_COMPLETE.md`

---

### ➡️ Step 3: Multi-Scenario Workload Generation - NEXT

**Goal**: Generate diverse PSI patterns using Phase 4 workload generators

**Scenarios to implement**:
1. **Step pattern**: Gradual load increase
2. **Ramp pattern**: Linear increase over time  
3. **Periodic pattern**: Repeated bursts (sine wave)
4. **Sustained pattern**: Constant high load
5. **Flash pattern**: Sudden spikes
6. **Mixed pattern**: Combination of above

**Target**: 50-100 new spike events across scenarios

**Duration**: 3-5 days continuous

**Files to create**:
- `multi-scenario-workload.sh` - Orchestrates all scenarios
- `STEP3_WORKLOAD_SCENARIOS.md` - Documentation

---

### ⏳ Step 4: Run Prediction Service Continuously - PENDING

**Goal**: Service runs at native 20s interval in shadow mode

**Configuration**:
- Keep `PREDICTION_INTERVAL=20` (don't compress)
- Run in background for several days
- Log all predictions to disk
- Compute metrics post-hoc

**Target duration**: 5-7 days (parallel with Step 3)

**Expected output**:
- Predictions: ~21,600 per day × 5 days = ~108,000
- Combined with historical: 26,830 + 108,000 = ~135,000 samples

**Files to create**:
- `run-continuous-prediction-service.sh`
- Log analysis scripts

---

### ⏳ Step 5: Spike-Count Target - PENDING

**Goal**: Track spike events, not sample count

**New Target**: 100-200 distinct spike events

**Progress tracking**:
```
Historical spikes:     53  ✅
New spikes needed:     47-147
Check frequency:       Every 1-2 days
```

**Stop condition**: When 100+ spike events collected with scenario diversity

**Files**:
- `count-spikes.sh` - Daily spike counter
- `spike-progress.md` - Running log

---

### ⏳ Step 6: Confirmation-Gate Logic - PENDING

**Goal**: Implement two-consecutive-forecast confirmation (Phase 8 prerequisite)

**Requirements**:
- Spike must be predicted in 2 consecutive forecasts
- Reduces false positives
- Ready for HPA integration

**Can work on in parallel** while Steps 3-5 run unattended

**Files to create**:
- `confirmation_gate.py` - Two-forecast logic
- `test_confirmation_gate.py` - Unit tests

---

### ⏳ Step 7: Report Results Separately - PENDING

**Goal**: Present training/synthetic vs real-Kubernetes results separately

**Tables for paper**:

**Table 1: Training/Synthetic Performance**
- Dataset: Synthetic + training data
- Samples: X
- Precision/Recall/F1

**Table 2: Real Kubernetes Validation**  
- Dataset: Historical + multi-scenario
- Samples: ~135,000
- Spike events: 100-200
- Precision/Recall/F1

**Files**:
- `generate-paper-tables.py`
- LaTeX table templates

---

## Current Status

**Completed**: Steps 1-2 ✅  
**Next Action**: Step 3 - Create multi-scenario workload generator  
**Parallel Work**: Can start Step 6 (confirmation gate) now

---

## Timeline Estimate

| Step | Duration | Status |
|------|----------|--------|
| 1. Check retention | 5 min | ✅ Done |
| 2. Pull history | 10 min | ✅ Done |
| 3. Multi-scenario workloads | 1 hour setup | ➡️ Next |
| 4. Run prediction service | 5-7 days | ⏳ Pending |
| 5. Track spikes | Ongoing | ⏳ Pending |
| 6. Confirmation gate | 2-3 hours | ⏳ Can start now |
| 7. Paper tables | 1 hour | ⏳ After data collection |

**Total**: ~1 week for complete validation with 100-200 real spike events

---

## Key Decisions Made

1. ✅ **Target shift**: From "200k samples" to "100-200 spike events"
2. ✅ **Use real data first**: 53 historical spikes already collected
3. ✅ **Multi-scenario approach**: Diverse patterns, not just volume
4. ✅ **Keep native 20s interval**: Don't compress prediction timing
5. ✅ **Separate reporting**: Training vs production results

---

## Success Criteria

**Minimum for paper**:
- ✅ 53 historical spikes (done)
- ⏳ 47+ new spikes from scenarios
- ⏳ 100+ total spike events
- ⏳ 5+ scenario types tested
- ⏳ Confirmation gate implemented

**Excellent for paper**:
- ✅ 53 historical spikes (done)
- ⏳ 147+ new spikes
- ⏳ 200 total spike events
- ⏳ All 6 scenario types
- ⏳ 5-7 days continuous operation

---

## Next Actions

**Immediate** (today):
1. Create multi-scenario workload generator (Step 3)
2. Start continuous prediction service (Step 4)

**This week**:
3. Implement confirmation gate (Step 6)
4. Monitor spike collection daily (Step 5)

**Next week**:
5. Analyze results
6. Generate paper tables (Step 7)

---

**Ready to proceed with Step 3!** 🚀
