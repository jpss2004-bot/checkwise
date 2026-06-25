"""Phase 5 — client acceptance axis (Axis 2).

Adds the second, orthogonal approval axis: the client's business acceptance
of a submission, independent of CheckWise's compliance-validity verdict
(``submissions.status``, Axis 1). Purely additive columns + an opt-in
preference flag on clients; no data backfill needed beyond the PENDING /
false server defaults.

Revision ID: 0059_client_acceptance_axis
Revises: 0058_entitlements_and_billing
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0059_client_acceptance_axis"
down_revision = "0058_entitlements_and_billing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Axis-2 state on each submission. ``server_default`` so existing rows
    # backfill to PENDING in a single non-blocking metadata update.
    op.add_column(
        "submissions",
        sa.Column(
            "client_acceptance",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "submissions",
        sa.Column("client_decided_by_user_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "submissions",
        sa.Column(
            "client_decided_at", sa.DateTime(timezone=True), nullable=True
        ),
    )
    op.add_column(
        "submissions",
        sa.Column("client_decision_reason", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "fk_submissions_client_decided_by_user",
        "submissions",
        "users",
        ["client_decided_by_user_id"],
        ["id"],
    )
    # Hot path: the client portal lists "pending acceptance" per client; index
    # the (client_id, client_acceptance) predicate the worklist will filter on.
    op.create_index(
        "ix_submissions_client_acceptance",
        "submissions",
        ["client_id", "client_acceptance"],
    )

    # Opt-in auto-accept-on-valid preference (Phase 5 hook; default off).
    op.add_column(
        "clients",
        sa.Column(
            "auto_accept_valid",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("clients", "auto_accept_valid")
    op.drop_index("ix_submissions_client_acceptance", table_name="submissions")
    op.drop_constraint(
        "fk_submissions_client_decided_by_user", "submissions", type_="foreignkey"
    )
    op.drop_column("submissions", "client_decision_reason")
    op.drop_column("submissions", "client_decided_at")
    op.drop_column("submissions", "client_decided_by_user_id")
    op.drop_column("submissions", "client_acceptance")
