"""Create tables, load master data, then bulk-load telemetry with PostgreSQL COPY."""
import io
import json
import time
from pathlib import Path

import pandas as pd
from sqlalchemy import insert, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from src.config import GeneratorConfig
from src.generator.hierarchy import SENSOR_SPECS, build_hierarchy
from src.generator.records import build_records
from src.generator.scenarios import apply_scenarios, plan_manifest, plan_scenarios
from src.generator.telemetry import generate_sensor_readings
from src.migrate import upgrade
from src.models import tables as T
from src.models.tables import Base, Machine, Plant, ProductionLine, Sensor

# Phase 3B tables, in the order they must be inserted (parents first).
SCENARIO_TABLE_ORDER = [
    ("technician", T.Technician), ("part", T.Part), ("failure_event", T.FailureEvent),
    ("maintenance_work_order", T.MaintenanceWorkOrder), ("work_order_technician", T.WorkOrderTechnician),
    ("work_order_part", T.WorkOrderPart), ("machine_state_history", T.MachineStateHistory),
    ("sensor_status_history", T.SensorStatusHistory), ("work_order_status_history", T.WorkOrderStatusHistory),
    ("operating_shift", T.OperatingShift),
]

TELEMETRY_COLUMNS = ["telemetry_id", "sensor_id", "event_ts", "reading_value", "unit", "machine_state"]


def reset_tables(engine: Engine) -> None:
    """DEVELOPMENT / TEST ONLY: drops every table, then rebuilds the schema by running the migrations.
    (Phase 2 used create_all(); now there is a single way to build the schema: migrations.)
    The CLI refuses to call this on a database whose name does not end in _test unless --force is given."""
    Base.metadata.drop_all(engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
    upgrade(engine)


def copy_telemetry(engine: Engine, df: pd.DataFrame) -> None:
    """Fast bulk insert via COPY (much faster than row-by-row INSERT)."""
    buf = io.StringIO()
    df[TELEMETRY_COLUMNS].to_csv(buf, index=False, header=False, na_rep="")  # empty -> NULL
    raw = engine.raw_connection()
    try:
        with raw.cursor() as cur:
            with cur.copy(
                f"COPY telemetry_event ({', '.join(TELEMETRY_COLUMNS)}) FROM STDIN WITH (FORMAT csv)"
            ) as cp:
                cp.write(buf.getvalue())
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()


class DatabaseNotEmptyError(RuntimeError):
    pass


def assert_database_empty(engine: Engine) -> None:
    """A load without --reset must only ever write into an EMPTY database (never mix into existing data)."""
    existing = set(inspect(engine).get_table_names())
    with engine.connect() as c:
        for name in (t.name for t in Base.metadata.sorted_tables):
            if name in existing and c.execute(text(f"SELECT 1 FROM {name} LIMIT 1")).first():
                raise DatabaseNotEmptyError(
                    f"database '{engine.url.database}' already contains data (table '{name}'). "
                    "A load only writes into an empty database. Use a separate development database.")


def write_manifest(cfg: GeneratorConfig, plan) -> Path:
    path = Path(cfg.output_dir) / "scenario_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan_manifest(cfg, plan), indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_dataset(engine: Engine, cfg: GeneratorConfig, reset: bool = False) -> dict:
    if reset:
        reset_tables(engine)
    else:
        assert_database_empty(engine)
    t0 = time.perf_counter()
    h = build_hierarchy(cfg)
    plan = plan_scenarios(cfg, h) if cfg.scenarios_enabled else None
    records = build_records(cfg, h, plan) if plan is not None else {}

    with Session(engine) as session, session.begin():  # parents first, one transaction
        for model, rows in ((Plant, h["plants"]), (ProductionLine, h["lines"]),
                            (Machine, h["machines"]), (Sensor, h["sensors"])):
            session.execute(insert(model), rows)
        for name, model in SCENARIO_TABLE_ORDER:
            if records.get(name):
                session.execute(insert(model), records[name])

    buffer, buffered, total, batches = [], 0, 0, 0
    for idx, sensor in enumerate(h["sensors"]):
        df = generate_sensor_readings(cfg, sensor, idx)
        if plan is not None:
            df = apply_scenarios(cfg, sensor, idx, df, plan, SENSOR_SPECS[sensor["sensor_type"]])
        buffer.append(df)
        buffered += len(df)
        if buffered >= cfg.batch_size:
            copy_telemetry(engine, pd.concat(buffer, ignore_index=True))
            total, batches, buffer, buffered = total + buffered, batches + 1, [], 0
    if buffer:
        copy_telemetry(engine, pd.concat(buffer, ignore_index=True))
        total, batches = total + buffered, batches + 1

    result = dict(plants=len(h["plants"]), lines=len(h["lines"]), machines=len(h["machines"]),
                  sensors=len(h["sensors"]), telemetry=total, batches=batches,
                  seconds=round(time.perf_counter() - t0, 2))
    if plan is not None:
        result.update({k: len(v) for k, v in records.items()})
        result["manifest"] = str(write_manifest(cfg, plan))
    return result


ALL_TABLES = [t.name for t in Base.metadata.sorted_tables]  # parents first


def table_counts(engine: Engine) -> dict:
    """Row count per table. A table that does not exist yet (database not upgraded) is reported as None."""
    existing = set(inspect(engine).get_table_names())
    with engine.connect() as c:
        return {n: (c.execute(text(f"SELECT count(*) FROM {n}")).scalar_one() if n in existing else None)
                for n in ALL_TABLES}
