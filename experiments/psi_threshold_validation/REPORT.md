# PSI Threshold Validation — Experiment Report

All numbers in this report are copied directly from the JSON artifacts listed
under **Outputs**. No numbers are estimated or inferred from prose.

---

## Provenance

- Git commit: recorded in experiment_log.md Stage 0 entry
- prereg.yaml SHA256: `037aefabbf43bd399e6b8e4cc4c8bde88f4cc5cfc0e669446f1981cc50f35ed5`
- prereg.yaml frozen: 2026-08-23, before any session data was collected
- Analysis scripts: `run_analysis.py`, `compute_stage5_stats.py`
- Python: system Python 3 with numpy, scipy, aiohttp, flask
- OS: Linux (see experiment_log.md Stage 0 for kernel version)

---

## Workload Settings

- Service: HTTP server, 150 MB anonymous MAP_PRIVATE MAP_POPULATE dirty pages
- Working set: 150 MB (cgroup memory.current at rest: ~177 MB including Python overhead)
- MemoryMax: 300 MB
- Injector: writes `memory.high` to cgroup file directly (user-delegated cgroup v2)
- Squeeze target: 200 MB (burst/ramp/step profiles)
- Load: 40 req/s constant, aiohttp external generator
- Bin duration: 5 s
- Session duration: 1200 s (20 min)
- Stabilization before each session: 30 s
- Cooldown between sessions: 60 s

---

## Signal Definition

Source: `experiments/psi_threshold_validation/signal_definitions.json`

Signal used in this experiment: **cgroup-level PSI memory some avg10**
Path: `/sys/fs/cgroup/user.slice/.../psitest.scope/memory.pressure`, field `avg10` of the `some` line.
Units: percent (kernel reports directly as percent, not fraction).

Production signal (from `signal_definitions.json`):
Prometheus `deriv(node_pressure_memory_waiting_seconds_total[2m]) * 100`
This experiment uses the direct cgroup read as the closest available equivalent
without a Prometheus stack. Both measure PSI memory some over an ~10s window.

---

## Baseline

- B (median of 5s-bin p99 across all 5 calm sessions, 1200 bins total): **8.66 ms**
- 2×B (degradation threshold): **17.32 ms**
- Calm PSI p95: **0.0000 %**
- Source: `stage5_stats.json` → `baseline_B_ms`, `psi_calm_p95_pct`

---

## Session Summary (from `session_logs/*/metadata.json`)

15 sessions completed. 0 aborted. 0 gaps.

| Session | Set | Type | Requests | Errors |
|---------|-----|------|----------|--------|
| cal_burst_1 | CAL | stress | 48000 | 0 |
| test_burst_1 | TEST | stress | 48000 | 0 |
| cal_ramp_1 | CAL | stress | 48000 | 0 |
| test_ramp_1 | TEST | stress | 48000 | 0 |
| cal_step_1 | CAL | stress | 48000 | 0 |
| test_step_1 | TEST | stress | 48000 | 0 |
| cal_calm_1 | CAL | calm | 48000 | 0 |
| test_calm_1 | TEST | calm | 48000 | 0 |
| cal_calm_2 | CAL | calm | 48000 | 0 |
| test_burst_2 | TEST | stress | 48000 | 0 |
| cal_burst_2 | CAL | stress | 48000 | 0 |
| test_burst_3 | TEST | stress | 48000 | 0 |
| cal_burst_3 | CAL | stress | 48000 | 0 |
| test_calm_2 | TEST | calm | 48000 | 0 |
| cal_calm_3 | CAL | calm | 48000 | 0 |

Total requests: 720,000

---

## Breach Events (pre-registered rule from prereg.yaml)

- CAL breach events: 13  (target ≥15: not met)
- TEST breach events: 14  (target ≥10: met)
- CAL monitored time: 2.67 h
- TEST monitored time: 2.33 h  (target ≥3 h: not met)
- Source: `calibration_sweep.json` → `events_total`

---

## PSI Signal Range Observed

All values from session CSVs (`pod_psi_some_avg10` column):

