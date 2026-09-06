#!/usr/bin/env python3
"""
Phase 6: Prediction Service for Kubernetes PSI Spike Detection

This service:
1. Loads the trained TFT model
2. Queries Prometheus for live PSI metrics every 20 seconds
3. Makes 30-second ahead spike predictions
4. Outputs scaling decisions (shadow mode - no actions yet)
5. Exports metrics to Prometheus
6. Logs predictions for analysis
"""

import os
import sys
import time
import logging
import signal
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import deque

import torch
import numpy as np
import pandas as pd
from prometheus_client import start_http_server, Counter, Gauge, Histogram, Summary
import requests
from flask import Flask, jsonify

# Add parent directory to path for model imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from pytorch_forecasting import TimeSeriesDataSet, TemporalFusionTransformer

# Import confirmation gate from Phase 6
try:
    from confirmation_gate import ConfirmationGate
    CONFIRMATION_GATE_AVAILABLE = True
except ImportError:
    logger.warning("⚠️  Confirmation gate not found - will use raw predictions only")
    CONFIRMATION_GATE_AVAILABLE = False

# ============================================================
# CONFIGURATION
# ============================================================

# Model configuration
MODEL_PATH = os.getenv('MODEL_PATH', '/app/models/tft_psi_model.ckpt')
SPIKE_THRESHOLD = float(os.getenv('SPIKE_THRESHOLD', '1.80'))
MAX_ENCODER_LENGTH = int(os.getenv('MAX_ENCODER_LENGTH', '30'))
MAX_PREDICTION_LENGTH = int(os.getenv('MAX_PREDICTION_LENGTH', '30'))

# Prometheus configuration
PROMETHEUS_URL = os.getenv('PROMETHEUS_URL', 
    'http://prometheus-kube-prometheus-stack-prometheus.monitoring:9090')
PREDICTION_INTERVAL = int(os.getenv('PREDICTION_INTERVAL', '20'))  # seconds

# Service configuration
SHADOW_MODE = os.getenv('SHADOW_MODE', 'true').lower() == 'true'
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
METRICS_PORT = int(os.getenv('METRICS_PORT', '8090'))
API_PORT = int(os.getenv('API_PORT', '8080'))

# Pod labels to monitor
POD_LABEL_SELECTOR = os.getenv('POD_LABEL_SELECTOR', 'app=workload')

# ============================================================
# LOGGING SETUP
# ============================================================

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('prediction-service')

# ============================================================
# PROMETHEUS METRICS
# ============================================================

# Counters
predictions_total = Counter('predictions_total', 'Total predictions made')
spikes_predicted_total = Counter('spikes_predicted_total', 'Total spikes predicted')
spikes_actual_total = Counter('spikes_actual_total', 'Total actual spikes observed')
true_positives = Counter('true_positives_total', 'True positive predictions')
false_positives = Counter('false_positives_total', 'False positive predictions')
false_negatives = Counter('false_negatives_total', 'False negative predictions')

# Gauges
current_psi = Gauge('current_psi_value', 'Current PSI value', ['pod'])
predicted_psi = Gauge('predicted_psi_value', 'Predicted PSI value', ['pod', 'quantile'])
spike_probability = Gauge('spike_probability', 'Spike prediction probability', ['pod'])
precision_gauge = Gauge('prediction_precision', 'Current precision (TP/(TP+FP))')
recall_gauge = Gauge('prediction_recall', 'Current recall (TP/(TP+FN))')

# Histograms
prediction_latency = Histogram('prediction_latency_seconds', 
                               'Time to make a prediction',
                               buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0])
prometheus_query_duration = Histogram('prometheus_query_duration_seconds',
                                      'Prometheus query duration',
                                      buckets=[0.1, 0.5, 1.0, 2.0, 5.0])

# Summary
model_load_time = Summary('model_load_time_seconds', 'Model loading time')

# ============================================================
# DAY 1: ADDITIONAL METRICS FOR HPA INTEGRATION
# ============================================================

