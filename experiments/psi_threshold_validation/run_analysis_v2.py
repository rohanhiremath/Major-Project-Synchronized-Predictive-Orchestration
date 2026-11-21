#!/usr/bin/env python3
"""
Analysis v2 — Tests 1, 3, 4 on the correct signal.

Pre-registered rules loaded from prereg_v2.yaml.
Outputs: calibration_sweep_v2.json, selected_v2.json,
         test_results_v2.json, verdict_v2.json.

STOP conditions:
  - SHA256 of any data file does not match prereg.
  - Test 1 AUC < 0.55.
  - Any assertion failure.
Failure writes FAILURE_REPORT_v2.md and exits non-zero.
"""

import csv, json, hashlib, sys, math, pathlib, datetime
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

BASE   = pathlib.Path(__file__).resolve().parent.parent.parent
EXPDIR = pathlib.Path(__file__).resolve().parent
DATA   = BASE / "data"

# ── Constants from prereg_v2.yaml (copied; do not change) ──────────────────
B_MS          = 60.34          # baseline median latency (ms)
THRESHOLD_2B  = 2.0 * B_MS    # 120.68 ms
BIN_S         = 20             # seconds per row
MERGE_ROWS    = 3              # merge gap (3 rows = 60 s)
COOLDOWN_ROWS = 3              # alert cooldown
MATCH_PRE_S   = 120            # seconds before onset
MATCH_POST_S  = 180            # seconds after onset — extended from 15s (see prereg_v2.yaml deviation note)
T_GRID        = [0.5,1.0,1.5,1.8,2.0,2.5,3.0,4.0,5.0,6.0,7.0,8.0,9.0]
K_VALUES      = [1, 3]
FA_LIMIT_PH   = 2.0            # max false alarms per hour (selection rule)
RECALL_MIN    = 0.50           # min recall for a viable threshold (selection)
PASS_RECALL_WILSON_LO = 0.60   # pass criterion: Wilson lower bound
PASS_FA_UPPER = 2.0            # pass criterion: FA rate upper bound /hr
MIN_TEST_EVENTS = 15
MIN_TEST_HOURS  = 3.0
BOOTSTRAP_N   = 2000
BOOTSTRAP_SEED = 42

EXPECTED_SHA = {
    "train.csv":      "3a636ac20df412cda0f22f6cfe5b9ac6e69b66b5cfefa47b0807fee80393955b",
    "test.csv":       "ee52a4f55439d41a57f1c0121d08203f4351695042a1f7fc79061c7313bd417d",
    "validation.csv": "a5aa59626f1d59abf42fa52b28b0d0e7ddaec1782b16b185711f9221f4118c9c",
}

# ── Helpers ────────────────────────────────────────────────────────────────

def fail(stage, message, values=None, next_step=None):
    report = {
        "stage": stage, "message": message,
        "values": values or {}, "suggested_next_diagnostic": next_step or "",
        "timestamp": datetime.datetime.now().isoformat(),
    }
    out = EXPDIR / "FAILURE_REPORT_v2.md"
    with open(out, "w") as f:
        f.write(f"# FAILURE REPORT v2\n\n")
        f.write(f"**Stage**: {stage}\n\n")
        f.write(f"**Message**: {message}\n\n")
        f.write(f"**Values**:\n```json\n{json.dumps(values or {}, indent=2)}\n```\n\n")
        f.write(f"**Suggested next diagnostic**: {next_step or 'N/A'}\n")
    print(f"\nFAILURE at stage {stage}: {message}", file=sys.stderr)
    print(f"Written: {out}", file=sys.stderr)
    sys.exit(1)

def sha256(path):
    return hashlib.sha256(open(path,"rb").read()).hexdigest()

