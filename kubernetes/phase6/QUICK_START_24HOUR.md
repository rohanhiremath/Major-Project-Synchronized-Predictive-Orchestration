# Quick Start: 24-Hour Test

**Goal**: Get 50+ spikes for paper submission in 24 hours

---

## ⚡ One-Command Start

```bash
cd /home/kesavan-p/Documents/major\ project/implementation/Major-Project-Synchronized-Predictive-Orchestration/kubernetes/phase6

# Test spike generation (1 minute)
./test-spike-generation.sh

# If test passes, start 24-hour test
./run-24hour-test.sh
```

**That's it!** Test will run for 24 hours automatically.

---

## 📊 Monitor Progress (Optional)

In a **separate terminal**:

```bash
cd /home/kesavan-p/Documents/major\ project/implementation/Major-Project-Synchronized-Predictive-Orchestration/kubernetes/phase6

./monitor-24hour-test.sh
```

Press Ctrl+C to stop monitoring (test continues).

---

## 📁 Results

After 24 hours, find results in:
```
kubernetes/phase6/test-results-YYYYMMDD_HHMMSS/
```

Analyze results:
```bash
./analyze-results.py test-results-YYYYMMDD_HHMMSS/
```

---

## 🎯 Expected Results

- **Predictions**: ~4,320 (one every 20 seconds)
- **Spikes**: 50-180 
- **Precision**: >90%
- **Recall**: >95%
- **Duration**: 24 hours

---

## 🆘 If Something Goes Wrong

**Test stopped?**
```bash
# Check logs
ls -lt test-results-*/
tail -100 test-results-LATEST/test-execution.log
```

**No spikes?**
```bash
# Verify Prometheus has PSI data
kubectl port-forward -n monitoring svc/prometheus-operated 9090:9090 &
curl 'http://localhost:9090/api/v1/query?query=node_pressure_memory_waiting_seconds_total'
```

**Service crashed?**
- Auto-restarts automatically
- Check: `tail -100 test-results-LATEST/prediction-service.log`

---

## ✅ Pre-Flight Checklist

- [ ] Workload pods running: `kubectl get pods -l app=workload`
- [ ] Prometheus accessible: `kubectl get -n monitoring svc/prometheus-operated`
- [ ] Model exists: `ls models/tft_psi_model.ckpt`
- [ ] Venv works: `.venv/bin/python --version`
- [ ] 5GB+ disk space: `df -h .`

---

## 📞 Need Help?

See detailed guide: `24HOUR_TEST_GUIDE.md`

---

**Ready? Run the test!** 🚀

```bash
./run-24hour-test.sh
```
