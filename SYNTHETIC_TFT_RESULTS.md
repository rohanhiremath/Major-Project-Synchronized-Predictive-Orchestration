# Synthetic PSI Data - TFT Model Results

## Actual Results from Testing

### Prediction Output
- Prediction shape: (120069, 30)
- Actual shape: (120069, 30)
- Quantiles: (0.1, 0.5, 0.9)

### Quantile Loss
- q10: 0.069073
- q50: 0.209250
- q90: 0.160080

### Coverage & Interval
- q10-q90 coverage: 74.045%
- Average q10-q90 interval width: 0.898508

### Regression Metrics
- MAE: 0.418501
- RMSE: 1.071201

### Spike Detection Performance
- Threshold: 1.8 PSI
- Precision: 81.127%
- Recall: 74.645%
- F1 Score: 77.63%

### F1 Score Calculation
```
F1 = 2 × (Precision × Recall) / (Precision + Recall)
F1 = 2 × (0.81127 × 0.74645) / (0.81127 + 0.74645)
F1 = 2 × 0.60567 / 1.55772
F1 = 1.21134 / 1.55772
F1 = 0.7763 = 77.63%
```

## Data Samples

### Training Data - First 5 Rows
```
timestamp,node_id,workload_type,disk_iops,disk_queue_depth,io_wait_pct,cpu_util_pct,pod_count,p95_latency_ms,psi_io_some_avg10
2026-08-21 00:00:00,node-a,db,604.488,2.5095525,12.266596,22.041325,15,16.669847,0.40022737
2026-08-21 00:00:15,node-a,db,655.3837,0.0,9.994319,19.67168,20,15.251125,0.39338914
2026-08-21 00:00:30,node-a,db,666.5055,0.0,8.6793375,26.375345,14,17.82983,0.5126123
2026-08-21 00:00:45,node-a,db,535.3448,2.4777153,12.239021,18.672712,17,14.439314,0.29353762
2026-08-21 00:01:00,node-a,db,1052.7836,0.0,10.64059,20.111853,17,16.069323,0.40223414
```

### Test Data - First 5 Rows
```
timestamp,node_id,workload_type,disk_iops,disk_queue_depth,io_wait_pct,cpu_util_pct,pod_count,p95_latency_ms,psi_io_some_avg10
2026-08-26 00:30:00,node-a,db,0.0,0.0,0.0,12.303701,12,11.271356,0.0
2026-08-26 00:30:15,node-a,db,0.0,5.7788706,0.6824806,11.896401,9,12.700385,0.14513086
2026-08-26 00:30:30,node-a,db,0.0,0.0,0.0,12.357334,9,9.82575,0.016340887
2026-08-26 00:30:45,node-a,db,0.0,0.0,0.0,15.190047,16,12.148915,0.16707665
2026-08-26 00:31:00,node-a,db,291.10336,0.0,4.1051483,12.728597,9,9.394919,0.0
```

## Dataset Split

| Split | Rows | Spikes (%) | Events |
|-------|------|-----------|--------|
| Train | 77,763 | 5,535 (7.1%) | 1,202 |
| Val | 8,283 | 612 (7.4%) | 122 |
| Test | 34,200 | 2,346 (6.9%) | 519 |

## Model Configuration

- Encoder Length: 96 steps
- Prediction Length: 24 steps
- Hidden Size: 16
- Attention Heads: 2
- Batch Size: 32
- Max Epochs: 10

## Output Files Generated

- `data/synthetic/train.csv`
- `data/synthetic/val.csv`
- `data/synthetic/test.csv`
- `data/synthetic/psi_7d_full.csv`
- `data/synthetic/metadata.json`
- `data/synthetic/psi_7d_visualization.png`
- `data/synthetic/tft_predictions.csv`
- `data/synthetic/tft_prediction_plot.png`
- `models/tft_psi_model_synthetic.ckpt`