def wilson_ci(k, n, z=1.96):
    """Wilson 95% CI for recall k/n. Returns (lo, hi)."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z*z/n
    centre = (p + z*z/(2*n)) / denom
    margin = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))

def fa_upper_bound(fa_count, monitored_hours):
    """
    Upper bound on FA rate using Poisson/normal approximation.
    (FA + 1.96*sqrt(FA + 0.96)) / hours  -- consistent with prereg.
    """
    if monitored_hours <= 0:
        return float('inf')
    return (fa_count + 1.96 * math.sqrt(fa_count + 0.96)) / monitored_hours

# ── Data loading ───────────────────────────────────────────────────────────

def load_and_verify():
    dfs = {}
    for fname, expected_hash in EXPECTED_SHA.items():
        path = DATA / fname
        actual = sha256(path)
        if actual != expected_hash:
            fail("SHA256_CHECK", f"{fname} hash mismatch",
                 {"expected": expected_hash, "actual": actual},
                 "Check that data files have not been modified since prereg.")
        dfs[fname] = pd.read_csv(path).sort_values(
            ['series_id','time_idx']).reset_index(drop=True)
    return dfs

# ── Breach event detection ─────────────────────────────────────────────────

def find_breach_events(df):
    """
    Apply pre-registered breach rule to a DataFrame.
    Returns list of dicts: {series, onset_idx, end_idx, onset_time_s, end_time_s,
                             max_latency_ms, n_rows}
    """
    events = []
    for sid, g in df.groupby('series_id', sort=True):
        g = g.reset_index(drop=True)
        deg = (g['latency_ms'] > THRESHOLD_2B).tolist()
        i = 0
        raw = []
        while i < len(deg):
            if deg[i]:
                s = i
                while i < len(deg) and deg[i]:
                    i += 1
                if i - s >= 2:
                    raw.append((s, i - 1))
            else:
                i += 1
        # merge
        merged = []
        for ev in raw:
            if merged and ev[0] - merged[-1][1] <= MERGE_ROWS:
                merged[-1][1] = ev[1]
            else:
                merged.append(list(ev))
        for (s, e) in merged:
            events.append({
                'series':       sid,
                'onset_idx':    int(s),
                'end_idx':      int(e),
                'onset_time_s': int(g['time_idx'].iloc[s] * BIN_S),
                'end_time_s':   int(g['time_idx'].iloc[e] * BIN_S),
                'max_latency':  float(g['latency_ms'].iloc[s:e+1].max()),
                'n_rows':       int(e - s + 1),
            })
    return events

# ── Alert firing ───────────────────────────────────────────────────────────

def fire_alerts(df, T, k):
    """
    Fire alerts per series using pre-registered alert rule.
    Returns list of dicts: {series, alert_time_s}
    """
    alerts = []
    for sid, g in df.groupby('series_id', sort=True):
        g = g.reset_index(drop=True)
        run = 0
        cooldown_until_idx = -1
        for i, row in g.iterrows():
            if row['psi_some_avg10'] > T:
                run += 1
            else:
                run = 0
            if run >= k and i > cooldown_until_idx:
                alerts.append({
                    'series':       sid,
                    'alert_time_s': int(row['time_idx'] * BIN_S),
                    'psi_value':    float(row['psi_some_avg10']),
                })
                cooldown_until_idx = i + COOLDOWN_ROWS
                run = 0
    return alerts

# ── Match alerts to events ────────────────────────────────────────────────

def match(alerts, events):
    """
    Returns (matched_event_indices, fa_count, lead_times).
    Each event matched to at most one alert (earliest in window).
    """
    matched = set()
    fa = 0
    lead_times = []
    for a in alerts:
        hit = False
        for j, ev in enumerate(events):
            if ev['series'] != a['series']:
                continue
            lo = ev['onset_time_s'] - MATCH_PRE_S
            hi = ev['onset_time_s'] + MATCH_POST_S
            if lo <= a['alert_time_s'] <= hi and j not in matched:
                matched.add(j)
                lead_times.append(ev['onset_time_s'] - a['alert_time_s'])
                hit = True
                break
        if not hit:
            fa += 1
    return matched, fa, lead_times

# ══════════════════════════════════════════════════════════════════════════════
# TEST 1: Signal sanity — AUC + distributions
# ══════════════════════════════════════════════════════════════════════════════

def test1(train_df):
    print("\n" + "="*60)
    print("TEST 1: Signal Sanity (AUC + Distributions)")
    print("="*60)

    # Per-row breach label
    label = (train_df['latency_ms'] > THRESHOLD_2B).astype(int)
    signal = train_df['psi_some_avg10'].clip(lower=0)

    n_pos = int(label.sum())
    n_neg = int((label == 0).sum())
    print(f"Breach rows: {n_pos}  Non-breach rows: {n_neg}  Total: {len(label)}")

    if n_pos == 0 or n_neg == 0:
        fail("TEST1_AUC", "All rows have the same label; AUC undefined.",
             {"n_pos": n_pos, "n_neg": n_neg},
             "Check breach threshold 2xB against latency_ms distribution.")

    auc = float(roc_auc_score(label, signal))
    print(f"AUC (signal predicts per-row breach label): {auc:.4f}")

    if auc < 0.55:
        fail("TEST1_AUC",
             f"AUC={auc:.4f} < 0.55: signal carries no information about outcome.",
             {"auc": auc, "threshold": 0.55},
             "Check signal query and latency column. Consider resampling or lag correction.")

    # Calm vs stress distribution
    calm_rows   = train_df[train_df['psi_some_avg10'] == 0.0]['psi_some_avg10']
    stress_rows = train_df[train_df['psi_some_avg10'] > 0.0]['psi_some_avg10']
    all_rows    = signal

    def dist(s):
        a = s.values
        return {
            'n':   int(len(a)),
            'min': float(np.min(a))  if len(a) else None,
            'p50': float(np.median(a)) if len(a) else None,
            'p90': float(np.percentile(a, 90)) if len(a) else None,
            'p95': float(np.percentile(a, 95)) if len(a) else None,
            'p99': float(np.percentile(a, 99)) if len(a) else None,
            'max': float(np.max(a))  if len(a) else None,
        }

    result = {
        "auc":          auc,
        "n_breach_rows":     n_pos,
        "n_non_breach_rows": n_neg,
        "B_ms":         B_MS,
        "threshold_2B_ms": THRESHOLD_2B,
        "signal_distribution": {
            "all_rows":   dist(all_rows),
            "calm_rows":  dist(calm_rows),
            "stress_rows": dist(stress_rows),
        },
    }

    print(f"Signal distribution (all train rows):")
    for k2, v2 in dist(all_rows).items():
        print(f"  {k2:4s}: {v2}")
    print(f"  (calm=PSI==0: {len(calm_rows)} rows; stress=PSI>0: {len(stress_rows)} rows)")

    return result

# ══════════════════════════════════════════════════════════════════════════════
# TEST 3: Calibration sweep
# ══════════════════════════════════════════════════════════════════════════════

def test3(train_df, cal_events, cal_hours):
    print("\n" + "="*60)
    print("TEST 3: Calibration Sweep")
    print(f"Events: {len(cal_events)}   Monitored: {cal_hours:.2f}h")
    print("="*60)

    sweep = []
    hdr = f"{'T':>5} {'k':>2}  {'recall':>7} {'det/tot':>8}  {'FA':>4} {'FA/hr':>7}  {'prec':>6}  {'lt_med':>7} {'lt_iqr':>7}"
    print(hdr)
    print("-" * len(hdr))

    for T in T_GRID:
        for k in K_VALUES:
            alerts = fire_alerts(train_df, T, k)
            matched, fa, lead_times = match(alerts, cal_events)

            n_ev   = len(cal_events)
            recall = len(matched) / n_ev if n_ev else 0.0
            fa_ph  = fa / cal_hours
            prec   = len(matched) / (len(matched) + fa) if (len(matched) + fa) > 0 else 0.0
            lt_med = float(np.median(lead_times)) if lead_times else None
            lt_iqr = float(np.percentile(lead_times, 75) - np.percentile(lead_times, 25)) \
                     if len(lead_times) >= 2 else None

            row = {
                "T": T, "k": k,
                "recall":           round(recall, 4),
                "events_detected":  len(matched),
                "events_total":     n_ev,
                "false_alarms":     fa,
                "fa_per_hour":      round(fa_ph, 4),
                "precision":        round(prec, 4),
                "lead_time_median_s": round(lt_med, 1) if lt_med is not None else None,
                "lead_time_iqr_s":    round(lt_iqr, 1) if lt_iqr is not None else None,
                "n_alerts":         len(alerts),
            }
            sweep.append(row)

            lt_s = f"{lt_med:+7.1f}" if lt_med is not None else "   None"
            li_s = f"{lt_iqr:7.1f}"  if lt_iqr is not None else "   None"
            print(f"{T:5.1f} {k:2d}  {recall:7.4f} {len(matched):4d}/{n_ev:<4d}"
                  f"  {fa:4d} {fa_ph:7.3f}  {prec:6.4f}  {lt_s} {li_s}")

    # ── Apply selection rule ──
    candidates = [r for r in sweep
                  if r['fa_per_hour'] <= FA_LIMIT_PH and r['recall'] >= RECALL_MIN]

    if not candidates:
        sel_result = "no_viable_threshold"
        best = None
        print("\nSelection: no (T,k) achieves recall>=0.5 AND FA/hr<=2.0")
    else:
        best = max(candidates,
                   key=lambda r: (r['recall'], -r['false_alarms'], r['T']))
        sel_result = "selected"
        print(f"\nSelected: T={best['T']}%  k={best['k']}"
              f"  recall={best['recall']}  FA/hr={best['fa_per_hour']}")

    return sweep, {"selection_result": sel_result, "selected": best, "all_candidates": candidates}

# ══════════════════════════════════════════════════════════════════════════════
# TEST 4: Held-out evaluation (run ONCE)
# ══════════════════════════════════════════════════════════════════════════════

def evaluate_once(test_df, test_events, test_hours, T_eval, k_eval, label):
    """Evaluate one (T,k) pair on test data."""
    alerts  = fire_alerts(test_df, T_eval, k_eval)
    matched, fa, lead_times = match(alerts, test_events)

    n_ev   = len(test_events)
    recall = len(matched) / n_ev if n_ev else 0.0
    fa_ph  = fa / test_hours if test_hours > 0 else float('inf')
    prec   = len(matched) / (len(matched) + fa) if (len(matched) + fa) > 0 else 0.0
    lt_med = float(np.median(lead_times)) if lead_times else None
    lt_iqr = (float(np.percentile(lead_times, 75) - np.percentile(lead_times, 25))
              if len(lead_times) >= 2 else None)
    ci_lo, ci_hi = wilson_ci(len(matched), n_ev)
    fa_ub  = fa_upper_bound(fa, test_hours)

    # ── Pass criteria (pre-registered) ──
    if n_ev < MIN_TEST_EVENTS or test_hours < MIN_TEST_HOURS:
        verdict = "UNDERPOWERED"
    elif ci_lo >= PASS_RECALL_WILSON_LO and fa_ub <= PASS_FA_UPPER:
        verdict = "SUPPORTED_FOR_THIS_WORKLOAD"
    else:
        verdict = "NOT_SUPPORTED"

    return {
        "label":               label,
        "T": T_eval, "k": k_eval,
        "events_total":        n_ev,
        "events_detected":     len(matched),
        "recall":              round(recall, 4),
        "false_alarms_total":  fa,
        "fa_per_hour":         round(fa_ph, 4),
        "fa_upper_bound_ph":   round(fa_ub, 4),
        "precision":           round(prec, 4),
        "lead_time_median_s":  round(lt_med, 1) if lt_med is not None else None,
        "lead_time_iqr_s":     round(lt_iqr, 1) if lt_iqr is not None else None,
        "wilson_95ci_recall":  [round(ci_lo, 4), round(ci_hi, 4)],
        "n_alerts":            len(alerts),
        "test_hours":          round(test_hours, 3),
        "verdict":             verdict,
    }

def bootstrap_test(test_df, test_events, test_hours, T_eval, k_eval):
    """
    Bootstrap over series (2000 iterations, seed=42).
    Returns bootstrap CI for recall and FA rate.
    NOTE: skipped if series count < 2 (can't resample) or events < 5.
    """
    series_ids = test_df['series_id'].unique().tolist()
    if len(series_ids) < 2 or len(test_events) < 5:
        return {"skipped": True, "reason": f"Too few series ({len(series_ids)}) or events ({len(test_events)}) for meaningful bootstrap"}

    rng     = np.random.default_rng(BOOTSTRAP_SEED)
    recalls = []
    fa_phs  = []

    for _ in range(BOOTSTRAP_N):
        sample_ids = rng.choice(series_ids, size=len(series_ids), replace=True).tolist()
        frames = []
        for i, sid in enumerate(sample_ids):
            chunk = test_df[test_df['series_id'] == sid].copy()
            # remap series_id to avoid collision in find_breach_events
            chunk = chunk.copy()
            chunk['series_id'] = f"boot_{i}_{sid}"
            frames.append(chunk)
        boot_df = pd.concat(frames, ignore_index=True)
        boot_events = find_breach_events(boot_df)
        n_ev = len(boot_events)
        if n_ev == 0:
            recalls.append(0.0)
            fa_phs.append(0.0)
            continue
        alerts = fire_alerts(boot_df, T_eval, k_eval)
        matched, fa, _ = match(alerts, boot_events)
        recalls.append(len(matched) / n_ev)
        fa_phs.append(fa / test_hours if test_hours > 0 else float('inf'))

    return {
        "recall_median":    round(float(np.median(recalls)), 4),
        "recall_p2_5":      round(float(np.percentile(recalls, 2.5)), 4),
        "recall_p97_5":     round(float(np.percentile(recalls, 97.5)), 4),
        "fa_ph_median":     round(float(np.median(fa_phs)), 4),
        "fa_ph_p2_5":       round(float(np.percentile(fa_phs, 2.5)), 4),
        "fa_ph_p97_5":      round(float(np.percentile(fa_phs, 97.5)), 4),
        "n_iterations":     BOOTSTRAP_N,
        "seed":             BOOTSTRAP_SEED,
    }

def test4(test_df, test_events, test_hours, selected, T_grid):
    print("\n" + "="*60)
    print("TEST 4: Held-Out Evaluation (runs once)")
    print(f"Events: {len(test_events)}   Monitored: {test_hours:.2f}h")
    print("="*60)

    results = []

    # (a) Selected (T, k)
    if selected:
        T_sel = selected['T']
        k_sel = selected['k']
        r = evaluate_once(test_df, test_events, test_hours, T_sel, k_sel, "selected")
        bs = bootstrap_test(test_df, test_events, test_hours, T_sel, k_sel)
        r['bootstrap'] = bs
        results.append(r)
        print(f"\n  selected  T={T_sel}%  k={k_sel}")
        print(f"    recall={r['recall']} ({r['events_detected']}/{r['events_total']})"
              f"  FA/hr={r['fa_per_hour']}  Wilson95=[{r['wilson_95ci_recall'][0]},{r['wilson_95ci_recall'][1]}]")
        print(f"    VERDICT: {r['verdict']}")

    # (b) T=1.8 with same k as selected (or k=1 if no selection)
    k_ref = selected['k'] if selected else 1
    r18 = evaluate_once(test_df, test_events, test_hours, 1.8, k_ref, "T=1.8_project")
    bs18 = bootstrap_test(test_df, test_events, test_hours, 1.8, k_ref)
    r18['bootstrap'] = bs18
    results.append(r18)
    print(f"\n  T=1.8  k={k_ref}")
    print(f"    recall={r18['recall']} ({r18['events_detected']}/{r18['events_total']})"
          f"  FA/hr={r18['fa_per_hour']}  Wilson95=[{r18['wilson_95ci_recall'][0]},{r18['wilson_95ci_recall'][1]}]")
    print(f"    VERDICT: {r18['verdict']}")

    # Exploratory full grid (labelled, not used to choose)
    print("\n  --- Exploratory (informational only) ---")
    exploratory = []
    for T in T_grid:
        for k in K_VALUES:
            er = evaluate_once(test_df, test_events, test_hours, T, k,
                               f"exploratory_T{T}_k{k}")
            exploratory.append(er)
            print(f"  T={T:4.1f} k={k}  recall={er['recall']}  "
                  f"FA/hr={er['fa_per_hour']}  {er['verdict']}")

    return results, exploratory

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("="*60)
    print("PSI THRESHOLD VALIDATION v2")
    print(f"Started: {datetime.datetime.now().isoformat()}")
    print("="*60)

    # ── Load and verify ──
    print("\nVerifying SHA256 hashes...")
    dfs = load_and_verify()
    print("  All SHA256 hashes match.")

    train_df = dfs["train.csv"]
    test_df  = pd.concat([dfs["validation.csv"], dfs["test.csv"]], ignore_index=True)

    # Reindex time_idx per series in test_df (concat may cause duplicates)
    test_df = test_df.sort_values(['series_id','time_idx']).reset_index(drop=True)

    cal_hours  = len(train_df) * BIN_S / 3600
    test_hours = len(test_df)  * BIN_S / 3600
    print(f"Calibration: {len(train_df)} rows  {cal_hours:.2f}h")
    print(f"Test:        {len(test_df)} rows  {test_hours:.2f}h")

    # ── Breach events ──
    cal_events  = find_breach_events(train_df)
    test_events = find_breach_events(test_df)
    print(f"CAL breach events:  {len(cal_events)}")
    print(f"TEST breach events: {len(test_events)}")

    # ── Test 1 ──
    t1 = test1(train_df)

    # ── Test 3 ──
    sweep, selection = test3(train_df, cal_events, cal_hours)

    # ── Write Test 3 outputs ──
    with open(EXPDIR / "calibration_sweep_v2.json", "w") as f:
        json.dump({
            "prereg_sha256": "2ff19c58a3e7a2436392b3bf8c93b1f3d7596eaaead1b24906b8690cbc76b2a7",
            "B_ms": B_MS, "threshold_2B_ms": THRESHOLD_2B,
            "cal_events": len(cal_events), "cal_hours": cal_hours,
            "test1_auc": t1["auc"],
            "signal_distribution": t1["signal_distribution"],
            "sweep": sweep,
        }, f, indent=2)
    print(f"\nWrote calibration_sweep_v2.json")

    with open(EXPDIR / "selected_v2.json", "w") as f:
        json.dump(selection, f, indent=2)
    print(f"Wrote selected_v2.json")

    # ── Test 4 ──
    primary, exploratory = test4(
        test_df, test_events, test_hours,
        selection.get("selected"), T_GRID
    )

    # ── Write Test 4 outputs ──
    with open(EXPDIR / "test_results_v2.json", "w") as f:
        json.dump({
            "prereg_sha256": "2ff19c58a3e7a2436392b3bf8c93b1f3d7596eaaead1b24906b8690cbc76b2a7",
            "B_ms": B_MS, "threshold_2B_ms": THRESHOLD_2B,
            "test_events": len(test_events), "test_hours": test_hours,
            "primary": primary,
            "exploratory": exploratory,
        }, f, indent=2)
    print(f"\nWrote test_results_v2.json")

    # ── Verdict ──
    main_result = primary[0] if primary else primary[0] if len(primary)>0 else None
    t18_result  = next((r for r in primary if r['label'] == 'T=1.8_project'), None)

    verdict = {
        "T_selected":         selection['selected']['T'] if selection['selected'] else None,
        "k_selected":         selection['selected']['k'] if selection['selected'] else None,
        "selection_result":   selection['selection_result'],
        "verdict":            main_result['verdict']  if main_result  else "NO_SELECTION",
        "recall":             main_result['recall']   if main_result  else None,
        "fa_per_hour":        main_result['fa_per_hour'] if main_result else None,
        "fa_upper_bound_ph":  main_result['fa_upper_bound_ph'] if main_result else None,
        "wilson_95ci_recall": main_result['wilson_95ci_recall'] if main_result else None,
        "test_events":        len(test_events),
        "test_hours":         round(test_hours, 3),
        "T_1_8_verdict":      t18_result['verdict']   if t18_result  else None,
        "T_1_8_recall":       t18_result['recall']    if t18_result  else None,
        "T_1_8_fa_ph":        t18_result['fa_per_hour'] if t18_result else None,
        "T_1_8_wilson_95ci":  t18_result['wilson_95ci_recall'] if t18_result else None,
        "bootstrap_selected": main_result.get('bootstrap') if main_result else None,
        "bootstrap_T_1_8":    t18_result.get('bootstrap')  if t18_result  else None,
        "test1_auc":          t1['auc'],
        "prereg_sha256":      "2ff19c58a3e7a2436392b3bf8c93b1f3d7596eaaead1b24906b8690cbc76b2a7",
        "signal_definition_sha256": "61484120305457364fda4bcd50afa9f178c962b061fa810b5458a649078bacb0",
        "generated_at":       datetime.datetime.now().isoformat(),
        "note": (
            "Results apply to this workload, these 6 server series, and the signal "
            "deriv(node_pressure_memory_waiting_seconds_total[2m])*100. "
            "Host activity during data collection affects node-level PSI."
        ),
    }

    with open(EXPDIR / "verdict_v2.json", "w") as f:
        json.dump(verdict, f, indent=2)
    print(f"Wrote verdict_v2.json")

    print("\n" + "="*60)
    print(f"FINAL VERDICT: T={verdict['T_selected']}%  k={verdict['k_selected']}")
    print(f"  {verdict['verdict']}")
    print(f"  recall={verdict['recall']}  FA/hr={verdict['fa_per_hour']}")
    if verdict['wilson_95ci_recall']:
        print(f"  Wilson95CI={verdict['wilson_95ci_recall']}")
    print(f"T=1.8 verdict: {verdict['T_1_8_verdict']}  recall={verdict['T_1_8_recall']}")
    print("="*60)


if __name__ == "__main__":
    main()
