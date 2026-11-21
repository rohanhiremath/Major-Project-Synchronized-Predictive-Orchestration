#!/usr/bin/env python3
"""
Stage 5: Calibration & Test Sessions for PSI Threshold Validation.

Approach: host-level user-delegated cgroup v2 (no Kubernetes).
  - Service: psitest.scope (systemd user scope, Delegate=yes)
  - Cgroup: /sys/fs/cgroup/user.slice/.../app.slice/psitest.scope/
  - memory.high written directly (owned by user kesavan-p)
  - Load generator: aiohttp 40 req/s, latency measured OUTSIDE cgroup
  - PSI logger: 5s bins, cgroup memory.pressure + /proc/pressure/memory
  - Injector: writes memory.high per profile schedule
  - Safety: abort if host MemAvailable < 1 GiB

Session schedule frozen 2026-10-15 before any PSI-vs-latency analysis.
Assignment rule: odd session IDs -> CALIBRATION, even -> TEST.
"""

import asyncio
import aiohttp
import time
import csv
import json
import os
import sys
import glob
from datetime import datetime
from pathlib import Path
import numpy as np

# ============================ Paths ============================

SERVICE_URL = 'http://127.0.0.1:8888/work'
HEALTH_URL  = 'http://127.0.0.1:8888/health'

# Discover cgroup dynamically at startup
def find_cgroup():
    pattern = '/sys/fs/cgroup/user.slice/user-*/user@*.service/app.slice/psitest.scope'
    matches = glob.glob(pattern)
    if matches:
        return matches[0]
    return None

CGROUP_PATH = None   # set at startup in main()

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / 'session_logs'

# ============================ Configuration ============================

REQUEST_RATE        = 40      # req/s constant background load
BIN_DURATION        = 5       # seconds per log row
STABILIZATION_TIME  = 30      # seconds of calm before each session
COOLDOWN_TIME       = 60      # seconds between sessions
SAFETY_MB           = 1024    # abort if MemAvailable < 1 GiB
HEARTBEAT_INTERVAL  = 30      # seconds

# Injector parameters (v8: 150MB working set, squeeze to 50MB)
RAMP_START_MB   = 140         # memory.high at ramp start (just below ws)
BURST_TARGET_MB = 50          # memory.high during burst ON phase
STEP_TARGET_MB  = 50          # memory.high for step profile
RAMP_TARGET_MB  = 50          # memory.high at ramp end

# ============================ Session Schedule ============================
# Frozen 2026-10-15. Assignment: odd -> CAL, even -> TEST.
# Profile format:
#   burst:TARGET_MB:ON_S:OFF_S:CYCLES
#   ramp:TARGET_MB:DURATION_MIN   (ramp from RAMP_START_MB down to TARGET_MB)
#   step:TARGET_MB:DURATION_MIN   (immediate squeeze, hold)
#   calm:DURATION_MIN

