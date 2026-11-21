#!/usr/bin/env python3
"""
Experiments 7, 8, 9: Live cluster experiments.

These experiments require:
  - A running Kind Kubernetes cluster
  - Prometheus + node_exporter PSI scrape
  - Prometheus Adapter with custom metric 'predicted_psi_confirmed'
  - A StatefulSet workload + fio/stress-ng
  - Live HTTP/DB probe measuring p99 latency

This script documents exactly what cannot be run and why,
verifies only what CAN be verified offline (Exp9 analytical model),
and saves a structured JSON record for SUMMARY.md.

Saves:
  results/exp789_live/exp789_status.json
  results/exp789_live/exp9_sensitivity_table.csv
  results/exp789_live/exp9_sensitivity_heatmap.png
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent
OUT  = REPO / "results" / "exp789_live"
OUT.mkdir(parents=True, exist_ok=True)

INTERVAL_S = 15

print("=" * 70)
print("EXPERIMENTS 7, 8, 9  Live cluster (offline status report)")
print("=" * 70)

# ── Offline checks ────────────────────────────────────────────────────────────
# Check for kubectl / kind
import subprocess

def check_cmd(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=5)
        return r.returncode == 0, r.stdout.decode("utf-8", errors="replace").strip()
    except Exception as e:
        return False, str(e)

kubectl_ok, kubectl_out = check_cmd(["kubectl", "cluster-info"])
kind_ok, kind_out       = check_cmd(["kind", "get", "clusters"])
docker_ok, docker_out   = check_cmd(["docker", "info"])

print(f"kubectl available: {kubectl_ok}")
print(f"kind available:    {kind_ok}")
print(f"docker available:  {docker_ok}")
if kind_ok: print(f"kind clusters: {kind_out}")

cluster_running = kubectl_ok and ("running" in kubectl_out.lower() or
                                   "kubernetes" in kubectl_out.lower())
print(f"Cluster accessible: {cluster_running}")

# ── Experiment 7 status ───────────────────────────────────────────────────────
exp7_status = {
    "can_run": False,
    "reason": (
        "Experiment 7 requires a live Kind cluster with fio/stress-ng stressor, "
        "node-exporter PSI scrape via Prometheus, and an HTTP/DB probe measuring "
        "p99 latency every 15 s for >= 2 hours. "
        "No Kind cluster is running (kubectl_ok={}, cluster_accessible={})."
        " No latency data has been collected.".format(kubectl_ok, cluster_running)
    ),
    "what_would_be_done": (
        "1. Run fio I/O stress on a pod for 2+ hours with 15 s PSI scrape. "
        "2. Measure p99 application latency with a wrk/hey HTTP probe every 15 s. "
        "3. Align PSI > 1.80% signal with p99 > 200 ms label. "
        "4. Compute precision/recall/ROC for 'PSI > T' predicting 'p99 > 200 ms'. "
        "5. Measure lead/lag between PSI crossing and latency breach."
    ),
    "kubectl_available": kubectl_ok,
    "kind_available": kind_ok,
    "docker_available": docker_ok,
    "cluster_running": cluster_running,
}

# ── Experiment 8 status ───────────────────────────────────────────────────────
exp8_status = {
    "can_run": False,
    "reason": (
        "Experiment 8 requires a Kind cluster with StatefulSet, min_replicas=1, "
        "max_replicas>=8, Prometheus Adapter serving 'predicted_psi_confirmed' custom "
        "metric, and the TFT inference service live. Requires 10+ run repetitions "
        "per mode (reactive vs predictive HPA) with full reset between runs. "
        "No cluster is accessible."
    ),
    "what_would_be_done": (
        "1. Configure reactive HPA (CPU/memory) and predictive HPA (custom metric). "
        "2. Run scripted fio burst: 5 min idle → 10 min ramp → 5 min idle. "
        "3. Record: burst onset, HPA scale decision, pod schedule, pod Ready. "
        "4. Repeat 10+ times per mode; compute mean±std of onset-to-Ready. "
        "5. Run Mann-Whitney U test; dump HPA YAML config."
    ),
    "hpa_config_note": (
        "HPA YAML config would be obtained via: "
        "'kubectl get hpa -o yaml'. "
        "The existing kubernetes/ directory contains deployment YAMLs that can be "
        "inspected to verify the stabilization window and sync period."
    ),
    "kubectl_available": kubectl_ok,
    "cluster_running": cluster_running,
}

# ── Experiment 9: analytical model (can be run offline) ──────────────────────
print("\n--- Experiment 9: Analytical latency model (offline) ---")

# Default Kubernetes HPA behavior (documented, verifiable against Kind version)
# scaleUp.stabilizationWindowSeconds default = 0 (since Kubernetes 1.18+, not 30 s)
# --horizontal-pod-autoscaler-sync-period default = 15 s
# These are documented facts; we note them and flag the paper's assumption.

hpa_defaults = {
    "kubernetes_version_note":
        "Kind typically runs Kubernetes 1.27+. "
        "HPA scaleUp.stabilizationWindowSeconds default = 0 (not 30 s) since K8s 1.18. "
        "scaleDown.stabilizationWindowSeconds default = 300 s. "
        "--horizontal-pod-autoscaler-sync-period default = 15 s. "
        "Cannot verify empirically without running cluster.",
    "paper_assumption_t_stabilize": 30,
    "actual_default_t_stabilize_scaleup": 0,
    "discrepancy": "Paper uses t_stabilize=30 s; K8s 1.18+ default is 0 s for scale-up.",
    "sync_period_s": 15,
}

# TFT inference time from predict_tft.py run (we measured this in Exp4)
# Use the value from Exp4 results if available, otherwise compute
exp4_inf_path = REPO / "results" / "exp4_baselines" / "inference_times.csv"
tft_inf_ms = None
if exp4_inf_path.exists():
    inf_df = pd.read_csv(exp4_inf_path)
    tft_row = inf_df[inf_df["model"]=="TFT"]
    if len(tft_row):
        tft_inf_ms = float(tft_row["inf_ms"].iloc[0])
if tft_inf_ms is None:
    # Measure inline from existing checkpoint
    import torch
    from pytorch_forecasting import TimeSeriesDataSet, TemporalFusionTransformer
    import time as _time

    model_path = REPO / "models" / "tft_psi_model.ckpt"
    if model_path.exists():
        tft_model = TemporalFusionTransformer.load_from_checkpoint(
            str(model_path)
        )
        tft_model.eval()
        sample_df = pd.read_csv(REPO / "data" / "train.csv").head(500)
        sample_df["timestamp"] = pd.to_datetime(sample_df["timestamp"])
        ds = TimeSeriesDataSet(
            sample_df,
            time_idx="time_idx", target="psi_some_avg10", group_ids=["series_id"],
            max_encoder_length=30, max_prediction_length=30,
            time_varying_known_reals=["time_idx","hour_sin","hour_cos"],
            time_varying_unknown_reals=[
                "request_rate","active_connections","cpu_usage","memory_usage",
                "read_bytes_per_sec","write_bytes_per_sec","latency_ms","error_rate",
                "psi_some_avg10","psi_some_avg60","psi_some_avg300",
                "psi_full_avg10","psi_full_avg60","psi_full_avg300"],
            allow_missing_timesteps=False,
        )
        dl = ds.to_dataloader(train=False, batch_size=1, num_workers=0)
        times = []
        with torch.no_grad():
            for i, (x, y) in enumerate(dl):
                if i >= 1000: break
                t0 = _time.perf_counter()
                _ = tft_model(x)
                times.append((_time.perf_counter()-t0)*1000)
        tft_inf_ms = float(np.mean(times))
        print(f"TFT inference: {tft_inf_ms:.4f} ms/window (n={len(times)})")

# Sensitivity table: ΔL = (T_react - T_pred) / T_react
# T_react = t_stabilize + t_sync + t_provision
# T_pred  = t_inf + t_horizon (but lead time is horizon = 30 s at 2 steps × 15 s)
# More precisely from paper: ΔL = t_lead / (t_stabilize + t_provision)
# where t_lead = horizon = 30 s (2 steps × 15 s)
T_HORIZON = 30   # seconds (2 steps × 15 s)
T_INF_S   = (tft_inf_ms or 5) / 1000   # convert ms to seconds

T_STABILIZE_VALUES = [0, 15, 30, 60]   # seconds
T_PROVISION_VALUES = [15, 30, 45, 60]  # seconds

rows_sens = []
for t_stab in T_STABILIZE_VALUES:
    for t_prov in T_PROVISION_VALUES:
        # Reactive total time from burst onset to Ready
        T_react = t_stab + INTERVAL_S + t_prov   # sync period + stabilize + provision
        # Predictive total time: alert fires 30 s before burst
        # → HPA can decide within 15 s (sync) → pod provision begins 30-15 = 15 s early
        t_lead_effective = T_HORIZON - T_INF_S - INTERVAL_S
        t_lead_effective = max(0, t_lead_effective)
        # Time saved compared to reactive
        delta_L = t_lead_effective / T_react if T_react > 0 else 0
        rows_sens.append({
            "t_stabilize_s":    t_stab,
            "t_provision_s":    t_prov,
            "T_react_s":        T_react,
            "t_lead_effective_s": round(t_lead_effective, 2),
            "delta_L_pct":      round(delta_L * 100, 2),
        })

sens_df = pd.DataFrame(rows_sens)
sens_df.to_csv(OUT / "exp9_sensitivity_table.csv", index=False)
print("\nExp9 sensitivity table (ΔL = latency reduction fraction):")
print(sens_df.pivot(index="t_stabilize_s",
                    columns="t_provision_s",
                    values="delta_L_pct").to_string())

# Paper claims 33.3% projected latency reduction
# Our analytical model at t_stab=30, t_prov=30:
row_paper = sens_df[(sens_df["t_stabilize_s"]==30) & (sens_df["t_provision_s"]==30)]
if len(row_paper):
    paper_delta = float(row_paper["delta_L_pct"].iloc[0])
    print(f"\nΔL at paper assumptions (t_stab=30, t_prov=30): {paper_delta:.2f}%")
    print(f"Paper claims 33.3%; our model gives {paper_delta:.2f}%")

exp9_status = {
    "can_run_offline_analysis": True,
    "can_run_live_measurement": False,
    "reason_live_not_runnable":
        "No Kind cluster available to empirically measure t_provision or verify "
        "HPA behavior (kubectl output not accessible).",
    "hpa_defaults": hpa_defaults,
    "tft_inf_ms": round(tft_inf_ms or 0, 4),
    "horizon_s": T_HORIZON,
    "sensitivity_table_saved": str(OUT / "exp9_sensitivity_table.csv"),
    "paper_delta_L_assumption": "33.3% at t_stab=30 s, t_prov=30 s",
    "analytical_delta_L_at_paper_params": round(paper_delta, 2) if len(row_paper) else "N/A",
}

# ── Plot: heatmap ─────────────────────────────────────────────────────────────
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

pivot = sens_df.pivot(index="t_stabilize_s", columns="t_provision_s", values="delta_L_pct")
fig, ax = plt.subplots(figsize=(7, 5))
im = ax.imshow(pivot.values, cmap="YlOrRd", aspect="auto", vmin=0, vmax=50)
ax.set_xticks(range(len(pivot.columns)))
ax.set_yticks(range(len(pivot.index)))
ax.set_xticklabels([f"{c}s" for c in pivot.columns])
ax.set_yticklabels([f"{r}s" for r in pivot.index])
ax.set_xlabel("t_provision (s)"); ax.set_ylabel("t_stabilize (s)")
ax.set_title(f"Exp9: ΔL (% latency reduction)\nhorizon={T_HORIZON}s, "
             f"t_inf={tft_inf_ms:.1f}ms" if tft_inf_ms else
             f"Exp9: ΔL (% latency reduction)\nhorizon={T_HORIZON}s")
for i in range(len(pivot.index)):
    for j in range(len(pivot.columns)):
        ax.text(j, i, f"{pivot.values[i,j]:.1f}%",
                ha="center", va="center", fontsize=10,
                color="white" if pivot.values[i,j] > 25 else "black")
plt.colorbar(im, ax=ax, label="ΔL (%)")
plt.tight_layout()
plt.savefig(OUT / "exp9_sensitivity_heatmap.png", dpi=150)
plt.close()
print(f"\nHeatmap saved to {OUT / 'exp9_sensitivity_heatmap.png'}")

# ── Summary ───────────────────────────────────────────────────────────────────
status = {
    "exp7": exp7_status,
    "exp8": exp8_status,
    "exp9": exp9_status,
}
with open(OUT / "exp789_status.json", "w") as f:
    json.dump(status, f, indent=2)

print(f"\nAll outputs saved to {OUT}")
print("EXPERIMENTS 7/8/9 (offline portion) COMPLETE")
