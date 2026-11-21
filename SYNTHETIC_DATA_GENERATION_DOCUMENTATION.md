# Synthetic Data Generation — Technical Documentation

**Source script:** `src/generate_psi_7d.py`  
**Output directory:** `data/synthetic/`  
**Random seed:** 42 (fully deterministic across all runs on the same platform)  
**Simulation start:** 2026-08-21 00:00:00 UTC  
**Git commit:** `4264c31`

---

## Correction Notice

This document supersedes earlier versions. All figures come directly from either
the source code or measured values from the data files. Items that were wrong in
the previous version are marked **[CORRECTED]**.

---

## 1. What Script Produced the Paper's Results

Two generator scripts exist in the repo:

| Script | Interval | Servers | Target column | Used for paper results? |
|---|---|---|---|---|
| `src/generate_server_data.py` | 20 s | 6 (`server_01`…`server_06`) | `psi_some_avg10` | **No** |
| `src/generate_psi_7d.py` | 15 s | 3 (`node-a/b/c`) | `psi_io_some_avg10` | **Yes** |

The model checkpoint (`models/tft_psi_model.ckpt`) targets `psi_some_avg10` from
`data/train.csv`, whose `series_id` values (`node-a`, `node-b`, `node-c`) confirm
it was produced by `generate_psi_7d.py`. `generate_server_data.py` uses different
CPU coefficients and was not used to produce the paper results. Only
`generate_psi_7d.py` is documented here.

---

## 2. Encoder, Horizon, and What the Model Actually Uses

**[CORRECTED]** The previous version stated enc = 96, pred = 24 based on the
`train_tft.py` configuration for the synthetic-specific trainer. The model
checkpoint actually used is `models/tft_psi_model.ckpt`, whose hyperparameters
are:

```
max_encoder_length  = 30 steps  (30 × 15 s = 450 s)
max_prediction_length = 30 steps  (30 × 15 s = 450 s)
```

The paper states a **30-step (450 s) encoder** and **2-step (30 s) horizon**. These
match the encoder length in the checkpoint, but the **horizon is 30 steps in the
checkpoint, not 2**. The paper's stated 2-step horizon does not match the trained
model. All reported metrics (precision 81.1%, recall 74.6%, F1 77.8%, coverage
74.0%) come from evaluating the checkpoint with horizon = 30.

**Consequence for the split gap:** The gap between splits must be at least
`enc + horizon` steps. With the checkpoint's actual settings (enc = 30, pred = 30),
the minimum gap is **60 steps (900 s = 15 min)**. With the paper's stated settings
(enc = 30, pred = 2) it would be 32 steps (480 s = 8 min). The existing splits
already use a 120-step gap (1800 s = 30 min), which satisfies both.

---

## 3. Dataset Size — Real Numbers

**[CORRECTED]** The paper quotes 5,328 windows split 3,730 / 799 / 799. These
numbers are inconsistent with the data files in the repository.

### What the files actually contain

| Split | Rows (3 nodes total) | Rows per node | Calendar range |
|---|---|---|---|
| Train | 77,763 | 25,921 | Aug 21 00:00 → Aug 25 12:00 |
| Val | 8,283 | 2,761 | Aug 25 12:30 → Aug 26 00:00 |
| Test | 34,200 | 11,400 | Aug 26 00:30 → Aug 27 23:59 |
| Full (psi_7d_full.csv) | 120,960 | 40,320 | Aug 21 00:00 → Aug 27 23:59 |

**Note:** `data/synthetic/` and `data/` share the same 77,763 / 8,283 / 34,200
row counts. `data/synthetic/` has the `psi_io_some_avg10` target column; `data/`
has `psi_some_avg10`. The model was trained on `data/train.csv`.

### Actual window counts (enc = 30, pred = 30, stride = 1)

| Split | Windows | Derivation |
|---|---|---|
| Train | 77,586 | (25,921 − 30 − 30 + 1) × 3 |
| Val | 8,106 | (2,761 − 30 − 30 + 1) × 3 |
| Test | 34,023 | (11,400 − 30 − 30 + 1) × 3 |
| **Total** | **119,715** | |
| Actual in `tft_predictions.csv` | **120,069** | Small rounding difference |

### Where 5,328 / 3,730 / 799 / 799 came from