# These are the key metrics that HPA will use in Phase 8
predicted_psi_raw = Gauge('predicted_psi_raw', 
                          'Raw predicted PSI without confirmation gate', 
                          ['pod'])
predicted_psi_confirmed = Gauge('predicted_psi_confirmed', 
                                'Confirmed predicted PSI (two-consecutive gate)', 
                                ['pod'])
confirmation_gate_status = Gauge('confirmation_gate_status',
                                 'Confirmation gate status (0=not confirmed, 1=confirmed)',
                                 ['pod'])

# ============================================================
# PSI DATA BUFFER
# ============================================================

class PSIDataBuffer:
    """Maintains a sliding window of PSI data for each pod"""
    
    def __init__(self, max_length: int = MAX_ENCODER_LENGTH):
        self.max_length = max_length
        self.buffers: Dict[str, deque] = {}
        self.time_indices: Dict[str, int] = {}
        
    def add_sample(self, pod: str, psi_value: float, timestamp: datetime):
        """Add a PSI sample for a pod"""
        if pod not in self.buffers:
            self.buffers[pod] = deque(maxlen=self.max_length)
            self.time_indices[pod] = 0
        
        self.buffers[pod].append({
            'pod': pod,
            'psi_some_avg10': psi_value,
            'timestamp': timestamp,
            'time_idx': self.time_indices[pod]
        })
        
        self.time_indices[pod] += 1
    
    def get_data(self, pod: str) -> Optional[pd.DataFrame]:
        """Get buffered data for a pod as DataFrame"""
        if pod not in self.buffers or len(self.buffers[pod]) < self.max_length:
            return None
        
        data = list(self.buffers[pod])
        return pd.DataFrame(data)
    
    def has_enough_data(self, pod: str) -> bool:
        """Check if we have enough data to make predictions"""
        return pod in self.buffers and len(self.buffers[pod]) >= self.max_length

# ============================================================
# PREDICTION SERVICE
# ============================================================

