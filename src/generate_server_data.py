"""Generate one day of multi-server telemetry at 20-second intervals."""

from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_FILE = PROJECT_ROOT / "data" / "server_telemetry_1day_20s.csv"

SEED = 42
SERVER_COUNT = 6
INTERVAL_SECONDS = 20
DAY_START = "2026-08-21 00:00:00"


def make_spike_profile(rng: np.random.Generator, points: int) -> np.ndarray:
    """Create traffic bursts with ramps and cooldowns throughout the day."""
    time = np.arange(points)
    profile = np.zeros(points, dtype=float)
    centers = np.array([360, 720, 1080, 1440, 1800, 2160, 2520, 2880, 3240, 3780, 4020, 4200])

    for center in centers:
        center += int(rng.integers(-18, 19))
        width = int(rng.integers(10, 19))
        amplitude = float(rng.uniform(0.8, 1.4))
        distance = np.abs(time - center)
        burst = np.exp(-0.5 * (distance / width) ** 2)
        # A bounded triangular ramp gives a lead-in without leaving the
        # server permanently saturated after the burst.
        lead_in = np.exp(-np.maximum(center - time, 0) / max(width * 1.5, 1))
        cooldown = np.exp(-np.maximum(time - center, 0) / max(width * 3, 1))
        ramp = lead_in * cooldown
        profile += amplitude * (0.35 * ramp + 0.65 * burst)

    return profile


def main() -> None:
    rng = np.random.default_rng(SEED)
    points = 24 * 60 * 60 // INTERVAL_SECONDS
    timestamps = pd.date_range(
        start=DAY_START,
        periods=points,
        freq=f"{INTERVAL_SECONDS}s",
    )
    minute = np.arange(points) * INTERVAL_SECONDS / 60
    day_fraction = minute / (24 * 60)

    # Daily workload plus repeatable, learnable traffic bursts.
    daily_cycle = 0.18 + 0.12 * np.sin(2 * np.pi * (day_fraction - 0.25))
    morning_ramp = 0.30 / (1 + np.exp(-(minute - 7 * 60) / 35))
    evening_falloff = 0.25 / (1 + np.exp((minute - 21 * 60) / 40))
    shared_load = np.clip(
        daily_cycle + morning_ramp + evening_falloff + make_spike_profile(rng, points),
        0,
        None,
    )

    frames = []
    for server_number in range(SERVER_COUNT):
        server_id = f"server_{server_number + 1:02d}"
        capacity = float(rng.uniform(0.85, 1.15))
        baseline = float(rng.uniform(0.75, 1.10))
        noise = rng.normal(0, 0.018, points)
        short_term = pd.Series(noise).rolling(5, min_periods=1).mean().to_numpy()
        load = np.clip(shared_load * baseline * (1 + short_term), 0, None)

        request_rate = np.clip(
            35 + 115 * load * capacity + rng.normal(0, 4, points),
            0,
            None,
        )
        active_connections = np.clip(
            25 + request_rate * 0.9 + rng.normal(0, 5, points),
            0,
            None,
        )
        cpu_usage = np.clip(
            0.08 + 0.62 * load + 0.0007 * request_rate + rng.normal(0, 0.015, points),
            0,
            1.0,
        )
        memory_usage = np.clip(
            1.2e9 + 1.7e9 * pd.Series(load).ewm(span=45, adjust=False).mean().to_numpy()
            + rng.normal(0, 2.0e7, points),
            0,
            None,
        )
        read_bytes = np.clip(request_rate * 18_000 + rng.normal(0, 3_000, points), 0, None)
        write_bytes = np.clip(request_rate * (28_000 + 8_000 * load) + rng.normal(0, 4_000, points), 0, None)

        # Pressure is nonlinear near saturation, which creates useful spikes.
        pressure = np.maximum(cpu_usage - 0.62, 0) * 14 + np.maximum(load - 0.85, 0) * 5
        psi_some_avg10 = np.clip(pressure * 0.75 + rng.normal(0, 0.03, points), 0, None)
        psi_some_avg60 = pd.Series(psi_some_avg10).rolling(3, min_periods=1).mean().to_numpy()
        psi_some_avg300 = pd.Series(psi_some_avg10).rolling(15, min_periods=1).mean().to_numpy()
        psi_full_avg10 = np.clip(psi_some_avg10 * 0.72 + rng.normal(0, 0.02, points), 0, None)
        psi_full_avg60 = pd.Series(psi_full_avg10).rolling(3, min_periods=1).mean().to_numpy()
        psi_full_avg300 = pd.Series(psi_full_avg10).rolling(15, min_periods=1).mean().to_numpy()
        latency_ms = np.clip(
            45 + 28 * load + 75 * psi_some_avg10 + rng.normal(0, 2, points),
            1,
            None,
        )
        error_rate = np.clip(
            0.001 + np.maximum(psi_some_avg10 - 0.8, 0) * 0.012 + rng.normal(0, 0.0005, points),
            0,
            None,
        )

        frames.append(
            pd.DataFrame(
                {
                    "timestamp": timestamps,
                    "server_id": server_id,
                    "request_rate": request_rate,
                    "active_connections": active_connections,
                    "cpu_usage": cpu_usage,
                    "memory_usage": memory_usage,
                    "read_bytes_per_sec": read_bytes,
                    "write_bytes_per_sec": write_bytes,
                    "latency_ms": latency_ms,
                    "error_rate": error_rate,
                    "psi_some_avg10": psi_some_avg10,
                    "psi_some_avg60": psi_some_avg60,
                    "psi_some_avg300": psi_some_avg300,
                    "psi_full_avg10": psi_full_avg10,
                    "psi_full_avg60": psi_full_avg60,
                    "psi_full_avg300": psi_full_avg300,
                }
            )
        )

    output = pd.concat(frames, ignore_index=True)
    output.to_csv(OUTPUT_FILE, index=False)
    print(f"Generated {len(output):,} rows ({SERVER_COUNT} servers x {points:,} points).")
    print(f"Saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
