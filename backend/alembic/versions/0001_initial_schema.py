"""Initial CheckWise V1 schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-05-12
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clients",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("rfc", sa.String(length=13), nullable=True),
        sa.Column("responsible_name", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("rfc", name="uq_clients_rfc"),
    )

    op.create_table(
        "institutions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("code", name="uq_institutions_code"),
    )

    op.create_table(
        "periods",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("month", sa.Integer(), nullable=True),
        sa.Column("period_type", sa.String(length=40), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=True),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("due_on", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("code", "period_type", name="uq_periods_code_type"),
    )

    op.create_table(
        "vendors",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("client_id", sa.String(length=36), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("rfc", sa.String(length=13), nullable=False),
        sa.Column("contact_name", sa.String(length=255), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("repse_id", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("client_id", "rfc", name="uq_vendors_client_rfc"),
    )

    op.create_table(
        "requirements",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "institution_id", sa.String(length=36), sa.ForeignKey("institutions.id"), nullable=False
        ),
        sa.Column("load_type", sa.String(length=40), nullable=False),
        sa.Column("frequency", sa.String(length=60), nullable=False),
        sa.Column("risk_level", sa.String(length=40), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("code", name="uq_requirements_code"),
    )

    op.create_table(
        "contracts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("client_id", sa.String(length=36), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("vendor_id", sa.String(length=36), sa.ForeignKey("vendors.id"), nullable=False),
        sa.Column("external_reference", sa.String(length=120), nullable=True),
        sa.Column("repse_folio", sa.String(length=120), nullable=True),
        sa.Column("service_object", sa.Text(), nullable=True),
        sa.Column("registered_activity", sa.Text(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("estimated_workers", sa.Integer(), nullable=True),
        sa.Column("work_location", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "requirement_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "requirement_id", sa.String(length=36), sa.ForeignKey("requirements.id"), nullable=False
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("legal_basis", sa.Text(), nullable=True),
        sa.Column("applicability_rule", sa.Text(), nullable=True),
        sa.Column("minimum_validation", sa.Text(), nullable=True),
        sa.Column("automatic_signals", sa.Text(), nullable=True),
        sa.Column(
            "human_review_required", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("missing_state", sa.String(length=120), nullable=True),
        sa.Column("temporal_rule", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("implementation_notes", sa.Text(), nullable=True),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "requirement_id", "version", name="uq_requirement_versions_requirement_version"
        ),
    )

    op.create_table(
        "submissions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("client_id", sa.String(length=36), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("vendor_id", sa.String(length=36), sa.ForeignKey("vendors.id"), nullable=False),
        sa.Column(
            "contract_id", sa.String(length=36), sa.ForeignKey("contracts.id"), nullable=True
        ),
        sa.Column("period_id", sa.String(length=36), sa.ForeignKey("periods.id"), nullable=False),
        sa.Column(
            "institution_id", sa.String(length=36), sa.ForeignKey("institutions.id"), nullable=False
        ),
        sa.Column(
            "requirement_id", sa.String(length=36), sa.ForeignKey("requirements.id"), nullable=False
        ),
        sa.Column(
            "requirement_version_id",
            sa.String(length=36),
            sa.ForeignKey("requirement_versions.id"),
            nullable=True,
        ),
        sa.Column("load_type", sa.String(length=40), nullable=False),
        sa.Column("source", sa.String(length=60), nullable=False, server_default="portal"),
        sa.Column(
            "status", sa.String(length=40), nullable=False, server_default="pendiente_revision"
        ),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column("submitted_by", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "submission_id", sa.String(length=36), sa.ForeignKey("submissions.id"), nullable=False
        ),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "status", sa.String(length=40), nullable=False, server_default="pendiente_revision"
        ),
        sa.Column("ocr_status", sa.String(length=40), nullable=False, server_default="not_started"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_documents_sha256", "documents", ["sha256"])

    op.create_table(
        "validations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "submission_id", sa.String(length=36), sa.ForeignKey("submissions.id"), nullable=False
        ),
        sa.Column(
            "document_id", sa.String(length=36), sa.ForeignKey("documents.id"), nullable=True
        ),
        sa.Column("rule_code", sa.String(length=120), nullable=False),
        sa.Column("rule_type", sa.String(length=60), nullable=False),
        sa.Column("result", sa.String(length=40), nullable=False),
        sa.Column("severity", sa.String(length=40), nullable=False, server_default="info"),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "requires_human_review", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("reviewed_by", sa.String(length=255), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "document_status_history",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "document_id", sa.String(length=36), sa.ForeignKey("documents.id"), nullable=False
        ),
        sa.Column(
            "submission_id", sa.String(length=36), sa.ForeignKey("submissions.id"), nullable=False
        ),
        sa.Column("from_status", sa.String(length=40), nullable=True),
        sa.Column("to_status", sa.String(length=40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("actor", sa.String(length=255), nullable=False, server_default="system"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "reports",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("client_id", sa.String(length=36), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("period_id", sa.String(length=36), sa.ForeignKey("periods.id"), nullable=False),
        sa.Column("report_type", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="draft"),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("file_url", sa.String(length=500), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("actor_id", sa.String(length=120), nullable=True),
        sa.Column("actor_type", sa.String(length=60), nullable=False, server_default="system"),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("entity_type", sa.String(length=120), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("reports")
    op.drop_table("document_status_history")
    op.drop_table("validations")
    op.drop_index("ix_documents_sha256", table_name="documents")
    op.drop_table("documents")
    op.drop_table("submissions")
    op.drop_table("requirement_versions")
    op.drop_table("contracts")
    op.drop_table("requirements")
    op.drop_table("vendors")
    op.drop_table("periods")
    op.drop_table("institutions")
    op.drop_table("clients")
