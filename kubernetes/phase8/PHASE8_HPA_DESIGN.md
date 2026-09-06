# Phase 8: HPA Integration Design
## Predictive Autoscaling with Confirmation Gate

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                           │
│                                                                  │
│  ┌──────────────┐      ┌──────────────────────────────────┐   │
│  │   Workload   │      │   Prediction Service             │   │
│  │     Pods     │      │   (with Confirmation Gate)       │   │
│  └──────────────┘      └──────────────────────────────────┘   │
│         │                          │                            │
│         │ PSI metrics             │ Predictions                │
│         ↓                          ↓                            │
│  ┌─────────────────────────────────────────────────┐          │
│  │              Prometheus                          │          │
│  │  - Collects PSI via cAdvisor                    │          │
│  │  - Stores predictions as custom metrics         │          │
│  └─────────────────────────────────────────────────┘          │
│         │                          │                            │
│         │                          │                            │
│         ↓                          ↓                            │
│  ┌──────────────┐      ┌─────────────────────────┐           │
│  │  Prometheus  │      │  Custom Metrics API     │           │
│  │   Adapter    │◄─────│  (k8s-prometheus-adapter)│           │
│  └──────────────┘      └─────────────────────────┘           │
│         │                                                       │
│         │ predicted_psi metric                                 │
│         ↓                                                       │
│  ┌──────────────────────────────────────────────┐             │
│  │   Horizontal Pod Autoscaler (HPA)            │             │
│  │   - Scales on predicted_psi_confirmed        │             │
│  │   - Target: < 1.80%                          │             │
│  └──────────────────────────────────────────────┘             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Component Breakdown

### 1. Prediction Service Enhancement

**Current State**: Shadow mode logging only
**Phase 8 Enhancement**: Export metrics to Prometheus

**New Capability**: Prometheus metric export
```python
from prometheus_client import Gauge, start_http_server

# Metrics to expose
predicted_psi_gauge = Gauge(
    'predicted_psi_confirmed', 
    'Confirmed predicted PSI (two-consecutive gate)',
    ['pod']
)

predicted_psi_raw_gauge = Gauge(
    'predicted_psi_raw', 
    'Raw predicted PSI (no confirmation)',
    ['pod']
)

# In prediction loop
if is_confirmed:
    predicted_psi_gauge.labels(pod=pod_name).set(predicted_psi)

predicted_psi_raw_gauge.labels(pod=pod_name).set(predicted_psi)
```

**Deployment**:
```yaml
apiVersion: v1
kind: Service
metadata:
  name: prediction-service
  labels:
    app: prediction-service
spec:
  selector:
    app: prediction-service
  ports:
  - name: metrics
    port: 8000
    targetPort: 8000
  - name: health
    port: 8080
    targetPort: 8080
```

**Prometheus Scrape Config**:
```yaml
- job_name: 'prediction-service'
  static_configs:
    - targets: ['prediction-service:8000']
  scrape_interval: 20s
```

---

### 2. Custom Metrics API Setup

**Install Prometheus Adapter**:
```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm install prometheus-adapter prometheus-community/prometheus-adapter \
  --namespace monitoring \
  --set prometheus.url=http://prometheus-server.monitoring.svc \
  --set prometheus.port=80 \
  -f custom-metrics-config.yaml
```

**Custom Metrics Configuration** (`custom-metrics-config.yaml`):
```yaml
rules:
- seriesQuery: 'predicted_psi_confirmed{pod!=""}'
  resources:
    overrides:
      pod: {resource: "pod"}
  name:
    matches: "^(.*)$"
    as: "predicted_psi_confirmed"
  metricsQuery: |
    max_over_time(
      predicted_psi_confirmed{<<.LabelMatchers>>}[2m]
    )

- seriesQuery: 'predicted_psi_raw{pod!=""}'
  resources:
    overrides:
      pod: {resource: "pod"}
  name:
    matches: "^(.*)$"
    as: "predicted_psi_raw"
  metricsQuery: |
    max_over_time(
      predicted_psi_raw{<<.LabelMatchers>>}[2m]
    )
```

**Verify Custom Metrics**:
```bash
kubectl get --raw "/apis/custom.metrics.k8s.io/v1beta1" | jq .

# Should show: predicted_psi_confirmed and predicted_psi_raw
```

