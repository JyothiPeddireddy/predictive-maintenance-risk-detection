"""Command line entry point:  python -m src.cli <command>"""
import argparse
import sys
from pathlib import Path

from sqlalchemy import text

from src.config import load_config
from src.db import get_engine
from src.exports.checksums import telemetry_checksum
from src.generator.pipeline import load_dataset, reset_tables, table_counts
from src.migrate import current_revision, head_revision, upgrade
from src.exports.schema_docs import build_data_dictionary, build_schema_sql


def _guard_destructive(engine, force: bool) -> None:
    """Dropping tables is only allowed on *_test databases unless --force is given."""
    name = engine.url.database
    if not name.endswith("_test") and not force:
        sys.exit(f"REFUSED: this command DELETES all tables in database '{name}'.\n"
                 "It is meant for test databases (names ending in _test).\n"
                 "If you really want to wipe this database, add --force.\n"
                 "To upgrade a database and KEEP its data, use:  python -m src.cli migrate")


def main() -> None:
    p = argparse.ArgumentParser(prog="python -m src.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check-db", help="test the connection")
    sub.add_parser("migrate", help="SAFE: upgrade the database schema to the latest version, keeping all data")
    sub.add_parser("db-status", help="schema version, tables and row counts (read-only)")
    ct = sub.add_parser("create-tables", help="DROP all tables, then rebuild them (test databases only)")
    ct.add_argument("--force", action="store_true", help="allow this on a non-test database")
    ld = sub.add_parser("load", help="generate data and load it into PostgreSQL")
    ld.add_argument("--config", default="config/starter.json")
    ld.add_argument("--reset", action="store_true", help="DROP all tables and rebuild first (test databases only)")
    ld.add_argument("--force", action="store_true", help="allow --reset on a non-test database")
    sub.add_parser("summary", help="row counts + telemetry checksum")
    sub.add_parser("export-schema", help="write schemas/schema.sql from the models")
    sub.add_parser("export-dictionary", help="write schemas/data_dictionary.md from the models")
    args = p.parse_args()

    if args.cmd in ("export-schema", "export-dictionary"):  # these need no database connection
        engine = None
    else:
        engine = get_engine()
    if args.cmd == "check-db":
        with engine.connect() as c:
            print(c.execute(text("select version()")).scalar_one())
            print("database:", c.execute(text("select current_database()")).scalar_one())
    elif args.cmd == "migrate":
        before = current_revision(engine)
        upgrade(engine)
        print(f"schema version: {before} -> {current_revision(engine)} (latest: {head_revision()})")
    elif args.cmd == "db-status":
        print("database:", engine.url.database)
        print(f"schema version: {current_revision(engine)} (latest: {head_revision()})")
        for table, n in table_counts(engine).items():
            print(f"  {table:<28}{'(not created yet)' if n is None else format(n, ','):>18}")
    elif args.cmd == "create-tables":
        _guard_destructive(engine, args.force)
        reset_tables(engine)
        print("tables recreated")
    elif args.cmd == "load":
        if args.reset:
            _guard_destructive(engine, args.force)
        print(load_dataset(engine, load_config(args.config), reset=args.reset))
    elif args.cmd == "summary":
        print(table_counts(engine))
        print("telemetry md5:", telemetry_checksum(engine))
    elif args.cmd == "export-schema":
        Path("schemas/schema.sql").write_text(build_schema_sql(), encoding="utf-8")
        print("wrote schemas/schema.sql")
    elif args.cmd == "export-dictionary":
        Path("schemas/data_dictionary.md").write_text(build_data_dictionary(), encoding="utf-8")
        print("wrote schemas/data_dictionary.md")


if __name__ == "__main__":
    main()
