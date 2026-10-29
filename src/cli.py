"""Command line entry point:  python -m src.cli <command>"""
import argparse
import sys
from pathlib import Path

from sqlalchemy import text

from src.config import load_config
from src.db import get_engine
from src.exports.checksums import all_table_checksums, telemetry_checksum
from src.generator.pipeline import DatabaseNotEmptyError, load_dataset, reset_tables, table_counts
from src.migrate import current_revision, head_revision, upgrade
from src.exports.schema_docs import build_data_dictionary, build_schema_sql

# The original starter database. Scenario data (Phase 3B onwards) is NEVER loaded into it.
PROTECTED_DATABASES = ("predictive_maintenance",)
DISPOSABLE_SUFFIXES = ("_test", "_dev")

def _guard_destructive(engine, force: bool) -> None:
    """Dropping tables is only allowed on *_test / *_dev databases unless --force is given."""
    name = engine.url.database
    if not name.endswith(DISPOSABLE_SUFFIXES) and not force:
        sys.exit(f"REFUSED: this command DELETES all tables in database '{name}'.\n"
                 "It is meant for test or development databases (names ending in _test or _dev).\n"
                 "If you really want to wipe this database, add --force.\n"
                 "To upgrade a database and KEEP its data, use:  python -m src.cli migrate")


def _guard_scenario_load(engine, cfg) -> None:
    """Scenario datasets go into a separate development database, never into the protected original."""
    name = engine.url.database
    if cfg.scenarios_enabled and name in PROTECTED_DATABASES:
        sys.exit(f"REFUSED: this config adds failure scenarios and must not be loaded into '{name}' "
                 "(your original starter database).\n"
                 "Create a separate database (e.g. predictive_maintenance_dev) and add:  --db predictive_maintenance_dev")


def main() -> None:
    p = argparse.ArgumentParser(prog="python -m src.cli")
    p.add_argument("--db", help="database name to use instead of PM_DB_NAME (e.g. predictive_maintenance_dev)")
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
    sub.add_parser("checksums", help="md5 of every table (reproducibility check, read-only)")
    sub.add_parser("scenario-summary", help="failures, work orders, downtime and parts (read-only)")
    sc = sub.add_parser("score", help="risk score (0-100) for every machine over time -> CSV (read-only)")
    sc.add_argument("--every-hours", type=float, default=3.0)
    sc.add_argument("--out", default="reports/risk_scores.csv")
    rp = sub.add_parser("report", help="latest machine-risk ranking + maintenance/downtime summary -> CSV (read-only)")
    rp.add_argument("--at", help="score as of this UTC time (default: end of the data)")
    rp.add_argument("--out-dir", default="reports")
    ev = sub.add_parser("evaluate", help="score the database and compare with its failure records (read-only)")
    ev.add_argument("--every-hours", type=float, default=3.0)
    ev.add_argument("--threshold", type=float, help="warning threshold (default: the tuned one)")
    ev.add_argument("--out-dir", default="reports")
    ho = sub.add_parser("evaluate-holdout", help="tune-vs-holdout evaluation on in-memory synthetic datasets (no database)")
    ho.add_argument("--config", default="config/dev_scenarios.json")
    ho.add_argument("--only", choices=["both", "tuning", "holdout"], default="both")
    ho.add_argument("--out", default="reports/evaluation_holdout.md")
    sub.add_parser("export-schema", help="write schemas/schema.sql from the models")
    sub.add_parser("export-dictionary", help="write schemas/data_dictionary.md from the models")
    args = p.parse_args()

    if args.cmd == "evaluate-holdout":
        _evaluate_holdout(args)
        return
    if args.cmd in ("export-schema", "export-dictionary"):  # these need no database connection
        engine = None
    else:
        engine = get_engine(args.db)
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
        cfg = load_config(args.config)
        _guard_scenario_load(engine, cfg)
        try:
            print(load_dataset(engine, cfg, reset=args.reset))
        except DatabaseNotEmptyError as exc:
            sys.exit(f"REFUSED: {exc}")
    elif args.cmd == "summary":
        print(table_counts(engine))
        print("telemetry md5:", telemetry_checksum(engine))
    elif args.cmd == "checksums":
        print("database:", engine.url.database)
        for table, digest in all_table_checksums(engine).items():
            print(f"  {table:<28}{digest or '(empty)'}")
    elif args.cmd == "scenario-summary":
        _scenario_summary(engine)
    elif args.cmd in ("score", "report", "evaluate"):
        _risk_commands(engine, args)
    elif args.cmd == "export-schema":
        Path("schemas/schema.sql").write_text(build_schema_sql(), encoding="utf-8")
        print("wrote schemas/schema.sql")
    elif args.cmd == "export-dictionary":
        Path("schemas/data_dictionary.md").write_text(build_data_dictionary(), encoding="utf-8")
        print("wrote schemas/data_dictionary.md")


