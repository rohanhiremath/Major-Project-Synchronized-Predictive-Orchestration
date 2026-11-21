# Threshold Selection and Validation — Paper Section

This file contains text intended for inclusion in the project report or paper.
All numbers are taken directly from the JSON artifacts listed in parentheses.
Do not edit numbers without re-running the analysis scripts.

---

## 4.x  PSI Spike Threshold: Selection, Testing, and Limitations

### 4.x.1  Operating Point

The prediction service uses a configurable spike threshold,
`SPIKE_THRESHOLD = 1.80` (percent), to decide whether a predicted PSI value
constitutes a spike that should trigger autoscaling.
The value 1.80 was chosen as a project operating point before any controlled
experiment was conducted.
It is not derived from measured workload data.

### 4.x.2  Controlled Threshold Experiment

A controlled experiment was run to find which PSI threshold value best predicts
user-visible latency degradation on a real running workload.
The experiment followed a pre-registered protocol
(file `prereg.yaml`, SHA256 `037aefabbf43bd399e6b8e4cc4c8bde88f4cc5cfc0e669446f1981cc50f35ed5`)
frozen before any data collection.

**Signal measured.** The experiment read cgroup-level PSI directly from the
kernel interface:
`/sys/fs/cgroup/.../memory.pressure`, field `some avg10` (percent).
This is the 10-second exponential moving average of the fraction of time any
task in the cgroup was stalled waiting for memory reclaim.

**Latency label.** Degradation was labelled from external load-generator
latency measurements only.
A 5-second bin was labelled *degraded* if the externally measured p99 latency
exceeded 2.0 × B, where B = 8.66 ms is the median 5-second-bin p99 across all
calm sessions (source: `stage5_stats.json` → `baseline_B_ms`).
PSI was never used to derive the latency label.

**Sessions.** Fifteen 20-minute sessions were run: 5 calibration stress, 5 test
stress, and 5 calm (source: `session_logs/*/metadata.json`).
Every session completed with 48,000 requests, 0 errors, 0 gaps, and was not
aborted.
Total monitored time: 5.00 h.
Calibration breach events: 13.
Test breach events: 14.

**Calibration sweep.** The pre-registered T-grid
[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2, 1.5, 1.8, 2.0,
2.5, 3.0, 4.0, 5.0] percent was evaluated with k ∈ {1, 3} consecutive bins
required to fire an alert, with a 60-second cooldown after each alert.
The pre-registered selection rule chose the (T, k) pair that maximised event
recall subject to false alarms ≤ 2 per hour, with ties broken by fewer false
alarms then higher T.

Selected threshold (source: `selected.json`):

| Parameter | Value |
|-----------|-------|
| T | 1.0 % |
| k | 1 |
| Calibration recall | 0.8462 (11 / 13 events) |
| Calibration false alarms | 1 |
| Calibration FA per hour | 0.375 |
| Calibration precision | 0.9167 |
| Lead-time median | -5.0 s |
| Lead-time IQR | 0.0 s |

The negative lead time indicates the alert fires approximately 5 seconds after
breach onset, because PSI avg10 is a 10-second exponential average that rises
after the reclaim stall begins.

**Test evaluation** (source: `verdict.json`, `test_results.json`):

| Metric | T = 1.0 %, k = 1 | T = 1.8 %, k = 1 |
|--------|-------------------|-------------------|
| Test events total | 14 | 14 |
| Events detected | 10 | 1 |
| Recall | 0.7143 | 0.0714 |
| FA per hour | 0.0 | 0.0 |
| Precision | 1.0 | 1.0 |
| Wilson 95 % CI on recall | [0.4535, 0.8828] | [0.0127, 0.3147] |
| Test monitored time (h) | 2.333 | 2.333 |
| Formal verdict | UNDERPOWERED | UNDERPOWERED |

**Formal verdict.** Both evaluations received the verdict `UNDERPOWERED` because
the test monitored time (2.333 h) was below the pre-registered minimum of 3.0 h
(source: `verdict.json` → `test_hours`, `verdict`).
The UNDERPOWERED verdict overrides per `prereg.yaml` → `verdict_rule`.
The point estimates (recall = 0.71 at T = 1.0; recall = 0.07 at T = 1.8) are
reported as informational only; they do not constitute a validated finding.

### 4.x.3  Why T = 1.8 % Performs Poorly on This Hardware

On the test host (Linux, SSD-backed swap), the cgroup PSI avg10 value only
exceeds 1.8 % briefly at the onset of a fresh memory reclaim burst.
Once the kernel has moved the excess pages to the fast SSD swap device, the
per-task stall time drops and avg10 decays below 1.8 % within the first two
5-second bins.
The experiment measured PSI stress sessions reaching a maximum of 4.73 % and a
p99 of 1.45 % across all 2,400 stress-session bins
(source: session CSV files, `pod_psi_some_avg10` column).
T = 1.8 % therefore lies above the sustained steady-state range of the signal
on this workload, which explains the low recall.

