"""Add folio_verifications — cache of live SAT CFDI consulta verdicts (B1).

Revision ID: 0060_folio_verifications
Revises: 0059_document_folio_index
Create Date: 2026-06-23

The B1 "live SAT folio verification" moat caches, per
``(cfdi_uuid, emisor_rfc, receptor_rfc)``, the verdict SAT returns for a CFDI
fiscal UUID (``vigente`` | ``cancelado`` | ``no_existe`` | ``not_verifiable``).
A reviewer-triggered worker (``services.folio_verification``) populates it;
intake never touches it. Keying on the triple (not the UUID alone) mirrors the
SAT consulta, which depends on all three. ``not_verifiable`` (stub mode /
transport error / missing inputs) is cached too so a doomed query is not
retried on every reviewer click, but it never elevates a verdict.

Plain CREATE TABLE — no data migration, trivially reversible (DROP TABLE). The
``last_document_id`` FK takes a brief lock on ``documents`` only for the CREATE
on this empty table; no populated table is touched. The SQLite test fixtures
build this table from the ``FolioVerification`` model via ``create_all`` and
never run this migration.

NUMBERING (parallel-branch coordination): chains off ``0059`` (the head of this
branch's folio stack). Numbered ``0060`` to sit clear of the concurrent
``0056_rename_rbac_roles`` (role-model) and ``0057``/``0058`` (provider-limits
PR #32). Revision IDs are full descriptive strings so they cannot
duplicate-collide regardless. If the folio stack is renumbered at merge,
re-point ``down_revision`` to the then-current head (``alembic`` flags multiple
heads loudly) before merging.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0060_folio_verifications"
down_revision = "0059_document_folio_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "folio_verifications",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("cfdi_uuid", sa.String(length=120), nullable=False),
        sa.Column(
            "emisor_rfc", sa.String(length=13), nullable=False, server_default=""
        ),
        sa.Column(
            "receptor_rfc", sa.String(length=13), nullable=False, server_default=""
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.Column(
            "last_document_id",
            sa.String(length=36),
            sa.ForeignKey("documents.id"),
            nullable=True,
        ),
        sa.Column(
            "checked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "cfdi_uuid",
            "emisor_rfc",
            "receptor_rfc",
            name="uq_folio_verifications_key",
        ),
    )
    # No separate index: the unique constraint's implicit index already serves
    # the cache's 3-column equality lookup.


def downgrade() -> None:
    op.drop_table("folio_verifications")
