#!/usr/bin/env python3
"""
Stage 2: PSI and Latency Logging
- Logs every 5 seconds with shared monotonic clock
- Node-level PSI memory some avg10 and full avg10
- Pod-cgroup memory.pressure some avg10 and full avg10
- Host MemAvailable
- Pod memory usage
- p99 latency for 5s bin
- Error count for 5s bin
- Request rate
- Heartbeat check every 30s
"""
import os
import sys
import time
import json
import csv
import subprocess
import signal
from datetime import datetime
from pathlib import Path
from collections import deque
import requests
import psutil

# Configuration
POD_NAME = os.getenv('POD_NAME', 'psi-workload')
POD_NAMESPACE = os.getenv('POD_NAMESPACE', 'psi-experiment')

# Get kind node IP
try:
    node_ip = subprocess.check_output(
        "docker ps | grep presync-control-plane | awk '{print $1}' | xargs docker inspect --format='{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'",
        shell=True, text=True
    ).strip()
    SERVICE_URL = f'http://{node_ip}:30080/work'
    INJECTOR_URL = f'http://{node_ip}:30081'
except:
    SERVICE_URL = 'http://localhost:30080/work'
    INJECTOR_URL = 'http://localhost:30081'

LOG_INTERVAL = 5  # seconds
HEARTBEAT_INTERVAL = 30  # seconds
OUTPUT_DIR = Path('session_logs')

