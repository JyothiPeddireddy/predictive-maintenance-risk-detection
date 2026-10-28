"""Phase 3A: schema, relationships and constraints. Every rejection test also checks WHICH constraint fired."""
import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import CheckConstraint, inspect, text
from sqlalchemy.exc import DBAPIError

from src.models import tables as t
from tests.helpers import (MACHINE, SENSOR, add, at, expect_violation, failure, machine_state, part,
                           seed_parents, sensor_status, shift, technician, wo_part, wo_status,
                           wo_technician, work_order)

NEW_TABLES = {"operating_shift", "technician", "part", "failure_event", "maintenance_work_order",
              "work_order_technician", "work_order_part", "machine_state_history",
              "sensor_status_history", "work_order_status_history"}


# ---------------------------------------------------------------- schema creation
def test_all_fifteen_tables_exist(engine, loaded):
    assert len(t.Base.metadata.tables) == 15
    assert set(t.Base.metadata.tables) <= set(inspect(engine).get_table_names())


def test_new_tables_have_expected_foreign_keys(engine, loaded):
    expected = {
        "operating_shift": {"machine"}, "technician": {"plant"}, "part": set(),
        "failure_event": {"machine"},
        "maintenance_work_order": {"machine", "failure_event"},
        "work_order_technician": {"maintenance_work_order", "technician"},
        "work_order_part": {"maintenance_work_order", "part"},
        "machine_state_history": {"machine", "maintenance_work_order", "failure_event"},
        "sensor_status_history": {"sensor"},
        "work_order_status_history": {"maintenance_work_order", "technician"},
    }
    insp = inspect(engine)
    for table, parents in expected.items():
        assert {fk["referred_table"] for fk in insp.get_foreign_keys(table)} == parents, table


def test_database_schema_matches_the_models(engine, loaded):
    """Drift check: the migrated database must equal src/models/tables.py (columns, types, FKs, indexes)."""
    with engine.connect() as c:
        diff = compare_metadata(MigrationContext.configure(c, opts={"compare_type": True}), t.Base.metadata)
    assert diff == []


def test_every_check_constraint_in_the_models_exists_in_the_database(engine, loaded):
    insp = inspect(engine)
    for table in t.Base.metadata.sorted_tables:
        in_models = {c.name for c in table.constraints if isinstance(c, CheckConstraint)}
        in_db = {c["name"] for c in insp.get_check_constraints(table.name)}
        assert in_models == in_db, table.name


def test_constraint_names_fit_postgresql_limit():
    names = [c.name for tb in t.Base.metadata.tables.values() for c in tb.constraints if c.name]
    names += [i.name for tb in t.Base.metadata.tables.values() for i in tb.indexes]
    assert max(len(str(n)) for n in names) <= 63


# ---------------------------------------------------------------- valid parent-child rows
def test_valid_chain_inserts_and_joins(conn):
    seed_parents(conn)
    add(conn, t.WorkOrderTechnician, wo_technician(hours_worked="3.5"))
    add(conn, t.WorkOrderPart, wo_part(quantity_used="2", replaced_at=at(12)))
    add(conn, t.OperatingShift, shift())
    row = conn.execute(text("""
        SELECT m.machine_id, f.failure_category, w.priority, tc.full_name, p.part_name, wp.quantity_used
        FROM maintenance_work_order w
        JOIN machine m USING (machine_id)
        JOIN failure_event f USING (failure_id)
        JOIN work_order_technician wt USING (work_order_id) JOIN technician tc USING (technician_id)
        JOIN work_order_part wp USING (work_order_id)       JOIN part p USING (part_id)
        WHERE w.work_order_id = 'WO-2026-000001'""")).one()
    assert tuple(row) == (MACHINE, "BEARING_WEAR", "HIGH", "Asha Rao", "Ball bearing 6204", 2)


def test_downtime_is_derived_from_source_timestamps(conn):
    add(conn, t.MaintenanceWorkOrder, work_order(downtime_start=at(10), returned_to_service_at=at(14.5)))
    minutes = conn.execute(text(
        "SELECT EXTRACT(EPOCH FROM (returned_to_service_at - downtime_start)) / 60 "
        "FROM maintenance_work_order")).scalar_one()
    assert float(minutes) == 270.0


