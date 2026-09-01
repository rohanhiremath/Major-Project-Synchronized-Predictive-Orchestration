# Project Cleanup and Organization Plan

## Files Analysis

### ✅ KEEP - Essential Files

#### Root Documentation
- `README.md` - Main project readme (needs update)
- `PROJECT_SUMMARY.md` - Comprehensive project overview (needs update)
- `requirements.txt` - Python dependencies
- `.gitignore` - Git configuration
- `LICENSE` - License file

#### Source Code (src/)
- `train_tft.py` - Original model training (KEEP - baseline)
- `predict_tft.py` - Original prediction script (UPDATE threshold)
- `generate_server_data.py` - Synthetic data generation (KEEP)
- `create_train_val_test.py` - Data splitting (KEEP)
- `visualize.py` - Visualization utilities (KEEP)

#### Models
- `models/tft_psi_model.ckpt` - **PRODUCTION MODEL** (200KB)
- `models/tft-psi-epoch=05-val_loss=1.9868.ckpt` - Training checkpoint (KEEP for reference)

#### Data (Essential)
- `data/train.csv` - Training data (6.9MB)
- `data/validation.csv` - Validation data (867KB)
- `data/test.csv` - Test data (870KB)
- `data/test_kubernetes.csv` - **K8s validation data** (107KB) - KEEP!

#### Phase 5 (Kubernetes Validation)
- `kubernetes/phase5/run_prediction_k8s.py` - **Main validation script**
- `kubernetes/phase5/preprocess_k8s_data.py` - K8s data preprocessing
- `kubernetes/phase5/kubernetes_psi_data/` - Collected K8s metrics
- `kubernetes/phase5/PRECISION_OPTIMIZATION_FINAL.md` - **Final report**
- `kubernetes/phase5/threshold_optimization.png` - Visualization
- `kubernetes/phase5/optimal_config.txt` - Production config

---

### 🗑️ DELETE - Redundant/Outdated Files

#### Root - Outdated Documentation
- `CURRENT_STATUS.md` - Outdated, superseded by PROJECT_SUMMARY.md
- `IMPROVEMENTS_SUMMARY.md` - Outdated, covered in final reports
- `TIER_IMPROVEMENTS_REPORT.md` - Outdated, model finalized

#### Src - Redundant/Experimental
- `train_tft_improved.py` - Experimental, not used for production model
- `predict_tft_improved.py` - Experimental, not used for production
- `compare_models.py` - One-time comparison, no longer needed
- `create_tft_dataset.py` - Superseded by create_train_val_test.py
- `preprocess.py` - Generic, superseded by specific scripts
- `split_data.py` - Superseded by create_train_val_test.py
- `inspect_data.py` - One-time use, no longer needed

#### Data - Redundant/Old Datasets
- `processed_ptcs.csv` - Old dataset, not used
- `processed_server_telemetry.csv` - Raw data, train/val/test extracted
- `ptcs_dataset2_full_psi.csv` - Old dataset
- `ptcs_dataset_full_psi.csv` - Old dataset  
- `ptcs_training_data_full_psi.csv` - Old dataset
- `server_telemetry_1day_20s.csv` - Raw data, train/val/test extracted
- `tft_predictions.csv` - Old predictions from original model (7.4MB)
- `tft_predictions_improved.csv` - Experimental predictions (47MB!)
- `tft_prediction_plot.png` - Old visualization

#### Phase 5 - Redundant Reports/Scripts
- `PHASE5_COMPLETE.md` - Interim report, superseded
- `FINAL_RESULTS.md` - Interim report, superseded
- `OPTIMIZED_RESULTS.md` - Interim report, superseded
- `PREDICTION_RESULTS.txt` - Console log, not needed
- `FINAL_OPTIMIZED_RESULTS.txt` - Console log, not needed
- `THRESHOLD_OPTIMIZATION.txt` - Console log, not needed
- `prediction_results.log` - Old log
- `run-model-prediction.py` - Early version, superseded
- `optimize_threshold.py` - Basic version, superseded
- `optimize_threshold_advanced.py` - Script used, but not needed after optimization
- `evaluate-model.py` - One-time analysis script
- `export-psi-data.py` - Old export script (Prometheus)
- `DATA_EXPORT_FIX.md` - Troubleshooting doc, issue resolved
- `QUICKSTART.md` - Old instructions
- `RUN_OPTION_A.md` - Old instructions
- `optimal_threshold.txt` - Superseded by optimal_config.txt
- `threshold_analysis.csv` - Raw analysis data, info in report

#### Models - Redundant
- `tft_psi_model_improved.ckpt` - Experimental model (2.7MB), production uses original

---

### 🔄 UPDATE - Files Needing Updates

