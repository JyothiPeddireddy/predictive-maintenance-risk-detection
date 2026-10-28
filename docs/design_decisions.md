# Design decisions (living document)

- **PostgreSQL 16 + SQLAlchemy 2.x + psycopg 3.** Production-style relational design; psycopg 3 provides `COPY` for fast bulk load.
- **Enums = VARCHAR + CHECK constraints.** Readable in pgAdmin, no migration pain when adding a value.
- **Timestamps = `timestamptz`, always UTC.** Fixed `start_utc` in config; no `now()` in generated data.
- **IDs are generated in Python**, never by the database (no serial/identity), so they are deterministic.
- **Telemetry IDs:** `TEL-<sensor-id>-YYYYMMDDTHHMMSSZ`; a 2nd reading in the same second gets `-01`, `-02`...
- **Per-sensor random streams** `SeedSequence([seed, sensor_index])`: output is independent of batch size and write order.
- **Bulk load via COPY**, master data via SQLAlchemy `insert()`.
- **Invalid records live in a separate exceptions dataset**, because PostgreSQL constraints (correctly) reject them in the real tables.
- **Checksums are computed in SQL** over ordered rows with explicit UTC formatting.

## Phase 3A: complete relational model

### Migrations (Alembic) instead of create_all
`create_all()` only creates tables that are missing; it never changes an existing table and cannot upgrade a database
that already holds data. Alembic records a **schema version** inside the database (table `alembic_version`) and applies
only the steps that database has not had yet.
- `0001` baseline: the 5 Phase 2 tables. If they already exist it changes nothing (your data stays); if the database is
  empty it creates them. Its downgrade is refused because it would delete starter data.
- `0002` adds 10 new tables. It does not touch the 5 old tables.
- `0003` adds append-only triggers to the history tables.
- Every schema build (including `--reset` and the tests) now goes through migrations, so the migrations are exercised
  on every test run. A test also compares the migrated database with the models to catch drift.
- `load --reset` and `create-tables` (which drop all tables) are refused on any database whose name does not end in
  `_test`, unless you add `--force`.

### Why each new table exists
| Table | Why it exists |
|---|---|
| operating_shift | Required entity: planned operating context (planned state/load) per machine and shift. |
| technician | Required entity: one row per person, so people are never duplicated across work orders. |
| part | Required entity: catalogue of parts, so part data is stored once. |
| failure_event | Required entity: confirmed failures; source of ground truth. Keeps onset, failure, detection and resolution times. |
| maintenance_work_order | Required entity: maintenance jobs with lifecycle, timestamps and downtime source times. |
| work_order_technician | Bridge for the N:M link between work orders and technicians (plus role and hours). |
| work_order_part | Bridge for the N:M link between work orders and parts (plus quantity and replacement time). |
| machine_state_history | Explicit, append-only machine state changes (RUNNING, IDLE, FAILED, ...), required by the brief. |
| sensor_status_history | Keeps the history of ACTIVE/FAULTY/RETIRED, needed to tell sensor faults from machine faults. |
| work_order_status_history | Records lifecycle transitions with timestamps and enforces the legal transitions in the database. |

### Other decisions
- **Downtime is not stored.** The work order stores the two source timestamps (`downtime_start`,
  `returned_to_service_at`); downtime = their difference. This follows the rule "derive values from source records".
- **No machine-status history table.** `machine.status` is the coarse asset lifecycle (OPERATIONAL, ... DECOMMISSIONED)
  and rarely changes; day-to-day operating state is in `machine_state_history`. Two tables would duplicate each other.
- **History tables are transitions, not intervals.** Each row says "at time T the state changed from A to B". Nothing
  ever needs to be updated to close an interval, so rows can be append-only (enforced by trigger).
- **Enums = VARCHAR + CHECK.** Same as Phase 2.
- **Database constraints reject invalid records**, so the five deliberate negative scenarios (Phase 4) are stored in a
  separate exceptions dataset, not in these tables. Tests prove the database rejects them.
- **CHECK constraints and NULL.** A CHECK that evaluates to NULL counts as *passed* in PostgreSQL. The transition rule
  originally had this bug (a test caught it); every branch now tests `previous_status` explicitly.
- **Constraint names must be <= 63 characters** (PostgreSQL limit). Two foreign keys have explicit short names; a test
  guards the limit.

### Assumptions (ambiguous requirements)
- `operating_shift` is per machine (not per line) so machines on one line can have different plans.
- `failure_event.symptom_onset_at` is mandatory: every scenario has a degradation start. Sudden failures with no
  precursor are out of scope. Risk scoring must never read `failure_event`.
- One row per part per work order in `work_order_part` (a part used twice is one row with a larger quantity).
- `telemetry_event.machine_state` was left unchanged (4 values, no `FAILED`) to keep Phase 2 data compatible. Revisit in
  Phase 3B if failed machines must keep emitting telemetry with a `FAILED` state.
