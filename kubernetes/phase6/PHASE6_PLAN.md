# Phase 6: Prediction Service Deployment

**Goal**: Deploy the TFT model as a production service in Kubernetes that makes real-time PSI spike predictions.

---

## Objectives

1. ✅ Build Python prediction service
2. ✅ Query Prometheus for live PSI metrics
3. ✅ Make predictions every 20 seconds
4. ✅ Output scaling decisions
5. ✅ Containerize the service
6. ✅ Deploy to Kubernetes
7. ✅ Test in shadow mode

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                 Kubernetes Cluster                       │
│                                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐             │
│  │  Pod 0   │  │  Pod 1   │  │  Pod 2   │             │
│  │ Workload │  │ Workload │  │ Workload │             │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘             │
│       │             │             │                     │
│       └─────────────┴─────────────┘                     │
│                     │ PSI metrics                       │
│            ┌────────▼────────┐                          │
│            │   Prometheus    │                          │
│            │  (Scrapes 20s)  │                          │
│            └────────┬────────┘                          │
│                     │ HTTP queries                      │
│       ┌─────────────▼─────────────┐                    │
│       │  Prediction Service       │                    │
│       │  ┌─────────────────────┐  │                    │
│       │  │ TFT Model           │  │                    │
│       │  │ - Threshold: 1.80%  │  │                    │
│       │  │ - 30s horizon       │  │                    │
│       │  └─────────────────────┘  │                    │
│       │  ┌─────────────────────┐  │                    │
│       │  │ Decision Logic      │  │                    │
│       │  │ - Spike detection   │  │                    │
│       │  │ - Confidence score  │  │                    │
│       │  └─────────────────────┘  │                    │
│       │  ┌─────────────────────┐  │                    │
│       │  │ Metrics Exporter    │  │                    │
│       │  │ - Predictions/sec   │  │                    │
│       │  │ - Accuracy          │  │                    │
│       │  └─────────────────────┘  │                    │
│       └───────────┬───────────────┘                    │
│                   │ Logs & metrics                      │
│                   ▼                                     │
│       ┌───────────────────────┐                        │
│       │   Logs / Dashboard    │                        │
│       └───────────────────────┘                        │
└─────────────────────────────────────────────────────────┘
```

---

## Components to Build

### 1. Prediction Service (Python)

**File**: `prediction_service.py`

**Features**:
- Load TFT model from checkpoint
- Query Prometheus for PSI metrics
- Maintain sliding window (30 steps = 10 minutes)
- Make predictions every 20 seconds
- Output spike predictions with confidence
- Log predictions and actuals
- Export Prometheus metrics

**Configuration**:
```python
MODEL_PATH = "/app/models/tft_psi_model.ckpt"
PROMETHEUS_URL = "http://prometheus-kube-prometheus-stack-prometheus.monitoring:9090"
PREDICTION_INTERVAL = 20  # seconds
SPIKE_THRESHOLD = 1.80  # optimized
MAX_ENCODER_LENGTH = 30  # 10 minutes history
```

---

### 2. Dockerfile

**File**: `Dockerfile`

**Base**: Python 3.10-slim
**Size target**: <500MB
**Includes**:
- PyTorch (CPU version)
- PyTorch Forecasting
- Prometheus client
- Model checkpoint

---

### 3. Kubernetes Manifests

#### Deployment

**File**: `deployment.yaml`

**Specs**:
- Replicas: 1
- Resources:
  - CPU: 500m request, 1000m limit
  - Memory: 1Gi request, 2Gi limit
- Readiness probe: HTTP /health
- Liveness probe: HTTP /health
- Environment variables from ConfigMap

#### ConfigMap

**File**: `configmap.yaml`

**Configuration**:
```yaml
SPIKE_THRESHOLD: "1.80"
PREDICTION_INTERVAL: "20"
PROMETHEUS_URL: "http://prometheus-..."
LOG_LEVEL: "INFO"
SHADOW_MODE: "true"  # Don't trigger actions yet
```

#### Service

**File**: `service.yaml`

**Ports**:
- 8080: HTTP API
- 9090: Prometheus metrics

---

### 4. Prometheus ServiceMonitor

**File**: `servicemonitor.yaml`

**Metrics to export**:
- `predictions_total` - Total predictions made
- `spikes_predicted_total` - Spikes predicted
- `prediction_latency_seconds` - Prediction latency
- `model_load_time_seconds` - Model load time
- `prometheus_query_duration_seconds` - Query time

---

## Implementation Steps

### Step 1: Build Prediction Service ✅
- Create `prediction_service.py`
- Implement Prometheus query logic
- Implement prediction loop
- Add health check endpoint
- Add metrics endpoint

### Step 2: Create Dockerfile ✅
- Multi-stage build for smaller image
- Copy model checkpoint
- Install dependencies
- Configure entrypoint

### Step 3: Build and Test Locally ✅
- Build Docker image
- Test with local Prometheus port-forward
- Verify predictions work
- Check metrics export

### Step 4: Create Kubernetes Manifests ✅
- Deployment with proper resources
- ConfigMap for configuration
- Service for discovery
- ServiceMonitor for metrics

### Step 5: Deploy to Kubernetes ✅
- Apply manifests
- Verify pod starts
- Check logs for predictions
- Verify metrics in Prometheus

### Step 6: Shadow Mode Testing ✅
- Monitor predictions vs actuals
- Calculate real-time precision/recall
- Log all decisions
- No actual scaling actions

### Step 7: Create Dashboard ✅
- Grafana dashboard
- Show predictions over time
- Show accuracy metrics
- Compare with actual PSI

---

## Success Criteria

### Service Health
- [ ] Pod starts successfully
- [ ] Model loads in <30 seconds
- [ ] Health check passes
- [ ] No crashes for 1 hour

### Prediction Performance
- [ ] Makes predictions every 20 seconds
- [ ] Query latency <1 second
- [ ] Prediction latency <100ms
- [ ] Memory usage <2GB

### Accuracy (Shadow Mode)
- [ ] Precision >90% over 1 hour
- [ ] Recall >95% over 1 hour
- [ ] False positive rate <5%
- [ ] Zero crashes

### Monitoring
- [ ] Metrics exported to Prometheus
- [ ] Logs show predictions
- [ ] Grafana dashboard functional
- [ ] Alerts configured

---

## Configuration

### Model Configuration
```python
{
    "model_path": "/app/models/tft_psi_model.ckpt",
    "spike_threshold": 1.80,
    "max_encoder_length": 30,
    "prediction_horizon": 30,
    "target": "psi_some_avg10"
}
```

### Prometheus Queries
```promql
# Get PSI metrics for all pods
rate(node_pressure_memory_waiting_seconds_total[10s]) * 100