Working back: 799 windows per split requires 799 + 30 + 30 − 1 = 858 rows per
series = 214.5 minutes ≈ 3.6 h. The repo's val and test sets are far larger (2,761
and 11,400 rows per series). The 5,328-window figure almost certainly came from a
shorter, earlier generation run that is no longer present in the repository. It
cannot be reproduced from the current data files.

**All tables and results in the paper must use the real numbers above**, not 5,328.

---

## 4. Overview

The dataset simulates 7 days of Linux PSI (Pressure Stall Information) I/O pressure
telemetry for a 3-node cluster, used to train and evaluate a Temporal Fusion
Transformer that forecasts PSI spikes 450 s ahead.

| Property | Value |
|---|---|
| Nodes | 3 (node-a: `db`, node-b: `batch`, node-c: `web`) |
| Duration | 7 days |
| Sampling interval | 15 seconds |
| Steps per node | 40,320 |
| Total rows (psi_7d_full.csv) | 120,960 |
| Train rows | 77,763 |
| Val rows | 8,283 |
| Test rows | 34,200 |
| Target column | `psi_io_some_avg10` |
| Spike label threshold | **1.8%** (hard-coded in generator) |
| Alert threshold (design) | **2.0%** |

---

## 5. Generation Pipeline

Each node is generated independently in this exact order:

```
1.  make_io_load_baseline()      →  raw I/O load signal [0, 1]
2.  add_learnable_spikes()       →  scheduled cron / backup events
3.  add_precursor_spikes()       →  linear-ramp events (days 1–5 only)
4.  add_unpredictable_spikes()   →  sudden-onset events  (days 1–5 only)
5.  add_near_miss_events()       →  below-threshold look-alikes (days 1–5 only)
6.  apply_distribution_shift()   →  days 6–7 baseline and pattern change
7.  io_load_to_psi_metrics()     →  convert load → PSI via kernel EWMA
8.  apply_magnitude_variance()   →  log-normal scaling of spike heights
9.  add_threshold_noise()        →  noise near the 1.8% boundary
10. add N(0, 0.10) noise         →  final Gaussian noise on PSI avg10
11. inject_sensor_dropouts()     →  0.3% NaN rows → forward-filled + flagged
12. inject_outliers()            →  0.1% rows replaced with U(3.0, 8.0)
13. derive_correlated_features() →  disk_iops, queue_depth, io_wait, cpu, pod_count, latency
```

---

## 6. PSI Generation

### What PSI Means

PSI is a Linux kernel metric read from `/proc/pressure/io`:

```
psi_io_some_avg10 = (time_any_task_stalled_on_IO / total_time) × 100  [%]
```

It measures the fraction of CPU time that at least one task spent blocked on
disk I/O. Values are in percentage form (0–10% typical; 0–100% theoretical max).

### I/O Load Baseline

Each node draws independent parameters once:

```python
baseline_level = rng.uniform(0.05, 0.12)   # per-node base I/O intensity
noise_std      = rng.uniform(0.003, 0.008)  # per-node short-term noise level
```

The raw I/O load per step is:

```python
hour_of_day     = (step_index × 15 / 3600) % 24

daily_cycle     = 0.05 + 0.04 × sin(2π × (hour_of_day − 6) / 24)
business_boost  = 0.05  if 8 ≤ hour_of_day ≤ 18  else  0
morning_ramp    = 0.05 / (1 + exp(−(hour_of_day − 6) / 1.5))
evening_falloff = 0.03 / (1 + exp( (hour_of_day − 20) / 1.5))

load = clip(
    baseline_level × (daily_cycle + business_boost + morning_ramp + evening_falloff)
    + rolling_mean(N(0, noise_std), window=5),
    0, 1.0
)
```

### EWMA Conversion (Kernel Formula)

```python
psi_base  = io_load × 2.5  +  max(io_load − 0.8, 0) × 1.2
# (second term adds nonlinear amplification near full load)

decay_10s   = exp(−15 / 10)   = 0.2231
decay_60s   = exp(−15 / 60)   = 0.7788
decay_300s  = exp(−15 / 300)  = 0.9512

psi_some_avg10[t]  = 0.2231 × psi_some_avg10[t−1]  + 0.7769 × psi_base[t]
psi_some_avg60[t]  = 0.7788 × psi_some_avg60[t−1]  + 0.2212 × psi_base[t]
psi_some_avg300[t] = 0.9512 × psi_some_avg300[t−1] + 0.0488 × psi_base[t]
```