# ---------------------------------------------------------------- invalid foreign keys
UNKNOWN = "DOES-NOT-EXIST"
# NOTE: each row uses IDs that do not clash with the seeded parents, so ONLY the foreign key can fail.
FK_CASES = [
    (t.OperatingShift, shift(machine_id=UNKNOWN), "fk_operating_shift_machine_id_machine"),
    (t.Technician, technician(technician_id="TECH-777", plant_id=UNKNOWN), "fk_technician_plant_id_plant"),
    (t.FailureEvent, failure(failure_id="FAIL-NEW-1", machine_id=UNKNOWN), "fk_failure_event_machine_id_machine"),
    (t.MaintenanceWorkOrder, work_order(work_order_id="WO-2026-000009", machine_id=UNKNOWN),
     "fk_maintenance_work_order_machine_id_machine"),
    (t.MaintenanceWorkOrder, work_order(work_order_id="WO-2026-000009", failure_id=UNKNOWN),
     "fk_maintenance_work_order_failure_id_failure_event"),
    (t.WorkOrderTechnician, wo_technician(technician_id=UNKNOWN),
     "fk_work_order_technician_technician_id_technician"),
    (t.WorkOrderTechnician, wo_technician(work_order_id=UNKNOWN),
     "fk_work_order_technician_work_order_id_maintenance_work_order"),
    (t.WorkOrderPart, wo_part(part_id=UNKNOWN), "fk_work_order_part_part_id_part"),
    (t.WorkOrderPart, wo_part(work_order_id=UNKNOWN),
     "fk_work_order_part_work_order_id_maintenance_work_order"),
    (t.MachineStateHistory, machine_state(machine_id=UNKNOWN), "fk_machine_state_history_machine_id_machine"),
    (t.SensorStatusHistory, sensor_status(sensor_id=UNKNOWN), "fk_sensor_status_history_sensor_id_sensor"),
    (t.WorkOrderStatusHistory, wo_status(work_order_id=UNKNOWN), "fk_wo_status_history_work_order"),
]


@pytest.mark.parametrize("model,row,constraint", FK_CASES, ids=[c[2] for c in FK_CASES])
def test_invalid_foreign_key_rejected(conn, model, row, constraint):
    seed_parents(conn)
    expect_violation(conn, model, row, constraint)


# ---------------------------------------------------------------- invalid enum / status values
ENUM_CASES = [
    (t.OperatingShift, shift(shift_name="EVENING"), "ck_operating_shift_name_enum"),
    (t.OperatingShift, shift(planned_state="BROKEN"), "ck_operating_shift_planned_state_enum"),
    (t.Technician, technician(specialty="WIZARD"), "ck_technician_specialty_enum"),
    (t.Technician, technician(status="RETIRED"), "ck_technician_status_enum"),
    (t.Part, part(category="MAGIC"), "ck_part_category_enum"),
    (t.Part, part(unit_of_measure="BOX"), "ck_part_unit_enum"),
    (t.Part, part(status="LOST"), "ck_part_status_enum"),
    (t.FailureEvent, failure(failure_category="GREMLINS"), "ck_failure_event_category_enum"),
    (t.FailureEvent, failure(severity="EXTREME"), "ck_failure_event_severity_enum"),
    (t.FailureEvent, failure(status="PENDING"), "ck_failure_event_status_enum"),
    (t.MaintenanceWorkOrder, work_order(work_order_id="WO-2026-000009", maintenance_type="PAINTING"),
     "ck_maintenance_work_order_type_enum"),
    (t.MaintenanceWorkOrder, work_order(work_order_id="WO-2026-000009", priority="WHENEVER"),
     "ck_maintenance_work_order_priority_enum"),
    (t.MaintenanceWorkOrder, work_order(work_order_id="WO-2026-000009", status="DONE"),
     "ck_maintenance_work_order_status_enum"),
    (t.WorkOrderTechnician, wo_technician(role="BOSS"), "ck_work_order_technician_role_enum"),
    (t.MachineStateHistory, machine_state(new_state="EXPLODED"), "ck_machine_state_history_new_state_enum"),
    (t.MachineStateHistory, machine_state(change_source="RUMOUR"), "ck_machine_state_history_source_enum"),
    (t.SensorStatusHistory, sensor_status(new_status="SLEEPY"), "ck_sensor_status_history_new_status_enum"),
]


@pytest.mark.parametrize("model,row,constraint", ENUM_CASES, ids=[c[2] for c in ENUM_CASES])
def test_invalid_enum_value_rejected(conn, model, row, constraint):
    seed_parents(conn)
    expect_violation(conn, model, row, constraint)


