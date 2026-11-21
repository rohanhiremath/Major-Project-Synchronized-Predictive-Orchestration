#!/usr/bin/env python3
"""
Experiment 5: Quantile ablation (q50 / q75 / q90 / q95) + CQR calibration.

Steps:
  1. Retrain TFT (5 seeds) with output quantiles [0.1, 0.5, 0.75, 0.9, 0.95].
  2. Evaluate spike detection at each quantile as the decision output.
  3. Report precision, recall, F1, event_recall, FA/hr, empirical q10-q90 coverage
     vs nominal 80%.
  4. CQR on validation: calibrate q90 → report interval coverage before/after.
  5. Report detection metrics with calibrated q90.

Saves:
  results/exp5_quantile/quantile_seed_results.csv
  results/exp5_quantile/quantile_comparison.csv
  results/exp5_quantile/cqr_calibration.json
  results/exp5_quantile/exp5_summary.json
  results/exp5_quantile/exp5_plot.png
"""

import json, time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from pytorch_forecasting import TimeSeriesDataSet, TemporalFusionTransformer
from pytorch_forecasting.metrics import QuantileLoss

REPO      = Path(__file__).resolve().parent.parent.parent
TRAIN_CSV = REPO / "data" / "train.csv"
VAL_CSV   = REPO / "data" / "validation.csv"
TEST_CSV  = REPO / "data" / "test.csv"
OUT       = REPO / "results" / "exp5_quantile"
OUT.mkdir(parents=True, exist_ok=True)

# Paper / global constants
MAX_ENC   = 30
MAX_PRED  = 2
SPIKE_T   = 1.80
SEEDS     = [0, 1, 2, 3, 4]
BATCH     = 64
MAX_EPOCHS= 15
LR        = 1e-3
HIDDEN    = 8
ATTN      = 2
DROPOUT   = 0.1
PATIENCE  = 3
INTERVAL_S= 15
MERGE_GAP = 2

QUANTILES = [0.1, 0.5, 0.75, 0.9, 0.95]   # extended set
Q_IDX     = {q: i for i, q in enumerate(QUANTILES)}

TIME_K   = ["time_idx","hour_sin","hour_cos"]
TIME_UNK = ["request_rate","active_connections","cpu_usage","memory_usage",
            "read_bytes_per_sec","write_bytes_per_sec","latency_ms","error_rate",
            "psi_some_avg10","psi_some_avg60","psi_some_avg300",
            "psi_full_avg10","psi_full_avg60","psi_full_avg300"]

print("=" * 70)
print("EXPERIMENT 5  Quantile ablation + CQR calibration")
print("=" * 70)

# ── Load data ────────────────────────────────────────────────────────────────
train = pd.read_csv(TRAIN_CSV)
val   = pd.read_csv(VAL_CSV)
test  = pd.read_csv(TEST_CSV)
for df in [train, val, test]:
    df["timestamp"] = pd.to_datetime(df["timestamp"])

# ── Helpers ──────────────────────────────────────────────────────────────────
def count_events(vals, threshold=SPIKE_T, merge_gap=MERGE_GAP):
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
    if in_ev: events.append((start, len(vals)-1))
    return events

def evaluate(act_max, pred_alert, hours, threshold=SPIKE_T, lead_win=MAX_PRED):
    tp = int(( (act_max>=threshold) &  pred_alert).sum())
    fp = int(((act_max< threshold)  &  pred_alert).sum())
    fn = int(( (act_max>=threshold) & ~pred_alert).sum())
    prec = tp/(tp+fp) if (tp+fp)>0 else 0.0
    rec  = tp/(tp+fn) if (tp+fn)>0 else 0.0
    f1   = 2*prec*rec/(prec+rec) if (prec+rec)>0 else 0.0
    fa   = fp/hours if hours>0 else 0.0
    events = count_events(act_max, threshold)
    det = sum(1 for (s,e) in events
              if pred_alert[max(0,s-lead_win):e+1].any())
    ev_rec = det/len(events) if events else 0.0
    return dict(precision=round(prec,6), recall=round(rec,6),
                f1=round(f1,6), fa_per_hour=round(fa,4),
                event_recall=round(ev_rec,6),
                tp=tp, fp=fp, fn=fn)

