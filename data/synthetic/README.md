# PreSync 7-Day PSI Synthetic Dataset

Synthetic Linux PSI I/O pressure data for training pytorch-forecasting TemporalFusionTransformer models.

## PSI Clarification

**PSI values are in PERCENTAGE form (0–10% typical range):**
- **psi_io_some_avg10** = percentage of CPU time stalled on I/O
- **ΔΨ (Delta PSI)** = typical change between 15s samples ≈ ±1.8%
- **Spike threshold** = 2.0% (latency degradation risk)

## Quick Stats

- **Duration:** 7 days (2026-08-21 to 2026-08-27) @ 15s intervals
- **Nodes:** 3 (node-a: db, node-b: batch, node-c: web)
- **Splits:** Train 77.7k rows, Val 8.3k, Test 34.2k
- **Spike rate:** 6.9–7.4% (realistic predictability)
- **Total rows:** 120,249

## Files

- `train.csv` - Training split
- `val.csv` - Validation split
- `test.csv` - Test split
- `psi_7d_full.csv` - Full 7-day dataset
- `metadata.json` - Column roles and statistics
- `psi_7d_visualization.png` - 7-day visualization

## Usage

```bash
# Generate (deterministic, seed=42)
python3 src/generate_psi_7d.py

# Load in PyTorch
python3 src/tft_dataset_example.py
```

## Key Columns

| Column | Unit | Range | Description |
|--------|------|-------|-------------|
| **psi_io_some_avg10** | % | 0–10% | **TARGET: PSI I/O "some" 10s average** |
| psi_io_some_avg60 | % | 0–10% | 60s average |
| psi_io_some_avg300 | % | 0–10% | 300s average |
| psi_io_full_avg10 | % | 0–7% | PSI "full" variant (≈65% of "some") |
| disk_iops | ops/sec | 0–5000 | I/O operations |
| disk_queue_depth | count | 0–100 | Queue length (5-step lag) |
| io_wait_pct | % | 0–100 | CPU time waiting for I/O |
| cpu_util_pct | % | 0–100 | CPU utilization |
| p95_latency_ms | ms | 10–300 | P95 request latency |
| pod_count | count | 1–100 | Running pods |

## Data Characteristics

**5 Event Types (By Design):**
1. Learnable spikes (40%) — Scheduled backups, hourly crons
2. Precursor spikes (25%) — Queue rises before PSI > 2.0%
3. Unpredictable spikes (20%) — No warning (prevents 100% recall)
4. Near-miss events (15%) — Look-alikes that stay < 2.0%
5. Magnitude variance — Log-normal peak PSI (median 2.6%)

**Naive Baseline:** PSI > 1.2% → precision ~69%, recall 100% (intentionally imperfect)

## Validated Threshold

From SYNTHETIC_VALIDATION_WITH_FINDINGS.md:
- **T = 1.8%** threshold validated with 83% recall, 1.5 FA/hr
- Spike threshold of **2.0%** in dataset ensures clear separation

## Generated

- Date: 2026-10-18
- Seed: 42 (deterministic)
- Data Origin: Synthetic
- Created: generate_psi_7d.py
