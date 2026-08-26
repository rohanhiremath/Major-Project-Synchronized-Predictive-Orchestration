# Prometheus Queries for PSI Metrics

## Access Prometheus

```bash
# Port-forward to Prometheus
kubectl port-forward -n monitoring svc/kube-prometheus-stack-prometheus 9090:9090

# Open browser: http://localhost:9090
```

---

## Core PSI Metrics

### Memory Pressure (Stalled)
```promql
# Rate of memory stall time (percentage, 0-100)
rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m]) * 100

# Average across all workload pods
avg(rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m])) * 100

# Per-pod breakdown
rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m]) * 100
```

### Memory Pressure (Some waiting)
```promql
# Rate of memory wait time (percentage)
rate(node_pressure_memory_waiting_seconds_total{pod=~"workload-.*"}[1m]) * 100
```

### CPU Pressure
```promql
# CPU stall rate
rate(node_pressure_cpu_stalled_seconds_total{pod=~"workload-.*"}[1m]) * 100

# CPU wait rate
rate(node_pressure_cpu_waiting_seconds_total{pod=~"workload-.*"}[1m]) * 100
```

### I/O Pressure
```promql
# I/O stall rate
rate(node_pressure_io_stalled_seconds_total{pod=~"workload-.*"}[1m]) * 100

# I/O wait rate
rate(node_pressure_io_waiting_seconds_total{pod=~"workload-.*"}[1m]) * 100
```

---

## Training Data Format Queries

These match the format used for model training:

### PSI Full (avg10, avg60, avg300)
```promql
# 10-second average (instant vector)
node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}

# Calculate 10s, 60s, 300s rolling averages
rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[10s]) * 100
rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m]) * 100
rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[5m]) * 100
```

### Combined Dashboard Query
```promql
# All PSI metrics in one graph (memory focus)
{
  rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m]) * 100,
  rate(node_pressure_memory_waiting_seconds_total{pod=~"workload-.*"}[1m]) * 100,
  rate(node_pressure_cpu_stalled_seconds_total{pod=~"workload-.*"}[1m]) * 100,
  rate(node_pressure_io_stalled_seconds_total{pod=~"workload-.*"}[1m]) * 100
}
```

---

## Spike Detection Queries

Based on model threshold=1.5:

### Spike Alert (PSI Full > 1.5%)
```promql
# Current spikes
rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m]) * 100 > 1.5

# Count spikes in last hour
count_over_time((rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m]) * 100 > 1.5)[1h:20s])

# Percentage of time in spike state (last 5 minutes)
(count_over_time((rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m]) * 100 > 1.5)[5m:20s]) / count_over_time(up{pod=~"workload-.*"}[5m:20s])) * 100
```

### Derivative-based Spike Detection
```promql
# Rate of change (derivative approximation)
deriv(rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m])[5m:])

# Spike if derivative > 0.1 per second
deriv(rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m])[5m:]) > 0.1
```

---

## Resource Usage Queries

### CPU Usage
```promql
# Per pod
rate(container_cpu_usage_seconds_total{pod=~"workload-.*", container="app"}[1m]) * 100

# Average across pods
avg(rate(container_cpu_usage_seconds_total{pod=~"workload-.*", container="app"}[1m])) * 100
```

### Memory Usage
```promql
# Current memory (bytes)
container_memory_usage_bytes{pod=~"workload-.*", container="app"}

# Memory as percentage of limit
(container_memory_usage_bytes{pod=~"workload-.*", container="app"} / container_spec_memory_limit_bytes{pod=~"workload-.*", container="app"}) * 100
```

### Network I/O
```promql
# Receive rate (bytes/sec)
rate(container_network_receive_bytes_total{pod=~"workload-.*"}[1m])

# Transmit rate (bytes/sec)
rate(container_network_transmit_bytes_total{pod=~"workload-.*"}[1m])
```

---

## Model Validation Queries

### Compare Actual vs Predicted Spikes

Once you collect real data, compare with model predictions:

