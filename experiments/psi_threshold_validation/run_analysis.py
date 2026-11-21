#!/usr/bin/env python3
"""
Stage 5 → 6 → 7 analysis.

Reads the 15 completed session CSVs, applies the pre-registered breach
and alert rules across the FULL T_grid, selects the best (T, k) on
calibration data, then evaluates it once on test data.

Pre-registered rules (from prereg.yaml):
  - B: median of 5s-bin p99 across all calm sessions
  - degraded bin: p99 > 2*B  OR  error_count > 0
  - breach event: first bin of >=2 consecutive degraded bins;
                  events <60s apart merged
  - alert: PSI (cgroup some_avg10) > T for k consecutive bins;
           60s cooldown after each alert
  - match window: [onset-120s, onset+15s]
  - selection (CAL only): max recall subject to FA <= 2/hr;
                          tie-break: fewer FA, then higher T
  - verdict (T=best, TEST): SUPPORTED if recall>=0.8 AND FA<=2/hr
  - UNDERPOWERED overrides if test has <10 breach events OR <3h monitored

Outputs: calibration_sweep.json, selected.json, test_results.json,
         verdict.json, stage5_stats.json (updated).
"""

import csv, json, numpy as np
from pathlib import Path
from scipy import stats as scipy_stats

SDIR      = Path(__file__).resolve().parent / 'session_logs'
OUT_DIR   = Path(__file__).resolve().parent
BIN_S     = 5
MERGE_GAP = 60   # seconds
COOLDOWN  = 60   # seconds
MATCH_PRE = 120  # seconds before onset
MATCH_POST = 15  # seconds after onset

T_GRID = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2, 1.5, 1.8, 2.0, 2.5, 3.0, 4.0, 5.0]
K_VALUES = [1, 3]

SESSIONS = [
    {'id':  1, 'name': 'cal_burst_1',  'set': 'CAL',  'type': 'stress'},
    {'id':  2, 'name': 'test_burst_1', 'set': 'TEST', 'type': 'stress'},
    {'id':  3, 'name': 'cal_ramp_1',   'set': 'CAL',  'type': 'stress'},
    {'id':  4, 'name': 'test_ramp_1',  'set': 'TEST', 'type': 'stress'},
    {'id':  5, 'name': 'cal_step_1',   'set': 'CAL',  'type': 'stress'},
    {'id':  6, 'name': 'test_step_1',  'set': 'TEST', 'type': 'stress'},
    {'id':  7, 'name': 'cal_calm_1',   'set': 'CAL',  'type': 'calm'},
    {'id':  8, 'name': 'test_calm_1',  'set': 'TEST', 'type': 'calm'},
    {'id':  9, 'name': 'cal_calm_2',   'set': 'CAL',  'type': 'calm'},
    {'id': 10, 'name': 'test_burst_2', 'set': 'TEST', 'type': 'stress'},
    {'id': 11, 'name': 'cal_burst_2',  'set': 'CAL',  'type': 'stress'},
    {'id': 12, 'name': 'test_burst_3', 'set': 'TEST', 'type': 'stress'},
    {'id': 13, 'name': 'cal_burst_3',  'set': 'CAL',  'type': 'stress'},
    {'id': 14, 'name': 'test_calm_2',  'set': 'TEST', 'type': 'calm'},
    {'id': 15, 'name': 'cal_calm_3',   'set': 'CAL',  'type': 'calm'},
]

# ─────────────────────────────── helpers ────────────────────────────────

def load_metrics(name):
    rows = []
    with open(SDIR / name / 'metrics.csv') as f:
        for row in csv.DictReader(f):
            t = row.get('monotonic_time','').strip()
            if not t: continue
            p   = row.get('p99_latency_ms','').strip()
            err = row.get('error_count','0').strip()
            psi = row.get('pod_psi_some_avg10','').strip()
            rows.append({
                'mono_time':  float(t),
                'p99':        float(p)   if p   else None,
                'error_count':int(err)   if err else 0,
                'psi':        float(psi) if psi else 0.0,
            })
    return rows


def compute_B(calm_sessions):
    vals = []
    for name in calm_sessions:
        for r in load_metrics(name):
            if r['p99'] is not None:
                vals.append(r['p99'])
    return float(np.median(vals))


