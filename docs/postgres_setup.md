# PostgreSQL setup on Windows + VS Code

You already have PostgreSQL and pgAdmin installed. These steps create a dedicated user and two databases
(one for real data, one for tests) and connect the project.

## 1. Create the user and databases (pgAdmin)
1. Open pgAdmin, connect to your local server (use the `postgres` superuser password you chose at install).
2. Right-click the server -> **Query Tool** (or open it on the `postgres` database), then run
   (choose your OWN password and replace `YOUR_PASSWORD_HERE`):

```sql
CREATE ROLE pm_user LOGIN PASSWORD 'YOUR_PASSWORD_HERE' CREATEDB;
CREATE DATABASE predictive_maintenance      OWNER pm_user;
CREATE DATABASE predictive_maintenance_test OWNER pm_user;
```
Do not save this query with the real password into the repository.

## 2. Python environment (VS Code terminal, PowerShell)
```powershell
python --version                      # 3.11 or 3.12
python -m venv .venv
.venv\Scripts\Activate.ps1            # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements.txt
```
In VS Code: Ctrl+Shift+P -> **Python: Select Interpreter** -> choose `.venv`.

## 3. Configure credentials
```powershell
copy .env.example .env
```
Edit `.env` (it is git-ignored) and set `PM_DB_PASSWORD` to the password from step 1.
If your PostgreSQL does not use port 5432, change `PM_DB_PORT`.

## 4. Verify
```powershell
python -m src.cli check-db            # prints the PostgreSQL version and database name
python -m pytest -q                   # runs against predictive_maintenance_test
python -m src.cli load --config config/starter.json --reset
python -m src.cli summary             # expected: 1 plant, 2 lines, 4 machines, 8 sensors, 2304 telemetry
```
In pgAdmin: Databases -> predictive_maintenance -> Schemas -> public -> Tables (right-click Refresh).

## 5. Upgrading an existing database to the Phase 3A schema (keeps your data)
Run these in the VS Code PowerShell terminal, in the project folder, with `.venv` active:
```powershell
pip install -r requirements.txt            # installs Alembic (new dependency)
python -m src.cli db-status                # read-only: shows schema version and row counts BEFORE
python -m src.cli migrate                  # SAFE upgrade; keeps all existing rows
python -m src.cli db-status                # AFTER: version 0003, same starter counts, 10 new empty tables
python -m src.cli summary                  # telemetry md5 must be the same value as before
python -m pytest -q                        # runs on the *_test database only
```
- `migrate` never deletes data. Running it again does nothing.
- If you ran `summary` before upgrading, its `telemetry md5` should match the one after.
- **Do not** use `--reset` or `create-tables` on `predictive_maintenance`: they delete everything and are refused
  unless you add `--force`. They are for the `_test` database only.
- Optional safety copy before upgrading (adjust the path/version): `pg_dump -U pm_user -h localhost -Fc -f backup.dump predictive_maintenance`
  (the `pg_dump` program is in PostgreSQL's `bin` folder). `*.dump` files are git-ignored.
- The tests that check upgrading create and drop a temporary database `pm_migration_scratch_test`; this needs the
  `CREATEDB` permission (the setup SQL above grants it). Without it those tests are skipped, with a message.

## Common problems
| Message | Likely cause |
|---|---|
| `password authentication failed` | wrong `PM_DB_PASSWORD` or `PM_DB_USER` in `.env` |
| `connection refused` / timeout | PostgreSQL service not running (Services -> postgresql-x64-NN) or wrong port |
| `database "..." does not exist` | step 1 not completed for that database |
| `REFUSED: this command DELETES all tables` | working as designed: use `migrate`, not `--reset`, on the real database |
| `Environment variable PM_DB_USER is not set` | `.env` missing, or you ran the command from a different folder |
