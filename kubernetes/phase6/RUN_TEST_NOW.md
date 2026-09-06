# 🚀 START 24-HOUR TEST NOW

**Everything is ready. Follow these 3 steps:**

---

## Step 1: Pre-Flight Check (2 minutes)

```bash
cd /home/kesavan-p/Documents/major\ project/implementation/Major-Project-Synchronized-Predictive-Orchestration/kubernetes/phase6

./test-spike-generation.sh
```

**✅ PASS**: If you see PSI increase above 1.80%  
**❌ FAIL**: If PSI stays at 0% → Debug before continuing

---

## Step 2: Start 24-Hour Test (1 minute)

```bash
# Optional: Use tmux so test continues if SSH disconnects
tmux new -s phase6-test

# Start the test
./run-24hour-test.sh
```

**What happens**:
- Test runs for 24 hours automatically
- Generates ~180 spike cycles
- Logs everything to `test-results-YYYYMMDD_HHMMSS/`
- Auto-restarts services if they crash
- Prints progress every cycle

**To detach from tmux**: Press `Ctrl+B`, then press `D`  
**To reattach later**: `tmux attach -t phase6-test`

---

## Step 3: Monitor Progress (Optional)

**In a SEPARATE terminal**:

```bash
cd /home/kesavan-p/Documents/major\ project/implementation/Major-Project-Synchronized-Predictive-Orchestration/kubernetes/phase6

./monitor-24hour-test.sh
```

**Shows**:
- Real-time prediction count
- Spikes detected
- Progress to 50-spike target
- System health

**Press Ctrl+C to stop monitoring** (test keeps running)

---

## ⏰ Come Back in 24 Hours

After 24 hours, analyze results:

```bash
cd /home/kesavan-p/Documents/major\ project/implementation/Major-Project-Synchronized-Predictive-Orchestration/kubernetes/phase6

# Find your test results
ls -lt test-results-*/

# Analyze (replace with your test directory)
./analyze-results.py test-results-YYYYMMDD_HHMMSS/
```

---

## 📊 Expected Results for Paper

- **Total Predictions**: ~4,320
- **Spikes Detected**: 50-180 
- **Precision**: >90%
- **Recall**: >95%
- **F1 Score**: >92%

---

## 🆘 Quick Troubleshooting

**Test stopped?**
```bash
tail -100 test-results-*/test-execution.log
```

**No spikes?**
```bash
# Check if services are running
ps aux | grep prediction_service
ps aux | grep port-forward

# Check recent predictions
tail -50 test-results-*/prediction-service.log
```

**Need help?**
- Read: `24HOUR_TEST_GUIDE.md` (detailed)
- Read: `QUICK_START_24HOUR.md` (quick reference)

---

## ✅ That's It!

**Run step 1, then step 2. Come back in 24 hours.**

**Good luck with your paper! 🎉**
