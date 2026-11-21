#!/usr/bin/env python3
"""
Stage 4 Pilot Runner V2 - Uses in-cluster load generator
Runs: 1 calm baseline (20 min) + 3 stress episodes (5 min each)
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

SESSION_DIR = Path('session_logs')
SESSION_DIR.mkdir(exist_ok=True)

def get_node_ip():
    """Get kind node IP for injector access"""
    try:
        node_ip = subprocess.check_output(
            "docker ps | grep presync-control-plane | awk '{print $1}' | xargs docker inspect --format='{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'",
            shell=True, text=True
        ).strip()
        return node_ip
    except:
        return None

NODE_IP = get_node_ip()
INJECTOR_URL = f'http://{NODE_IP}:30081' if NODE_IP else None

def deploy_loadgen(duration_minutes):
    """Deploy load generator Job"""
    print(f"Deploying load generator for {duration_minutes} minutes...")
    
    # Update duration in Job
    cmd = f"""
cat loadgen-job.yaml | \
sed 's/value: "20"/value: "{duration_minutes}"/' | \
kubectl apply -f -
"""
    subprocess.run(cmd, shell=True, check=True)
    
    # Wait for pod to start
    time.sleep(10)
    
    # Check if running
    cmd = "kubectl get pod -n psi-experiment -l app=loadgen -o jsonpath='{.items[0].status.phase}'"
    phase = subprocess.check_output(cmd, shell=True, text=True).strip()
    print(f"Load generator status: {phase}")
    
    return phase in ['Running', 'Pending']

def wait_for_loadgen_complete(timeout=1800):
    """Wait for loadgen Job to complete"""
    print("Waiting for load generator to complete...")
    
    start = time.time()
    while time.time() - start < timeout:
        cmd = "kubectl get job loadgen -n psi-experiment -o jsonpath='{.status.completionTime}'"
        try:
            completion_time = subprocess.check_output(cmd, shell=True, text=True).strip()
            if completion_time:
                print("✓ Load generator completed")
                # Wait a bit for pod to be available
                time.sleep(5)
                return True
        except:
            pass
        
        time.sleep(5)
    
    print("✗ Load generator timeout")
    return False

def cleanup_loadgen():
    """Delete load generator Job - but pod will persist due to ttlSecondsAfterFinished"""
    # Don't delete immediately - let ttl handle it
    # Just mark for cleanup later
    pass

def copy_loadgen_results(session_name):
    """Read loadgen CSV results from pod (while running or immediately after)"""
    output_dir = SESSION_DIR / session_name
    output_dir.mkdir(parents=True, exist_ok=True)
    
    csv_path = output_dir / 'requests.csv'
    
    # Method 1: Try kubectl cp first (works with both Running and Succeeded)
    print("Attempting kubectl cp...")
    for attempt in range(10):
        try:
            cmd = "kubectl get pods -n psi-experiment -l app=loadgen -o jsonpath='{.items[0].metadata.name}'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
            pod_name = result.stdout.strip()
            
            if not pod_name:
                print(f"  Attempt {attempt+1}: No pod found")
                time.sleep(1)
                continue
            
            # Try kubectl cp with explicit source path
            cmd = f"kubectl cp -n psi-experiment {pod_name}:/results/requests.csv {csv_path} --no-preserve=true 2>&1"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0 and csv_path.exists():
                size = csv_path.stat().st_size
                if size > 100:
                    lines = sum(1 for _ in open(csv_path))
                    print(f"✓ Retrieved loadgen results via kubectl cp ({size} bytes, {lines} lines)")
                    return True
            
            print(f"  Attempt {attempt+1}: kubectl cp failed: {result.stderr[:50] if result.stderr else 'no output'}")
            time.sleep(1)
        
        except Exception as e:
            print(f"  Attempt {attempt+1}: {str(e)[:50]}")
            time.sleep(1)
    
    print(f"✗ Failed to retrieve loadgen results after 10 attempts")
    
    # Debug info
    try:
        cmd = "kubectl get pods -n psi-experiment -l app=loadgen"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        print(f"Debug - pod status:\n{result.stdout}")
    except:
        pass
    
    return False

def run_psi_logger(session_name, duration_minutes):
    """Run PSI logger in background"""
    cmd = f"python3 psi_logger_v2.py {session_name} {duration_minutes}"
    process = subprocess.Popen(cmd, shell=True)
    return process

def compute_metrics_from_requests(session_name):
    """Compute p99 per 5s bin from requests.csv"""
    csv_path = SESSION_DIR / session_name / 'requests.csv'
    
    if not csv_path.exists():
        return None
    
    df = pd.read_csv(csv_path)
    
    if df.empty:
        return None
    
    # Bin by 5-second intervals
    df['time_bin'] = (df['monotonic_time'] // 5).astype(int)
    
    # Compute p99 per bin
    bins = []
    for bin_id, group in df.groupby('time_bin'):
        success = group[group['status_code'] == 200]
        errors = group[group['status_code'] != 200]
        
        if len(success) > 0:
            p99 = np.percentile(success['latency_ms'], 99)
        else:
            p99 = None
        
        bins.append({
            'bin': bin_id,
            'p99_ms': p99,
            'error_count': len(errors),
            'request_count': len(group)
        })
    
    return pd.DataFrame(bins)

def run_calm_baseline():
    """Run calm baseline session"""
    print("="*60)
    print("PILOT: Calm Baseline Session (20 min)")
    print("="*60)
    
    session_name = 'pilot_calm_baseline'
    duration_minutes = 20
    
    # Ensure injector is off
    if INJECTOR_URL:
        try:
            requests.post(f"{INJECTOR_URL}/release", json={}, timeout=5)
            print("✓ Injector released")
        except Exception as e:
            print(f"⚠️  Could not reach injector: {e}")
    
    # Deploy loadgen
    if not deploy_loadgen(duration_minutes):
        print("✗ Failed to deploy load generator")
        return None
    
    # Run PSI logger
    logger_process = run_psi_logger(session_name, duration_minutes)
    
    # Wait for Job to start running (give it 10 seconds)
    time.sleep(10)
    
    # Continuously try to copy results while running (don't wait for completion)
    print("Attempting to retrieve results from running pod...")
    csv_retrieved = False
    start_copy = time.time()
    
    while time.time() - start_copy < 60:  # Try for up to 60 seconds
        # Try to copy before completion
        if copy_loadgen_results(session_name):
            csv_retrieved = True
            print("✓ Results retrieved while pod was running")
            break
        time.sleep(5)
    
    # Wait for loadgen to complete
    if not wait_for_loadgen_complete(timeout=duration_minutes * 60 + 120):
        logger_process.terminate()
        return None
    
    # If we didn't get results while running, try again after completion
    if not csv_retrieved:
        print("⚠️  Trying to retrieve results after completion...")
        time.sleep(5)  # Give pod time to write final data
        # This will fail, but let's try
        copy_loadgen_results(session_name)
    
    # Stop logger
    time.sleep(10)
    logger_process.terminate()
    
    # Compute baseline B
    csv_path = Path(session_name) / 'requests.csv' if Path(session_name / 'requests.csv').exists() else None
    
    if not csv_path or not csv_path.exists():
        print("✗ No metrics file found - results not retrieved")
        return None
    
    bins_df = compute_metrics_from_requests(session_name)
    
    if bins_df is None or bins_df.empty:
        print("✗ No metrics computed")
        return None
    
    p99_values = bins_df['p99_ms'].dropna()
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
    """Run a stress episode"""
    print(f"\n{'='*60}")
    print(f"PILOT: Stress Episode {episode_num}/3 (5 min)")
    print(f"{'='*60}")
    
    session_name = f'pilot_stress_{episode_num}'
    duration_minutes = 5
    
    # Deploy loadgen
    if not deploy_loadgen(duration_minutes):
        print("✗ Failed to deploy load generator")
        return None
    
    # Start PSI logger
    logger_process = run_psi_logger(session_name, duration_minutes)
    
    # Wait for loadgen to start
    time.sleep(15)
    
    # Inject stress after 1 minute (ramp to 180 MB)
    print("Waiting 60s before injecting stress...")
    time.sleep(60)
    
    print("Injecting memory stress (180 MB)...")
    if INJECTOR_URL:
        try:
            response = requests.post(
                f"{INJECTOR_URL}/inject",
                json={'target_mb': 180, 'mode': 'sustained'},
                timeout=5
            )
            print(f"✓ Injector: {response.json()}")
        except Exception as e:
            print(f"✗ Injector failed: {e}")
    
    # Wait for loadgen to complete
    if not wait_for_loadgen_complete(timeout=duration_minutes * 60 + 120):
        logger_process.terminate()
        return None
    
    # Release injector
    if INJECTOR_URL:
        try:
            requests.post(f"{INJECTOR_URL}/release", json={}, timeout=5)
            print("✓ Injector released")
        except:
            pass
    
    # Stop logger
    time.sleep(10)
    logger_process.terminate()
    
    # Copy results
    copy_loadgen_results(session_name)
    
    # Cleanup
    cleanup_loadgen()
    
    # Analyze
    bins_df = compute_metrics_from_requests(session_name)
    
    if bins_df is None or bins_df.empty:
        print("✗ No metrics computed")
        return None
    
    p99_values = bins_df['p99_ms'].dropna()
    max_p99 = p99_values.max()
    threshold_2B = 2.0 * baseline_B
    
    print(f"\nResults for Episode {episode_num}:")
    print(f"  Max p99: {max_p99:.2f} ms")
    print(f"  Threshold (2.0 * B): {threshold_2B:.2f} ms")
    
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
        'passed': passed
    }

def main():
    """Run pilot gate"""
    print("="*80)
    print("STAGE 4: PILOT GATE (In-Cluster Load Generator)")
    print("="*80)
    
    if not NODE_IP:
        print("✗ Could not get kind node IP")
        sys.exit(1)
    
    print(f"Kind node IP: {NODE_IP}")
    print(f"Injector URL: {INJECTOR_URL}")
    
    # Step 1: Calm baseline
    print("\nStep 1: Running calm baseline (20 min)...")
    baseline_B = run_calm_baseline()
    
    if baseline_B is None:
        print("\n✗ PILOT GATE FAILED: Could not establish baseline")
        sys.exit(1)
    
    # Step 2: Stress episodes
    print(f"\nStep 2: Running 3 stress episodes (5 min each)...")
    
    results = []
    for i in range(1, 4):
        result = run_stress_episode(i, baseline_B)
        if result:
            results.append(result)
        time.sleep(30)  # Cool down
    
    # Step 3: Evaluate
    print(f"\n{'='*80}")
    print("PILOT GATE EVALUATION")
    print(f"{'='*80}")
    
    num_passed = sum(1 for r in results if r['passed'])
    
    print(f"\nResults: {num_passed}/3 episodes passed")
    
    for r in results:
        status = "✓ PASS" if r['passed'] else "✗ FAIL"
        print(f"  Episode {r['episode']}: {status} (max_p99={r['max_p99_ms']:.2f} ms)")
    
    gate_passed = num_passed >= 3
    
    pilot_results = {
        'baseline_B_ms': float(baseline_B),
        'episodes': results,
        'num_passed': num_passed,
        'gate_P1_passed': gate_passed,
        'access_method': 'in-cluster load generator',
        'node_ip': NODE_IP
    }
    
    # Save
    with open('pilot_results.json', 'w') as f:
        json.dump(pilot_results, f, indent=2)
    
    print(f"\n✓ Pilot results saved to: pilot_results.json")
    
    if gate_passed:
        print(f"\n{'='*80}")
        print("✓ PILOT GATE PASSED")
        print(f"{'='*80}")
        print("Proceeding to Stage 5 (full experiment sessions)...")
        return 0
    else:
        print(f"\n{'='*80}")
        print("✗ PILOT GATE FAILED")
        print(f"{'='*80}")
        print(f"Only {num_passed}/3 episodes passed.")
        print("Workload adjustment needed.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
