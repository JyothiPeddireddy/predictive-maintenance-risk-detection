-- Generated from src/models/tables.py by: python -m src.cli export-schema
-- Informational copy. The database itself is built by the Alembic migrations in migrations/.
-- (The append-only triggers on the *_history tables come from migration 0003 and are not shown here.)

CREATE TABLE part (
	part_id VARCHAR(16) NOT NULL, 
	part_number VARCHAR(32) NOT NULL, 
	part_name VARCHAR(100) NOT NULL, 
	category VARCHAR(16) NOT NULL, 
	unit_of_measure VARCHAR(4) NOT NULL, 
	unit_cost NUMERIC(12, 2) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	CONSTRAINT pk_part PRIMARY KEY (part_id), 
	CONSTRAINT ck_part_category_enum CHECK (category IN ('BEARING','SEAL','MOTOR','BELT','FILTER','SENSOR','LUBRICANT','ELECTRICAL','OTHER')), 
	CONSTRAINT ck_part_unit_enum CHECK (unit_of_measure IN ('EA','L','KG','M')), 
	CONSTRAINT ck_part_status_enum CHECK (status IN ('ACTIVE','DISCONTINUED')), 
	CONSTRAINT ck_part_cost_non_negative CHECK (unit_cost >= 0), 
	CONSTRAINT uq_part_part_number UNIQUE (part_number)
);

CREATE TABLE plant (
	plant_id VARCHAR(16) NOT NULL, 
	plant_name VARCHAR(100) NOT NULL, 
	timezone VARCHAR(40) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	commissioned_on DATE NOT NULL, 
	CONSTRAINT pk_plant PRIMARY KEY (plant_id), 
	CONSTRAINT ck_plant_status_enum CHECK (status IN ('ACTIVE','INACTIVE','DECOMMISSIONED')), 
	CONSTRAINT uq_plant_plant_name UNIQUE (plant_name)
);

CREATE TABLE production_line (
	line_id VARCHAR(32) NOT NULL, 
	plant_id VARCHAR(16) NOT NULL, 
	line_name VARCHAR(100) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	CONSTRAINT pk_production_line PRIMARY KEY (line_id), 
	CONSTRAINT uq_production_line_plant_id UNIQUE (plant_id, line_name), 
	CONSTRAINT ck_production_line_status_enum CHECK (status IN ('ACTIVE','INACTIVE','DECOMMISSIONED')), 
	CONSTRAINT fk_production_line_plant_id_plant FOREIGN KEY(plant_id) REFERENCES plant (plant_id)
);

CREATE INDEX ix_production_line_plant_id ON production_line (plant_id);

CREATE TABLE technician (
	technician_id VARCHAR(16) NOT NULL, 
	plant_id VARCHAR(16) NOT NULL, 
	full_name VARCHAR(100) NOT NULL, 
	specialty VARCHAR(20) NOT NULL, 
	status VARCHAR(12) NOT NULL, 
	hired_on DATE NOT NULL, 
	CONSTRAINT pk_technician PRIMARY KEY (technician_id), 
	CONSTRAINT ck_technician_specialty_enum CHECK (specialty IN ('MECHANICAL','ELECTRICAL','INSTRUMENTATION','GENERAL')), 
	CONSTRAINT ck_technician_status_enum CHECK (status IN ('ACTIVE','ON_LEAVE','INACTIVE')), 
	CONSTRAINT fk_technician_plant_id_plant FOREIGN KEY(plant_id) REFERENCES plant (plant_id)
);

CREATE INDEX ix_technician_plant_id ON technician (plant_id);

CREATE TABLE machine (
	machine_id VARCHAR(48) NOT NULL, 
	line_id VARCHAR(32) NOT NULL, 
	machine_name VARCHAR(100) NOT NULL, 
	machine_type VARCHAR(32) NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	installed_on DATE NOT NULL, 
	CONSTRAINT pk_machine PRIMARY KEY (machine_id), 
	CONSTRAINT uq_machine_line_id UNIQUE (line_id, machine_name), 
	CONSTRAINT ck_machine_status_enum CHECK (status IN ('OPERATIONAL','UNDER_MAINTENANCE','FAILED','DECOMMISSIONED')), 
	CONSTRAINT fk_machine_line_id_production_line FOREIGN KEY(line_id) REFERENCES production_line (line_id)
);

