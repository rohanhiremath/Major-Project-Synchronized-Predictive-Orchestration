#!/usr/bin/env python3
"""
Stage 1: HTTP Service with Memory Pressure
- Small HTTP service with in-memory cache
- Working set near 70% of memory limit
- Allocates/touches memory per request
- Reclaim pressure raises request latency
"""
import os
import time
import random
import asyncio
from datetime import datetime
from flask import Flask, jsonify, request
import psutil

app = Flask(__name__)

# Configuration
MEMORY_LIMIT_MB = int(os.getenv('MEMORY_LIMIT_MB', '256'))
TARGET_WORKING_SET_PCT = float(os.getenv('TARGET_WORKING_SET_PCT', '0.70'))
ALLOCATION_PER_REQUEST_KB = int(os.getenv('ALLOCATION_PER_REQUEST_KB', '512'))

# In-memory cache to maintain working set
cache = {}
cache_size_target = int(MEMORY_LIMIT_MB * TARGET_WORKING_SET_PCT * 1024 * 1024)

def initialize_cache():
    """Initialize cache to target working set size"""
    print(f"Initializing cache to {cache_size_target / 1024 / 1024:.1f} MB...")
    
    # Pre-allocate working set
    chunk_size = 1024 * 1024  # 1 MB chunks
    num_chunks = cache_size_target // chunk_size
    
    for i in range(num_chunks):
        # Create 1MB of data
        cache[f'chunk_{i}'] = bytearray(chunk_size)
        # Touch the memory to ensure it's resident
        for j in range(0, chunk_size, 4096):
            cache[f'chunk_{i}'][j] = random.randint(0, 255)
    
    process = psutil.Process()
    mem_info = process.memory_info()
    print(f"Cache initialized. RSS: {mem_info.rss / 1024 / 1024:.1f} MB")

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

@app.route('/work')
def work():
    """Work endpoint that allocates and touches memory"""
    start_time = time.time()
    
    # Allocate memory per request
    temp_data = bytearray(ALLOCATION_PER_REQUEST_KB * 1024)
    
    # Touch the memory to ensure page faults
    for i in range(0, len(temp_data), 4096):
        temp_data[i] = random.randint(0, 255)
    
    # Access cache to create memory pressure
    num_accesses = random.randint(10, 50)
    cache_keys = list(cache.keys())
    
    for _ in range(num_accesses):
        if cache_keys:
            key = random.choice(cache_keys)
            # Read from cache
            _ = cache[key][0]
    
    # Simulate some work
    time.sleep(random.uniform(0.001, 0.01))
    
    latency = (time.time() - start_time) * 1000  # ms
    
    return jsonify({
        'status': 'ok',
        'latency_ms': latency,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/stats')
def stats():
    """Return memory statistics"""
    process = psutil.Process()
    mem_info = process.memory_info()
    
    return jsonify({
        'rss_mb': mem_info.rss / 1024 / 1024,
        'vms_mb': mem_info.vms / 1024 / 1024,
        'cache_keys': len(cache),
        'memory_limit_mb': MEMORY_LIMIT_MB,
        'target_working_set_mb': cache_size_target / 1024 / 1024
    })

if __name__ == '__main__':
    print("="*60)
    print("PSI THRESHOLD VALIDATION - HTTP SERVICE")
    print("="*60)
    print(f"Memory limit: {MEMORY_LIMIT_MB} MB")
    print(f"Target working set: {TARGET_WORKING_SET_PCT * 100:.0f}% ({cache_size_target / 1024 / 1024:.1f} MB)")
    print(f"Allocation per request: {ALLOCATION_PER_REQUEST_KB} KB")
    print("="*60)
    
    # Initialize working set
    initialize_cache()
    
    # Start Flask server
    app.run(host='0.0.0.0', port=8080, threaded=True)