def find_breach_events(rows, B):
    for r in rows:
        r['degraded'] = (r['p99'] is not None and r['p99'] > 2.0 * B) \
                        or r['error_count'] > 0
    events = []
    i = 0
    while i < len(rows):
        if rows[i]['degraded']:
            s = i
            while i < len(rows) and rows[i]['degraded']:
                i += 1
            e = i - 1
            if e - s + 1 >= 2:
                onset = rows[s]['mono_time'] - BIN_S
                end   = rows[e]['mono_time']
                events.append({'onset_s': onset, 'end_s': end,
                                'max_p99': max(r['p99'] for r in rows[s:e+1] if r['p99'])})
        else:
            i += 1
    if not events:
        return events
    merged = [events[0]]
    for ev in events[1:]:
        if ev['onset_s'] - merged[-1]['end_s'] < MERGE_GAP:
            merged[-1]['end_s']   = ev['end_s']
            merged[-1]['max_p99'] = max(merged[-1]['max_p99'], ev['max_p99'])
        else:
            merged.append(ev)
    return merged


def fire_alerts(rows, T, k):
    """Return list of alert times (monotonic_time of firing bin)."""
    alerts = []
    run = 0
    cooldown_until = -1
    for r in rows:
        t = r['mono_time']
        if r['psi'] > T:
            run += 1
        else:
            run = 0
        if run >= k and t > cooldown_until:
            alerts.append(t)
            cooldown_until = t + COOLDOWN
            run = 0
    return alerts


def match_alerts_to_events(alerts, events):
    """
    Returns (matched_events, false_alarms, lead_times).
    Each breach event can be matched by at most one alert (first in window).
    """
    matched_event_ids = set()
    false_alarms = 0
    lead_times = []

    for at in alerts:
        matched = False
        for i, ev in enumerate(events):
            window_start = ev['onset_s'] - MATCH_PRE
            window_end   = ev['onset_s'] + MATCH_POST
            if window_start <= at <= window_end and i not in matched_event_ids:
                matched_event_ids.add(i)
                lead_times.append(ev['onset_s'] - at)  # positive = early
                matched = True
                break
        if not matched:
            false_alarms += 1

    return matched_event_ids, false_alarms, lead_times


def wilson_ci(successes, total, z=1.96):
    if total == 0:
        return (0.0, 0.0)
    p = successes / total
    denom = 1 + z*z/total
    centre = (p + z*z/(2*total)) / denom
    margin = (z * (p*(1-p)/total + z*z/(4*total*total))**0.5) / denom
    return (max(0, centre - margin), min(1, centre + margin))


# ──────────────────────────────── main ──────────────────────────────────