---

### 3. HPA Configuration

**Predictive HPA** (Phase 8):
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: workload-predictive-hpa
  namespace: default
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: workload-app
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Pods
    pods:
      metric:
        name: predicted_psi_confirmed
      target:
        type: AverageValue
        averageValue: "1800m"  # 1.80% threshold
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 0  # Immediate scale-up (predictive)
      policies:
      - type: Percent
        value: 50
        periodSeconds: 15
      - type: Pods
        value: 2
        periodSeconds: 15
      selectPolicy: Max
    scaleDown:
      stabilizationWindowSeconds: 300  # 5-min cooldown
      policies:
      - type: Percent
        value: 10
        periodSeconds: 60
```

**Baseline Reactive HPA** (Phase 9 comparison):
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: workload-reactive-hpa
  namespace: default
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: workload-app
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Pods
    pods:
      metric:
        name: container_cpu_pressure_some_avg10  # Current PSI
      target:
        type: AverageValue
        averageValue: "1800m"  # Same 1.80% threshold
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 30  # Reactive delay
      policies:
      - type: Percent
        value: 50
        periodSeconds: 30
    scaleDown:
      stabilizationWindowSeconds: 300
```

---

## Rollout Strategy (Controlled)

### Phase 8.1: Shadow Mode with Metrics (Week 1)
- Deploy prediction service with Prometheus export
- Deploy Prometheus Adapter with custom metrics
- **NO HPA changes yet**
- Validate metrics are visible: `kubectl get --raw /apis/custom.metrics.k8s.io/v1beta1`

**Success Criteria**:
- ✅ `predicted_psi_confirmed` metric available
- ✅ Values match prediction service logs
- ✅ No impact on existing pods

---

### Phase 8.2: Predictive HPA - 10% Traffic (Week 2)
- Create A/B test: 10% pods use predictive HPA, 90% use reactive HPA
- Use pod labels to segregate: `hpa-mode: predictive` vs `hpa-mode: reactive`

**Deployment**:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: workload-app-predictive
spec:
  replicas: 1  # 10% of 10 pods
  selector:
    matchLabels:
      app: workload-app
      hpa-mode: predictive
  template:
    metadata:
      labels:
        app: workload-app
        hpa-mode: predictive
    spec:
      containers:
      - name: workload
        image: workload:latest
```

**Monitor**:
- Scale-up latency: reactive vs predictive
- False positive rate (unnecessary scale-ups)
- PSI breach duration

**Success Criteria**:
- ✅ Predictive pods scale faster (< 30s vs > 60s)
- ✅ False positive rate < 5%
- ✅ PSI breach reduction > 50%

---

### Phase 8.3: Predictive HPA - 50% Traffic (Week 3)
- Increase to 50% pods on predictive HPA
- Continue monitoring metrics

**Success Criteria**:
- ✅ No HPA flapping (excessive scale-up/down cycles)
- ✅ Cost neutral or lower (pod-hour efficiency)

---

### Phase 8.4: Predictive HPA - 100% Traffic (Week 4)
- Full rollout to all pods
- Keep reactive HPA config as fallback

**Success Criteria**:
- ✅ All pods using predictive HPA
- ✅ Production stability maintained

---

## Monitoring & Observability

### Key Metrics to Track

1. **Scale-up Latency**:
   - Time from PSI > 1.80% to new pod ready
   - Target: < 30s (predictive) vs > 60s (reactive)

2. **PSI Breach Duration**:
   - Time PSI stays above threshold
   - Target: < 60s (predictive) vs > 120s (reactive)

3. **False Positive Rate**:
   - Scale-ups where PSI never breaches
   - Target: < 5%

4. **Pod Efficiency**:
   - Total pod-hours for same workload
   - Target: ≤ 1.1x reactive (acceptable overhead)

5. **HPA Flapping**:
   - Rapid scale-up/down cycles
   - Target: 0 flaps over 24h

### Grafana Dashboard Panels

```json
{
  "title": "Predictive vs Reactive HPA Comparison",
  "panels": [
    {
      "title": "Scale-up Latency",
      "targets": [
        {
          "expr": "histogram_quantile(0.95, rate(hpa_scale_up_duration_seconds_bucket[5m]))",
          "legendFormat": "{{hpa_mode}}"
        }
      ]
    },
    {
      "title": "PSI Breach Duration",
      "targets": [
        {
          "expr": "rate(psi_breach_duration_seconds[5m])",
          "legendFormat": "{{hpa_mode}}"
        }
      ]
    },
    {
      "title": "Pod Count Over Time",
      "targets": [
        {
          "expr": "count(kube_pod_info{hpa_mode=~'predictive|reactive'})",
          "legendFormat": "{{hpa_mode}}"
        }
      ]
    }
  ]
}
```

---

## Rollback Plan

### Trigger Conditions
- False positive rate > 10%
- HPA flapping (> 5 cycles/hour)
- Increased pod-hour cost (> 1.5x baseline)
- Production instability

### Rollback Procedure
```bash
# Immediate: Switch all pods back to reactive HPA
kubectl apply -f workload-reactive-hpa.yaml

