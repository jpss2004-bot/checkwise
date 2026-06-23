"""Add intake_queue — durable intake-finalize job queue (B2).

Revision ID: 0061_intake_queue
Revises: 0055_perf_indexes_trgm_search_and_renewals
Create Date: 2026-06-23

The async-intake endpoint schedules the heavy back-half (PDF inspection,
forensics, QR, status derivation, metadata export, shadow analysis) as an
in-process FastAPI BackgroundTask, which is lost if the dyno restarts mid-flight
(the reconcile cron is the only backstop). Behind ``INTAKE_QUEUE_CONSUMER_ENABLED``
the endpoint instead enqueues one row here (committed with the receipt) and a
separate worker consuming the queue runs the already-idempotent
``finalize_intake_submission_background`` — so the work survives a restart and
moves off the web tier.

Plain CREATE TABLE — no data migration, trivially reversible (DROP TABLE). The
``submission_id`` FK takes a brief lock on ``submissions`` only for the CREATE on
this empty table. The SQLite test fixtures build this table from the
``IntakeQueueJob`` model via ``create_all`` and never run this migration.

NUMBERING (parallel-branch coordination): chains off ``0055`` — the head of this
branch's base (e36577b / the ai-cost-efficiency lineage). Numbered ``0061`` to
sit clear of the concurrent ``0056_rename_rbac_roles`` (role-model), ``0057`` /
``0058`` (provider-limits PR #32), and the folio stack's ``0059`` / ``0060``.
Revision IDs are full descriptive strings so they cannot duplicate-collide. If
any of those land on the base first, re-point ``down_revision`` to the
then-current head (``alembic`` flags multiple heads loudly) before merging.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0061_intake_queue"
down_revision = "0055_perf_indexes_trgm_search_and_renewals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "intake_queue",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "submission_id",
            sa.String(length=36),
            sa.ForeignKey("submissions.id"),
            nullable=False,
        ),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("intake_source", sa.String(length=40), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="pending"
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_by", sa.String(length=80), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("submission_id", name="uq_intake_queue_submission"),
    )
    op.create_index(
        "ix_intake_queue_claim",
        "intake_queue",
        ["status", "available_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_intake_queue_claim", table_name="intake_queue")
    op.drop_table("intake_queue")
