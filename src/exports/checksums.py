"""Deterministic checksum computed INSIDE PostgreSQL over ordered, explicitly formatted rows.
Timestamps are rendered in UTC so the result does not depend on the session time zone."""
from sqlalchemy import text
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