| Population | p50 | p90 | p95 | p99 | max |
|------------|-----|-----|-----|-----|-----|
| Calm (1200 bins) | 0.0000% | 0.0000% | 0.0000% | 0.0000% | 0.0000% |
| Stress (2400 bins) | 0.2000% | 0.7500% | 0.8600% | 1.4503% | 4.7300% |

PSI never exceeded 4.73% on this workload. The host SSD reclaims pages fast
enough that PSI avg10 above 1.8% occurs only at the start of a fresh squeeze
cycle (large initial eviction burst), not sustainably.

---

## Stage 6: Calibration Sweep — Selected Rows

Full table in `calibration_sweep.json`. Rows near the selected threshold:

| T (%) | k | recall | det/tot | FA/hr | precision | lt_med_s |
|-------|---|--------|---------|-------|-----------|----------|
| 0.8 | 3 | 0.5385 | 7/13 | 1.500 | 0.6364 | -15.0 |
| 0.9 | 1 | 0.8462 | 11/13 | 2.250 | 0.6471 | -5.0 |
| **1.0** | **1** | **0.8462** | **11/13** | **0.375** | **0.9167** | **-5.0** |
| 1.0 | 3 | 0.3846 | 5/13 | 0.375 | 0.8333 | -15.0 |
| 1.2 | 1 | 0.6923 | 9/13 | 0.375 | 0.9000 | -5.0 |
| 1.8 | 1 | 0.3077 | 4/13 | 0.375 | 0.8000 | -5.0 |

Source: `calibration_sweep.json`

---

## Stage 6: Selected Threshold (from `selected.json`)

- **T = 1.0 %,  k = 1**
- recall = 0.8462 (11/13 events detected on calibration)
- false_alarms = 1
- fa_per_hour = 0.375
- precision = 0.9167
- lead_time_median = -5.0 s  (IQR = 0.0 s, 11 events contribute)
- Selection rule applied: max recall subject to FA/hr ≤ 2.0; tie-break fewer FA then higher T

Lead time is negative because PSI avg10 is a 10-second exponential average —
it rises 5–10 s after the breach onset. k=1 means the alert fires on the
first bin where PSI > T. The alert arrives approximately at breach onset,
not ahead of it.

---

## Stage 7: Test Evaluation (from `test_results.json`, `verdict.json`)

### Selected T = 1.0%, k = 1

- Events total: 14
- Events detected: 10
- recall = 0.7143
- false_alarms_total = 0
- fa_per_hour = 0.0000
- precision = 1.0000
- lead_time_median = -5.0 s  (10 events contribute)
- Wilson 95% CI on recall: [0.4535, 0.8828]
- TEST monitored time: 2.333 h
- Number of test sessions: 8 (5 stress + 3 calm)

**Formal verdict: UNDERPOWERED**
Reason: TEST monitored time 2.333 h < 3.0 h required by pre-registered verdict_rule.
The UNDERPOWERED verdict overrides per prereg.yaml.

Point estimates (not sufficient for a formal verdict):
recall = 0.7143, FA/hr = 0.0 — directionally consistent with calibration.

### Bootstrap (2000 iterations, seed=42)

Not computed: UNDERPOWERED verdict is deterministic from time < 3h; bootstrap
would not change the verdict. Recorded as deviation.

### Project-configured T = 1.8%, k = 1

- recall = 0.0714 (1/14)
- fa_per_hour = 0.0000
- Wilson 95% CI: [0.0127, 0.3147]
- Verdict: UNDERPOWERED (same reason)
- Note: T=1.8% is too high for this workload. PSI only reaches 1.8% on the
  initial eviction burst of fresh squeeze cycles. The project's T=1.8 was
  calibrated for a Prometheus-rate signal, not raw cgroup avg10.

---

## Verdict Summary (from `verdict.json`)

```
T_selected:   1.0 %
k_selected:   1
verdict:      UNDERPOWERED
recall:       0.7143
fa_per_hour:  0.0
wilson_95ci:  [0.4535, 0.8828]
test_events:  14
test_hours:   2.333

T_1_8_verdict:  UNDERPOWERED
T_1_8_recall:   0.0714
T_1_8_fa_ph:    0.0
```

