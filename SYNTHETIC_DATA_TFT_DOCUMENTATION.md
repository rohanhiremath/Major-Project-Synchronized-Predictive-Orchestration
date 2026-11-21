# Synthetic PSI Data & TFT Model - Comprehensive Documentation

## Overview

This documentation covers the synthetic 7-day PSI dataset and the TemporalFusionTransformer (TFT) model trained to predict I/O pressure spikes. The system includes data generation, model training, and prediction evaluation with spike detection capabilities.

---

## Part 1: Synthetic Data Generation

### Data Generation Script
**Location:** `src/generate_psi_7d.py`

### Features

#### 1. Time Axis and Resolution
- **Duration:** 7 days (2026-08-21 to 2026-08-27)
- **Sampling Interval:** 15 seconds
- **Total Points per Series:** 40,320 rows
- **Number of Series:** 3 (node-a, node-b, node-c)
- **Total Dataset Rows:** 120,249

#### 2. Node Configuration
| Node | Workload Type | Baseline | Noise Level | Spike Intensity |
|------|---------------|----------|-------------|-----------------|
| node-a | db | 0.05-0.12 | 0.003-0.008 | 0.8-1.2 |
| node-b | batch | 0.05-0.12 | 0.003-0.008 | 0.8-1.2 |
| node-c | web | 0.05-0.12 | 0.003-0.008 | 0.8-1.2 |

#### 3. Event Types (Intentional Variability)

**a) Learnable Spikes (40%)**
- Scheduled backups, hourly crons
- Same hour daily, ±5 min jitter
- ±30% magnitude variation
- 5-15 min duration
- Makes pattern learning possible

**b) Precursor Spikes (25%)**
- Queue depth rises before PSI crosses threshold
- 10-30 min ramp + decay
- Partially learnable if patterns repeat
- Enables lead-indicator learning

**c) Unpredictable Spikes (20%)**
- Sudden onset, no precursor
- Random timing, random magnitude
- Sharp exponential decay
- **Makes 100% recall impossible by design**

**d) Near-Miss Events (15%)**
- Ramps that peak at 1.2-1.9 PSI
- Never cross 2.0 threshold
- Look-alike patterns
- **Cause false positives**

**e) Magnitude Variance**
- Log-normal distribution (median ~2.6 PSI, tails to ~8.0)
- Some spikes barely cross 2.0
- Others reach extreme values

#### 4. Data Quality Features
- **Noise:** Heteroscedastic Gaussian (std ~0.1)
- **Sensor Dropouts:** 0.3% of rows (forward-filled, marked)
- **Outliers:** 0.1% of rows
- **Distribution Shift:** Days 6-7 include:
  - +10-15% baseline shift
  - New periodic job (non-hourly)
  - 20-40 min plateau spikes
  - Workload mix change

### Column Definitions

#### Target Variable
- **psi_io_some_avg10:** 10-second EWMA of I/O stall fraction (primary prediction target)

#### PSI Metrics (Time-Varying Unknown Reals)
- `psi_io_some_avg10`, `psi_io_some_avg60`, `psi_io_some_avg300` - "some" pressure
- `psi_io_full_avg10`, `psi_io_full_avg60`, `psi_io_full_avg300` - "full" pressure (65% of "some")
- `psi_io_some_total_us` - Cumulative stall time in microseconds

#### I/O Metrics (Time-Varying Unknown Reals)
- `disk_iops` - I/O operations per second (0-5000)
- `disk_queue_depth` - Queue depth with 5-step lag vs PSI (0-100)
- `io_wait_pct` - CPU time waiting for I/O (0-100%)
- `p95_latency_ms` - P95 request latency (1-50+ ms)

#### Compute Metrics (Time-Varying Unknown Reals)
- `cpu_util_pct` - CPU utilization (0-100%)
- `pod_count` - Running pod count (1-100)

#### Time Features (Time-Varying Known Reals)
- `hour_of_day` - Hour of day [0, 23]
- `day_of_week` - Day of week [0, 6] (Monday=0)
- `minute_sin` - sin(2π × minute / 1440)
- `minute_cos` - cos(2π × minute / 1440)
- `is_business_hours` - 1 if 8am-6pm, else 0
- `is_maintenance_window` - 1 if 2am-4am, else 0

#### Static Categoricals
- `node_id` - "node-a", "node-b", "node-c"
- `workload_type` - "db", "batch", "web"

#### Auxiliary Columns
- `timestamp` - ISO datetime
- `time_idx` - Contiguous integer per node per split (reset per split)
- `group_id` - Group identifier (same as node_id)
- `sensor_imputed` - 1 if forward-filled from dropout, else 0

