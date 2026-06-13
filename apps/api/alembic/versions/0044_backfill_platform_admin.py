"""Backfill the platform_admin role.

Revision ID: 0044_backfill_platform_admin
Revises: 0043_audit_request_context
Create Date: 2026-06-13

Introduces the ``platform_admin`` membership role (platform rework,
Phase 1) by granting it to every existing active ``internal_admin``.
This is the migration half of the role split: the IT/platform surfaces
(``/platform/*``) will gate on ``platform_admin`` while the compliance
surfaces keep gating on ``internal_admin``. Backfilling here means no
current operator loses access the moment the new gate ships.

``memberships.role`` is ``VARCHAR(40)`` with no CHECK constraint, so the
new value needs no schema change — only this data insert. The insert is
re-runnable: a ``NOT EXISTS`` guard skips users who already hold the
role, and the new rows are ``is_primary = false`` so they never collide
with the one-active-primary-per-org partial unique index.

Postgres-only by design (test fixtures build the schema via
``create_all``, not Alembic).
"""

from __future__ import annotations

from alembic import op

revision = "0044_backfill_platform_admin"
down_revision = "0043_audit_request_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO memberships (
            id, user_id, organization_id, role,
            is_primary, status, created_at, updated_at
        )
        SELECT
            gen_random_uuid()::text,
            m.user_id,
            m.organization_id,
            'platform_admin',
            false,
            'active',
            now(),
            now()
        FROM memberships m
        WHERE m.role = 'internal_admin'
          AND m.status = 'active'
          AND NOT EXISTS (
              SELECT 1 FROM memberships pm
              WHERE pm.user_id = m.user_id
                AND pm.organization_id = m.organization_id
                AND pm.role = 'platform_admin'
          )
        """
    )


def downgrade() -> None:
    # Remove only the rows this migration could have created. Safe
    # because no other surface mints platform_admin memberships yet.
    op.execute("DELETE FROM memberships WHERE role = 'platform_admin'")