### 4.x.4  Signal Mismatch Between Experiment and Production

The experiment signal and the production signal are not the same quantity.
Three mismatches are recorded:

| # | Mismatch | Consequence |
|---|----------|-------------|
| 1 | **Signal definition.** The experiment measured cgroup `memory.pressure some avg10` (%). The production service (`prediction_service.py` line 267) queries `deriv(node_pressure_memory_waiting_seconds_total{...}[2m]) * 100`, which is the rate of change of the cumulative PSI stall counter — a different quantity with a different numerical range and different dynamics. | The threshold values found by the experiment (T = 1.0 %, T = 1.8 %) do not directly apply to the production signal. A separate experiment on the Prometheus deriv signal is required to validate any threshold for production use. |
| 2 | **Training vs. inference signal.** The TFT model was trained on `psi_some_avg10` values from the dataset CSVs, which contain raw kernel avg10 readings. At inference, `PSIDataBuffer.add_sample()` stores the Prometheus deriv value under the key `psi_some_avg10`, so the model receives a quantity at inference time that it was not trained on. | Model predictions are unreliable until either (a) the inference pipeline is fixed to feed raw avg10, or (b) the model is retrained on the Prometheus deriv signal. |
| 3 | **Placeholder inference.** `make_prediction()` in `prediction_service.py` does not run the TFT model. It computes `q90 = current * 1.3` (a fixed-ratio heuristic). `SPIKE_THRESHOLD` is currently applied to this heuristic output, not to a real model prediction. | The threshold comparison is not a model-based decision. Results from model evaluation studies do not describe the current production behaviour. |

### 4.x.5  Summary Statement for the Paper

The value T = 1.8 % is a project-chosen operating point.
It was not derived from measured data and was not validated by the host
experiment.
On cgroup avg10, T = 1.8 % detected 1 of 14 test degradation events
(recall = 0.07, Wilson 95 % CI [0.013, 0.315]).
The experiment identified T = 1.0 % as the best threshold for cgroup avg10
on this workload (calibration recall = 0.85, test recall = 0.71, zero false
alarms on test), but the formal verdict is UNDERPOWERED due to insufficient
test time.
Neither result applies to the production Prometheus deriv signal.
The production signal was not tested.

---

## Deviations from Pre-Registered Protocol

The following table lists every deviation from `prereg.yaml`.
No rule was changed after seeing data; all deviations are shortfalls or
additions, not post-hoc modifications.

| # | Pre-registered requirement | Actual outcome | Reason |
|---|---------------------------|----------------|--------|
| 1 | CAL breach events ≥ 15 | 13 events | Ramp and step profiles each produce one sustained merged breach event rather than multiple discrete events; burst profile cycle 1 startup spike merged with first ON phase. No rule was modified. |
| 2 | TEST monitored time ≥ 3.0 h | 2.333 h | Sessions 16–19 (added to reach event target) were not completed. The PSI signal on this host could not be reliably driven above 1.8 % in later sessions due to SSD-backed swap speed. |
| 3 | Bootstrap (Stage 7, 2000 iterations, seed fixed) | Not computed | UNDERPOWERED verdict is deterministic from test time < 3 h; bootstrap cannot change it. Recorded as an omission. |
| 4 | T-grid: [0.5, 1.0, 1.5, 1.8, 2.0, 2.5, 3.0, 4.0, 5.0] | Extended to [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2, 1.5, 1.8, 2.0, 2.5, 3.0, 4.0, 5.0] | Observed PSI range (0–4.73 %) lies mostly below 1.5 %; the original grid had no resolution in that range. Additive extension only; original grid is a strict subset. |
| 5 | PSI gate: alert fires on cgroup PSI or node PSI (per prereg pilot gate P1) | Calm PSI was 0.0000 % on all 1,200 calm bins; node PSI not separately evaluated | On this host the signal range makes the distinction moot for T ≥ 0.1 %, but it was not formally checked per the gate P1 node-PSI criterion. |

---

## Artifact Locations

| Artifact | Path |
|----------|------|
| Pre-registered rules | `experiments/psi_threshold_validation/prereg.yaml` |
| Signal definitions | `experiments/psi_threshold_validation/signal_definitions.json` |
| Calibration sweep | `experiments/psi_threshold_validation/calibration_sweep.json` |
| Selected threshold | `experiments/psi_threshold_validation/selected.json` |
| Test results | `experiments/psi_threshold_validation/test_results.json` |
| Verdict | `experiments/psi_threshold_validation/verdict.json` |
| Session metrics | `experiments/psi_threshold_validation/session_logs/*/metrics.csv` |
| Session requests | `experiments/psi_threshold_validation/session_logs/*/requests.csv` |
| Full experiment log | `experiment_log.md` |
| Production threshold | `kubernetes/phase6/prediction_service.py` line 78 |
| Production configmap | `kubernetes/phase6/configmap.yaml` line 17 |