CREATE INDEX ix_machine_line_id ON machine (line_id);

CREATE TABLE failure_event (
	failure_id VARCHAR(48) NOT NULL, 
	machine_id VARCHAR(48) NOT NULL, 
	failure_category VARCHAR(16) NOT NULL, 
	severity VARCHAR(8) NOT NULL, 
	symptom_onset_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	failure_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	detected_at TIMESTAMP WITH TIME ZONE, 
	resolved_at TIMESTAMP WITH TIME ZONE, 
	status VARCHAR(12) NOT NULL, 
	description TEXT, 
	CONSTRAINT pk_failure_event PRIMARY KEY (failure_id), 
	CONSTRAINT uq_failure_event_machine_id UNIQUE (machine_id, failure_at), 
	CONSTRAINT ck_failure_event_category_enum CHECK (failure_category IN ('BEARING_WEAR','OVERHEATING','ELECTRICAL','LUBRICATION','MISALIGNMENT','OTHER')), 
	CONSTRAINT ck_failure_event_severity_enum CHECK (severity IN ('MINOR','MAJOR','CRITICAL')), 
	CONSTRAINT ck_failure_event_status_enum CHECK (status IN ('CONFIRMED','UNDER_REPAIR','RESOLVED')), 
	CONSTRAINT ck_failure_event_onset_before_failure CHECK (symptom_onset_at <= failure_at), 
	CONSTRAINT ck_failure_event_detected_after_onset CHECK (detected_at IS NULL OR detected_at >= symptom_onset_at), 
	CONSTRAINT ck_failure_event_resolved_after_failure CHECK (resolved_at IS NULL OR resolved_at >= failure_at), 
	CONSTRAINT ck_failure_event_resolved_matches_status CHECK ((status = 'RESOLVED') = (resolved_at IS NOT NULL)), 
	CONSTRAINT fk_failure_event_machine_id_machine FOREIGN KEY(machine_id) REFERENCES machine (machine_id)
);

CREATE TABLE operating_shift (
	shift_id VARCHAR(48) NOT NULL, 
	machine_id VARCHAR(48) NOT NULL, 
	shift_name VARCHAR(12) NOT NULL, 
	shift_start TIMESTAMP WITH TIME ZONE NOT NULL, 
	shift_end TIMESTAMP WITH TIME ZONE NOT NULL, 
	planned_state VARCHAR(20) NOT NULL, 
	planned_load_pct NUMERIC(5, 2), 
	CONSTRAINT pk_operating_shift PRIMARY KEY (shift_id), 
	CONSTRAINT uq_operating_shift_machine_id UNIQUE (machine_id, shift_start), 
	CONSTRAINT ck_operating_shift_name_enum CHECK (shift_name IN ('MORNING','AFTERNOON','NIGHT')), 
	CONSTRAINT ck_operating_shift_planned_state_enum CHECK (planned_state IN ('RUNNING','IDLE','PLANNED_SHUTDOWN')), 
	CONSTRAINT ck_operating_shift_end_after_start CHECK (shift_end > shift_start), 
	CONSTRAINT ck_operating_shift_load_pct_range CHECK (planned_load_pct IS NULL OR planned_load_pct BETWEEN 0 AND 100), 
	CONSTRAINT fk_operating_shift_machine_id_machine FOREIGN KEY(machine_id) REFERENCES machine (machine_id)
);