def build_dataset(df, ref_ds=None, predict=False):
    kw = dict(time_idx="time_idx", target="psi_some_avg10", group_ids=["series_id"],
              max_encoder_length=MAX_ENC, max_prediction_length=MAX_PRED,
              time_varying_known_reals=TIME_K, time_varying_unknown_reals=TIME_UNK,
              allow_missing_timesteps=False)
    if ref_ds is None:
        return TimeSeriesDataSet(df, **kw)
    return TimeSeriesDataSet.from_dataset(ref_ds, df, predict=predict,
                                          stop_randomization=True)

def run_inference(model, dataloader, min_tidx=None):
    """Returns arrays: q_all (W, T, Q), act_all (W, T)"""
    q_batches, a_batches = [], []
    model.eval()
    with torch.no_grad():
        for x, y in dataloader:
            out = model(x)
            q   = model.to_quantiles(out)   # (B, T, Q)
            if min_tidx is not None:
                mask = x["decoder_time_idx"][:,0] >= min_tidx
                if not mask.any(): continue
                q   = q[mask]
                y0  = y[0][mask]
            else:
                y0 = y[0]
            q_batches.append(q.cpu().numpy())
            a_batches.append(y0.cpu().numpy())
    if not q_batches: return None, None
    return np.concatenate(q_batches, 0), np.concatenate(a_batches, 0)

# ── 5-seed TFT training ──────────────────────────────────────────────────────
all_seed_records = []
# Store last-seed val predictions for CQR
cqr_q90_val, cqr_act_val = None, None
# Store averaged test quantiles
test_q_accum = None
test_a_accum = None
n_seeds_done = 0

