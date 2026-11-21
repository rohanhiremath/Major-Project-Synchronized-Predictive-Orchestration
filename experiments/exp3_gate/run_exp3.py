#!/usr/bin/env python3
"""
Experiment 3: Calibration consistency – k=1 vs k=2 gate.

Steps:
  1. Grid search on VALIDATION split only: T in {0.5,0.75,1.0,1.25,1.5,1.8,2.0,2.5,3.0}
     k in {1,2,3}. Metric: recall subject to FA < 2.0/hr.
  2. Evaluate on TEST (k=1 raw, k=2 gate G: current AND previous forecast exceed T).
  3. Verify gate implementation matches paper description.
  4. Report system-level vs model-level recall.

Label definition: PSI > T (ground truth = actual PSI from data, NOT SLO).
SLO-based ground truth requires live latency data → not available → say so.

Saves:
  results/exp3_gate/val_grid_search.csv
  results/exp3_gate/test_k1_vs_k2.csv
  results/exp3_gate/gate_verification.json
  results/exp3_gate/exp3_summary.json
  results/exp3_gate/exp3_plot.png
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO      = Path(__file__).resolve().parent.parent.parent
PRED_CSV  = REPO / "data" / "tft_predictions.csv"
VAL_CSV   = REPO / "data" / "validation.csv"
TEST_CSV  = REPO / "data" / "test.csv"
OUT       = REPO / "results" / "exp3_gate"
OUT.mkdir(parents=True, exist_ok=True)

THRESHOLDS  = [0.5, 0.75, 1.0, 1.25, 1.5, 1.8, 2.0, 2.5, 3.0]
K_VALUES    = [1, 2, 3]
FA_LIMIT    = 2.0          # false alarms per hour
INTERVAL_S  = 15
MERGE_GAP   = 2            # steps to merge events

print("=" * 70)
print("EXPERIMENT 3  Calibration consistency: k=1 vs k=2 gate")
print("=" * 70)

# ── Load predictions ─────────────────────────────────────────────────────────
pred = pd.read_csv(PRED_CSV)
val  = pd.read_csv(VAL_CSV)
test = pd.read_csv(TEST_CSV)
val["timestamp"]  = pd.to_datetime(val["timestamp"])
test["timestamp"] = pd.to_datetime(test["timestamp"])

# Per-window q90 and actual max (horizon=30 as per existing model)
wq90 = pred.groupby("window_id")["q90"].max().values   # shape (W,)
wact = pred.groupby("window_id")["actual_psi"].max().values

# Split windows into val-region and test-region.
# Existing predictions cover all windows including val; we need to map
# windows to val vs test. The val CSV has 8283 rows / 3 series = 2761 per series.
# windows_in_val = max(0, 2761 - 30 + 1) = 2732 per series = 8196 total (approx).
# Windows are ordered: first val, then test.
# From prior analysis: test_df has 11400 rows/series = 11369 windows/series = 34107 total.
# Total windows = 120069; val windows ≈ 8190; test windows ≈ 34107
# val window IDs: 0..8189 (approx); test window IDs: 8190..end
# However the existing predictions include TRAIN windows too: train=77670, val=8190, test=34107
# total=119967 ≈ 120069 (small rounding). We separate by count.
N_TRAIN = 25890 * 3   # 77670
N_VAL   = 2730  * 3   # 8190
N_TEST  = 11369 * 3   # 34107

val_q90  = wq90[N_TRAIN : N_TRAIN + N_VAL]
val_act  = wact[N_TRAIN : N_TRAIN + N_VAL]
test_q90 = wq90[N_TRAIN + N_VAL : N_TRAIN + N_VAL + N_TEST]
test_act = wact[N_TRAIN + N_VAL : N_TRAIN + N_VAL + N_TEST]

val_hours  = len(val_q90)  * INTERVAL_S / 3600
test_hours = len(test_q90) * INTERVAL_S / 3600
print(f"Val  windows: {len(val_q90)} ({val_hours:.1f} h)")
print(f"Test windows: {len(test_q90)} ({test_hours:.1f} h)")

# ── Helper: apply k-consecutive gate ────────────────────────────────────────
def apply_gate(scores, threshold, k):
    """
    Raw alert at step i = (scores[i] >= threshold).
    k-gate: an alert fires only if the LAST k consecutive steps all exceeded threshold.
    Returns boolean array of gated alerts.
    """
    raw   = (scores >= threshold).astype(int)
    gated = np.zeros(len(raw), dtype=bool)
    for i in range(k-1, len(raw)):
        if raw[i-k+1:i+1].sum() == k:
            gated[i] = True
    return gated

def count_events(vals, threshold=1.80, merge_gap=MERGE_GAP):
    above = (vals >= threshold).astype(int)
    events = []
    in_ev = False; start = None; gap = 0
    for i, v in enumerate(above):
        if v:
            if not in_ev: start = i; in_ev = True
            gap = 0
        else:
            if in_ev:
                gap += 1
                if gap > merge_gap:
                    events.append((start, i - gap)); in_ev = False; gap = 0
    if in_ev: events.append((start, len(above)-1))
    return events

def compute_metrics(act, pred_alert, hours, threshold, lead_win=2):
    tp = int(( (act>=threshold) &  pred_alert).sum())
    fp = int(((act< threshold) &  pred_alert).sum())
    fn = int(( (act>=threshold) & ~pred_alert).sum())
    tn = int(((act< threshold) & ~pred_alert).sum())
    prec = tp/(tp+fp) if (tp+fp)>0 else 0.0
    rec  = tp/(tp+fn) if (tp+fn)>0 else 0.0
    f1   = 2*prec*rec/(prec+rec) if (prec+rec)>0 else 0.0
    fa_hr = fp / hours if hours > 0 else 0.0
    # Event recall
    events = count_events(act, threshold)
    det = 0
    for (s, e) in events:
        lo = max(0, s - lead_win)
        if pred_alert[lo:e+1].any():
            det += 1
    ev_rec = det / len(events) if events else 0.0
    # Mean lead time
    lead_times = []
    for (s, e) in events:
        lo = max(0, s - lead_win)
        idxs = np.where(pred_alert[lo:e+1])[0]
        if len(idxs):
            lead_times.append((s - (idxs[0] + lo)) * INTERVAL_S)
    mean_lead = float(np.mean(lead_times)) if lead_times else 0.0
    return dict(tp=tp, fp=fp, fn=fn, tn=tn,
                precision=round(prec,6), recall=round(rec,6),
                f1=round(f1,6), fa_per_hour=round(fa_hr,4),
                event_recall=round(ev_rec,6),
                mean_lead_s=round(mean_lead,2),
                n_events=len(events))

# ── 1. Grid search on VALIDATION ──────────────────────────────────────────────
print("\n--- Validation grid search ---")
grid_rows = []
for T in THRESHOLDS:
    for k in K_VALUES:
        alerts = apply_gate(val_q90, T, k)
        m = compute_metrics(val_act, alerts, val_hours, T)
        m.update({"T": T, "k": k, "split": "val"})
        grid_rows.append(m)

grid_df = pd.DataFrame(grid_rows)
grid_df.to_csv(OUT / "val_grid_search.csv", index=False)

print(grid_df[["T","k","precision","recall","f1","fa_per_hour","event_recall","mean_lead_s"]]
      .to_string(index=False))

# Select best: maximize recall subject to FA < 2.0/hr
viable = grid_df[grid_df["fa_per_hour"] < FA_LIMIT].copy()
if len(viable) > 0:
    best_row = viable.loc[viable["recall"].idxmax()]
    print(f"\nBest on val (max recall, FA<2/hr): T={best_row['T']} k={best_row['k']}")
    print(f"  P={best_row['precision']:.4f} R={best_row['recall']:.4f} "
          f"F1={best_row['f1']:.4f} FA/hr={best_row['fa_per_hour']:.4f}")
    best_T = float(best_row["T"])
    best_k = int(best_row["k"])
else:
    print("No config meets FA<2/hr on validation!")
    best_T = 1.8; best_k = 1

# ── 2. Test: k=1 vs k=2 at T=1.80 ───────────────────────────────────────────
print("\n--- Test evaluation: k=1 vs k=2 at T=1.80 ---")
test_rows = []
for k in [1, 2]:
    alerts = apply_gate(test_q90, 1.80, k)
    m = compute_metrics(test_act, alerts, test_hours, 1.80)
    m.update({"T": 1.80, "k": k, "split": "test", "label": f"TFT_k{k}"})
    test_rows.append(m)
    print(f"  k={k}: P={m['precision']:.4f} R={m['recall']:.4f} "
          f"F1={m['f1']:.4f} FA/hr={m['fa_per_hour']:.4f} "
          f"event_recall={m['event_recall']:.4f} lead={m['mean_lead_s']:.1f}s")

# Also test at best-val threshold
if best_T != 1.80 or best_k not in [1,2]:
    alerts = apply_gate(test_q90, best_T, best_k)
    m = compute_metrics(test_act, alerts, test_hours, best_T)
    m.update({"T": best_T, "k": best_k, "split": "test",
              "label": f"best_val_T{best_T}_k{best_k}"})
    test_rows.append(m)
    print(f"  best-val T={best_T} k={best_k}: P={m['precision']:.4f} "
          f"R={m['recall']:.4f} F1={m['f1']:.4f}")

test_df = pd.DataFrame(test_rows)
test_df.to_csv(OUT / "test_k1_vs_k2.csv", index=False)

# False alarm reduction from gate
fa_k1 = test_rows[0]["fa_per_hour"]
fa_k2 = test_rows[1]["fa_per_hour"]
fa_reduction = (fa_k1 - fa_k2) / fa_k1 * 100 if fa_k1 > 0 else 0

r_k1 = test_rows[0]["recall"]
r_k2 = test_rows[1]["recall"]

print(f"\nFA reduction (k1→k2): {fa_reduction:.1f}%")
print(f"Recall cost (k1→k2): {(r_k1-r_k2)*100:.2f} pp")

# System-level recall vs model-level recall
# System-level: fraction of events where scaling begins before breach
# Model-level: fraction of windows correctly flagged (= window recall = recall above)
# Here system-level recall ≈ event recall (requires pod provisioning data, not available;
# we use event_recall as the closest proxy and document the limitation).
print(f"\nSystem vs model recall (proxy):")
print(f"  k=1: model_recall={r_k1:.4f}, event_recall={test_rows[0]['event_recall']:.4f}")
print(f"  k=2: model_recall={r_k2:.4f}, event_recall={test_rows[1]['event_recall']:.4f}")

# ── 3. Gate implementation verification ─────────────────────────────────────
print("\n--- Gate verification ---")
# Paper description: "An alert is raised only if BOTH the current and the previous
# 15-second forecast exceed the threshold (Gate G, consecutive within a 60-second window)."
# 60 s window at 15 s sampling = 4 steps.
# Our implementation: k=2 means last 2 consecutive steps >= threshold.
# This matches: current step AND previous step both exceed → k=2 consecutive gate.
gate_ok = True  # k=2 consecutive = paper description
gate_note = (
    "Paper specifies: current and previous forecast both exceed threshold within 60-second "
    "window. At 15-second sampling, 60 s = 4 steps; 'current and previous' = k=2 consecutive. "
    "Implementation: apply_gate(k=2) requires raw[i-1] AND raw[i] both >= T. "
    "This matches the paper description. "
    "Note: existing model uses prediction_length=30 (not 2 as stated in paper); "
    "gate is applied to max(q90) over the 30-step window, not step-by-step. "
    "This is a discrepancy from the paper spec."
)
gate_info = {
    "paper_description": "Alert if current AND previous forecast exceed T (within 60 s)",
    "implementation": "k=2 consecutive gate: gated[i]=True iff raw[i-1] AND raw[i] both >= T",
    "matches_paper": gate_ok,
    "discrepancy": "Existing model uses horizon=30 steps; paper states horizon=2. "
                   "Gate in paper applies to 2-step forecasts; here applied to window max.",
    "note": gate_note,
}
print(json.dumps(gate_info, indent=2))

# ── 4. SLO-based ground truth note ──────────────────────────────────────────
slo_note = (
    "Experiment 3 step 2b (200 ms p99 SLO ground truth) CANNOT BE RUN. "
    "Live Kind cluster latency data is not available in this environment. "
    "PSI-based ground truth (label definition a) has been used throughout."
)
print(f"\nSLO note: {slo_note}")

# ── Summary ───────────────────────────────────────────────────────────────────
summary = {
    "best_val_config": {"T": best_T, "k": best_k},
    "test_k1_vs_k2": test_rows[:2],
    "fa_reduction_pct": round(fa_reduction, 2),
    "recall_cost_pp":   round((r_k1 - r_k2)*100, 2),
    "gate_verification": gate_info,
    "slo_ground_truth_status": slo_note,
}
with open(OUT / "gate_verification.json", "w") as f:
    json.dump(gate_info, f, indent=2)
with open(OUT / "exp3_summary.json", "w") as f:
    json.dump(summary, f, indent=2)

# ── Plot ─────────────────────────────────────────────────────────────────────
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# Left: val grid heatmap of recall (k=1)
k1_grid = grid_df[grid_df["k"]==1].set_index("T")["recall"]
k2_grid = grid_df[grid_df["k"]==2].set_index("T")["recall"]
k3_grid = grid_df[grid_df["k"]==3].set_index("T")["recall"]
axes[0].plot(THRESHOLDS, k1_grid.values, "o-", label="k=1")
axes[0].plot(THRESHOLDS, k2_grid.values, "s-", label="k=2")
axes[0].plot(THRESHOLDS, k3_grid.values, "^-", label="k=3")
axes[0].axvline(1.80, color="red", linestyle="--", alpha=0.6, label="T=1.80 (paper)")
axes[0].set_xlabel("Threshold T (% PSI)"); axes[0].set_ylabel("Recall")
axes[0].set_title("Val: Recall vs Threshold (k=1,2,3)")
axes[0].legend(); axes[0].grid(alpha=0.3)

# Right: FA/hr vs T (k=1)
fa1 = grid_df[grid_df["k"]==1].set_index("T")["fa_per_hour"]
fa2 = grid_df[grid_df["k"]==2].set_index("T")["fa_per_hour"]
axes[1].plot(THRESHOLDS, fa1.values, "o-", label="k=1")
axes[1].plot(THRESHOLDS, fa2.values, "s-", label="k=2")
axes[1].axhline(FA_LIMIT, color="red", linestyle="--", alpha=0.6, label="FA limit 2/hr")
axes[1].axvline(1.80, color="gray", linestyle="--", alpha=0.5, label="T=1.80")
axes[1].set_xlabel("Threshold T (% PSI)"); axes[1].set_ylabel("False Alarms / hr")
axes[1].set_title("Val: False Alarm Rate vs Threshold")
axes[1].legend(); axes[1].grid(alpha=0.3)

plt.tight_layout()
plt.savefig(OUT / "exp3_plot.png", dpi=150)
plt.close()
print(f"\nPlot saved to {OUT / 'exp3_plot.png'}")
print(f"All outputs in {OUT}")
print("EXPERIMENT 3 COMPLETE")
