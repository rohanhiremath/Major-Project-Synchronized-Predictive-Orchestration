# Day 1: Prometheus Metrics Export - Quick Start Guide

**Date**: September 7, 2026 (Sunday)  
**Duration**: 4-6 hours  
**Goal**: Enable prediction service to export metrics to Prometheus

---

## 📋 Prerequisites Check

Before starting, verify:
```bash
# 1. Prediction service exists
ls kubernetes/phase6/prediction_service.py

# 2. Virtual environment active
source .venv/bin/activate

# 3. Kubernetes cluster running
kubectl get nodes

# 4. Prometheus accessible
curl http://localhost:9090/-/healthy
```

---

## 🎯 What We're Building

**Current State**: Prediction service logs to files  
**Target State**: Prediction service exports metrics to Prometheus

**Metrics to Export**:
1. `predicted_psi_confirmed` - Gated predictions (production)
2. `predicted_psi_raw` - Raw predictions (comparison)
3. `prediction_latency_seconds` - Performance monitoring
4. `predictions_total` - Counter for monitoring

---

## 🔧 Step 1: Add Prometheus Client (15 min)

### Update requirements.txt
```bash
cd kubernetes/phase6
echo "prometheus_client==0.17.1" >> requirements.txt
pip install prometheus_client
```

### Verify Installation
```bash
python3 -c "from prometheus_client import Gauge, Counter, start_http_server; print('✅ Prometheus client installed')"
```

---

## 🔧 Step 2: Update Prediction Service (60-90 min)

### Add Metrics Export Code

Add this at the top of `prediction_service.py` (after imports):

```python
from prometheus_client import Gauge, Counter, Histogram, start_http_server
import threading

# Prometheus metrics
predicted_psi_confirmed_gauge = Gauge(
    'predicted_psi_confirmed',
    'Confirmed predicted PSI (two-consecutive gate)',
    ['pod']
)

predicted_psi_raw_gauge = Gauge(
    'predicted_psi_raw',
    'Raw predicted PSI (no confirmation)',
    ['pod']
)

prediction_latency_histogram = Histogram(
    'prediction_latency_seconds',
    'Time taken to make a prediction',
    ['pod']
)

predictions_total_counter = Counter(
    'predictions_total',
    'Total number of predictions made',
    ['pod', 'spike_predicted']
)

# Start metrics server on port 8000
def start_metrics_server():
    """Start Prometheus metrics HTTP server"""
    start_http_server(8000)
    print("📊 Metrics server started on port 8000")

# Start in background thread
threading.Thread(target=start_metrics_server, daemon=True).start()
```

### Update Prediction Loop

Find the main prediction loop and add metric exports:

```python
# Inside the prediction loop, after making predictions:

# Record latency
with prediction_latency_histogram.labels(pod=pod_name).time():
    # ... existing prediction code ...
    pass

# Export raw prediction
predicted_psi_raw_gauge.labels(pod=pod_name).set(predicted_psi)

# Export confirmed prediction (if confirmed)
if is_confirmed:
    predicted_psi_confirmed_gauge.labels(pod=pod_name).set(predicted_psi)

# Increment counter
predictions_total_counter.labels(
    pod=pod_name,
    spike_predicted=str(is_spike)
).inc()
```

**Note**: Integrate with existing confirmation gate logic from Phase 6.

---

## 🔧 Step 3: Test Locally (30 min)

### Start Prediction Service
```bash
cd kubernetes/phase6

# Start in background
nohup python3 prediction_service.py > test-metrics.log 2>&1 &
PRED_PID=$!

echo "Prediction service PID: $PRED_PID"
```

### Check Metrics Endpoint
```bash
# Wait 30 seconds for first prediction
sleep 30

# Check metrics are being exported
curl http://localhost:8000/metrics | grep predicted_psi

# Should see output like:
# predicted_psi_raw{pod="workload-app-0"} 1.23
# predicted_psi_confirmed{pod="workload-app-0"} 1.45
```

