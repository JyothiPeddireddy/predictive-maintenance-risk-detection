"""Builders for VALID rows. A test changes exactly one field to break exactly one rule."""
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError

from src.models import tables as t

PLANT = "PLT-001"
MACHINE = "MCH-LINE-PLT-001-001-001"          # exists in the starter data
SENSOR = "SNS-MCH-LINE-PLT-001-001-001-TEMP-01"  # exists in the starter data
T0 = datetime(2026, 3, 1, 8, 0, tzinfo=timezone.utc)


def at(hours: float) -> datetime:
    return T0 + timedelta(hours=hours)


def _make(defaults: dict, overrides: dict) -> dict:
    return {**defaults, **overrides}


def technician(**o):
    return _make(dict(technician_id="TECH-001", plant_id=PLANT, full_name="Asha Rao",
                      specialty="MECHANICAL", status="ACTIVE", hired_on=date(2020, 1, 1)), o)


def part(**o):
    return _make(dict(part_id="PRT-0001", part_number="BRG-6204", part_name="Ball bearing 6204",
                      category="BEARING", unit_of_measure="EA", unit_cost="12.50", status="ACTIVE"), o)


def shift(**o):
    return _make(dict(shift_id="SHF-A-20260301-M", machine_id=MACHINE, shift_name="MORNING",
                      shift_start=at(0), shift_end=at(8), planned_state="RUNNING", planned_load_pct="80"), o)


def failure(**o):
    return _make(dict(failure_id="FAIL-A-001", machine_id=MACHINE, failure_category="BEARING_WEAR",
                      severity="MAJOR", symptom_onset_at=at(0), failure_at=at(10), detected_at=None,
                      resolved_at=None, status="CONFIRMED", description=None), o)


def work_order(**o):
    return _make(dict(work_order_id="WO-2026-000001", machine_id=MACHINE, failure_id=None,
                      maintenance_type="CORRECTIVE", priority="HIGH", status="OPEN", created_at=at(11),
                      scheduled_for=None, started_at=None, completed_at=None, downtime_start=None,
                      returned_to_service_at=None, findings=None, corrective_action=None), o)


def wo_technician(**o):
    return _make(dict(work_order_id="WO-2026-000001", technician_id="TECH-001", role="LEAD",
                      assigned_at=at(11), hours_worked=None), o)


def wo_part(**o):
    return _make(dict(work_order_id="WO-2026-000001", part_id="PRT-0001", quantity_used="2",
                      replaced_at=None), o)


def machine_state(**o):
    return _make(dict(history_id="MSH-A-1", machine_id=MACHINE, previous_state=None, new_state="RUNNING",
                      changed_at=at(0), change_source="SCHEDULE", work_order_id=None, failure_id=None), o)


def sensor_status(**o):
    return _make(dict(history_id="SSH-A-1", sensor_id=SENSOR, previous_status=None, new_status="ACTIVE",
                      changed_at=at(0), reason=None), o)


def wo_status(**o):
    return _make(dict(history_id="WSH-A-1", work_order_id="WO-2026-000001", previous_status=None,
                      new_status="OPEN", changed_at=at(11), changed_by_technician_id=None, note=None), o)


def add(conn, model, row):
    conn.execute(insert(model), row)


def seed_parents(conn):
    """Valid technician, part, failure and an OPEN work order, ready for dependent rows."""
    add(conn, t.Technician, technician())
    add(conn, t.Part, part())
    add(conn, t.FailureEvent, failure())
    add(conn, t.MaintenanceWorkOrder, work_order(failure_id="FAIL-A-001"))


def expect_violation(conn, model, row, constraint):
    """The insert must fail, AND fail because of the named constraint (not for some other reason)."""
    allowed = (constraint,) if isinstance(constraint, str) else tuple(constraint)
    with pytest.raises(IntegrityError) as exc:
        with conn.begin_nested():  # savepoint, so the outer test transaction survives the error
            conn.execute(insert(model), row)
    assert exc.value.orig.diag.constraint_name in allowed, exc.value.orig.diag.constraint_name
