"""phase 3a relational model

Adds 10 NEW tables only (shifts, technicians, parts, failures, work orders, 2 bridge tables,
3 history tables). The 5 starter tables and their data are not modified in any way.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-28 02:27:52.769052

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('part',
    sa.Column('part_id', sa.String(length=16), nullable=False),
    sa.Column('part_number', sa.String(length=32), nullable=False),
    sa.Column('part_name', sa.String(length=100), nullable=False),
    sa.Column('category', sa.String(length=16), nullable=False),
    sa.Column('unit_of_measure', sa.String(length=4), nullable=False),
    sa.Column('unit_cost', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.CheckConstraint("category IN ('BEARING','SEAL','MOTOR','BELT','FILTER','SENSOR','LUBRICANT','ELECTRICAL','OTHER')", name=op.f('ck_part_category_enum')),
    sa.CheckConstraint("status IN ('ACTIVE','DISCONTINUED')", name=op.f('ck_part_status_enum')),
    sa.CheckConstraint("unit_of_measure IN ('EA','L','KG','M')", name=op.f('ck_part_unit_enum')),
    sa.CheckConstraint('unit_cost >= 0', name=op.f('ck_part_cost_non_negative')),
    sa.PrimaryKeyConstraint('part_id', name=op.f('pk_part')),
    sa.UniqueConstraint('part_number', name=op.f('uq_part_part_number'))
    )
    op.create_table('technician',
    sa.Column('technician_id', sa.String(length=16), nullable=False),
    sa.Column('plant_id', sa.String(length=16), nullable=False),
    sa.Column('full_name', sa.String(length=100), nullable=False),
    sa.Column('specialty', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('hired_on', sa.Date(), nullable=False),
    sa.CheckConstraint("specialty IN ('MECHANICAL','ELECTRICAL','INSTRUMENTATION','GENERAL')", name=op.f('ck_technician_specialty_enum')),
    sa.CheckConstraint("status IN ('ACTIVE','ON_LEAVE','INACTIVE')", name=op.f('ck_technician_status_enum')),
    sa.ForeignKeyConstraint(['plant_id'], ['plant.plant_id'], name=op.f('fk_technician_plant_id_plant')),
    sa.PrimaryKeyConstraint('technician_id', name=op.f('pk_technician'))
    )
    op.create_index(op.f('ix_technician_plant_id'), 'technician', ['plant_id'], unique=False)
    op.create_table('failure_event',
    sa.Column('failure_id', sa.String(length=48), nullable=False),
    sa.Column('machine_id', sa.String(length=48), nullable=False),
    sa.Column('failure_category', sa.String(length=16), nullable=False),
    sa.Column('severity', sa.String(length=8), nullable=False),
    sa.Column('symptom_onset_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('failure_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('detected_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.CheckConstraint("(status = 'RESOLVED') = (resolved_at IS NOT NULL)", name=op.f('ck_failure_event_resolved_matches_status')),
    sa.CheckConstraint("failure_category IN ('BEARING_WEAR','OVERHEATING','ELECTRICAL','LUBRICATION','MISALIGNMENT','OTHER')", name=op.f('ck_failure_event_category_enum')),
    sa.CheckConstraint("severity IN ('MINOR','MAJOR','CRITICAL')", name=op.f('ck_failure_event_severity_enum')),
    sa.CheckConstraint("status IN ('CONFIRMED','UNDER_REPAIR','RESOLVED')", name=op.f('ck_failure_event_status_enum')),
    sa.CheckConstraint('detected_at IS NULL OR detected_at >= symptom_onset_at', name=op.f('ck_failure_event_detected_after_onset')),
    sa.CheckConstraint('resolved_at IS NULL OR resolved_at >= failure_at', name=op.f('ck_failure_event_resolved_after_failure')),
    sa.CheckConstraint('symptom_onset_at <= failure_at', name=op.f('ck_failure_event_onset_before_failure')),
    sa.ForeignKeyConstraint(['machine_id'], ['machine.machine_id'], name=op.f('fk_failure_event_machine_id_machine')),
    sa.PrimaryKeyConstraint('failure_id', name=op.f('pk_failure_event')),
    sa.UniqueConstraint('machine_id', 'failure_at', name=op.f('uq_failure_event_machine_id'))
    )
    op.create_table('operating_shift',
    sa.Column('shift_id', sa.String(length=48), nullable=False),
    sa.Column('machine_id', sa.String(length=48), nullable=False),
    sa.Column('shift_name', sa.String(length=12), nullable=False),
    sa.Column('shift_start', sa.DateTime(timezone=True), nullable=False),
    sa.Column('shift_end', sa.DateTime(timezone=True), nullable=False),
    sa.Column('planned_state', sa.String(length=20), nullable=False),
    sa.Column('planned_load_pct', sa.Numeric(precision=5, scale=2), nullable=True),
    sa.CheckConstraint("planned_state IN ('RUNNING','IDLE','PLANNED_SHUTDOWN')", name=op.f('ck_operating_shift_planned_state_enum')),
    sa.CheckConstraint("shift_name IN ('MORNING','AFTERNOON','NIGHT')", name=op.f('ck_operating_shift_name_enum')),
    sa.CheckConstraint('planned_load_pct IS NULL OR planned_load_pct BETWEEN 0 AND 100', name=op.f('ck_operating_shift_load_pct_range')),
    sa.CheckConstraint('shift_end > shift_start', name=op.f('ck_operating_shift_end_after_start')),
    sa.ForeignKeyConstraint(['machine_id'], ['machine.machine_id'], name=op.f('fk_operating_shift_machine_id_machine')),
    sa.PrimaryKeyConstraint('shift_id', name=op.f('pk_operating_shift')),
    sa.UniqueConstraint('machine_id', 'shift_start', name=op.f('uq_operating_shift_machine_id'))
    )
    op.create_table('maintenance_work_order',
    sa.Column('work_order_id', sa.String(length=20), nullable=False),
    sa.Column('machine_id', sa.String(length=48), nullable=False),
    sa.Column('failure_id', sa.String(length=48), nullable=True),
    sa.Column('maintenance_type', sa.String(length=12), nullable=False),
    sa.Column('priority', sa.String(length=8), nullable=False),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('scheduled_for', sa.DateTime(timezone=True), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('downtime_start', sa.DateTime(timezone=True), nullable=True),
    sa.Column('returned_to_service_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('findings', sa.Text(), nullable=True),
    sa.Column('corrective_action', sa.Text(), nullable=True),
    sa.CheckConstraint("(status = 'OPEN' AND started_at IS NULL AND completed_at IS NULL) OR (status = 'IN_PROGRESS' AND started_at IS NOT NULL AND completed_at IS NULL) OR (status = 'COMPLETED' AND started_at IS NOT NULL AND completed_at IS NOT NULL) OR (status = 'CANCELLED' AND completed_at IS NULL)", name=op.f('ck_maintenance_work_order_status_matches_timestamps')),
    sa.CheckConstraint("maintenance_type IN ('PREVENTIVE','CORRECTIVE','PREDICTIVE','INSPECTION')", name=op.f('ck_maintenance_work_order_type_enum')),
    sa.CheckConstraint("priority IN ('LOW','MEDIUM','HIGH','URGENT')", name=op.f('ck_maintenance_work_order_priority_enum')),
    sa.CheckConstraint("status IN ('OPEN','IN_PROGRESS','COMPLETED','CANCELLED')", name=op.f('ck_maintenance_work_order_status_enum')),
    sa.CheckConstraint('returned_to_service_at IS NULL OR (downtime_start IS NOT NULL AND returned_to_service_at >= downtime_start)', name=op.f('ck_maintenance_work_order_downtime_order')),
    sa.CheckConstraint('started_at IS NULL OR completed_at IS NULL OR completed_at >= started_at', name=op.f('ck_maintenance_work_order_end_after_start')),
    sa.CheckConstraint('started_at IS NULL OR started_at >= created_at', name=op.f('ck_maintenance_work_order_start_after_created')),
    sa.ForeignKeyConstraint(['failure_id'], ['failure_event.failure_id'], name=op.f('fk_maintenance_work_order_failure_id_failure_event')),
    sa.ForeignKeyConstraint(['machine_id'], ['machine.machine_id'], name=op.f('fk_maintenance_work_order_machine_id_machine')),
    sa.PrimaryKeyConstraint('work_order_id', name=op.f('pk_maintenance_work_order'))
    )
    op.create_index(op.f('ix_maintenance_work_order_failure_id'), 'maintenance_work_order', ['failure_id'], unique=False)
    op.create_index('ix_work_order_machine_created', 'maintenance_work_order', ['machine_id', 'created_at'], unique=False)
    op.create_table('sensor_status_history',
    sa.Column('history_id', sa.String(length=80), nullable=False),
    sa.Column('sensor_id', sa.String(length=64), nullable=False),
    sa.Column('previous_status', sa.String(length=16), nullable=True),
    sa.Column('new_status', sa.String(length=16), nullable=False),
    sa.Column('changed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('reason', sa.String(length=200), nullable=True),
    sa.CheckConstraint("new_status IN ('ACTIVE','FAULTY','RETIRED')", name=op.f('ck_sensor_status_history_new_status_enum')),
    sa.CheckConstraint("previous_status IS DISTINCT FROM 'RETIRED'", name=op.f('ck_sensor_status_history_retired_is_final')),
    sa.CheckConstraint("previous_status IS NULL OR previous_status IN ('ACTIVE','FAULTY','RETIRED')", name=op.f('ck_sensor_status_history_previous_status_enum')),
    sa.CheckConstraint('previous_status IS NULL OR previous_status <> new_status', name=op.f('ck_sensor_status_history_status_really_changed')),
    sa.ForeignKeyConstraint(['sensor_id'], ['sensor.sensor_id'], name=op.f('fk_sensor_status_history_sensor_id_sensor')),
    sa.PrimaryKeyConstraint('history_id', name=op.f('pk_sensor_status_history')),
    sa.UniqueConstraint('sensor_id', 'changed_at', name=op.f('uq_sensor_status_history_sensor_id'))
    )
    op.create_table('machine_state_history',
    sa.Column('history_id', sa.String(length=64), nullable=False),
    sa.Column('machine_id', sa.String(length=48), nullable=False),
    sa.Column('previous_state', sa.String(length=20), nullable=True),
    sa.Column('new_state', sa.String(length=20), nullable=False),
    sa.Column('changed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('change_source', sa.String(length=12), nullable=False),
    sa.Column('work_order_id', sa.String(length=20), nullable=True),
    sa.Column('failure_id', sa.String(length=48), nullable=True),
    sa.CheckConstraint("(work_order_id IS NULL OR change_source = 'WORK_ORDER') AND (failure_id IS NULL OR change_source = 'FAILURE')", name=op.f('ck_machine_state_history_link_matches_source')),
    sa.CheckConstraint("change_source IN ('SCHEDULE','WORK_ORDER','FAILURE','MANUAL')", name=op.f('ck_machine_state_history_source_enum')),
    sa.CheckConstraint("new_state IN ('RUNNING','IDLE','PLANNED_SHUTDOWN','MAINTENANCE','FAILED')", name=op.f('ck_machine_state_history_new_state_enum')),
    sa.CheckConstraint("previous_state IS NULL OR previous_state IN ('RUNNING','IDLE','PLANNED_SHUTDOWN','MAINTENANCE','FAILED')", name=op.f('ck_machine_state_history_previous_state_enum')),
    sa.CheckConstraint('previous_state IS NULL OR previous_state <> new_state', name=op.f('ck_machine_state_history_state_really_changed')),
    sa.ForeignKeyConstraint(['failure_id'], ['failure_event.failure_id'], name=op.f('fk_machine_state_history_failure_id_failure_event')),
    sa.ForeignKeyConstraint(['machine_id'], ['machine.machine_id'], name=op.f('fk_machine_state_history_machine_id_machine')),
    sa.ForeignKeyConstraint(['work_order_id'], ['maintenance_work_order.work_order_id'], name=op.f('fk_machine_state_history_work_order_id_maintenance_work_order')),
    sa.PrimaryKeyConstraint('history_id', name=op.f('pk_machine_state_history')),
    sa.UniqueConstraint('machine_id', 'changed_at', name=op.f('uq_machine_state_history_machine_id'))
    )
    op.create_index(op.f('ix_machine_state_history_failure_id'), 'machine_state_history', ['failure_id'], unique=False)
    op.create_index(op.f('ix_machine_state_history_work_order_id'), 'machine_state_history', ['work_order_id'], unique=False)
    op.create_table('work_order_part',
    sa.Column('work_order_id', sa.String(length=20), nullable=False),
    sa.Column('part_id', sa.String(length=16), nullable=False),
    sa.Column('quantity_used', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('replaced_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint('quantity_used > 0', name=op.f('ck_work_order_part_quantity_positive')),
    sa.ForeignKeyConstraint(['part_id'], ['part.part_id'], name=op.f('fk_work_order_part_part_id_part')),
    sa.ForeignKeyConstraint(['work_order_id'], ['maintenance_work_order.work_order_id'], name=op.f('fk_work_order_part_work_order_id_maintenance_work_order')),
    sa.PrimaryKeyConstraint('work_order_id', 'part_id', name=op.f('pk_work_order_part'))
    )
    op.create_index(op.f('ix_work_order_part_part_id'), 'work_order_part', ['part_id'], unique=False)
    op.create_table('work_order_status_history',
    sa.Column('history_id', sa.String(length=64), nullable=False),
    sa.Column('work_order_id', sa.String(length=20), nullable=False),
    sa.Column('previous_status', sa.String(length=12), nullable=True),
    sa.Column('new_status', sa.String(length=12), nullable=False),
    sa.Column('changed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('changed_by_technician_id', sa.String(length=16), nullable=True),
    sa.Column('note', sa.String(length=200), nullable=True),
    sa.CheckConstraint("(previous_status IS NULL AND new_status = 'OPEN') OR (previous_status IS NOT NULL AND previous_status = 'OPEN' AND new_status IN ('IN_PROGRESS','CANCELLED')) OR (previous_status IS NOT NULL AND previous_status = 'IN_PROGRESS' AND new_status IN ('COMPLETED','CANCELLED'))", name=op.f('ck_work_order_status_history_allowed_transition')),
    sa.CheckConstraint("new_status IN ('OPEN','IN_PROGRESS','COMPLETED','CANCELLED')", name=op.f('ck_work_order_status_history_new_status_enum')),
    sa.ForeignKeyConstraint(['changed_by_technician_id'], ['technician.technician_id'], name='fk_wo_status_history_technician'),
    sa.ForeignKeyConstraint(['work_order_id'], ['maintenance_work_order.work_order_id'], name='fk_wo_status_history_work_order'),
    sa.PrimaryKeyConstraint('history_id', name=op.f('pk_work_order_status_history')),
    sa.UniqueConstraint('work_order_id', 'changed_at', name=op.f('uq_work_order_status_history_work_order_id'))
    )
    op.create_table('work_order_technician',
    sa.Column('work_order_id', sa.String(length=20), nullable=False),
    sa.Column('technician_id', sa.String(length=16), nullable=False),
    sa.Column('role', sa.String(length=10), nullable=False),
    sa.Column('assigned_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('hours_worked', sa.Numeric(precision=6, scale=2), nullable=True),
    sa.CheckConstraint("role IN ('LEAD','ASSISTANT')", name=op.f('ck_work_order_technician_role_enum')),
    sa.CheckConstraint('hours_worked IS NULL OR hours_worked >= 0', name=op.f('ck_work_order_technician_hours_non_negative')),
    sa.ForeignKeyConstraint(['technician_id'], ['technician.technician_id'], name=op.f('fk_work_order_technician_technician_id_technician')),
    sa.ForeignKeyConstraint(['work_order_id'], ['maintenance_work_order.work_order_id'], name=op.f('fk_work_order_technician_work_order_id_maintenance_work_order')),
    sa.PrimaryKeyConstraint('work_order_id', 'technician_id', name=op.f('pk_work_order_technician'))
    )
    op.create_index(op.f('ix_work_order_technician_technician_id'), 'work_order_technician', ['technician_id'], unique=False)
    op.create_index('uq_work_order_technician_one_lead', 'work_order_technician', ['work_order_id'], unique=True, postgresql_where=sa.text("role = 'LEAD'"))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_work_order_technician_one_lead', table_name='work_order_technician', postgresql_where=sa.text("role = 'LEAD'"))
    op.drop_index(op.f('ix_work_order_technician_technician_id'), table_name='work_order_technician')
    op.drop_table('work_order_technician')
    op.drop_table('work_order_status_history')
    op.drop_index(op.f('ix_work_order_part_part_id'), table_name='work_order_part')
    op.drop_table('work_order_part')
    op.drop_index(op.f('ix_machine_state_history_work_order_id'), table_name='machine_state_history')
    op.drop_index(op.f('ix_machine_state_history_failure_id'), table_name='machine_state_history')
    op.drop_table('machine_state_history')
    op.drop_table('sensor_status_history')
    op.drop_index('ix_work_order_machine_created', table_name='maintenance_work_order')
    op.drop_index(op.f('ix_maintenance_work_order_failure_id'), table_name='maintenance_work_order')
    op.drop_table('maintenance_work_order')
    op.drop_table('operating_shift')
    op.drop_table('failure_event')
    op.drop_index(op.f('ix_technician_plant_id'), table_name='technician')
    op.drop_table('technician')
    op.drop_table('part')
