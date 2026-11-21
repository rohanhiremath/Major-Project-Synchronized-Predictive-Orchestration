#!/usr/bin/env python3
"""
Stage 1: Memory Pressure Injector
- Runs as sidecar in same pod (shares cgroup)
- Controllable via HTTP endpoint or file
- Respects safety cap from Stage 0
"""
import os
import sys
import time
import random
import signal
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, request
import psutil

app = Flask(__name__)

# Configuration
SAFETY_CAP_MB = int(os.getenv('SAFETY_CAP_MB', '1107'))  # From Stage 0
DEFAULT_TARGET_MB = int(os.getenv('DEFAULT_TARGET_MB', '0'))
CONTROL_FILE = Path('/tmp/injector_control.txt')

# State
injector_state = {
    'active': False,
    'target_mb': 0,
    'current_mb': 0,
    'allocated_chunks': [],
    'mode': 'idle'  # idle, ramp, burst, sustained
}

def read_control_file():
    """Read control file if it exists"""
    if CONTROL_FILE.exists():
        try:
            with open(CONTROL_FILE, 'r') as f:
                lines = f.readlines()
                if lines:
                    parts = lines[0].strip().split()
                    if len(parts) >= 2:
                        target_mb = int(parts[0])
                        mode = parts[1] if len(parts) > 1 else 'sustained'
                        return target_mb, mode
        except Exception as e:
            print(f"Error reading control file: {e}")
    return None, None

def check_safety_cap(target_mb):
    """Ensure we don't exceed safety cap"""
    if target_mb > SAFETY_CAP_MB:
        print(f"⚠️  Safety cap exceeded: {target_mb} MB > {SAFETY_CAP_MB} MB")
        print(f"   Clamping to safety cap")
        return SAFETY_CAP_MB
    return target_mb

def allocate_memory(target_mb):
    """Allocate memory to reach target"""
    chunk_size_mb = 10  # 10 MB chunks
    chunk_size_bytes = chunk_size_mb * 1024 * 1024
    
    current_mb = injector_state['current_mb']
    
    if target_mb > current_mb:
        # Need to allocate more
        needed_mb = target_mb - current_mb
        num_chunks = int(needed_mb / chunk_size_mb)
        
        print(f"Allocating {needed_mb:.0f} MB ({num_chunks} chunks)...")
        
        for i in range(num_chunks):
            chunk = bytearray(chunk_size_bytes)
            # Touch memory to ensure it's resident
            for j in range(0, chunk_size_bytes, 4096):
                chunk[j] = random.randint(0, 255)
            
            injector_state['allocated_chunks'].append(chunk)
            injector_state['current_mb'] += chunk_size_mb
            
            # Yield control periodically
            if i % 10 == 0:
                time.sleep(0.01)
        
        print(f"✓ Allocated to {injector_state['current_mb']:.0f} MB")
    
    elif target_mb < current_mb:
        # Need to release memory
        release_mb = current_mb - target_mb
        num_chunks_release = int(release_mb / chunk_size_mb)
        
        print(f"Releasing {release_mb:.0f} MB ({num_chunks_release} chunks)...")
        
        for _ in range(num_chunks_release):
            if injector_state['allocated_chunks']:
                injector_state['allocated_chunks'].pop()
                injector_state['current_mb'] -= chunk_size_mb
        
        print(f"✓ Released to {injector_state['current_mb']:.0f} MB")

def ramp_profile(target_mb, duration_sec):
    """Ramp from current to target over duration"""
    start_mb = injector_state['current_mb']
    delta_mb = target_mb - start_mb
    steps = max(int(duration_sec / 5), 1)  # 5-second steps
    step_mb = delta_mb / steps
    
    print(f"Ramping from {start_mb:.0f} MB to {target_mb:.0f} MB over {duration_sec}s ({steps} steps)")
    
    for step in range(steps):
        target_this_step = int(start_mb + (step + 1) * step_mb)
        allocate_memory(target_this_step)
        time.sleep(duration_sec / steps)
    
    # Final adjustment
    allocate_memory(target_mb)

def burst_profile(target_mb, on_duration_sec, off_duration_sec, num_cycles):
    """Burst on and off"""
    print(f"Burst profile: {num_cycles} cycles of {on_duration_sec}s on / {off_duration_sec}s off")
    
    for cycle in range(num_cycles):
        print(f"Cycle {cycle + 1}/{num_cycles}: ON")
        allocate_memory(target_mb)
        time.sleep(on_duration_sec)
        
        print(f"Cycle {cycle + 1}/{num_cycles}: OFF")
        allocate_memory(0)
        time.sleep(off_duration_sec)

@app.route('/health')
def health():
    """Health check"""
    return jsonify({'status': 'healthy'})

@app.route('/status')
def status():
    """Get injector status"""
    process = psutil.Process()
    mem_info = process.memory_info()
    
    return jsonify({
        'active': injector_state['active'],
        'mode': injector_state['mode'],
        'target_mb': injector_state['target_mb'],
        'current_mb': injector_state['current_mb'],
        'rss_mb': mem_info.rss / 1024 / 1024,
        'safety_cap_mb': SAFETY_CAP_MB,
        'num_chunks': len(injector_state['allocated_chunks'])
    })

@app.route('/inject', methods=['POST'])
def inject():
    """Set injection parameters"""
    data = request.json
    
    target_mb = data.get('target_mb', 0)
    target_mb = check_safety_cap(target_mb)
    
    mode = data.get('mode', 'sustained')
    duration_sec = data.get('duration_sec', 60)
    
    injector_state['active'] = True
    injector_state['target_mb'] = target_mb
    injector_state['mode'] = mode
    
    if mode == 'ramp':
        ramp_profile(target_mb, duration_sec)
    elif mode == 'burst':
        on_sec = data.get('on_duration_sec', 180)
        off_sec = data.get('off_duration_sec', 60)
        cycles = data.get('num_cycles', 3)
        burst_profile(target_mb, on_sec, off_sec, cycles)
    else:  # sustained
        allocate_memory(target_mb)
    
    return jsonify({
        'status': 'ok',
        'target_mb': target_mb,
        'current_mb': injector_state['current_mb'],
        'mode': mode
    })

@app.route('/release', methods=['POST'])
def release():
    """Release all allocated memory"""
    print("Releasing all memory...")
    allocate_memory(0)
    injector_state['active'] = False
    injector_state['mode'] = 'idle'
    
    return jsonify({
        'status': 'ok',
        'current_mb': injector_state['current_mb']
    })

def control_loop():
    """Background loop to check control file"""
    while True:
        target_mb, mode = read_control_file()
        
        if target_mb is not None:
            target_mb = check_safety_cap(target_mb)
            
            if target_mb != injector_state['target_mb']:
                print(f"Control file update: target={target_mb} MB, mode={mode}")
                injector_state['target_mb'] = target_mb
                injector_state['mode'] = mode
                injector_state['active'] = target_mb > 0
                
                allocate_memory(target_mb)
        
        time.sleep(5)

if __name__ == '__main__':
    print("="*60)
    print("PSI THRESHOLD VALIDATION - MEMORY INJECTOR")
    print("="*60)
    print(f"Safety cap: {SAFETY_CAP_MB} MB")
    print(f"Control file: {CONTROL_FILE}")
    print("="*60)
    
    # Start control loop in background
    import threading
    control_thread = threading.Thread(target=control_loop, daemon=True)
    control_thread.start()
    
    # Start Flask server
    app.run(host='0.0.0.0', port=8081, threaded=True)
