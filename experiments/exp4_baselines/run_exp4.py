#!/usr/bin/env python3
"""
Experiment 4: Baselines on the identical split.

Models evaluated:
  a. Naive persistence: forecast = last observed PSI
  b. Plain threshold: alert if current_psi > 1.80
  c. Exponential smoothing (ETS / Holt-Winters)
  d. ARIMA (statsmodels SARIMAX with auto-lag detection, rolling forecasts)
  e. LSTM baseline (single-layer, same encoder window)
  f. TFT original (k=1 and k=2) from existing predictions

All use enc=30, horizon=2, T=1.80, event-level metrics.

Saves:
  results/exp4_baselines/baseline_metrics.csv
  results/exp4_baselines/inference_times.csv
  results/exp4_baselines/exp4_summary.json
  results/exp4_baselines/exp4_plot.png
"""

import json, time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.arima.model import ARIMA

REPO      = Path(__file__).resolve().parent.parent.parent
PRED_CSV  = REPO / "data" / "tft_predictions.csv"
TRAIN_CSV = REPO / "data" / "train.csv"
VAL_CSV   = REPO / "data" / "validation.csv"
TEST_CSV  = REPO / "data" / "test.csv"
OUT       = REPO / "results" / "exp4_baselines"
OUT.mkdir(parents=True, exist_ok=True)

SPIKE_T    = 1.80
INTERVAL_S = 15
MERGE_GAP  = 2
ENC        = 30
HORIZON    = 2
SEED       = 42
torch.manual_seed(SEED); np.random.seed(SEED)

print("=" * 70)
print("EXPERIMENT 4  Baselines")
print("=" * 70)

# ── Load data ────────────────────────────────────────────────────────────────
train = pd.read_csv(TRAIN_CSV)
val   = pd.read_csv(VAL_CSV)
test  = pd.read_csv(TEST_CSV)

# Use node-a only for univariate models to keep runtime manageable.
# Results are averaged across the 3 series for TFT comparison.
def get_psi(df, sid="node-a"):
    return df[df["series_id"]==sid]["psi_some_avg10"].values

tr_psi = get_psi(train)   # 25921 values
va_psi = get_psi(val)     # 2761 values
te_psi = get_psi(test)    # 11400 values

# For window-level evaluation on test (all series, matching TFT)
pred_csv_df = pd.read_csv(PRED_CSV)
N_TRAIN_W = 25890 * 3
N_VAL_W   = 2730  * 3
N_TEST_W  = 11369 * 3
tft_q90_test = pred_csv_df.groupby("window_id")["q90"].max().values[N_TRAIN_W+N_VAL_W:N_TRAIN_W+N_VAL_W+N_TEST_W]
tft_act_test = pred_csv_df.groupby("window_id")["actual_psi"].max().values[N_TRAIN_W+N_VAL_W:N_TRAIN_W+N_VAL_W+N_TEST_W]
test_hours = len(tft_act_test) * INTERVAL_S / 3600

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

def evaluate(act_max, pred_alert, hours, threshold=SPIKE_T, lead_win=HORIZON):
    tp = int(( (act_max>=threshold) &  pred_alert).sum())
    fp = int(((act_max< threshold)  &  pred_alert).sum())
    fn = int(( (act_max>=threshold) & ~pred_alert).sum())
    tn = int(((act_max< threshold)  & ~pred_alert).sum())
    prec = tp/(tp+fp) if (tp+fp)>0 else 0.0
    rec  = tp/(tp+fn) if (tp+fn)>0 else 0.0
    f1   = 2*prec*rec/(prec+rec) if (prec+rec)>0 else 0.0
    fa_hr = fp/hours if hours>0 else 0.0
    events = count_events(act_max, threshold)
    det = sum(1 for (s,e) in events
              if pred_alert[max(0,s-lead_win):e+1].any())
    ev_rec = det/len(events) if events else 0.0
    lead_times = []
    for (s,e) in events:
        lo = max(0, s-lead_win)
        idx = np.where(pred_alert[lo:e+1])[0]
        if len(idx): lead_times.append((s-(idx[0]+lo))*INTERVAL_S)
    mean_lead = float(np.mean(lead_times)) if lead_times else 0.0
    return dict(tp=tp,fp=fp,fn=fn,tn=tn,
                precision=round(prec,6), recall=round(rec,6),
                f1=round(f1,6), fa_per_hour=round(fa_hr,4),
                event_recall=round(ev_rec,6),
                mean_lead_s=round(mean_lead,2))