### Data Split Strategy

**Chronological splits with gap insertion (prevents window overlap):**

| Split | Rows | Days | Spikes | Events | Purpose |
|-------|------|------|--------|--------|---------|
| Train | 77,763 | Days 1-4 + 12h of day 5 | 5,535 (7.1%) | 1,202 | Model learning |
| Val | 8,283 | Remainder of day 5 | 612 (7.4%) | 122 | Early stopping |
| Test | 34,200 | Days 6-7 | 2,346 (6.9%) | 519 | Final evaluation |

**Gap Design:** 120 timesteps (30 minutes) between splits
- Prevents encoder context from accessing data across split boundaries
- Ensures no information leakage during prediction

### Generation Command

```bash
# Generate with default settings (seed=42)
python3 src/generate_psi_7d.py

# Generate with custom parameters
python3 src/generate_psi_7d.py \
  --seed 99 \
  --step-seconds 15 \
  --max-encoder-length 96 \
  --max-prediction-length 24
```

### Output Files
- `data/synthetic/train.csv` - Training split
- `data/synthetic/val.csv` - Validation split
- `data/synthetic/test.csv` - Test split
- `data/synthetic/psi_7d_full.csv` - Complete 7-day dataset
- `data/synthetic/metadata.json` - Column roles and statistics
- `data/synthetic/psi_7d_visualization.png` - 7-day plot with splits

---

## Part 2: Sample Data

### Training Data (First 5 Rows)

```csv
timestamp,node_id,workload_type,disk_iops,disk_queue_depth,io_wait_pct,cpu_util_pct,pod_count,p95_latency_ms,psi_io_some_avg10,psi_io_some_avg60,psi_io_some_avg300,psi_io_full_avg10,psi_io_full_avg60,psi_io_full_avg300,psi_io_some_total_us,hour_of_day,day_of_week,minute_sin,minute_cos,is_business_hours,is_maintenance_window,sensor_imputed,group_id,time_idx
2026-08-21 00:00:00,node-a,db,604.488,2.5095525,12.266596,22.041325,15,16.669847,0.40022737,0.41214865,0.41214865,0.29891217,0.24955437,0.23749122,2472892.0,0,4,0.0,1.0,0,0,0,node-a,0
2026-08-21 00:00:15,node-a,db,655.3837,0.0,9.994319,19.67168,20,15.251125,0.39338914,0.40916562,0.41149095,0.24483855,0.24324773,0.2442411,4864869.5,0,4,0.0,1.0,0,0,0,node-a,1
2026-08-21 00:00:30,node-a,db,666.5055,0.0,8.6793375,26.375345,14,17.82983,0.5126123,0.41319677,0.41215398,0.33521512,0.24637994,0.24522898,7289251.5,0,4,0.0,1.0,0,0,0,node-a,2
2026-08-21 00:00:45,node-a,db,535.3448,2.4777153,12.239021,18.672712,17,14.439314,0.29353762,0.40019565,0.41141367,0.19001547,0.24548055,0.24519638,9000833.0,0,4,0.0,1.0,0,0,0,node-a,3
2026-08-21 00:01:00,node-a,db,1052.7836,0.0,10.64059,20.111853,17,16.069323,0.40223414,0.39890605,0.41085303,0.26145322,0.24423837,0.2448547,11800833.0,0,4,0.0,1.0,0,0,0,node-a,4
```

### Test Data (First 5 Rows)

```csv
timestamp,node_id,workload_type,disk_iops,disk_queue_depth,io_wait_pct,cpu_util_pct,pod_count,p95_latency_ms,psi_io_some_avg10,psi_io_some_avg60,psi_io_some_avg300,psi_io_full_avg10,psi_io_full_avg60,psi_io_full_avg300,psi_io_some_total_us,hour_of_day,day_of_week,minute_sin,minute_cos,is_business_hours,is_maintenance_window,sensor_imputed,group_id,time_idx
2026-08-26 00:30:00,node-a,db,0.0,0.0,0.0,12.303701,12,11.271356,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0,2,0.0,1.0,0,0,0,node-a,0
2026-08-26 00:30:15,node-a,db,0.0,5.7788706,0.6824806,11.896401,9,12.700385,0.14513086,0.10199405,0.06843737,0.09433909,0.06629614,0.04448379,2177 964.0,0,2,0.0,1.0,0,0,0,node-a,1
2026-08-26 00:30:30,node-a,db,0.0,0.0,0.0,12.357334,9,9.82575,0.016340887,0.079766936,0.055022863,0.010621577,0.051848406,0.0357649,2177964.0,0,2,0.0,1.0,0,0,0,node-a,2
2026-08-26 00:30:45,node-a,db,0.0,0.0,0.0,15.190047,16,12.148915,0.16707665,0.10090821,0.062101003,0.10860244,0.06559034,0.04036152,2177964.0,0,2,0.0,1.0,0,0,0,node-a,3
2026-08-26 00:31:00,node-a,db,291.10336,0.0,4.1051483,12.728597,9,9.394919,0.0,0.083786435,0.062101003,0.0,0.054511283,0.04036152,2468 964.0,0,2,0.0,1.0,0,0,0,node-a,4
```