SESSIONS = [
    # --- Frozen 8-session schedule ---
    {'id':  1, 'name': 'cal_burst_1',  'set': 'CAL',  'type': 'stress',
     'profile': 'burst:200:180:90:4',  'duration': 1200},
    {'id':  2, 'name': 'test_burst_1', 'set': 'TEST', 'type': 'stress',
     'profile': 'burst:200:180:90:4',  'duration': 1200},
    {'id':  3, 'name': 'cal_ramp_1',   'set': 'CAL',  'type': 'stress',
     'profile': 'ramp:200:20',         'duration': 1200},
    {'id':  4, 'name': 'test_ramp_1',  'set': 'TEST', 'type': 'stress',
     'profile': 'ramp:200:20',         'duration': 1200},
    {'id':  5, 'name': 'cal_step_1',   'set': 'CAL',  'type': 'stress',
     'profile': 'step:200:20',         'duration': 1200},
    {'id':  6, 'name': 'test_step_1',  'set': 'TEST', 'type': 'stress',
     'profile': 'step:200:20',         'duration': 1200},
    {'id':  7, 'name': 'cal_calm_1',   'set': 'CAL',  'type': 'calm',
     'profile': 'calm:20',             'duration': 1200},
    {'id':  8, 'name': 'test_calm_1',  'set': 'TEST', 'type': 'calm',
     'profile': 'calm:20',             'duration': 1200},
    # --- Additional sessions for event targets and >=3 calm sessions ---
    {'id':  9, 'name': 'cal_calm_2',   'set': 'CAL',  'type': 'calm',
     'profile': 'calm:20',             'duration': 1200},
    {'id': 10, 'name': 'test_burst_2', 'set': 'TEST', 'type': 'stress',
     'profile': 'burst:200:180:90:4',  'duration': 1200},
    {'id': 11, 'name': 'cal_burst_2',  'set': 'CAL',  'type': 'stress',
     'profile': 'burst:200:180:90:4',  'duration': 1200},
    {'id': 12, 'name': 'test_burst_3', 'set': 'TEST', 'type': 'stress',
     'profile': 'burst:200:180:90:4',  'duration': 1200},
    {'id': 13, 'name': 'cal_burst_3',  'set': 'CAL',  'type': 'stress',
     'profile': 'burst:200:180:90:4',  'duration': 1200},
    # --- Third calm session pair ---
    {'id': 14, 'name': 'test_calm_2',  'set': 'TEST', 'type': 'calm',
     'profile': 'calm:20',             'duration': 1200},
    {'id': 15, 'name': 'cal_calm_3',   'set': 'CAL',  'type': 'calm',
     'profile': 'calm:20',             'duration': 1200},
    # --- Additional sessions to reach CAL event target (>=15) ---
    # Session 16: even -> TEST (required by assignment rule)
    {'id': 16, 'name': 'test_burst_4', 'set': 'TEST', 'type': 'stress',
     'profile': 'burst:50:180:90:4',   'duration': 1200},
    # Session 17: odd -> CAL
    {'id': 17, 'name': 'cal_burst_4',  'set': 'CAL',  'type': 'stress',
     'profile': 'burst:50:180:90:4',   'duration': 1200},
    # Session 18: even -> TEST
    {'id': 18, 'name': 'test_burst_5', 'set': 'TEST', 'type': 'stress',
     'profile': 'burst:50:180:90:4',   'duration': 1200},
    # Session 19: odd -> CAL  (reaches 15 CAL events: 13+4=17 or at worst 13+2=15)
    {'id': 19, 'name': 'cal_burst_5',  'set': 'CAL',  'type': 'stress',
     'profile': 'burst:50:180:90:4',   'duration': 1200},
]

# ============================ Helpers ============================

def read_psi_file(path):
    """Return (some_avg10, full_avg10) from a kernel pressure file."""
    try:
        with open(path) as f:
            lines = f.readlines()
        some = full = None
        for line in lines:
            if line.startswith('some'):
                for tok in line.split():
                    if tok.startswith('avg10='):
                        some = float(tok.split('=')[1])
            elif line.startswith('full'):
                for tok in line.split():
                    if tok.startswith('avg10='):
                        full = float(tok.split('=')[1])
        return some, full
    except Exception:
        return None, None

def read_mem_available_mb():
    try:
        with open('/proc/meminfo') as f:
            for line in f:
                if line.startswith('MemAvailable:'):
                    return int(line.split()[1]) / 1024
    except Exception:
        pass
    return None

def read_cgroup_memory_mb():
    try:
        with open(f'{CGROUP_PATH}/memory.current') as f:
            return int(f.read().strip()) / (1024 * 1024)
    except Exception:
        return None

def set_memory_high(value):
    """Write memory.high directly. value: int bytes, or 'max'."""
    try:
        with open(f'{CGROUP_PATH}/memory.high', 'w') as f:
            f.write(str(value))
    except Exception as e:
        print(f"  [injector] memory.high write error: {e}", flush=True)

# ============================ Server check ============================

def server_is_healthy():
    import urllib.request
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=3) as r:
            return r.status == 200
    except Exception:
        return False

# ============================ Async session components ============================

async def load_generator(duration, request_log, start_time, state):
    """40 req/s external load generator. Latency measured outside cgroup."""
    interval = 1.0 / REQUEST_RATE
    target_time = start_time
    connector = aiohttp.TCPConnector(limit=80, force_close=False)
    timeout_cfg = aiohttp.ClientTimeout(total=5)

    try:
        async with aiohttp.ClientSession(connector=connector, timeout=timeout_cfg) as session:
            while True:
                now = time.monotonic()
                if now - start_time >= duration or state.get('aborted'):
                    break
                elapsed = now - start_time
                req_start = time.monotonic()
                try:
                    async with session.get(SERVICE_URL) as resp:
                        lat = (time.monotonic() - req_start) * 1000
                        request_log.append((elapsed, lat, resp.status))
                except Exception:
                    lat = (time.monotonic() - req_start) * 1000
                    request_log.append((elapsed, lat, 0))

                target_time += interval
                sleep_t = target_time - time.monotonic()
                if sleep_t > 0:
                    await asyncio.sleep(min(sleep_t, interval))
    except Exception as e:
        state['load_gen_error'] = str(e)
        print(f"  [load_gen] ERROR: {e}", flush=True)


