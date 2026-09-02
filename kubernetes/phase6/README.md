# Phase 6: Prediction Service Deployment

This directory contains the production-ready prediction service that makes real-time PSI spike predictions in Kubernetes.

---

## 📋 Overview

The prediction service:
- ✅ Loads the trained TFT model (92% precision, 100% recall)
- ✅ Queries Prometheus for PSI metrics every 20 seconds
- ✅ Makes 30-second ahead spike predictions
- ✅ Operates in shadow mode (logs predictions, no actions)
- ✅ Exports metrics to Prometheus
- ✅ Provides health check and metrics APIs

---

## 📁 Files

```
phase6/
├── prediction_service.py    # Main service (Python)
├── Dockerfile               # Container image
├── requirements.txt         # Python dependencies
├── configmap.yaml          # Configuration
├── deployment.yaml         # Kubernetes deployment
├── service.yaml            # Kubernetes service
├── rbac.yaml               # ServiceAccount & permissions
├── servicemonitor.yaml     # Prometheus metrics scraping
├── PHASE6_PLAN.md          # Detailed plan
└── README.md               # This file
```

---

## 🚀 Quick Start

### Step 1: Build Docker Image

```bash
# From project root
cd kubernetes/phase6

# Build image
docker build -t prediction-service:v1.0.0 \
  --build-context models=../../models \
  --build-context src=../../src \
  .

# Or use docker-compose
docker build -t prediction-service:v1.0.0 -f Dockerfile ../../
```

### Step 2: Load Image to kind (if using kind)

```bash
kind load docker-image prediction-service:v1.0.0
```

### Step 3: Deploy to Kubernetes

```bash
# Apply all manifests
kubectl apply -f rbac.yaml
kubectl apply -f configmap.yaml
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
kubectl apply -f servicemonitor.yaml

# Or apply all at once
kubectl apply -f .
```

### Step 4: Verify Deployment

```bash
# Check pod status
kubectl get pods -l app=prediction-service

# Check logs
kubectl logs -f deployment/prediction-service

# Check health
kubectl port-forward service/prediction-service 8080:8080
curl http://localhost:8080/health
```

---

## ⚙️ Configuration

### Environment Variables (via ConfigMap)

| Variable | Default | Description |
|----------|---------|-------------|
| `SPIKE_THRESHOLD` | 1.80 | PSI threshold for spike detection (%) |
| `MAX_ENCODER_LENGTH` | 30 | History window (steps) |
| `MAX_PREDICTION_LENGTH` | 30 | Prediction horizon (steps) |
| `PROMETHEUS_URL` | `http://prometheus-...` | Prometheus endpoint |
| `PREDICTION_INTERVAL` | 20 | Prediction frequency (seconds) |
| `POD_LABEL_SELECTOR` | `app=workload` | Pods to monitor |
| `SHADOW_MODE` | true | Shadow mode (no actions) |
| `LOG_LEVEL` | INFO | Logging level |
| `METRICS_PORT` | 9090 | Prometheus metrics port |
| `API_PORT` | 8080 | API/health check port |

### Modifying Configuration

```bash
# Edit ConfigMap
kubectl edit configmap prediction-service-config

# Or update file and reapply
kubectl apply -f configmap.yaml

# Restart pod to pick up changes
kubectl rollout restart deployment/prediction-service
```

---

## 🔍 Monitoring

### View Logs

```bash
# Follow logs
kubectl logs -f deployment/prediction-service

# Last 100 lines
kubectl logs --tail=100 deployment/prediction-service

# Logs with timestamps
kubectl logs --timestamps deployment/prediction-service
```

### Check Metrics

```bash
# Port-forward metrics endpoint
kubectl port-forward service/prediction-service 9090:9090

# View Prometheus metrics
curl http://localhost:9090/metrics

# View custom metrics summary
curl http://localhost:8080/metrics-summary
```

### Prometheus Queries

```promql
# Total predictions made
predictions_total

# Spikes predicted
spikes_predicted_total

# Current precision
prediction_precision

# Current recall
prediction_recall

# Prediction latency (99th percentile)
histogram_quantile(0.99, rate(prediction_latency_seconds_bucket[5m]))

# Prometheus query duration
rate(prometheus_query_duration_seconds_sum[5m]) / rate(prometheus_query_duration_seconds_count[5m])
```

---

## 📊 Exported Metrics

### Counters
- `predictions_total` - Total predictions made
- `spikes_predicted_total` - Spikes predicted
- `spikes_actual_total` - Actual spikes observed
- `true_positives_total` - True positive predictions
- `false_positives_total` - False positive predictions
- `false_negatives_total` - False negative predictions

### Gauges
- `current_psi_value{pod}` - Current PSI value per pod
- `predicted_psi_value{pod,quantile}` - Predicted PSI (q50, q90)
- `spike_probability{pod}` - Spike probability per pod
- `prediction_precision` - Current precision
- `prediction_recall` - Current recall

