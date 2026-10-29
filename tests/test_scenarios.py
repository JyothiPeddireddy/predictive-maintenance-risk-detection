"""Phase 3B tests: failure scenarios, sensor faults, maintenance records, safe loading, reproducibility.

The in-memory tests need no database. The database tests load config/dev_scenarios.json into the *_test
database (never the real one) and, when finished, put the plain starter data back so the other test files
see exactly what they expect.
"""
import json
from dataclasses import replace
from datetime import timedelta

import numpy as np
import pytest
from sqlalchemy import text

from src import cli
from src.config import load_config
from src.db import get_engine
from src.exports.checksums import all_table_checksums
from src.generator.hierarchy import SENSOR_SPECS, build_hierarchy
from src.generator.pipeline import DatabaseNotEmptyError, assert_database_empty, load_dataset
from src.generator.scenarios import CATEGORIES, FAULT_TYPES, apply_scenarios, plan_scenarios
from src.generator.telemetry import generate_sensor_readings


@pytest.fixture(scope="module")
def dev_cfg():
    return load_config("config/dev_scenarios.json")


@pytest.fixture(scope="module")
def hier(dev_cfg):
    return build_hierarchy(dev_cfg)


@pytest.fixture(scope="module")
def plan(dev_cfg, hier):
    return plan_scenarios(dev_cfg, hier)


# =====================================================================================
# In memory: configuration and planning
# =====================================================================================
def test_scenarios_are_off_for_starter_and_full_configs():
    assert not load_config("config/starter.json").scenarios_enabled
    assert not load_config("config/full.json").scenarios_enabled
    assert load_config("config/dev_scenarios.json").scenarios_enabled


def test_plan_is_deterministic_and_depends_on_seed(dev_cfg, hier, plan):
    assert plan == plan_scenarios(dev_cfg, hier)
    assert plan != plan_scenarios(replace(dev_cfg, seed=dev_cfg.seed + 1), hier)


def test_plan_covers_every_failure_category_and_sensor_fault_type(plan):
    assert {f.category for f in plan.failures} == set(CATEGORIES)
    assert {x.fault_type for x in plan.sensor_faults} == set(FAULT_TYPES)
    assert len({f.machine_id for f in plan.failures}) == len(plan.failures)   # one failure per machine
    assert len({x.sensor_id for x in plan.sensor_faults}) == len(plan.sensor_faults)


def test_plan_includes_weak_signal_failures_and_healthy_machines(plan, hier):
    gains = sorted(f.gain for f in plan.failures)
    assert gains[0] < 0.55 and gains[-1] > 0.7          # some subtle, some obvious
    assert len(plan.failures) < len(hier["machines"])    # healthy machines exist
    assert plan.benign and plan.preventive


def test_failure_timelines_are_valid(plan, dev_cfg):
    for f in plan.failures:
        assert f.onset >= dev_cfg.start + timedelta(days=3)                   # healthy days come first
        assert f.onset <= f.detected_at <= f.failure_at
        assert f.onset < f.failure_at < f.wo_created < f.wo_started < f.wo_completed < f.returned_to_service
        assert f.returned_to_service <= dev_cfg.end - timedelta(days=3)       # repair finishes inside the data


def test_nothing_overlaps_a_failure_window_on_the_same_machine(plan):
    for f in plan.failures:
        for x in plan.sensor_faults:
            if x.machine_id == f.machine_id:
                assert x.end <= f.onset or x.start >= f.returned_to_service
        for p in plan.preventive:
            if p.machine_id == f.machine_id:
                assert p.completed_at <= f.failure_at or p.started_at >= f.returned_to_service


def test_scenario_count_limits_are_checked(dev_cfg, hier):
    with pytest.raises(ValueError):
        plan_scenarios(replace(dev_cfg, n_failures=99), hier)
    with pytest.raises(ValueError):
        plan_scenarios(replace(dev_cfg, days=8), hier)


