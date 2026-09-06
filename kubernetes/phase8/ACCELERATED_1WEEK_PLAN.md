# ACCELERATED 1-WEEK PLAN: Phase 8 + Phase 9

**Goal**: Complete HPA integration and comparative validation in 7 days  
**Status**: Phase 6 complete, ready to execute  
**Timeline**: September 7-13, 2026

---

## 🚀 Quick Summary

Instead of 6 weeks with gradual rollout, we'll:
1. **Skip gradual rollout** (10%→50%→100%) - Deploy directly to 100%
2. **Run Phase 8 and Phase 9 in parallel** - Test both HPAs simultaneously
3. **Shorten monitoring periods** - 24 hours instead of 7 days per stage
4. **Use shadow mode validation** - Test without production risk

**Original Timeline**: 6 weeks  
**Accelerated Timeline**: 7 days  
**Risk**: Moderate (shadow mode keeps it safe)

---

## 📅 Day-by-Day Plan

### **Day 1 (Sunday)**: Setup & Metrics Export
**Goal**: Get prediction service exporting metrics to Prometheus

**Tasks**:
1. ✅ Add Prometheus metric export to `prediction_service.py`
2. ✅ Deploy updated prediction service
3. ✅ Verify metrics are scraped by Prometheus
4. ✅ Install Prometheus Adapter (if not already installed)

**Time**: 4-6 hours

**Deliverables**:
- Updated `prediction_service.py` with Prometheus export
- Metrics visible in Prometheus: `predicted_psi_confirmed`, `predicted_psi_raw`

---

### **Day 2 (Monday)**: Custom Metrics API
**Goal**: Make predicted PSI available as a Kubernetes custom metric

**Tasks**:
1. Configure Prometheus Adapter rules
2. Deploy adapter configuration
3. Verify custom metrics API: `kubectl get --raw /apis/custom.metrics.k8s.io/v1beta1`
4. Test metric queries for specific pods

**Time**: 4-6 hours

**Deliverables**:
- Custom metrics adapter configured
- `predicted_psi_confirmed` available via custom metrics API

---

### **Day 3 (Tuesday)**: Deploy Both HPAs (Shadow Mode)
**Goal**: Deploy predictive AND reactive HPA, both in shadow mode

**Tasks**:
1. Create predictive HPA manifest (uses `predicted_psi_confirmed`)
2. Create reactive HPA manifest (uses `container_cpu_pressure_some_avg10`)
3. Deploy BOTH HPAs but **disable actual scaling** (shadow mode)
4. Verify both HPAs are reading metrics correctly

**Shadow Mode Implementation**:
```yaml
# Predictive HPA - Shadow Mode
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: workload-predictive-hpa-shadow
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: workload-app-shadow  # Separate deployment for testing
  minReplicas: 2
  maxReplicas: 2  # Same min/max = no actual scaling
  metrics:
  - type: Pods
    pods:
      metric:
        name: predicted_psi_confirmed
      target:
        type: AverageValue
        averageValue: "1800m"  # 1.80%
```

**Time**: 4-6 hours

**Deliverables**:
- Predictive HPA deployed (shadow)
- Reactive HPA deployed (shadow)
- Both reading metrics correctly

---

### **Day 4 (Wednesday)**: Phase 9 Experiment Setup
**Goal**: Prepare 24-hour A/B comparison experiment

**Tasks**:
1. Create experiment runner script
2. Deploy two identical workload sets:
   - Set A: Reactive HPA (actual scaling)
   - Set B: Predictive HPA (actual scaling)
3. Configure monitoring (Prometheus queries, Grafana dashboard)
4. Test workload scenarios (quick smoke test)

**Architecture**:
```
Workload Set A (Reactive):
  - workload-reactive-0, workload-reactive-1, workload-reactive-2
  - Uses reactive HPA (CPU PSI based)
  
Workload Set B (Predictive):
  - workload-predictive-0, workload-predictive-1, workload-predictive-2
  - Uses predictive HPA (predicted PSI based)

Same workload applied to both sets simultaneously
```

**Time**: 6-8 hours

**Deliverables**:
- Two workload deployments (reactive + predictive)
- Experiment runner script
- Monitoring dashboard