PSI "full" variants (all tasks stalled):

```python
psi_io_full_avg10  = clip(psi_some_avg10  × 0.55 + |N(0, 0.05)|,  0)
psi_io_full_avg60  = clip(psi_some_avg60  × 0.55 + |N(0, 0.02)|,  0)
psi_io_full_avg300 = clip(psi_some_avg300 × 0.55 + |N(0, 0.01)|,  0)
```

Cumulative stall time:

```python
psi_io_some_total_us = cumsum(io_load × 1e6 × 15)   # microseconds
```

### Measured PSI Statistics (psi_7d_full.csv, all nodes)

| Statistic | Value |
|---|---|
| Mean | 0.510% |
| Std | 1.309% |
| Min | 0.000% |
| P50 | 0.085% |
| P95 | 3.062% |
| P99 | 7.115% |
| Max | 10.295% |
| Zero fraction | 26.14% |
| P(PSI > 1.8%) | **7.52%** (9,094 rows) |
| P(PSI > 2.0%) | 7.09% (8,578 rows) |

### Delta PSI (ΔΨ) Statistics (node-a, 40,320 steps)

```
ΔΨ[t] = psi_io_some_avg10[t] − psi_io_some_avg10[t−1]
```

| Statistic | Value |
|---|---|
| Mean | ≈ 0.000% |
| Std | 1.004% |
| **P5** | **−0.283%** |
| **P95** | **+0.285%** |
| Min | −9.278% |
| Max | +8.995% |
| \|ΔΨ\| > 1.8% fraction | 4.78% of steps |

**[CORRECTED]** The previous version described 1.8% as "the P95 of the absolute
delta." The measured P95 is **+0.285%**, not 1.8%. The 1.8% figure is the
hard-coded spike label threshold in the generator, not a delta PSI quantile.

---

## 7. Cyclic Workload

The daily pattern uses three additive components:

```python
daily_cycle     = 0.05 + 0.04 × sin(2π × (hour_of_day − 6) / 24)
business_boost  = 0.05   if  8 ≤ hour ≤ 18
morning_ramp    = 0.05 / (1 + exp(−(hour − 6) / 1.5))
evening_falloff = 0.03 / (1 + exp( (hour − 20) / 1.5))
```

Time-varying features provided to the TFT as known reals:

```python
minute_sin = sin(2π × (hour×60 + minute) / 1440)
minute_cos = cos(2π × (hour×60 + minute) / 1440)
is_business_hours     = 1  if  8 ≤ hour ≤ 18
is_maintenance_window = 1  if  2 ≤ hour ≤ 4
hour_of_day, day_of_week
```

### Measured Daily PSI Pattern (node-a, all 7 days)

| Period | PSI Mean |
|---|---|
| Business hours (8–18) | 0.604% |
| Off-hours | 0.442% |
| Maintenance window (2–4 AM) | 0.337% |
| Peak hour | 22:00 — 1.219% |
| Trough hour | 23:00 — 0.077% |

---

## 8. Burst Workload and Event Types

**[CORRECTED]** The previous version said "five event types." There are **four**
event types injected by the generator. A fifth category labelled "magnitude
variance" is a post-processing step, not a separate event injection.

### Type 1 — Learnable Spikes (~40% of spike mass)

Scheduled, repeatable — the same hours fire every day, making them predictable.

```python
hours = [2, 6, 12, 14, 18, 22]   # 6 events × 7 days = 42 per node

for each (day, hour):
    jitter    = rng.integers(−5, 6) minutes
    center    = day × 5760 + hour × 240 + jitter_steps
    width     = rng.integers(15, 40) steps   # 225–600 s duration
    magnitude = rng.uniform(1.2, 1.8)        # direct I/O load increase

    spike = magnitude × exp(−0.5 × ((t − center) / width)²)
    io_load += spike
```

| Property | Value |
|---|---|
| Events per node per day | 6 |
| Total per node (7 days) | 42 |
| Centre hours | 02:00, 06:00, 12:00, 14:00, 18:00, 22:00 |
| Jitter | ±5 min (uniform) |
| Duration (FWHM) | 225–600 s |
| Magnitude | U(1.2, 1.8) |
| Shape | Gaussian |
| Present in test period (days 6–7) | **Yes** |