async def psi_logger(duration, request_log, start_time, csv_writer, csv_file, state):
    """Log one row every 5s. Safety abort if MemAvailable < 1 GiB."""
    bin_num = 0
    last_hb_count = 0
    last_hb_bin   = 0

    while True:
        now = time.monotonic()
        if now - start_time >= duration or state.get('aborted'):
            break

        # Wait for next bin boundary
        target_t = start_time + (bin_num + 1) * BIN_DURATION
        wait = target_t - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)

        bin_num   += 1
        bin_start  = (bin_num - 1) * BIN_DURATION
        bin_end    = bin_num * BIN_DURATION

        # PSI readings
        node_some, node_full = read_psi_file('/proc/pressure/memory')
        cg_some,   cg_full   = read_psi_file(f'{CGROUP_PATH}/memory.pressure')

        # Memory readings
        host_mem = read_mem_available_mb()
        cg_mem   = read_cgroup_memory_mb()

        # Safety
        if host_mem is not None and host_mem < SAFETY_MB:
            state['aborted']      = 'ABORTED_SAFETY'
            state['abort_reason'] = f'MemAvailable={host_mem:.1f}MB < {SAFETY_MB}MB'
            set_memory_high('max')
            print(f"  [SAFETY] {state['abort_reason']}", flush=True)
            break

        # Latency from external load generator
        bin_reqs   = [r for r in request_log if bin_start <= r[0] < bin_end]
        good_lat   = [r[1] for r in bin_reqs if r[2] == 200]
        err_count  = len(bin_reqs) - len(good_lat)
        p99        = float(np.percentile(good_lat, 99)) if good_lat else None
        req_rate   = len(bin_reqs) / BIN_DURATION

        # Write row
        ts = datetime.now().isoformat()
        csv_writer.writerow([
            ts,
            f'{bin_end:.1f}',
            f'{node_some:.4f}' if node_some is not None else '',
            f'{node_full:.4f}' if node_full is not None else '',
            f'{cg_some:.4f}'  if cg_some  is not None else '',
            f'{cg_full:.4f}'  if cg_full  is not None else '',
            f'{host_mem:.1f}' if host_mem is not None else '',
            f'{cg_mem:.1f}'   if cg_mem   is not None else '',
            f'{p99:.2f}'      if p99       is not None else '',
            err_count,
            f'{req_rate:.2f}',
            len(bin_reqs),
        ])
        csv_file.flush()

        psi_s = f'{cg_some:.2f}' if cg_some is not None else '----'
        p99_s = f'{p99:.2f}'     if p99      is not None else '----'
        mem_s = f'{host_mem:.0f}MB' if host_mem is not None else '----'
        print(f"  [{ts}] bin={bin_num:3d} psi={psi_s}% p99={p99_s}ms "
              f"err={err_count} rate={req_rate:.1f} hostmem={mem_s}", flush=True)

        # Heartbeat every 30s
        if (bin_num - last_hb_bin) * BIN_DURATION >= HEARTBEAT_INTERVAL:
            new_reqs = len(request_log) - last_hb_count
            if new_reqs == 0:
                gap = {'time': bin_end, 'component': 'load_generator',
                       'reason': f'0 new reqs in last {(bin_num-last_hb_bin)*BIN_DURATION}s'}
                state.setdefault('gaps', []).append(gap)
                print(f"  [heartbeat] WARNING: load_generator stale", flush=True)
            last_hb_count = len(request_log)
            last_hb_bin   = bin_num

    csv_file.flush()


