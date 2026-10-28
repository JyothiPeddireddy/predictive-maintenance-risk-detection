# Prompt history

Record every prompt you ACTUALLY submitted to each AI tool. Never add prompts you did not use.

| Field | Entry |
|---|---|
| Timestamp | |
| Tool name / model | |
| Exact prompt | |
| Purpose | |
| Code or decision used | |
| Changes I made | |
| Verification outcome | |

Copy the table for each new prompt.


---

## Entry: Phase 3A - complete the relational data model

| Field | Entry |
|---|---|
| Timestamp | 2026-10-28, time: ______ (fill in the local time you submitted it) |
| Tool name / model | Claude (Sonnet 5.5) in claude.ai, with code execution |
| Purpose | Complete the relational model (all 10 required entities + bridge/history tables) with a safe migration strategy and tests |
| Code or decision used | Alembic migrations 0001-0003; 10 new tables in `src/models/tables.py`; `src/migrate.py`; CLI `migrate`/`db-status` and a guard on destructive commands; generated data dictionary; tests `test_relational_model.py` and `test_migration.py`; decisions documented in `docs/design_decisions.md` |
| Changes I made | ______ (record any edits you make to the generated code) |
| Verification outcome | In the AI's sandbox (PostgreSQL 16, Linux): 88 tests passed. Not yet run on my Windows machine / PostgreSQL 18.4: ______ (fill in after running the commands in docs/postgres_setup.md section 5) |

Notable implementation decisions: Alembic instead of create_all; idempotent baseline migration; downtime derived not
stored; history tables are append-only transitions enforced by trigger; invalid records go to a separate exceptions
dataset because the database rejects them; a test caught a NULL-handling bug in the work-order transition CHECK, which
was fixed in the model and in migration 0002 before it was ever applied to my database.

**Exact prompt submitted:**

```text
We have successfully completed and tested the PostgreSQL starter version of my predictive maintenance project on Windows.

Current status:
- PostgreSQL 18.4 connection works.
- All 14 existing tests pass.
- Starter data loads successfully: 1 plant, 2 production lines, 4 machines, 8 sensors, and 2,304 telemetry readings.
- Existing SQLAlchemy models are in `src/models/tables.py`.
- Existing tables are `plant`, `production_line`, `machine`, `sensor`, and `telemetry_event`.
- The project uses Python, SQLAlchemy 2.x, PostgreSQL, psycopg 3, pytest, and a CLI.
- Keep the existing working code and follow its naming conventions.

## Task: Phase 3A — Complete the relational data model

First inspect the entire repository, including the models, generator, configuration, CLI, tests, schema files, README, and setup documentation. Do not assume files or features are missing until you inspect them.

Then implement the missing database entities and relationships required by the predictive maintenance challenge.

The model must cover:

1. Plant
2. ProductionLine
3. Machine
4. Sensor
5. TelemetryEvent
6. OperatingShift
7. MaintenanceWorkOrder
8. FailureEvent
9. Part
10. Technician

Also include any necessary bridge and history tables, such as:
- Work-order parts used, including quantity and replacement timestamp where appropriate.
- Technician assignments to work orders.
- Explicit machine-state history records.
- Sensor or machine status-change history when appropriate.
- Other association tables needed to represent the challenge accurately.

## Data integrity requirements

- Use primary keys, foreign keys, appropriate uniqueness constraints, indexes, and CHECK constraints.
- Preserve the existing plant → production line → machine → sensor hierarchy.
- Store telemetry with timestamps, reading values, units, and machine operating state.
- Support work-order lifecycle, maintenance type, priority, status, start/end times, downtime, findings, and corrective actions where appropriate.
- Record failure onset, detection, failure category, severity, and resolution where appropriate.
- Track parts, quantities used, and replacement history.
- Model technician details and assignments without duplicating technician records.
- Represent historical state changes as separate records; do not overwrite history.
- Ensure time fields and quantities have sensible validation rules.
- Avoid unnecessary columns and tables. Document why each additional table exists.
- Follow the existing SQLAlchemy 2.x style and naming conventions.

## Compatibility and migration requirements

- Preserve existing table names, primary keys, column meanings, and starter-data behavior wherever possible.
- Do not drop or recreate the user's development database.
- Do not use `Base.metadata.create_all()` as a substitute for a migration strategy when existing tables need changes.
- Inspect how the project currently creates tables and manages schema changes. Implement a safe, documented migration approach that preserves existing data.
- Keep the test database separate from the development database.
- Never run destructive tests against the development database.
- Do not hardcode database passwords or commit `.env`.

## Tests

Add tests for:
- Successful creation of the new schema.
- Valid parent-child relationships.
- Rejection of invalid foreign keys and invalid enum/status values.
- Uniqueness constraints.
- Invalid date ranges, quantities, and other applicable constraints.
- Work-order/technician/parts associations.
- Machine-state history preserving multiple changes over time.
- Existing starter functionality remaining compatible.

Run the complete test suite using the repository's existing test setup. Report the actual results; do not claim tests passed unless you ran them.

## Deliverables

1. Updated SQLAlchemy models.
2. Safe schema migration or upgrade mechanism.
3. Tests for new entities, relationships, and constraints.
4. Updated schema documentation or data dictionary.
5. Updated setup instructions for Windows PowerShell and PostgreSQL.
6. A list of files changed and the reason for each change.
7. Exact commands I should run locally to apply the schema changes safely and verify them.

## Important working rules

- Work only on this phase. Do not implement the telemetry scale-up, risk engine, AI agents, or evaluation engine yet.
- Inspect before editing and reuse existing code.
- Make focused changes instead of rewriting the entire repository.
- Do not change my PostgreSQL credentials.
- Do not expose secrets in logs or output.
- Explain important design decisions in simple English because I am a beginner.
- If a requirement is ambiguous, state your assumption.
- Finish with a summary of completed work, tests actually run, limitations, and the next recommended phase.
- Record this prompt and the actual implementation decisions in `prompt-history/prompts.md` so the project's AI-use history remains accurate.

yes start Phase 3.
```