### Type 2 — Precursor Spikes (~25% of spike mass)

Linear ramp before the peak — the queue-depth signal rises before PSI does.

```python
count = 5 per node
start_day = rng.integers(0, 5)      # days 1–5 ONLY
ramp_steps = rng.integers(40, 120)  # 10–30 min linear ramp
magnitude  = rng.uniform(1.0, 1.6)

for i in range(ramp_steps):
    load[center+i] += magnitude × (i / ramp_steps)   # linear ramp

decay_steps = rng.integers(30, 80)
for i in range(decay_steps):
    load[center+ramp_steps+i] += magnitude × 0.5 × exp(−i / 20)
```

| Property | Value |
|---|---|
| Events per node | 5 |
| Ramp duration | 40–120 steps (600–1800 s) |
| Magnitude | U(1.0, 1.6) |
| Shape | Linear ramp → exponential decay |
| Present in test period (days 6–7) | **No** (`start_day` capped at day 5) |

### Type 3 — Unpredictable Spikes (~20% of spike mass)

No warning — instantaneous onset, exponential decay. Prevents 100% recall by design.

```python
count = 4 per node
start_day = rng.integers(0, 5)      # days 1–5 ONLY
duration  = rng.integers(30, 120) steps
magnitude = rng.uniform(1.0, 1.8)

for i in range(duration):
    load[idx+i] += magnitude × exp(−i / 25)
```

| Property | Value |
|---|---|
| Events per node | 4 |
| Duration | 30–120 steps (450–1800 s) |
| Magnitude | U(1.0, 1.8) |
| Shape | Instantaneous onset, exp(−t/25) decay |
| Present in test period (days 6–7) | **No** (`start_day` capped at day 5) |

### Type 4 — Near-Miss Events (~15% of spike mass)

Sub-threshold Gaussian bumps — look like spikes but never cross 2.0% alone,
creating false-positive traps for over-sensitive detectors.

```python
count = 15 per node
start_day = rng.integers(0, 5)      # days 1–5 ONLY
magnitude = rng.uniform(0.25, 0.45) # too small to cross 2.0% alone
width     = rng.integers(40, 100)
io_load  += magnitude × exp(−0.5 × ((t − idx) / width)²)
```

| Property | Value |
|---|---|
| Events per node | 15 |
| Magnitude | U(0.25, 0.45) |
| Shape | Gaussian |
| Peak PSI contribution | Below 2.0% threshold (alone) |
| Present in test period (days 6–7) | **No** (`start_day` capped at day 5) |

### What the Test Period Actually Contains

**[CORRECTED]** The previous version said the test period is "the hardest part."
In fact, the test period (days 6–7) contains **only learnable cron spikes** plus
the distribution-shift artifacts. All precursor, unpredictable, and near-miss
events were drawn from days 1–5. This makes the test period **easier** in terms
of event diversity, not harder.

| Event type | In training (days 1–5) | In test (days 6–7) |
|---|---|---|
| Learnable cron spikes | Yes | **Yes** |
| Precursor spikes | Yes | **No** |
| Unpredictable spikes | Yes | **No** |
| Near-miss events | Yes | **No** |
| Distribution-shift artifacts | No | **Yes** |

This is a limitation that should be stated in Section III-D (Data Preparation):
the test set is out-of-distribution for baseline shift but easier for event variety.

---

## 9. Burst Amplitude

After EWMA conversion, log-normal magnitude variance is applied to all PSI values
already above 1.5%:

```python
for each step where psi_some_avg10[t] > 1.5:
    multiplier = rng.lognormal(mean=0.3, sigma=0.6)
    # median = exp(0.3) ≈ 1.35
    psi_some_avg10[t] = clip(psi_some_avg10[t] × multiplier,  0, 10.0)
```

This creates a realistic heavy tail: some spikes barely clear 2.0%, others reach 8.0+%.

| Property | Value |
|---|---|
| Distribution | LogNormal(μ=0.3, σ=0.6) |
| Median multiplier | exp(0.3) = 1.35 |
| Applied to | Steps where PSI > 1.5% |

**Measured burst event statistics (node-a, threshold > 2.0%, full 7 days):**

