# Execute 7-Step Plan - Complete Guide

**Status**: Steps 1-2 ✅ Complete | Steps 3-7 Ready to Execute

---

## Quick Summary

| Step | Status | Description | Duration |
|------|--------|-------------|----------|
| 1 | ✅ Done | Check Prometheus retention | 5 min |
| 2 | ✅ Done | Pull historical spikes (53 events!) | 10 min |
| 3 | 📝 Ready | Multi-scenario workload generation | 5 days |
| 4 | 📝 Ready | Continuous prediction service | 5 days (parallel) |
| 5 | 📝 Ready | Daily spike counting | 5 min/day |
| 6 | ✅ Done | Confirmation gate implementation | Complete |
| 7 | 📝 Ready | Results analysis & paper tables | 30 min |

**Timeline**: 5-7 days for complete validation with 100-200 spike events

---

## Current Progress

✅ **Step 1**: Retention window = 11 days  
✅ **Step 2**: Collected 26,830 samples + **53 historical spikes**  
✅ **Step 6**: Confirmation gate implemented & tested  

**Ready to start**: Steps 3, 4, 5, 7

---

## How to Execute Steps 3-7

### Step 3: Multi-Scenario Workload Generation

**Purpose**: Generate diverse PSI spike patterns

**Command**:
```bash
cd /home/kesavan-p/Documents/major\ project/implementation/Major-Project-Synchronized-Predictive-Orchestration/kubernetes/phase6

# Run in tmux for reliability
tmux new -s workload-scenarios

# Start 5-day multi-scenario workload
./multi-scenario-workload.sh 120

# Detach: Ctrl+B then D
# Reattach: tmux attach -t workload-scenarios
```

**What it does**:
- Cycles through 6 scenario types every 4 hours
- Scenarios: Step, Ramp, Periodic, Sustained, Flash, Mixed
- Generates diverse PSI patterns automatically
- Logs everything to `workload-logs-*/`

**Scenarios explained**:
1. **Step**: Gradual increase (Low → Medium → High)
2. **Ramp**: Linear increase (10% → 90%)
3. **Periodic**: Repeated bursts (5min on, 5min off)
4. **Sustained**: Constant high load (75%)
5. **Flash**: Random sudden spikes
6. **Mixed**: Chaotic combination

---

### Step 4: Continuous Prediction Service

**Purpose**: Run service at native 20s interval for days

**Command** (in **SEPARATE terminal/tmux session**):
```bash
cd /home/kesavan-p/Documents/major\ project/implementation/Major-Project-Synchronized-Predictive-Orchestration/kubernetes/phase6

# Run in separate tmux session
tmux new -s prediction-service

# Start 5-day continuous prediction
./run-continuous-prediction-service.sh 5

# Detach: Ctrl+B then D
# Reattach: tmux attach -t prediction-service
```

**What it does**:
- Predicts every 20 seconds (native interval)
- Logs all predictions to `prediction-logs-*/`
- Auto-restarts on failures
- Runs in shadow mode (logging only)
- Monitors health every 5 minutes

**Expected output**:
- ~21,600 predictions per day
- 5 days = ~108,000 predictions
- Combined with historical: ~135,000 total samples

---

### Step 5: Track Spike Count Daily

**Purpose**: Monitor progress toward 100-200 spike target

**Command** (run daily):
```bash
cd /home/kesavan-p/Documents/major\ project/implementation/Major-Project-Synchronized-Predictive-Orchestration/kubernetes/phase6

./count-spikes.sh
```

**Output example**:
```
Historical (Step 2):  53
New (Step 4):         47
─────────────────────────
TOTAL:                100

Progress: [████████████████████████░░] 50%

✅ SUCCESS: Target reached!
```

**When to check**:
- Day 1: After 24 hours
- Day 2: Check progress
- Day 3: Check progress  
- Day 4: Check progress
- Day 5: Final check

**Stop conditions**:
- ✅ 100+ spikes: Minimum target reached
- ✅ 200 spikes: Excellent target reached
- ⏳ <100 spikes: Keep running

---

### Step 6: Confirmation Gate (Already Done ✅)

**Purpose**: Two-consecutive-forecast logic for HPA

**Status**: ✅ Implemented and tested

**File**: `confirmation_gate.py`

**Test it**:
```bash
python3 confirmation_gate.py
```

**Key features**:
- Requires 2 consecutive spike predictions
- Reduces false positives
- 60-second confirmation window
- Ready for Phase 8 HPA integration

---

### Step 7: Analyze Results & Generate Paper Tables

**Purpose**: Combine all data and generate LaTeX tables

**Command** (after Steps 3-4 complete):
```bash
cd /home/kesavan-p/Documents/major\ project/implementation/Major-Project-Synchronized-Predictive-Orchestration/kubernetes/phase6

./analyze-all-results.sh
```

**What it generates**:
1. `combined_summary.json` - All statistics
2. `table1_dataset_overview.tex` - LaTeX table
3. `table2_validation_results.tex` - LaTeX table  
4. `paper_snippets.txt` - Ready-to-use text
5. Combined prediction logs
6. Spike event details

**Output directory**: `final-results-YYYYMMDD_HHMMSS/`

---

## Monitoring During Execution

### Check Workload Status (Step 3)
```bash
# Check which scenario is running
tmux attach -t workload-scenarios

# Or check logs
tail -f workload-logs-*/workload-execution.log
```