for seed in SEEDS:
    print(f"\n--- seed={seed} ---")
    torch.manual_seed(seed); np.random.seed(seed)

    train_ds = build_dataset(train)
    tv = pd.concat([train, val]).sort_values(["series_id","time_idx"])
    val_ds  = build_dataset(tv, ref_ds=train_ds, predict=True)
    tvt     = pd.concat([train, val, test]).sort_values(["series_id","time_idx"])
    # Assign continuous time_idx
    tvt["time_idx"] = tvt.groupby("series_id").cumcount()
    tr_re   = tvt[tvt["time_idx"] < len(train)//3].copy()
    tr_re["time_idx"] = tr_re.groupby("series_id").cumcount()
    train_ds2 = build_dataset(tr_re)
    test_ds   = build_dataset(tvt, ref_ds=train_ds2, predict=False)

    train_dl = train_ds.to_dataloader(train=True,  batch_size=BATCH, num_workers=0)
    val_dl   = val_ds.to_dataloader(  train=False, batch_size=BATCH, num_workers=0)
    test_dl  = test_ds.to_dataloader( train=False, batch_size=BATCH, num_workers=0)

    tft = TemporalFusionTransformer.from_dataset(
        train_ds, learning_rate=LR, hidden_size=HIDDEN,
        attention_head_size=ATTN, dropout=DROPOUT, hidden_continuous_size=HIDDEN,
        output_size=len(QUANTILES),
        loss=QuantileLoss(quantiles=QUANTILES),
        log_interval=-1, reduce_on_plateau_patience=PATIENCE,
    )
    opt = torch.optim.Adam(tft.parameters(), lr=LR)
    best_vl = float("inf"); no_imp = 0; best_state = None

    for ep in range(1, MAX_EPOCHS+1):
        tft.train()
        tl=0.0; nb=0
        for x,y in train_dl:
            opt.zero_grad()
            loss = tft.loss(tft(x)["prediction"], y)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(tft.parameters(), 0.1)
            opt.step(); tl+=float(loss.detach()); nb+=1
        tft.eval()
        vl=0.0; mv=0
        with torch.no_grad():
            for x,y in val_dl:
                vl+=float(tft.loss(tft(x)["prediction"],y)); mv+=1
        tl/=max(nb,1); vl/=max(mv,1)
        print(f"  ep{ep:02d} train={tl:.4f} val={vl:.4f}", flush=True)
        if vl < best_vl-1e-4:
            best_vl=vl; no_imp=0
            best_state={k:v.clone() for k,v in tft.state_dict().items()}
        else:
            no_imp+=1
            if no_imp>=PATIENCE: print("  early stop"); break

    if best_state: tft.load_state_dict(best_state)
    tft.eval()

    # Validation predictions (for CQR)
    q_val, a_val = run_inference(tft, val_dl)
    if q_val is not None and seed == SEEDS[-1]:
        cqr_q90_val = q_val[:, :, Q_IDX[0.9]].max(axis=1)   # (W,)
        cqr_act_val = a_val.max(axis=1)                       # (W,)

    # Test predictions
    te_min_tidx = tvt[tvt["time_idx"] >= len(train)//3 + len(val)//3]["time_idx"].min()
    q_test, a_test = run_inference(tft, test_dl, min_tidx=te_min_tidx)
    if q_test is None:
        q_test, a_test = run_inference(tft, test_dl)

    if q_test is not None:
        if test_q_accum is None:
            test_q_accum = q_test.copy()
            test_a_accum = a_test.copy()
        else:
            min_w = min(test_q_accum.shape[0], q_test.shape[0])
            test_q_accum = test_q_accum[:min_w] + q_test[:min_w]
            test_a_accum = test_a_accum[:min_w]
        n_seeds_done += 1

        # Per-seed metrics for each quantile
        hours = q_test.shape[0] * MAX_PRED * INTERVAL_S / 3600
        seed_row = {"seed": seed, "val_loss": round(best_vl,6)}
        for q in [0.5, 0.75, 0.9, 0.95]:
            q_pred = q_test[:, :, Q_IDX[q]].max(axis=1)
            alert  = (q_pred >= SPIKE_T)
            m = evaluate(a_test.max(axis=1), alert, hours)
            seed_row[f"q{int(q*100)}_P"] = m["precision"]
            seed_row[f"q{int(q*100)}_R"] = m["recall"]
            seed_row[f"q{int(q*100)}_F1"]= m["f1"]
        all_seed_records.append(seed_row)
        print(f"  seed={seed}: q90 P={seed_row.get('q90_P',0):.4f} "
              f"R={seed_row.get('q90_R',0):.4f} F1={seed_row.get('q90_F1',0):.4f}")

seed_df = pd.DataFrame(all_seed_records)
seed_df.to_csv(OUT / "quantile_seed_results.csv", index=False)

# ── Average over seeds ───────────────────────────────────────────────────────
if n_seeds_done > 0:
    test_q_avg = test_q_accum / n_seeds_done   # (W, T, Q)
    test_a_avg = test_a_accum                  # (W, T)
    hours = test_q_avg.shape[0] * MAX_PRED * INTERVAL_S / 3600

    print("\n--- Quantile comparison (mean across seeds, test) ---")
    comp_rows = []
    for q in [0.5, 0.75, 0.9, 0.95]:
        q_pred = test_q_avg[:, :, Q_IDX[q]].max(axis=1)
        alert  = (q_pred >= SPIKE_T)
        act_max= test_a_avg.max(axis=1)
        m = evaluate(act_max, alert, hours)

        # Empirical coverage: fraction of actual values within [q10, q_upper]
        q10_pred = test_q_avg[:, :, Q_IDX[0.1]]
        qupper   = test_q_avg[:, :, Q_IDX[q]]
        coverage = float(((test_a_avg >= q10_pred) & (test_a_avg <= qupper)).mean())
        nominal  = q - 0.1   # e.g. q90-q10 = 80%

        row = {"quantile": q, "nominal_coverage": round(nominal,4),
               "empirical_coverage": round(coverage,6), **m}
        comp_rows.append(row)
        print(f"  q{int(q*100)}: P={m['precision']:.4f} R={m['recall']:.4f} "
              f"F1={m['f1']:.4f} FA/hr={m['fa_per_hour']:.4f} "
              f"cov={coverage:.4f} (nominal {nominal:.2f})")

    comp_df = pd.DataFrame(comp_rows)
    comp_df.to_csv(OUT / "quantile_comparison.csv", index=False)

# ── CQR calibration ──────────────────────────────────────────────────────────
print("\n--- Conformalized Quantile Regression ---")
cqr_results = {}
if cqr_q90_val is not None:
    # Conformity scores on validation: s_i = act_i - q90_i
    scores_cal = cqr_act_val - cqr_q90_val
    alpha      = 0.10   # 90% coverage target
    n_cal      = len(scores_cal)
    # Finite-sample correction: ceil((n+1)(1-alpha))/n quantile
    q_level = np.ceil((n_cal + 1) * (1 - alpha)) / n_cal
    q_level = min(q_level, 1.0)
    q_cqr   = float(np.quantile(scores_cal, q_level))
    print(f"  CQR correction term: {q_cqr:.6f}")

    # Apply to test
    if test_q_accum is not None:
        q90_test_uncal = (test_q_avg[:, :, Q_IDX[0.9]].max(axis=1))
        q90_test_cal   = q90_test_uncal + q_cqr
        # Coverage before/after
        q10_test = test_q_avg[:, :, Q_IDX[0.1]]
        q90_uncal_full = test_q_avg[:, :, Q_IDX[0.9]]
        q90_cal_full   = q90_uncal_full + q_cqr

        cov_before = float(((test_a_avg >= q10_test) & (test_a_avg <= q90_uncal_full)).mean())
        cov_after  = float(((test_a_avg >= q10_test) & (test_a_avg <= q90_cal_full)).mean())

        # Detection metrics with calibrated q90
        alert_cal = (q90_test_cal >= SPIKE_T)
        m_cal = evaluate(act_max, alert_cal, hours)

        cqr_results = {
            "n_calibration": int(n_cal),
            "alpha": alpha,
            "cqr_correction": round(q_cqr, 6),
            "coverage_before_cqr": round(cov_before, 6),
            "coverage_after_cqr":  round(cov_after,  6),
            "nominal_coverage":    0.80,
            "detection_uncalibrated": evaluate(act_max,
                                               (q90_test_uncal >= SPIKE_T), hours),
            "detection_calibrated":   {**m_cal},
        }
        print(f"  Coverage before CQR: {cov_before:.4f}  after: {cov_after:.4f} (nominal 0.80)")
        print(f"  Calibrated q90 P={m_cal['precision']:.4f} R={m_cal['recall']:.4f} "
              f"F1={m_cal['f1']:.4f}")
else:
    cqr_results = {"status": "CQR skipped: no validation predictions available"}

with open(OUT / "cqr_calibration.json", "w") as f:
    json.dump(cqr_results, f, indent=2)

# ── Summary ───────────────────────────────────────────────────────────────────
summary = {
    "quantiles_tested": QUANTILES,
    "seeds": SEEDS,
    "per_quantile_means": comp_rows if n_seeds_done>0 else [],
    "cqr": cqr_results,
    "original_q90_coverage": 0.74045,
    "note": (
        "Original model uses quantiles [0.1, 0.5, 0.9] with q10-q90 coverage 0.74045. "
        "This experiment adds q75 and q95 and measures empirical coverage for each interval."
    ),
}
with open(OUT / "exp5_summary.json", "w") as f:
    json.dump(summary, f, indent=2)

# ── Plot ─────────────────────────────────────────────────────────────────────
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

if n_seeds_done > 0:
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    qs = [r["quantile"] for r in comp_rows]
    # Left: detection metrics vs quantile
    for metric, color in [("recall","#DD8452"),("precision","#4C72B0"),("f1","#55A868")]:
        axes[0].plot(qs, [r[metric] for r in comp_rows], "o-",
                     label=metric.capitalize(), color=color)
    axes[0].set_xlabel("Quantile"); axes[0].set_ylabel("Score")
    axes[0].set_title("Detection Metrics vs Quantile (mean, 5 seeds)")
    axes[0].legend(); axes[0].grid(alpha=0.3)

    # Right: empirical vs nominal coverage
    nominal = [r["nominal_coverage"] for r in comp_rows]
    empirical= [r["empirical_coverage"] for r in comp_rows]
    axes[1].plot(qs, nominal,  "k--", label="Nominal")
    axes[1].plot(qs, empirical,"o-", color="#C44E52", label="Empirical")
    if cqr_results.get("coverage_after_cqr"):
        axes[1].axhline(cqr_results["coverage_after_cqr"], color="green",
                        linestyle=":", label=f"CQR calibrated ({cqr_results['coverage_after_cqr']:.3f})")
    axes[1].axhline(0.74045, color="gray", linestyle="--",
                    alpha=0.6, label="Original 0.74045")
    axes[1].set_xlabel("Upper quantile"); axes[1].set_ylabel("Coverage")
    axes[1].set_title("Empirical vs Nominal Interval Coverage")
    axes[1].legend(); axes[1].grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(OUT / "exp5_plot.png", dpi=150)
    plt.close()

print(f"\nAll outputs saved to {OUT}")
print("EXPERIMENT 5 COMPLETE")