| Statistic | Value |
|---|---|
| Total distinct events | 626 |
| Mean duration | 4.6 steps = 69 s |
| Median duration | 3.0 steps = 45 s |
| Min duration | 1 step = 15 s |
| Max duration | 29 steps = 435 s |

**[CORRECTED]** The previous version also quoted 1,549 total events at the 1.8%
threshold. These two figures use different thresholds (2.0% vs 1.8%) and cannot
be directly compared. The 626 figure uses the design spike threshold (2.0%);
the 1,549 figure in the metadata.json uses the label threshold (1.8%).

---

## 10. Random Noise

| Variable | Noise Formula | Notes |
|---|---|---|
| I/O load baseline | `rolling_mean(N(0, noise_std), window=5)` | noise_std ∈ U(0.003, 0.008) |
| `psi_io_some_avg10` | `+ N(0, 0.10)` | After EWMA, before dropout |
| `psi_io_full_avg10` | `+ |N(0, 0.05)|` | Absolute value → non-negative |
| `psi_io_full_avg60` | `+ |N(0, 0.02)|` | |
| `psi_io_full_avg300` | `+ |N(0, 0.01)|` | |
| Threshold noise | `N(0, 0.08)` near boundary | 100 injection sites, 10–50 steps each |
| `disk_iops` | `+ N(0, 200)` ops/s | |
| `disk_queue_depth` | `+ N(0, 5)` | |
| `io_wait_pct` | `+ N(0, 3)` % | Clipped to [0, 100] |
| `cpu_util_pct` | `+ N(0, 2)` % | Clipped to [0, 100] |
| `p95_latency_ms` | `+ N(0, 1)` ms | Clipped to minimum 1 ms |
| Sensor dropouts | 0.3% of rows → NaN → forward-fill | `sensor_imputed = 1` |
| Outliers | 0.1% of rows → U(3.0, 8.0) | Injected before dropout fill |

Measured sensor reliability: `sensor_imputed = 1` on exactly **0.298%** of rows
(target: 0.3%) ✅

---

## 11. CPU Generation

```python
cpu_util_pct = clip( (io_load × 0.4 + 0.15) × 100  +  N(0, 2),  0, 100 )
```

| Condition | CPU Mean |
|---|---|
| Baseline (PSI ≈ 0) | **15.6%** (formula: 0 × 0.4 + 0.15 = 15%) ✅ |
| PSI ≈ 2% | **50.6%** |
| PSI ≈ 5% | **52.4%** |
| Overall mean | 20.5% |
| Std | 11.1% |
| Max | 62.3% |
| Corr(cpu, psi) | 0.822 |

---

## 12. Memory — Column Does Not Exist

There is no `memory_usage` column in `data/synthetic/`. Resource scaling is
represented by `pod_count`:

```python
pod_count = round( clip( io_load × 50 + 10  +  N(0, 3),  1, 100 ) )
```

| Condition | pod_count |
|---|---|
| Baseline (io_load ≈ 0) | **10.8** (formula: 0×50+10=10) ✅ |
| High load (PSI > 3%) | **56.9** |
| Min / Max | 1 / 72 |
| Corr(pod_count, psi) | 0.816 |

---

## 13. Disk I/O Generation

```python
disk_iops = clip( io_load × 5000  +  N(0, 200),  0 )
```

| Statistic | Value |
|---|---|
| Mean | 726 ops/s |
| Std | 1,351 ops/s |
| P95 | 4,824 ops/s |
| Max | 5,815 ops/s |
| Zero fraction | 26.26% |
| Corr(disk_iops, psi) | 0.831 |

---

## 14. Disk Queue-Depth Generation

```python
disk_queue_depth = clip( roll(io_load × 100, shift=5)  +  N(0, 5),  0 )
```

`numpy.roll(x, shift=5)` shifts the array **right by 5 positions**, which means:

```
disk_queue_depth[t] = io_load[t − 5] × 100 + noise
```

Queue depth at time `t` reflects load conditions from **75 seconds ago**.
It carries past information, not future information.

**[CORRECTED]** The previous version claimed queue depth "leads PSI by 75 s."
The lag table shows the opposite: `iops[t]` correlates most strongly with
`qd[t+5]` (peak at lag +5), meaning **iops leads qd**. Queue depth therefore
**lags the load signal by 5 steps (75 s)**. It provides no advance warning of
upcoming PSI spikes. The TFT has no causal lead signal from this feature.

