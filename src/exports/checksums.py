"""Deterministic checksum computed INSIDE PostgreSQL over ordered, explicitly formatted rows.
Timestamps are rendered in UTC so the result does not depend on the session time zone."""
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

TELEMETRY_SQL = """
SELECT md5(string_agg(
    telemetry_id || '|' || sensor_id || '|' ||
    to_char(event_ts AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS') || '|' ||
    coalesce(reading_value::text, '') || '|' || unit || '|' || machine_state,
    E'\\n' ORDER BY telemetry_id))
FROM telemetry_event
"""


def telemetry_checksum(engine: Engine) -> str | None:
    with engine.connect() as c:
        return c.execute(text(TELEMETRY_SQL)).scalar_one()


def table_checksum(engine: Engine, table_name: str, pk_columns: list[str]) -> str | None:
    """md5 over every row of a table (ordered by primary key, rendered in UTC). None if the table is empty.
    `table_name` / `pk_columns` come from the SQLAlchemy models, never from user input."""
    order = ", ".join(pk_columns)
    sql = f"SELECT md5(string_agg(t::text, E'\\n' ORDER BY {order})) FROM {table_name} t"
    with engine.begin() as c:
        c.execute(text("SET LOCAL TIME ZONE 'UTC'"))
        return c.execute(text(sql)).scalar_one()


def all_table_checksums(engine: Engine) -> dict[str, str | None]:
    from src.models.tables import Base
    existing = set(inspect(engine).get_table_names())
    return {t.name: (table_checksum(engine, t.name, [c.name for c in t.primary_key.columns])
                     if t.name in existing else None)
            for t in Base.metadata.sorted_tables}