### Histograms
- `prediction_latency_seconds` - Prediction latency
- `prometheus_query_duration_seconds` - Prometheus query time

### Summary
- `model_load_time_seconds` - Model loading time

---

## 🔧 Troubleshooting

### Pod Not Starting

```bash
# Check pod status
kubectl describe pod -l app=prediction-service

# Check events
kubectl get events --sort-by='.lastTimestamp'

# Check if model file exists
kubectl exec -it deployment/prediction-service -- ls -lh /app/models/
```

### Model Loading Errors

```bash
# Check logs for model loading
kubectl logs deployment/prediction-service | grep "Model"

# Verify model path
kubectl exec -it deployment/prediction-service -- cat /app/models/tft_psi_model.ckpt | head -c 100
```

### Prometheus Connection Issues

```bash
# Test Prometheus from pod
kubectl exec -it deployment/prediction-service -- \
  curl -s "http://prometheus-kube-prometheus-stack-prometheus.monitoring:9090/api/v1/query?query=up"

# Check DNS resolution
kubectl exec -it deployment/prediction-service -- \
  nslookup prometheus-kube-prometheus-stack-prometheus.monitoring
```

### No Predictions Being Made

```bash
# Check if workload pods are running
kubectl get pods -l app=workload

# Check PSI metrics in Prometheus
kubectl port-forward -n monitoring service/prometheus-kube-prometheus-stack-prometheus 9090:9090

# Query: rate(node_pressure_memory_waiting_seconds_total[10s]) * 100
```

### High Memory Usage

```bash
# Check resource usage
kubectl top pod -l app=prediction-service

# Reduce buffer size in code or restart
kubectl rollout restart deployment/prediction-service
```

---

## 🧪 Testing

### Local Testing (Before Deployment)

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export MODEL_PATH="../../models/tft_psi_model.ckpt"
export PROMETHEUS_URL="http://localhost:9090"
export SHADOW_MODE="true"

# Port-forward Prometheus
kubectl port-forward -n monitoring service/prometheus-kube-prometheus-stack-prometheus 9090:9090

# Run service locally
python prediction_service.py
```

### Integration Testing

```bash
# Deploy to test namespace
kubectl create namespace prediction-test
kubectl apply -f . -n prediction-test

# Run for 10 minutes
sleep 600

# Check logs
kubectl logs -n prediction-test deployment/prediction-service --tail=100

# Clean up
kubectl delete namespace prediction-test
```

---

## 📈 Performance Expectations

### Resource Usage
- **CPU**: 200-500m average, 1000m spike during prediction
- **Memory**: 800MB-1.5GB (model + buffers)
- **Prediction latency**: <100ms
- **Prometheus query latency**: <1s

### Accuracy (Shadow Mode)
- **Precision**: Target >90% (optimized threshold)
- **Recall**: Target >95%
- **F1 Score**: Target >90%

---

## 🔄 Updating

### Update Configuration

```bash
# Edit configmap
kubectl edit configmap prediction-service-config

# Or apply updated file
kubectl apply -f configmap.yaml

# Rolling restart
kubectl rollout restart deployment/prediction-service
```

### Update Image

```bash
# Build new image
docker build -t prediction-service:v1.0.1 ../../

# Load to kind
kind load docker-image prediction-service:v1.0.1

# Update deployment
kubectl set image deployment/prediction-service \
  prediction-service=prediction-service:v1.0.1

# Or update deployment.yaml and apply
kubectl apply -f deployment.yaml
```

---

## 🗑️ Cleanup

```bash
# Delete all resources
kubectl delete -f .

# Or delete individually
kubectl delete deployment prediction-service
kubectl delete service prediction-service
kubectl delete configmap prediction-service-config
kubectl delete serviceaccount prediction-service
kubectl delete clusterrolebinding prediction-service-binding
kubectl delete clusterrole prediction-service-role
kubectl delete servicemonitor prediction-service
```

---

## 📚 Next Steps

After Phase 6 shadow mode validation:

1. **Collect 1 week of shadow mode data**
2. **Analyze precision/recall over time**
3. **Identify edge cases**
4. **Tune threshold if needed**
5. **Proceed to Phase 7: HPA Integration**

---

## 🔗 Related Documentation

- [PHASE6_PLAN.md](PHASE6_PLAN.md) - Detailed implementation plan
- [Phase 5 Results](../phase5/PRECISION_OPTIMIZATION_FINAL.md) - Model validation
- [Project Summary](../../PROJECT_SUMMARY.md) - Complete project overview

---

## 📝 Notes

- **Shadow Mode**: Service makes predictions but doesn't trigger scaling
- **Production Model**: Uses `tft_psi_model.ckpt` (92% precision)
- **Threshold**: Optimized to 1.80% for best precision/recall balance
- **Monitoring**: All predictions logged and exported to Prometheus
- **Safety**: Runs as non-root, read-only filesystem where possible

---

*Phase 6 Version: 1.0.0*  
*Last Updated: September 1, 2026*  
*Status: Ready for Deployment*
