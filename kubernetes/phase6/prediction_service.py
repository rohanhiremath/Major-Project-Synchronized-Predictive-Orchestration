#!/usr/bin/env python3
"""
Phase 6 / Phase 8: Prediction Service for Kubernetes PSI Spike Detection

What this service does:
  1. Loads the trained TFT model from checkpoint (models/tft_psi_model.ckpt).
  2. Every PREDICTION_INTERVAL seconds, queries Prometheus for the live PSI
     io_some_avg10 value and all correlated features for each workload pod.
  3. Maintains a 30-step (450 s) sliding window per pod and runs a real
     TFT forward pass to produce q10 / q50 / q90 forecasts over the next
     30 steps (450 s).
  4. Fires a spike alert if max(q90 over horizon) >= SPIKE_THRESHOLD (1.80%).
  5. Applies the two-consecutive confirmation gate (k=2) before exposing
     the confirmed metric to the HPA custom-metrics API.
  6. Exports predicted_psi_raw, predicted_psi_confirmed, and
     confirmation_gate_status as Prometheus gauges so the Prometheus
     Adapter can serve them as Kubernetes custom metrics.

Signal / threshold notes
------------------------
  The model was trained on psi_some_avg10 from data/train.csv.
  That column is derived from container I/O pressure (some/avg10), which
  cAdvisor exposes as container_pressure_io_some_avg10 (direct %, same
  units). We query that metric first; if it is absent we fall back to:
    irate(container_pressure_io_some_seconds_total[1m]) * 100
  which is also in % units and matches the training signal closely.

  The threshold T = 1.80 % was chosen as the paper operating point.
  It was validated offline on the synthetic test set (Precision 0.707,
  Recall 0.798, F1 0.750, 34 107 windows). Live calibration against a
  200 ms p99 SLO is a separate procedure not yet completed.

Feature mapping
---------------
  The checkpoint's categorical encoder only knows server_01..06_segment_0.
  Every live pod is mapped to 'server_01_segment_0' (class 0). This is
  safe because the model uses series_id only as a group key for the
  EWMA scaler; with one live series the value is arbitrary.

  For features that cannot be queried from Prometheus in this deployment
  (request_rate, active_connections, etc.) we use the scaler means fitted
  during training. This keeps the normalised input at exactly zero for
  those dimensions so they contribute nothing to the prediction — the
  model falls back to PSI + time features only, which is the core signal.
"""

import os
import sys
import time
import logging
import signal
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple
from collections import deque
from threading import Thread

import numpy as np
import pandas as pd
import torch
import requests
from flask import Flask, jsonify
from prometheus_client import (
    Counter, Gauge, Histogram, Summary, start_http_server
)

# ── Path setup ────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from pytorch_forecasting import TimeSeriesDataSet, TemporalFusionTransformer

try:
    from confirmation_gate import ConfirmationGate
    _GATE_AVAILABLE = True
except ImportError:
    _GATE_AVAILABLE = False

# ── Configuration (all overridable via environment variables) ─────────────────
MODEL_PATH          = os.getenv("MODEL_PATH",
                        str(REPO_ROOT / "models" / "tft_psi_model.ckpt"))
SPIKE_THRESHOLD     = float(os.getenv("SPIKE_THRESHOLD",    "1.80"))
MAX_ENCODER_LENGTH  = int(os.getenv("MAX_ENCODER_LENGTH",   "30"))
MAX_PREDICTION_LENGTH = int(os.getenv("MAX_PREDICTION_LENGTH", "30"))
PROMETHEUS_URL      = os.getenv("PROMETHEUS_URL",
                        "http://kube-prometheus-stack-prometheus.monitoring.svc:9090")
PREDICTION_INTERVAL = int(os.getenv("PREDICTION_INTERVAL",  "20"))   # seconds
SHADOW_MODE         = os.getenv("SHADOW_MODE", "true").lower() == "true"
LOG_LEVEL           = os.getenv("LOG_LEVEL",   "INFO")
METRICS_PORT        = int(os.getenv("METRICS_PORT",  "8000"))
API_PORT            = int(os.getenv("API_PORT",      "8080"))

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("prediction-service")

