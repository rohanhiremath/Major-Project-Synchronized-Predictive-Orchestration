#!/usr/bin/env python3
"""
Parallel Pilot: Deploy and test multiple workload variants simultaneously
Each variant gets its own pod in the cluster
Run quick stress tests (5 min each) to find best configuration
"""
import os
import sys
import json
import time
import subprocess
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import numpy as np

CONFIG_FILE = Path('parallel_pilot_config.json')
RESULTS_FILE = Path('parallel_pilot_results.json')

def create_variant_deployment(variant):
    """Create Kubernetes deployment for a variant"""
    name = variant['name']
    namespace = 'psi-experiment'
    
    yaml_content = f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: psi-workload-{name}
  namespace: {namespace}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: psi-workload-{name}
  template:
    metadata:
      labels:
        app: psi-workload-{name}
        variant: {name}
    spec:
      containers:
      - name: http-service
        image: python:3.11-slim
        command:
          - /bin/bash
          - -c
          - |
            pip install -q flask psutil && \
            cat > /tmp/service.py << 'PYEOF'
import os, time, random
from datetime import datetime
from flask import Flask, jsonify
import psutil

app = Flask(__name__)

MEMORY_LIMIT_MB = {variant['memory_limit_mb']}
TARGET_WORKING_SET_PCT = {variant['working_set_pct']}
ALLOCATION_PER_REQUEST_KB = {variant['allocation_per_request_kb']}

cache = {{}}
cache_size_target = int(MEMORY_LIMIT_MB * TARGET_WORKING_SET_PCT * 1024 * 1024)

def initialize_cache():
    chunk_size = 1024 * 1024
    num_chunks = cache_size_target // chunk_size
    for i in range(num_chunks):
        cache['chunk_' + str(i)] = bytearray(chunk_size)
        for j in range(0, chunk_size, 4096):
            cache['chunk_' + str(i)][j] = random.randint(0, 255)

@app.route('/health')
def health():
    return jsonify({{'status': 'healthy', 'variant': '{name}'}})

@app.route('/work')
def work():
    start_time = time.time()
    temp_data = bytearray(ALLOCATION_PER_REQUEST_KB * 1024)
    for i in range(0, len(temp_data), 4096):
        temp_data[i] = random.randint(0, 255)
    cache_keys = list(cache.keys())
    for _ in range(random.randint(10, 50)):
        if cache_keys:
            _ = cache[random.choice(cache_keys)][0]
    time.sleep(random.uniform(0.001, 0.01))
    latency = (time.time() - start_time) * 1000
    return jsonify({{'status': 'ok', 'latency_ms': latency, 'variant': '{name}'}})

if __name__ == '__main__':
    initialize_cache()
    app.run(host='0.0.0.0', port=8080, threaded=True)
PYEOF
            python3 /tmp/service.py
        ports:
        - containerPort: 8080
        resources:
          requests:
            memory: "{int(variant['memory_limit_mb'] * 0.5)}Mi"
          limits:
            memory: "{variant['memory_limit_mb']}Mi"
      
      - name: memory-injector
        image: python:3.11-slim
        command:
          - /bin/bash
          - -c
          - |
            pip install -q flask psutil && \
            cat > /tmp/injector.py << 'PYEOF'
import time, random
from flask import Flask, jsonify, request
import psutil

app = Flask(__name__)
injector_state = {{'active': False, 'target_mb': 0, 'current_mb': 0, 'allocated_chunks': []}}

def allocate_memory(target_mb):
    chunk_size_mb = 10
    chunk_size_bytes = chunk_size_mb * 1024 * 1024
    current_mb = injector_state['current_mb']
    if target_mb > current_mb:
        needed_mb = target_mb - current_mb
        num_chunks = int(needed_mb / chunk_size_mb)
        for i in range(num_chunks):
            chunk = bytearray(chunk_size_bytes)
            for j in range(0, chunk_size_bytes, 4096):
                chunk[j] = random.randint(0, 255)
            injector_state['allocated_chunks'].append(chunk)
            injector_state['current_mb'] += chunk_size_mb
    elif target_mb < current_mb:
        release_mb = current_mb - target_mb
        num_chunks_release = int(release_mb / chunk_size_mb)
        for _ in range(num_chunks_release):
            if injector_state['allocated_chunks']:
                injector_state['allocated_chunks'].pop()
                injector_state['current_mb'] -= chunk_size_mb

@app.route('/health')
def health():
    return jsonify({{'status': 'healthy'}})

@app.route('/inject', methods=['POST'])
def inject():
    data = request.json
    target_mb = data.get('target_mb', 0)
    injector_state['target_mb'] = target_mb
    allocate_memory(target_mb)
    return jsonify({{'status': 'ok', 'current_mb': injector_state['current_mb']}})

@app.route('/release', methods=['POST'])
def release():
    allocate_memory(0)
    return jsonify({{'status': 'ok'}})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8081, threaded=True)
PYEOF
            python3 /tmp/injector.py
        ports:
        - containerPort: 8081
        resources:
          limits:
            memory: "1200Mi"
