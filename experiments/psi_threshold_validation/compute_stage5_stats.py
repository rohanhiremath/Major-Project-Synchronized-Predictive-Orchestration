#!/usr/bin/env python3
"""
Compute Stage 5 summary statistics from session CSVs.
Applies the pre-registered breach rule:
  degraded bin: p99 > 2.0 * B  OR  error_count > 0
  breach event: first bin of >= 2 consecutive degraded bins
  merge: events < 60s apart are merged
  B: median of 5s-bin p99 from calm sessions only (no injector)
Outputs stage5_stats.json with counts used in experiment_log.md.
"""
import json, csv, numpy as np
from pathlib import Path
from collections import defaultdict

SDIR   = Path(__file__).resolve().parent / 'session_logs'
BIN_S  = 5       # seconds per bin
MERGE_GAP_S = 60 # seconds -- events within this gap are merged

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


def load_metrics(name):
    """Return list of dicts from metrics.csv, skipping rows with no p99."""
    path = SDIR / name / 'metrics.csv'
    rows = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            p99_s = row.get('p99_latency_ms', '').strip()
            err_s = row.get('error_count', '0').strip()
            t_s   = row.get('monotonic_time', '').strip()
            if not t_s:
                continue
            rows.append({
                'mono_time':   float(t_s),
                'p99':         float(p99_s) if p99_s else None,
                'error_count': int(err_s) if err_s else 0,
                'psi_cg':      float(row.get('pod_psi_some_avg10','').strip() or 0),
                'psi_node':    float(row.get('node_psi_some_avg10','').strip() or 0),
            })
    return rows


def compute_B(calm_sessions):
    """Baseline B: median of 5s-bin p99 values across all calm sessions."""
    all_p99 = []
    for name in calm_sessions:
        rows = load_metrics(name)
        for r in rows:
            if r['p99'] is not None:
                all_p99.append(r['p99'])
    return float(np.median(all_p99)) if all_p99 else None


def find_breach_events(rows, B):
    """Apply pre-registered breach rule. Return list of event dicts."""
    # Step 1: label each bin
    for r in rows:
        r['degraded'] = (r['p99'] is not None and r['p99'] > 2.0 * B) \
                        or r['error_count'] > 0

    # Step 2: find runs of >= 2 consecutive degraded bins
    events = []
    i = 0
    while i < len(rows):
        if rows[i]['degraded']:
            run_start = i
            while i < len(rows) and rows[i]['degraded']:
                i += 1
            run_end = i - 1
            run_len = run_end - run_start + 1
            if run_len >= 2:
                onset_t = rows[run_start]['mono_time'] - BIN_S  # start of bin
                end_t   = rows[run_end]['mono_time']
                max_p99 = max(r['p99'] for r in rows[run_start:run_end+1]
                              if r['p99'] is not None)
                events.append({
                    'onset_s':     onset_t,
                    'end_s':       end_t,
                    'duration_s':  end_t - onset_t,
                    'max_p99':     max_p99,
                    'bin_count':   run_len,
                })
        else:
            i += 1

    # Step 3: merge events < 60s apart
    if not events:
        return events
    merged = [events[0]]
    for ev in events[1:]:
        last = merged[-1]
        gap = ev['onset_s'] - last['end_s']
        if gap < MERGE_GAP_S:
            last['end_s']      = ev['end_s']
            last['duration_s'] = last['end_s'] - last['onset_s']
            last['max_p99']    = max(last['max_p99'], ev['max_p99'])
            last['bin_count'] += ev['bin_count']
        else:
            merged.append(ev)
    return merged


def compute_psi_calm_p95(calm_sessions):
    """95th percentile of cgroup PSI across all calm-session bins."""
    vals = []
    for name in calm_sessions:
        rows = load_metrics(name)
        for r in rows:
            if r['psi_cg'] is not None:
                vals.append(r['psi_cg'])
    return float(np.percentile(vals, 95)) if vals else None


def session_psi_stats(name):
    rows = load_metrics(name)
    psi  = [r['psi_cg'] for r in rows if r['psi_cg'] is not None]
    if not psi:
        return {'max': None, 'mean': None, 'p95': None}
    return {
        'max':  float(max(psi)),
        'mean': float(np.mean(psi)),
        'p95':  float(np.percentile(psi, 95)),
    }