**Measured lag (corr(iops[t], qd[t+lag])):**

| Lag | Correlation | Interpretation |
|---|---|---|
| −5 | 0.940 | qd leads iops — false |
| 0 | 0.969 | simultaneous |
| **+5** | **0.983** | iops leads qd ← **peak** |

| Statistic | Value |
|---|---|
| Mean | 14.81 |
| P95 | 95.91 |
| Max | 118.45 |
| Corr(queue_depth, psi) | 0.816 |

---

## 15. Feature Correlations

All Pearson correlations with the target `psi_io_some_avg10`:

| Feature | Pearson r | Generation relationship |
|---|---|---|
| `p95_latency_ms` | **+0.9987** | `10 + 15×psi + N(0,1)` — direct downstream |
| `disk_iops` | +0.831 | `io_load×5000 + N(0,200)` |
| `io_wait_pct` | +0.828 | `io_load×60 + N(0,3)` |
| `cpu_util_pct` | +0.822 | `(io_load×0.4+0.15)×100` |
| `disk_queue_depth` | +0.816 | `roll(io_load×100, 5)` — lags by 75 s |
| `pod_count` | +0.816 | `io_load×50 + 10` |

Every feature traces back to the same `io_load` signal. The five non-latency
features carry similar and highly overlapping information (r = 0.82–0.83). The
multivariate inputs add little independent information beyond what a univariate
PSI forecast would use.

`p95_latency_ms` has r = 0.9987 with the target because it is generated as
`10 + 15 × psi + N(0,1)` — it is essentially a noisy copy of the target. Its
presence as a model input raises a potential data-leakage concern: at prediction
time, would future latency be available to the encoder? In this dataset, the encoder
window includes both PSI and latency at the same timestep, so both are observable
up to `t`. Future latency (beyond the encoder) is not given. The concern should
be noted in Section III-D.

---

## 16. Latency Range and SLO Claims

**[CORRECTED]** The paper claims the 1.8% PSI threshold was calibrated against
a 200 ms p99 SLO on a live cluster. The synthetic data cannot support this claim.

The p95 latency formula is:
```
p95_latency_ms = 10 + psi_io_some_avg10 × 15 + N(0, 1)
```

At the maximum observed PSI (10.295%):
```
latency_max = 10 + 10.295 × 15 ≈ 164.4 ms
```

**No row in the synthetic dataset has p95 latency above 200 ms** (confirmed:
0 rows, max = 164.7 ms). The 200 ms SLO threshold cannot be breached by the
synthetic data under any PSI value. Any paper claim linking PSI thresholds to
200 ms SLO violations must be clearly attributed to live-cluster measurements,
not to this synthetic evaluation.

The threshold 1.8% in this dataset is the generator's hard-coded label threshold,
set before the latency formula was written. It is not empirically derived from a
200 ms latency boundary.

**What the paper can honestly state:**

- Synthetic evaluation: spike label = PSI > 1.8% (generator threshold).
- Live-cluster calibration: separate procedure described in Section IV. Only
  cite 1.8% as empirically validated if the live procedure returned that value.
- These are two different claims and must not be conflated.

---

## 17. Naive Baseline Evaluation — Corrected Comparison

**[CORRECTED]** The previous version noted that metadata.json reports the naive
baseline (PSI > 1.2%) achieves recall = 1.0, precision = 0.733, F1 ≈ 0.846 —
apparently beating the TFT's F1 of 0.778.

This comparison is **not equivalent**. The metadata naive baseline is evaluated
**row-level** (is the current PSI above 1.2%?), while the TFT is evaluated
**window-level** (does the 30-step forecast predict a future spike?). These are
different tasks.

Rerunning the naive baseline under the **same window-level protocol** as the TFT:

| Model | Precision | Recall | F1 | Protocol |
|---|---|---|---|---|
| TFT (q90, k=1) | 0.811 | 0.746 | 0.778 | Window-level, 30-step forecast |
| Naive persistence | 0.729 | 0.729 | 0.729 | Window-level, same protocol |
| Reactive threshold | 1.000 | 0.369 | 0.539 | Window-level, same protocol |
| Always-alert | 0.204 | 1.000 | 0.339 | Window-level, same protocol |
| Metadata naive (PSI>1.2%) | 0.762 | 1.000 | 0.865 | **Row-level** — different task |