# ── Prometheus metrics ────────────────────────────────────────────────────────
predictions_total       = Counter("predictions_total",        "Total predictions made")
spikes_predicted_total  = Counter("spikes_predicted_total",   "Total spikes predicted (raw)")
spikes_confirmed_total  = Counter("spikes_confirmed_total",   "Total spikes confirmed (gated)")
spikes_actual_total     = Counter("spikes_actual_total",      "Total actual spikes observed")
true_positives_ctr      = Counter("true_positives_total",     "True positives")
false_positives_ctr     = Counter("false_positives_total",    "False positives")
false_negatives_ctr     = Counter("false_negatives_total",    "False negatives")

current_psi_gauge       = Gauge("current_psi_value",          "Current PSI value (%)",          ["pod"])
predicted_psi_gauge     = Gauge("predicted_psi_value",        "Predicted PSI (%)",              ["pod", "quantile"])
spike_prob_gauge        = Gauge("spike_probability",          "Spike alert (0/1)",              ["pod"])
precision_gauge         = Gauge("prediction_precision",       "Rolling precision")
recall_gauge            = Gauge("prediction_recall",          "Rolling recall")

# HPA custom-metric gauges (read by Prometheus Adapter)
predicted_psi_raw       = Gauge("predicted_psi_raw",          "Raw q90 forecast (%)",           ["pod"])
predicted_psi_confirmed = Gauge("predicted_psi_confirmed",    "Confirmed q90 forecast (%)",     ["pod"])
confirmation_gate_status= Gauge("confirmation_gate_status",   "Gate state (0=waiting,1=fired)", ["pod"])

prediction_latency      = Histogram("prediction_latency_seconds",
                                    "TFT forward-pass wall time",
                                    buckets=[0.005, 0.01, 0.05, 0.1, 0.5, 1.0])
prom_query_latency      = Histogram("prometheus_query_duration_seconds",
                                    "Prometheus query wall time",
                                    buckets=[0.05, 0.1, 0.5, 1.0, 2.0, 5.0])
model_load_time         = Summary("model_load_time_seconds",  "Model loading time")

