"""Contact requests — public-landing inbound lead persistence.

Revision ID: 0010_contact_requests
Revises: 0009_reports_core
Create Date: 2026-05-19

Replaces the V1.x mock helper (``frontend/lib/mock/contact-requests.ts``)
which returned a fake folio ID without persisting. New table:

* ``contact_requests`` — one row per submission from the public
  landing-page form. Tiny by design — no joins, no FKs, no
  organization scoping (the form is public).

Conventions matched to the rest of the schema:
- ``String(36)`` ids.
- ``DateTime(timezone=True)`` timestamps.
- ``TimestampMixin`` semantics replicated inline.

Indexes:
- ``status`` — most common ops filter ("show me everything new").
- ``created_at`` — recency-first listings.
- ``ip_hash`` — abuse triage when a cluster of submissions arrives
  from the same hashed IP.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0010_contact_requests"
down_revision = "0009_reports_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contact_requests",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("company", sa.String(length=200), nullable=True),
        sa.Column("role", sa.String(length=60), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "source",
            sa.String(length=60),
            nullable=False,
            server_default="landing",
        ),
        sa.Column(
            "status",
            sa.String(length=40),
            nullable=False,
            server_default="new",
        ),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_contact_requests_status",
        "contact_requests",
        ["status"],
    )
    op.create_index(
        "ix_contact_requests_created_at",
        "contact_requests",
        ["created_at"],
    )
    op.create_index(
        "ix_contact_requests_ip_hash",
        "contact_requests",
        ["ip_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_contact_requests_ip_hash", table_name="contact_requests")
    op.drop_index("ix_contact_requests_created_at", table_name="contact_requests")
    op.drop_index("ix_contact_requests_status", table_name="contact_requests")
    op.drop_table("contact_requests")
