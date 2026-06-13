"""Audit log request context.

Revision ID: 0043_audit_request_context
Revises: 0042_user_soft_delete
Create Date: 2026-06-13

Adds best-effort request provenance to the append-only audit log so an
operator action can be traced to a network origin (platform rework,
Phase 0). Both columns are nullable: system-originated events and rows
written before this revision carry NULL. ``add_audit_event`` /
``_audit_admin`` populate them from the first ``X-Forwarded-For`` hop
(Render terminates TLS in front of uvicorn).

- ``audit_log.ip_address`` — VARCHAR(45), sized for an IPv6 literal.
- ``audit_log.user_agent`` — VARCHAR(512), truncated defensively.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0043_audit_request_context"
down_revision = "0042_user_soft_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "audit_log",
        sa.Column("ip_address", sa.String(length=45), nullable=True),
    )
    op.add_column(
        "audit_log",
        sa.Column("user_agent", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("audit_log", "user_agent")
    op.drop_column("audit_log", "ip_address")