# ── PSIDataBuffer ─────────────────────────────────────────────────────────────
class PSIDataBuffer:
    """
    Sliding-window buffer that stores all 14 model input features for each pod.

    One sample is added every PREDICTION_INTERVAL seconds.  Once the buffer
    reaches MAX_ENCODER_LENGTH samples the service can make predictions.

    Stored features per step
    ------------------------
    Known reals (time-varying, available at forecast time):
        time_idx, hour_sin, hour_cos

    Unknown reals (observable only up to t, used as encoder inputs):
        psi_some_avg10, psi_some_avg60, psi_some_avg300,
        psi_full_avg10, psi_full_avg60, psi_full_avg300,
        cpu_usage, memory_usage, latency_ms, error_rate,
        request_rate, active_connections,
        read_bytes_per_sec, write_bytes_per_sec
    """

    # Scaler means from the training checkpoint — used as fallback for
    # features that cannot be queried from Prometheus.
    _FALLBACK = {
        "request_rate":        115.63,
        "active_connections":  129.06,
        "cpu_usage":             0.576,
        "memory_usage":       2.366e9,
        "read_bytes_per_sec": 2.081e6,
        "write_bytes_per_sec":3.966e6,
        "latency_ms":          124.05,
        "error_rate":           0.00787,
    }

    def __init__(self, max_length: int = MAX_ENCODER_LENGTH):
        self.max_length = max_length
        # pod → deque of feature dicts
        self._bufs: Dict[str, deque] = {}
        # pod → monotonically increasing time_idx (resets to 0 when buffer created)
        self._tidx: Dict[str, int]   = {}

    def add_sample(self, pod: str, features: Dict[str, float], ts: datetime):
        """
        Append one sample to the buffer for `pod`.

        Parameters
        ----------
        pod      : pod name string
        features : dict with at minimum 'psi_some_avg10'; all other keys
                   are optional and fall back to the scaler training means.
        ts       : wall-clock time of this sample
        """
        if pod not in self._bufs:
            self._bufs[pod] = deque(maxlen=self.max_length)
            self._tidx[pod] = 0

        tidx      = self._tidx[pod]
        hour_frac = ts.hour + ts.minute / 60.0 + ts.second / 3600.0

        psi10  = max(0.0, features.get("psi_some_avg10", 0.0))
        psi60  = max(0.0, features.get("psi_some_avg60",  psi10 * 0.90))
        psi300 = max(0.0, features.get("psi_some_avg300", psi10 * 0.75))
        psiF10 = max(0.0, features.get("psi_full_avg10",  psi10 * 0.55))
        psiF60 = max(0.0, features.get("psi_full_avg60",  psi10 * 0.50))
        psiF300= max(0.0, features.get("psi_full_avg300", psi10 * 0.45))

        row = {
            # group
            "series_id":           "server_01_segment_0",   # mapped to known class
            # known reals
            "time_idx":            tidx,
            "hour_sin":            float(np.sin(2 * np.pi * hour_frac / 24)),
            "hour_cos":            float(np.cos(2 * np.pi * hour_frac / 24)),
            # PSI (the primary signal)
            "psi_some_avg10":      psi10,
            "psi_some_avg60":      psi60,
            "psi_some_avg300":     psi300,
            "psi_full_avg10":      psiF10,
            "psi_full_avg60":      psiF60,
            "psi_full_avg300":     psiF300,
            # correlated features (Prometheus values when available, else fallback)
            "cpu_usage":           max(0.0, features.get("cpu_usage",           self._FALLBACK["cpu_usage"])),
            "memory_usage":        max(0.0, features.get("memory_usage",        self._FALLBACK["memory_usage"])),
            "latency_ms":          max(0.0, features.get("latency_ms",          self._FALLBACK["latency_ms"])),
            "error_rate":          max(0.0, features.get("error_rate",          self._FALLBACK["error_rate"])),
            "request_rate":        max(0.0, features.get("request_rate",        self._FALLBACK["request_rate"])),
            "active_connections":  max(0.0, features.get("active_connections",  self._FALLBACK["active_connections"])),
            "read_bytes_per_sec":  max(0.0, features.get("read_bytes_per_sec",  self._FALLBACK["read_bytes_per_sec"])),
            "write_bytes_per_sec": max(0.0, features.get("write_bytes_per_sec", self._FALLBACK["write_bytes_per_sec"])),
        }

        self._bufs[pod].append(row)
        self._tidx[pod] += 1

    def ready(self, pod: str) -> bool:
        return pod in self._bufs and len(self._bufs[pod]) >= self.max_length

    def get_dataframe(self, pod: str) -> Optional[pd.DataFrame]:
        if not self.ready(pod):
            return None
        return pd.DataFrame(list(self._bufs[pod]))

    def depth(self, pod: str) -> int:
        return len(self._bufs.get(pod, []))