# =====================================================================================
# In memory: telemetry effects
# =====================================================================================
def _frame(cfg, hier, plan, sensor_id):
    idx = next(i for i, s in enumerate(hier["sensors"]) if s["sensor_id"] == sensor_id)
    s = hier["sensors"][idx]
    base = generate_sensor_readings(cfg, s, idx)
    return base, apply_scenarios(cfg, s, idx, base, plan, SENSOR_SPECS[s["sensor_type"]])


def _sensor_of(hier, machine, kind):
    return next(s["sensor_id"] for s in hier["sensors"] if s["machine_id"] == machine and s["sensor_type"] == kind)


@pytest.mark.parametrize("category,kind", [("BEARING_WEAR", "VIB"), ("OVERHEATING", "TEMP"),
                                           ("LUBRICATION", "VIB"), ("MISALIGNMENT", "VIB")])
def test_failures_raise_the_expected_sensor_before_failing(dev_cfg, hier, plan, category, kind):
    f = next(f for f in plan.failures if f.category == category)
    base, out = _frame(dev_cfg, hier, plan, _sensor_of(hier, f.machine_id, kind))
    run = out.machine_state == "RUNNING"
    before = out[run & (out.event_ts < f.onset)].reading_value.mean()
    last_day = out[run & (out.event_ts >= f.failure_at - timedelta(hours=24)) & (out.event_ts < f.failure_at)]
    assert last_day.reading_value.mean() > before * 1.15
    # nothing changes before the onset (only maintenance/benign windows could differ, and they are not here)
    early = out.event_ts < f.onset
    assert (out.loc[early, "reading_value"].to_numpy() == base.loc[early, "reading_value"].to_numpy()).mean() > 0.9


def test_degradation_grows_over_time(dev_cfg, hier, plan):
    f = next(f for f in plan.failures if f.category == "BEARING_WEAR")
    _, out = _frame(dev_cfg, hier, plan, _sensor_of(hier, f.machine_id, "VIB"))
    run = out[out.machine_state == "RUNNING"]
    span = f.failure_at - f.onset
    early = run[(run.event_ts >= f.onset) & (run.event_ts < f.onset + span / 3)].reading_value.mean()
    late = run[(run.event_ts >= f.failure_at - span / 3) & (run.event_ts < f.failure_at)].reading_value.mean()
    assert late > early


def test_machine_is_stopped_between_failure_and_return_to_service(dev_cfg, hier, plan):
    f = plan.failures[0]
    _, out = _frame(dev_cfg, hier, plan, _sensor_of(hier, f.machine_id, "TEMP"))
    down = out[(out.event_ts >= f.failure_at) & (out.event_ts < f.returned_to_service)]
    assert len(down) > 0 and (down.machine_state == "MAINTENANCE").all()
    assert down.reading_value.mean() < 55                       # idle-level temperature, not 70+
    after = out[out.event_ts >= f.returned_to_service + timedelta(hours=1)]
    assert (after.machine_state != "MAINTENANCE").any()


def test_sensor_fault_signatures(dev_cfg, hier, plan):
    for x in plan.sensor_faults:
        base, out = _frame(dev_cfg, hier, plan, x.sensor_id)
        inside = (out.event_ts >= x.start) & (out.event_ts < x.end)
        assert inside.sum() >= 3
        values = out.loc[inside, "reading_value"]
        if x.fault_type == "DROPOUT":
            assert values.isna().all() and out.loc[~inside, "reading_value"].notna().all()
        elif x.fault_type == "FLATLINE":
            assert values.nunique() == 1 and values.notna().all()
        else:  # DRIFT grows, so the end of the episode is clearly above the baseline
            diff = (out.reading_value - base.reading_value)[inside].to_numpy()
            assert diff[-1] > diff[0] and diff[-1] > 0.5 * x.amplitude


