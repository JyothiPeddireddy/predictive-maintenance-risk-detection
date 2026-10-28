"""history tables are append-only

Adds a database trigger that rejects UPDATE and DELETE on the three *_history tables, so history
cannot be overwritten by accident (or by a bug). New rows can always be INSERTed.
No tables or data are changed. (Triggers are not visible to Alembic autogenerate, so this is hand-written.)

Revision ID: 0003
Revises: 0002
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

HISTORY_TABLES = ("machine_state_history", "sensor_status_history", "work_order_status_history")


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION forbid_history_change() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'table % is append-only: % is not allowed', TG_TABLE_NAME, TG_OP
                USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql
    """)
    for table in HISTORY_TABLES:
        op.execute(f"""
            CREATE TRIGGER trg_{table}_append_only
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION forbid_history_change()
        """)


def downgrade() -> None:
    for table in HISTORY_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_append_only ON {table}")
    op.execute("DROP FUNCTION IF EXISTS forbid_history_change()")