# ── PredictionService ─────────────────────────────────────────────────────────
class PredictionService:
    """
    Orchestrates the prediction loop:
      Prometheus → PSIDataBuffer → TFT forward pass → gate → Prometheus gauges
    """

    def __init__(self):
        self.model: Optional[TemporalFusionTransformer] = None
        self._ds_params: Optional[Dict] = None   # checkpoint dataset_parameters
        self._sc_means:  Dict[str, float] = {}   # scaler means for time_idx fill
        self.buffer  = PSIDataBuffer()
        self.running = True
        self.stats   = dict(TP=0, FP=0, FN=0, TN=0)
        self.gate    = (ConfirmationGate(threshold=SPIKE_THRESHOLD, window_seconds=60)
                        if _GATE_AVAILABLE else None)

        logger.info("PredictionService initialised")
        logger.info("  model path   : %s", MODEL_PATH)
        logger.info("  threshold    : %.2f %%", SPIKE_THRESHOLD)
        logger.info("  shadow mode  : %s", SHADOW_MODE)
        logger.info("  gate         : %s", "enabled" if self.gate else "disabled (import failed)")

    # ── model loading ──────────────────────────────────────────────────────────
    @model_load_time.time()
    def load_model(self):
        logger.info("Loading TFT checkpoint …")
        ckpt = torch.load(MODEL_PATH, map_location="cpu", weights_only=False)
        self._ds_params = ckpt["hyper_parameters"]["dataset_parameters"]

        # Extract scaler means so we can fill time_idx correctly
        for name, sc in self._ds_params["scalers"].items():
            if hasattr(sc, "mean_") and sc.mean_ is not None:
                self._sc_means[name] = float(
                    sc.mean_ if np.ndim(sc.mean_) == 0 else sc.mean_[0]
                )

        self.model = TemporalFusionTransformer.load_from_checkpoint(
            MODEL_PATH, map_location="cpu"
        )
        self.model.eval()
        n_params = sum(p.numel() for p in self.model.parameters())
        logger.info("  loaded  enc=%d  pred=%d  params=%d",
                    self._ds_params["max_encoder_length"],
                    self._ds_params["max_prediction_length"],
                    n_params)

    # ── Prometheus queries ─────────────────────────────────────────────────────
    def _prom_query(self, query: str) -> Dict:
        url = f"{PROMETHEUS_URL}/api/v1/query"
        try:
            with prom_query_latency.time():
                r = requests.get(url, params={"query": query}, timeout=5)
                r.raise_for_status()
                return r.json()
        except Exception as exc:
            logger.debug("Prometheus query failed: %s  (%s)", query[:80], exc)
            return {"status": "error", "data": {"result": []}}

    def _scalar_result(self, prom_result: Dict) -> Dict[str, float]:
        """Extract {pod: float} from a Prometheus instant-query result."""
        out = {}
        if prom_result.get("status") == "success":
            for item in prom_result["data"]["result"]:
                pod = item["metric"].get("pod") or item["metric"].get("instance", "unknown")
                try:
                    out[pod] = max(0.0, float(item["value"][1]))
                except (ValueError, IndexError):
                    pass
        return out

    def get_live_features(self) -> Dict[str, Dict[str, float]]:
        """
        Query Prometheus for all features the model needs, per workload pod.

        Returns
        -------
        {pod_name: {feature_name: float, ...}, ...}

        PSI signal
        ----------
        Primary:  container_pressure_io_some_avg10  — direct kernel avg10 in %,
                  same units as training data.  Available from cAdvisor >= 0.47.
        Fallback: irate(container_pressure_io_some_seconds_total[1m]) * 100
                  — rate of cumulative stall time, also in % units.
        Node-level fallback:
                  irate(node_pressure_io_stalled_seconds_total[1m]) * 100

        Correlated features
        -------------------
        Queried when available; each falls back to the scaler training mean
        inside PSIDataBuffer.add_sample() if the query returns nothing.
        """
        POD_RE = "workload-app-.*"

        # ── PSI io some avg10 ──────────────────────────────────────────────────
        # Try cAdvisor direct avg10 first (best match to training signal)
        psi_raw = self._scalar_result(self._prom_query(
            f'container_pressure_io_some_avg10{{pod=~"{POD_RE}",container!=""}}'
        ))

        # Fallback 1: cumulative stall rate (container level)
        if not psi_raw:
            psi_raw = self._scalar_result(self._prom_query(
                f'irate(container_pressure_io_some_seconds_total{{pod=~"{POD_RE}",container!=""}}[1m]) * 100'
            ))

        # Fallback 2: node-level stall rate (not pod-scoped but better than nothing)
        if not psi_raw:
            node_psi = self._scalar_result(self._prom_query(
                'irate(node_pressure_io_stalled_seconds_total[1m]) * 100'
            ))
            # Assign the same node-level value to every known pod
            for pod in list(self.buffer._bufs.keys()) or ["workload-app-0"]:
                if pod not in psi_raw:
                    psi_raw[pod] = list(node_psi.values())[0] if node_psi else 0.0

        # If still nothing, we have no pods — return empty
        if not psi_raw:
            logger.warning("No PSI metrics found for any pod matching '%s'", POD_RE)
            return {}

        # Seed feature dict with PSI
        features: Dict[str, Dict[str, float]] = {
            pod: {"psi_some_avg10": val} for pod, val in psi_raw.items()
        }

        # ── CPU usage (0–1 fraction) ───────────────────────────────────────────
        cpu = self._scalar_result(self._prom_query(
            f'rate(container_cpu_usage_seconds_total{{pod=~"{POD_RE}",container!=""}}[1m])'
        ))
        for pod, val in cpu.items():
            if pod in features:
                features[pod]["cpu_usage"] = min(val, 1.0)

        # ── Memory working set (bytes) ─────────────────────────────────────────
        mem = self._scalar_result(self._prom_query(
            f'container_memory_working_set_bytes{{pod=~"{POD_RE}",container!=""}}'
        ))
        for pod, val in mem.items():
            if pod in features:
                features[pod]["memory_usage"] = val

        # ── HTTP request rate (req/s) ──────────────────────────────────────────
        rps = self._scalar_result(self._prom_query(
            f'rate(http_requests_total{{pod=~"{POD_RE}"}}[1m])'
        ))
        for pod, val in rps.items():
            if pod in features:
                features[pod]["request_rate"] = val

        # ── p95 latency (ms) ───────────────────────────────────────────────────
        lat = self._scalar_result(self._prom_query(
            f'histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{{pod=~"{POD_RE}"}}[1m])) * 1000'
        ))
        for pod, val in lat.items():
            if pod in features:
                features[pod]["latency_ms"] = val

        # ── Disk read throughput (bytes/s) ─────────────────────────────────────
        rbps = self._scalar_result(self._prom_query(
            f'rate(container_fs_reads_bytes_total{{pod=~"{POD_RE}",container!=""}}[1m])'
        ))
        for pod, val in rbps.items():
            if pod in features:
                features[pod]["read_bytes_per_sec"] = val

        # ── Disk write throughput (bytes/s) ────────────────────────────────────
        wbps = self._scalar_result(self._prom_query(
            f'rate(container_fs_writes_bytes_total{{pod=~"{POD_RE}",container!=""}}[1m])'
        ))
        for pod, val in wbps.items():
            if pod in features:
                features[pod]["write_bytes_per_sec"] = val

        # Update Prometheus gauge for current PSI
        for pod, fdict in features.items():
            current_psi_gauge.labels(pod=pod).set(fdict["psi_some_avg10"])

        return features

    # ── DataFrame preparation ─────────────────────────────────────────────────
    def _build_dataframe(self, pod: str) -> Optional[pd.DataFrame]:
        """
        Return a DataFrame with ENC+PRED rows suitable for TimeSeriesDataSet.

        The encoder portion (rows 0..ENC-1) comes from the buffer.
        The decoder portion (rows ENC..ENC+PRED-1) is a copy of the last
        encoder row with time_idx and time features extended forward.
        The decoder is never used as input to unknown-reals features;
        TimeSeriesDataSet uses it only to build the prediction window index.
        """
        enc_df = self.buffer.get_dataframe(pod)
        if enc_df is None:
            return None

        last = enc_df.iloc[-1].to_dict()
        last_tidx    = int(last["time_idx"])
        last_psi     = float(last["psi_some_avg10"])
        last_psi60   = float(last["psi_some_avg60"])
        last_psi300  = float(last["psi_some_avg300"])
        last_psiF10  = float(last["psi_full_avg10"])
        last_psiF60  = float(last["psi_full_avg60"])
        last_psiF300 = float(last["psi_full_avg300"])

        dec_rows = []
        for step in range(1, MAX_PREDICTION_LENGTH + 1):
            new_tidx  = last_tidx + step
            # Advance time-of-day features by PREDICTION_INTERVAL each step
            hour_frac  = (new_tidx * PREDICTION_INTERVAL) / 3600.0 % 24
            dec_rows.append({
                "series_id":           "server_01_segment_0",
                "time_idx":            new_tidx,
                "hour_sin":            float(np.sin(2 * np.pi * hour_frac / 24)),
                "hour_cos":            float(np.cos(2 * np.pi * hour_frac / 24)),
                # Carry forward the last observed PSI values into the decoder.
                # TimeSeriesDataSet masks these for the prediction window, so
                # exact values don't matter — they affect only the encoder state.
                "psi_some_avg10":      last_psi,
                "psi_some_avg60":      last_psi60,
                "psi_some_avg300":     last_psi300,
                "psi_full_avg10":      last_psiF10,
                "psi_full_avg60":      last_psiF60,
                "psi_full_avg300":     last_psiF300,
                "cpu_usage":           float(last["cpu_usage"]),
                "memory_usage":        float(last["memory_usage"]),
                "latency_ms":          float(last["latency_ms"]),
                "error_rate":          float(last["error_rate"]),
                "request_rate":        float(last["request_rate"]),
                "active_connections":  float(last["active_connections"]),
                "read_bytes_per_sec":  float(last["read_bytes_per_sec"]),
                "write_bytes_per_sec": float(last["write_bytes_per_sec"]),
            })

        combined = pd.concat(
            [enc_df.reset_index(drop=True),
             pd.DataFrame(dec_rows)],
            ignore_index=True,
        )
        return combined

    # ── TFT forward pass ──────────────────────────────────────────────────────
    def make_prediction(self, pod: str) -> Optional[Tuple[float, float, float, bool]]:
        """
        Run the TFT on the current 30-step buffer for `pod`.

        Returns
        -------
        (q50_max, q90_max, current_psi, spike_alert)
          q50_max    : max of q50 over the 30-step horizon
          q90_max    : max of q90 over the 30-step horizon
          current_psi: last observed psi_some_avg10 value
          spike_alert: True if q90_max >= SPIKE_THRESHOLD
        Returns None if the buffer is not yet full or inference fails.
        """
        if not self.buffer.ready(pod):
            return None
        if self.model is None:
            return None

        df = self._build_dataframe(pod)
        if df is None:
            return None

        try:
            with prediction_latency.time():
                ds = TimeSeriesDataSet(
                    df,
                    time_idx="time_idx",
                    target="psi_some_avg10",
                    group_ids=["series_id"],
                    max_encoder_length=MAX_ENCODER_LENGTH,
                    max_prediction_length=MAX_PREDICTION_LENGTH,
                    time_varying_known_reals=["time_idx", "hour_sin", "hour_cos"],
                    time_varying_unknown_reals=self._ds_params["time_varying_unknown_reals"],
                    allow_missing_timesteps=False,
                    # Re-use the FITTED scalers from training so the model
                    # receives inputs normalised exactly as during training.
                    scalers=self._ds_params["scalers"],
                    categorical_encoders=self._ds_params["categorical_encoders"],
                )
                dl  = ds.to_dataloader(train=False, batch_size=1, num_workers=0)

                with torch.no_grad():
                    for x, _ in dl:
                        out  = self.model(x)
                        q    = self.model.to_quantiles(out)   # (1, PRED, 3)
                        q50  = q[0, :, 1].cpu().numpy()
                        q90  = q[0, :, 2].cpu().numpy()
                        break

            current_psi_val = float(df["psi_some_avg10"].iloc[MAX_ENCODER_LENGTH - 1])
            q50_max         = float(q50.max())
            q90_max         = float(q90.max())
            spike_alert     = q90_max >= SPIKE_THRESHOLD

            return (q50_max, q90_max, current_psi_val, spike_alert)

        except Exception as exc:
            logger.error("Inference failed for pod %s: %s", pod, exc, exc_info=True)
            return None

    # ── statistics ────────────────────────────────────────────────────────────
    def _update_stats(self, predicted: bool, actual: bool):
        if predicted and actual:
            self.stats["TP"] += 1; true_positives_ctr.inc()
        elif predicted and not actual:
            self.stats["FP"] += 1; false_positives_ctr.inc()
        elif not predicted and actual:
            self.stats["FN"] += 1; false_negatives_ctr.inc()
        else:
            self.stats["TN"] += 1

        tp = self.stats["TP"]; fp = self.stats["FP"]; fn = self.stats["FN"]
        if tp + fp > 0:
            precision_gauge.set(tp / (tp + fp))
        if tp + fn > 0:
            recall_gauge.set(tp / (tp + fn))

    def _print_stats(self):
        tp = self.stats["TP"]; fp = self.stats["FP"]
        fn = self.stats["FN"]; tn = self.stats["TN"]
        total = tp + fp + fn + tn
        logger.info("=" * 60)
        logger.info("FINAL STATISTICS  (total=%d)", total)
        if total:
            prec = tp/(tp+fp) if tp+fp else 0
            rec  = tp/(tp+fn) if tp+fn else 0
            f1   = 2*prec*rec/(prec+rec) if prec+rec else 0
            logger.info("  TP=%-6d  FP=%-6d  FN=%-6d  TN=%-6d", tp, fp, fn, tn)
            logger.info("  Precision %.3f  Recall %.3f  F1 %.3f", prec, rec, f1)
        logger.info("=" * 60)

    # ── main loop ─────────────────────────────────────────────────────────────
    def run(self):
        logger.info("Prediction loop started  (interval=%ds)", PREDICTION_INTERVAL)
        iteration = 0

        while self.running:
            try:
                iteration += 1
                now      = datetime.now()
                features = self.get_live_features()

                if not features:
                    logger.warning("No live features — waiting …")
                    time.sleep(PREDICTION_INTERVAL)
                    continue

                for pod, fdict in features.items():
                    # 1. Feed new sample into the buffer
                    self.buffer.add_sample(pod, fdict, now)

                    psi_now = fdict["psi_some_avg10"]
                    depth   = self.buffer.depth(pod)
                    logger.debug("  %-30s  PSI=%.3f  buf=%d/%d",
                                 pod, psi_now, depth, MAX_ENCODER_LENGTH)

                    if not self.buffer.ready(pod):
                        logger.info("  %s warming up (%d/%d samples)",
                                    pod, depth, MAX_ENCODER_LENGTH)
                        continue

                    # 2. Run TFT inference
                    result = self.make_prediction(pod)
                    if result is None:
                        continue

                    q50_max, q90_max, current, spike_raw = result
                    predictions_total.inc()

                    # 3. Export raw prediction
                    predicted_psi_raw.labels(pod=pod).set(q90_max)
                    predicted_psi_gauge.labels(pod=pod, quantile="q50").set(q50_max)
                    predicted_psi_gauge.labels(pod=pod, quantile="q90").set(q90_max)
                    spike_prob_gauge.labels(pod=pod).set(1.0 if spike_raw else 0.0)

                    if spike_raw:
                        spikes_predicted_total.inc()

                    # 4. Apply two-consecutive confirmation gate
                    is_confirmed = False
                    gate_reason  = "no gate"

                    if self.gate:
                        _, is_confirmed, gate_reason = self.gate.check_spike(
                            pod=pod,
                            psi_value=current,
                            predicted_psi=q90_max,
                            timestamp=now,
                        )
                    else:
                        # No gate: treat raw alert as confirmed immediately
                        is_confirmed = spike_raw

                    # 5. Export confirmed metric (this is what the HPA reads)
                    if is_confirmed:
                        predicted_psi_confirmed.labels(pod=pod).set(q90_max)
                        confirmation_gate_status.labels(pod=pod).set(1.0)
                        spikes_confirmed_total.inc()
                    else:
                        # Emit zero when not confirmed so the HPA does not
                        # trigger on stale confirmed values from prior iterations.
                        predicted_psi_confirmed.labels(pod=pod).set(0.0)
                        confirmation_gate_status.labels(pod=pod).set(0.0)

                    # 6. Log and act
                    logger.info(
                        "[iter %d] %s  PSI=%.3f%%  q50=%.3f  q90=%.3f  "
                        "raw=%s  confirmed=%s  (%s)",
                        iteration, pod, current, q50_max, q90_max,
                        "YES" if spike_raw else "no",
                        "YES" if is_confirmed else "no",
                        gate_reason,
                    )

                    if is_confirmed:
                        if SHADOW_MODE:
                            logger.info("  SHADOW — would scale up %s", pod)
                        else:
                            logger.info("  ACTION — triggering scale-up for %s", pod)
                            # Actual HPA scaling happens automatically via the
                            # predicted_psi_confirmed custom metric + Prometheus Adapter

                    # 7. Track statistics against current observed PSI
                    actual_spike = current >= SPIKE_THRESHOLD
                    if actual_spike:
                        spikes_actual_total.inc()
                    self._update_stats(is_confirmed, actual_spike)

            except KeyboardInterrupt:
                logger.info("KeyboardInterrupt — stopping")
                self.running = False
                break
            except Exception as exc:
                logger.error("Unhandled error in prediction loop: %s", exc, exc_info=True)

            time.sleep(PREDICTION_INTERVAL)

        self._print_stats()


