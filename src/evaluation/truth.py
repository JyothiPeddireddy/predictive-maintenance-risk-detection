"""Ground truth for EVALUATION ONLY. The risk engine never imports this module.

Truth = the confirmed failures (when they happened, how long the machine was down). It comes either from the
failure_event table of a database, or straight from the synthetic generator (for in-memory holdout tests).
"""
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.config import GeneratorConfig
from src.generator.hierarchy import SENSOR_SPECS, build_hierarchy
from src.generator.records import build_records
from src.generator.scenarios import apply_scenarios, plan_scenarios
from src.generator.telemetry import generate_sensor_readings
from src.risk.data import RiskInputs, validate_inputs

TRUTH_COLUMNS = ["failure_id", "machine_id", "category", "onset", "failure_at", "returned_to_service", "gain"]


def truth_from_db(engine: Engine) -> pd.DataFrame:
    sql = """SELECT f.failure_id, f.machine_id, f.failure_category AS category, f.symptom_onset_at AS onset,
                    f.failure_at, max(w.returned_to_service_at) AS returned_to_service
             FROM failure_event f LEFT JOIN maintenance_work_order w USING (failure_id)
             GROUP BY f.failure_id, f.machine_id, f.failure_category, f.symptom_onset_at, f.failure_at
             ORDER BY f.failure_at"""
    with engine.connect() as c:
        df = pd.DataFrame(c.execute(text(sql)).mappings().all(), columns=TRUTH_COLUMNS[:-1])
    df["gain"] = float("nan")
    for col in ("onset", "failure_at", "returned_to_service"):
        df[col] = pd.to_datetime(df[col], utc=True)
    df["returned_to_service"] = df["returned_to_service"].fillna(df["failure_at"] + pd.Timedelta(hours=24))
    return df[TRUTH_COLUMNS]


def synthetic_dataset(cfg: GeneratorConfig) -> tuple[RiskInputs, pd.DataFrame]:
    """Build one complete synthetic dataset in memory (no database): risk inputs + ground truth."""
    h = build_hierarchy(cfg)
    plan = plan_scenarios(cfg, h)
    rec = build_records(cfg, h, plan)
    machine_of = {s["sensor_id"]: s["machine_id"] for s in h["sensors"]}
    frames = []
    for idx, s in enumerate(h["sensors"]):
        df = apply_scenarios(cfg, s, idx, generate_sensor_readings(cfg, s, idx), plan, SENSOR_SPECS[s["sensor_type"]])
        frames.append(df[["sensor_id", "event_ts", "reading_value", "machine_state"]])
    sensors = pd.DataFrame([{k: s[k] for k in ("sensor_id", "machine_id", "sensor_type", "sampling_interval_s")}
                            for s in h["sensors"]])
    wo = pd.DataFrame(rec["maintenance_work_order"])[["machine_id", "maintenance_type", "created_at", "started_at",
                                                      "completed_at", "returned_to_service_at"]]
    inputs = RiskInputs(
        sensors=sensors, telemetry=pd.concat(frames, ignore_index=True),
        sensor_status=pd.DataFrame(rec["sensor_status_history"])[["sensor_id", "new_status", "changed_at"]],
        work_orders=wo)
    truth = pd.DataFrame([dict(failure_id=f.failure_id, machine_id=f.machine_id, category=f.category,
                               onset=f.onset, failure_at=f.failure_at, returned_to_service=f.returned_to_service,
                               gain=f.gain) for f in plan.failures], columns=TRUTH_COLUMNS)
    for col in ("onset", "failure_at", "returned_to_service"):
        truth[col] = pd.to_datetime(truth[col], utc=True)
    return validate_inputs(inputs), truth