# ---------------------------------------------------------------- uniqueness
def test_duplicate_primary_keys_rejected(conn):
    seed_parents(conn)
    expect_violation(conn, t.Technician, technician(full_name="Other"), "pk_technician")
    expect_violation(conn, t.MaintenanceWorkOrder, work_order(), "pk_maintenance_work_order")
    add(conn, t.WorkOrderTechnician, wo_technician())
    expect_violation(conn, t.WorkOrderTechnician, wo_technician(role="ASSISTANT"), "pk_work_order_technician")
    add(conn, t.WorkOrderPart, wo_part())
    expect_violation(conn, t.WorkOrderPart, wo_part(quantity_used="5"), "pk_work_order_part")


def test_duplicate_part_number_rejected(conn):
    seed_parents(conn)
    expect_violation(conn, t.Part, part(part_id="PRT-0002"), "uq_part_part_number")


def test_machine_cannot_have_two_shifts_starting_at_the_same_time(conn):
    add(conn, t.OperatingShift, shift())
    expect_violation(conn, t.OperatingShift, shift(shift_id="SHF-A-20260301-X"), "uq_operating_shift_machine_id")


def test_machine_cannot_fail_twice_at_the_same_instant(conn):
    add(conn, t.FailureEvent, failure())
    expect_violation(conn, t.FailureEvent, failure(failure_id="FAIL-A-002"), "uq_failure_event_machine_id")


def test_history_cannot_have_two_changes_at_the_same_instant(conn):
    add(conn, t.MachineStateHistory, machine_state())
    expect_violation(conn, t.MachineStateHistory, machine_state(history_id="MSH-A-2", previous_state="RUNNING",
                                                                new_state="IDLE"),
                     "uq_machine_state_history_machine_id")


def test_only_one_lead_technician_per_work_order(conn):
    seed_parents(conn)
    add(conn, t.Technician, technician(technician_id="TECH-002", full_name="Ben Iyer"))
    add(conn, t.Technician, technician(technician_id="TECH-003", full_name="Chitra Nair"))
    add(conn, t.WorkOrderTechnician, wo_technician(technician_id="TECH-001", role="LEAD"))
    expect_violation(conn, t.WorkOrderTechnician, wo_technician(technician_id="TECH-002", role="LEAD"),
                     "uq_work_order_technician_one_lead")
    add(conn, t.WorkOrderTechnician, wo_technician(technician_id="TECH-002", role="ASSISTANT"))
    add(conn, t.WorkOrderTechnician, wo_technician(technician_id="TECH-003", role="ASSISTANT"))  # many assistants OK


# ---------------------------------------------------------------- dates, quantities, consistency
def test_shift_end_must_be_after_start_and_load_in_range(conn):
    expect_violation(conn, t.OperatingShift, shift(shift_end=at(0)), "ck_operating_shift_end_after_start")
    expect_violation(conn, t.OperatingShift, shift(shift_end=at(-1)), "ck_operating_shift_end_after_start")
    expect_violation(conn, t.OperatingShift, shift(planned_load_pct="120"), "ck_operating_shift_load_pct_range")


FAILURE_DATE_CASES = [
    (dict(symptom_onset_at=at(11), failure_at=at(10)), "ck_failure_event_onset_before_failure"),
    (dict(detected_at=at(-1)), "ck_failure_event_detected_after_onset"),
    (dict(status="RESOLVED", resolved_at=at(9)), "ck_failure_event_resolved_after_failure"),
    (dict(status="RESOLVED", resolved_at=None), "ck_failure_event_resolved_matches_status"),
    (dict(status="CONFIRMED", resolved_at=at(12)), "ck_failure_event_resolved_matches_status"),
]


@pytest.mark.parametrize("override,constraint", FAILURE_DATE_CASES, ids=[c[1] for c in FAILURE_DATE_CASES])
def test_failure_event_time_rules(conn, override, constraint):
    expect_violation(conn, t.FailureEvent, failure(**override), constraint)


def test_failure_event_valid_lifecycle_is_accepted(conn):
    add(conn, t.FailureEvent, failure(detected_at=at(9), status="RESOLVED", resolved_at=at(20)))


