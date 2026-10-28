"""Generates schemas/schema.sql and schemas/data_dictionary.md straight from the SQLAlchemy models,
so the documentation can never drift from the code (a test checks the files are up to date)."""
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from src.models.tables import Base

PG = postgresql.dialect()

TABLE_PURPOSE = {
    "plant": "A factory site. Top of the hierarchy.",
    "production_line": "A line inside a plant (1 plant : N lines).",
    "machine": "A machine on a production line (1 line : N machines). Central entity of the project.",
    "sensor": "A sensor attached to a machine. Stores unit and plausible range used to judge sensor quality.",
    "telemetry_event": "One sensor reading with its timestamp, unit and the machine operating state at that time.",
    "operating_shift": "Planned operating context of one machine for one shift (planned state and load).",
    "technician": "A maintenance technician (one row per person, never duplicated; assignments are in the bridge table).",
    "part": "Catalogue of replaceable parts and consumables.",
    "failure_event": "A confirmed machine failure with symptom onset, failure, detection and resolution times. "
                     "Ground-truth source: never used as an input to risk scoring.",
    "maintenance_work_order": "A maintenance job on a machine, with lifecycle status, start/end and downtime timestamps.",
    "work_order_technician": "Bridge table (N:M) work order <-> technician, with role and hours worked.",
    "work_order_part": "Bridge table (N:M) work order <-> part, with quantity used and replacement timestamp.",
    "machine_state_history": "Append-only log of machine operating-state changes (never updated or deleted).",
    "sensor_status_history": "Append-only log of sensor status changes, e.g. ACTIVE -> FAULTY.",
    "work_order_status_history": "Append-only log of work-order lifecycle transitions; legal transitions are enforced.",
}

# Extra notes for columns where units, formats or meaning need spelling out ("table.column": note)
COLUMN_NOTES = {
    "plant.plant_id": "Format PLT-001.",
    "production_line.line_id": "Format LINE-<plant-id>-001.",
    "machine.machine_id": "Format MCH-<line-id>-001.",
    "sensor.sensor_id": "Format SNS-<machine-id>-TEMP-01.",
    "sensor.min_plausible": "Same unit as sensor.unit. Readings outside min/max are sensor-quality suspects.",
    "sensor.max_plausible": "Same unit as sensor.unit.",
    "sensor.sampling_interval_s": "Seconds between readings.",
    "telemetry_event.telemetry_id": "Format TEL-<sensor-id>-YYYYMMDDTHHMMSSZ (UTC); -01, -02... added for same-second duplicates.",
    "telemetry_event.event_ts": "UTC.",
    "telemetry_event.reading_value": "In the sensor's unit. NULL = missing reading (a genuine 0 is stored as 0).",
    "telemetry_event.machine_state": "Operating state when the reading was taken.",
    "operating_shift.shift_id": "Format SHF-<machine-id>-YYYYMMDD-M|A|N.",
    "operating_shift.planned_load_pct": "Percent, 0-100.",
    "technician.technician_id": "Format TECH-001.",
    "technician.plant_id": "Home plant.",
    "part.part_id": "Format PRT-0001.",
    "part.unit_cost": "Currency units per unit_of_measure (EA = each, L = litre, KG = kilogram, M = metre).",
    "failure_event.failure_id": "Format FAIL-<machine-id>-001.",
    "failure_event.symptom_onset_at": "When degradation began. Must not be after failure_at.",
    "failure_event.failure_at": "When the failure was confirmed.",
    "failure_event.detected_at": "First detection by a person or system. NULL = not detected beforehand.",
    "failure_event.resolved_at": "NULL until status = RESOLVED.",
    "maintenance_work_order.work_order_id": "Format WO-2026-000001.",
    "maintenance_work_order.failure_id": "Set when the order repairs a recorded failure.",
    "maintenance_work_order.downtime_start": "When the machine stopped for this work. Downtime = returned_to_service_at - downtime_start (derived, not stored).",
    "maintenance_work_order.returned_to_service_at": "When the machine went back into service.",
    "work_order_technician.hours_worked": "Hours.",
    "work_order_part.quantity_used": "In the part's unit_of_measure. Must be > 0.",
    "work_order_part.replaced_at": "When the part was fitted. NULL if not recorded.",
    "machine_state_history.history_id": "Format MSH-<machine-id>-YYYYMMDDTHHMMSSZ.",
    "machine_state_history.previous_state": "NULL on the machine's first record.",
    "machine_state_history.work_order_id": "Optional: the work order that caused this change.",
    "machine_state_history.failure_id": "Optional: the failure that caused this change.",
    "sensor_status_history.history_id": "Format SSH-<sensor-id>-YYYYMMDDTHHMMSSZ.",
    "sensor_status_history.previous_status": "NULL on the sensor's first record. RETIRED is final.",
    "work_order_status_history.history_id": "Format WSH-<work-order-id>-YYYYMMDDTHHMMSSZ.",
    "work_order_status_history.changed_by_technician_id": "Optional.",
}