---
apiVersion: v1
kind: Service
metadata:
  name: psi-workload-{name}
  namespace: {namespace}
spec:
  type: NodePort
  selector:
    app: psi-workload-{name}
  ports:
  - name: http
    port: 8080
    targetPort: 8080
  - name: injector
    port: 8081
    targetPort: 8081
"""
    
    yaml_file = Path(f'deployment_{name}.yaml')
    with open(yaml_file, 'w') as f:
        f.write(yaml_content)
    
    return yaml_file

def deploy_variant(variant):
    """Deploy a single variant"""
    name = variant['name']
    print(f"[{name}] Deploying...")
    
    yaml_file = create_variant_deployment(variant)
    
    try:
        subprocess.run(
            f"kubectl apply -f {yaml_file}",
            shell=True,
            check=True,
            capture_output=True
        )
        print(f"[{name}] ✓ Deployed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[{name}] ✗ Deploy failed: {e}")
        return False

def wait_for_ready(variant, timeout=120):
    """Wait for variant pod to be ready"""
    name = variant['name']
    print(f"[{name}] Waiting for pod ready...")
    
    cmd = f"kubectl wait --for=condition=ready pod -l app=psi-workload-{name} -n psi-experiment --timeout={timeout}s"
    
    try:
        subprocess.run(cmd, shell=True, check=True, capture_output=True, timeout=timeout)
        
        # Get service nodeport
        cmd = f"kubectl get svc psi-workload-{name} -n psi-experiment -o jsonpath='{{.spec.ports[0].nodePort}}'"
        http_port = subprocess.check_output(cmd, shell=True, text=True).strip()
        
        cmd = f"kubectl get svc psi-workload-{name} -n psi-experiment -o jsonpath='{{.spec.ports[1].nodePort}}'"
        injector_port = subprocess.check_output(cmd, shell=True, text=True).strip()
        
        print(f"[{name}] ✓ Ready (http:{http_port}, injector:{injector_port})")
        return http_port, injector_port
    
    except Exception as e:
        print(f"[{name}] ✗ Not ready: {e}")
        return None, None

def run_quick_test(variant, http_port, injector_port):
    """Run a quick 5-minute stress test"""
    name = variant['name']
    print(f"[{name}] Starting quick test...")
    
    service_url = f"http://localhost:{http_port}/work"
    injector_url = f"http://localhost:{injector_port}"
    
    results = {
        'variant': name,
        'config': variant,
        'baseline_latencies': [],
        'stress_latencies': [],
        'psi_values': [],
        'success': False
    }
    
    try:
        # Phase 1: 60s baseline (no stress)
        print(f"[{name}] Phase 1: 60s baseline")
        requests.post(f"{injector_url}/release", json={}, timeout=2)
        time.sleep(2)
        
        for _ in range(60):
            try:
                start = time.time()
                resp = requests.get(service_url, timeout=2)
                if resp.status_code == 200:
                    latency = (time.time() - start) * 1000
                    results['baseline_latencies'].append(latency)
            except:
                pass
            time.sleep(1)
        
        baseline_p99 = np.percentile(results['baseline_latencies'], 99) if results['baseline_latencies'] else 0
        print(f"[{name}] Baseline p99: {baseline_p99:.2f} ms")
        
        # Phase 2: 180s stress
        print(f"[{name}] Phase 2: 180s stress (injector → {variant['injector_target_mb']} MB)")
        requests.post(
            f"{injector_url}/inject",
            json={'target_mb': variant['injector_target_mb']},
            timeout=5
        )
        time.sleep(5)
        
        for _ in range(180):
            try:
                start = time.time()
                resp = requests.get(service_url, timeout=2)
                if resp.status_code == 200:
                    latency = (time.time() - start) * 1000
                    results['stress_latencies'].append(latency)
            except:
                pass
            
            # Read PSI
            try:
                with open('/proc/pressure/memory', 'r') as f:
                    for line in f:
                        if line.startswith('some'):
                            for part in line.split():
                                if part.startswith('avg10='):
                                    psi = float(part.split('=')[1])
                                    results['psi_values'].append(psi)
                                    break
            except:
                pass
            
            time.sleep(1)
        
        # Phase 3: Release
        print(f"[{name}] Phase 3: Releasing injector")
        requests.post(f"{injector_url}/release", json={}, timeout=2)
        
        # Analyze
        if results['stress_latencies'] and baseline_p99 > 0:
            stress_p99 = np.percentile(results['stress_latencies'], 99)
            max_psi = max(results['psi_values']) if results['psi_values'] else 0
            
            ratio = stress_p99 / baseline_p99
            
            results['baseline_p99_ms'] = float(baseline_p99)
            results['stress_p99_ms'] = float(stress_p99)
            results['latency_ratio'] = float(ratio)
            results['max_psi'] = float(max_psi)
            results['success'] = ratio >= 2.0 and max_psi > 0.5
            
            print(f"[{name}] Results:")
            print(f"  Baseline p99: {baseline_p99:.2f} ms")
            print(f"  Stress p99: {stress_p99:.2f} ms")
            print(f"  Ratio: {ratio:.2f}x")
            print(f"  Max PSI: {max_psi:.2f}%")
            print(f"  {'✓ PASS' if results['success'] else '✗ FAIL'}")
        
        return results
    
    except Exception as e:
        print(f"[{name}] ✗ Test failed: {e}")
        results['error'] = str(e)
        return results

def cleanup_variant(variant):
    """Delete variant deployment"""
    name = variant['name']
    subprocess.run(
        f"kubectl delete deployment psi-workload-{name} -n psi-experiment --ignore-not-found=true",
        shell=True,
        capture_output=True
    )
    subprocess.run(
        f"kubectl delete service psi-workload-{name} -n psi-experiment --ignore-not-found=true",
        shell=True,
        capture_output=True
    )

def main():
    """Run parallel pilot"""
    print("="*80)
    print("PARALLEL PILOT: Testing Multiple Workload Variants")
    print("="*80)
    
    # Load configuration
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)
    
    variants = config['variants']
    target = config['target_criteria']
    
    print(f"\nTesting {len(variants)} variants:")
    for v in variants:
        print(f"  - {v['name']}: {v['description']}")
    
    print(f"\nTarget criteria:")
    print(f"  - Latency increase: ≥{target['min_latency_increase']}x")
    print(f"  - PSI range: {target['preferred_psi_range']}")
    
    # Deploy all variants
    print(f"\n{'='*80}")
    print("PHASE 1: Deploying all variants")
    print(f"{'='*80}")
    
    deployed = []
    for variant in variants:
        if deploy_variant(variant):
            deployed.append(variant)
    
    print(f"\n✓ Deployed {len(deployed)}/{len(variants)} variants")
    
    # Wait for all to be ready
    print(f"\n{'='*80}")
    print("PHASE 2: Waiting for pods to be ready")
    print(f"{'='*80}")
    
    variant_ports = {}
    for variant in deployed:
        http_port, injector_port = wait_for_ready(variant)
        if http_port and injector_port:
            variant_ports[variant['name']] = (http_port, injector_port)
    
    print(f"\n✓ {len(variant_ports)}/{len(deployed)} variants ready")
    
    # Run tests in parallel
    print(f"\n{'='*80}")
    print("PHASE 3: Running quick stress tests (5 min each, parallel)")
    print(f"{'='*80}")
    
    all_results = []
    
    with ThreadPoolExecutor(max_workers=len(variant_ports)) as executor:
        futures = {}
        
        for variant in deployed:
            if variant['name'] in variant_ports:
                http_port, injector_port = variant_ports[variant['name']]
                future = executor.submit(run_quick_test, variant, http_port, injector_port)
                futures[future] = variant['name']
        
        for future in as_completed(futures):
            name = futures[future]
            try:
                result = future.result()
                all_results.append(result)
            except Exception as e:
                print(f"[{name}] Exception: {e}")
    
    # Analyze results
    print(f"\n{'='*80}")
    print("RESULTS SUMMARY")
    print(f"{'='*80}")
    
    successful = [r for r in all_results if r.get('success', False)]
    
    print(f"\nPassed: {len(successful)}/{len(all_results)} variants")
    print(f"\nDetailed results:")
    
    sorted_results = sorted(all_results, key=lambda x: x.get('latency_ratio', 0), reverse=True)
    
    for r in sorted_results:
        name = r['variant']
        if 'latency_ratio' in r:
            print(f"\n  {name}:")
            print(f"    Latency ratio: {r['latency_ratio']:.2f}x")
            print(f"    Stress p99: {r['stress_p99_ms']:.2f} ms")
            print(f"    Max PSI: {r['max_psi']:.2f}%")
            print(f"    Status: {'✓ PASS' if r['success'] else '✗ FAIL'}")
    
    # Find best variant
    if successful:
        # Prefer variants with PSI in target range
        psi_min, psi_max = target['preferred_psi_range']
        in_range = [r for r in successful if psi_min <= r.get('max_psi', 0) <= psi_max]
        
        if in_range:
            best = max(in_range, key=lambda x: x['latency_ratio'])
            print(f"\n✓ BEST VARIANT (PSI in target range): {best['variant']}")
        else:
            best = max(successful, key=lambda x: x['latency_ratio'])
            print(f"\n✓ BEST VARIANT (no PSI in range): {best['variant']}")
        
        print(f"  Latency ratio: {best['latency_ratio']:.2f}x")
        print(f"  Max PSI: {best['max_psi']:.2f}%")
    else:
        print(f"\n✗ No variants passed")
        best = None
    
    # Save results
    output = {
        'target_criteria': target,
        'results': all_results,
        'successful_count': len(successful),
        'best_variant': best['variant'] if best else None
    }
    
    with open(RESULTS_FILE, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n✓ Results saved to: {RESULTS_FILE}")
    
    # Cleanup
    print(f"\n{'='*80}")
    print("PHASE 4: Cleanup")
    print(f"{'='*80}")
    
    for variant in deployed:
        cleanup_variant(variant)
    
    print(f"\n✓ All variants cleaned up")
    
    return 0 if best else 1

if __name__ == '__main__':
    sys.exit(main())
