"""SQLAlchemy 2.x models for the vertical slice (5 of the 10 entities).

Phase 2 tables: plant, production_line, machine, sensor, telemetry_event.
Phase 3A tables (bottom of this file): operating_shift, technician, part, failure_event,
maintenance_work_order, work_order_technician, work_order_part and three *_history tables.
Enums are stored as VARCHAR + CHECK constraint (simple, portable, easy to read in pgAdmin).
All timestamps are timestamptz and are always written in UTC.
"""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, MetaData,
                        Numeric, String, Text, UniqueConstraint, text)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class Plant(Base):
    __tablename__ = "plant"
    plant_id: Mapped[str] = mapped_column(String(16), primary_key=True)  # PLT-001
    plant_name: Mapped[str] = mapped_column(String(100), unique=True)
    timezone: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")
    commissioned_on: Mapped[date] = mapped_column(Date)
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','INACTIVE','DECOMMISSIONED')", name="status_enum"),
    )


class ProductionLine(Base):
    __tablename__ = "production_line"
    line_id: Mapped[str] = mapped_column(String(32), primary_key=True)  # LINE-PLT-001-001
    plant_id: Mapped[str] = mapped_column(ForeignKey("plant.plant_id"), index=True)
    line_name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")
    __table_args__ = (
        UniqueConstraint("plant_id", "line_name"),
        CheckConstraint("status IN ('ACTIVE','INACTIVE','DECOMMISSIONED')", name="status_enum"),
    )


class Machine(Base):
    __tablename__ = "machine"
    machine_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    line_id: Mapped[str] = mapped_column(ForeignKey("production_line.line_id"), index=True)
    machine_name: Mapped[str] = mapped_column(String(100))
    machine_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24), default="OPERATIONAL")
    installed_on: Mapped[date] = mapped_column(Date)
    __table_args__ = (
        UniqueConstraint("line_id", "machine_name"),
        CheckConstraint(
            "status IN ('OPERATIONAL','UNDER_MAINTENANCE','FAILED','DECOMMISSIONED')",
            name="status_enum"),
    )


class Sensor(Base):
    __tablename__ = "sensor"
    sensor_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    machine_id: Mapped[str] = mapped_column(ForeignKey("machine.machine_id"), index=True)
    sensor_type: Mapped[str] = mapped_column(String(8))   # TEMP, VIB (more in Phase 3)
    sensor_seq: Mapped[int] = mapped_column(Integer)      # the "01" in ...-TEMP-01
    unit: Mapped[str] = mapped_column(String(12))         # degC, mm/s
    min_plausible: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    max_plausible: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    sampling_interval_s: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")
    __table_args__ = (
        UniqueConstraint("machine_id", "sensor_type", "sensor_seq"),
        CheckConstraint("sensor_type IN ('TEMP','VIB')", name="type_enum"),
        CheckConstraint("status IN ('ACTIVE','FAULTY','RETIRED')", name="status_enum"),
        CheckConstraint("min_plausible < max_plausible", name="range_order"),
        CheckConstraint("sampling_interval_s > 0", name="interval_positive"),
    )


class TelemetryEvent(Base):
    __tablename__ = "telemetry_event"
    telemetry_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    sensor_id: Mapped[str] = mapped_column(ForeignKey("sensor.sensor_id"))
    event_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reading_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    unit: Mapped[str] = mapped_column(String(12))
    machine_state: Mapped[str] = mapped_column(String(20))
    __table_args__ = (
        Index("ix_telemetry_sensor_ts", "sensor_id", "event_ts"),
        CheckConstraint(
            "machine_state IN ('RUNNING','IDLE','PLANNED_SHUTDOWN','MAINTENANCE')",
            name="state_enum"),
    )


# =====================================================================================
# Phase 3A: remaining entities, bridge tables and history tables
# =====================================================================================
# Allowed values, kept in one place so the generator and validators can reuse them.
MACHINE_STATES = ("RUNNING", "IDLE", "PLANNED_SHUTDOWN", "MAINTENANCE", "FAILED")
SENSOR_STATUSES = ("ACTIVE", "FAULTY", "RETIRED")
SHIFT_NAMES = ("MORNING", "AFTERNOON", "NIGHT")
PLANNED_STATES = ("RUNNING", "IDLE", "PLANNED_SHUTDOWN")
TECHNICIAN_SPECIALTIES = ("MECHANICAL", "ELECTRICAL", "INSTRUMENTATION", "GENERAL")
TECHNICIAN_STATUSES = ("ACTIVE", "ON_LEAVE", "INACTIVE")
PART_CATEGORIES = ("BEARING", "SEAL", "MOTOR", "BELT", "FILTER", "SENSOR", "LUBRICANT",
                   "ELECTRICAL", "OTHER")
