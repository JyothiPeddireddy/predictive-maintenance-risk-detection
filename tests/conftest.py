import os

import pytest
from sqlalchemy import text

from src.config import load_config
from src.db import get_engine
from src.generator.pipeline import load_dataset


@pytest.fixture(scope="session")
def engine():
    name = os.getenv("PM_TEST_DB_NAME", "predictive_maintenance_test")
    # Safety guard: tests DROP tables, so never run them against the real database.
    assert name.endswith("_test"), f"Refusing to run tests on database '{name}' (must end with _test)"
    eng = get_engine(name)
    with eng.connect() as c:
        c.execute(text("select 1"))
    return eng


@pytest.fixture(scope="session")
def cfg():
    return load_config("config/starter.json")


@pytest.fixture(scope="session")
def loaded(engine, cfg):
    return load_dataset(engine, cfg, reset=True)


@pytest.fixture
def conn(engine, loaded):
    """A connection whose changes are always rolled back, so tests never leave data behind."""
    with engine.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()