### Verify Data
```bash
# Check for our metrics
curl http://localhost:8000/metrics | grep -E "(predicted_psi|predictions_total|prediction_latency)"

# You should see:
# - predicted_psi_raw (one per pod)
# - predicted_psi_confirmed (one per pod, when confirmed)
# - predictions_total (counter)
# - prediction_latency_seconds (histogram)
```

### Stop Test
```bash
kill $PRED_PID
```

---

## 🔧 Step 4: Create Kubernetes Service (30 min)

### Create Service Manifest

Create `kubernetes/phase6/prediction-service-svc.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: prediction-service
  namespace: default
  labels:
    app: prediction-service
spec:
  selector:
    app: prediction-service
  ports:
  - name: metrics
    port: 8000
    targetPort: 8000
    protocol: TCP
  - name: api
    port: 8080
    targetPort: 8080
    protocol: TCP
  type: ClusterIP
```

### Create Deployment Manifest

Create `kubernetes/phase6/prediction-service-deploy.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: prediction-service
  namespace: default
spec:
  replicas: 1
  selector:
    matchLabels:
      app: prediction-service
  template:
    metadata:
      labels:
        app: prediction-service
    spec:
      containers:
      - name: prediction-service
        image: python:3.9-slim  # Or your custom image
        command:
        - python3
        - /app/prediction_service.py
        ports:
        - name: metrics
          containerPort: 8000
        - name: api
          containerPort: 8080
        volumeMounts:
        - name: app-code
          mountPath: /app
        - name: model
          mountPath: /models
        env:
        - name: MODEL_PATH
          value: "/models/tft_psi_model.ckpt"
        - name: PROMETHEUS_URL
          value: "http://prometheus-server.monitoring.svc:80"
      volumes:
      - name: app-code
        configMap:
          name: prediction-service-code
      - name: model
        hostPath:
          path: /path/to/models
          type: Directory
```

**Note**: Adjust paths and image as needed for your environment.

---

## 🔧 Step 5: Create Prometheus Scrape Config (30 min)

### Create ServiceMonitor

Create `kubernetes/phase6/prediction-service-monitor.yaml`:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: prediction-service
  namespace: default
  labels:
    app: prediction-service
spec:
  selector:
    matchLabels:
      app: prediction-service
  endpoints:
  - port: metrics
    interval: 20s
    path: /metrics
```

### Or Update Prometheus ConfigMap (if not using operator)

Edit Prometheus config:

```yaml
scrape_configs:
- job_name: 'prediction-service'
  static_configs:
    - targets: ['prediction-service.default.svc:8000']
  scrape_interval: 20s
  scrape_timeout: 10s
```

---

## 🔧 Step 6: Deploy to Kubernetes (30 min)

### Deploy All Resources
```bash
cd kubernetes/phase6

# Deploy service
kubectl apply -f prediction-service-svc.yaml

# Deploy deployment
kubectl apply -f prediction-service-deploy.yaml

# Deploy ServiceMonitor (if using Prometheus Operator)
kubectl apply -f prediction-service-monitor.yaml

# Check status
kubectl get pods -l app=prediction-service
kubectl get svc prediction-service
```

### Port Forward for Testing
```bash
# Forward metrics port
kubectl port-forward svc/prediction-service 8000:8000 &

# Test
curl http://localhost:8000/metrics | grep predicted_psi
```

---

## 🔧 Step 7: Verify in Prometheus (30 min)

### Access Prometheus UI
```bash
# Port forward Prometheus (if needed)
kubectl port-forward -n monitoring svc/prometheus-server 9090:80

# Open in browser
http://localhost:9090
```

### Query Metrics

In Prometheus UI, try these queries:

```promql
# Check if metrics exist
predicted_psi_raw

# Check per pod
predicted_psi_raw{pod="workload-app-0"}

# Check confirmed predictions
predicted_psi_confirmed

# Check prediction rate
rate(predictions_total[5m])

