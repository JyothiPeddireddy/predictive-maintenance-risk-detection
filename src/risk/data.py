"""Inputs of the risk engine.

LEAKAGE RULE: the risk engine may only see what a real plant would know at scoring time:
telemetry, sensor status changes and maintenance work orders. It must never see failure labels.
`RiskInputs` therefore has a FIXED set of columns (checked by `validate_inputs`), and the work-order
table is read WITHOUT its failure link. Everything is further restricted to "what was known at time t"
inside the engine (point-in-time), and `truncate_inputs` lets a test prove that data after t is never used.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

COLUMNS = {
    "sensors": ["sensor_id", "machine_id", "sensor_type", "sampling_interval_s"],
    "telemetry": ["sensor_id", "event_ts", "reading_value", "machine_state"],
    "sensor_status": ["sensor_id", "new_status", "changed_at"],
    "work_orders": ["machine_id", "maintenance_type", "created_at", "started_at", "completed_at",
                    "returned_to_service_at"],
}


@dataclass
class RiskInputs:
    sensors: pd.DataFrame
    telemetry: pd.DataFrame
    sensor_status: pd.DataFrame
    work_orders: pd.DataFrame

    @property
    def machines(self) -> list[str]:
        return sorted(self.sensors["machine_id"].unique())


def validate_inputs(inp: RiskInputs) -> RiskInputs:
    """Refuse any table that has columns beyond the allowed list (so a label can never slip in)."""
    for name, cols in COLUMNS.items():
        got = list(getattr(inp, name).columns)
        if got != cols:
            raise ValueError(f"risk input '{name}' must have exactly the columns {cols}, got {got}")
    return inp


def to_seconds(series: pd.Series) -> np.ndarray:
    """Timestamps -> float seconds since 1970 (UTC). Missing timestamps become NaN."""
    s = pd.to_datetime(series, utc=True)
    return (s - pd.Timestamp("1970-01-01", tz="UTC")).dt.total_seconds().to_numpy(dtype=float)


def inputs_from_db(engine: Engine) -> RiskInputs:
    """Read the risk inputs from a database. Read-only. The work-order query deliberately leaves out the failure link."""
    q = {
        "sensors": "SELECT sensor_id, machine_id, sensor_type, sampling_interval_s FROM sensor ORDER BY sensor_id",
        "telemetry": "SELECT sensor_id, event_ts, reading_value, machine_state FROM telemetry_event "
                     "ORDER BY sensor_id, event_ts",
        "sensor_status": "SELECT sensor_id, new_status, changed_at FROM sensor_status_history "
                         "ORDER BY sensor_id, changed_at",
        "work_orders": "SELECT machine_id, maintenance_type, created_at, started_at, completed_at, "
                       "returned_to_service_at FROM maintenance_work_order ORDER BY created_at",
    }
    with engine.connect() as conn:
        frames = {k: pd.read_sql(text(sql), conn) for k, sql in q.items()}
    frames["telemetry"]["reading_value"] = pd.to_numeric(frames["telemetry"]["reading_value"], errors="coerce")
    return validate_inputs(RiskInputs(**frames))


def truncate_inputs(inp: RiskInputs, t) -> RiskInputs:
    """Keep only what existed at time t (used by tests to prove the engine never looks into the future)."""
    t = pd.Timestamp(t)
    tel = inp.telemetry[pd.to_datetime(inp.telemetry["event_ts"], utc=True) <= t]
    st = inp.sensor_status[pd.to_datetime(inp.sensor_status["changed_at"], utc=True) <= t]
    wo = inp.work_orders[pd.to_datetime(inp.work_orders["created_at"], utc=True) <= t].copy()
    for col in ("started_at", "completed_at", "returned_to_service_at"):
        later = pd.to_datetime(wo[col], utc=True) > t
        wo[col] = wo[col].where(~later, pd.NaT)
    return RiskInputs(inp.sensors.copy(), tel.copy(), st.copy(), wo)