def _risk_commands(engine, args) -> None:
    import pandas as pd
    from dataclasses import replace
    from src.evaluation import runner as R
    from src.risk.engine import RiskParams

    params = RiskParams()
    if args.cmd == "evaluate" and args.threshold is not None:
        params = replace(params, warn_threshold=args.threshold)
    with engine.connect() as c:
        start, end = c.execute(text("SELECT min(event_ts), max(event_ts) FROM telemetry_event")).one()
    if start is None:
        sys.exit("REFUSED: this database has no telemetry to score.")
    every = getattr(args, "every_hours", 3.0)
    if args.cmd == "evaluate":
        scores, truth, m = R.evaluate_database(engine, params, every)
        if m["failures"] == 0:
            sys.exit(f"Nothing to evaluate: database '{engine.url.database}' has no failure records, so there is no "
                     "ground truth to compare the scores with. Use a scenario database (e.g. predictive_maintenance_dev).")
        out = Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        scores.to_csv(out / "risk_scores.csv", index=False)
        pd.DataFrame(m["per_failure"]).to_csv(out / "evaluation_per_failure.csv", index=False)
        report = out / f"evaluation_{engine.url.database}.md"
        report.write_text(f"# Evaluation of database `{engine.url.database}`\n\nThreshold {params.warn_threshold:g}. "
                          f"SYNTHETIC data; rules were tuned on other seeds.\n\n{R.metrics_table(m)}\n\n"
                          f"By failure category:\n\n{R.md_table(R.M.by_category(m['per_failure']).round(1))}\n\n{R.LIMITS}",
                          encoding="utf-8")
        print(R.metrics_table(m))
        print(f"\nwrote {report}, {out / 'risk_scores.csv'}, {out / 'evaluation_per_failure.csv'}")
        return
    inputs = R.inputs_from_db(engine)
    end_t = R._utc(end) + pd.Timedelta(hours=every)
    if args.cmd == "score":
        scores = R.score_inputs(inputs, params, start, end_t, every)
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        scores.to_csv(args.out, index=False)
        print(f"wrote {args.out}: {len(scores)} rows, warnings (score >= {params.warn_threshold:g}): "
              f"{int((scores.score >= params.warn_threshold).sum())}")
    else:  # report
        at = pd.Timestamp(args.at, tz="UTC") if args.at else R._utc(end)
        scores = R.RiskEngine(inputs, params).score_grid([at])
        rank = R.machine_risk_report(scores, at)
        out = Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        rank.to_csv(out / "machine_risk_report.csv", index=False)
        R.downtime_summary(engine).to_csv(out / "maintenance_downtime_summary.csv", index=False)
        print(f"Machine risk as of {at:%Y-%m-%d %H:%M} UTC (warning at >= {params.warn_threshold:g})")
        print(rank[["machine_id", "score", "band", "status", "reasons"]].head(10).to_string(index=False))
        print(f"\nwrote {out / 'machine_risk_report.csv'} and {out / 'maintenance_downtime_summary.csv'}")


def _evaluate_holdout(args) -> None:
    from src.evaluation import runner as R
    from src.risk.engine import RiskParams

    cfg, params = load_config(args.config), RiskParams()
    tuning = R.evaluate_seeds(cfg, R.TUNING_SEEDS, params) if args.only in ("both", "tuning") else None
    holdout = R.evaluate_seeds(cfg, R.HOLDOUT_SEEDS, params) if args.only in ("both", "holdout") else None
    R.write_holdout_report(Path(args.out), params, tuning, holdout)
    for name, res in (("TUNING", tuning), ("HOLDOUT", holdout)):
        if res:
            print(f"\n== {name} seeds ==\n{R.metrics_table(R.M.pool(res))}")
    print(f"\nwrote {args.out}")


SUMMARY_SQL = {
    "Failures (ground truth, for evaluation only)": """
        SELECT f.failure_id, f.failure_category AS category, f.severity,
               to_char(f.symptom_onset_at AT TIME ZONE 'UTC','YYYY-MM-DD HH24:MI') AS onset,
               to_char(f.failure_at AT TIME ZONE 'UTC','YYYY-MM-DD HH24:MI') AS failed,
               round(extract(epoch FROM (w.returned_to_service_at - w.downtime_start))/3600.0, 1) AS downtime_h
        FROM failure_event f JOIN maintenance_work_order w USING (failure_id) ORDER BY f.failure_at""",
    "Maintenance by type": """
        SELECT maintenance_type, count(*) AS orders,
               round(coalesce(sum(extract(epoch FROM (returned_to_service_at - downtime_start)))/3600.0, 0), 1) AS downtime_h
        FROM maintenance_work_order GROUP BY maintenance_type ORDER BY maintenance_type""",
    "Parts used (top 5 by cost)": """
        SELECT p.part_name, sum(wp.quantity_used) AS qty, round(sum(wp.quantity_used * p.unit_cost), 2) AS cost
        FROM work_order_part wp JOIN part p USING (part_id) GROUP BY p.part_name ORDER BY cost DESC LIMIT 5""",
}


def _scenario_summary(engine) -> None:
    print("database:", engine.url.database)
    with engine.connect() as c:
        for title, sql in SUMMARY_SQL.items():
            rows = c.execute(text(sql)).all()
            print(f"\n{title}")
            if not rows:
                print("  (none)")
            for r in rows:
                print("  " + " | ".join(str(v) for v in r))


if __name__ == "__main__":
    main()
