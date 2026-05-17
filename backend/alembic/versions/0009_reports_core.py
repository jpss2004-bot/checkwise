"""Reports core — 6 tables for the AI-orchestrated reports workspace.

Revision ID: 0009_reports_core
Revises: 0008_submission_supersedes
Create Date: 2026-05-17

Lays down the entire Phase 3 storage spine in one migration:

* ``reports`` — the entity. Owned by an organization. Optionally scoped
  to a client + vendor pair. Audience enum gates who can see what.
* ``report_versions`` — every persisted snapshot of the report content
  tree, plus the LLM plan that produced it. Block data lives inside
  ``content_json``, not in per-block rows.
* ``report_conversations`` — chat turns with the copilot, bound to a
  report. Used by Phase 3.4 (copilot).
* ``compliance_snapshots`` — the canonical data the LLM saw at
  generation time, decoupled from live state so reports are
  reproducible and auditable. Used by Phase 3.3+.
* ``report_shares`` — signed-link records. Used by Phase 3.7.
* ``report_exports`` — async export artifacts (DOCX / PDF / PPTX).
  Used by Phase 3.6.

All tables introduced together so we don't have to evolve the schema
across the rest of the Phase 3 sub-phases. Endpoints land
sub-phase-by-sub-phase; the tables sit empty until each one needs them.

Architectural commitments (see docs/REPORTS_ARCHITECTURE.md §3):
- AI-generated text is storage-separated from canonical data
  (``report_versions.llm_metadata`` + ``report_versions.source_snapshot_id``).
- Tenant trust boundary is ``organization_id``. Every read path joins
  through it server-side.
- Audience is a per-report property, enforced at the API layer.

Conventions matched to the existing codebase:
- ``String(36)`` for ids (matches all other tables; no native UUID).
- ``sa.JSON()`` for jsonb-shaped columns (cross-dialect with sqlite tests).
- ``DateTime(timezone=True)`` for timestamps.
- ``TimestampMixin`` semantics replicated in the table definitions.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0009_reports_core"
down_revision = "0008_submission_supersedes"
branch_labels = None
depends_on = None


REPORT_AUDIENCES = ("internal_only", "client_facing", "vendor_facing", "external_signed")
REPORT_STATUSES = ("draft", "active", "archived")
VERSION_GENERATED_BY = ("user", "ai", "ai_refined")
CONVERSATION_ROLES = ("user", "assistant", "system", "tool")
SHARE_AUDIENCES = REPORT_AUDIENCES
EXPORT_FORMATS = ("pdf", "docx", "pptx", "html")
EXPORT_STATUSES = ("pending", "rendering", "ready", "failed")


def upgrade() -> None:
    # ──────────────────────────────────────────────────────────────
    # 0. Retire the legacy ``reports`` table.
    #
    # Migration 0001 created a stub ``reports`` table that was never
    # used (no inserts, no service, no API). Phase 3 reclaims the name
    # for the AI-orchestrated reports workspace. The legacy table had
    # zero callers (verified by grep) and no rows in any environment
    # CheckWise has shipped, so dropping it here is the cleanup pass
    # the codebase has been waiting for.
    # ──────────────────────────────────────────────────────────────
    op.drop_table("reports")

    # ──────────────────────────────────────────────────────────────
    # 1. reports — the new entity
    # ──────────────────────────────────────────────────────────────
    op.create_table(
        "reports",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("client_id", sa.String(length=36), sa.ForeignKey("clients.id")),
        sa.Column("vendor_id", sa.String(length=36), sa.ForeignKey("vendors.id")),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("audience", sa.String(length=40), nullable=False),
        sa.Column(
            "status", sa.String(length=40), nullable=False, server_default="draft"
        ),
        sa.Column(
            "created_by_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        # current_version_id is intentionally NOT a FK at the DB level
        # to avoid the FK cycle between reports and report_versions.
        # The service layer keeps it consistent.
        sa.Column("current_version_id", sa.String(length=36)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        # If the audience requires a scope, at least one of client_id or
        # vendor_id must be present.
        sa.CheckConstraint(
            "audience = 'internal_only' OR client_id IS NOT NULL OR vendor_id IS NOT NULL",
            name="ck_reports_scope_required",
        ),
        sa.CheckConstraint(
            "audience IN ('internal_only','client_facing','vendor_facing','external_signed')",
            name="ck_reports_audience_enum",
        ),
        sa.CheckConstraint(
            "status IN ('draft','active','archived')",
            name="ck_reports_status_enum",
        ),
    )
    op.create_index("ix_reports_organization_id", "reports", ["organization_id"])
    op.create_index("ix_reports_client_id", "reports", ["client_id"])
    op.create_index("ix_reports_vendor_id", "reports", ["vendor_id"])
    op.create_index("ix_reports_status", "reports", ["status"])
    op.create_index("ix_reports_audience", "reports", ["audience"])

    # ──────────────────────────────────────────────────────────────
    # 2. compliance_snapshots — created before report_versions because
    #    report_versions.source_snapshot_id references it.
    # ──────────────────────────────────────────────────────────────
    op.create_table(
        "compliance_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(length=36),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("client_id", sa.String(length=36), sa.ForeignKey("clients.id")),
        sa.Column("vendor_id", sa.String(length=36), sa.ForeignKey("vendors.id")),
        sa.Column("scope_filter", sa.JSON(), nullable=False),
        sa.Column("data_json", sa.JSON(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("data_hash", sa.String(length=64), nullable=False),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_compliance_snapshots_org_taken",
        "compliance_snapshots",
        ["organization_id", "taken_at"],
    )
    op.create_index(
        "ix_compliance_snapshots_hash", "compliance_snapshots", ["data_hash"]
    )

    # ──────────────────────────────────────────────────────────────
    # 3. report_versions — every persisted snapshot
    # ──────────────────────────────────────────────────────────────
    op.create_table(
        "report_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "report_id",
            sa.String(length=36),
            sa.ForeignKey("reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column(
            "parent_version_id",
            sa.String(length=36),
            sa.ForeignKey("report_versions.id"),
        ),
        sa.Column("label", sa.String(length=120)),
        # The canvas tree — block array + global metadata.
        sa.Column("content_json", sa.JSON(), nullable=False),
        # The LLM plan that produced this version (null for manual edits).
        sa.Column("plan_json", sa.JSON()),
        # 'user' | 'ai' | 'ai_refined'
        sa.Column("generated_by", sa.String(length=40), nullable=False),
        sa.Column(
            "source_snapshot_id",
            sa.String(length=36),
            sa.ForeignKey("compliance_snapshots.id"),
        ),
        # {model, prompt_hash, token_usage, cost_usd, latency_ms}
        sa.Column("llm_metadata", sa.JSON()),
        sa.Column(
            "created_by_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "report_id", "version_number", name="uq_report_versions_report_version"
        ),
        sa.CheckConstraint(
            "generated_by IN ('user','ai','ai_refined')",
            name="ck_report_versions_generated_by",
        ),
    )
    op.create_index(
        "ix_report_versions_report_version",
        "report_versions",
        ["report_id", "version_number"],
    )

    # ──────────────────────────────────────────────────────────────
    # 4. report_conversations — copilot chat turns
    # ──────────────────────────────────────────────────────────────
    op.create_table(
        "report_conversations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "report_id",
            sa.String(length=36),
            sa.ForeignKey("reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        # 'user' | 'assistant' | 'system' | 'tool'
        sa.Column("role", sa.String(length=40), nullable=False),
        # {text, plan_card?, patch_card?, tool_calls?, tool_results?}
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column(
            "attached_version_id",
            sa.String(length=36),
            sa.ForeignKey("report_versions.id"),
        ),
        sa.Column(
            "created_by_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "report_id", "turn_number", name="uq_report_conversations_report_turn"
        ),
        sa.CheckConstraint(
            "role IN ('user','assistant','system','tool')",
            name="ck_report_conversations_role",
        ),
    )
    op.create_index(
        "ix_report_conversations_report",
        "report_conversations",
        ["report_id", "turn_number"],
    )

    # ──────────────────────────────────────────────────────────────
    # 5. report_shares — signed-link records
    # ──────────────────────────────────────────────────────────────
    op.create_table(
        "report_shares",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "report_id",
            sa.String(length=36),
            sa.ForeignKey("reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "version_id",
            sa.String(length=36),
            sa.ForeignKey("report_versions.id"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("audience", sa.String(length=40), nullable=False),
        sa.Column("watermark", sa.String(length=255)),
        sa.Column("password_hash", sa.String(length=255)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_by_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True)),
        sa.Column("access_count", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint(
            "audience IN ('internal_only','client_facing','vendor_facing','external_signed')",
            name="ck_report_shares_audience",
        ),
    )
    op.create_index("ix_report_shares_report", "report_shares", ["report_id"])

    # ──────────────────────────────────────────────────────────────
    # 6. report_exports — async export artifacts
    # ──────────────────────────────────────────────────────────────
    op.create_table(
        "report_exports",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "report_id",
            sa.String(length=36),
            sa.ForeignKey("reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "version_id",
            sa.String(length=36),
            sa.ForeignKey("report_versions.id"),
            nullable=False,
        ),
        sa.Column("format", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
        sa.Column("storage_key", sa.String(length=512)),
        sa.Column("error_text", sa.Text()),
        sa.Column("bytes", sa.Integer()),
        sa.Column(
            "requested_by_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ready_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "format IN ('pdf','docx','pptx','html')",
            name="ck_report_exports_format",
        ),
        sa.CheckConstraint(
            "status IN ('pending','rendering','ready','failed')",
            name="ck_report_exports_status",
        ),
    )
    op.create_index("ix_report_exports_report", "report_exports", ["report_id"])
    op.create_index(
        "ix_report_exports_status_format",
        "report_exports",
        ["status", "format"],
    )


def downgrade() -> None:
    op.drop_index("ix_report_exports_status_format", table_name="report_exports")
    op.drop_index("ix_report_exports_report", table_name="report_exports")
    op.drop_table("report_exports")

    op.drop_index("ix_report_shares_report", table_name="report_shares")
    op.drop_table("report_shares")

    op.drop_index(
        "ix_compliance_snapshots_hash", table_name="compliance_snapshots"
    )
    op.drop_index(
        "ix_compliance_snapshots_org_taken", table_name="compliance_snapshots"
    )
    op.drop_table("compliance_snapshots")

    op.drop_index("ix_report_conversations_report", table_name="report_conversations")
    op.drop_table("report_conversations")

    op.drop_index("ix_report_versions_report_version", table_name="report_versions")
    op.drop_table("report_versions")

    op.drop_index("ix_reports_audience", table_name="reports")
    op.drop_index("ix_reports_status", table_name="reports")
    op.drop_index("ix_reports_vendor_id", table_name="reports")
    op.drop_index("ix_reports_client_id", table_name="reports")
    op.drop_index("ix_reports_organization_id", table_name="reports")
    op.drop_table("reports")