# Aggregate by pod
sum by (pod) (rate(node_pressure_memory_waiting_seconds_total[10s])) * 100
```

---

## Testing Plan

### Unit Tests
- Test Prometheus query builder
- Test prediction function
- Test threshold logic
- Test metrics export

### Integration Tests
- Test with mock Prometheus
- Test model loading
- Test prediction pipeline
- Test error handling

### System Tests
- Deploy to test cluster
- Run for 1 hour
- Verify predictions
- Check accuracy

---

## Rollout Plan

### Phase 6a: Local Development ✅
- Build service locally
- Test with port-forwarded Prometheus
- Verify predictions work

### Phase 6b: Deployment ✅
- Build Docker image
- Push to registry
- Deploy to Kubernetes
- Verify pod health

### Phase 6c: Shadow Mode (1 week)
- Monitor predictions
- Log all decisions
- Calculate metrics
- No actions taken

### Phase 6d: Validation
- Compare shadow predictions with reactive HPA
- Calculate improvement metrics
- Present results
- Get approval for Phase 7

---

## Deliverables

1. `prediction_service.py` - Main service
2. `Dockerfile` - Container image
3. `deployment.yaml` - Kubernetes deployment
4. `configmap.yaml` - Configuration
5. `service.yaml` - Service definition
6. `servicemonitor.yaml` - Prometheus metrics
7. `dashboard.json` - Grafana dashboard
8. `README.md` - Deployment instructions
9. `RESULTS.md` - Shadow mode results

---

## Timeline

- **Day 1**: Build prediction service
- **Day 2**: Create Dockerfile and test locally
- **Day 3**: Create K8s manifests and deploy
- **Day 4**: Shadow mode testing
- **Day 5-11**: Monitor and collect metrics (1 week)
- **Day 12**: Analyze results and report

**Total: ~2 weeks for complete Phase 6**

---

## Next: Phase 7

After Phase 6 shadow mode validation:
- Integrate with HPA
- Enable actual scaling
- A/B test with reactive HPA
- Measure improvements

---

*Phase 6 Start Date: September 1, 2026*  
*Expected Completion: September 15, 2026*  
*Status: Starting*
