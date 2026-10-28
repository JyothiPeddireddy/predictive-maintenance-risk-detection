# Data dictionary

Generated from `src/models/tables.py` by `python -m src.cli export-dictionary` (do not edit by hand).
All timestamps are `timestamptz`, always UTC. Enum-like fields are `VARCHAR` with a CHECK constraint.

## `part`

Catalogue of replaceable parts and consumables.

| Column | Type | Null? | Key | Notes |
|---|---|---|---|---|
| `part_id` | VARCHAR(16) | no | PK | Format PRT-0001. |
| `part_number` | VARCHAR(32) | no | UQ |  |
| `part_name` | VARCHAR(100) | no |  |  |
| `category` | VARCHAR(16) | no |  |  |
| `unit_of_measure` | VARCHAR(4) | no |  |  |
| `unit_cost` | NUMERIC(12, 2) | no |  | Currency units per unit_of_measure (EA = each, L = litre, KG = kilogram, M = metre). |
| `status` | VARCHAR(16) | no |  |  |

**CHECK constraints**

- `ck_part_category_enum`: `category IN ('BEARING','SEAL','MOTOR','BELT','FILTER','SENSOR','LUBRICANT','ELECTRICAL','OTHER')`
- `ck_part_cost_non_negative`: `unit_cost >= 0`
- `ck_part_status_enum`: `status IN ('ACTIVE','DISCONTINUED')`
- `ck_part_unit_enum`: `unit_of_measure IN ('EA','L','KG','M')`

## `plant`

A factory site. Top of the hierarchy.

| Column | Type | Null? | Key | Notes |
|---|---|---|---|---|
| `plant_id` | VARCHAR(16) | no | PK | Format PLT-001. |
| `plant_name` | VARCHAR(100) | no | UQ |  |
| `timezone` | VARCHAR(40) | no |  |  |
| `status` | VARCHAR(16) | no |  |  |
| `commissioned_on` | DATE | no |  |  |

**CHECK constraints**

- `ck_plant_status_enum`: `status IN ('ACTIVE','INACTIVE','DECOMMISSIONED')`

## `production_line`

A line inside a plant (1 plant : N lines).

| Column | Type | Null? | Key | Notes |
|---|---|---|---|---|
| `line_id` | VARCHAR(32) | no | PK | Format LINE-<plant-id>-001. |
| `plant_id` | VARCHAR(16) | no | FK -> plant.plant_id; UQ (with line_name) |  |
| `line_name` | VARCHAR(100) | no | UQ (with plant_id) |  |
| `status` | VARCHAR(16) | no |  |  |

**CHECK constraints**

- `ck_production_line_status_enum`: `status IN ('ACTIVE','INACTIVE','DECOMMISSIONED')`

**Indexes**

- `ix_production_line_plant_id` on (plant_id)

## `technician`

A maintenance technician (one row per person, never duplicated; assignments are in the bridge table).

| Column | Type | Null? | Key | Notes |
|---|---|---|---|---|
| `technician_id` | VARCHAR(16) | no | PK | Format TECH-001. |
| `plant_id` | VARCHAR(16) | no | FK -> plant.plant_id | Home plant. |
| `full_name` | VARCHAR(100) | no |  |  |
| `specialty` | VARCHAR(20) | no |  |  |
| `status` | VARCHAR(12) | no |  |  |
| `hired_on` | DATE | no |  |  |

**CHECK constraints**

- `ck_technician_specialty_enum`: `specialty IN ('MECHANICAL','ELECTRICAL','INSTRUMENTATION','GENERAL')`
- `ck_technician_status_enum`: `status IN ('ACTIVE','ON_LEAVE','INACTIVE')`

**Indexes**

- `ix_technician_plant_id` on (plant_id)

## `machine`

A machine on a production line (1 line : N machines). Central entity of the project.

