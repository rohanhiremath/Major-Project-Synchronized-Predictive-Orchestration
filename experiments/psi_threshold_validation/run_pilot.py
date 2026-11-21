#!/usr/bin/env python3
"""
Stage 4: Pilot Gate
- Run 1 calm baseline session (20 min)
- Run 3 pilot stress episodes
- Verify workload couples memory pressure to latency
"""
import os
import sys
import time
import json
import subprocess
import requests
import numpy as np
import pandas as pd
from pathlib import Path

# Get kind node IP
try:
    node_ip = subprocess.check_output(
        "docker ps | grep presync-control-plane | awk '{print $1}' | xargs docker inspect --format='{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'",
        shell=True, text=True
    ).strip()
    INJECTOR_URL = f'http://{node_ip}:30081'
    SERVICE_URL = f'http://{node_ip}:30080'
    print(f"Using kind node IP: {node_ip}")
except Exception as e:
    INJECTOR_URL = 'http://localhost:30081'
    SERVICE_URL = 'http://localhost:30080'
    print(f"Warning: Could not get kind node IP, using localhost: {e}")

SESSION_DIR = Path('session_logs')

def run_calm_baseline():
    """Run calm baseline session (no injector)"""
    print("="*60)
    print("PILOT: Calm Baseline Session")
    print("="*60)
    
    session_name = 'pilot_calm_baseline'
    duration_minutes = 20
    
    # Ensure injector is off
    try:
        requests.post(f"{INJECTOR_URL}/release", json={}, timeout=5)
        print("✓ Injector released")
    except:
        print("⚠️  Could not reach injector")
    
    # Run logger
    cmd = f"python3 psi_latency_logger.py {session_name} {duration_minutes}"
    print(f"Running: {cmd}")
    
    result = subprocess.run(cmd, shell=True)
    
    if result.returncode != 0:
        print(f"✗ Baseline session failed")
        return None
    
    # Load and analyze
    csv_path = SESSION_DIR / session_name / 'metrics.csv'
    if not csv_path.exists():
        print(f"✗ Metrics file not found: {csv_path}")
        return None
    
    df = pd.read_csv(csv_path)
    
    # Calculate baseline B (median p99)
    p99_values = df['p99_latency_ms'].dropna()
    baseline_B = p99_values.median()
    
    print(f"\n✓ Baseline B = {baseline_B:.2f} ms (median p99 from {len(p99_values)} bins)")
    
    # Save baseline
    baseline_data = {
        'session': session_name,
        'duration_minutes': duration_minutes,
        'baseline_B_ms': float(baseline_B),
        'num_bins': len(p99_values),
        'p99_stats': {
            'mean': float(p99_values.mean()),
            'std': float(p99_values.std()),
            'min': float(p99_values.min()),
            'max': float(p99_values.max())
        }
    }
    
    with open(SESSION_DIR / 'baseline.json', 'w') as f:
        json.dump(baseline_data, f, indent=2)
    
    return baseline_B