# ── Flask health / readiness API ──────────────────────────────────────────────
app              = Flask(__name__)
_service_ref: Optional[PredictionService] = None


@app.route("/health")
def health():
    if _service_ref and _service_ref.model is not None:
        return jsonify({"status": "healthy", "model_loaded": True,
                        "shadow_mode": SHADOW_MODE,
                        "spike_threshold": SPIKE_THRESHOLD}), 200
    return jsonify({"status": "unhealthy", "model_loaded": False}), 503


@app.route("/ready")
def ready():
    if _service_ref and _service_ref.model is not None:
        return jsonify({"status": "ready"}), 200
    return jsonify({"status": "not_ready"}), 503


@app.route("/metrics-summary")
def metrics_summary():
    if _service_ref is None:
        return jsonify({"error": "not initialised"}), 503
    s  = _service_ref.stats
    tp = s["TP"]; fp = s["FP"]; fn = s["FN"]
    return jsonify({
        "precision":       tp / (tp + fp) if (tp + fp) else None,
        "recall":          tp / (tp + fn) if (tp + fn) else None,
        "true_positives":  tp, "false_positives": fp, "false_negatives": fn,
    }), 200


@app.route("/buffer-status")
def buffer_status():
    """Show how many samples are buffered per pod (useful for warm-up monitoring)."""
    if _service_ref is None:
        return jsonify({"error": "not initialised"}), 503
    status = {
        pod: {"depth": _service_ref.buffer.depth(pod),
              "ready": _service_ref.buffer.ready(pod)}
        for pod in _service_ref.buffer._bufs
    }
    return jsonify(status), 200