---

## Part 3: TFT Model Training & Prediction

### Training Script
**Location:** `src/train_tft.py` (original) or `src/train_predict_synthetic.py` (adapted)

### Model Architecture

| Component | Value |
|-----------|-------|
| Hidden Size | 16 |
| Attention Heads | 2 |
| Dropout | 0.1 |
| Quantiles | (0.1, 0.5, 0.9) |
| Loss Function | QuantileLoss |
| Optimizer | Adam (lr=0.001) |
| Max Epochs | 10 |
| Early Stopping Patience | 3 |

### Training Configuration

```python
MAX_ENCODER_LENGTH = 96      # 24 min history @ 15s interval
MAX_PREDICTION_LENGTH = 24   # 6 min forecast horizon
BATCH_SIZE = 32
LEARNING_RATE = 0.001
MAX_EPOCHS = 10
EARLY_STOPPING_PATIENCE = 3
```

### Training Process

1. **Data Loading:** Load train/val/test CSVs
2. **Dataset Creation:** Build TimeSeriesDataSet with:
   - Static categoricals: node_id, workload_type
   - Time-varying known: hour_of_day, day_of_week, minute_sin/cos, business_hours, maintenance_window
   - Time-varying unknown: disk_iops, disk_queue_depth, io_wait_pct, cpu_util_pct, p95_latency_ms, PSI metrics
3. **Model Instantiation:** Create TFT from dataset
4. **Training Loop:** Adam optimizer with gradient clipping
5. **Validation:** Check loss on val split every epoch
6. **Early Stopping:** Stop if val_loss doesn't improve for 3 epochs
7. **Checkpoint:** Save best model state

### Prediction Process

1. **Load Trained Model:** Restore state_dict from checkpoint
2. **Create Test Dataset:** Combine train+val+test for historical context
3. **Generate Predictions:** Run inference on test windows
4. **Extract Quantiles:** q10, q50 (median), q90
5. **Evaluate Metrics:** MAE, RMSE, quantile loss, spike detection

### Prediction Script
**Location:** `src/predict_tft.py` (auto-detects synthetic data)

**Auto-Detection Logic:**
- Checks if `data/synthetic/` exists
- If yes, loads synthetic data and uses synthetic config
- If no, falls back to original data and original config

---

## Part 4: Evaluation Results

### Metrics Calculated

#### Regression Metrics
- **MAE (Mean Absolute Error):** L1 distance between actual and predicted
- **RMSE (Root Mean Square Error):** L2 distance (penalizes outliers more)

#### Quantile Metrics
- **Pinball Loss (q10, q50, q90):** Asymmetric loss for each quantile
- **Coverage:** % of actual values within q10-q90 interval
- **Interval Width:** Average distance between q10 and q90

#### Spike Detection (Threshold = 2.0 PSI)
- **True Positives (TP):** Correctly predicted spikes
- **False Positives (FP):** Predicted spike where none occurred
- **False Negatives (FN):** Missed actual spikes
- **Precision:** TP / (TP + FP) — accuracy of spike predictions
- **Recall:** TP / (TP + FN) — coverage of actual spikes
- **F1 Score:** 2 × (Precision × Recall) / (Precision + Recall)

### Example Output Format

```
================================================================================
MODEL EVALUATION
================================================================================

Regression Metrics:
  MAE:  0.125432
  RMSE: 0.287654

Quantile Pinball Loss:
  q10: 0.043210
  q50: 0.087654
  q90: 0.065432

Prediction Coverage:
  q10-q90 coverage: 87.3%
  Average q10-q90 interval width: 0.654321

Spike Detection Performance (Threshold = 2.0 PSI):
  True Positives: 1847
  False Positives: 234
  False Negatives: 89
  Precision: 88.7%
  Recall: 95.4%
  F1 Score: 92.0%
```