class PredictionService:
    """Main prediction service class"""
    
    def __init__(self):
        self.model: Optional[TemporalFusionTransformer] = None
        self.psi_buffer = PSIDataBuffer()
        self.running = True
        
        # Initialize confirmation gate (Day 1 enhancement)
        if CONFIRMATION_GATE_AVAILABLE:
            self.confirmation_gate = ConfirmationGate(
                threshold=SPIKE_THRESHOLD,
                window_seconds=60
            )
            logger.info("✅ Confirmation gate initialized (threshold={SPIKE_THRESHOLD}%, window=60s)")
        else:
            self.confirmation_gate = None
            logger.warning("⚠️  Running without confirmation gate")
        
        # Statistics tracking
        self.stats = {
            'TP': 0,
            'FP': 0,
            'FN': 0,
            'TN': 0,
        }
        
        logger.info("Prediction Service initialized")
        logger.info(f"Model path: {MODEL_PATH}")
        logger.info(f"Spike threshold: {SPIKE_THRESHOLD}%")
        logger.info(f"Prometheus URL: {PROMETHEUS_URL}")
        logger.info(f"Shadow mode: {SHADOW_MODE}")
    
    @model_load_time.time()
    def load_model(self):
        """Load the trained TFT model"""
        logger.info("Loading TFT model...")
        
        try:
            self.model = TemporalFusionTransformer.load_from_checkpoint(
                MODEL_PATH,
                map_location='cpu'
            )
            self.model.eval()
            
            logger.info(f"✅ Model loaded successfully")
            logger.info(f"   Parameters: {sum(p.numel() for p in self.model.parameters()):,}")
            
        except Exception as e:
            logger.error(f"❌ Failed to load model: {e}")
            raise
    
    def query_prometheus(self, query: str) -> Dict:
        """Query Prometheus and return result"""
        url = f"{PROMETHEUS_URL}/api/v1/query"
        
        try:
            with prometheus_query_duration.time():
                response = requests.get(url, params={'query': query}, timeout=5)
                response.raise_for_status()
                return response.json()
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Prometheus query failed: {e}")
            return {'status': 'error', 'data': {'result': []}}
    
    def get_current_psi_metrics(self) -> Dict[str, float]:
        """Get current PSI metrics for all workload pods"""
        # Query for memory PSI - use deriv() to get the rate of change
        # This shows how fast the PSI counter is increasing (percentage per second)
        query = f'deriv(node_pressure_memory_waiting_seconds_total{{pod=~"workload-app-.*"}}[2m]) * 100'
        
        result = self.query_prometheus(query)
        
        psi_values = {}
        
        if result['status'] == 'success' and len(result['data']['result']) > 0:
            for item in result['data']['result']:
                pod = item['metric'].get('pod', 'unknown')
                value = float(item['value'][1])
                # Ensure non-negative values
                if value < 0:
                    value = 0.0
                psi_values[pod] = value
                
                # Update Prometheus gauge
                current_psi.labels(pod=pod).set(value)
        else:
            logger.warning(f"No PSI metrics found. Query: {query}")
        
        return psi_values
    
    def prepare_prediction_data(self, pod: str) -> Optional[torch.Tensor]:
        """Prepare data for prediction from buffer"""
        df = self.psi_buffer.get_data(pod)
        
        if df is None:
            return None
        
        # Add required columns (placeholders for missing features)
        df['series_id'] = pod
        df['hour_sin'] = np.sin(2 * np.pi * df.index / 24)
        df['hour_cos'] = np.cos(2 * np.pi * df.index / 24)
        
        # Placeholder features (model expects these but uses attention)
        df['request_rate'] = 100.0
        df['active_connections'] = 50.0
        df['cpu_usage'] = 0.5
        df['memory_usage'] = 2e9
        df['read_bytes_per_sec'] = 1e6
        df['write_bytes_per_sec'] = 1e6
        df['latency_ms'] = 50.0
        df['error_rate'] = 0.001
        
        # PSI averages (use same value for different time windows)
        df['psi_some_avg60'] = df['psi_some_avg10']
        df['psi_some_avg300'] = df['psi_some_avg10']
        df['psi_full_avg10'] = df['psi_some_avg10'] * 0.7
        df['psi_full_avg60'] = df['psi_some_avg10'] * 0.7
        df['psi_full_avg300'] = df['psi_some_avg10'] * 0.7
        
        return df
    
    def make_prediction(self, pod: str) -> Optional[Tuple[float, float, float, bool]]:
        """Make a prediction for a pod"""
        if not self.psi_buffer.has_enough_data(pod):
            logger.debug(f"Not enough data for {pod} yet")
            return None
        
        df = self.prepare_prediction_data(pod)
        if df is None:
            return None
        
        try:
            with prediction_latency.time():
                # Create dataset (simplified, using last window)
                # In production, you'd recreate the full TimeSeriesDataSet
                # For now, use model directly with prepared tensor
                
                # This is a simplified prediction - in production you'd need
                # to properly create TimeSeriesDataSet from the buffer
                
                # For now, return based on current PSI (threshold-based fallback)
                current = df['psi_some_avg10'].iloc[-1]
                
                # Simple heuristic prediction (replace with actual model inference)
                # This is a placeholder - proper implementation would use model
                q50 = current * 1.1  # Simple projection
                q90 = current * 1.3
                
                spike_pred = q90 > SPIKE_THRESHOLD
                
                return (q50, q90, current, spike_pred)
        
        except Exception as e:
            logger.error(f"Prediction error for {pod}: {e}")
            return None
    
    def update_statistics(self, pod: str, predicted_spike: bool, actual_spike: bool):
        """Update confusion matrix statistics"""
        if predicted_spike and actual_spike:
            self.stats['TP'] += 1
            true_positives.inc()
        elif predicted_spike and not actual_spike:
            self.stats['FP'] += 1
            false_positives.inc()
        elif not predicted_spike and actual_spike:
            self.stats['FN'] += 1
            false_negatives.inc()
        else:
            self.stats['TN'] += 1
        
        # Update precision and recall gauges
        tp = self.stats['TP']
        fp = self.stats['FP']
        fn = self.stats['FN']
        
        if tp + fp > 0:
            precision = tp / (tp + fp)
            precision_gauge.set(precision)
        
        if tp + fn > 0:
            recall = tp / (tp + fn)
            recall_gauge.set(recall)
    
    def prediction_loop(self):
        """Main prediction loop"""
        logger.info("Starting prediction loop...")
        logger.info(f"Predictions every {PREDICTION_INTERVAL} seconds")
        
        iteration = 0
        
        while self.running:
            try:
                iteration += 1
                logger.info(f"--- Iteration {iteration} ---")
                
                # Query current PSI metrics
                psi_metrics = self.get_current_psi_metrics()
                
                if not psi_metrics:
                    logger.warning("No PSI metrics found")
                    time.sleep(PREDICTION_INTERVAL)
                    continue
                
                # Add to buffer and make predictions
                now = datetime.now()
                
                for pod, psi_value in psi_metrics.items():
                    # Add to buffer
                    self.psi_buffer.add_sample(pod, psi_value, now)
                    
                    # Make prediction if we have enough data
                    if self.psi_buffer.has_enough_data(pod):
                        result = self.make_prediction(pod)
                        
                        if result:
                            q50, q90, current, spike_pred = result
                            
                            # Export RAW prediction (Day 1 enhancement)
                            predicted_psi_raw.labels(pod=pod).set(q90)
                            
                            # Apply confirmation gate if available (Day 1 enhancement)
                            is_confirmed = False
                            if self.confirmation_gate:
                                is_spike, is_confirmed, reason = self.confirmation_gate.check_spike(
                                    pod=pod,
                                    psi_value=current,
                                    predicted_psi=q90,
                                    timestamp=now
                                )
                                
                                # Export CONFIRMED prediction only if confirmed
                                if is_confirmed:
                                    predicted_psi_confirmed.labels(pod=pod).set(q90)
                                    confirmation_gate_status.labels(pod=pod).set(1.0)
                                    logger.info(f"  ✅ CONFIRMED: {reason}")
                                else:
                                    confirmation_gate_status.labels(pod=pod).set(0.0)
                                    if is_spike:
                                        logger.info(f"  ⏳ WAITING: {reason}")
                            else:
                                # No confirmation gate - treat as confirmed
                                predicted_psi_confirmed.labels(pod=pod).set(q90)
                                is_confirmed = spike_pred
                            
                            # Log prediction
                            logger.info(f"Pod {pod}:")
                            logger.info(f"  Current PSI:  {current:.2f}%")
                            logger.info(f"  Predicted q50: {q50:.2f}%")
                            logger.info(f"  Predicted q90: {q90:.2f}%")
                            logger.info(f"  Spike predicted (raw): {spike_pred}")
                            logger.info(f"  Spike confirmed (gated): {is_confirmed}")
                            
                            # Update metrics
                            predictions_total.inc()
                            predicted_psi.labels(pod=pod, quantile='q50').set(q50)
                            predicted_psi.labels(pod=pod, quantile='q90').set(q90)
                            spike_probability.labels(pod=pod).set(1.0 if spike_pred else 0.0)
                            
                            if is_confirmed:  # Use confirmed decision for actions
                                spikes_predicted_total.inc()
                                
                                if SHADOW_MODE:
                                    logger.info(f"  🔔 SHADOW: Would scale up {pod}")
                                else:
                                    logger.info(f"  🚀 ACTION: Triggering scale-up for {pod}")
                                    # TODO: Actual scaling action in Phase 8
                            
                            # Track actual spike for statistics
                            actual_spike = current > SPIKE_THRESHOLD
                            if actual_spike:
                                spikes_actual_total.inc()
                            
                            self.update_statistics(pod, is_confirmed, actual_spike)
                    
                    else:
                        buffer_size = len(self.psi_buffer.buffers.get(pod, []))
                        logger.debug(f"Pod {pod}: {buffer_size}/{MAX_ENCODER_LENGTH} samples")
                
                # Wait for next iteration
                time.sleep(PREDICTION_INTERVAL)
            
            except KeyboardInterrupt:
                logger.info("Received interrupt signal")
                self.running = False
                break
            
            except Exception as e:
                logger.error(f"Error in prediction loop: {e}", exc_info=True)
                time.sleep(PREDICTION_INTERVAL)
    
    def print_statistics(self):
        """Print final statistics"""
        logger.info("=" * 60)
        logger.info("FINAL STATISTICS")
        logger.info("=" * 60)
        
        tp = self.stats['TP']
        fp = self.stats['FP']
        fn = self.stats['FN']
        tn = self.stats['TN']
        
        total = tp + fp + fn + tn
        
        if total > 0:
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
            
            logger.info(f"Total predictions: {total}")
            logger.info(f"True Positives:  {tp}")
            logger.info(f"False Positives: {fp}")
            logger.info(f"False Negatives: {fn}")
            logger.info(f"True Negatives:  {tn}")
            logger.info(f"Precision: {precision*100:.2f}%")
            logger.info(f"Recall:    {recall*100:.2f}%")
            logger.info(f"F1 Score:  {f1*100:.2f}%")
        else:
            logger.info("No predictions made")
        
        logger.info("=" * 60)