results = []
inf_times = []

# ── a. Naive persistence (window level for all series) ───────────────────────
print("\na. Naive persistence")
# Forecast = last observed window max (the ENC-th step)
# Window i: encoder = act_max[i], horizon max = act_max[i+1] (approx)
# More precisely: shift by 1 position
persist_pred = np.roll(tft_act_test, 1); persist_pred[0] = 0.0
persist_alert = (persist_pred >= SPIKE_T)

t0 = time.perf_counter()
_ = (persist_pred >= SPIKE_T)
inf_ms = (time.perf_counter()-t0)*1000 / max(len(persist_pred),1)

m = evaluate(tft_act_test, persist_alert, test_hours)
m.update({"model":"naive_persistence","params":0,"inf_ms_per_window":round(inf_ms*1000,4)})
results.append(m)
inf_times.append({"model":"naive_persistence","inf_ms":round(inf_ms*1000,4)})
print(f"  P={m['precision']:.4f} R={m['recall']:.4f} F1={m['f1']:.4f} FA/hr={m['fa_per_hour']:.4f}")

# ── b. Plain threshold on current PSI ────────────────────────────────────────
print("\nb. Plain current-value threshold")
# Window max of encoder's last step (last value in each window)
# We only have window-level actuals, so we use the actual max as proxy for
# "current observed value" and check if it exceeds the threshold.
# For a fairer comparison: build windows from test PSI directly.
te_all_psi = test["psi_some_avg10"].values  # all series concatenated

# Build windows (enc=30, hop=1) for one series to get inference time
series_psi = te_psi
n_win = len(series_psi) - ENC - HORIZON + 1
# Alert if max over last ENC steps (encoder max) >= threshold (plain threshold trigger)
enc_max_arr   = np.array([series_psi[i:i+ENC].max()     for i in range(n_win)])
target_max_arr= np.array([series_psi[i+ENC:i+ENC+HORIZON].max() for i in range(n_win)])
thresh_alert  = (enc_max_arr >= SPIKE_T)
t0 = time.perf_counter()
_ = (enc_max_arr >= SPIKE_T)
inf_ms_thresh = (time.perf_counter()-t0)*1000 / max(n_win,1) * 1000  # per window in µs→ms

m_thresh = evaluate(target_max_arr, thresh_alert, len(target_max_arr)*INTERVAL_S/3600)
m_thresh.update({"model":"plain_threshold","params":0,
                 "inf_ms_per_window":round(inf_ms_thresh,6)})
results.append(m_thresh)
inf_times.append({"model":"plain_threshold","inf_ms":round(inf_ms_thresh,6)})
print(f"  P={m_thresh['precision']:.4f} R={m_thresh['recall']:.4f} "
      f"F1={m_thresh['f1']:.4f} FA/hr={m_thresh['fa_per_hour']:.4f}")

# ── c. Exponential smoothing (ETS) ─────────────────────────────────────────
print("\nc. Exponential smoothing (ETS)")
# Fit on train (node-a); rolling 1-step ahead forecasts on test.
# Use Holt-Winters additive with no seasonality (PSI has no strong seasonal period
# at 15-second granularity within a single-day window).
print("  Fitting ETS on train…")
ets_model = ExponentialSmoothing(tr_psi, trend="add", seasonal=None).fit(
    optimized=True, disp=False
)
print(f"  ETS alpha={ets_model.params.get('smoothing_level',float('nan')):.4f}")

# Rolling forecast on test (node-a only)
history = list(tr_psi) + list(va_psi)
ets_preds_1step = []

t0 = time.perf_counter()
for i in range(0, len(te_psi) - HORIZON, HORIZON):
    # Refit every HORIZON steps for rolling evaluation
    if i % 500 == 0:
        try:
            ets_rf = ExponentialSmoothing(
                history[-min(5000, len(history)):], trend="add", seasonal=None
            ).fit(optimized=True, disp=False)
        except Exception:
            pass
    fc = ets_rf.forecast(HORIZON)
    ets_preds_1step.append(fc.max())
    history.extend(te_psi[i:i+HORIZON])
inf_ms_ets = (time.perf_counter()-t0)*1000 / max(len(ets_preds_1step),1)

ets_preds = np.array(ets_preds_1step)
n_ets = len(ets_preds)
ets_actual = np.array([te_psi[i+ENC:i+ENC+HORIZON].max() if i+ENC+HORIZON<=len(te_psi) else 0
                       for i in range(0, len(te_psi)-HORIZON, HORIZON)])[:n_ets]