PART_UNITS = ("EA", "L", "KG", "M")
PART_STATUSES = ("ACTIVE", "DISCONTINUED")
FAILURE_CATEGORIES = ("BEARING_WEAR", "OVERHEATING", "ELECTRICAL", "LUBRICATION",
                      "MISALIGNMENT", "OTHER")
FAILURE_SEVERITIES = ("MINOR", "MAJOR", "CRITICAL")
FAILURE_STATUSES = ("CONFIRMED", "UNDER_REPAIR", "RESOLVED")
MAINTENANCE_TYPES = ("PREVENTIVE", "CORRECTIVE", "PREDICTIVE", "INSPECTION")
WORK_ORDER_PRIORITIES = ("LOW", "MEDIUM", "HIGH", "URGENT")
WORK_ORDER_STATUSES = ("OPEN", "IN_PROGRESS", "COMPLETED", "CANCELLED")
TECHNICIAN_ROLES = ("LEAD", "ASSISTANT")
STATE_CHANGE_SOURCES = ("SCHEDULE", "WORK_ORDER", "FAILURE", "MANUAL")


def _in(column: str, values: tuple[str, ...]) -> str:
    """Builds the text of an enum CHECK, e.g.  status IN ('A','B')."""
    return f"{column} IN ({','.join(repr(v) for v in values)})"


class OperatingShift(Base):
    """Planned operating context of ONE machine during ONE shift (what the machine was scheduled to do)."""
    __tablename__ = "operating_shift"
    shift_id: Mapped[str] = mapped_column(String(48), primary_key=True)  # SHF-<machine-id>-YYYYMMDD-M|A|N
    machine_id: Mapped[str] = mapped_column(ForeignKey("machine.machine_id"))
    shift_name: Mapped[str] = mapped_column(String(12))
    shift_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    shift_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    planned_state: Mapped[str] = mapped_column(String(20))
    planned_load_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)  # percent 0-100
    __table_args__ = (
        UniqueConstraint("machine_id", "shift_start"),  # also serves as the machine_id lookup index
        CheckConstraint(_in("shift_name", SHIFT_NAMES), name="name_enum"),
        CheckConstraint(_in("planned_state", PLANNED_STATES), name="planned_state_enum"),
        CheckConstraint("shift_end > shift_start", name="end_after_start"),
        CheckConstraint("planned_load_pct IS NULL OR planned_load_pct BETWEEN 0 AND 100",
                        name="load_pct_range"),
    )


class Technician(Base):
    __tablename__ = "technician"
    technician_id: Mapped[str] = mapped_column(String(16), primary_key=True)  # TECH-001
    plant_id: Mapped[str] = mapped_column(ForeignKey("plant.plant_id"), index=True)  # home plant
    full_name: Mapped[str] = mapped_column(String(100))
    specialty: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(12), default="ACTIVE")
    hired_on: Mapped[date] = mapped_column(Date)
    __table_args__ = (
        CheckConstraint(_in("specialty", TECHNICIAN_SPECIALTIES), name="specialty_enum"),
        CheckConstraint(_in("status", TECHNICIAN_STATUSES), name="status_enum"),
    )


class Part(Base):
    __tablename__ = "part"
    part_id: Mapped[str] = mapped_column(String(16), primary_key=True)  # PRT-0001
    part_number: Mapped[str] = mapped_column(String(32), unique=True)    # manufacturer / catalogue number
    part_name: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(16))
    unit_of_measure: Mapped[str] = mapped_column(String(4))             # EA, L, KG, M
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2))          # currency units per unit_of_measure
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")
    __table_args__ = (
        CheckConstraint(_in("category", PART_CATEGORIES), name="category_enum"),
        CheckConstraint(_in("unit_of_measure", PART_UNITS), name="unit_enum"),
        CheckConstraint(_in("status", PART_STATUSES), name="status_enum"),
        CheckConstraint("unit_cost >= 0", name="cost_non_negative"),
    )


