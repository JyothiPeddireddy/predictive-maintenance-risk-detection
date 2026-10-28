"""Migration safety. Each test works in a throw-away database (pm_migration_scratch_test) that is created
and dropped by the test itself. The development database is never touched."""
import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError

from src import cli, migrate
from src.db import get_engine
from src.exports.checksums import telemetry_checksum
from src.generator.pipeline import load_dataset
from src.models.tables import Base

SCRATCH = "pm_migration_scratch_test"
STARTER = ["plant", "production_line", "machine", "sensor", "telemetry_event"]
NEW = sorted(set(Base.metadata.tables) - set(STARTER))


@pytest.fixture
def scratch(engine):
    admin = engine.execution_options(isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as c:
            c.execute(text(f"DROP DATABASE IF EXISTS {SCRATCH} WITH (FORCE)"))
            c.execute(text(f"CREATE DATABASE {SCRATCH}"))
    except DBAPIError as exc:  # e.g. the user has no CREATEDB permission
        pytest.skip(f"cannot create scratch database (grant CREATEDB to your user): {exc.orig}")
    eng = get_engine(SCRATCH)
    yield eng
    eng.dispose()
    with admin.connect() as c:
        c.execute(text(f"DROP DATABASE IF EXISTS {SCRATCH} WITH (FORCE)"))


def make_phase2_database(eng, cfg):
    """Re-creates exactly what the Phase 2 starter produced: the 5 tables (built with create_all, as
    Phase 2 did - this is the ONLY place create_all is still used, to imitate the old state) + starter data."""
    Base.metadata.create_all(eng, tables=[Base.metadata.tables[t] for t in STARTER])
    load_dataset(eng, cfg, reset=False)


def starter_counts(eng):
    with eng.connect() as c:
        return {t: c.execute(text(f"SELECT count(*) FROM {t}")).scalar_one() for t in STARTER}


def tables(eng):
    return set(inspect(eng).get_table_names())


def test_there_is_exactly_one_migration_head():
    heads = ScriptDirectory.from_config(migrate._config()).get_heads()
    assert heads == [migrate.head_revision()] and len(heads) == 1


def test_fresh_empty_database_upgrades_to_latest(scratch):
    assert migrate.current_revision(scratch) is None
    migrate.upgrade(scratch)
    assert migrate.current_revision(scratch) == migrate.head_revision()
    assert set(Base.metadata.tables) <= tables(scratch)
    assert len(Base.metadata.tables) == 15
    assert sum(starter_counts(scratch).values()) == 0


def test_existing_phase2_database_keeps_all_data_when_upgraded(scratch, cfg):
    make_phase2_database(scratch, cfg)
    assert tables(scratch) >= set(STARTER) and not (tables(scratch) & set(NEW))   # really the old shape
    counts_before, md5_before = starter_counts(scratch), telemetry_checksum(scratch)
    assert counts_before["telemetry_event"] == 2304

    migrate.upgrade(scratch)

    assert migrate.current_revision(scratch) == migrate.head_revision()
    assert set(NEW) <= tables(scratch)                                  # new tables arrived
    assert starter_counts(scratch) == counts_before                     # no row lost or added
    assert telemetry_checksum(scratch) == md5_before                    # and not a single value changed
    with scratch.connect() as c:                                        # new tables start empty
        assert all(c.execute(text(f"SELECT count(*) FROM {t}")).scalar_one() == 0 for t in NEW)


def test_running_upgrade_twice_changes_nothing(scratch, cfg):
    make_phase2_database(scratch, cfg)
    migrate.upgrade(scratch)
    md5, counts = telemetry_checksum(scratch), starter_counts(scratch)
    migrate.upgrade(scratch)
    assert migrate.current_revision(scratch) == migrate.head_revision()
    assert (telemetry_checksum(scratch), starter_counts(scratch)) == (md5, counts)


def test_downgrading_new_tables_keeps_starter_data(scratch, cfg):
    make_phase2_database(scratch, cfg)
    migrate.upgrade(scratch)
    md5 = telemetry_checksum(scratch)
    migrate.downgrade(scratch, "0001")
    assert migrate.current_revision(scratch) == "0001"
    assert not (tables(scratch) & set(NEW))
    assert telemetry_checksum(scratch) == md5


def test_baseline_refuses_to_downgrade_and_loses_nothing(scratch, cfg):
    make_phase2_database(scratch, cfg)
    migrate.upgrade(scratch)
    with pytest.raises(RuntimeError, match="Refusing"):
        migrate.downgrade(scratch, "base")
    assert set(STARTER) <= tables(scratch)
    assert starter_counts(scratch)["telemetry_event"] == 2304


def test_half_built_starter_schema_is_reported_not_guessed(scratch):
    Base.metadata.create_all(scratch, tables=[Base.metadata.tables["plant"]])
    with pytest.raises(RuntimeError, match="Only some starter tables exist"):
        migrate.upgrade(scratch)


# ---- CLI safety guard ----
def test_destructive_commands_refused_on_non_test_database():
    dev_engine = get_engine("predictive_maintenance")      # lazy: no connection is made
    with pytest.raises(SystemExit) as exc:
        cli._guard_destructive(dev_engine, force=False)
    assert "REFUSED" in str(exc.value)


def test_destructive_commands_allowed_on_test_database_or_with_force():
    cli._guard_destructive(get_engine("predictive_maintenance_test"), force=False)   # no exception
    cli._guard_destructive(get_engine("predictive_maintenance"), force=True)          # no exception


# ---- generated documentation must match the models ----
def test_generated_docs_are_up_to_date():
    from pathlib import Path
    from src.exports.schema_docs import build_data_dictionary, build_schema_sql
    root = Path(__file__).resolve().parent.parent
    assert (root / "schemas/schema.sql").read_text(encoding="utf-8") == build_schema_sql(), \
        "run: python -m src.cli export-schema"
    assert (root / "schemas/data_dictionary.md").read_text(encoding="utf-8") == build_data_dictionary(), \
        "run: python -m src.cli export-dictionary"
    for table in Base.metadata.tables:
        assert f"## `{table}`" in build_data_dictionary()