| Column | Type | Null? | Key | Notes |
|---|---|---|---|---|
| `machine_id` | VARCHAR(48) | no | PK | Format MCH-<line-id>-001. |
| `line_id` | VARCHAR(32) | no | FK -> production_line.line_id; UQ (with machine_name) |  |
| `machine_name` | VARCHAR(100) | no | UQ (with line_id) |  |
| `machine_type` | VARCHAR(32) | no |  |  |
| `status` | VARCHAR(24) | no |  |  |
| `installed_on` | DATE | no |  |  |

**CHECK constraints**

- `ck_machine_status_enum`: `status IN ('OPERATIONAL','UNDER_MAINTENANCE','FAILED','DECOMMISSIONED')`

**Indexes**

- `ix_machine_line_id` on (line_id)

## `failure_event`

A confirmed machine failure with symptom onset, failure, detection and resolution times. Ground-truth source: never used as an input to risk scoring.

| Column | Type | Null? | Key | Notes |
|---|---|---|---|---|
| `failure_id` | VARCHAR(48) | no | PK | Format FAIL-<machine-id>-001. |
| `machine_id` | VARCHAR(48) | no | FK -> machine.machine_id; UQ (with failure_at) |  |
| `failure_category` | VARCHAR(16) | no |  |  |
| `severity` | VARCHAR(8) | no |  |  |
| `symptom_onset_at` | TIMESTAMP WITH TIME ZONE | no |  | When degradation began. Must not be after failure_at. |
| `failure_at` | TIMESTAMP WITH TIME ZONE | no | UQ (with machine_id) | When the failure was confirmed. |
| `detected_at` | TIMESTAMP WITH TIME ZONE | yes |  | First detection by a person or system. NULL = not detected beforehand. |
| `resolved_at` | TIMESTAMP WITH TIME ZONE | yes |  | NULL until status = RESOLVED. |
| `status` | VARCHAR(12) | no |  |  |
| `description` | TEXT | yes |  |  |

**CHECK constraints**

- `ck_failure_event_category_enum`: `failure_category IN ('BEARING_WEAR','OVERHEATING','ELECTRICAL','LUBRICATION','MISALIGNMENT','OTHER')`
- `ck_failure_event_detected_after_onset`: `detected_at IS NULL OR detected_at >= symptom_onset_at`
- `ck_failure_event_onset_before_failure`: `symptom_onset_at <= failure_at`
- `ck_failure_event_resolved_after_failure`: `resolved_at IS NULL OR resolved_at >= failure_at`
- `ck_failure_event_resolved_matches_status`: `(status = 'RESOLVED') = (resolved_at IS NOT NULL)`
- `ck_failure_event_severity_enum`: `severity IN ('MINOR','MAJOR','CRITICAL')`
- `ck_failure_event_status_enum`: `status IN ('CONFIRMED','UNDER_REPAIR','RESOLVED')`

## `operating_shift`

Planned operating context of one machine for one shift (planned state and load).

| Column | Type | Null? | Key | Notes |
|---|---|---|---|---|
| `shift_id` | VARCHAR(48) | no | PK | Format SHF-<machine-id>-YYYYMMDD-M|A|N. |
| `machine_id` | VARCHAR(48) | no | FK -> machine.machine_id; UQ (with shift_start) |  |
| `shift_name` | VARCHAR(12) | no |  |  |
| `shift_start` | TIMESTAMP WITH TIME ZONE | no | UQ (with machine_id) |  |
| `shift_end` | TIMESTAMP WITH TIME ZONE | no |  |  |
| `planned_state` | VARCHAR(20) | no |  |  |
| `planned_load_pct` | NUMERIC(5, 2) | yes |  | Percent, 0-100. |

**CHECK constraints**

- `ck_operating_shift_end_after_start`: `shift_end > shift_start`
- `ck_operating_shift_load_pct_range`: `planned_load_pct IS NULL OR planned_load_pct BETWEEN 0 AND 100`
- `ck_operating_shift_name_enum`: `shift_name IN ('MORNING','AFTERNOON','NIGHT')`
- `ck_operating_shift_planned_state_enum`: `planned_state IN ('RUNNING','IDLE','PLANNED_SHUTDOWN')`

## `sensor`

A sensor attached to a machine. Stores unit and plausible range used to judge sensor quality.