def test_untouched_sensors_equal_the_healthy_baseline(dev_cfg, hier, plan):
    touched = {f.machine_id for f in plan.failures} | {b.machine_id for b in plan.benign} \
        | {p.machine_id for p in plan.preventive} | {x.machine_id for x in plan.sensor_faults}
    # every machine has preventive maintenance in this config, so build a plan without it
    quiet = plan_scenarios(replace(dev_cfg, pm_interval_days=0, n_benign_events=0, n_sensor_faults=0), hier)
    machine = next(m["machine_id"] for m in hier["machines"] if m["machine_id"] not in {f.machine_id for f in quiet.failures})
    base, out = _frame(dev_cfg, hier, quiet, _sensor_of(hier, machine, "VIB"))
    assert base.equals(out)
    assert touched                                              # sanity: the full plan does touch machines


def test_readings_stay_in_the_plausible_range(dev_cfg, hier, plan):
    for idx, s in enumerate(hier["sensors"]):
        out = apply_scenarios(dev_cfg, s, idx, generate_sensor_readings(dev_cfg, s, idx), plan,
                              SENSOR_SPECS[s["sensor_type"]])
        v = out.reading_value.dropna()
        assert v.between(float(s["min_plausible"]), float(s["max_plausible"])).all()
        assert np.allclose(v, v.round(3))


def test_effects_are_reproducible(dev_cfg, hier, plan):
    sid = _sensor_of(hier, plan.failures[0].machine_id, "VIB")
    _, a = _frame(dev_cfg, hier, plan, sid)
    _, b = _frame(dev_cfg, hier, plan, sid)
    assert a.equals(b)


