#!/usr/bin/env python3
"""
PSI Logger V2 - Works with in-cluster load generator
- Reads per-request latencies from loadgen Job
- Computes p99 per 5-second bin
- Logs PSI metrics every 5 seconds
"""
import os
import sys
import time
import csv
import subprocess
import json
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd

POD_NAMESPACE = 'psi-experiment'
LOG_INTERVAL = 5  # seconds
OUTPUT_DIR = Path('session_logs')

class PSILoggerV2:
    """Logs PSI metrics alongside loadgen request data"""
    
    def __init__(self, session_name):
        self.session_name = session_name
        self.output_dir = OUTPUT_DIR / session_name
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.csv_path = self.output_dir / 'metrics.csv'
        self.start_time = time.monotonic()
        
        # Initialize CSV
        with open(self.csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'timestamp',
                'monotonic_time',
                'node_psi_some_avg10',
                'node_psi_full_avg10',
                'pod_psi_some_avg10',
                'pod_psi_full_avg10',
                'host_mem_available_mb',
                'pod_memory_usage_mb',
                'p99_latency_ms',
                'error_count',
                'request_rate',
                'request_count'
            ])
        
        print(f"PSI Logger V2 initialized for session: {session_name}")
    
    def read_node_psi(self):
        """Read node-level PSI from /proc/pressure/memory"""
        try:
            with open('/proc/pressure/memory', 'r') as f:
                lines = f.readlines()
            
            some_avg10 = None
            full_avg10 = None
            
            for line in lines:
                if line.startswith('some'):
                    for part in line.split():
                        if part.startswith('avg10='):
                            some_avg10 = float(part.split('=')[1])
                elif line.startswith('full'):
                    for part in line.split():
                        if part.startswith('avg10='):
                            full_avg10 = float(part.split('=')[1])
            
            return some_avg10, full_avg10
        except Exception as e:
            return None, None
    
    def read_pod_psi(self):
        """Read pod-cgroup PSI - try cgroup v2 path"""
        try:
            # Get pod name
            cmd = f"kubectl get pod -n {POD_NAMESPACE} -l app=psi-workload -o jsonpath='{{.items[0].metadata.name}}'"
            pod_name = subprocess.check_output(cmd, shell=True, text=True).strip()
            
            if not pod_name:
                return None, None
            
            # Try to read from pod
            cmd = f"kubectl exec -n {POD_NAMESPACE} {pod_name} -c http-service -- cat /sys/fs/cgroup/memory.pressure 2>/dev/null || echo ''"
            result = subprocess.check_output(cmd, shell=True, text=True).strip()
            
            if not result:
                return None, None
            
            some_avg10 = None
            full_avg10 = None
            
            for line in result.split('\n'):
                if line.startswith('some'):
                    for part in line.split():
                        if part.startswith('avg10='):
                            some_avg10 = float(part.split('=')[1])
                elif line.startswith('full'):
                    for part in line.split():
                        if part.startswith('avg10='):
                            full_avg10 = float(part.split('=')[1])
            
            return some_avg10, full_avg10
        except:
            return None, None
    
    def read_host_mem_available(self):
        """Read host MemAvailable"""
        try:
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    if 'MemAvailable' in line:
                        mem_kb = int(line.split()[1])
                        return mem_kb / 1024
        except:
            pass
        return None
    
    def read_pod_memory_usage(self):
        """Read pod memory usage via kubectl top"""
        try:
            cmd = f"kubectl top pod -n {POD_NAMESPACE} -l app=psi-workload --no-headers 2>/dev/null | awk '{{print $3}}'"
            result = subprocess.check_output(cmd, shell=True, text=True).strip()
            
            if result and result.endswith('Mi'):
                return float(result[:-2])
            elif result and result.endswith('Gi'):
                return float(result[:-2]) * 1024
        except:
            pass
        return None
    
    def get_loadgen_metrics(self, bin_start, bin_end):
        """Get p99 latency from loadgen for this time bin"""
        try:
            # Get pod name - works for Running and Succeeded pods
            cmd = f"kubectl get pod -n {POD_NAMESPACE} -l app=loadgen --field-selector=status.phase=Running,status.phase=Succeeded -o jsonpath='{{.items[0].metadata.name}}'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            loadgen_pod = result.stdout.strip()
            
            if not loadgen_pod:
                return None, 0, 0
            
            # Read CSV from loadgen pod
            cmd = f"kubectl exec -n {POD_NAMESPACE} {loadgen_pod} -- cat /results/requests.csv 2>/dev/null"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                return None, 0, 0
            
            csv_data = result.stdout
            
            # Parse CSV
            lines = csv_data.strip().split('\n')
            if len(lines) <= 1:
                return None, 0, 0
            
            # Find requests in this time bin
            latencies = []
            errors = 0
            
            for line in lines[1:]:  # Skip header
                if not line.strip():
                    continue
                parts = line.split(',')
                if len(parts) >= 4:
                    try:
                        mono_time = float(parts[1])
                        latency = float(parts[2])
                        status = int(parts[3])
                        
                        if bin_start <= mono_time < bin_end:
                            if status == 200:
                                latencies.append(latency)
                            else:
                                errors += 1
                    except (ValueError, IndexError):
                        continue
            
            if latencies:
                p99 = np.percentile(latencies, 99)
                request_count = len(latencies) + errors
                return p99, errors, request_count
            else:
                return None, errors, errors
        
        except Exception as e:
            return None, 0, 0
    
    def log_metrics(self, bin_number):
        """Log metrics for current 5s bin"""
        monotonic_time = time.monotonic() - self.start_time
        timestamp = datetime.now().isoformat()
        
        # Define time bin
        bin_start = bin_number * LOG_INTERVAL
        bin_end = (bin_number + 1) * LOG_INTERVAL
        
        # Read PSI
        node_psi_some, node_psi_full = self.read_node_psi()
        pod_psi_some, pod_psi_full = self.read_pod_psi()
        
        # Read memory
        host_mem_available = self.read_host_mem_available()
        pod_memory_usage = self.read_pod_memory_usage()
        
        # Get loadgen metrics for this bin
        p99_latency, error_count, request_count = self.get_loadgen_metrics(bin_start, bin_end)
        request_rate = request_count / LOG_INTERVAL if LOG_INTERVAL > 0 else 0
        
        # Write to CSV
        with open(self.csv_path, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                timestamp,
                f"{monotonic_time:.1f}",
                f"{node_psi_some:.2f}" if node_psi_some is not None else '',
                f"{node_psi_full:.2f}" if node_psi_full is not None else '',
                f"{pod_psi_some:.2f}" if pod_psi_some is not None else '',
                f"{pod_psi_full:.2f}" if pod_psi_full is not None else '',
                f"{host_mem_available:.1f}" if host_mem_available is not None else '',
                f"{pod_memory_usage:.1f}" if pod_memory_usage is not None else '',
                f"{p99_latency:.2f}" if p99_latency is not None else '',
                error_count,
                f"{request_rate:.2f}",
                request_count
            ])
        
        # Print
        psi_str = f"{node_psi_some:.2f}" if node_psi_some is not None else "N/A"
        p99_str = f"{p99_latency:.2f}" if p99_latency is not None else "N/A"
        print(f"[{timestamp}] PSI={psi_str}% p99={p99_str}ms errors={error_count} rate={request_rate:.1f}req/s")
    
    def run_session(self, duration_minutes):
        """Run a logging session"""
        print(f"="*60)
        print(f"Starting PSI logging for session: {self.session_name}")
        print(f"Duration: {duration_minutes} minutes")
        print(f"="*60)
        
        num_bins = (duration_minutes * 60) // LOG_INTERVAL
        
        for bin_number in range(num_bins):
            time.sleep(LOG_INTERVAL)
            self.log_metrics(bin_number)
        
        print(f"Session complete: {self.session_name}")

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python3 psi_logger_v2.py <session_name> <duration_minutes>")
        sys.exit(1)
    
    session_name = sys.argv[1]
    duration_minutes = int(sys.argv[2])
    
    logger = PSILoggerV2(session_name)
    logger.run_session(duration_minutes)