CREATE TABLE sensor (
	sensor_id VARCHAR(64) NOT NULL, 
	machine_id VARCHAR(48) NOT NULL, 
	sensor_type VARCHAR(8) NOT NULL, 
	sensor_seq INTEGER NOT NULL, 
	unit VARCHAR(12) NOT NULL, 
	min_plausible NUMERIC(12, 3) NOT NULL, 
	max_plausible NUMERIC(12, 3) NOT NULL, 
	sampling_interval_s INTEGER NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	CONSTRAINT pk_sensor PRIMARY KEY (sensor_id), 
	CONSTRAINT uq_sensor_machine_id UNIQUE (machine_id, sensor_type, sensor_seq), 
	CONSTRAINT ck_sensor_type_enum CHECK (sensor_type IN ('TEMP','VIB')), 
	CONSTRAINT ck_sensor_status_enum CHECK (status IN ('ACTIVE','FAULTY','RETIRED')), 
	CONSTRAINT ck_sensor_range_order CHECK (min_plausible < max_plausible), 
	CONSTRAINT ck_sensor_interval_positive CHECK (sampling_interval_s > 0), 
	CONSTRAINT fk_sensor_machine_id_machine FOREIGN KEY(machine_id) REFERENCES machine (machine_id)
);

CREATE INDEX ix_sensor_machine_id ON sensor (machine_id);

CREATE TABLE maintenance_work_order (
	work_order_id VARCHAR(20) NOT NULL, 
	machine_id VARCHAR(48) NOT NULL, 
	failure_id VARCHAR(48), 
	maintenance_type VARCHAR(12) NOT NULL, 
	priority VARCHAR(8) NOT NULL, 
	status VARCHAR(12) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	scheduled_for TIMESTAMP WITH TIME ZONE, 
	started_at TIMESTAMP WITH TIME ZONE, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	downtime_start TIMESTAMP WITH TIME ZONE, 
	returned_to_service_at TIMESTAMP WITH TIME ZONE, 
	findings TEXT, 
	corrective_action TEXT, 
	CONSTRAINT pk_maintenance_work_order PRIMARY KEY (work_order_id), 
	CONSTRAINT ck_maintenance_work_order_type_enum CHECK (maintenance_type IN ('PREVENTIVE','CORRECTIVE','PREDICTIVE','INSPECTION')), 
	CONSTRAINT ck_maintenance_work_order_priority_enum CHECK (priority IN ('LOW','MEDIUM','HIGH','URGENT')), 
	CONSTRAINT ck_maintenance_work_order_status_enum CHECK (status IN ('OPEN','IN_PROGRESS','COMPLETED','CANCELLED')), 
	CONSTRAINT ck_maintenance_work_order_start_after_created CHECK (started_at IS NULL OR started_at >= created_at), 
	CONSTRAINT ck_maintenance_work_order_end_after_start CHECK (started_at IS NULL OR completed_at IS NULL OR completed_at >= started_at), 
	CONSTRAINT ck_maintenance_work_order_downtime_order CHECK (returned_to_service_at IS NULL OR (downtime_start IS NOT NULL AND returned_to_service_at >= downtime_start)), 
	CONSTRAINT ck_maintenance_work_order_status_matches_timestamps CHECK ((status = 'OPEN' AND started_at IS NULL AND completed_at IS NULL) OR (status = 'IN_PROGRESS' AND started_at IS NOT NULL AND completed_at IS NULL) OR (status = 'COMPLETED' AND started_at IS NOT NULL AND completed_at IS NOT NULL) OR (status = 'CANCELLED' AND completed_at IS NULL)), 
	CONSTRAINT fk_maintenance_work_order_machine_id_machine FOREIGN KEY(machine_id) REFERENCES machine (machine_id), 
	CONSTRAINT fk_maintenance_work_order_failure_id_failure_event FOREIGN KEY(failure_id) REFERENCES failure_event (failure_id)
);

CREATE INDEX ix_maintenance_work_order_failure_id ON maintenance_work_order (failure_id);

CREATE INDEX ix_work_order_machine_created ON maintenance_work_order (machine_id, created_at);