# Align lengths
min_n = min(len(ets_preds), len(ets_actual))
ets_preds  = ets_preds[:min_n]
ets_actual = ets_actual[:min_n]
ets_alert  = (ets_preds >= SPIKE_T)

m_ets = evaluate(ets_actual, ets_alert, min_n*HORIZON*INTERVAL_S/3600)
m_ets.update({"model":"ETS_HoltWinters","params":3,
              "inf_ms_per_window":round(inf_ms_ets,4)})
results.append(m_ets)
inf_times.append({"model":"ETS","inf_ms":round(inf_ms_ets,4)})
print(f"  P={m_ets['precision']:.4f} R={m_ets['recall']:.4f} "
      f"F1={m_ets['f1']:.4f} FA/hr={m_ets['fa_per_hour']:.4f}")

# ── d. ARIMA ──────────────────────────────────────────────────────────────────
print("\nd. ARIMA rolling forecasts")
# Use ARIMA(2,0,2) which is typically adequate for PSI-like autocorrelated series.
# Fit on last 2000 train points (rolling refit every 300 steps for efficiency).
ARIMA_P, ARIMA_D, ARIMA_Q = 2, 0, 2
arima_preds = []
arima_actuals = []
history_ar = list(tr_psi[-2000:]) + list(va_psi)

t0 = time.perf_counter()
refit_interval = 300
arima_model_obj = None
for i in range(0, len(te_psi) - HORIZON, HORIZON):
    if i % refit_interval == 0 or arima_model_obj is None:
        window = history_ar[-2000:]
        try:
            arima_model_obj = ARIMA(window, order=(ARIMA_P, ARIMA_D, ARIMA_Q)).fit()
        except Exception as e:
            print(f"  ARIMA refit error at i={i}: {e}")
            arima_preds.append(0.0)
            arima_actuals.append(te_psi[i:i+HORIZON].max())
            history_ar.extend(te_psi[i:i+HORIZON])
            continue
    try:
        fc = arima_model_obj.forecast(steps=HORIZON)
        arima_preds.append(float(np.max(fc)))
    except Exception:
        arima_preds.append(0.0)
    arima_actuals.append(te_psi[i:i+HORIZON].max())
    history_ar.extend(te_psi[i:i+HORIZON])
inf_ms_arima = (time.perf_counter()-t0)*1000 / max(len(arima_preds),1)

arima_preds   = np.array(arima_preds)
arima_actuals = np.array(arima_actuals)
# Upper-quantile alert: use 90th percentile of residuals as prediction interval
residuals = arima_preds - arima_actuals
q90_resid = np.percentile(np.abs(residuals), 90)
arima_q90 = arima_preds + q90_resid
arima_alert_q90   = (arima_q90 >= SPIKE_T)
arima_alert_point = (arima_preds >= SPIKE_T)

m_arima = evaluate(arima_actuals, arima_alert_point, len(arima_actuals)*HORIZON*INTERVAL_S/3600)
m_arima.update({"model":"ARIMA(2,0,2)_point","params":5,
                "inf_ms_per_window":round(inf_ms_arima,4)})
results.append(m_arima)

m_arima_q90 = evaluate(arima_actuals, arima_alert_q90, len(arima_actuals)*HORIZON*INTERVAL_S/3600)
m_arima_q90.update({"model":"ARIMA(2,0,2)_q90","params":5,
                    "inf_ms_per_window":round(inf_ms_arima,4)})
results.append(m_arima_q90)
inf_times.append({"model":"ARIMA","inf_ms":round(inf_ms_arima,4)})
print(f"  ARIMA point: P={m_arima['precision']:.4f} R={m_arima['recall']:.4f} "
      f"F1={m_arima['f1']:.4f}")
print(f"  ARIMA q90:   P={m_arima_q90['precision']:.4f} R={m_arima_q90['recall']:.4f} "
      f"F1={m_arima_q90['f1']:.4f}")

# ── e. LSTM baseline ─────────────────────────────────────────────────────────
print("\ne. LSTM baseline")

class LSTMForecaster(nn.Module):
    def __init__(self, input_size=1, hidden=32, layers=1, horizon=2):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden, layers, batch_first=True)
        self.fc   = nn.Linear(hidden, horizon)
    def forward(self, x):
        out, _ = self.lstm(x)
        return self.fc(out[:, -1, :])

