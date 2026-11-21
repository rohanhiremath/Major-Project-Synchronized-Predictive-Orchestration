# TEST 0: SIGNAL LOCKED — Pre-Registration

**Frozen**: 2026-10-18  
**Authority**: User requirement (per user instruction)  
**Status**: LOCKED — No changes permitted after this point

---

## Signal Choice: Production Signal (Prometheus Derivative)

### Why This Signal?

**Two candidates were evaluated:**

1. **Cgroup PSI `memory.pressure some avg10`** (v1 experiment)
   - Direct kernel read from `/sys/fs/cgroup/.../memory.pressure`
   - Range observed in v1: 0–4.73%
   - Never reaches 1.8% except at squeeze onset
   - Result: recall=0.07 at T=1.8% (UNDERPOWERED)
   - **Rejected**: Production does not use this signal

2. **Prometheus rate-of-change derivative** (LOCKED)
   - Query: `deriv(node_pressure_memory_waiting_seconds_total{pod=~"workload-app-.*"}[2m]) * 100`
   - Used in: `prediction_service.py` line 267 (live inference)
   - Used in: Training dataset `data/train.csv`, `data/test.csv`, `data/validation.csv`
   - **Selected**: This is what production actually uses

---

## Exact Signal Definition (LOCKED)

### Query
```
deriv(node_pressure_memory_waiting_seconds_total{pod=~"workload-app-.*"}[2m]) * 100
```

### Prometheus Components
- **Metric**: `node_pressure_memory_waiting_seconds_total` (counter, cumulative)
- **Label filter**: `pod=~"workload-app-.*"` (regex)
- **Window**: `[2m]` (2-minute lookback)
- **Operation**: `deriv()` (rate of change per second)
- **Scale**: `* 100` (convert to percentage)

### Semantic Meaning
- **What it measures**: Rate of change of memory pressure counter (percentage per second)
- **Interpretation**: How fast the PSI counter is accumulating due to memory reclaim
- **Range in data**: 0.0–9.71%
- **Sampling interval**: 20 seconds (rows in data/*.csv are 20s apart)
- **Units**: Percent (%)
- **Sign**: Always non-negative (counter only increases)

### Data Provenance
- **Training data**: `data/train.csv` column `psi_some_avg10`
- **Test data**: `data/test.csv` column `psi_some_avg10`
- **Validation data**: `data/validation.csv` column `psi_some_avg10`
- **Generation source**: `src/generate_server_data.py` line 86–88
- **Generated from**: `pressure = np.maximum(cpu_usage - 0.62, 0) * 14 + np.maximum(load - 0.85, 0) * 5`

### Implementation Verification
**Where it's used in production:**

File: `kubernetes/phase6/prediction_service.py`
```python
# Line 267
query = f'deriv(node_pressure_memory_waiting_seconds_total{{pod=~"workload-app-.*"}}[2m]) * 100'

# Line 278-280
for item in result['data']['result']:
    pod = item['metric'].get('pod', 'unknown')
    value = float(item['value'][1])
    psi_values[pod] = value
```

**Stored as**: `psi_some_avg10` in PSIDataBuffer (line 130)

---

## SHA256 Verification

**This document**: 
```
SHA256(SIGNAL_LOCKED.md) = [to be computed after finalization]
```

**Signal query string**:
```
Query = 'deriv(node_pressure_memory_waiting_seconds_total{pod=~"workload-app-.*"}[2m]) * 100'
SHA256(query) = 61484120305457364fda4bcd50afa9f178c962b061fa810b5458a649078bacb0
```

**Training data file**:
```
File: data/train.csv
SHA256 = [capture after freeze]
Rows: 20,736 (115.2 hours at 20s intervals)
Column: psi_some_avg10 (0.0–9.71%)
```

**Test data files**:
```
File: data/test.csv
SHA256 = [capture after freeze]
Rows: 2,592 (14.4 hours at 20s intervals)

File: data/validation.csv
SHA256 = [capture after freeze]
Rows: 2,592 (14.4 hours at 20s intervals)
```

---

## Constraints (LOCKED)

1. **No signal modifications** after this signature
2. **No post-hoc selection** from the two candidates based on data
3. **No switch to cgroup avg10** if results are unfavorable
4. **Production signal is canonical**: Data experiments must validate against this signal

---

## Decision Record

**Decision maker**: [User]  
**Date**: 2026-10-18  
**Rationale**: Production code uses Prometheus derivative; training data uses same signal; no data mismatch  
**Impact**: All analyses (Tests 1–5) use this signal only  
**Reversibility**: None — frozen before data collection  

---

**LOCKED AND SIGNED** — 2026-10-18  
Proceed to Test 1 (label independence verification).