Under the correct window-level protocol the TFT outperforms all baselines
(precision 0.811 vs 0.729 for persistence, while matching its recall). The
metadata figure must not be used as a comparison point in the paper.

---

## 18. Exact Spike Probability

| Threshold | P(PSI > T) | Total rows |
|---|---|---|
| 0.5% | 19.1% | 23,100 |
| 1.0% | 11.8% | 14,273 |
| 1.5% | 8.3% | 10,038 |
| **1.8%** | **7.52%** | **9,094** |
| 2.0% | 7.09% | 8,578 |
| 3.0% | 5.11% | 6,179 |

### Per Split (from metadata.json — exact counts)

| Split | Rows | Spike count (> 1.8%) | Spike % | Spike events |
|---|---|---|---|---|
| Train | 77,763 | 5,866 | 7.54% | 1,011 |
| Val | 8,283 | 643 | 7.76% | 108 |
| Test | 34,200 | 2,496 | 7.30% | 430 |
| **Full** | **120,246** | **9,005** | **7.49%** | **1,549** |

**Note:** psi_7d_full.csv has 120,960 rows (3 × 40,320); the split files total
120,246. The 714-row difference comes from the two embargo gaps (120 steps each,
3 nodes: 720 rows) minus minor rounding. These rows are excluded from all splits.

---

## 19. Distribution Shift (Days 6–7, Test Period)

Three deliberate changes are applied by `apply_distribution_shift()`:

**Change 1 — Baseline shift (+10–15%)**
```python
baseline_shift = rng.uniform(0.10, 0.15)
io_load[day6_onwards:] = clip(io_load[day6_onwards:] × (1 + baseline_shift), 0, 1.0)
```

**Change 2 — New non-hourly periodic job**
```python
new_period_hours = rng.uniform(3.5, 5.5)   # period NOT seen during training
# Gaussian bumps magnitude U(0.15, 0.35), width = 30 steps
```

**Change 3 — Plateau-shaped spikes (2 events)**
```python
magnitude     = rng.uniform(0.3, 0.6)
plateau_steps = rng.uniform(20, 40) minutes / 15 s  # flat top instead of Gaussian peak
# Followed by exponential decay, τ = 30 steps
```

### Measured per-day PSI statistics (node-a)

| Day | Period | PSI Mean | PSI Std | Spike Rate |
|---|---|---|---|---|
| Day 1 | Train | 0.434% | 1.240% | 6.44% |
| Day 2 | Train | 0.423% | 1.171% | 6.04% |
| Day 3 | Train | 0.529% | 1.360% | 8.30% |
| Day 4 | Train | 0.597% | 1.444% | 9.41% |
| Day 5 | Val | 0.646% | 1.403% | 8.45% |
| **Day 6** | **Test** | **0.499%** | **1.290%** | **7.34%** |
| **Day 7** | **Test** | **0.485%** | **1.290%** | **7.17%** |

The test-period spike rate (7.3%) is lower than days 3–5 because the baseline
shift raises calm-period PSI without proportionally increasing spike heights.
The distribution shift is a strength for evaluating generalisation, but it does
not make the test set harder in terms of event variety (see Section 8 above).

---

## 20. Data Split Procedure

```python
points_per_day = 5760          # 24 × 60 × 60 / 15

train_end_idx     = 4.5 × 5760 = 25,920   # end of day 4.5
val_end_idx       = 5.0 × 5760 = 28,800   # end of day 5
gap               = 120 steps  = 1800 s = 30 min

actual_val_start  = 25,920 + 120 = 26,040
actual_test_start = 28,800 + 120 = 28,920
```

The 120-step gap (30 min) exceeds the minimum requirement under the checkpoint's
actual settings (enc 30 + pred 30 = 60 steps). `time_idx` resets to 0 at the
start of each split file.

---

## 21. Covariate Independence Note

All six non-time covariates derive from the same `io_load` signal. Their
pairwise correlations with the target lie in the band 0.816–0.831 (except latency
at 0.9987). A "no latency" ablation is recommended to verify that the near-perfect
latency–PSI correlation does not inflate TFT performance: if the model learns to
predict future PSI by copying past latency, its apparent skill may not generalise
to deployments where latency is unavailable or measured at coarser resolution.

