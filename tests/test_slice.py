from datetime import datetime, timezone

import pandas as pd
import pytest
from dataclasses import replace
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from src.exports.checksums import telemetry_checksum
from src.generator import ids
from src.generator.hierarchy import build_hierarchy
from src.generator.pipeline import load_dataset, table_counts
from src.generator.telemetry import generate_sensor_readings


# ---------- IDs ----------
def test_id_formats():
    assert ids.plant_id(1) == "PLT-001"
    assert ids.line_id("PLT-001", 1) == "LINE-PLT-001-001"
    assert ids.machine_id("LINE-PLT-001-001", 1) == "MCH-LINE-PLT-001-001-001"
    assert ids.sensor_id("MCH-LINE-PLT-001-001-001", "TEMP", 1) == "SNS-MCH-LINE-PLT-001-001-001-TEMP-01"
    assert ids.work_order_id(2026, 1) == "WO-2026-000001"


def test_telemetry_id_collision_suffix():
    ts = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    assert ids.telemetry_id("SNS-X", ts) == "TEL-SNS-X-20260101T000000Z"
    assert ids.telemetry_id("SNS-X", ts, 1) == "TEL-SNS-X-20260101T000000Z-01"
    assert ids.telemetry_id("SNS-X", ts) != ids.telemetry_id("SNS-X", ts, 1)


def test_generated_telemetry_ids_match_id_function(cfg):
    sensor = build_hierarchy(cfg)["sensors"][0]
    df = generate_sensor_readings(cfg, sensor, 0)
    first = ids.telemetry_id(sensor["sensor_id"], df["event_ts"].iloc[0].to_pydatetime())
    assert df["telemetry_id"].iloc[0] == first


# ---------- Hierarchy (in memory) ----------
def test_hierarchy_counts_unique_ids_and_valid_parents(cfg):
    h = build_hierarchy(cfg)
    assert (len(h["plants"]), len(h["lines"]), len(h["machines"]), len(h["sensors"])) == (1, 2, 4, 8)
    for key, col in (("plants", "plant_id"), ("lines", "line_id"),
                     ("machines", "machine_id"), ("sensors", "sensor_id")):
        values = [r[col] for r in h[key]]
        assert len(values) == len(set(values))
    assert {l["plant_id"] for l in h["lines"]} <= {p["plant_id"] for p in h["plants"]}
    assert {m["line_id"] for m in h["machines"]} <= {l["line_id"] for l in h["lines"]}
    assert {s["machine_id"] for s in h["sensors"]} <= {m["machine_id"] for m in h["machines"]}


# ---------- Determinism (in memory) ----------
def _frame_hash(df):
    return pd.util.hash_pandas_object(df, index=False).sum()


def test_same_seed_same_data(cfg):
    s = build_hierarchy(cfg)["sensors"][0]
    assert _frame_hash(generate_sensor_readings(cfg, s, 0)) == _frame_hash(generate_sensor_readings(cfg, s, 0))


def test_different_seed_different_data(cfg):
    s = build_hierarchy(cfg)["sensors"][0]
    other = replace(cfg, seed=cfg.seed + 1)
    assert _frame_hash(generate_sensor_readings(cfg, s, 0)) != _frame_hash(generate_sensor_readings(other, s, 0))


def test_values_are_physically_plausible(cfg):
    for idx, s in enumerate(build_hierarchy(cfg)["sensors"]):
        df = generate_sensor_readings(cfg, s, idx)
        assert df["reading_value"].between(float(s["min_plausible"]), float(s["max_plausible"])).all()
        run = df.loc[df.machine_state == "RUNNING", "reading_value"].mean()
        idle = df.loc[df.machine_state == "IDLE", "reading_value"].mean()
        assert run > idle  # running machines read higher than idle ones


# ---------- Database ----------
def test_tables_and_foreign_keys_exist(engine, loaded):
    insp = inspect(engine)
    assert {"plant", "production_line", "machine", "sensor", "telemetry_event"} <= set(insp.get_table_names())
    expected = {"production_line": "plant", "machine": "production_line",
                "sensor": "machine", "telemetry_event": "sensor"}
    for table, parent in expected.items():
        assert parent in {fk["referred_table"] for fk in insp.get_foreign_keys(table)}


def test_row_counts_match_config(engine, cfg, loaded):
    c = table_counts(engine)
    assert c["plant"] == 1 and c["production_line"] == 2 and c["machine"] == 4 and c["sensor"] == 8
    assert c["telemetry_event"] == 8 * cfg.readings_per_sensor == loaded["telemetry"]


def test_no_orphan_rows(engine, loaded):
    sql = {
        "line": "SELECT count(*) FROM production_line l LEFT JOIN plant p USING (plant_id) WHERE p.plant_id IS NULL",
        "machine": "SELECT count(*) FROM machine m LEFT JOIN production_line l USING (line_id) WHERE l.line_id IS NULL",
        "sensor": "SELECT count(*) FROM sensor s LEFT JOIN machine m USING (machine_id) WHERE m.machine_id IS NULL",
        "telemetry": "SELECT count(*) FROM telemetry_event t LEFT JOIN sensor s USING (sensor_id) WHERE s.sensor_id IS NULL",
    }
    with engine.connect() as c:
        for name, q in sql.items():
            assert c.execute(text(q)).scalar_one() == 0, name


def test_sample_telemetry_rows(engine, loaded):
    with engine.connect() as c:
        row = c.execute(text(
            "SELECT telemetry_id, sensor_id, reading_value, unit, machine_state "
            "FROM telemetry_event WHERE sensor_id LIKE '%TEMP-01' ORDER BY event_ts LIMIT 1")).one()
    assert row.telemetry_id == f"TEL-{row.sensor_id}-20260101T000000Z"
    assert row.unit == "degC" and row.machine_state == "IDLE"  # 00:00 UTC is an idle hour
    assert 30 < float(row.reading_value) < 50


def test_database_rejects_unknown_sensor(engine, loaded):
    """Negative scenario #1 can NOT be stored in the real table: PostgreSQL's FK blocks it.
    It will live in the separate exceptions dataset instead (Phase 4)."""
    with pytest.raises(IntegrityError):
        with engine.begin() as c:
            c.execute(text(
                "INSERT INTO telemetry_event VALUES ('TEL-BAD-20260101T000000Z','SNS-DOES-NOT-EXIST',"
                "now(), 1.0, 'degC', 'RUNNING')"))


def test_database_rejects_invalid_enum(engine, loaded):
    with pytest.raises(IntegrityError):
        with engine.begin() as c:
            c.execute(text("UPDATE machine SET status='BROKEN-ISH' WHERE machine_id = "
                           "(SELECT min(machine_id) FROM machine)"))


# ---------- Reproducibility in the database ----------
def test_checksum_identical_after_reload_and_across_batch_sizes(engine, cfg, loaded):
    first = telemetry_checksum(engine)
    load_dataset(engine, replace(cfg, batch_size=100), reset=True)    # many tiny batches
    second = telemetry_checksum(engine)
    load_dataset(engine, replace(cfg, batch_size=10_000_000), reset=True)  # one big batch
    third = telemetry_checksum(engine)
    assert first and first == second == third