# ── Entry point ───────────────────────────────────────────────────────────────
def _signal_handler(signum, _frame):
    logger.info("Received signal %d — shutting down", signum)
    if _service_ref:
        _service_ref.running = False


def main() -> int:
    global _service_ref

    logger.info("=" * 60)
    logger.info("PRESYNC PREDICTION SERVICE  v2.0")
    logger.info("  shadow_mode : %s", SHADOW_MODE)
    logger.info("  threshold   : %.2f %%", SPIKE_THRESHOLD)
    logger.info("  enc / pred  : %d / %d steps", MAX_ENCODER_LENGTH, MAX_PREDICTION_LENGTH)
    logger.info("=" * 60)

    signal.signal(signal.SIGINT,  _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # Prometheus metrics server
    start_http_server(METRICS_PORT)
    logger.info("Prometheus metrics on :%d", METRICS_PORT)

    # Flask API in a daemon thread
    Thread(
        target=lambda: app.run(host="0.0.0.0", port=API_PORT, debug=False),
        daemon=True,
    ).start()
    logger.info("Flask API on :%d", API_PORT)

    # Prediction service
    _service_ref = PredictionService()
    try:
        _service_ref.load_model()
        _service_ref.run()
    except Exception as exc:
        logger.error("Fatal: %s", exc, exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