| Column | Type | Null? | Key | Notes |
|---|---|---|---|---|
| `sensor_id` | VARCHAR(64) | no | PK | Format SNS-<machine-id>-TEMP-01. |
| `machine_id` | VARCHAR(48) | no | FK -> machine.machine_id; UQ (with sensor_type, sensor_seq) |  |
| `sensor_type` | VARCHAR(8) | no | UQ (with machine_id, sensor_seq) |  |
| `sensor_seq` | INTEGER | no | UQ (with machine_id, sensor_type) |  |
| `unit` | VARCHAR(12) | no |  |  |
| `min_plausible` | NUMERIC(12, 3) | no |  | Same unit as sensor.unit. Readings outside min/max are sensor-quality suspects. |
| `max_plausible` | NUMERIC(12, 3) | no |  | Same unit as sensor.unit. |
| `sampling_interval_s` | INTEGER | no |  | Seconds between readings. |
| `status` | VARCHAR(16) | no |  |  |

**CHECK constraints**

- `ck_sensor_interval_positive`: `sampling_interval_s > 0`
- `ck_sensor_range_order`: `min_plausible < max_plausible`
- `ck_sensor_status_enum`: `status IN ('ACTIVE','FAULTY','RETIRED')`
- `ck_sensor_type_enum`: `sensor_type IN ('TEMP','VIB')`

**Indexes**

- `ix_sensor_machine_id` on (machine_id)

## `maintenance_work_order`

A maintenance job on a machine, with lifecycle status, start/end and downtime timestamps.

| Column | Type | Null? | Key | Notes |
|---|---|---|---|---|
| `work_order_id` | VARCHAR(20) | no | PK | Format WO-2026-000001. |
| `machine_id` | VARCHAR(48) | no | FK -> machine.machine_id |  |
| `failure_id` | VARCHAR(48) | yes | FK -> failure_event.failure_id | Set when the order repairs a recorded failure. |
| `maintenance_type` | VARCHAR(12) | no |  |  |
| `priority` | VARCHAR(8) | no |  |  |
| `status` | VARCHAR(12) | no |  |  |
| `created_at` | TIMESTAMP WITH TIME ZONE | no |  |  |
| `scheduled_for` | TIMESTAMP WITH TIME ZONE | yes |  |  |
| `started_at` | TIMESTAMP WITH TIME ZONE | yes |  |  |
| `completed_at` | TIMESTAMP WITH TIME ZONE | yes |  |  |
| `downtime_start` | TIMESTAMP WITH TIME ZONE | yes |  | When the machine stopped for this work. Downtime = returned_to_service_at - downtime_start (derived, not stored). |
| `returned_to_service_at` | TIMESTAMP WITH TIME ZONE | yes |  | When the machine went back into service. |
| `findings` | TEXT | yes |  |  |
| `corrective_action` | TEXT | yes |  |  |

**CHECK constraints**

- `ck_maintenance_work_order_downtime_order`: `returned_to_service_at IS NULL OR (downtime_start IS NOT NULL AND returned_to_service_at >= downtime_start)`
- `ck_maintenance_work_order_end_after_start`: `started_at IS NULL OR completed_at IS NULL OR completed_at >= started_at`
- `ck_maintenance_work_order_priority_enum`: `priority IN ('LOW','MEDIUM','HIGH','URGENT')`
- `ck_maintenance_work_order_start_after_created`: `started_at IS NULL OR started_at >= created_at`
- `ck_maintenance_work_order_status_enum`: `status IN ('OPEN','IN_PROGRESS','COMPLETED','CANCELLED')`
- `ck_maintenance_work_order_status_matches_timestamps`: `(status = 'OPEN' AND started_at IS NULL AND completed_at IS NULL) OR (status = 'IN_PROGRESS' AND started_at IS NOT NULL AND completed_at IS NULL) OR (status = 'COMPLETED' AND started_at IS NOT NULL AND completed_at IS NOT NULL) OR (status = 'CANCELLED' AND completed_at IS NULL)`
- `ck_maintenance_work_order_type_enum`: `maintenance_type IN ('PREVENTIVE','CORRECTIVE','PREDICTIVE','INSPECTION')`