```promql
# Actual spike rate (ground truth)
count_over_time((rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m]) * 100 > 1.5)[1h:20s])

# Later: join with model predictions from predictive-hpa controller
# (This will be implemented in Phase 8)
```

### 94.65% Recall Validation
```promql
# True positives: actual spikes that model predicted
# (Requires model prediction time series - Phase 8)

# False negatives: actual spikes that model missed
# Expected: ~5.35% of actual spikes (100 - 94.65)
```

---

## Alerting Rules (for later)

### High PSI Alert
```yaml
alert: HighMemoryPressure
expr: rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m]) * 100 > 5
for: 1m
labels:
  severity: warning
annotations:
  summary: "High memory pressure on {{ $labels.pod }}"
  description: "PSI full > 5% for 1 minute"
```

### Predicted Spike Alert (Phase 8)
```yaml
alert: PredictedMemorySpike
expr: predictive_hpa_spike_forecast{pod=~"workload-.*"} > 0.8
for: 0m
labels:
  severity: info
annotations:
  summary: "Memory spike predicted for {{ $labels.pod }}"
  description: "TFT model predicts spike with {{ $value }} probability"
```

---

## Grafana Dashboard Panels

### Panel 1: PSI Overview (Time Series)
- Query: `rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m]) * 100`
- Legend: `{{ pod }}`
- Y-axis: PSI Full (%)
- Thresholds: Warning 1.5%, Critical 5%

### Panel 2: PSI Heatmap
- Query: `rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m]) * 100`
- Visualization: Heatmap
- Time grain: 20s (matches scrape interval)

### Panel 3: Spike Count (Stat)
- Query: `count_over_time((rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m]) * 100 > 1.5)[1h:20s])`
- Visualization: Stat
- Title: "Spikes in Last Hour (threshold=1.5%)"

### Panel 4: Resource Usage (Time Series)
- CPU: `rate(container_cpu_usage_seconds_total{pod=~"workload-.*", container="app"}[1m]) * 100`
- Memory: `container_memory_usage_bytes{pod=~"workload-.*", container="app"} / 1024 / 1024`
- Dual Y-axis

---

## CLI Query Examples

```bash
# Get Prometheus pod
PROM_POD=$(kubectl get pods -n monitoring -l app.kubernetes.io/name=prometheus -o jsonpath='{.items[0].metadata.name}')

# Query current PSI
kubectl exec -n monitoring $PROM_POD -c prometheus -- \
  wget -qO- 'http://localhost:9090/api/v1/query?query=rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m])*100' | \
  python3 -m json.tool

# Query spike count
kubectl exec -n monitoring $PROM_POD -c prometheus -- \
  wget -qO- 'http://localhost:9090/api/v1/query?query=count_over_time((rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m])*100>1.5)[1h:20s])' | \
  python3 -m json.tool

# Range query (last 5 minutes)
kubectl exec -n monitoring $PROM_POD -c prometheus -- \
  wget -qO- 'http://localhost:9090/api/v1/query_range?query=rate(node_pressure_memory_stalled_seconds_total{pod=~"workload-.*"}[1m])*100&start='$(date -u -d '5 minutes ago' +%s)'&end='$(date -u +%s)'&step=20s' | \
  python3 -m json.tool
```

---

## Expected Values

**Idle System:**
- PSI Full: 0.0% - 0.5%
- PSI Some: 0.0% - 1.0%
- No spikes above 1.5% threshold

**Under Load (synthetic workloads in Phase 4):**
- PSI Full: 0.5% - 10%+
- Spikes: 10-20% of time above 1.5%
- Should match training data distribution (12.78% train, 16.51% test spike density)

**Model Training Data Context:**
- Threshold: 1.5%
- Spike definition: PSI Full avg10 > 1.5%
- Training spike density: 12.78%
- Test spike density: 16.51%
- Model recall at threshold=1.5: 94.65%

---

## Next Steps

1. **Phase 3:** Confirm 20s scrape interval is working
2. **Phase 4:** Generate synthetic workloads and validate spike detection
3. **Phase 5:** Compare real Kubernetes PSI with synthetic training data
4. **Phase 8:** Export model predictions as Prometheus metrics for validation