def run_stress_episode(episode_num, baseline_B):
    """Run a single pilot stress episode"""
    print(f"\n{'='*60}")
    print(f"PILOT: Stress Episode {episode_num}/3")
    print(f"{'='*60}")
    
    session_name = f'pilot_stress_{episode_num}'
    duration_minutes = 5
    
    # Start logger in background
    log_cmd = f"python3 psi_latency_logger.py {session_name} {duration_minutes}"
    log_process = subprocess.Popen(log_cmd, shell=True)
    
    # Wait a bit for logger to start
    time.sleep(10)
    
    # Ramp injector to near pod limit (180 MB, pod limit is 256 MB)
    print("Ramping injector to 180 MB...")
    try:
        response = requests.post(
            f"{INJECTOR_URL}/inject",
            json={
                'target_mb': 180,
                'mode': 'sustained'
            },
            timeout=5
        )
        print(f"✓ Injector response: {response.json()}")
    except Exception as e:
        print(f"✗ Injector failed: {e}")
        log_process.terminate()
        return None
    
    # Hold for 3 minutes
    print("Holding for 3 minutes...")
    time.sleep(180)
    
    # Release injector
    print("Releasing injector...")
    try:
        requests.post(f"{INJECTOR_URL}/release", json={}, timeout=5)
    except:
        pass
    
    # Wait for logger to finish
    log_process.wait()
    
    # Analyze results
    csv_path = SESSION_DIR / session_name / 'metrics.csv'
    if not csv_path.exists():
        print(f"✗ Metrics file not found: {csv_path}")
        return None
    
    df = pd.read_csv(csv_path)
    
    # Check criteria
    p99_values = df['p99_latency_ms'].dropna()
    psi_values = df['node_psi_some_avg10'].dropna()
    
    max_p99 = p99_values.max()
    max_psi = psi_values.max()
    
    threshold_2B = 2.0 * baseline_B
    
    print(f"\nResults for Episode {episode_num}:")
    print(f"  Max p99: {max_p99:.2f} ms")
    print(f"  Threshold (2.0 * B): {threshold_2B:.2f} ms")
    print(f"  Max PSI: {max_psi:.2f}%")
    
    passed = max_p99 > threshold_2B
    
    if passed:
        print(f"  ✓ PASS: max_p99 ({max_p99:.2f}) > 2.0 * B ({threshold_2B:.2f})")
    else:
        print(f"  ✗ FAIL: max_p99 ({max_p99:.2f}) <= 2.0 * B ({threshold_2B:.2f})")
    
    return {
        'episode': episode_num,
        'session': session_name,
        'max_p99_ms': float(max_p99),
        'baseline_2B_ms': float(threshold_2B),
        'max_psi': float(max_psi),
        'passed': passed
    }

def main():
    """Run pilot gate"""
    print("="*80)
    print("STAGE 4: PILOT GATE")
    print("="*80)
    
    # Step 1: Run calm baseline
    print("\nStep 1: Running calm baseline session...")
    baseline_B = run_calm_baseline()
    
    if baseline_B is None:
        print("\n✗ PILOT GATE FAILED: Could not establish baseline")
        sys.exit(1)
    
    # Step 2: Run 3 stress episodes
    print(f"\nStep 2: Running 3 stress episodes (baseline B = {baseline_B:.2f} ms)...")
    
    results = []
    for i in range(1, 4):
        result = run_stress_episode(i, baseline_B)
        if result:
            results.append(result)
        time.sleep(30)  # Cool down between episodes
    
    # Step 3: Evaluate gate
    print(f"\n{'='*80}")
    print("PILOT GATE EVALUATION")
    print(f"{'='*80}")
    
    num_passed = sum(1 for r in results if r['passed'])
    
    print(f"\nResults: {num_passed}/3 episodes passed")
    
    for r in results:
        status = "✓ PASS" if r['passed'] else "✗ FAIL"
        print(f"  Episode {r['episode']}: {status} (max_p99={r['max_p99_ms']:.2f} ms, max_psi={r['max_psi']:.2f}%)")
    
    # Gate P1: At least 3/3 must pass
    gate_passed = num_passed >= 3
    
    pilot_results = {
        'baseline_B_ms': float(baseline_B),
        'episodes': results,
        'num_passed': num_passed,
        'gate_P1_passed': gate_passed,
        'gate_P1_rule': 'At least 3/3 episodes must exceed 2.0 * B AND PSI must rise above calm 95th percentile'
    }
    
    # Save results
    output_file = Path('pilot_results.json')
    with open(output_file, 'w') as f:
        json.dump(pilot_results, f, indent=2)
    
    print(f"\n✓ Pilot results saved to: {output_file}")
    
    if gate_passed:
        print(f"\n{'='*80}")
        print("✓ PILOT GATE PASSED")
        print(f"{'='*80}")
        print(f"Workload successfully couples memory pressure to latency.")
        print(f"Proceeding to full experiment sessions...")
        return 0
    else:
        print(f"\n{'='*80}")
        print("✗ PILOT GATE FAILED")
        print(f"{'='*80}")
        print(f"Workload does not reliably couple memory pressure to latency.")
        print(f"Only {num_passed}/3 episodes passed.")
        print(f"\nNext steps:")
        print(f"  1. Adjust workload (increase working set or allocation per request)")
        print(f"  2. Adjust injector (increase target memory)")
        print(f"  3. Re-run pilot")
        return 1

if __name__ == '__main__':
    sys.exit(main())