def main():
    calm_names = [s['name'] for s in SESSIONS if s['type'] == 'calm']
    stress_names = [s['name'] for s in SESSIONS if s['type'] == 'stress']

    print(f"Calm sessions:   {calm_names}")
    print(f"Stress sessions: {stress_names}")

    # Compute B from ALL calm sessions
    B = compute_B(calm_names)
    print(f"\nBaseline B = {B:.4f} ms  (2xB = {2*B:.4f} ms)")

    # PSI calm p95
    psi_calm_p95 = compute_psi_calm_p95(calm_names)
    print(f"Calm PSI p95 = {psi_calm_p95:.4f}%")

    # Breach events per session
    session_results = {}
    cal_events_total  = 0
    test_events_total = 0

    print(f"\n{'Session':<18} {'Set':4} {'Type':6} {'Events':7} {'PSI_max':8} {'Max_p99_ms':12}")
    print("-" * 60)

    for s in SESSIONS:
        name = s['name']
        rows = load_metrics(name)

        if s['type'] == 'stress':
            events = find_breach_events(rows, B)
        else:
            events = []   # calm sessions have no injector -- should be 0

        psi = session_psi_stats(name)

        p99_all = [r['p99'] for r in rows if r['p99'] is not None]
        max_p99 = max(p99_all) if p99_all else 0.0

        session_results[name] = {
            'set':          s['set'],
            'type':         s['type'],
            'n_events':     len(events),
            'events':       events,
            'psi_max':      psi['max'],
            'psi_mean':     psi['mean'],
            'max_p99_ms':   max_p99,
            'total_bins':   len(rows),
            'duration_min': len(rows) * BIN_S / 60,
        }

        if s['set'] == 'CAL' and s['type'] == 'stress':
            cal_events_total += len(events)
        elif s['set'] == 'TEST' and s['type'] == 'stress':
            test_events_total += len(events)

        print(f"{name:<18} {s['set']:4} {s['type']:6} {len(events):7d} "
              f"{psi['max'] if psi['max'] is not None else 0:8.2f} {max_p99:12.2f}")

    print("-" * 60)
    print(f"CAL breach events total:  {cal_events_total}")
    print(f"TEST breach events total: {test_events_total}")

    # Total monitored time
    total_bins = sum(v['total_bins'] for v in session_results.values())
    cal_time_h  = sum(v['duration_min'] for k, v in session_results.items()
                      if v['set'] == 'CAL') / 60
    test_time_h = sum(v['duration_min'] for k, v in session_results.items()
                      if v['set'] == 'TEST') / 60
    total_time_h = (total_bins * BIN_S) / 3600

    print(f"\nTotal monitored time: {total_time_h:.2f} h")
    print(f"CAL time:  {cal_time_h:.2f} h   TEST time: {test_time_h:.2f} h")

    # Check prereg targets
    print(f"\nPrereq targets:")
    print(f"  CAL events >= 15:  {cal_events_total} -> {'PASS' if cal_events_total >= 15 else 'FAIL'}")
    print(f"  TEST events >= 10: {test_events_total} -> {'PASS' if test_events_total >= 10 else 'FAIL'}")
    print(f"  TEST time >= 3h:   {test_time_h:.2f}h -> {'PASS' if test_time_h >= 3 else 'FAIL'}")
    print(f"  Calm sessions >= 3: {len(calm_names)} -> {'PASS' if len(calm_names) >= 3 else 'FAIL'}")

    # Save
    output = {
        'baseline_B_ms':          B,
        'baseline_2B_ms':         2 * B,
        'psi_calm_p95_pct':       psi_calm_p95,
        'cal_events_total':       cal_events_total,
        'test_events_total':      test_events_total,
        'total_monitored_hours':  total_time_h,
        'cal_monitored_hours':    cal_time_h,
        'test_monitored_hours':   test_time_h,
        'n_calm_sessions':        len(calm_names),
        'n_cal_stress_sessions':  len([s for s in SESSIONS if s['set']=='CAL' and s['type']=='stress']),
        'n_test_stress_sessions': len([s for s in SESSIONS if s['set']=='TEST' and s['type']=='stress']),
        'sessions':               session_results,
    }

    out_path = Path(__file__).resolve().parent / 'stage5_stats.json'
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"\nSaved: {out_path}")


if __name__ == '__main__':
    main()