class PSILatencyLogger:
    """Logs PSI and latency metrics every 5 seconds"""
    
    def __init__(self, session_name):
        self.session_name = session_name
        self.output_dir = OUTPUT_DIR / session_name
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.csv_path = self.output_dir / 'metrics.csv'
        self.log_path = self.output_dir / 'logger.log'
        
        self.running = True
        self.latency_buffer = deque(maxlen=1000)
        self.error_count = 0
        self.request_count = 0
        
        self.last_heartbeat = {
            'load_generator': time.time(),
            'psi_reader': time.time(),
            'injector': time.time()
        }
        
        # Initialize CSV
        self.init_csv()
        
        self.start_time = time.monotonic()
        
        print(f"PSI Latency Logger initialized for session: {session_name}")
        print(f"Output directory: {self.output_dir}")
    
    def init_csv(self):
        """Initialize CSV file with headers"""
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
    
    def read_node_psi(self):
        """Read node-level PSI from /proc/pressure/memory"""
        try:
            with open('/proc/pressure/memory', 'r') as f:
                lines = f.readlines()
            
            some_avg10 = None
            full_avg10 = None
            
            for line in lines:
                if line.startswith('some'):
                    parts = line.split()
                    for part in parts:
                        if part.startswith('avg10='):
                            some_avg10 = float(part.split('=')[1])
                elif line.startswith('full'):
                    parts = line.split()
                    for part in parts:
                        if part.startswith('avg10='):
                            full_avg10 = float(part.split('=')[1])
            
            return some_avg10, full_avg10
        
        except Exception as e:
            print(f"Error reading node PSI: {e}")
            return None, None
    
    def read_pod_psi(self):
        """Read pod-cgroup PSI via kubectl"""
        try:
            # Get pod cgroup path
            cmd = f"kubectl get pod -n {POD_NAMESPACE} -l app=psi-workload -o jsonpath='{{.items[0].metadata.name}}'"
            pod_name = subprocess.check_output(cmd, shell=True, text=True).strip()
            
            if not pod_name:
                return None, None
            
            # Read PSI from pod container
            cmd = f"kubectl exec -n {POD_NAMESPACE} {pod_name} -c http-service -- cat /sys/fs/cgroup/memory.pressure 2>/dev/null || echo 'unavailable'"
            result = subprocess.check_output(cmd, shell=True, text=True).strip()
            
            if result == 'unavailable' or not result:
                # Fallback: try cgroup v1 location
                return None, None
            
            some_avg10 = None
            full_avg10 = None
            
            for line in result.split('\n'):
                if line.startswith('some'):
                    parts = line.split()
                    for part in parts:
                        if part.startswith('avg10='):
                            some_avg10 = float(part.split('=')[1])
                elif line.startswith('full'):
                    parts = line.split()
                    for part in parts:
                        if part.startswith('avg10='):
                            full_avg10 = float(part.split('=')[1])
            
            return some_avg10, full_avg10
        
        except Exception as e:
            print(f"Error reading pod PSI: {e}")
            return None, None
    
    def read_host_mem_available(self):
        """Read host MemAvailable"""
        try:
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    if 'MemAvailable' in line:
                        mem_kb = int(line.split()[1])
                        return mem_kb / 1024  # Convert to MB
        except Exception as e:
            print(f"Error reading MemAvailable: {e}")
        return None
    
    def read_pod_memory_usage(self):
        """Read pod memory usage via kubectl"""
        try:
            cmd = f"kubectl top pod -n {POD_NAMESPACE} -l app=psi-workload --no-headers 2>/dev/null | awk '{{print $3}}'"
            result = subprocess.check_output(cmd, shell=True, text=True).strip()
            
            if result and result.endswith('Mi'):
                return float(result[:-2])
            elif result and result.endswith('Gi'):
                return float(result[:-2]) * 1024
        except Exception as e:
            pass
        
        return None
    
    def make_request(self):
        """Make a single request and record latency"""
        try:
            start_time = time.time()
            response = requests.get(SERVICE_URL, timeout=5)
            latency = (time.time() - start_time) * 1000  # ms
            
            if response.status_code == 200:
                self.latency_buffer.append(latency)
                self.request_count += 1
                return True
            else:
                self.error_count += 1
                return False
        
        except Exception as e:
            self.error_count += 1
            return False
    
    def calculate_p99_latency(self):
        """Calculate p99 latency from buffer"""
        if not self.latency_buffer:
            return None
        
        sorted_latencies = sorted(self.latency_buffer)
        p99_index = int(len(sorted_latencies) * 0.99)
        return sorted_latencies[p99_index]
    
    def check_heartbeat(self):
        """Check if all components are alive"""
        now = time.time()
        
        # Check load generator (this process)
        self.last_heartbeat['load_generator'] = now
        
        # Check PSI reader
        node_psi_some, node_psi_full = self.read_node_psi()
        if node_psi_some is not None:
            self.last_heartbeat['psi_reader'] = now
        
        # Check injector
        try:
            injector_url = INJECTOR_URL if 'INJECTOR_URL' in globals() else f'http://{node_ip}:30081/health'
            response = requests.get(f'{injector_url}/health', timeout=2)
            if response.status_code == 200:
                self.last_heartbeat['injector'] = now
        except:
            pass
        
        # Report if any component is stale
        for component, last_time in self.last_heartbeat.items():
            age = now - last_time
            if age > HEARTBEAT_INTERVAL * 2:
                print(f"⚠️  {component} heartbeat stale ({age:.0f}s)")
                return False
        
        return True
    
    def log_metrics(self):
        """Log all metrics for current 5s bin"""
        monotonic_time = time.monotonic() - self.start_time
        timestamp = datetime.now().isoformat()
        
        # Read PSI metrics
        node_psi_some, node_psi_full = self.read_node_psi()
        pod_psi_some, pod_psi_full = self.read_pod_psi()
        
        # Read memory metrics
        host_mem_available = self.read_host_mem_available()
        pod_memory_usage = self.read_pod_memory_usage()
        
        # Calculate latency
        p99_latency = self.calculate_p99_latency()
        
        # Calculate request rate
        request_rate = self.request_count / LOG_INTERVAL if LOG_INTERVAL > 0 else 0
        
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
                self.error_count,
                f"{request_rate:.2f}",
                self.request_count
            ])
        
        # Print to console
        psi_str = f"{node_psi_some:.2f}" if node_psi_some is not None else "N/A"
        p99_str = f"{p99_latency:.2f}" if p99_latency is not None else "N/A"
        print(f"[{timestamp}] PSI={psi_str}% p99={p99_str}ms errors={self.error_count} rate={request_rate:.1f}req/s")
        
        # Reset counters
        self.error_count = 0
        self.request_count = 0
        self.latency_buffer.clear()
    
    def run_session(self, duration_minutes):
        """Run a logging session"""
        print(f"="*60)
        print(f"Starting session: {self.session_name}")
        print(f"Duration: {duration_minutes} minutes")
        print(f"="*60)
        
        end_time = time.time() + (duration_minutes * 60)
        last_log_time = time.time()
        last_heartbeat_time = time.time()
        
        # Generate constant background load (10 req/sec)
        load_interval = 0.1
        last_request_time = time.time()
        
        while self.running and time.time() < end_time:
            current_time = time.time()
            
            # Make request at regular intervals
            if current_time - last_request_time >= load_interval:
                self.make_request()
                last_request_time = current_time
            
            # Log metrics every LOG_INTERVAL seconds
            if current_time - last_log_time >= LOG_INTERVAL:
                self.log_metrics()
                last_log_time = current_time
            
            # Heartbeat check
            if current_time - last_heartbeat_time >= HEARTBEAT_INTERVAL:
                self.check_heartbeat()
                last_heartbeat_time = current_time
            
            # Small sleep to prevent busy-wait
            time.sleep(0.01)
        
        print(f"Session complete: {self.session_name}")
    
    def stop(self):
        """Stop logging"""
        self.running = False

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    print(f"\nReceived signal {signum}, stopping...")
    sys.exit(0)

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python3 psi_latency_logger.py <session_name> <duration_minutes>")
        sys.exit(1)
    
    session_name = sys.argv[1]
    duration_minutes = int(sys.argv[2])
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger = PSILatencyLogger(session_name)
    logger.run_session(duration_minutes)