def build_schema_sql() -> str:
    parts = []
    for table in Base.metadata.sorted_tables:
        parts.append(str(CreateTable(table).compile(dialect=PG)).strip() + ";")
        parts += [str(CreateIndex(i).compile(dialect=PG)).strip() + ";"
                  for i in sorted(table.indexes, key=lambda i: i.name)]
    return ("-- Generated from src/models/tables.py by: python -m src.cli export-schema\n"
            "-- Informational copy. The database itself is built by the Alembic migrations in migrations/.\n"
            "-- (The append-only triggers on the *_history tables come from migration 0003 and are not shown here.)\n\n"
            + "\n\n".join(parts) + "\n")


def _key_text(table, column) -> str:
    keys = []
    if column.primary_key:
        keys.append("PK")
    for fk in column.foreign_keys:
        keys.append(f"FK -> {fk.column.table.name}.{fk.column.name}")
    for c in table.constraints:
        if isinstance(c, UniqueConstraint) and column.name in c.columns:
            keys.append("UQ" if len(c.columns) == 1 else "UQ (with " + ", ".join(
                x.name for x in c.columns if x.name != column.name) + ")")
    if column.unique:
        keys.append("UQ")
    return "; ".join(dict.fromkeys(keys))


def build_data_dictionary() -> str:
    out = ["# Data dictionary", "",
           "Generated from `src/models/tables.py` by `python -m src.cli export-dictionary` (do not edit by hand).",
           "All timestamps are `timestamptz`, always UTC. Enum-like fields are `VARCHAR` with a CHECK constraint.", ""]
    for table in Base.metadata.sorted_tables:
        out += [f"## `{table.name}`", "", TABLE_PURPOSE[table.name], "",
                "| Column | Type | Null? | Key | Notes |", "|---|---|---|---|---|"]
        for col in table.columns:
            out.append(f"| `{col.name}` | {col.type.compile(dialect=PG)} | {'yes' if col.nullable else 'no'} | "
                       f"{_key_text(table, col)} | {COLUMN_NOTES.get(f'{table.name}.{col.name}', '')} |")
        checks = [c for c in table.constraints if isinstance(c, CheckConstraint)]
        if checks:
            out += ["", "**CHECK constraints**", ""]
            out += [f"- `{c.name}`: `{' '.join(str(c.sqltext).split())}`" for c in sorted(checks, key=lambda c: c.name)]
        indexes = sorted(table.indexes, key=lambda i: i.name)
        if indexes:
            out += ["", "**Indexes**", ""]
            for i in indexes:
                where = i.dialect_options["postgresql"]["where"]
                out.append(f"- `{i.name}` on ({', '.join(c.name for c in i.columns)})"
                           f"{' UNIQUE' if i.unique else ''}{f' WHERE {where}' if where is not None else ''}")
        out.append("")
    return "\n".join(out)