# =====================================================================================
# Database
# =====================================================================================
@pytest.fixture(scope="module")
def scenario_db(engine, dev_cfg, tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("manifest")
    cfg = replace(dev_cfg, output_dir=str(out_dir))
    result = load_dataset(engine, cfg, reset=True)
    try:
        yield dict(engine=engine, cfg=cfg, result=result, out_dir=out_dir)
    finally:  # restore the plain starter data for the other test files
        load_dataset(engine, load_config("config/starter.json"), reset=True)


def q(db, sql, **params):
    with db["engine"].connect() as c:
        return c.execute(text(sql), params).all()


def test_scenario_load_counts(scenario_db, dev_cfg, plan, hier):
    r = scenario_db["result"]
    assert r["telemetry"] == len(hier["sensors"]) * dev_cfg.readings_per_sensor
    assert r["failure_event"] == len(plan.failures) == 6
    assert r["maintenance_work_order"] == len(plan.failures) + len(plan.preventive) + len(plan.sensor_faults)
    assert r["technician"] == 6 and r["part"] >= 10
    assert r["operating_shift"] == len(hier["machines"]) * dev_cfg.days * 3
    assert q(scenario_db, "SELECT count(*) FROM telemetry_event")[0][0] == r["telemetry"]


def test_every_failure_has_one_resolved_corrective_order_with_downtime(scenario_db):
    rows = q(scenario_db, """
        SELECT f.failure_id, f.status, count(w.work_order_id), min(w.maintenance_type),
               min(w.returned_to_service_at - w.downtime_start), min(w.downtime_start - f.failure_at)
        FROM failure_event f LEFT JOIN maintenance_work_order w USING (failure_id) GROUP BY f.failure_id, f.status""")
    assert len(rows) == 6
    for _, status, n, mtype, downtime, start_gap in rows:
        assert status == "RESOLVED" and n == 1 and mtype == "CORRECTIVE"
        assert downtime > timedelta(hours=2) and start_gap == timedelta(0)


def test_all_maintenance_types_present_with_parts_and_crews(scenario_db):
    types = {r[0]: r[1] for r in q(scenario_db, "SELECT maintenance_type, count(*) FROM maintenance_work_order GROUP BY 1")}
    assert set(types) == {"CORRECTIVE", "PREVENTIVE", "INSPECTION"}
    assert q(scenario_db, """SELECT count(*) FROM maintenance_work_order w
                             WHERE (SELECT count(*) FROM work_order_technician t
                                    WHERE t.work_order_id = w.work_order_id AND t.role = 'LEAD') <> 1""")[0][0] == 0
    assert q(scenario_db, """SELECT count(*) FROM maintenance_work_order w
                             WHERE w.maintenance_type <> 'INSPECTION'
                               AND NOT EXISTS (SELECT 1 FROM work_order_part p WHERE p.work_order_id = w.work_order_id)""")[0][0] == 0
    assert q(scenario_db, "SELECT count(DISTINCT part_id) FROM work_order_part")[0][0] >= 6


def test_inactive_technicians_are_never_assigned(scenario_db):
    assert q(scenario_db, """SELECT count(*) FROM work_order_technician b JOIN technician t USING (technician_id)
                             WHERE t.status <> 'ACTIVE'""")[0][0] == 0
    assert q(scenario_db, "SELECT count(*) FROM technician WHERE status = 'ON_LEAVE'")[0][0] == 1


def test_no_technician_works_two_jobs_at_once(scenario_db):
    overlaps = q(scenario_db, """
        SELECT count(*) FROM work_order_technician a
        JOIN maintenance_work_order wa ON wa.work_order_id = a.work_order_id
        JOIN work_order_technician b ON b.technician_id = a.technician_id AND b.work_order_id > a.work_order_id
        JOIN maintenance_work_order wb ON wb.work_order_id = b.work_order_id
        WHERE wa.started_at < wb.completed_at AND wb.started_at < wa.completed_at""")
    assert overlaps[0][0] == 0


def test_work_order_status_history_is_complete(scenario_db):
    rows = q(scenario_db, """SELECT work_order_id, array_agg(new_status ORDER BY changed_at)
                             FROM work_order_status_history GROUP BY 1""")
    assert len(rows) == scenario_db["result"]["maintenance_work_order"]
    assert all(r[1] == ["OPEN", "IN_PROGRESS", "COMPLETED"] for r in rows)


def test_machine_state_history_is_a_consistent_chain(scenario_db):
    rows = q(scenario_db, """SELECT machine_id, previous_state, new_state, change_source, failure_id, work_order_id
                             FROM machine_state_history ORDER BY machine_id, changed_at""")
    last = {}
    for machine, prev, new, source, failure, wo in rows:
        assert prev == last.get(machine)                       # chain: previous = the earlier new state
        last[machine] = new
        if new == "FAILED":
            assert source == "FAILURE" and failure is not None
    assert set(last.values()) <= {"IDLE", "RUNNING"}            # every machine is back in service at the end
    assert sum(1 for r in rows if r[2] == "FAILED") == 6
    assert len(last) == 12


def test_sensor_status_history_matches_the_plan(scenario_db, plan):
    rows = q(scenario_db, "SELECT sensor_id, previous_status, new_status FROM sensor_status_history")
    assert sum(1 for r in rows if r[2] == "FAULTY") == len(plan.sensor_faults)
    assert sum(1 for r in rows if r[1] is None) == 48
    assert {r[0] for r in q(scenario_db, "SELECT sensor_id FROM sensor WHERE status <> 'ACTIVE'")} == set()


def test_dropouts_are_nulls_flatlines_are_constant_in_the_database(scenario_db, plan):
    for x in plan.sensor_faults:
        if x.fault_type == "DROPOUT":
            n = q(scenario_db, """SELECT count(*) FROM telemetry_event WHERE sensor_id = :s
                                  AND event_ts >= :a AND event_ts < :b AND reading_value IS NULL""",
                  s=x.sensor_id, a=x.start, b=x.end)[0][0]
            assert n >= 3
        if x.fault_type == "FLATLINE":
            n = q(scenario_db, """SELECT count(DISTINCT reading_value) FROM telemetry_event WHERE sensor_id = :s
                                  AND event_ts >= :a AND event_ts < :b""", s=x.sensor_id, a=x.start, b=x.end)[0][0]
            assert n == 1
    all_nulls = q(scenario_db, "SELECT count(*) FROM telemetry_event WHERE reading_value IS NULL")[0][0]
    dropouts = [x for x in plan.sensor_faults if x.fault_type == "DROPOUT"]
    inside = sum(q(scenario_db, """SELECT count(*) FROM telemetry_event WHERE sensor_id = :s
                                   AND event_ts >= :a AND event_ts < :b AND reading_value IS NULL""",
                   s=x.sensor_id, a=x.start, b=x.end)[0][0] for x in dropouts)
    assert all_nulls == inside                                  # no stray missing values anywhere else


def test_telemetry_state_matches_the_down_windows(scenario_db, plan, hier, dev_cfg):
    expected = 0
    per_sensor = {m["machine_id"]: sum(1 for s in hier["sensors"] if s["machine_id"] == m["machine_id"]) for m in hier["machines"]}
    step = timedelta(seconds=dev_cfg.sampling_interval_s)
    for machine, n_sensors in per_sensor.items():
        for a, b in plan.down_windows(machine):
            first = -(-(a - dev_cfg.start) // step)            # ceil
            last = -(-(b - dev_cfg.start) // step)
            expected += max(0, last - first) * n_sensors
    got = q(scenario_db, "SELECT count(*) FROM telemetry_event WHERE machine_state = 'MAINTENANCE'")[0][0]
    assert got == expected


def test_manifest_matches_database(scenario_db):
    manifest = json.loads((scenario_db["out_dir"] / "scenario_manifest.json").read_text(encoding="utf-8"))
    in_db = {r[0] for r in q(scenario_db, "SELECT failure_id FROM failure_event")}
    assert {f["failure_id"] for f in manifest["failures"]} == in_db
    assert len(manifest["sensor_faults"]) == 6 and len(manifest["benign_events"]) == 4


# ---------- safety ----------
def test_loading_into_a_non_empty_database_is_refused(scenario_db, dev_cfg):
    with pytest.raises(DatabaseNotEmptyError):
        assert_database_empty(scenario_db["engine"])
    with pytest.raises(DatabaseNotEmptyError):
        load_dataset(scenario_db["engine"], scenario_db["cfg"], reset=False)


def test_scenario_loads_are_refused_for_the_original_database(dev_cfg):
    with pytest.raises(SystemExit) as exc:
        cli._guard_scenario_load(get_engine("predictive_maintenance"), dev_cfg)   # lazy: no connection is made
    assert "REFUSED" in str(exc.value)
    cli._guard_scenario_load(get_engine("predictive_maintenance_dev"), dev_cfg)  # a separate dev database is fine
    cli._guard_scenario_load(get_engine("predictive_maintenance"), load_config("config/starter.json"))  # starter is fine


def test_dev_databases_may_be_reset_but_not_the_original_without_force():
    cli._guard_destructive(get_engine("predictive_maintenance_dev"), force=False)
    with pytest.raises(SystemExit):
        cli._guard_destructive(get_engine("predictive_maintenance"), force=False)


# ---------- reproducibility (runs last: it reloads the database) ----------
def test_same_config_gives_identical_checksums_and_other_seed_does_not(scenario_db):
    eng, cfg = scenario_db["engine"], scenario_db["cfg"]
    first = all_table_checksums(eng)
    assert all(first[t] for t in ("telemetry_event", "failure_event", "maintenance_work_order",
                                  "machine_state_history", "operating_shift"))
    load_dataset(eng, replace(cfg, batch_size=7_777), reset=True)        # different batching, same data
    assert all_table_checksums(eng) == first
    load_dataset(eng, replace(cfg, seed=cfg.seed + 1), reset=True)
    assert all_table_checksums(eng)["telemetry_event"] != first["telemetry_event"]
    load_dataset(eng, cfg, reset=True)                                    # leave the module data as it was
    assert all_table_checksums(eng) == first
