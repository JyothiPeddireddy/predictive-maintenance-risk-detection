# Industrial Predictive Maintenance (PostgreSQL)

Status: **Phase 3A complete** - full relational model (15 tables) with migrations. Telemetry is still the small starter
sample; scale-up, failure scenarios, validation reports, risk engine and evaluation come in later phases.

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
Destructive (test databases only; refused elsewhere unless `--force`):
`python -m src.cli load --config config/starter.json --reset`, `python -m src.cli create-tables`

## Documentation
- `schemas/data_dictionary.md` - every table, column, key, CHECK constraint and index (generated)
- `schemas/relationships.md` - ER diagram and cardinalities (1:N, N:M)
- `schemas/schema.sql` - informational SQL (generated); the database is built by `migrations/`
- `docs/design_decisions.md` - why each table exists, migration strategy, assumptions
