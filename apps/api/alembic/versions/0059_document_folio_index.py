"""Add document_folios — indexed projection of folio / fiscal-UUID anchors.

Revision ID: 0059_document_folio_index
Revises: 0055_perf_indexes_trgm_search_and_renewals
Create Date: 2026-06-23

The Phase-B verification extractor already pulls each document's folio anchors
(CFDI fiscal UUID, SAT/IMSS opinion folios) but only stores them inside the
``DocumentInspection.verification["folios"]`` JSON blob, where they are
write-only — never queryable. This table promotes them into an indexed
``document_folios`` table so folio-keyed lookups (cross-tenant recycled-document
detection, cross-period reuse, a live-SAT verification cache) become single
indexed reads instead of full JSON scans. The rows are populated at intake and
by ``scripts/backfill_document_folios.py``; the consumers are later phases —
this migration only lays the keystone.

``value`` is deliberately NOT globally unique (the same value recurring across
documents/tenants IS the downstream signal). Uniqueness is per
(document_id, kind, value) so intake + backfill are idempotent. ``client_id`` /
``vendor_id`` / ``period_id`` are denormalized from the document's submission so
the future scans don't re-join through submissions.

Plain CREATE TABLE — no data migration, trivially reversible (DROP TABLE). The
inline foreign keys take a brief lock on the referenced tables (documents /
clients / vendors / periods) only for the duration of the CREATE on this empty
table; there is no ACCESS EXCLUSIVE on any populated table and no constraint
validation pass. Auto-runs via the Render preDeployCommand; snapshot Neon before
deploying per the standing convention. The SQLite test fixtures build this table
from the ``DocumentFolio`` model via ``create_all`` and never run this migration.

NUMBERING (parallel-branch coordination): this revision chains off ``0055`` —
the migration head of this branch's base (e36577b). It is numbered ``0059`` to
sit clear of the concurrent ``0056_rename_rbac_roles`` (role-model branch) and
the ``0057`` / ``0058`` reserved by the provider-limits PR #32; the revision IDs
are full descriptive strings so they cannot duplicate-collide regardless. If any
of those land on the base before this branch, re-point ``down_revision`` to the
then-current head (``alembic`` will flag multiple heads loudly) before merging.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0059_document_folio_index"
down_revision = "0055_perf_indexes_trgm_search_and_renewals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_folios",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(length=36),
            sa.ForeignKey("documents.id"),
            nullable=False,
        ),
        sa.Column(
            "client_id",
            sa.String(length=36),
            sa.ForeignKey("clients.id"),
            nullable=False,
        ),
        sa.Column(
            "vendor_id",
            sa.String(length=36),
            sa.ForeignKey("vendors.id"),
            nullable=False,
        ),
        sa.Column(
            "period_id",
            sa.String(length=36),
            sa.ForeignKey("periods.id"),
            nullable=True,
        ),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("value", sa.String(length=120), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "document_id",
            "kind",
            "value",
            name="uq_document_folios_doc_kind_value",
        ),
    )
    op.create_index(
        "ix_document_folios_kind_value",
        "document_folios",
        ["kind", "value"],
    )
    op.create_index(
        "ix_document_folios_vendor",
        "document_folios",
        ["vendor_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_folios_vendor", table_name="document_folios")
    op.drop_index("ix_document_folios_kind_value", table_name="document_folios")
    op.drop_table("document_folios")