WORK_ORDER_CASES = [
    (dict(status="COMPLETED", created_at=at(11), started_at=at(13), completed_at=at(12)),
     "ck_maintenance_work_order_end_after_start"),                       # maintenance end BEFORE start
    (dict(status="IN_PROGRESS", started_at=at(10)), "ck_maintenance_work_order_start_after_created"),
    (dict(downtime_start=at(14), returned_to_service_at=at(13)), "ck_maintenance_work_order_downtime_order"),
    (dict(returned_to_service_at=at(13)), "ck_maintenance_work_order_downtime_order"),
    (dict(status="COMPLETED", started_at=at(12), completed_at=None),
     "ck_maintenance_work_order_status_matches_timestamps"),
    (dict(status="OPEN", started_at=at(12)), "ck_maintenance_work_order_status_matches_timestamps"),
    (dict(status="IN_PROGRESS", started_at=None), "ck_maintenance_work_order_status_matches_timestamps"),
]


@pytest.mark.parametrize("override,constraint", WORK_ORDER_CASES, ids=[f"{i}-{c[1][29:]}" for i, c in enumerate(WORK_ORDER_CASES)])
def test_work_order_time_and_status_rules(conn, override, constraint):
    expect_violation(conn, t.MaintenanceWorkOrder, work_order(**override), constraint)


def test_work_order_valid_lifecycles_are_accepted(conn):
    add(conn, t.MaintenanceWorkOrder, work_order(work_order_id="WO-2026-000001"))                  # OPEN
    add(conn, t.MaintenanceWorkOrder, work_order(work_order_id="WO-2026-000002", status="IN_PROGRESS",
                                                 started_at=at(12)))
    add(conn, t.MaintenanceWorkOrder, work_order(work_order_id="WO-2026-000003", status="COMPLETED",
                                                 started_at=at(12), completed_at=at(15)))
    add(conn, t.MaintenanceWorkOrder, work_order(work_order_id="WO-2026-000004", status="CANCELLED"))


def test_quantities_costs_and_hours_must_be_sensible(conn):
    seed_parents(conn)
    expect_violation(conn, t.Part, part(part_id="PRT-0002", part_number="X-2", unit_cost="-1"),
                     "ck_part_cost_non_negative")
    expect_violation(conn, t.WorkOrderPart, wo_part(quantity_used="0"), "ck_work_order_part_quantity_positive")
    expect_violation(conn, t.WorkOrderPart, wo_part(quantity_used="-3"), "ck_work_order_part_quantity_positive")
    expect_violation(conn, t.WorkOrderTechnician, wo_technician(hours_worked="-0.5"),
                     "ck_work_order_technician_hours_non_negative")


def test_state_and_status_history_rules(conn):
    seed_parents(conn)
    expect_violation(conn, t.MachineStateHistory, machine_state(previous_state="IDLE", new_state="IDLE"),
                     "ck_machine_state_history_state_really_changed")
    expect_violation(conn, t.MachineStateHistory,
                     machine_state(change_source="SCHEDULE", work_order_id="WO-2026-000001"),
                     "ck_machine_state_history_link_matches_source")
    expect_violation(conn, t.SensorStatusHistory, sensor_status(previous_status="FAULTY", new_status="FAULTY"),
                     "ck_sensor_status_history_status_really_changed")
    expect_violation(conn, t.SensorStatusHistory, sensor_status(previous_status="RETIRED", new_status="ACTIVE"),
                     "ck_sensor_status_history_retired_is_final")


def test_work_order_lifecycle_transition_rules(conn):
    seed_parents(conn)
    bad = [(None, "IN_PROGRESS"), (None, "COMPLETED"), ("OPEN", "COMPLETED"),
           ("COMPLETED", "IN_PROGRESS"), ("CANCELLED", "OPEN"), ("IN_PROGRESS", "OPEN")]
    for previous, new in bad:
        expect_violation(conn, t.WorkOrderStatusHistory, wo_status(previous_status=previous, new_status=new),
                         "ck_work_order_status_history_allowed_transition")
    for i, (previous, new) in enumerate([(None, "OPEN"), ("OPEN", "IN_PROGRESS"), ("IN_PROGRESS", "COMPLETED")]):
        add(conn, t.WorkOrderStatusHistory, wo_status(history_id=f"WSH-A-{i}", previous_status=previous,
                                                      new_status=new, changed_at=at(11 + i)))
    assert conn.execute(text("SELECT count(*) FROM work_order_status_history")).scalar_one() == 3