async def injector(duration, profile, start_time, state):
    """Control memory.high per pre-registered profile."""
    if profile.startswith('calm'):
        set_memory_high('max')
        return

    parts      = profile.split(':')
    ptype      = parts[0]
    target_mb  = int(parts[1])
    target_b   = target_mb * 1024 * 1024

    try:
        if ptype == 'burst':
            on_s   = int(parts[2])
            off_s  = int(parts[3])
            cycles = int(parts[4])

            for c in range(cycles):
                if state.get('aborted'):
                    set_memory_high('max')
                    return

                c_start = c * (on_s + off_s)

                # ON phase
                set_memory_high(target_b)
                print(f"  [injector] cycle {c+1}/{cycles} ON "
                      f"({target_mb}MB for {on_s}s)", flush=True)
                while time.monotonic() - start_time < c_start + on_s:
                    if state.get('aborted'):
                        set_memory_high('max')
                        return
                    await asyncio.sleep(1)

                # OFF phase
                set_memory_high('max')
                print(f"  [injector] cycle {c+1}/{cycles} OFF "
                      f"(released for {off_s}s)", flush=True)
                while time.monotonic() - start_time < c_start + on_s + off_s:
                    if state.get('aborted'):
                        return
                    await asyncio.sleep(1)

        elif ptype == 'ramp':
            dur_s    = int(parts[2]) * 60
            start_b  = RAMP_START_MB * 1024 * 1024
            n_steps  = dur_s // BIN_DURATION
            print(f"  [injector] ramp {RAMP_START_MB}MB -> {target_mb}MB "
                  f"over {dur_s}s", flush=True)
            for step in range(n_steps):
                if state.get('aborted'):
                    set_memory_high('max')
                    return
                frac = step / max(n_steps - 1, 1)
                val  = int(start_b + (target_b - start_b) * frac)
                set_memory_high(val)
                await asyncio.sleep(BIN_DURATION)

        elif ptype == 'step':
            dur_s = int(parts[2]) * 60
            set_memory_high(target_b)
            print(f"  [injector] step {target_mb}MB for {dur_s}s", flush=True)
            deadline = start_time + dur_s
            while time.monotonic() < deadline:
                if state.get('aborted'):
                    set_memory_high('max')
                    return
                await asyncio.sleep(BIN_DURATION)

        else:
            print(f"  [injector] unknown profile type: {ptype}", flush=True)

    except Exception as e:
        state['injector_error'] = str(e)
        print(f"  [injector] ERROR: {e}", flush=True)
    finally:
        set_memory_high('max')
        print(f"  [injector] released memory.high=max", flush=True)


# ============================ Session runner ============================

async def run_session(session):
    name     = session['name']
    duration = session['duration']
    profile  = session['profile']

    print(f"\n{'='*70}", flush=True)
    print(f"SESSION {session['id']}: {name}  ({session['set']}, {session['type']})", flush=True)
    print(f"Profile: {profile}  Duration: {duration}s", flush=True)
    print(f"CGROUP: {CGROUP_PATH}", flush=True)
    print(f"{'='*70}", flush=True)

    # Ensure released and server healthy
    set_memory_high('max')
    if not server_is_healthy():
        print("  ERROR: server not healthy before session", flush=True)
        return {'name': name, 'set': session['set'], 'type': session['type'],
                'aborted': 'ABORTED_INFRA', 'abort_reason': 'server not healthy'}

    print(f"  Stabilization: {STABILIZATION_TIME}s...", flush=True)
    await asyncio.sleep(STABILIZATION_TIME)

    out_dir = OUTPUT_DIR / name
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / 'metrics.csv'
    csv_file = open(csv_path, 'w', newline='')
    csv_w    = csv.writer(csv_file)
    csv_w.writerow([
        'timestamp', 'monotonic_time',
        'node_psi_some_avg10', 'node_psi_full_avg10',
        'pod_psi_some_avg10',  'pod_psi_full_avg10',
        'host_mem_available_mb', 'pod_memory_usage_mb',
        'p99_latency_ms', 'error_count', 'request_rate', 'request_count',
    ])

    request_log = []
    state       = {'aborted': None, 'gaps': []}
    start_time  = time.monotonic()
    start_ts    = datetime.now().isoformat()

    await asyncio.gather(
        load_generator(duration, request_log, start_time, state),
        psi_logger(duration, request_log, start_time, csv_w, csv_file, state),
        injector(duration, profile, start_time, state),
        return_exceptions=True,
    )

    end_ts = datetime.now().isoformat()

    # Save per-request CSV
    req_csv = out_dir / 'requests.csv'
    with open(req_csv, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['monotonic_time', 'latency_ms', 'status_code'])
        for r in request_log:
            w.writerow([f'{r[0]:.3f}', f'{r[1]:.2f}', r[2]])

    csv_file.close()

    total   = len(request_log)
    errors  = sum(1 for r in request_log if r[2] != 200)

    meta = {
        'session_id':     session['id'],
        'name':           name,
        'set':            session['set'],
        'type':           session['type'],
        'profile':        profile,
        'duration_s':     duration,
        'request_rate':   REQUEST_RATE,
        'start_time':     start_ts,
        'end_time':       end_ts,
        'total_requests': total,
        'total_errors':   errors,
        'aborted':        state.get('aborted'),
        'abort_reason':   state.get('abort_reason'),
        'gaps':           state.get('gaps', []),
        'cgroup_path':    CGROUP_PATH,
        'working_set_mb': 600,
        'ramp_start_mb':  RAMP_START_MB,
    }
    with open(out_dir / 'metadata.json', 'w') as f:
        json.dump(meta, f, indent=2)

    print(f"  Session {name}: {total} requests, {errors} errors, "
          f"aborted={state.get('aborted')}, gaps={len(state.get('gaps',[]))}", flush=True)
    return meta