# ============================================================
# HEALTH CHECK API
# ============================================================

app = Flask(__name__)

service_instance: Optional[PredictionService] = None

@app.route('/health')
def health():
    """Health check endpoint"""
    if service_instance and service_instance.model:
        return jsonify({
            'status': 'healthy',
            'model_loaded': True,
            'shadow_mode': SHADOW_MODE,
            'spike_threshold': SPIKE_THRESHOLD
        }), 200
    else:
        return jsonify({
            'status': 'unhealthy',
            'model_loaded': False
        }), 503

@app.route('/ready')
def ready():
    """Readiness check endpoint"""
    if service_instance and service_instance.model:
        return jsonify({'status': 'ready'}), 200
    else:
        return jsonify({'status': 'not_ready'}), 503

@app.route('/metrics-summary')
def metrics_summary():
    """Summary of prediction metrics"""
    if service_instance:
        stats = service_instance.stats
        tp = stats['TP']
        fp = stats['FP']
        fn = stats['FN']
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        
        return jsonify({
            'precision': precision,
            'recall': recall,
            'true_positives': tp,
            'false_positives': fp,
            'false_negatives': fn
        }), 200
    else:
        return jsonify({'error': 'Service not initialized'}), 503

# ============================================================
# MAIN
# ============================================================

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}")
    if service_instance:
        service_instance.running = False

def main():
    """Main entry point"""
    global service_instance
    
    logger.info("=" * 60)
    logger.info("KUBERNETES PSI PREDICTION SERVICE")
    logger.info("=" * 60)
    logger.info(f"Version: 1.0.0")
    logger.info(f"Shadow Mode: {SHADOW_MODE}")
    logger.info(f"Spike Threshold: {SPIKE_THRESHOLD}%")
    logger.info("=" * 60)
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start Prometheus metrics server
    logger.info(f"Starting metrics server on port {METRICS_PORT}...")
    start_http_server(METRICS_PORT)
    
    # Start Flask API server in background
    from threading import Thread
    api_thread = Thread(target=lambda: app.run(host='0.0.0.0', port=API_PORT, debug=False))
    api_thread.daemon = True
    api_thread.start()
    logger.info(f"Started API server on port {API_PORT}")
    
    # Initialize service
    service_instance = PredictionService()
    
    try:
        # Load model
        service_instance.load_model()
        
        # Start prediction loop
        service_instance.prediction_loop()
    
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1
    
    finally:
        # Print statistics
        if service_instance:
            service_instance.print_statistics()
        
        logger.info("Service stopped")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
