# PSI Units and Delta PSI (ΔΨ) Clarification

## Key Point

**PSI values in the synthetic dataset are in PERCENTAGE form (%)**, not raw fractions.

- **psi_io_some_avg10** = 0–10% (typical range)
- **ΔΨ (Delta PSI)** = change between 15s samples ≈ ±1.8%
- **Spike threshold** = 2.0% (latency risk begins)

---

## PSI Definition

From Linux kernel (`/proc/pressure/io`):

```
psi_io_some = (time_stalled_on_io / total_time) × 100  [%]
```

### Examples

| PSI Value | Meaning |
|-----------|---------|
| 0.0–0.5% | Calm baseline |
| 1.0–1.5% | Light I/O contention (normal) |
| **1.8%** | Typical ΔΨ magnitude per 15s sample |
| **2.0%** | Spike threshold → latency degradation risk |
| 3.0–5.0% | Heavy I/O stall |
| 5.0%+ | Severe bottleneck |

---

## Delta PSI (ΔΨ)

**ΔΨ is the change in PSI between consecutive timesteps:**

```
ΔΨ[t] = psi_io_some_avg10[t] - psi_io_some_avg10[t-1]
```

**Why ≈ ±1.8%?**
1. Baseline noise: ±0.1–0.3% per sample
2. Event ramps: +0.5–2.0% per sample during onset
3. EWMA smoothing reduces variability
4. Typical spike rise: 0→2% in 30–60s = ~0.5–1.8% per sample

---

## Example Timeline

```
Time            PSI (%)   ΔΨ (%)    Status
00:00:00        0.12      —         Baseline
00:00:15        0.15     +0.03      Normal
00:00:30        0.18     +0.03      Normal
00:00:45        0.52     +0.34      Load begins
00:01:00        1.08     +0.56      Load increasing
00:01:15        1.64     +0.56      Approaching threshold
00:01:30        2.20     +0.56      ⚠️ SPIKE (>2.0%)
00:01:45        2.85     +0.65      Peak
00:02:00        2.40     -0.45      Decay
00:02:15        1.92     -0.48      Below threshold
00:02:30        1.35     -0.57      Return to baseline
```

---

## Reference: Validation Study

**T = 1.8%** threshold (from SYNTHETIC_VALIDATION_WITH_FINDINGS.md):
- Not the PSI value, but the **optimal detection threshold**
- Achieved 83% recall with 1.5 false alarms/hour
- Balances catching spikes vs. nuisance alerts

**Spike threshold = 2.0%** in this dataset:
- Intentionally higher for clear separation
- Ensures realistic model learning
- Consistent with latency degradation onset

---

## Files & Documentation

- **README.md** - Overview, usage, quick reference
- **PSI_CLARIFICATION.md** - This file (units and ΔΨ)
- **metadata.json** - Column roles, statistics
- **generate_psi_7d.py** - Updated docstrings explaining PSI %

---

**Summary:** PSI ∈ [0–10%], ΔΨ ≈ ±1.8%, Spike threshold = 2.0%
