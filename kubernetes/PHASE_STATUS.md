# Kubernetes Deployment Phases - Status Tracker

## Project: Predictive HPA using PSI Metrics
**Model:** TFT-PSI Improved (94.65% recall, threshold=1.5%)

---

## ✅ Phase 1: Prerequisites (COMPLETE)

**Status:** Completed before project started

- ✅ Kubernetes cluster installed (kind/minikube)
- ✅ Prometheus Operator deployed via Helm
- ✅ Grafana configured
- ✅ Node-exporter running
- ✅ PSI kernel support verified

---

## ✅ Phase 2: Workload Deployment (COMPLETE)

**Status:** Deployed and verified on Aug 26, 2026

**Deployed Components:**
- ✅ StatefulSet: `workload-app` (3 replicas)
- ✅ Storage: 6 PVCs (21Gi total)
- ✅ Services: Headless + NodePort
- ✅ ServiceMonitor: 20s scrape interval
- ✅ PSI Metrics: All 6 types exposed

**Verification Results:**
- 3/3 pods running (2/2 containers ready)
- Prometheus scraping all targets at 20s intervals
- PSI metrics available: memory, CPU, I/O (stalled + waiting)
- Model metadata annotated on pods

**Files:**
- `phase2/workload-statefulset.yaml`
- `phase2/workload-service.yaml`
- `phase2/verify-phase2.sh`
- `phase2/COMMANDS.sh`
- `phase2/DEPLOY.md`
- `phase2/PROMETHEUS_QUERIES.md`
- `phase2/README.md`

**Commands to verify:**
```bash
kubectl get pods -l app=workload
kubectl get pvc | grep workload
kubectl get servicemonitor workload-psi-monitor
```

---

## 🔄 Phase 3: Metrics Validation (IN PROGRESS)

**Status:** Scripts created, ready to run

**Objectives:**
- Validate 20s scrape interval consistency
- Check PSI metrics data quality
- Establish idle baseline (< 0.5% PSI expected)
- Create Grafana dashboard
- Test training data format queries
- Compare baseline with synthetic training data

**Files Created:**
- `phase3/README.md` - Complete guide
- `phase3/validate-metrics.sh` - Scrape interval and data quality checks
- `phase3/baseline-measurement.sh` - Collect idle PSI baseline
- `phase3/validate-all.sh` - Run all validation tasks
- `phase3/quick-test.sh` - Quick sanity check
- `phase3/create-dashboard.sh` - Deploy Grafana dashboard
- `phase3/grafana-dashboard.json` - Dashboard configuration

**Next Steps:**
1. Run quick test: `cd kubernetes/phase3 && ./quick-test.sh`
2. Run full validation: `./validate-all.sh`
3. Review baseline measurements
4. Import Grafana dashboard

**Success Criteria:**
- [ ] All 3 targets scraped consistently at 20s
- [ ] No data gaps in 10-minute window
- [ ] Idle PSI < 0.5% on all pods
- [ ] Grafana dashboard displays metrics
- [ ] Training queries compatible

---

## 📋 Phase 4: Synthetic Workload Generation (PLANNED)

**Status:** Not started

**Objectives:**
- Deploy fio for I/O stress
- Deploy stress-ng for CPU/memory stress
- Create spike patterns matching training data
- Target: 16.51% spike density (matching test set)
- Validate PSI metrics respond correctly

**Expected Activities:**
- Create workload generation DaemonSet/Jobs
- Implement spike pattern generator
- Monitor PSI spikes in Grafana
- Collect 1-2 hours of workload data

---

## 📋 Phase 5: Model Evaluation on Real Data (PLANNED)

**Status:** Not started

**Objectives:**
- Export Prometheus PSI data to CSV
- Match training data format
- Run model predictions on real Kubernetes data
- Compare predicted vs actual spikes
- Validate 94.65% recall holds on real data

**Expected Activities:**
- Create Prometheus→CSV export script
- Preprocess data to match training format
- Run `predict_tft_improved.py` on real data
- Generate evaluation report

---

## 📋 Phase 6: Predictive Scaling Logic (PLANNED)

**Status:** Not started

**Objectives:**
- Create decision service consuming model predictions
- Define scaling thresholds and cooldown periods
- Implement shadow mode (predict without scaling)
- Log all prediction/decision pairs

**Expected Activities:**
- Build prediction service (Python/Go)
- Deploy as Kubernetes Deployment
- Integrate with model checkpoint
- Create decision logging

---

## 📋 Phase 7: Shadow Mode Deployment (PLANNED)

**Status:** Not started

**Objectives:**
- Run predictive logic without actual scaling
- Compare what would happen vs what did happen
- Tune thresholds and cooldowns
- Validate recall/precision on live traffic

**Expected Activities:**
- Deploy decision service in shadow mode
- Monitor prediction accuracy
- Collect actuation recommendations
- Analyze performance

---

## 📋 Phase 8: HPA Integration (PLANNED)

**Status:** Not started

**Objectives:**
- Integrate with Kubernetes HPA custom metrics
- Expose model predictions as metrics
- Configure HPA to use predictive metrics
- Enable automatic scaling based on predictions

**Expected Activities:**
- Create custom metrics adapter
- Expose predictions via Prometheus
- Configure HPA with custom metrics
- Test end-to-end autoscaling

---

## 📋 Phase 9: Performance Comparison (PLANNED)

**Status:** Not started

**Objectives:**
- Compare reactive HPA vs predictive HPA
- Measure: latency reduction, resource efficiency, SLO compliance
- Generate performance report
- Document improvements

**Expected Activities:**
- Run A/B test (reactive vs predictive)
- Collect metrics: scaling time, resource waste, SLO violations
- Create comparison report
- Document findings

---

## 📊 Overall Progress

```
Phase 1: ████████████████████████████████ 100% COMPLETE
Phase 2: ████████████████████████████████ 100% COMPLETE
Phase 3: ████████░░░░░░░░░░░░░░░░░░░░░░░░  30% IN PROGRESS
Phase 4: ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   0% PLANNED
Phase 5: ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   0% PLANNED
Phase 6: ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   0% PLANNED
Phase 7: ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   0% PLANNED
Phase 8: ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   0% PLANNED
Phase 9: ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   0% PLANNED

Overall: ███████░░░░░░░░░░░░░░░░░░░░░░░░░  23% COMPLETE
```

---

## 🎯 Current Focus

**Active Phase:** Phase 3 - Metrics Validation

**Immediate Next Steps:**
1. Run `kubernetes/phase3/quick-test.sh` to verify setup
2. Run `kubernetes/phase3/validate-all.sh` for full validation
3. Review baseline measurements
4. Import Grafana dashboard
5. Complete Phase 3 checklist

**Blocked:** None

**Risks:** None identified

---

## 📚 Key Links

- **Model Checkpoint:** `models/tft_psi_model_improved.ckpt`
- **Training Data:** `data/ptcs_training_data_full_psi.csv`
- **Prediction Script:** `src/predict_tft_improved.py`
- **Phase 2 Docs:** `kubernetes/phase2/README.md`
- **Phase 3 Docs:** `kubernetes/phase3/README.md`

---

## 🔑 Key Metrics

- **Model Recall:** 94.65% (exceeds 90% automation gate ✅)
- **Model Precision:** 87.64%
- **F1 Score:** 91.01%
- **Threshold:** 1.5%
- **Training Spike Density:** 12.78%
- **Test Spike Density:** 16.51%

---

**Last Updated:** Aug 26, 2026 18:15 UTC
**Status:** Phase 2 complete, Phase 3 scripts ready