def main():
    calm_names = [s['name'] for s in SESSIONS if s['type'] == 'calm']
    cal_sess   = [s for s in SESSIONS if s['set'] == 'CAL']
    test_sess  = [s for s in SESSIONS if s['set'] == 'TEST']

    B = compute_B(calm_names)
    print(f"B = {B:.4f} ms   2×B = {2*B:.4f} ms")

    # ── Pre-compute breach events and raw rows per session ──
    all_rows   = {}
    all_events = {}
    for s in SESSIONS:
        rows = load_metrics(s['name'])
        all_rows[s['name']]   = rows
        if s['type'] == 'stress':
            all_events[s['name']] = find_breach_events(rows, B)
        else:
            all_events[s['name']] = []

    cal_events_total  = sum(len(all_events[s['name']]) for s in cal_sess if s['type']=='stress')
    test_events_total = sum(len(all_events[s['name']]) for s in test_sess if s['type']=='stress')
    cal_time_h  = sum(len(all_rows[s['name']]) * BIN_S for s in cal_sess)  / 3600
    test_time_h = sum(len(all_rows[s['name']]) * BIN_S for s in test_sess) / 3600

    print(f"CAL  breach events: {cal_events_total}   time: {cal_time_h:.2f}h")
    print(f"TEST breach events: {test_events_total}   time: {test_time_h:.2f}h")
    print()

    # ── Stage 6: calibration sweep ──────────────────────────────────────
    print("=== Stage 6: Calibration Sweep ===")
    sweep = []
    for T in T_GRID:
        for k in K_VALUES:
            # Collect all alerts and events across CAL sessions
            total_matched = set()
            total_events_list = []
            total_fa = 0
            total_lt = []
            event_offset = 0

            for s in cal_sess:
                rows   = all_rows[s['name']]
                events = all_events[s['name']]
                alerts = fire_alerts(rows, T, k)
                if events:
                    m, fa, lt = match_alerts_to_events(alerts, events)
                    for idx in m:
                        total_matched.add(event_offset + idx)
                    total_fa += fa
                    total_lt.extend(lt)
                    total_events_list.extend(events)
                    event_offset += len(events)
                else:
                    # calm CAL sessions: any alert is a false alarm
                    total_fa += len(alerts)

            n_events = cal_events_total
            recall   = len(total_matched) / n_events if n_events else 0.0
            fa_ph    = total_fa / cal_time_h if cal_time_h else 0.0
            precision = (len(total_matched) / (len(total_matched) + total_fa)
                         if (len(total_matched) + total_fa) > 0 else 0.0)
            lt_med = float(np.median(total_lt)) if total_lt else None
            lt_iqr = float(np.percentile(total_lt, 75) - np.percentile(total_lt, 25)) \
                     if len(total_lt) >= 2 else None

            sweep.append({
                'T': T, 'k': k,
                'recall': round(recall, 4),
                'events_detected': len(total_matched),
                'events_total': n_events,
                'false_alarms': total_fa,
                'fa_per_hour': round(fa_ph, 4),
                'precision': round(precision, 4),
                'lead_time_median_s': round(lt_med, 2) if lt_med is not None else None,
                'lead_time_iqr_s':    round(lt_iqr, 2) if lt_iqr is not None else None,
            })

    # Print sweep table
    print(f"{'T':>6} {'k':>3} {'recall':>8} {'det/tot':>8} {'FA':>5} {'FA/hr':>7} {'prec':>6} {'lt_med':>8}")
    print("-"*65)
    for row in sweep:
        print(f"{row['T']:6.1f} {row['k']:3d} {row['recall']:8.4f} "
              f"{row['events_detected']:4d}/{row['events_total']:<4d}"
              f"{row['false_alarms']:5d} {row['fa_per_hour']:7.3f} "
              f"{row['precision']:6.4f} "
              f"{str(row['lead_time_median_s']):>8}")

    with open(OUT_DIR / 'calibration_sweep.json', 'w') as f:
        json.dump(sweep, f, indent=2)
    print(f"\nSaved calibration_sweep.json")

    # ── Apply selection rule ─────────────────────────────────────────────
    # max recall subject to FA <= 2/hr; tie-break: fewer FA, then higher T
    candidates = [r for r in sweep if r['fa_per_hour'] <= 2.0 and r['recall'] >= 0.5]
    if not candidates:
        best = None
        selection_result = 'no_viable_threshold'
        print("\nSelection: no (T,k) achieves recall>=0.5 with FA<=2/hr")
    else:
        best = max(candidates,
                   key=lambda r: (r['recall'], -r['false_alarms'], r['T']))
        selection_result = 'selected'
        print(f"\nSelected: T={best['T']}% k={best['k']} "
              f"recall={best['recall']:.4f} FA/hr={best['fa_per_hour']:.4f}")

    with open(OUT_DIR / 'selected.json', 'w') as f:
        json.dump({'selection_result': selection_result,
                   'selected': best,
                   'all_candidates': candidates}, f, indent=2)

    # ── Stage 7: test evaluation ─────────────────────────────────────────
    print("\n=== Stage 7: Test Evaluation ===")

    def evaluate_on_test(T_eval, k_eval, label):
        total_matched = set()
        total_fa = 0
        total_lt = []
        event_offset = 0
        per_session = []

        for s in test_sess:
            rows   = all_rows[s['name']]
            events = all_events[s['name']]
            alerts = fire_alerts(rows, T_eval, k_eval)
            if events:
                m, fa, lt = match_alerts_to_events(alerts, events)
                for idx in m:
                    total_matched.add(event_offset + idx)
                total_fa += fa
                total_lt.extend(lt)
                event_offset += len(events)
                per_session.append({
                    'session': s['name'], 'n_events': len(events),
                    'detected': len(m), 'false_alarms': fa,
                    'recall': round(len(m)/len(events), 4) if events else None,
                })
            else:
                total_fa += len(alerts)
                per_session.append({
                    'session': s['name'], 'n_events': 0,
                    'detected': 0, 'false_alarms': len(alerts), 'recall': None,
                })
            event_offset += len(events)

        n_ev   = test_events_total
        recall = len(total_matched) / n_ev if n_ev else 0.0
        fa_ph  = total_fa / test_time_h if test_time_h else 0.0
        prec   = (len(total_matched) / (len(total_matched) + total_fa)
                  if (len(total_matched) + total_fa) > 0 else 0.0)
        lt_med = float(np.median(total_lt)) if total_lt else None
        lt_iqr = (float(np.percentile(total_lt, 75) - np.percentile(total_lt, 25))
                  if len(total_lt) >= 2 else None)
        ci_lo, ci_hi = wilson_ci(len(total_matched), n_ev)

        # Determine verdict
        if n_ev < 10 or test_time_h < 3.0:
            verdict = 'UNDERPOWERED'
        elif recall >= 0.8 and fa_ph <= 2.0:
            verdict = 'SUPPORTED_FOR_THIS_WORKLOAD'
        else:
            verdict = 'NOT_SUPPORTED'

        result = {
            'label': label,
            'T': T_eval, 'k': k_eval,
            'events_total': n_ev,
            'events_detected': len(total_matched),
            'recall': round(recall, 4),
            'false_alarms_total': total_fa,
            'fa_per_hour': round(fa_ph, 4),
            'precision': round(prec, 4),
            'lead_time_median_s': round(lt_med, 2) if lt_med is not None else None,
            'lead_time_iqr_s':    round(lt_iqr, 2) if lt_iqr is not None else None,
            'wilson_95ci_recall': [round(ci_lo, 4), round(ci_hi, 4)],
            'test_time_h': round(test_time_h, 3),
            'verdict': verdict,
            'per_session': per_session,
        }

        print(f"\n  {label}  T={T_eval}%  k={k_eval}")
        print(f"    recall={recall:.4f} ({len(total_matched)}/{n_ev})  "
              f"FA/hr={fa_ph:.4f}  precision={prec:.4f}")
        print(f"    lead_time_median={lt_med}s  "
              f"Wilson95CI=[{ci_lo:.4f},{ci_hi:.4f}]")
        print(f"    VERDICT: {verdict}")
        return result

    results = []

    # (a) Selected (T,k)
    if best is not None:
        r = evaluate_on_test(best['T'], best['k'], 'selected')
        results.append(r)

    # (b) Project's configured T=1.8 with same k as selected (or k=1 if no selection)
    k_ref = best['k'] if best else 1
    r18   = evaluate_on_test(1.8, k_ref, 'T=1.8_project')
    results.append(r18)

    # Exploratory: full grid on test (not used for selection, labelled clearly)
    print("\n  --- Exploratory grid on TEST (informational only) ---")
    exploratory = []
    for T in T_GRID:
        for k in K_VALUES:
            er = evaluate_on_test(T, k, f'exploratory_T{T}_k{k}')
            exploratory.append(er)

    with open(OUT_DIR / 'test_results.json', 'w') as f:
        json.dump({'primary': results, 'exploratory': exploratory}, f, indent=2)
    print(f"\nSaved test_results.json")

    # Verdict for the selected threshold
    primary_verdict = results[0] if results else r18
    verdict_out = {
        'T_selected':    primary_verdict['T'],
        'k_selected':    primary_verdict['k'],
        'verdict':       primary_verdict['verdict'],
        'recall':        primary_verdict['recall'],
        'fa_per_hour':   primary_verdict['fa_per_hour'],
        'wilson_95ci':   primary_verdict['wilson_95ci_recall'],
        'test_events':   primary_verdict['events_total'],
        'test_hours':    primary_verdict['test_time_h'],
        'T_1_8_verdict': r18['verdict'],
        'T_1_8_recall':  r18['recall'],
        'T_1_8_fa_ph':   r18['fa_per_hour'],
        'note': (
            'T_selected is the threshold chosen by the pre-registered selection '
            'rule on calibration data. T=1.8 is the project-configured value '
            'evaluated once on test data. Both verdicts apply only to this '
            'workload and this host. Node-level PSI is affected by other '
            'processes on the host.'
        ),
    }
    with open(OUT_DIR / 'verdict.json', 'w') as f:
        json.dump(verdict_out, f, indent=2)
    print(f"\nSaved verdict.json")
    print(f"\n{'='*60}")
    print(f"FINAL VERDICT:  T={primary_verdict['T']}%  k={primary_verdict['k']}")
    print(f"  {primary_verdict['verdict']}")
    print(f"  recall={primary_verdict['recall']}  FA/hr={primary_verdict['fa_per_hour']}")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