# Delete predictive HPA
kubectl delete hpa workload-predictive-hpa

# Keep prediction service running in shadow mode
# Analyze logs to fix confirmation gate logic
```

---

## Phase 9 Integration: Comparative Experiment

Once Phase 8 is stable (100% predictive HPA), run Phase 9:

**Experiment Design**:
1. Run same 6 workload scenarios (step/ramp/periodic/sustained/flash/mixed)
2. Capture metrics for:
   - **Reactive HPA baseline** (re-enable for comparison)
   - **Predictive HPA** (with confirmation gate)

**Duration**: 24 hours (4 full cycles through all scenarios)

**Metrics Collected**:
| Metric | Reactive | Predictive | Improvement |
|--------|----------|------------|-------------|
| Scale-up latency (p95) | ___ s | ___ s | ___% |
| PSI breach duration (avg) | ___ s | ___ s | ___% |
| PSI breach count | ___ | ___ | ___% |
| False positives | N/A | ___ | ___ |
| Total pod-hours | ___ | ___ | ___% |
| Pod-hour efficiency | baseline | ___ | ___% |

**Paper Results Table**: Use this data as the central validation results.

---

## Implementation Checklist

### Prerequisites (Phase 6 - DONE)
- [x] Prediction service running in shadow mode
- [x] Confirmation gate logic implemented
- [x] 100-200 spike events collected
- [x] Metrics validated (precision/recall/F1)

### Phase 8.1 (Week 1)
- [ ] Add Prometheus metric export to prediction service
- [ ] Deploy updated prediction service
- [ ] Install Prometheus Adapter
- [ ] Configure custom metrics
- [ ] Verify metrics: `kubectl get --raw /apis/custom.metrics.k8s.io/v1beta1`

### Phase 8.2 (Week 2)
- [ ] Deploy 10% pods with predictive HPA
- [ ] Monitor for 7 days
- [ ] Validate success criteria

### Phase 8.3 (Week 3)
- [ ] Scale to 50% pods with predictive HPA
- [ ] Monitor for 7 days
- [ ] Check for flapping

### Phase 8.4 (Week 4)
- [ ] Full rollout (100%)
- [ ] Production stability confirmed

### Phase 9 (Week 5)
- [ ] Run comparative experiment (reactive vs predictive)
- [ ] Collect all metrics
- [ ] Generate paper results table

---

## Files to Create

1. `prediction-service-deployment.yaml` - Updated with metrics endpoint
2. `prediction-service-prometheus.yaml` - ServiceMonitor for Prometheus
3. `custom-metrics-config.yaml` - Prometheus Adapter rules
4. `workload-predictive-hpa.yaml` - Predictive HPA config
5. `workload-reactive-hpa.yaml` - Baseline reactive HPA
6. `grafana-dashboard.json` - Comparison dashboard
7. `phase9-experiment-runner.sh` - Automated A/B test script

---

## Next Steps

1. **Let Phase 6 collection run to completion** (100-200 spikes)
2. **Stop collection and analyze** with `apply-confirmation-gate.py`
3. **Review precision/recall metrics** - ensure gate improves precision
4. **Begin Phase 8.1** - Add Prometheus export to prediction service
5. **Follow controlled rollout** - 10% → 50% → 100%
6. **Run Phase 9 comparison** - Final validation experiment
