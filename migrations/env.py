"""Alembic environment. Connection details come from src/db.py (environment variables / .env),
never from alembic.ini, so no password is ever stored in the repository."""
from alembic import context

from src.db import get_engine
from src.models.tables import Base

config = context.config
target_metadata = Base.metadata


def run_migrations_online() -> None:
    # src/migrate.py passes in an already-open connection (used by the CLI and by tests).
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    # Fallback for running the plain `alembic` command from a terminal.
    engine = get_engine()
    with engine.connect() as conn:
        _run(conn)
    engine.dispose()


def _run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("Offline (--sql) mode is not supported in this project.")
run_migrations_online()