### Check Prediction Service (Step 4)
```bash
# Check service
tmux attach -t prediction-service

# Or check logs
tail -f prediction-logs-*/predictions.log

# Check health
tail -f prediction-logs-*/health.log
```

### Check Overall Progress (Step 5)
```bash
# Quick check
./count-spikes.sh

# Detailed pod status
kubectl top pods -l app=workload

# Prometheus connectivity
curl http://localhost:9090/-/healthy
```

---

## Timeline & Milestones

### Day 0 (Setup)
- ✅ Steps 1-2 complete (historical data)
- ✅ Step 6 complete (confirmation gate)
- ▶️ Start Steps 3 & 4 (parallel)

### Day 1
- Check spike count: Expected ~53 + 10-20 = 63-73 spikes
- Verify services running
- Check logs for errors

### Day 2-3
- Check spike count daily
- Expected: 80-100 spikes
- Monitor workload scenarios cycling

### Day 4-5
- Check spike count daily
- Expected: 100-150 spikes
- Prepare for completion

### Day 5-6 (Completion)
- Final spike count: 100-200 spikes
- Stop services (Ctrl+C in tmux sessions)
- Run Step 7: `./analyze-all-results.sh`
- Review generated tables and text

---

## Success Criteria

### Minimum (Paper Acceptable)
- ✅ 53 historical spikes (done!)
- ⏳ 47+ new spikes
- ⏳ 100+ total spike events
- ⏳ 50k+ total samples
- ⏳ 5+ scenario types tested

### Target (Strong Paper)
- ✅ 53 historical spikes (done!)
- ⏳ 100+ new spikes
- ⏳ 150+ total spike events
- ⏳ 100k+ total samples
- ⏳ All 6 scenarios tested

### Excellent (Top-Tier)
- ✅ 53 historical spikes (done!)
- ⏳ 147+ new spikes
- ⏳ 200 total spike events
- ⏳ 135k+ total samples
- ⏳ 5 days continuous operation

---

## Troubleshooting

### Services Not Starting
```bash
# Check prerequisites
kubectl get pods -l app=workload  # Should show 3 pods
kubectl get -n monitoring svc/prometheus-operated  # Should exist
ls -la models/tft_psi_model.ckpt  # Should exist
ls -la .venv/bin/python  # Should exist
```

### No Spikes Generated
```bash
# Check if workload is actually running
kubectl top pods -l app=workload

# Should show high CPU/memory
# If low, check workload logs:
tail -100 workload-logs-*/workload-execution.log
```

### Prediction Service Crashing
```bash
# Check logs
tail -100 prediction-logs-*/predictions.log

# Common issues:
# 1. Port 9090 already in use → pkill -f port-forward
# 2. Model not found → check MODEL_PATH
# 3. Out of memory → service uses ~700MB
```

### Spike Count Not Increasing
```bash
# Verify predictions are happening
tail prediction-logs-*/predictions.log | grep "Iteration"

# Verify PSI is actually spiking
# (Prometheus query)
curl 'http://localhost:9090/api/v1/query?query=deriv(node_pressure_memory_waiting_seconds_total[2m])*100'
```

---

## Files Created

### Step 3
- ✅ `multi-scenario-workload.sh` - Workload orchestration
- Logs: `workload-logs-*/`

### Step 4  
- ✅ `run-continuous-prediction-service.sh` - Continuous service
- Logs: `prediction-logs-*/`

### Step 5
- ✅ `count-spikes.sh` - Progress tracker
- Log: `spike-progress.txt`

### Step 6
- ✅ `confirmation_gate.py` - Two-forecast logic
- Tested and working

### Step 7
- ✅ `analyze-all-results.sh` - Results analysis
- Output: `final-results-*/`

---

## Quick Start Commands

**Start everything** (in 3 terminals):

**Terminal 1** - Workload Generation:
```bash
cd /home/kesavan-p/Documents/major\ project/implementation/Major-Project-Synchronized-Predictive-Orchestration/kubernetes/phase6
tmux new -s workload-scenarios
./multi-scenario-workload.sh 120
```

**Terminal 2** - Prediction Service:
```bash
cd /home/kesavan-p/Documents/major\ project/implementation/Major-Project-Synchronized-Predictive-Orchestration/kubernetes/phase6
tmux new -s prediction-service
./run-continuous-prediction-service.sh 5
```

**Terminal 3** - Daily Monitoring:
```bash
cd /home/kesavan-p/Documents/major\ project/implementation/Major-Project-Synchronized-Predictive-Orchestration/kubernetes/phase6
watch -n 3600 ./count-spikes.sh  # Every hour
```

**Come back in 5 days, run**:
```bash
./analyze-all-results.sh
```

---

## What You'll Have for Paper

After 5 days:
- ✅ 100-200 spike events (strong validation)
- ✅ ~135,000 predictions (statistical significance)
- ✅ 6 diverse scenario types (generalization)
- ✅ Real historical + controlled new data
- ✅ LaTeX tables ready for paper
- ✅ Text snippets for manuscript
- ✅ Confirmation gate for HPA (Phase 8)

**This is publication-quality validation!** 🎉

---

**Ready to start?** Execute Steps 3 & 4 in parallel, monitor with Step 5!