# ============================ Main ============================

async def main():
    global CGROUP_PATH

    print("="*70, flush=True)
    print("STAGE 5: CALIBRATION & TEST SESSIONS", flush=True)
    print(f"Start: {datetime.now().isoformat()}", flush=True)
    print("="*70, flush=True)

    # Discover cgroup
    CGROUP_PATH = find_cgroup()
    if not CGROUP_PATH:
        print("FATAL: psitest.scope cgroup not found. "
              "Start server with: systemd-run --user --unit=psitest --scope "
              "-p Delegate=yes -p MemoryMax=1200M python3 /tmp/psi_server.py", flush=True)
        sys.exit(1)
    print(f"Cgroup: {CGROUP_PATH}", flush=True)

    # Verify server
    if not server_is_healthy():
        print("FATAL: Server not healthy.", flush=True)
        sys.exit(1)
    print("Server: healthy", flush=True)

    # Safety pre-check
    mem = read_mem_available_mb()
    print(f"Host MemAvailable: {mem:.0f} MB (safety floor: {SAFETY_MB} MB)", flush=True)
    if mem is not None and mem < SAFETY_MB:
        print("FATAL: MemAvailable already below safety threshold", flush=True)
        sys.exit(1)

    # Verify PSI readable
    some, _ = read_psi_file(f'{CGROUP_PATH}/memory.pressure')
    if some is None:
        print("FATAL: Cannot read cgroup memory.pressure", flush=True)
        sys.exit(1)
    print(f"PSI: readable (some_avg10={some:.4f}%)", flush=True)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Run sessions (skip already-completed ones)
    all_meta = []
    for i, session in enumerate(SESSIONS):
        out_dir = OUTPUT_DIR / session['name']
        meta_f  = out_dir / 'metadata.json'
        if meta_f.exists():
            print(f"\nSKIP {session['name']} (already completed)", flush=True)
            with open(meta_f) as f:
                all_meta.append(json.load(f))
            continue

        meta = await run_session(session)
        all_meta.append(meta)

        if i < len(SESSIONS) - 1:
            print(f"  Cooldown {COOLDOWN_TIME}s...", flush=True)
            await asyncio.sleep(COOLDOWN_TIME)

    # Final stats
    set_memory_high('max')
    print("\n" + "="*70, flush=True)
    print("STAGE 5 COMPLETE", flush=True)
    print(f"End: {datetime.now().isoformat()}", flush=True)

    cal_stress  = [m for m in all_meta if m.get('set') == 'CAL'  and m.get('type') == 'stress']
    test_stress = [m for m in all_meta if m.get('set') == 'TEST' and m.get('type') == 'stress']
    calm_sess   = [m for m in all_meta if m.get('type') == 'calm']
    aborted     = [m['name'] for m in all_meta if m.get('aborted')]

    print(f"Sessions total: {len(all_meta)}", flush=True)
    print(f"CAL stress: {len(cal_stress)}  TEST stress: {len(test_stress)}", flush=True)
    print(f"Calm: {len(calm_sess)}", flush=True)
    if aborted:
        print(f"Aborted: {aborted}", flush=True)

    with open(OUTPUT_DIR / 'stage5_summary.json', 'w') as f:
        json.dump(all_meta, f, indent=2, default=str)

    print(f"\nOutputs: {OUTPUT_DIR}/", flush=True)


if __name__ == '__main__':
    asyncio.run(main())