class FailureEvent(Base):
    """A confirmed machine failure. This is source data for ground truth, never an input to risk scoring."""
    __tablename__ = "failure_event"
    failure_id: Mapped[str] = mapped_column(String(48), primary_key=True)  # FAIL-<machine-id>-001
    machine_id: Mapped[str] = mapped_column(ForeignKey("machine.machine_id"))
    failure_category: Mapped[str] = mapped_column(String(16))
    severity: Mapped[str] = mapped_column(String(8))
    symptom_onset_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # degradation begins
    failure_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))        # failure confirmed
    detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="CONFIRMED")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (
        UniqueConstraint("machine_id", "failure_at"),  # also serves as the machine_id lookup index
        CheckConstraint(_in("failure_category", FAILURE_CATEGORIES), name="category_enum"),
        CheckConstraint(_in("severity", FAILURE_SEVERITIES), name="severity_enum"),
        CheckConstraint(_in("status", FAILURE_STATUSES), name="status_enum"),
        CheckConstraint("symptom_onset_at <= failure_at", name="onset_before_failure"),
        CheckConstraint("detected_at IS NULL OR detected_at >= symptom_onset_at",
                        name="detected_after_onset"),
        CheckConstraint("resolved_at IS NULL OR resolved_at >= failure_at", name="resolved_after_failure"),
        CheckConstraint("(status = 'RESOLVED') = (resolved_at IS NOT NULL)", name="resolved_matches_status"),
    )


class MaintenanceWorkOrder(Base):
    __tablename__ = "maintenance_work_order"
    work_order_id: Mapped[str] = mapped_column(String(20), primary_key=True)  # WO-2026-000001
    machine_id: Mapped[str] = mapped_column(ForeignKey("machine.machine_id"))
    failure_id: Mapped[str | None] = mapped_column(
        ForeignKey("failure_event.failure_id"), index=True, nullable=True)  # set for repairs of a failure
    maintenance_type: Mapped[str] = mapped_column(String(12))
    priority: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(12), default="OPEN")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    downtime_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    returned_to_service_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    findings: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrective_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    # NOTE: downtime duration is NOT stored. It is derived: returned_to_service_at - downtime_start.
    __table_args__ = (
        Index("ix_work_order_machine_created", "machine_id", "created_at"),
        CheckConstraint(_in("maintenance_type", MAINTENANCE_TYPES), name="type_enum"),
        CheckConstraint(_in("priority", WORK_ORDER_PRIORITIES), name="priority_enum"),
        CheckConstraint(_in("status", WORK_ORDER_STATUSES), name="status_enum"),
        CheckConstraint("started_at IS NULL OR started_at >= created_at", name="start_after_created"),
        CheckConstraint("started_at IS NULL OR completed_at IS NULL OR completed_at >= started_at",
                        name="end_after_start"),
        CheckConstraint("returned_to_service_at IS NULL OR "
                        "(downtime_start IS NOT NULL AND returned_to_service_at >= downtime_start)",
                        name="downtime_order"),
        CheckConstraint(
            "(status = 'OPEN' AND started_at IS NULL AND completed_at IS NULL) OR "
            "(status = 'IN_PROGRESS' AND started_at IS NOT NULL AND completed_at IS NULL) OR "
            "(status = 'COMPLETED' AND started_at IS NOT NULL AND completed_at IS NOT NULL) OR "
            "(status = 'CANCELLED' AND completed_at IS NULL)",
            name="status_matches_timestamps"),
    )


class WorkOrderTechnician(Base):
    """Bridge (N:M): which technicians worked on which work order."""
    __tablename__ = "work_order_technician"
    work_order_id: Mapped[str] = mapped_column(
        ForeignKey("maintenance_work_order.work_order_id"), primary_key=True)
    technician_id: Mapped[str] = mapped_column(
        ForeignKey("technician.technician_id"), primary_key=True, index=True)
    role: Mapped[str] = mapped_column(String(10))
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    hours_worked: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)  # hours
    __table_args__ = (
        CheckConstraint(_in("role", TECHNICIAN_ROLES), name="role_enum"),
        CheckConstraint("hours_worked IS NULL OR hours_worked >= 0", name="hours_non_negative"),
        # at most ONE lead technician per work order
        Index("uq_work_order_technician_one_lead", "work_order_id", unique=True,
              postgresql_where=text("role = 'LEAD'")),
    )


class WorkOrderPart(Base):
    """Bridge (N:M): which parts were consumed by which work order, how many, and when fitted."""
    __tablename__ = "work_order_part"
    work_order_id: Mapped[str] = mapped_column(
        ForeignKey("maintenance_work_order.work_order_id"), primary_key=True)
    part_id: Mapped[str] = mapped_column(ForeignKey("part.part_id"), primary_key=True, index=True)
    quantity_used: Mapped[Decimal] = mapped_column(Numeric(10, 2))  # in the part's unit_of_measure
    replaced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (CheckConstraint("quantity_used > 0", name="quantity_positive"),)