#### Root
- `README.md` - Update with final project structure and results
- `PROJECT_SUMMARY.md` - Update with Phase 5 completion and optimized threshold

#### Src
- `predict_tft.py` - Update SPIKE_THRESHOLD from 2.0 to 1.80
- `train_tft.py` - Add comments about production model

---

## Cleanup Actions

### Step 1: Delete Outdated Root Documentation
```bash
rm CURRENT_STATUS.md
rm IMPROVEMENTS_SUMMARY.md
rm TIER_IMPROVEMENTS_REPORT.md
```

### Step 2: Clean Src Directory
```bash
cd src
rm train_tft_improved.py
rm predict_tft_improved.py
rm compare_models.py
rm create_tft_dataset.py
rm preprocess.py
rm split_data.py
rm inspect_data.py
```

### Step 3: Clean Data Directory
```bash
cd data
rm processed_ptcs.csv
rm processed_server_telemetry.csv
rm ptcs_dataset2_full_psi.csv
rm ptcs_dataset_full_psi.csv
rm ptcs_training_data_full_psi.csv
rm server_telemetry_1day_20s.csv
rm tft_predictions.csv
rm tft_predictions_improved.csv
rm tft_prediction_plot.png
```

### Step 4: Clean Phase 5
```bash
cd kubernetes/phase5
rm PHASE5_COMPLETE.md
rm FINAL_RESULTS.md
rm OPTIMIZED_RESULTS.md
rm PREDICTION_RESULTS.txt
rm FINAL_OPTIMIZED_RESULTS.txt
rm THRESHOLD_OPTIMIZATION.txt
rm prediction_results.log
rm run-model-prediction.py
rm optimize_threshold.py
rm optimize_threshold_advanced.py
rm evaluate-model.py
rm export-psi-data.py
rm DATA_EXPORT_FIX.md
rm QUICKSTART.md
rm RUN_OPTION_A.md
rm optimal_threshold.txt
rm threshold_analysis.csv
```

### Step 5: Clean Models
```bash
cd models
rm tft_psi_model_improved.ckpt
```

---

## Final Structure

```
Major-Project-Synchronized-Predictive-Orchestration/
├── README.md                          ← Updated
├── PROJECT_SUMMARY.md                 ← Updated
├── requirements.txt
├── LICENSE
├── .gitignore
│
├── src/
│   ├── generate_server_data.py        ← Data generation
│   ├── create_train_val_test.py       ← Data splitting
│   ├── train_tft.py                   ← Model training
│   ├── predict_tft.py                 ← Prediction (updated threshold)
│   └── visualize.py                   ← Visualization
│
├── data/
│   ├── train.csv                      ← Training data (6.9MB)
│   ├── validation.csv                 ← Validation data (867KB)
│   ├── test.csv                       ← Test data (870KB)
│   └── test_kubernetes.csv            ← K8s validation (107KB)
│
├── models/
│   ├── tft_psi_model.ckpt            ← Production model (200KB)
│   └── tft-psi-epoch=05-val_loss=1.9868.ckpt  ← Training checkpoint
│
├── kubernetes/
│   ├── PHASE_STATUS.md
│   ├── phase2/                        ← Deployment manifests
│   ├── phase3/                        ← Validation scripts
│   ├── phase4/                        ← Workload generation
│   └── phase5/
│       ├── export-current-psi.py      ← Data collection
│       ├── preprocess_k8s_data.py     ← Data preprocessing
│       ├── run_prediction_k8s.py      ← Validation script
│       ├── PRECISION_OPTIMIZATION_FINAL.md  ← Final report
│       ├── threshold_optimization.png
│       ├── optimal_config.txt
│       └── kubernetes_psi_data/       ← Collected metrics
│
└── results/                           ← Visualization outputs
    ├── cpu_usage.png
    ├── memory_usage.png
    ├── psi_*.png
    └── *_bytes_per_sec.png
```

---

## Estimated Space Savings

| Category | Before | After | Savings |
|----------|--------|-------|---------|
| Data files | ~70MB | ~8.8MB | **~61MB** |
| Models | ~3MB | ~575KB | **~2.4MB** |
| Scripts | ~100KB | ~40KB | **~60KB** |
| Docs | ~40KB | ~20KB | **~20KB** |
| **Total** | **~73MB** | **~9.4MB** | **~64MB (87%)** |

---

## Post-Cleanup Verification

After cleanup, verify:
1. Training pipeline works: `python src/train_tft.py`
2. Prediction works: `python src/predict_tft.py`
3. K8s validation works: `python kubernetes/phase5/run_prediction_k8s.py`
4. Documentation is current
5. No broken references

---

## Notes

- All deleted files can be recovered from git history if needed
- Keep `.gitignore` updated to prevent committing large data files
- Consider adding data/ to .gitignore except for small test samples
- Archive old models if disk space is constrained