CREATE TABLE sensor_status_history (
	history_id VARCHAR(80) NOT NULL, 
	sensor_id VARCHAR(64) NOT NULL, 
	previous_status VARCHAR(16), 
	new_status VARCHAR(16) NOT NULL, 
	changed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	reason VARCHAR(200), 
	CONSTRAINT pk_sensor_status_history PRIMARY KEY (history_id), 
	CONSTRAINT uq_sensor_status_history_sensor_id UNIQUE (sensor_id, changed_at), 
	CONSTRAINT ck_sensor_status_history_new_status_enum CHECK (new_status IN ('ACTIVE','FAULTY','RETIRED')), 
	CONSTRAINT ck_sensor_status_history_previous_status_enum CHECK (previous_status IS NULL OR previous_status IN ('ACTIVE','FAULTY','RETIRED')), 
	CONSTRAINT ck_sensor_status_history_status_really_changed CHECK (previous_status IS NULL OR previous_status <> new_status), 
	CONSTRAINT ck_sensor_status_history_retired_is_final CHECK (previous_status IS DISTINCT FROM 'RETIRED'), 
	CONSTRAINT fk_sensor_status_history_sensor_id_sensor FOREIGN KEY(sensor_id) REFERENCES sensor (sensor_id)
);

CREATE TABLE telemetry_event (
	telemetry_id VARCHAR(96) NOT NULL, 
	sensor_id VARCHAR(64) NOT NULL, 
	event_ts TIMESTAMP WITH TIME ZONE NOT NULL, 
	reading_value NUMERIC(12, 3), 
	unit VARCHAR(12) NOT NULL, 
	machine_state VARCHAR(20) NOT NULL, 
	CONSTRAINT pk_telemetry_event PRIMARY KEY (telemetry_id), 
	CONSTRAINT ck_telemetry_event_state_enum CHECK (machine_state IN ('RUNNING','IDLE','PLANNED_SHUTDOWN','MAINTENANCE')), 
	CONSTRAINT fk_telemetry_event_sensor_id_sensor FOREIGN KEY(sensor_id) REFERENCES sensor (sensor_id)
);

CREATE INDEX ix_telemetry_sensor_ts ON telemetry_event (sensor_id, event_ts);

CREATE TABLE machine_state_history (
	history_id VARCHAR(64) NOT NULL, 
	machine_id VARCHAR(48) NOT NULL, 
	previous_state VARCHAR(20), 
	new_state VARCHAR(20) NOT NULL, 
	changed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	change_source VARCHAR(12) NOT NULL, 
	work_order_id VARCHAR(20), 
	failure_id VARCHAR(48), 
	CONSTRAINT pk_machine_state_history PRIMARY KEY (history_id), 
	CONSTRAINT uq_machine_state_history_machine_id UNIQUE (machine_id, changed_at), 
	CONSTRAINT ck_machine_state_history_new_state_enum CHECK (new_state IN ('RUNNING','IDLE','PLANNED_SHUTDOWN','MAINTENANCE','FAILED')), 
	CONSTRAINT ck_machine_state_history_previous_state_enum CHECK (previous_state IS NULL OR previous_state IN ('RUNNING','IDLE','PLANNED_SHUTDOWN','MAINTENANCE','FAILED')), 
	CONSTRAINT ck_machine_state_history_source_enum CHECK (change_source IN ('SCHEDULE','WORK_ORDER','FAILURE','MANUAL')), 
	CONSTRAINT ck_machine_state_history_state_really_changed CHECK (previous_state IS NULL OR previous_state <> new_state), 
	CONSTRAINT ck_machine_state_history_link_matches_source CHECK ((work_order_id IS NULL OR change_source = 'WORK_ORDER') AND (failure_id IS NULL OR change_source = 'FAILURE')), 
	CONSTRAINT fk_machine_state_history_machine_id_machine FOREIGN KEY(machine_id) REFERENCES machine (machine_id), 
	CONSTRAINT fk_machine_state_history_work_order_id_maintenance_work_order FOREIGN KEY(work_order_id) REFERENCES maintenance_work_order (work_order_id), 
	CONSTRAINT fk_machine_state_history_failure_id_failure_event FOREIGN KEY(failure_id) REFERENCES failure_event (failure_id)
);