# ---------------------------------------------------------------- many-to-many associations
def test_work_order_technician_and_part_associations(conn):
    seed_parents(conn)
    add(conn, t.MaintenanceWorkOrder, work_order(work_order_id="WO-2026-000002", maintenance_type="PREVENTIVE"))
    add(conn, t.Technician, technician(technician_id="TECH-002", full_name="Ben Iyer", specialty="ELECTRICAL"))
    add(conn, t.Part, part(part_id="PRT-0002", part_number="SEAL-01", part_name="Shaft seal", category="SEAL"))
    # WO-1: two technicians, two parts.  WO-2: TECH-001 again and PRT-0001 again (N:M both ways)
    add(conn, t.WorkOrderTechnician, wo_technician(technician_id="TECH-001", role="LEAD"))
    add(conn, t.WorkOrderTechnician, wo_technician(technician_id="TECH-002", role="ASSISTANT"))
    add(conn, t.WorkOrderTechnician, wo_technician(work_order_id="WO-2026-000002", technician_id="TECH-001"))
    add(conn, t.WorkOrderPart, wo_part(part_id="PRT-0001", quantity_used="2"))
    add(conn, t.WorkOrderPart, wo_part(part_id="PRT-0002", quantity_used="1"))
    add(conn, t.WorkOrderPart, wo_part(work_order_id="WO-2026-000002", part_id="PRT-0001", quantity_used="4"))

    def scalar(q):
        return conn.execute(text(q)).scalars().all()

    assert scalar("SELECT technician_id FROM work_order_technician WHERE work_order_id='WO-2026-000001' "
                  "ORDER BY 1") == ["TECH-001", "TECH-002"]
    assert scalar("SELECT work_order_id FROM work_order_technician WHERE technician_id='TECH-001' "
                  "ORDER BY 1") == ["WO-2026-000001", "WO-2026-000002"]
    assert scalar("SELECT part_id FROM work_order_part WHERE work_order_id='WO-2026-000001' "
                  "ORDER BY 1") == ["PRT-0001", "PRT-0002"]
    assert float(conn.execute(text("SELECT sum(quantity_used) FROM work_order_part WHERE part_id='PRT-0001'"
                                   )).scalar_one()) == 6.0


# ---------------------------------------------------------------- history is preserved
def test_machine_state_history_keeps_every_change(conn):
    seed_parents(conn)
    steps = [  # (previous, new, hour, source, work_order, failure)
        (None, "RUNNING", 0, "SCHEDULE", None, None),
        ("RUNNING", "IDLE", 6, "SCHEDULE", None, None),
        ("IDLE", "RUNNING", 8, "SCHEDULE", None, None),
        ("RUNNING", "FAILED", 10, "FAILURE", None, "FAIL-A-001"),
        ("FAILED", "MAINTENANCE", 12, "WORK_ORDER", "WO-2026-000001", None),
        ("MAINTENANCE", "RUNNING", 16, "WORK_ORDER", "WO-2026-000001", None),
    ]
    for i, (prev, new, hour, source, wo, fl) in enumerate(steps):
        add(conn, t.MachineStateHistory, machine_state(history_id=f"MSH-A-{i}", previous_state=prev, new_state=new,
                                                       changed_at=at(hour), change_source=source,
                                                       work_order_id=wo, failure_id=fl))
    rows = conn.execute(text("SELECT previous_state, new_state FROM machine_state_history "
                             "WHERE machine_id=:m ORDER BY changed_at"), {"m": MACHINE}).all()
    assert [r.new_state for r in rows] == ["RUNNING", "IDLE", "RUNNING", "FAILED", "MAINTENANCE", "RUNNING"]
    assert [r.previous_state for r in rows[1:]] == [r.new_state for r in rows[:-1]]  # unbroken chain
    assert sum(r.new_state == "RUNNING" for r in rows) == 3   # RUNNING appears 3 times: nothing overwritten


@pytest.mark.parametrize("model,row", [
    (t.MachineStateHistory, machine_state()),
    (t.SensorStatusHistory, sensor_status()),
    (t.WorkOrderStatusHistory, wo_status()),
], ids=["machine_state_history", "sensor_status_history", "work_order_status_history"])
def test_history_tables_are_append_only(conn, model, row):
    seed_parents(conn)
    add(conn, model, row)
    table = model.__tablename__
    for statement in (f"UPDATE {table} SET history_id = history_id",   # even a no-op update is blocked
                      f"DELETE FROM {table}"):
        with pytest.raises(DBAPIError) as exc:
            with conn.begin_nested():
                conn.execute(text(statement))
        assert "append-only" in str(exc.value)
    assert conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 1