class MachineStateHistory(Base):
    """Append-only log of machine operating-state changes. Rows are never updated or deleted."""
    __tablename__ = "machine_state_history"
    history_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # MSH-<machine-id>-<UTC ts>
    machine_id: Mapped[str] = mapped_column(ForeignKey("machine.machine_id"))
    previous_state: Mapped[str | None] = mapped_column(String(20), nullable=True)  # NULL = first record
    new_state: Mapped[str] = mapped_column(String(20))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    change_source: Mapped[str] = mapped_column(String(12))
    work_order_id: Mapped[str | None] = mapped_column(
        ForeignKey("maintenance_work_order.work_order_id"), index=True, nullable=True)
    failure_id: Mapped[str | None] = mapped_column(
        ForeignKey("failure_event.failure_id"), index=True, nullable=True)
    __table_args__ = (
        UniqueConstraint("machine_id", "changed_at"),  # also serves as the machine_id lookup index
        CheckConstraint(_in("new_state", MACHINE_STATES), name="new_state_enum"),
        CheckConstraint("previous_state IS NULL OR " + _in("previous_state", MACHINE_STATES),
                        name="previous_state_enum"),
        CheckConstraint(_in("change_source", STATE_CHANGE_SOURCES), name="source_enum"),
        CheckConstraint("previous_state IS NULL OR previous_state <> new_state", name="state_really_changed"),
        CheckConstraint("(work_order_id IS NULL OR change_source = 'WORK_ORDER') AND "
                        "(failure_id IS NULL OR change_source = 'FAILURE')", name="link_matches_source"),
    )


class SensorStatusHistory(Base):
    """Append-only log of sensor status changes (e.g. ACTIVE -> FAULTY). Supports sensor-fault analysis."""
    __tablename__ = "sensor_status_history"
    history_id: Mapped[str] = mapped_column(String(80), primary_key=True)  # SSH-<sensor-id>-<UTC ts>
    sensor_id: Mapped[str] = mapped_column(ForeignKey("sensor.sensor_id"))
    previous_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    new_status: Mapped[str] = mapped_column(String(16))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    __table_args__ = (
        UniqueConstraint("sensor_id", "changed_at"),  # also serves as the sensor_id lookup index
        CheckConstraint(_in("new_status", SENSOR_STATUSES), name="new_status_enum"),
        CheckConstraint("previous_status IS NULL OR " + _in("previous_status", SENSOR_STATUSES),
                        name="previous_status_enum"),
        CheckConstraint("previous_status IS NULL OR previous_status <> new_status",
                        name="status_really_changed"),
        CheckConstraint("previous_status IS DISTINCT FROM 'RETIRED'", name="retired_is_final"),
    )


class WorkOrderStatusHistory(Base):
    """Append-only log of work-order lifecycle transitions. The allowed transitions are enforced here."""
    __tablename__ = "work_order_status_history"
    history_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # WSH-<work-order-id>-<UTC ts>
    # explicit short FK names: the auto-generated ones would exceed PostgreSQL's 63-character limit
    work_order_id: Mapped[str] = mapped_column(
        ForeignKey("maintenance_work_order.work_order_id", name="fk_wo_status_history_work_order"))
    previous_status: Mapped[str | None] = mapped_column(String(12), nullable=True)
    new_status: Mapped[str] = mapped_column(String(12))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    changed_by_technician_id: Mapped[str | None] = mapped_column(
        ForeignKey("technician.technician_id", name="fk_wo_status_history_technician"), nullable=True)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    __table_args__ = (
        UniqueConstraint("work_order_id", "changed_at"),  # also serves as the work_order_id lookup index
        CheckConstraint(_in("new_status", WORK_ORDER_STATUSES), name="new_status_enum"),
        # Every branch tests previous_status explicitly with IS NULL / IS NOT NULL. Without that, a NULL
        # previous_status makes the whole CHECK evaluate to NULL, and PostgreSQL treats NULL as "passed".
        CheckConstraint(
            "(previous_status IS NULL AND new_status = 'OPEN') OR "
            "(previous_status IS NOT NULL AND previous_status = 'OPEN' "
            "AND new_status IN ('IN_PROGRESS','CANCELLED')) OR "
            "(previous_status IS NOT NULL AND previous_status = 'IN_PROGRESS' "
            "AND new_status IN ('COMPLETED','CANCELLED'))",
            name="allowed_transition"),
    )
