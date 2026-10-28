"""Create tables, load master data, then bulk-load telemetry with PostgreSQL COPY."""
import io
import time

import pandas as pd
from sqlalchemy import insert, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from src.config import GeneratorConfig
from src.generator.hierarchy import build_hierarchy
from src.generator.telemetry import generate_sensor_readings
from src.migrate import upgrade
from src.models.tables import Base, Machine, Plant, ProductionLine, Sensor

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


def load_dataset(engine: Engine, cfg: GeneratorConfig, reset: bool = False) -> dict:
    if reset:
        reset_tables(engine)
    t0 = time.perf_counter()
    h = build_hierarchy(cfg)

    with Session(engine) as session, session.begin():  # parents first, one transaction
        for model, rows in ((Plant, h["plants"]), (ProductionLine, h["lines"]),
                            (Machine, h["machines"]), (Sensor, h["sensors"])):
            session.execute(insert(model), rows)

    buffer, buffered, total, batches = [], 0, 0, 0
    for idx, sensor in enumerate(h["sensors"]):
        df = generate_sensor_readings(cfg, sensor, idx)
        buffer.append(df)
        buffered += len(df)
        if buffered >= cfg.batch_size:
            copy_telemetry(engine, pd.concat(buffer, ignore_index=True))
            total, batches, buffer, buffered = total + buffered, batches + 1, [], 0
    if buffer:
        copy_telemetry(engine, pd.concat(buffer, ignore_index=True))
        total, batches = total + buffered, batches + 1

    return dict(plants=len(h["plants"]), lines=len(h["lines"]), machines=len(h["machines"]),
                sensors=len(h["sensors"]), telemetry=total, batches=batches,
                seconds=round(time.perf_counter() - t0, 2))


ALL_TABLES = [t.name for t in Base.metadata.sorted_tables]  # parents first


def table_counts(engine: Engine) -> dict:
    """Row count per table. A table that does not exist yet (database not upgraded) is reported as None."""
    existing = set(inspect(engine).get_table_names())
    with engine.connect() as c:
        return {n: (c.execute(text(f"SELECT count(*) FROM {n}")).scalar_one() if n in existing else None)
                for n in ALL_TABLES}
