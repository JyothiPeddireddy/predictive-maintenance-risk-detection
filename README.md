# Industrial Predictive Maintenance and Equipment Failure Risk Detection

## Overview

This project is a Python and PostgreSQL-based industrial predictive maintenance system. It analyzes synthetic machine telemetry, operating context, and maintenance history to identify machines that may be at elevated risk of failure.

The system generates industrial asset data, stores related records in a relational database, calculates machine risk scores from 0 to 100, and evaluates the risk-scoring rules against known synthetic failure events.

The project focuses on relational data modeling, reproducible data generation, maintenance traceability, risk scoring, and measurable evaluation.

**Current Status:** Database modeling, synthetic scenario generation, risk scoring, and evaluation reports are implemented. Full-scale generation and validation against real industrial data are still pending.

All current evaluation results are based on synthetic data, not real industrial equipment.

## Technology Stack

- Python
- PostgreSQL
- SQLAlchemy
- Alembic
- Pandas
- NumPy
- Pytest
- python-dotenv
- Git and GitHub

## Features

### 1. Relational Database

The database models industrial assets and maintenance information, including:

- Plants and production lines
- Machines and sensors
- Timestamped telemetry
- Machine operating-state history
- Sensor status history
- Technicians and replacement parts
- Maintenance work orders
- Failure events
- Work-order parts usage
- Work-order status history

Database relationships and migrations support structured data, traceability, and consistency.

### 2. Synthetic Data Generation

The project uses JSON configuration files to control dataset size, random seed, sampling interval, and generation settings.

The generator supports synthetic failure scenarios, sensor faults, maintenance records, and related operating data.

A scenario manifest records injected scenario information and ground truth for evaluation.

### 3. Machine Risk Scoring

The rule-based risk engine calculates machine risk scores from 0 to 100.

It uses telemetry patterns such as rising sensor levels, trends, and bursts to identify potentially risky machine behaviour.

The system can produce risk-score CSV files and reports containing machine risk rankings and maintenance or downtime summaries.

The score is a rule-based risk indicator, not a calibrated probability of failure.

### 4. Evaluation

The evaluation module compares risk warnings against synthetic failure records using a 72-hour prediction horizon.

It reports:

- Precision
- Recall
- F1 score
- Failure-event detection rate
- Warning lead time
- Warning episodes
- False warning episodes

The project includes a tuning evaluation and a separate holdout evaluation using different random seeds.

### 5. Reproducibility and Traceability

The project includes table checksums, a scenario manifest, database status commands, schema documentation, and automated tests to support repeatable development and evaluation.

## Project Structure

```text
predictive-maintenance/
├── config/
│   ├── starter.json
│   ├── dev_scenarios.json
│   └── full.json
├── data/
│   ├── ground_truth/
│   └── sample/
├── docs/
│   ├── design_decisions.md
│   ├── postgres_setup.md
│   └── risk_and_evaluation.md
├── migrations/
│   └── versions/
├── output/
│   └── dev_scenarios/
├── prompt-history/
│   └── prompts.md
├── reports/
│   ├── evaluation_holdout.md
│   ├── evaluation_per_failure.csv
│   ├── evaluation_predictive_maintenance_dev.md
│   └── risk_scores.csv
├── schemas/
│   ├── data_dictionary.md
│   ├── relationships.md
│   └── schema.sql
├── src/
│   ├── evaluation/
│   ├── exports/
│   ├── generator/
│   ├── models/
│   ├── risk/
│   ├── cli.py
│   ├── config.py
│   ├── db.py
│   └── migrate.py
├── tests/
├── .env.example
├── requirements.txt
├── pytest.ini
└── README.md
```

## Prerequisites

Install the following:

- Python 3.11 or 3.12
- PostgreSQL
- Git
- Visual Studio Code
- pgAdmin (optional)

## Installation

### 1. Clone the Repository

```powershell
git clone https://github.com/JyothiPeddireddy/predictive-maintenance-risk-detection.git
cd predictive-maintenance-risk-detection
```

### 2. Create a Virtual Environment

```powershell
python -m venv .venv
```

Activate it in Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure PostgreSQL

Copy the example environment file:

```powershell
Copy-Item .env.example .env
```

Open `.env` and configure the database connection settings according to `docs/postgres_setup.md`.

Do not commit `.env`, database passwords, or other secrets to GitHub.

### 5. Check the Database Connection

```powershell
python -m src.cli check-db
```

### 6. Apply Migrations

```powershell
python -m src.cli migrate
```

The migration command upgrades the schema while preserving existing data.

## Running the Starter Dataset

Configure the starter database using `docs/postgres_setup.md`.

Load starter data into an empty database:

```powershell
python -m src.cli load --config config/starter.json
```

Inspect table counts and the telemetry checksum:

```powershell
python -m src.cli summary
```

Check the database schema version and row counts:

```powershell
python -m src.cli db-status
```

The starter configuration specifies one plant, two production lines, four machines, eight sensors, and a two-day telemetry period.

Only load the starter dataset into an appropriately configured empty database. The loader refuses to load into a non-empty database unless reset is explicitly requested.

## Running Development Scenarios

The development scenarios contain synthetic failures and related maintenance records. They must be loaded into a separate development database.

Do not load scenario data into the original `predictive_maintenance` starter database.

