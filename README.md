# Industrial Predictive Maintenance (PostgreSQL)

Status: **Phase 4 (risk engine + evaluation) built on top of Phase 3B** - synthetic failure scenarios load into a
SEPARATE development database; a rule-based 0-100 machine risk score, evaluation (72 h horizon) and reports exist.
The original starter database/dataset is unchanged (same md5). Results are on SYNTHETIC data only - see
`docs/risk_and_evaluation.md` for numbers and limits. Not built yet: full-scale (100 machines / 90 days) run,
validation on real data.

Setup (Windows PowerShell + PostgreSQL): see `docs/postgres_setup.md`.

## Everyday commands
```powershell
python -m src.cli check-db            # test the connection
python -m src.cli migrate             # SAFE: create/upgrade the schema, keeps data
python -m src.cli db-status           # schema version + row counts (read-only)
python -m src.cli load --config config/starter.json    # load starter data into an EMPTY database
python -m src.cli summary             # row counts + telemetry checksum
python -m pytest -q                   # all tests (use the *_test database)
python -m src.cli export-schema       # regenerate schemas/schema.sql
python -m src.cli export-dictionary   # regenerate schemas/data_dictionary.md
```
Phase 3B - scenario data (ALWAYS into a separate development database, never `predictive_maintenance`):
```powershell
python -m src.cli --db predictive_maintenance_dev migrate
python -m src.cli --db predictive_maintenance_dev load --config config/dev_scenarios.json
python -m src.cli --db predictive_maintenance_dev scenario-summary   # failures, downtime, parts (read-only)
python -m src.cli --db predictive_maintenance_dev checksums          # md5 per table (reproducibility)
```
The load also writes `output/dev_scenarios/scenario_manifest.json` (ground truth of everything injected).

Phase 4 - risk scores and evaluation (read-only; use the dev database):
```powershell
python -m src.cli --db predictive_maintenance_dev score       # reports/risk_scores.csv
python -m src.cli --db predictive_maintenance_dev report      # machine risk ranking + maintenance/downtime summary
python -m src.cli --db predictive_maintenance_dev evaluate    # precision / recall / F1 / event recall / lead time
python -m src.cli evaluate-holdout                            # tuning vs holdout seeds (in memory, ~1 min)
```

Destructive (test and *_dev databases only; refused elsewhere unless `--force`):
`python -m src.cli load --config config/starter.json --reset`, `python -m src.cli create-tables`

## Documentation
- `schemas/data_dictionary.md` - every table, column, key, CHECK constraint and index (generated)
- `schemas/relationships.md` - ER diagram and cardinalities (1:N, N:M)
- `schemas/schema.sql` - informational SQL (generated); the database is built by `migrations/`
- `docs/risk_and_evaluation.md` - how the risk score works, how it was evaluated, results and limits
- `docs/design_decisions.md` - why each table exists, migration strategy, assumptions