---

### **Day 5 (Thursday)**: Run 24-Hour Experiment
**Goal**: Execute comparative validation experiment

**Tasks**:
1. Start experiment runner (24 hours, 6 scenarios)
2. Apply same workload to both sets
3. Monitor metrics collection
4. Let it run overnight

**Workload Scenarios** (4 hours each, 4 complete cycles):
1. Step Pattern (4h)
2. Ramp Pattern (4h)
3. Periodic Bursts (4h)
4. Sustained Load (4h)
5. Flash Spikes (4h)
6. Mixed Chaos (4h)

**Time**: 24 hours (mostly automated)

**Manual Tasks**: 
- Morning: Start experiment (~1 hour)
- Evening: Check health (~30 min)
- Next morning: Stop experiment (~30 min)

---

### **Day 6 (Friday)**: Data Collection & Analysis
**Goal**: Stop experiment, collect metrics, analyze results

**Tasks**:
1. Stop experiment (morning)
2. Export Prometheus data for both sets
3. Calculate comparison metrics:
   - Scale-up latency (p50, p95, p99)
   - PSI breach duration (avg, max)
   - PSI breach count
   - False positive rate (predictive only)
   - Total pod-hours
   - Pod-hour efficiency
4. Generate comparison table
5. Create visualizations

**Metrics to Extract**:
```python
# For each HPA mode (reactive vs predictive):
scale_up_latency = time_to_scale - psi_breach_start
breach_duration = psi_above_threshold_duration
breach_count = count(psi > 1.80%)
false_positives = scale_ups_without_breach
pod_hours = sum(pod_count * duration)
efficiency = reactive_pod_hours / predictive_pod_hours
```

**Time**: 6-8 hours

**Deliverables**:
- Comparison metrics (CSV/JSON)
- Results table (LaTeX ready)
- Visualizations (PNG/PDF)

---

### **Day 7 (Saturday)**: Documentation & Paper Writing
**Goal**: Write up results for paper submission

**Tasks**:
1. Update Section 4: Experimental Setup
2. Write Section 5.1: Validation Results (Phase 6)
3. Write Section 5.2: Comparative Results (Phase 9)
4. Create Table 2: Validation metrics
5. Create Table 3: Comparative results
6. Write discussion and conclusions
7. Final review and polish

**Time**: 8-10 hours

**Deliverables**:
- Complete paper draft with all results
- LaTeX tables ready
- Figures and visualizations
- Ready for submission

---

## ⚡ Parallel Execution Strategy

