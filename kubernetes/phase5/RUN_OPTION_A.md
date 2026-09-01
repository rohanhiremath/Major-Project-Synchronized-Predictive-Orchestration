# Option A: Complete Instructions

## 🎯 Goal
Collect 1 hour of PSI data WHILE workloads are running to get ~15-18% spike density.

## ⏱️ Timeline
- **Total time:** 90 minutes
- **Active collection:** 60 minutes
- **Setup:** 5 minutes
- **Analysis:** 5-10 minutes

---

## 🖥️ You'll Need 2 Terminal Windows

### Terminal 1: Workload Generation
### Terminal 2: Data Collection

**IMPORTANT:** Start Terminal 2 within 1-2 minutes of starting Terminal 1!

---

## 📋 Step-by-Step Instructions

### **Terminal 1: Start Workloads**

```bash
cd ~/Documents/major\ project/implementation/Major-Project-Synchronized-Predictive-Orchestration/kubernetes/phase4

# Start all workloads
./start-workloads.sh
```

**What you'll see:**
```
============================================================
PHASE 4: STARTING SYNTHETIC WORKLOAD GENERATION
============================================================

Checking prerequisites...
✅ Prerequisites checked

Measuring baseline PSI (10 seconds)...
   Baseline Memory PSI: 0.XXXX%

Step 1: Deploying CPU/Memory Stress Workloads
✅ Stress workloads deployed:
NAME                    COMPLETIONS   DURATION   AGE
stress-memory-burst     0/1           Xs         Xs
stress-cpu-burst        0/1           Xs         Xs
stress-combined-burst   0/1           Xs         Xs

Step 2: Deploying FIO I/O Stress Workloads
✅ FIO workloads deployed

Workloads are now generating PSI spikes!
```

**Leave this terminal running!**

---

### **Terminal 2: Start Data Collection** 🚨 DO THIS IMMEDIATELY

Open a NEW terminal and run:

```bash
cd ~/Documents/major\ project/implementation/Major-Project-Synchronized-Predictive-Orchestration/kubernetes/phase5

# Collect for 1 hour (3600 seconds)
python3 export-current-psi.py 3600
```

**What you'll see:**
```
============================================================
PHASE 5: LIVE PSI DATA COLLECTION
============================================================

🔍 Collecting PSI data from pods
   Duration: 3600s (60 minutes)
   Interval: 20s
   Expected samples: 180 per pod

Starting collection... (Ctrl+C to stop early)

[ 5.5%] Samples:   10 | Remaining: 3400s
[11.1%] Samples:   20 | Remaining: 3200s
[16.7%] Samples:   30 | Remaining: 2940s
...
```

**This will run for 60 minutes!** You'll see:
- Real-time progress updates every 20 seconds
- Sample count increasing
- Time remaining countdown

---

## ⏰ What Happens During Collection

```
Timeline of 60 minutes:

0-5 min:   Workloads starting, first spikes appearing
           PSI: 0.5% → 2-3% 🔴

5-15 min:  Memory stress bursts
           PSI: 3-8% 🔴 → 0.3% 🟢 → 5% 🔴

15-30 min: CPU stress + I/O bursts
           PSI: 1-4% 🔴 → 0.2% 🟢 → 6% 🔴

30-50 min: Combined stress patterns
           PSI: 2-10% 🔴 → 0.4% 🟢 → 7% 🔴

50-60 min: Final bursts completing
           PSI: 3-5% 🔴 → 0.3% 🟢

Result: ~15-18% of samples above 1.5% ✅
```

---

## ✅ When Collection Completes

After 60 minutes, you'll see:

```
[100.0%] Samples:  540 | Remaining:    0s

✅ Collection complete!
   Samples collected: 540
   File: kubernetes_psi_data/kubernetes_psi_live_TIMESTAMP.csv

Converting to rate (PSI percentage)...
✅ Rates calculated: kubernetes_psi_data/kubernetes_psi_rates_TIMESTAMP.csv

📊 Analysis:
   Total samples: 537
   Spikes (>1.5%): 85
   Spike density: 15.83% (target: ~16%)
   Status: ✅ GOOD
```

**This is what we want!** 15-18% spike density.

---

## 🎓 Tips While Waiting

### Check Progress in Terminal 1
You can check workload status:
```bash
kubectl get jobs -l workload-type
```

Should show jobs running with 0/1 completions.

### Monitor PSI in Real-Time (Optional)
Open a 3rd terminal:
```bash
cd kubernetes/phase4
./monitor-simple.sh
```

This shows live PSI metrics from pods.

### Take a Break
- 60 minutes is long enough for a coffee break ☕
- The scripts will run automatically
- You can check progress anytime

---

## 🎯 After Collection Completes

You'll have two CSV files:

1. **`kubernetes_psi_live_TIMESTAMP.csv`**
   - Raw PSI counter values
   - Used for rate calculation

2. **`kubernetes_psi_rates_TIMESTAMP.csv`** ⭐ **USE THIS ONE**
   - PSI percentages (0-10%)
   - Format matches training data
   - Ready for model evaluation

---

## 📊 Next: Model Evaluation

Once collection is done, I'll help you:

1. **Load the CSV data**
2. **Run model predictions** using your trained model
3. **Compare predicted vs actual spikes**
4. **Calculate metrics:**
   - Recall: Did model catch the spikes?
   - Precision: Were predictions accurate?
   - F1 Score: Overall performance

Expected result: ~94% recall (matching training performance)

---

## ⚠️ What If Something Goes Wrong?

### Collection Crashes
```bash
# Restart collection
cd kubernetes/phase5
python3 export-current-psi.py 3600
```
It will create a new file, you can combine data later if needed.

### Workloads Fail
```bash
# Check status
kubectl get jobs -l workload-type
kubectl logs <job-name>

# Restart specific job
kubectl delete job <job-name>
kubectl apply -f kubernetes/phase4/workload-stress.yaml
```

### Want to Stop Early
Press `Ctrl+C` in Terminal 2
- Partial data will be saved
- Can still use if you have 20+ minutes (enough samples)

---

## 🚦 Ready to Start?

**In Terminal 1:**
```bash
cd ~/Documents/major\ project/implementation/Major-Project-Synchronized-Predictive-Orchestration/kubernetes/phase4
./start-workloads.sh
```

**Then IMMEDIATELY in Terminal 2:**
```bash
cd ~/Documents/major\ project/implementation/Major-Project-Synchronized-Predictive-Orchestration/kubernetes/phase5
python3 export-current-psi.py 3600
```

**Come back in 60 minutes!** ⏰

---

## 📞 Tell Me When Done

When the 60 minutes are up and you see the analysis with spike density, let me know:
- What spike density you got (target: 15-18%)
- File name of the `kubernetes_psi_rates_*.csv`

Then I'll guide you through model evaluation!

Good luck! 🚀