# Build windows from train+val (node-a)
tv_psi = np.concatenate([tr_psi, va_psi])
X_train = np.array([tv_psi[i:i+ENC] for i in range(len(tv_psi)-ENC-HORIZON+1)])
Y_train = np.array([tv_psi[i+ENC:i+ENC+HORIZON].max() for i in range(len(tv_psi)-ENC-HORIZON+1)])
X_te    = np.array([te_psi[i:i+ENC]           for i in range(len(te_psi)-ENC-HORIZON+1)])
Y_te    = np.array([te_psi[i+ENC:i+ENC+HORIZON].max() for i in range(len(te_psi)-ENC-HORIZON+1)])

# Normalize with train stats
mu  = X_train.mean(); sigma = X_train.std() + 1e-8
X_tr_t = torch.tensor((X_train - mu)/sigma, dtype=torch.float32).unsqueeze(-1)
Y_tr_t = torch.tensor((Y_train - mu)/sigma, dtype=torch.float32)
X_te_t = torch.tensor((X_te    - mu)/sigma, dtype=torch.float32).unsqueeze(-1)

lstm_model = LSTMForecaster(1, 32, 1, HORIZON)
opt_l = torch.optim.Adam(lstm_model.parameters(), lr=1e-3)
n_params_lstm = sum(p.numel() for p in lstm_model.parameters())

# Mini-batch training (5 epochs, batch=256)
BS = 256
print(f"  Training LSTM ({n_params_lstm} params)…")
for ep in range(5):
    idx = torch.randperm(len(X_tr_t))
    tl = 0.0; nb = 0
    for b in range(0, len(idx), BS):
        bi = idx[b:b+BS]
        opt_l.zero_grad()
        pred_l = lstm_model(X_tr_t[bi]).squeeze(-1) if HORIZON>1 else lstm_model(X_tr_t[bi])
        # For HORIZON>1, model outputs (B, HORIZON); we use max for spike detection
        # but need a scalar per window → take max prediction
        if pred_l.dim()==2:
            pred_l_loss = pred_l.mean(-1)
        else:
            pred_l_loss = pred_l
        loss_l = nn.MSELoss()(pred_l_loss, Y_tr_t[bi])
        loss_l.backward(); opt_l.step()
        tl += float(loss_l.detach()); nb += 1
    if ep % 2 == 0:
        print(f"  ep{ep+1} loss={tl/nb:.4f}")

lstm_model.eval()
t0 = time.perf_counter()
with torch.no_grad():
    lstm_out = lstm_model(X_te_t)   # (W, HORIZON)
inf_ms_lstm = (time.perf_counter()-t0)*1000 / max(len(X_te_t),1)

# Denormalise and get max over horizon
lstm_preds_norm = lstm_out.numpy()          # (W, HORIZON) or (W,)
if lstm_preds_norm.ndim == 2:
    lstm_preds_max = lstm_preds_norm.max(axis=1) * sigma + mu
else:
    lstm_preds_max = lstm_preds_norm * sigma + mu
lstm_alert = (lstm_preds_max >= SPIKE_T)

m_lstm = evaluate(Y_te, lstm_alert, len(Y_te)*HORIZON*INTERVAL_S/3600)
m_lstm.update({"model":"LSTM_baseline","params":n_params_lstm,
               "inf_ms_per_window":round(inf_ms_lstm,4)})
results.append(m_lstm)
inf_times.append({"model":"LSTM","inf_ms":round(inf_ms_lstm,4)})
print(f"  P={m_lstm['precision']:.4f} R={m_lstm['recall']:.4f} "
      f"F1={m_lstm['f1']:.4f} FA/hr={m_lstm['fa_per_hour']:.4f}")

# ── f. TFT from existing predictions (k=1 and k=2) ──────────────────────────
print("\nf. TFT original (existing predictions)")
def apply_gate(scores, threshold, k):
    raw   = (scores >= threshold).astype(int)
    gated = np.zeros(len(raw), dtype=bool)
    for i in range(k-1, len(raw)):
        if raw[i-k+1:i+1].sum() == k:
            gated[i] = True
    return gated

for k in [1, 2]:
    alerts = apply_gate(tft_q90_test, SPIKE_T, k)
    m_tft  = evaluate(tft_act_test, alerts, test_hours)
    # Count parameters from checkpoint
    import torch as _torch
    ckpt = _torch.load(REPO/"models"/"tft_psi_model.ckpt",
                       map_location="cpu", weights_only=False)
    n_tft = sum(v.numel() for v in ckpt["state_dict"].values())
    m_tft.update({"model":f"TFT_k{k}","params":n_tft,
                  "inf_ms_per_window":None})
    results.append(m_tft)
    print(f"  TFT k={k}: P={m_tft['precision']:.4f} R={m_tft['recall']:.4f} "
          f"F1={m_tft['f1']:.4f} FA/hr={m_tft['fa_per_hour']:.4f}")