CREATE INDEX ix_machine_state_history_failure_id ON machine_state_history (failure_id);

CREATE INDEX ix_machine_state_history_work_order_id ON machine_state_history (work_order_id);

CREATE TABLE work_order_part (
	work_order_id VARCHAR(20) NOT NULL, 
	part_id VARCHAR(16) NOT NULL, 
	quantity_used NUMERIC(10, 2) NOT NULL, 
	replaced_at TIMESTAMP WITH TIME ZONE, 
	CONSTRAINT pk_work_order_part PRIMARY KEY (work_order_id, part_id), 
	CONSTRAINT ck_work_order_part_quantity_positive CHECK (quantity_used > 0), 
	CONSTRAINT fk_work_order_part_work_order_id_maintenance_work_order FOREIGN KEY(work_order_id) REFERENCES maintenance_work_order (work_order_id), 
	CONSTRAINT fk_work_order_part_part_id_part FOREIGN KEY(part_id) REFERENCES part (part_id)
);

CREATE INDEX ix_work_order_part_part_id ON work_order_part (part_id);

CREATE TABLE work_order_status_history (
	history_id VARCHAR(64) NOT NULL, 
	work_order_id VARCHAR(20) NOT NULL, 
	previous_status VARCHAR(12), 
	new_status VARCHAR(12) NOT NULL, 
	changed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	changed_by_technician_id VARCHAR(16), 
	note VARCHAR(200), 
	CONSTRAINT pk_work_order_status_history PRIMARY KEY (history_id), 
	CONSTRAINT uq_work_order_status_history_work_order_id UNIQUE (work_order_id, changed_at), 
	CONSTRAINT ck_work_order_status_history_new_status_enum CHECK (new_status IN ('OPEN','IN_PROGRESS','COMPLETED','CANCELLED')), 
	CONSTRAINT ck_work_order_status_history_allowed_transition CHECK ((previous_status IS NULL AND new_status = 'OPEN') OR (previous_status IS NOT NULL AND previous_status = 'OPEN' AND new_status IN ('IN_PROGRESS','CANCELLED')) OR (previous_status IS NOT NULL AND previous_status = 'IN_PROGRESS' AND new_status IN ('COMPLETED','CANCELLED'))), 
	CONSTRAINT fk_wo_status_history_work_order FOREIGN KEY(work_order_id) REFERENCES maintenance_work_order (work_order_id), 
	CONSTRAINT fk_wo_status_history_technician FOREIGN KEY(changed_by_technician_id) REFERENCES technician (technician_id)
);

CREATE TABLE work_order_technician (
	work_order_id VARCHAR(20) NOT NULL, 
	technician_id VARCHAR(16) NOT NULL, 
	role VARCHAR(10) NOT NULL, 
	assigned_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	hours_worked NUMERIC(6, 2), 
	CONSTRAINT pk_work_order_technician PRIMARY KEY (work_order_id, technician_id), 
	CONSTRAINT ck_work_order_technician_role_enum CHECK (role IN ('LEAD','ASSISTANT')), 
	CONSTRAINT ck_work_order_technician_hours_non_negative CHECK (hours_worked IS NULL OR hours_worked >= 0), 
	CONSTRAINT fk_work_order_technician_work_order_id_maintenance_work_order FOREIGN KEY(work_order_id) REFERENCES maintenance_work_order (work_order_id), 
	CONSTRAINT fk_work_order_technician_technician_id_technician FOREIGN KEY(technician_id) REFERENCES technician (technician_id)
);

CREATE INDEX ix_work_order_technician_technician_id ON work_order_technician (technician_id);

CREATE UNIQUE INDEX uq_work_order_technician_one_lead ON work_order_technician (work_order_id) WHERE role = 'LEAD';