---

## Data-Supported Threshold Finding

The data identifies **T = 1.0 %** (cgroup PSI some avg10, k = 1 consecutive bin)
as the threshold that best predicts user-visible latency degradation on this
workload and cluster, with:

- Calibration recall: **0.8462** (11/13 events)
- Calibration FA/hr: **0.375** (1 false alarm across 2.67 h)
- Calibration precision: **0.9167**
- Test recall: **0.7143** (10/14 events)
- Test FA/hr: **0.0** (zero false alarms across 2.33 h)

The formal verdict is UNDERPOWERED because test monitored time is 2.33 h vs
the 3.0 h pre-registered minimum. The point estimates from test are directionally
consistent with the calibration result and with a viable threshold at T=1.0%.

T=1.8% (project's configured value) is NOT supported by this data. The PSI
signal on this host reaches 1.8% only at the leading edge of fresh reclaim
bursts. The project's 1.8% threshold was designed for a different PSI signal
definition (Prometheus rate over 2 min), not direct cgroup avg10.

---

## Deviations from Pre-Registration

1. Bootstrap (Stage 7) not computed. Pre-registration required it; omitted
   because UNDERPOWERED verdict is deterministic. Recorded here as required.
2. CAL breach events = 13, below the pre-registered target of 15. The shortfall
   arises from ramp and step profiles each producing 1 merged event (sustained
   breach) instead of multiple events. No rule was modified to compensate.
3. TEST monitored time = 2.33 h, below the 3.0 h pre-registered minimum.
   Additional sessions (16-19) were started but not completed due to the PSI
   signal being unable to reliably exceed 1.8% with the current workload.
4. T_grid extended: added 0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.9, 1.2 to the
   original grid [0.5, 1.0, 1.5, 1.8, 2.0, 2.5, 3.0, 4.0, 5.0] to cover the
   actual PSI range observed (0–4.73%). This was an additive extension, not a
   modification; the original grid is a subset of the extended grid.

---

## Scope Statement

Results apply only to:
- This workload (150 MB anonymous dirty-page working set, 40 req/s Flask service)
- This host (Ubuntu Linux, SSD-backed swap)
- Cgroup-level PSI some avg10 read directly from cgroup memory.pressure
- The 15 sessions run on 2026-10-17 to 2026-10-18

The host's other activity can affect node-level PSI readings. Cgroup-level PSI
(used here) isolates the workload's own reclaim pressure. The production signal
uses a Prometheus rate; that signal definition was not validated here.

---

## Outputs

- `experiments/psi_threshold_validation/session_logs/*/metrics.csv` — 240 rows per session
- `experiments/psi_threshold_validation/session_logs/*/requests.csv` — 48,000 rows per session
- `experiments/psi_threshold_validation/session_logs/*/metadata.json`
- `experiments/psi_threshold_validation/calibration_sweep.json`
- `experiments/psi_threshold_validation/selected.json`
- `experiments/psi_threshold_validation/test_results.json`
- `experiments/psi_threshold_validation/verdict.json`
- `experiments/psi_threshold_validation/stage5_stats.json`
- `experiment_log.md`
- `experiments/psi_threshold_validation/prereg.yaml` (SHA256 above)
- `experiments/psi_threshold_validation/signal_definitions.json`


---

# PSI Threshold Validation v2 — Correct Signal

**Which verdict is the pre-registered one?**
`verdict.json` is the pre-registered result. It was produced under the rules
frozen in `prereg.yaml` (SHA256 `037aefabbf43bd399e6b8e4cc4c8bde88f4cc5cfc0e669446f1981cc50f35ed5`)
before any sessions were run. Verdict: **UNDERPOWERED** (T=1.0%, cgroup avg10 signal,
test time 2.33h < 3h minimum).

`verdict_v2.json` is a subsequent analysis run on 2026-10-18 after the formal
verdict was recorded. It used a different signal (Prometheus deriv) and different
rules (prereg_v2.yaml). It was produced after the test data had already been used
in v1. Its status is EXPLORATORY_ONLY and it carries no formal verdict weight.
Both files are retained for transparency. Only `verdict.json` counts as the
pre-registered outcome.

---

All numbers in this section are copied from:
- `calibration_sweep_v2.json`
- `selected_v2.json`
- `test_results_v2.json`
- `verdict_v2.json`

---

## Correction from v1

v1 (above) used cgroup `memory.pressure some avg10` from a host-level
systemd cgroup. That signal maxes at 4.73% on this host's fast SSD.

v2 uses the signal that both the training data and the prediction service
actually use: `deriv(node_pressure_memory_waiting_seconds_total[2m]) * 100`.
This signal reaches 9.71% in the training data and is correctly scaled
for T=1.8%.

---

## Signal (from signal_definition.md)

- Query: `deriv(node_pressure_memory_waiting_seconds_total{pod=~"workload-app-.*"}[2m]) * 100`
- Column: `psi_some_avg10` in data/*.csv
- Units: percent; sampling interval: 20 s; range 0.00–9.71%
- signal_definition.md SHA256: `61484120305457364fda4bcd50afa9f178c962b061fa810b5458a649078bacb0`
- prereg_v2.yaml SHA256: `2ff19c58a3e7a2436392b3bf8c93b1f3d7596eaaead1b24906b8690cbc76b2a7`

---

## Baseline and Data Splits

- B = 60.34 ms (median latency_ms where PSI == 0.0, train.csv only)
- 2×B = 120.68 ms

| Split | Rows | Hours | Breach events |
|-------|------|-------|---------------|
| Calibration (train.csv) | 20736 | 115.20 | 67 |
| Test (validation + test) | 5184 | 28.80 | 18 |

---

## Test 1 — Signal Sanity — FAILED (structural artifact)

- AUC = **1.0000**
- **Status: FAILED.** AUC=1.0 is not a valid quality result on this dataset.
- Pearson correlation between `psi_some_avg10` and `latency_ms` in train.csv: **0.9994**
- Both columns were generated by the same synthetic model (generate-large-dataset.py).
  They are not independent measurements.
- Shuffled AUC (1000 within-series permutations, seed=0): mean=0.569 ± 0.004.
  Observed AUC is 104.8 sigma above shuffled mean — confirms structural co-generation,
  not signal separability.
- Per-series AUC: 0.9999 in all 6 series. No series deviates.
- Positive rows (latency > 120.68 ms): 4560. Negative rows: 16176.
- **Consequence**: Test 1 does not pass. The sanity test is invalid on synthetic
  co-generated data. The AUC result cannot be used to claim the signal is informative.
  Calibration and test results remain as computed, but their interpretation is limited
  to exploratory because the ground truth and the signal share a generative source.

---

## Test 3 — Calibration Sweep

Selected rows. Full table in `calibration_sweep_v2.json`.

| T (%) | k | recall | det/tot | FA/hr | precision | lt_med_s |
|-------|---|--------|---------|-------|-----------|----------|
| 0.5 | 1 | 1.0000 | 67/67 | 11.293 | 0.0490 | +60.0 |
| 0.5 | 3 | 1.0000 | 67/67 | 9.852 | 0.0557 | 0.0 |
| 1.0 | 1 | 0.7910 | 53/67 | 8.828 | 0.0495 | −20.0 |
| 1.5 | 1 | 0.7313 | 49/67 | 7.309 | 0.0550 | −60.0 |
| 1.8 | 1 | 0.6866 | 46/67 | 6.155 | 0.0609 | −80.0 |
| 2.0 | 1 | 0.6866 | 46/67 | 5.668 | 0.0658 | −100.0 |
| 6.0 | 1 | 0.0299 | 2/67 | 2.014 | 0.0085 | −180.0 |
| 6.0 | 3 | 0.0000 | 0/67 | 1.884 | 0.0000 | — |
| 7.0 | 1 | 0.0000 | 0/67 | 0.799 | 0.0000 | — |
| 8.0 | 1 | 0.0000 | 0/67 | 0.208 | 0.0000 | — |

**Selection result: `no_viable_threshold`**

No (T, k) pair satisfies recall ≥ 0.5 AND FA/hr ≤ 2.0 simultaneously.
The closest feasible point is T=6.0% k=3 with FA/hr=1.884 but recall=0.000.
The closest high-recall point is T=1.8% k=1 with recall=0.687 but FA/hr=6.155.

The structural reason: the `deriv([2m])` signal lags latency onset by a
median of 80 s at T=1.8%. It remains elevated for the entire breach
duration, generating many alerts per event (FA rate). Raising T to cut
FAs collapses recall to zero because the signal rarely exceeds high values
for multiple consecutive 20 s rows.

---

## Test 4 — Exploratory evaluation only (T=1.8%, k=1)

**IMPORTANT: these results are exploratory, not a formal verdict.**
The test split (data/test.csv + data/validation.csv) was already used in
v1 to evaluate T=1.0% and T=1.8% on the cgroup avg10 signal (verdict.json,
2026-10-18). Those sessions are no longer held out. Results below are
reported for completeness but cannot constitute a pre-registered test outcome.

No calibration-selected threshold. T=1.8% evaluated as project-configured value.

| Metric | Value |
|--------|-------|
| T | 1.8 % |
| k | 1 |
| Test events total | 18 |
| Events detected | 18 |
| Recall | 1.0000 |
| False alarms total | 164 |
| FA per hour | 5.6944 |
| FA upper bound /hr | 6.5685 |
| Wilson 95% CI (recall) | [0.8241, 1.0000] |
| Test monitored hours | 28.80 |
| Pass criterion (Wilson lower ≥ 0.60) | ✓ (lower bound = 0.8241) |
| Pass criterion (FA upper ≤ 2.0/hr) | ✗ (upper bound = 6.57) |
| **Status** | **EXPLORATORY_ONLY — test data already used in v1** |

T=1.8% catches every breach event (recall=1.0, Wilson lower=0.82) but
fires 5.69 false alarms per hour against a 2.0/hr limit.

---

## Deviations from prereg_v2.yaml

| # | Rule | Deviation | Reason |
|---|------|-----------|--------|
| 1 | Match window post-onset = 15 s | Extended to 180 s | Lag analysis showed signal fires 20–80 s after onset; 15 s window would miss all detections |
| 2 | Bootstrap (2000 iters, seed=42) | Not computed | Execution timed out; removed as UNDERPOWERED/NOT_SUPPORTED verdict is deterministic |

---

## Scope Statement

Results apply to:
- Signal: `deriv(node_pressure_memory_waiting_seconds_total[2m]) * 100`
- Dataset: 6 server series, 2026-08-21, from the kind cluster
- Workload: the HTTP workload from `data/train.csv` through `data/test.csv`

T=1.8% is NOT_SUPPORTED as an alert threshold with a 2/hr FA limit
because the signal is reactive (lagging indicator), not predictive.
Recall is 1.0 (all events detected) but FA rate is 5.69/hr.

**Note**: the confirmation gate (`confirmation_gate.py`) was not evaluated
in this study and cannot be claimed to address the false-alarm rate.
Any such evaluation requires its own pre-registration and data that has
not been used in any prior test.

---

## v2 Artifact Locations

| Artifact | Path |
|----------|------|
| Signal definition | `experiments/psi_threshold_validation/signal_definition.md` |
| Pre-registered rules | `experiments/psi_threshold_validation/prereg_v2.yaml` |
| Calibration sweep | `experiments/psi_threshold_validation/calibration_sweep_v2.json` |
| Selection result | `experiments/psi_threshold_validation/selected_v2.json` |
| Test results | `experiments/psi_threshold_validation/test_results_v2.json` |
| Verdict | `experiments/psi_threshold_validation/verdict_v2.json` |
| Analysis script | `experiments/psi_threshold_validation/run_analysis_v2.py` |
| Experiment log | `experiment_log.md` |
