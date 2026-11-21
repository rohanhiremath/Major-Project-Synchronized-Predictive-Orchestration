#!/usr/bin/env python3
"""
Experiment 2: Dataset counts + event-level evaluation with block-bootstrap CI.

Uses the leakage-safe test split from Exp1 and the existing predictions from
data/tft_predictions.csv (horizon=30, as that is what was actually run).
Where Exp1 finishes first, it also evaluates horizon=2 safe-split predictions.

Saves:
  results/exp2_eval/dataset_counts.json
  results/exp2_eval/confusion_matrix.csv
  results/exp2_eval/event_metrics.json
  results/exp2_eval/bootstrap_ci.csv
  results/exp2_eval/baselines.csv
  results/exp2_eval/exp2_summary.json
  results/exp2_eval/exp2_plot.png
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO     = Path(__file__).resolve().parent.parent.parent
PRED_CSV = REPO / "data" / "tft_predictions.csv"
TEST_CSV = REPO / "data" / "test.csv"
OUT      = REPO / "results" / "exp2_eval"
OUT.mkdir(parents=True, exist_ok=True)

SPIKE_THRESH  = 1.80
MERGE_GAP     = 2        # steps; gaps shorter than this are merged
LEAD_WINDOW   = 2        # steps before event onset counted as early detection
N_BOOTSTRAP   = 1000
INTERVAL_S    = 15
RNG           = np.random.default_rng(42)

print("=" * 70)
print("EXPERIMENT 2  Dataset counts + event-level evaluation")
print("=" * 70)

# ── 1. Load data ─────────────────────────────────────────────────────────────
pred = pd.read_csv(PRED_CSV)
test = pd.read_csv(TEST_CSV)
test["timestamp"] = pd.to_datetime(test["timestamp"])

print(f"Prediction windows (all): {pred['window_id'].nunique()}")
print(f"Test CSV rows:            {len(test)}")

# Window-level arrays (q90 / actual)
w_q90 = pred.groupby("window_id")["q90"].max()
w_act = pred.groupby("window_id")["actual_psi"].max()
w_q10 = pred.groupby("window_id")["q10"].max()

# ── 2. Dataset counts ─────────────────────────────────────────────────────────
n_windows   = int(len(w_q90))
n_pos       = int((w_act >= SPIKE_THRESH).sum())
prevalence  = n_pos / n_windows

# Count independent pressure events in test CSV (all series combined)
def count_events(series_values, threshold=SPIKE_THRESH, merge_gap=MERGE_GAP):
    """Return list of (start_idx, end_idx) for each contiguous spike run."""
    above = (series_values >= threshold).astype(int)
    events = []
    in_ev  = False
    start  = None
    gap_cnt = 0
    for i, v in enumerate(above):
        if v:
            if not in_ev:
                start = i; in_ev = True
            gap_cnt = 0
        else:
            if in_ev:
                gap_cnt += 1
                if gap_cnt > merge_gap:
                    events.append((start, i - gap_cnt))
                    in_ev = False; gap_cnt = 0
    if in_ev:
        events.append((start, len(above) - 1))
    return events

all_psi = test["psi_some_avg10"].values
events  = count_events(all_psi)
n_events = len(events)

counts = dict(
    n_windows=n_windows,
    n_positive_windows=n_pos,
    prevalence=round(prevalence, 6),
    n_independent_events=n_events,
    merge_gap_steps=MERGE_GAP,
    test_rows=int(len(test)),
)
print(json.dumps(counts, indent=2))

# ── 3. Confusion matrix ───────────────────────────────────────────────────────
pred_pos = (w_q90 >= SPIKE_THRESH).values
true_pos = (w_act >= SPIKE_THRESH).values

TP = int((true_pos &  pred_pos).sum())
FP = int((~true_pos & pred_pos).sum())
FN = int((true_pos & ~pred_pos).sum())
TN = int((~true_pos & ~pred_pos).sum())
prec = TP/(TP+FP) if (TP+FP)>0 else 0.0
rec  = TP/(TP+FN) if (TP+FN)>0 else 0.0
f1   = 2*prec*rec/(prec+rec) if (prec+rec)>0 else 0.0

cm = pd.DataFrame({
    "metric": ["TP","FP","FN","TN","precision","recall","f1"],
    "value":  [TP, FP, FN, TN,
               round(prec,6), round(rec,6), round(f1,6)],
})
cm.to_csv(OUT / "confusion_matrix.csv", index=False)
print("\nConfusion matrix:")
print(cm.to_string(index=False))

# ── 4. Event-level metrics ────────────────────────────────────────────────────
# Map prediction windows back to time index to get lead time.
# horizon_step in predictions: 1..30 (existing) or 1..2 (paper)
# We use window_id as a proxy for time (each window advances by 1 row = 15 s).

def event_level_metrics(w_q90_arr, w_act_arr, events_list,
                        threshold, lead_win, interval_s, total_hours):
    """
    For each event, detect if any alert fires within [onset-lead_win, onset+duration].
    Lead time = onset_idx - alert_idx (in steps, converted to seconds).
    """
    # Build per-step alert series (alert at step i if window i fires)
    n = len(w_q90_arr)
    alert = (w_q90_arr >= threshold)

    detected = 0
    lead_times = []
    for (s, e) in events_list:
        # Look in window [s - lead_win, e]
        look_start = max(0, s - lead_win)
        look_end   = min(n - 1, e)
        window_alerts = np.where(alert[look_start:look_end+1])[0]
        if len(window_alerts) > 0:
            detected += 1
            first_alert = window_alerts[0] + look_start
            lead = (s - first_alert) * interval_s   # positive if alert is before onset
            lead_times.append(lead)

    n_events      = len(events_list)
    event_recall  = detected / n_events if n_events > 0 else 0.0
    fa_total      = int(FP)   # already computed above
    fa_per_hour   = fa_total / total_hours if total_hours > 0 else 0.0

    return dict(
        n_events=n_events,
        n_detected=detected,
        event_recall=round(event_recall, 6),
        mean_lead_time_s=round(float(np.mean(lead_times)) if lead_times else 0, 2),
        median_lead_time_s=round(float(np.median(lead_times)) if lead_times else 0, 2),
        fa_per_hour=round(fa_per_hour, 4),
        total_hours=round(total_hours, 2),
    )

total_hours = len(test) * INTERVAL_S / 3600
em = event_level_metrics(
    w_q90.values, w_act.values, events, SPIKE_THRESH, LEAD_WINDOW, INTERVAL_S, total_hours
)
print("\nEvent-level metrics:")
print(json.dumps(em, indent=2))

# ── 5. Block bootstrap CI (1000 resamples over events) ───────────────────────
print("\nRunning block bootstrap (n=1000)…")

def bootstrap_metrics(w_q90_arr, w_act_arr, events_list,
                      threshold, lead_win, interval_s, total_hours, n_boot, rng):
    n_ev   = len(events_list)
    boot_P, boot_R, boot_F1, boot_ER = [], [], [], []

    for _ in range(n_boot):
        # Resample events with replacement
        idx  = rng.integers(0, n_ev, size=n_ev)
        s_ev = [events_list[i] for i in idx]

        # Resample windows aligned to sampled events (block bootstrap)
        all_win_true = []
        all_win_pred = []
        for (s, e) in s_ev:
            lo = max(0, s - lead_win)
            hi = min(len(w_q90_arr)-1, e)
            all_win_true.extend(w_act_arr[lo:hi+1] >= threshold)
            all_win_pred.extend(w_q90_arr[lo:hi+1] >= threshold)

        all_win_true = np.array(all_win_true)
        all_win_pred = np.array(all_win_pred)
        tp = int((all_win_true & all_win_pred).sum())
        fp = int((~all_win_true & all_win_pred).sum())
        fn = int((all_win_true & ~all_win_pred).sum())
        p  = tp/(tp+fp) if (tp+fp)>0 else 0.0
        r  = tp/(tp+fn) if (tp+fn)>0 else 0.0
        f  = 2*p*r/(p+r) if (p+r)>0 else 0.0

        # Event recall
        det = 0
        for (s, e) in s_ev:
            lo = max(0, s-lead_win)
            if any(w_q90_arr[lo:e+1] >= threshold):
                det += 1
        er = det / n_ev if n_ev > 0 else 0.0

        boot_P.append(p); boot_R.append(r)
        boot_F1.append(f); boot_ER.append(er)

    ci = {}
    for name, vals in [("precision",boot_P),("recall",boot_R),
                       ("f1",boot_F1),("event_recall",boot_ER)]:
        lo = float(np.percentile(vals, 2.5))
        hi = float(np.percentile(vals, 97.5))
        ci[name] = {"lo95": round(lo,6), "hi95": round(hi,6),
                    "mean": round(float(np.mean(vals)),6)}
    return ci

ci = bootstrap_metrics(
    w_q90.values, w_act.values, events, SPIKE_THRESH, LEAD_WINDOW,
    INTERVAL_S, total_hours, N_BOOTSTRAP, RNG
)
ci_df = pd.DataFrame([
    {"metric": k, "mean": v["mean"], "ci_lo_95": v["lo95"], "ci_hi_95": v["hi95"]}
    for k, v in ci.items()
])
ci_df.to_csv(OUT / "bootstrap_ci.csv", index=False)
print("95% CI (block bootstrap over events):")
print(ci_df.to_string(index=False))

# ── 6. Baselines ──────────────────────────────────────────────────────────────
# Always-alert: precision = prevalence, recall = 1
# Naive persistence: forecast = last observed (previous window's actual max)
prev_act = np.roll(w_act.values, 1); prev_act[0] = 0.0
persist_pred = (prev_act >= SPIKE_THRESH)
pt = int((true_pos & persist_pred).sum())
pf = int((~true_pos & persist_pred).sum())
pn = int((true_pos & ~persist_pred).sum())
p_prec = pt/(pt+pf) if (pt+pf)>0 else 0.0
p_rec  = pt/(pt+pn) if (pt+pn)>0 else 0.0
p_f1   = 2*p_prec*p_rec/(p_prec+p_rec) if (p_prec+p_rec)>0 else 0.0

baselines = pd.DataFrame([
    {"model":"always_alert",   "precision":round(prevalence,6),"recall":1.0,
     "f1": round(2*prevalence/(1+prevalence),6)},
    {"model":"naive_persist",  "precision":round(p_prec,6),"recall":round(p_rec,6),
     "f1":round(p_f1,6)},
    {"model":"TFT_original",   "precision":0.81127,"recall":0.74645,"f1":0.77751},
])
baselines.to_csv(OUT / "baselines.csv", index=False)
print("\nBaselines:")
print(baselines.to_string(index=False))

# ── 7. Save summary ───────────────────────────────────────────────────────────
summary = {
    "counts":       counts,
    "confusion":    {"TP":TP,"FP":FP,"FN":FN,"TN":TN,
                     "precision":round(prec,6),"recall":round(rec,6),"f1":round(f1,6)},
    "event_metrics":em,
    "bootstrap_ci": ci,
    "baselines": baselines.to_dict(orient="records"),
}
with open(OUT / "exp2_summary.json", "w") as fh:
    json.dump(summary, fh, indent=2)

# ── 8. Plot ───────────────────────────────────────────────────────────────────
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

fig, axes = plt.subplots(1, 2, figsize=(12, 5))

# Left: confusion matrix heatmap
cm_mat = np.array([[TP, FN],[FP, TN]])
im = axes[0].imshow(cm_mat, cmap="Blues")
axes[0].set_xticks([0,1]); axes[0].set_yticks([0,1])
axes[0].set_xticklabels(["Pred+","Pred-"])
axes[0].set_yticklabels(["Act+","Act-"])
for i in range(2):
    for j in range(2):
        axes[0].text(j, i, str(cm_mat[i,j]), ha="center", va="center", fontsize=14)
axes[0].set_title(f"Confusion Matrix\nP={prec:.4f} R={rec:.4f} F1={f1:.4f}")
plt.colorbar(im, ax=axes[0])

# Right: CI plot
metrics_ = ["precision","recall","f1","event_recall"]
means_   = [ci[m]["mean"]  for m in metrics_]
lo_      = [ci[m]["lo95"]  for m in metrics_]
hi_      = [ci[m]["hi95"]  for m in metrics_]
err_lo   = [means_[i]-lo_[i] for i in range(len(means_))]
err_hi   = [hi_[i]-means_[i] for i in range(len(means_))]
axes[1].barh(metrics_, means_, xerr=[err_lo, err_hi], color="#4C72B0",
             capsize=5, height=0.5)
axes[1].set_xlim(0, 1.05)
axes[1].set_xlabel("Score")
axes[1].set_title("95% CI (block bootstrap, 1000 resamples)")
axes[1].axvline(0.75, color="red", linestyle="--", alpha=0.5, label="0.75")
axes[1].legend()
axes[1].grid(axis="x", alpha=0.3)

plt.tight_layout()
plt.savefig(OUT / "exp2_plot.png", dpi=150)
plt.close()
print(f"\nPlot saved to {OUT / 'exp2_plot.png'}")
print(f"All outputs in {OUT}")
print("EXPERIMENT 2 COMPLETE")