### Expected Performance Targets

| Metric | Target Range | Rationale |
|--------|--------------|-----------|
| MAE | 0.05 - 0.20 | Captures typical PSI prediction error |
| RMSE | 0.10 - 0.35 | Slightly higher than MAE due to outliers |
| Precision | 70% - 95% | Realistic given unpredictable spikes |
| Recall | 70% - 95% | ~20% of spikes are intentionally unpredictable |
| F1 Score | 70% - 92% | Harmonic mean of precision & recall |
| Coverage | 85% - 95% | q10-q90 should contain most actual values |

### Why Performance is Imperfect (By Design)

1. **Unpredictable Spikes (20%):** No precursor → model must miss some
2. **Near-Miss Events (15%):** Look like spikes but don't cross threshold → false alarms
3. **Magnitude Variance:** Some spikes barely cross 2.0 → borderline predictions
4. **Distribution Shift (Test):** Days 6-7 introduce novelty not in training
5. **Sensor Noise:** Heteroscedastic noise adds irreducible uncertainty
6. **Temporal Lags:** Some features lag PSI → limited lead time

---

## Part 5: Usage Instructions

### Generate Synthetic Data
```bash
cd /path/to/project
python3 src/generate_psi_7d.py --seed 42
# Output: data/synthetic/{train,val,test}.csv, metadata.json, psi_7d_visualization.png
```

### Train TFT Model
```bash
# Option 1: Dedicated synthetic script
python3 src/train_predict_synthetic.py

# Option 2: Use original train script (will auto-adapt if synthetic data exists)
python3 src/train_tft.py
```

### Make Predictions
```bash
# Auto-detects synthetic data and uses appropriate config
python3 src/predict_tft.py
# Output: data/synthetic/tft_predictions.csv, tft_prediction_plot.png
```

### View Results
```bash
# Check CSV predictions
head data/synthetic/tft_predictions.csv

# View plot
open data/synthetic/tft_prediction_plot.png
```

---

## Part 6: File Structure

```
Project/
├── data/
│   └── synthetic/
│       ├── train.csv (77,763 rows)
│       ├── val.csv (8,283 rows)
│       ├── test.csv (34,200 rows)
│       ├── psi_7d_full.csv (120,960 rows)
│       ├── metadata.json
│       ├── psi_7d_visualization.png
│       ├── tft_predictions.csv (output)
│       └── tft_prediction_plot.png (output)
├── models/
│   └── tft_psi_model_synthetic.ckpt (trained model)
├── src/
│   ├── generate_psi_7d.py (data generation)
│   ├── train_tft.py (original training script)
│   ├── train_predict_synthetic.py (dedicated synthetic script)
│   ├── predict_tft.py (prediction with auto-detection)
│   └── tft_dataset_example.py (TimeSeriesDataSet usage)
└── data/synthetic/README.md (detailed data documentation)
```

---

## Part 7: Key Insights

### Why Synthetic Data is Valuable
1. **Reproducible:** Seed-based, byte-identical generation
2. **Controlled:** Event types, magnitudes, and timing are tunable
3. **Realistic:** Incorporates kernel PSI formulas and real-world patterns
4. **Challenging:** Intentional imperfection prevents overfitting on easy data
5. **Diverse:** 3 nodes × 7 days × 2,880 points/day = rich, varied dataset

### Why 70-95% Performance is Expected
- Real systems have unpredictable events
- No feature engineering can predict purely random spikes
- Even domain experts can't achieve 100% recall on I/O events
- Model should outperform naive baseline (69% precision, 100% recall)

### Model Interpretability
- **Attention Weights:** TFT learns which time steps matter most
- **Static Covariate Effects:** node_id and workload_type shape baseline
- **Temporal Patterns:** Morning/evening cycles, business hours effects
- **Quantiles:** q10/q90 show model confidence per prediction

---

## Conclusion

This system provides:
✓ Realistic 7-day PSI I/O pressure dataset  
✓ Intentional imperfection (70-95% achievable performance)  
✓ Proper train/val/test splits with gap protection  
✓ TFT model optimized for spike detection  
✓ Automated prediction evaluation with F1 scores  
✓ Reproducible results (seed-based generation)  

**Next Steps:**
1. Generate data: `python3 src/generate_psi_7d.py`
2. Train model: `python3 src/train_predict_synthetic.py`
3. Review predictions: `cat data/synthetic/tft_predictions.csv`
4. Check F1 score and spike metrics in terminal output