**Indexes**

- `ix_maintenance_work_order_failure_id` on (failure_id)
- `ix_work_order_machine_created` on (machine_id, created_at)

## `sensor_status_history`

Append-only log of sensor status changes, e.g. ACTIVE -> FAULTY.

| Column | Type | Null? | Key | Notes |
|---|---|---|---|---|
| `history_id` | VARCHAR(80) | no | PK | Format SSH-<sensor-id>-YYYYMMDDTHHMMSSZ. |
| `sensor_id` | VARCHAR(64) | no | FK -> sensor.sensor_id; UQ (with changed_at) |  |
| `previous_status` | VARCHAR(16) | yes |  | NULL on the sensor's first record. RETIRED is final. |
| `new_status` | VARCHAR(16) | no |  |  |
| `changed_at` | TIMESTAMP WITH TIME ZONE | no | UQ (with sensor_id) |  |
| `reason` | VARCHAR(200) | yes |  |  |

**CHECK constraints**

- `ck_sensor_status_history_new_status_enum`: `new_status IN ('ACTIVE','FAULTY','RETIRED')`
- `ck_sensor_status_history_previous_status_enum`: `previous_status IS NULL OR previous_status IN ('ACTIVE','FAULTY','RETIRED')`
- `ck_sensor_status_history_retired_is_final`: `previous_status IS DISTINCT FROM 'RETIRED'`
- `ck_sensor_status_history_status_really_changed`: `previous_status IS NULL OR previous_status <> new_status`

## `telemetry_event`

One sensor reading with its timestamp, unit and the machine operating state at that time.

| Column | Type | Null? | Key | Notes |
|---|---|---|---|---|
| `telemetry_id` | VARCHAR(96) | no | PK | Format TEL-<sensor-id>-YYYYMMDDTHHMMSSZ (UTC); -01, -02... added for same-second duplicates. |
| `sensor_id` | VARCHAR(64) | no | FK -> sensor.sensor_id |  |
| `event_ts` | TIMESTAMP WITH TIME ZONE | no |  | UTC. |
| `reading_value` | NUMERIC(12, 3) | yes |  | In the sensor's unit. NULL = missing reading (a genuine 0 is stored as 0). |
| `unit` | VARCHAR(12) | no |  |  |
| `machine_state` | VARCHAR(20) | no |  | Operating state when the reading was taken. |

**CHECK constraints**

- `ck_telemetry_event_state_enum`: `machine_state IN ('RUNNING','IDLE','PLANNED_SHUTDOWN','MAINTENANCE')`

**Indexes**

- `ix_telemetry_sensor_ts` on (sensor_id, event_ts)

## `machine_state_history`

Append-only log of machine operating-state changes (never updated or deleted).

| Column | Type | Null? | Key | Notes |
|---|---|---|---|---|
| `history_id` | VARCHAR(64) | no | PK | Format MSH-<machine-id>-YYYYMMDDTHHMMSSZ. |
| `machine_id` | VARCHAR(48) | no | FK -> machine.machine_id; UQ (with changed_at) |  |
| `previous_state` | VARCHAR(20) | yes |  | NULL on the machine's first record. |
| `new_state` | VARCHAR(20) | no |  |  |
| `changed_at` | TIMESTAMP WITH TIME ZONE | no | UQ (with machine_id) |  |
| `change_source` | VARCHAR(12) | no |  |  |
| `work_order_id` | VARCHAR(20) | yes | FK -> maintenance_work_order.work_order_id | Optional: the work order that caused this change. |
| `failure_id` | VARCHAR(48) | yes | FK -> failure_event.failure_id | Optional: the failure that caused this change. |

**CHECK constraints**

