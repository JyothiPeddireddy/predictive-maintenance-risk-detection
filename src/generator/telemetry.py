"""Baseline (healthy) telemetry for ONE sensor.

Slice scope: normal running + idle only. Faults, drift, pre-failure patterns and repairs
are added in Phase 3 on top of this baseline, driven by explicit failure scenarios.

Determinism: each sensor gets its own random stream seeded from (seed, sensor_index),
so the output does NOT depend on batch size or on the order batches are written.
"""
import numpy as np
import pandas as pd

from src.config import GeneratorConfig
from src.generator import ids
from src.generator.hierarchy import SENSOR_SPECS

IDLE_HOURS_UTC = range(0, 6)  # slice rule: machines idle 00:00-05:59 UTC


def generate_sensor_readings(cfg: GeneratorConfig, sensor: dict, sensor_index: int) -> pd.DataFrame:
    spec = SENSOR_SPECS[sensor["sensor_type"]]
    n = cfg.readings_per_sensor
    ts = pd.date_range(cfg.start, periods=n, freq=f"{cfg.sampling_interval_s}s", tz="UTC")

    rng = np.random.default_rng(np.random.SeedSequence([cfg.seed, sensor_index]))
    hours = np.asarray(ts.hour)
    idle = np.isin(hours, list(IDLE_HOURS_UTC))

    base = np.where(idle, spec["idle"], spec["run"])
    daily_wave = 0.05 * spec["run"] * np.sin(2 * np.pi * (hours + ts.minute / 60) / 24)
    value = base + np.where(idle, 0.0, daily_wave) + rng.normal(0.0, spec["noise"], n)
    value = np.round(np.maximum(value, spec["min"]), 3)

    tel_ids = "TEL-" + sensor["sensor_id"] + "-" + ts.strftime(ids.TS_FORMAT)
    return pd.DataFrame({
        "telemetry_id": tel_ids,   # regular sampling >= 1 s apart, so no same-second duplicates here
        "sensor_id": sensor["sensor_id"],
        "event_ts": ts,
        "reading_value": value,
        "unit": spec["unit"],
        "machine_state": np.where(idle, "IDLE", "RUNNING"),
    })
