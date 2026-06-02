"""Enforce audit_log as append-only via DB-level triggers.

The ``audit_log`` table is the forensic spine of CheckWise's REPSE
compliance story — every consent acknowledgment, every reviewer
decision, every privilege change writes a row here. Without
database-level enforcement a compromised ``internal_admin`` (or a
buggy migration) could DELETE or UPDATE rows and erase the trail
silently. Application code already only INSERTs, but defence in
depth: a Postgres ``BEFORE DELETE`` / ``BEFORE UPDATE`` trigger
that raises an exception means even a manual ``psql`` session
can't quietly mutate history.

The trigger is intentionally a hard ``RAISE EXCEPTION`` rather than
a no-op so the operator is forced to notice when something tries
to touch the audit row. The only legitimate way to retract an
entry is to write a *new* compensating row that references the
original — append-only by construction.

Note: PostgreSQL superusers can still ``ALTER TABLE ... DISABLE
TRIGGER`` so this is not a substitute for least-privilege DB
roles. It IS a substitute for "oops I ran the wrong DELETE in
the admin console at 2am". For full forensic guarantees the
ops runbook needs to mandate the app role doesn't own the table.
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0031_audit_log_append_only"
down_revision = "0030_notif_fabric_backfill"
branch_labels = None
depends_on = None


_FN_NAME = "checkwise_audit_log_block_mutation"
_TRIGGER_DELETE = "audit_log_block_delete"
_TRIGGER_UPDATE = "audit_log_block_update"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {_FN_NAME}()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION
                'audit_log is append-only: % blocked on row %',
                TG_OP, COALESCE(OLD.id::text, '<unknown>')
                USING ERRCODE = 'insufficient_privilege';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        f"""
        DROP TRIGGER IF EXISTS {_TRIGGER_DELETE} ON audit_log;
        CREATE TRIGGER {_TRIGGER_DELETE}
            BEFORE DELETE ON audit_log
            FOR EACH ROW
            EXECUTE FUNCTION {_FN_NAME}();
        """
    )
    op.execute(
        f"""
        DROP TRIGGER IF EXISTS {_TRIGGER_UPDATE} ON audit_log;
        CREATE TRIGGER {_TRIGGER_UPDATE}
            BEFORE UPDATE ON audit_log
            FOR EACH ROW
            EXECUTE FUNCTION {_FN_NAME}();
        """
    )


def downgrade() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER_UPDATE} ON audit_log;")
    op.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER_DELETE} ON audit_log;")
    op.execute(f"DROP FUNCTION IF EXISTS {_FN_NAME}();")