- `ck_machine_state_history_link_matches_source`: `(work_order_id IS NULL OR change_source = 'WORK_ORDER') AND (failure_id IS NULL OR change_source = 'FAILURE')`
- `ck_machine_state_history_new_state_enum`: `new_state IN ('RUNNING','IDLE','PLANNED_SHUTDOWN','MAINTENANCE','FAILED')`
- `ck_machine_state_history_previous_state_enum`: `previous_state IS NULL OR previous_state IN ('RUNNING','IDLE','PLANNED_SHUTDOWN','MAINTENANCE','FAILED')`
- `ck_machine_state_history_source_enum`: `change_source IN ('SCHEDULE','WORK_ORDER','FAILURE','MANUAL')`
- `ck_machine_state_history_state_really_changed`: `previous_state IS NULL OR previous_state <> new_state`

**Indexes**

- `ix_machine_state_history_failure_id` on (failure_id)
- `ix_machine_state_history_work_order_id` on (work_order_id)

## `work_order_part`

Bridge table (N:M) work order <-> part, with quantity used and replacement timestamp.

| Column | Type | Null? | Key | Notes |
|---|---|---|---|---|
| `work_order_id` | VARCHAR(20) | no | PK; FK -> maintenance_work_order.work_order_id |  |
| `part_id` | VARCHAR(16) | no | PK; FK -> part.part_id |  |
| `quantity_used` | NUMERIC(10, 2) | no |  | In the part's unit_of_measure. Must be > 0. |
| `replaced_at` | TIMESTAMP WITH TIME ZONE | yes |  | When the part was fitted. NULL if not recorded. |

**CHECK constraints**

- `ck_work_order_part_quantity_positive`: `quantity_used > 0`

**Indexes**

- `ix_work_order_part_part_id` on (part_id)

## `work_order_status_history`

Append-only log of work-order lifecycle transitions; legal transitions are enforced.

| Column | Type | Null? | Key | Notes |
|---|---|---|---|---|
| `history_id` | VARCHAR(64) | no | PK | Format WSH-<work-order-id>-YYYYMMDDTHHMMSSZ. |
| `work_order_id` | VARCHAR(20) | no | FK -> maintenance_work_order.work_order_id; UQ (with changed_at) |  |
| `previous_status` | VARCHAR(12) | yes |  |  |
| `new_status` | VARCHAR(12) | no |  |  |
| `changed_at` | TIMESTAMP WITH TIME ZONE | no | UQ (with work_order_id) |  |
| `changed_by_technician_id` | VARCHAR(16) | yes | FK -> technician.technician_id | Optional. |
| `note` | VARCHAR(200) | yes |  |  |

**CHECK constraints**

- `ck_work_order_status_history_allowed_transition`: `(previous_status IS NULL AND new_status = 'OPEN') OR (previous_status IS NOT NULL AND previous_status = 'OPEN' AND new_status IN ('IN_PROGRESS','CANCELLED')) OR (previous_status IS NOT NULL AND previous_status = 'IN_PROGRESS' AND new_status IN ('COMPLETED','CANCELLED'))`
- `ck_work_order_status_history_new_status_enum`: `new_status IN ('OPEN','IN_PROGRESS','COMPLETED','CANCELLED')`

## `work_order_technician`

Bridge table (N:M) work order <-> technician, with role and hours worked.

| Column | Type | Null? | Key | Notes |
|---|---|---|---|---|
| `work_order_id` | VARCHAR(20) | no | PK; FK -> maintenance_work_order.work_order_id |  |
| `technician_id` | VARCHAR(16) | no | PK; FK -> technician.technician_id |  |
| `role` | VARCHAR(10) | no |  |  |
| `assigned_at` | TIMESTAMP WITH TIME ZONE | no |  |  |
| `hours_worked` | NUMERIC(6, 2) | yes |  | Hours. |

**CHECK constraints**

- `ck_work_order_technician_hours_non_negative`: `hours_worked IS NULL OR hours_worked >= 0`
- `ck_work_order_technician_role_enum`: `role IN ('LEAD','ASSISTANT')`

**Indexes**

- `ix_work_order_technician_technician_id` on (technician_id)
- `uq_work_order_technician_one_lead` on (work_order_id) UNIQUE WHERE role = 'LEAD'