Apply migrations to the development database:

```powershell
python -m src.cli --db predictive_maintenance_dev migrate
```

Load development scenarios:

```powershell
python -m src.cli --db predictive_maintenance_dev load --config config/dev_scenarios.json
```

View the scenario summary:

```powershell
python -m src.cli --db predictive_maintenance_dev scenario-summary
```

Check table checksums:

```powershell
python -m src.cli --db predictive_maintenance_dev checksums
```

The generator also writes the scenario manifest to:

`output/dev_scenarios/scenario_manifest.json`

This manifest records the generated scenario information and ground truth used for evaluation.

## Generating Risk Scores and Reports

Generate risk scores for the development database:

--powershell
python -m src.cli --db predictive_maintenance_dev score


The default output file is:

reports/risk_scores.csv

Generate the machine-risk ranking and maintenance/downtime summary:

--powershell
python -m src.cli --db predictive_maintenance_dev report


Evaluate the development dataset:

--powershell
python -m src.cli --db predictive_maintenance_dev evaluate


The saved development evaluation report is:

`reports/evaluation_predictive_maintenance_dev.md`

## Evaluation Results

The following results are recorded in `reports/evaluation_holdout.md`. They were obtained from synthetic datasets generated using separate tuning and holdout seeds.

### Holdout Evaluation

- Scored machine-time pairs: 41,481
- Positive pairs within 72 hours: 1,440
- True positives: 975
- False positives: 276
- False negatives: 465
- True negatives: 39,765
- Precision: 77.9%
- Recall: 67.7%
- F1 score: 72.5%
- Failure events detected: 56 out of 60
- Event detection rate: 93.3%
- Median warning lead time: 69.4 hours
- Warning episodes: 73
- False warning episodes: 9
- False episodes per machine-month: 0.05

### Reproduce the Holdout Evaluation

Run:

powershell
python -m src.cli evaluate-holdout

This command evaluates tuning and holdout seeds using in-memory synthetic datasets.

The saved report is:

reports/evaluation_holdout.md

### Understanding the Metrics

Precision measures the proportion of positive warnings that match positive labels under the evaluation rules.

Recall measures the proportion of positive machine-time labels identified by the scoring system.

F1 Score combines precision and recall.

Event Detection Rate** measures the number of failure events preceded by a qualifying warning.

Warning Lead Time** measures how early the qualifying warning occurs before a failure, within the 72-hour evaluation horizon.

### Evaluation Limitations

- The data is synthetic and generated by this project.
- The risk rules are designed around patterns injected by the generator.
- Holdout seeds use the same generator and failure mechanisms, so they do not establish performance on real equipment.
- Warnings more than 72 hours before a failure may be counted as false positives under the strict evaluation labels.
- Consecutive scores are correlated because scoring occurs every three hours.
- Real industrial data validation has not been completed.

The results demonstrate performance on the project's simulated scenarios only.

## Configuration

### config/starter.json

Configures the small starter dataset for basic database and telemetry checks.

### config/dev_scenarios.json

Configures the development dataset with synthetic failure scenarios, sensor faults, and maintenance-related records.

### config/full.json

Defines a larger dataset configuration with:

- 3 plants
- 12 production lines
- 100 machines
- 5 sensors per machine
- 90 days of telemetry
- 30-minute sampling intervals

Important: This configuration defines the intended larger dataset. A successful full-scale generation run and its runtime and memory measurements have not been verified.

## Automated Tests

Run the test suite from the project root:

--powershell
python -m pytest -q


The tests cover the relational model, migrations, data generation, risk engine, evaluation, and starter-data checksum behaviour.

Run the tests using the test database settings documented in `docs/postgres_setup.md`. Do not run destructive tests against the original starter database.

## Database Safety

The project protects the original `predictive_maintenance` database from scenario-data loading.

Destructive operations such as table recreation or loading with `--reset` are intended for disposable development or test databases. The CLI checks database names and refuses destructive operations unless the appropriate safeguards are met.

Use migrations when you need to upgrade the schema without deleting existing records.

Never commit database credentials or local database backups to the public repository.

## Documentation

- `docs/postgres_setup.md` — PostgreSQL setup and database configuration.
- `docs/design_decisions.md` — Design decisions and assumptions.
- `docs/risk_and_evaluation.md` — Risk-scoring logic, evaluation methodology, and limitations.
- `schemas/data_dictionary.md` — Table and column definitions.
- `schemas/relationships.md` — Database relationships.
- `schemas/schema.sql` — Generated schema reference.
- `prompt-history/prompts.md` — Project prompt history.

## Current Status and Remaining Work

### Implemented

- PostgreSQL relational data model and migrations.
- Configurable synthetic data generation.
- Synthetic failure and sensor-fault scenarios.
- Maintenance-related records and ground-truth information.
- Rule-based risk scoring.
- Development and holdout evaluation reports.
- Database status, summary, and checksum commands.
- Schema and data-dictionary export commands.
- Automated tests.

### Remaining Work

- Run and verify the full-scale dataset configuration.
- Confirm the required failure-event volume and repeated failures per machine, if required by the challenge.
- Verify full-scale generation reproducibility.
- Measure full-scale execution time and memory use.
- Validate the complete workflow against additional data, including real industrial data when available.
- Run the complete test suite again after the final changes.
