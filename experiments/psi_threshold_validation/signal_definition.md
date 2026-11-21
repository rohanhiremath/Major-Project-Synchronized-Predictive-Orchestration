# Signal Definition — PSI Threshold Validation (v2)

Frozen before any calibration data is analysed.
Do not edit after the first calibration run.

---

## Chosen Signal

**Name**: `psi_memory_deriv_pct`

**Exact Prometheus query** (used both to generate the training/test datasets
and by `prediction_service.py` at inference time):

```
deriv(node_pressure_memory_waiting_seconds_total{pod=~"workload-app-.*"}[2m]) * 100
```

**Source**: Node-exporter counter `node_pressure_memory_waiting_seconds_total`
(cumulative seconds any task spent stalled waiting for memory, i.e. PSI memory
"some" total stall time). The `deriv()` function fits a least-squares slope over
the 2-minute look-back window, giving units of seconds/second (dimensionless
rate). Multiplying by 100 expresses the result as **percent of wall-clock time**
per second that tasks were stalling — an instantaneous approximation of PSI
memory some, consistent with the kernel's own avg10 definition.

**Units**: percent (0–100 scale; observed range in dataset 0–9.71 %).

**Sampling interval**: 20 seconds (one row per pod per 20 s in the CSV files).

**Non-negativity**: values below zero are clamped to 0.0 at ingestion
(see `prediction_service.py` lines 279–281).

---

## Consistency Check

The column `psi_some_avg10` in the dataset CSVs was populated by
`generate-large-dataset.py` using the query above.
The same query is used by `prediction_service.py::get_current_psi_metrics()`
at inference time.
The three data files therefore carry the same signal the model was trained on.

### Dataset statistics (from data/*.csv)

| File | Rows | Series | min | p50 | p90 | p99 | max |
|------|------|--------|-----|-----|-----|-----|-----|
| train.csv | 20736 | 6 | 0.000 | 0.023 | 2.976 | 7.372 | 9.708 |
| test.csv | 2592 | 6 | 0.000 | 0.013 | 4.054 | 6.537 | 7.704 |
| validation.csv | 2592 | 6 | 0.000 | 0.007 | 1.902 | 6.470 | 7.519 |

Row interval: 20 s.  All values ≥ 0. No negative values observed.

---

## SHA256 Hashes

These hashes are computed at freeze time and must match before any analysis runs.

| File | SHA256 |
|------|--------|
| data/train.csv | `3a636ac20df412cda0f22f6cfe5b9ac6e69b66b5cfefa47b0807fee80393955b` |
| data/test.csv | `ee52a4f55439d41a57f1c0121d08203f4351695042a1f7fc79061c7313bd417d` |
| data/validation.csv | `a5aa59626f1d59abf42fa52b28b0d0e7ddaec1782b16b185711f9221f4118c9c` |
| kubernetes/phase6/generate-large-dataset.py | `c93ada25f8461578ff2ba690e0e7875fdc64135e32cca9ee182173275378ff70` |

---

## What This Signal Is Not

- It is **not** the raw kernel `psi_some_avg10` read from `/proc/pressure/memory`
  or from a cgroup `memory.pressure` file.  The earlier host experiment
  (experiments/psi_threshold_validation/verdict.json) measured cgroup avg10 and
  found a maximum PSI of 4.73 %.  That experiment used the wrong signal for
  validating this production threshold.
- It is **not** `rate(node_pressure_memory_waiting_seconds_total[10s]) * 100`.
  That form (rate over 10 s) appears in README.md and PHASE6_PLAN.md as an
  alternative sketch; the actual code and dataset use `deriv([2m])`.

---

## File frozen at

2026-10-18.  SHA256 of this file recorded in experiment_log.md.