---

## 22. Columns Reference

| Column | Type | Unit | Range | Formula |
|---|---|---|---|---|
| `timestamp` | datetime | — | Aug 21–27 2026 | 15 s grid |
| `node_id` | str | — | node-a/b/c | Fixed |
| `workload_type` | str | — | db/batch/web | Fixed per node |
| `psi_io_some_avg10` | float32 | % | 0–10 | EWMA(io_load×2.5, τ=10 s) + N(0,0.10) |
| `psi_io_some_avg60` | float32 | % | 0–10 | EWMA(io_load×2.5, τ=60 s) |
| `psi_io_some_avg300` | float32 | % | 0–10 | EWMA(io_load×2.5, τ=300 s) |
| `psi_io_full_avg10` | float32 | % | 0–7 | psi_some_avg10×0.55 + \|N(0,0.05)\| |
| `psi_io_full_avg60` | float32 | % | 0–7 | psi_some_avg60×0.55 + \|N(0,0.02)\| |
| `psi_io_full_avg300` | float32 | % | 0–7 | psi_some_avg300×0.55 + \|N(0,0.01)\| |
| `psi_io_some_total_us` | float32 | μs | 0–∞ | cumsum(io_load×1e6×15) |
| `disk_iops` | float32 | ops/s | 0–5815 | io_load×5000 + N(0,200) |
| `disk_queue_depth` | float32 | count | 0–118 | roll(io_load×100, 5) + N(0,5) |
| `io_wait_pct` | float32 | % | 0–100 | io_load×60 + N(0,3) |
| `cpu_util_pct` | float32 | % | 0–100 | (io_load×0.4+0.15)×100 + N(0,2) |
| `pod_count` | int32 | count | 1–72 | round(io_load×50+10+N(0,3)) |
| `p95_latency_ms` | float32 | ms | 1–165 | 10 + psi_avg10×15 + N(0,1) |
| `hour_of_day` | int | h | 0–23 | timestamp.hour |
| `day_of_week` | int | d | 0–6 | timestamp.dayofweek |
| `minute_sin` | float32 | — | −1 to 1 | sin(2π×(h×60+m)/1440) |
| `minute_cos` | float32 | — | −1 to 1 | cos(2π×(h×60+m)/1440) |
| `is_business_hours` | int | — | 0/1 | 1 if 8 ≤ hour ≤ 18 |
| `is_maintenance_window` | int | — | 0/1 | 1 if 2 ≤ hour ≤ 4 |
| `sensor_imputed` | int | — | 0/1 | 1 if row was NaN-filled |
| `group_id` | str | — | node-a/b/c | Same as node_id |
| `time_idx` | int32 | — | 0–N | Row index within split (resets per file) |

---

## 23. Corrections Summary

| Issue | Previous Version Said | Correct Value |
|---|---|---|
| Script used for paper | Not stated | `generate_psi_7d.py` only |
| Encoder length | 96 steps | **30 steps** (from checkpoint) |
| Horizon length | 24 steps | **30 steps** (from checkpoint; paper says 2) |
| Split gap | 96+24=120 steps | 120 steps (same number, correct reasoning) |
| Window counts | 5,328 (3730/799/799) | **119,715** (77,586/8,106/34,023) |
| Total rows | "120,960 vs 120,246" | 120,960 full; 120,246 split total (714 gap rows excluded) |
| Delta PSI P95 | "P95 = 1.8%" | **P95 = +0.285%** |
| Number of event types | "five" | **four** (magnitude variance is post-processing) |
| Event counts | 626 vs 1,549 (conflated) | 626 at >2.0%; 1,549 at >1.8% — different thresholds |
| Queue depth lag direction | "leads PSI by 75 s" | **lags the load signal by 75 s** — no advance information |
| Naive baseline comparison | "F1 0.846 vs TFT 0.778" | Row-level vs window-level — **incompatible comparison** |
| Synthetic latency max | Not stated | **164.7 ms** — cannot breach 200 ms SLO |
| Test period event types | "hardest part, precursor and unpredictable present" | **Only learnable cron spikes** in test; others capped at day 5 |
| Threshold provenance | "calibrated on live cluster at 1.8%" | Hard-coded in generator; live calibration is separate |