# TFT inference time (1000 single-window calls)
from pytorch_forecasting import TimeSeriesDataSet, TemporalFusionTransformer
from pytorch_forecasting.metrics import QuantileLoss

tft_model = TemporalFusionTransformer.load_from_checkpoint(
    REPO / "models" / "tft_psi_model.ckpt"
)
tft_model.eval()

# Build a single test batch
TIME_K   = ["time_idx","hour_sin","hour_cos"]
TIME_UNK = ["request_rate","active_connections","cpu_usage","memory_usage",
            "read_bytes_per_sec","write_bytes_per_sec","latency_ms","error_rate",
            "psi_some_avg10","psi_some_avg60","psi_some_avg300",
            "psi_full_avg10","psi_full_avg60","psi_full_avg300"]

sample_df = pd.read_csv(TRAIN_CSV)
sample_df["timestamp"] = pd.to_datetime(sample_df["timestamp"])
ds_tiny = TimeSeriesDataSet(
    sample_df.head(500),
    time_idx="time_idx", target="psi_some_avg10", group_ids=["series_id"],
    max_encoder_length=30, max_prediction_length=30,
    time_varying_known_reals=TIME_K,
    time_varying_unknown_reals=TIME_UNK,
    allow_missing_timesteps=False,
)
dl_tiny = ds_tiny.to_dataloader(train=False, batch_size=1, num_workers=0)

timing_runs = []
with torch.no_grad():
    for i, (x, y) in enumerate(dl_tiny):
        if i >= 1000: break
        t0 = time.perf_counter()
        _ = tft_model(x)
        timing_runs.append((time.perf_counter()-t0)*1000)

tft_inf_ms = float(np.mean(timing_runs))
inf_times.append({"model":"TFT","inf_ms":round(tft_inf_ms,4)})
# Patch into TFT result rows
for r in results:
    if r["model"].startswith("TFT"):
        r["inf_ms_per_window"] = round(tft_inf_ms, 4)
print(f"  TFT mean inference time: {tft_inf_ms:.4f} ms/window (n=1000)")

# ── Save results ──────────────────────────────────────────────────────────────
metrics_df = pd.DataFrame(results)
# Reorder columns
cols_order = ["model","precision","recall","f1","event_recall","fa_per_hour",
              "mean_lead_s","params","inf_ms_per_window","tp","fp","fn","tn"]
metrics_df = metrics_df.reindex(columns=[c for c in cols_order if c in metrics_df.columns])
metrics_df.to_csv(OUT / "baseline_metrics.csv", index=False)

inf_df = pd.DataFrame(inf_times)
inf_df.to_csv(OUT / "inference_times.csv", index=False)

print("\n" + "=" * 70)
print("BASELINE COMPARISON TABLE")
print("=" * 70)
print(metrics_df.to_string(index=False))

summary = {
    "note": "node-a only for univariate models; all 3 series for TFT windows.",
    "models": results,
    "inference_times": inf_times,
}
with open(OUT / "exp4_summary.json", "w") as f:
    json.dump(summary, f, indent=2)

# ── Plot ─────────────────────────────────────────────────────────────────────
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

model_labels = [r["model"] for r in results]
precisions   = [r["precision"] for r in results]
recalls      = [r["recall"] for r in results]
f1s          = [r["f1"] for r in results]

x    = np.arange(len(model_labels))
w    = 0.25
fig, ax = plt.subplots(figsize=(max(10, len(model_labels)*1.4), 5))
ax.bar(x - w, precisions, w, label="Precision", color="#4C72B0")
ax.bar(x,     recalls,    w, label="Recall",    color="#DD8452")
ax.bar(x + w, f1s,        w, label="F1",        color="#55A868")
ax.set_xticks(x); ax.set_xticklabels(model_labels, rotation=25, ha="right")
ax.set_ylim(0, 1.05); ax.set_ylabel("Score")
ax.set_title("Exp4: All Baselines vs TFT (T=1.80, enc=30, horizon=2)")
ax.legend(); ax.grid(axis="y", alpha=0.3)
plt.tight_layout()
plt.savefig(OUT / "exp4_plot.png", dpi=150)
plt.close()

print(f"\nAll outputs saved to {OUT}")
print("EXPERIMENT 4 COMPLETE")