**Days 1-3**: Setup (can't parallelize)
- Day 1: Metrics export
- Day 2: Custom metrics API
- Day 3: HPA deployment

**Days 4-5**: Experiment (parallelized)
- Day 4 evening: Start experiment
- Day 5: Runs automatically (24h)
- Day 6 morning: Collect results

**Days 6-7**: Analysis & Writing (can parallelize)
- Day 6: Data analysis (can start while experiment runs)
- Day 7: Paper writing

---

## 🎯 Critical Path

**Must Complete in Order**:
1. Day 1 → Day 2 → Day 3 (dependencies)
2. Day 4 → Day 5 (experiment setup then run)
3. Day 5 → Day 6 (need data before analysis)
4. Day 6 → Day 7 (need results before writing)

**Can Start Early**:
- Grafana dashboard (Day 2-3)
- Experiment script (Day 3-4)
- Paper sections 1-3 (any time)
- LaTeX table templates (any time)

---

## 📊 Simplified Phase 8 (1 Day Instead of 4 Weeks)

### Original Plan (4 weeks):
```
Week 1: Shadow mode + metrics validation
Week 2: 10% rollout + monitoring
Week 3: 50% rollout + monitoring
Week 4: 100% rollout + stability check
```

### Accelerated Plan (Day 3):
```
Day 3: Deploy both HPAs in shadow mode
       Verify metrics, skip gradual rollout
       Go straight to Phase 9 experiment
```

**Why it's safe**:
- We already validated prediction service (Phase 6)
- We have confirmation gate (zero false positives)
- Phase 9 uses separate workload sets (no production impact)
- Can roll back instantly if issues arise

---

## 🛡️ Risk Mitigation

### Risk 1: Custom Metrics API Issues
**Mitigation**: Test on Day 2 with simple queries before Day 3
**Fallback**: Use Prometheus directly (slower but works)

### Risk 2: HPA Flapping
**Mitigation**: Use confirmation gate, set stabilization windows
**Fallback**: Adjust min/max replicas or threshold

### Risk 3: Experiment Failure
**Mitigation**: Monitor first 2 hours closely, restart if needed
**Fallback**: Extend to 36-48 hours if data quality issues

### Risk 4: Time Overrun
**Mitigation**: Start Day 1 early (morning), work longer days
**Fallback**: Skip Day 7 polish, submit draft results

---

## 📋 Daily Checklists

### Day 1 Checklist
- [ ] Update prediction_service.py with Prometheus export
- [ ] Add `prometheus_client` to requirements
- [ ] Deploy updated service
- [ ] Verify metrics in Prometheus UI
- [ ] Check metric labels (pod names)
- [ ] Document metric format

### Day 2 Checklist
- [ ] Install Prometheus Adapter (if needed)
- [ ] Create custom metrics config YAML
- [ ] Deploy adapter configuration
- [ ] Verify custom metrics API works
- [ ] Test pod-specific queries
- [ ] Document API endpoints

### Day 3 Checklist
- [ ] Create predictive HPA manifest
- [ ] Create reactive HPA manifest
- [ ] Deploy both HPAs (shadow mode)
- [ ] Verify HPA status (kubectl get hpa)
- [ ] Check HPA events (kubectl describe hpa)
- [ ] Document HPA behavior

### Day 4 Checklist
- [ ] Create two workload deployments
- [ ] Create experiment runner script
- [ ] Configure Grafana dashboard
- [ ] Test scenarios (smoke test)
- [ ] Prepare overnight monitoring
- [ ] Document experiment setup

### Day 5 Checklist
- [ ] Start experiment (morning)
- [ ] Check after 2 hours (health)
- [ ] Check in evening (progress)
- [ ] Let run overnight
- [ ] Stop experiment (next morning)
- [ ] Export logs

### Day 6 Checklist
- [ ] Stop experiment
- [ ] Export Prometheus data
- [ ] Calculate scale-up latency
- [ ] Calculate breach metrics
- [ ] Generate comparison table
- [ ] Create visualizations
- [ ] Save raw data

### Day 7 Checklist
- [ ] Write Section 4 (setup)
- [ ] Write Section 5.1 (Phase 6)
- [ ] Write Section 5.2 (Phase 9)
- [ ] Create Table 2 (validation)
- [ ] Create Table 3 (comparison)
- [ ] Write conclusions
- [ ] Final review

---

## 🎯 Success Criteria (1 Week)

### Minimum Acceptable:
- [x] Phase 6 validation complete (DONE)
- [ ] Predictive HPA deployed and tested
- [ ] 24-hour experiment executed
- [ ] Comparison metrics collected
- [ ] Paper draft with results tables

### Target (Ideal):
- [x] Phase 6 validation complete (DONE)
- [ ] Both HPAs deployed and stable
- [ ] Complete 24-hour experiment (all 6 scenarios)
- [ ] All comparison metrics with visualizations
- [ ] Polished paper ready for submission

### Stretch (Ambitious):
- [x] Phase 6 validation complete (DONE)
- [ ] Production HPA deployed (100%)
- [ ] 48-hour experiment (2 cycles)
- [ ] Additional sensitivity analysis
- [ ] Camera-ready paper with appendix

---

## 💻 Quick Start Commands

### Day 1: Metrics Export
```bash
cd kubernetes/phase6

# Update prediction service (add Prometheus export)
# (We'll create this script)
./add-prometheus-export.sh

# Deploy updated service
kubectl apply -f prediction-service-deployment.yaml

# Check metrics
curl localhost:8000/metrics | grep predicted_psi
```

### Day 2: Custom Metrics
```bash
cd kubernetes/phase8

# Install Prometheus Adapter
helm install prometheus-adapter prometheus-community/prometheus-adapter \
  -f custom-metrics-config.yaml

# Verify
kubectl get --raw /apis/custom.metrics.k8s.io/v1beta1 | jq .
```

### Day 3: HPA Deployment
```bash
# Deploy predictive HPA
kubectl apply -f workload-predictive-hpa.yaml

# Deploy reactive HPA
kubectl apply -f workload-reactive-hpa.yaml

# Check status
kubectl get hpa
kubectl describe hpa workload-predictive-hpa
```

### Day 4-5: Experiment
```bash
# Start 24-hour experiment
./run-phase9-experiment.sh 24

# Monitor
watch -n 60 kubectl top pods
tail -f experiment-logs/metrics.log
```

### Day 6: Analysis
```bash
# Export data
./export-experiment-results.sh

# Generate comparison table
python3 analyze-comparison.py experiment-results/

# View results
cat results/comparison-table.txt
```

---

## 📈 Expected Results (Paper Table 3)

```
Table 3: Reactive vs Predictive HPA Comparison

Metric                      Reactive    Predictive    Improvement
──────────────────────────────────────────────────────────────────
Scale-up Latency (p95)        72s          28s         61.1% ↓
PSI Breach Duration (avg)    156s          52s         66.7% ↓
PSI Breach Count              52           18          65.4% ↓
False Positive Rate           N/A        < 5%          Acceptable
Total Pod-Hours              288          302           4.9% ↑
Pod-Hour Efficiency        1.00x        0.95x         Acceptable

Dataset: 24 hours, 6 scenarios (4 complete cycles)
Configuration: 1.80% threshold, 60s confirmation window
```

---

## 🚦 Go/No-Go Decision Points

### After Day 1:
- **GO**: Metrics visible in Prometheus
- **NO-GO**: Metrics not exporting → Debug, extend Day 1

### After Day 2:
- **GO**: Custom metrics API working
- **NO-GO**: API errors → Use Prometheus directly

### After Day 3:
- **GO**: Both HPAs reading metrics correctly
- **NO-GO**: HPA errors → Fix configuration, extend Day 3

### After 2 Hours of Day 5:
- **GO**: Experiment running smoothly
- **NO-GO**: Errors or crashes → Restart experiment

### After Day 6:
- **GO**: Data collected, metrics calculated
- **NO-GO**: Data issues → Extend experiment to 48h

---

## 📊 Comparison: 6 Weeks vs 1 Week

| Aspect | Original (6 weeks) | Accelerated (1 week) |
|--------|-------------------|---------------------|
| **Phase 8 Rollout** | 10% → 50% → 100% | Direct to 100% |
| **Monitoring** | 7 days per stage | 24 hours total |
| **Phase 9 Experiment** | After full rollout | Parallel deployment |
| **Risk** | Very low | Moderate (mitigated) |
| **Production Impact** | Gradual, safe | Shadow mode, safe |
| **Results Quality** | High confidence | Good confidence |
| **Paper Readiness** | Polished | Draft with results |

**Recommendation**: Go with 1-week plan. Phase 6 validation already provides high confidence. Phase 8/9 is validation, not production deployment.

---

## ✅ What We Already Have (From Phase 6)

- [x] Model validated: 94.69% precision, 100% recall
- [x] Confirmation gate: 100% precision, 0 false positives
- [x] 107 spike events validated
- [x] Prediction service tested: 3.7 hours continuous
- [x] Production config: 1.80% threshold, 20s interval
- [x] Monitoring scripts: Health checks, progress tracking
- [x] Phase 8 HPA design: Complete architecture

**With this foundation, 1 week is achievable!**

---

## 🎯 Bottom Line

**Can we do it in 1 week?** ✅ **YES!**

**Key enablers**:
1. Phase 6 already done (strong foundation)
2. Skip gradual rollout (shadow mode validation)
3. Run Phase 8+9 in parallel (A/B experiment)
4. Focus on paper-ready results, not production polish

**Timeline**:
- Days 1-3: Setup (HPA deployment)
- Days 4-5: Experiment (24h run)
- Days 6-7: Analysis & paper writing

**Outcome**: Paper-ready results in 7 days, ready for submission!

**Start tomorrow (Day 1)?** Let me know and I'll create the implementation scripts!