# Check latency
histogram_quantile(0.95, rate(prediction_latency_seconds_bucket[5m]))
```

### Expected Results

You should see:
- ✅ Metrics appearing in Prometheus
- ✅ Values updating every 20 seconds
- ✅ One metric per pod (3 pods = 3 time series)
- ✅ Confirmed values lower than raw (confirmation gate working)

---

## ✅ Success Criteria

### Must Have (Complete Day 1)
- [ ] Prometheus client installed
- [ ] Metrics code added to prediction service
- [ ] Local test successful (metrics visible at localhost:8000)
- [ ] Service deployed to Kubernetes
- [ ] Metrics visible in Prometheus UI
- [ ] At least 10 predictions collected

### Nice to Have (If time permits)
- [ ] Grafana dashboard created
- [ ] Alert rules configured
- [ ] Documentation updated
- [ ] Performance benchmarks recorded

---

## 🐛 Troubleshooting

### Issue: Metrics endpoint not responding
```bash
# Check service is running
kubectl get pods -l app=prediction-service
kubectl logs -l app=prediction-service

# Check port 8000 is open
kubectl port-forward svc/prediction-service 8000:8000
curl http://localhost:8000/metrics
```

### Issue: Prometheus not scraping
```bash
# Check ServiceMonitor
kubectl get servicemonitor prediction-service

# Check Prometheus targets
# Visit: http://localhost:9090/targets
# Should see "prediction-service" target

# Check Prometheus logs
kubectl logs -n monitoring -l app=prometheus
```

### Issue: No metrics appearing
```bash
# Check if predictions are being made
kubectl logs -l app=prediction-service | grep "Iteration"

# Check metrics endpoint manually
curl http://localhost:8000/metrics

# Should see HELP and TYPE comments for our metrics
```

### Issue: Import errors
```bash
# Reinstall requirements
pip install -r kubernetes/phase6/requirements.txt

# Verify prometheus_client version
pip show prometheus_client
```

---

## 📊 Sample Output

### Expected Metrics Format
```
# HELP predicted_psi_raw Raw predicted PSI (no confirmation)
# TYPE predicted_psi_raw gauge
predicted_psi_raw{pod="workload-app-0"} 1.45
predicted_psi_raw{pod="workload-app-1"} 2.31
predicted_psi_raw{pod="workload-app-2"} 0.89

# HELP predicted_psi_confirmed Confirmed predicted PSI (two-consecutive gate)
# TYPE predicted_psi_confirmed gauge
predicted_psi_confirmed{pod="workload-app-0"} 1.45
predicted_psi_confirmed{pod="workload-app-1"} 2.31

# HELP predictions_total Total number of predictions made
# TYPE predictions_total counter
predictions_total{pod="workload-app-0",spike_predicted="True"} 15.0
predictions_total{pod="workload-app-0",spike_predicted="False"} 45.0
```

---

## 📁 Files Modified/Created

- ✅ `kubernetes/phase6/requirements.txt` - Added prometheus_client
- ✅ `kubernetes/phase6/prediction_service.py` - Added metrics export
- ✅ `kubernetes/phase6/prediction-service-svc.yaml` - Service definition
- ✅ `kubernetes/phase6/prediction-service-deploy.yaml` - Deployment
- ✅ `kubernetes/phase6/prediction-service-monitor.yaml` - ServiceMonitor

---

## ⏭️ Next Steps (Day 2)

After completing Day 1:
1. ✅ Metrics are being exported
2. ✅ Prometheus is scraping successfully
3. ✅ Data is visible in Prometheus UI

**Tomorrow (Day 2)**: Configure Prometheus Adapter to expose these as Kubernetes custom metrics so HPA can use them.

---

## 📞 Need Help?

If you get stuck:
1. Check logs: `kubectl logs -l app=prediction-service`
2. Verify Prometheus: http://localhost:9090/targets
3. Test metrics manually: `curl http://localhost:8000/metrics`
4. Review Phase 6 confirmation gate code for integration

**Day 1 Goal**: End the day with metrics visible in Prometheus! 🎯

---

*Estimated Time: 4-6 hours*  
*Difficulty: Medium*  
*Prerequisites: Phase 6 complete, Python/kubectl knowledge*
