"""Wise events — cliente scope.

Revision ID: 0041_wise_events_client_scope
Revises: 0040_document_rfc_alignment
Create Date: 2026-06-13

Lets the cliente (buyer) Wise dock persist analytics events to the same
``wise_events`` table the provider dock uses, instead of the previous
log-only path.

The provider dock anchors every event to a ``workspace_id``. The cliente
dock has no single workspace — the buyer reasons over a whole portfolio
of vendors — so cliente events anchor to ``client_id`` instead. Exactly
one of the two columns is populated per row.

Changes (all additive / backward-compatible on Postgres):
- ``wise_events.workspace_id`` becomes nullable (provider rows still set
  it; cliente rows leave it NULL).
- New nullable ``wise_events.client_id`` FK → ``clients.id``, indexed so
  per-client rollups stay cheap.

No data backfill: existing rows are all provider events with a
``workspace_id`` already set; ``client_id`` is simply NULL for them.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0041_wise_events_client_scope"
down_revision = "0040_document_rfc_alignment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "wise_events",
        sa.Column(
            "client_id",
            sa.String(length=36),
            sa.ForeignKey("clients.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_wise_events_client_id",
        "wise_events",
        ["client_id"],
    )
    # Provider rows keep their workspace_id; cliente rows leave it NULL.
    op.alter_column(
        "wise_events",
        "workspace_id",
        existing_type=sa.String(length=36),
        nullable=True,
    )


def downgrade() -> None:
    # NOTE: re-imposing NOT NULL will fail if any cliente events (NULL
    # workspace_id) have been written. Delete those rows first if you
    # must downgrade past this revision.
    op.alter_column(
        "wise_events",
        "workspace_id",
        existing_type=sa.String(length=36),
        nullable=False,
    )
    op.drop_index("ix_wise_events_client_id", table_name="wise_events")
    op.drop_column("wise_events", "client_id")
