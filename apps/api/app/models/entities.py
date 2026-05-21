from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants.statuses import DocumentStatus
from app.db.base import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class Client(TimestampMixin, Base):
    __tablename__ = "clients"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    rfc: Mapped[str | None] = mapped_column(String(13), unique=True)
    responsible_name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)

    vendors: Mapped[list[Vendor]] = relationship(back_populates="client")
    contracts: Mapped[list[Contract]] = relationship(back_populates="client")
    submissions: Mapped[list[Submission]] = relationship(back_populates="client")


_PERSONA_TYPE_CHECK = "persona_type IN ('moral', 'fisica')"


class Vendor(TimestampMixin, Base):
    __tablename__ = "vendors"
    # Bugfix (2026-05-21) — Jay Luna empty-calendar root cause.
    # CheckConstraint mirrors the migration-level CHECK so SQLite
    # test fixtures (which run ``Base.metadata.create_all`` rather
    # than Alembic) reject bad persona_type values consistently with
    # production Postgres. The runtime ``normalize_persona_type``
    # helper is still the read-time safety net for any legacy value
    # that somehow survives the constraint (e.g. on a DB ahead of
    # migration 0013).
    __table_args__ = (
        UniqueConstraint("client_id", "rfc", name="uq_vendors_client_rfc"),
        CheckConstraint(_PERSONA_TYPE_CHECK, name="ck_vendors_persona_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    rfc: Mapped[str] = mapped_column(String(13), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(255))
    contact_email: Mapped[str | None] = mapped_column(String(255))
    repse_id: Mapped[str | None] = mapped_column(String(120))
    persona_type: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)

    client: Mapped[Client] = relationship(back_populates="vendors")
    contracts: Mapped[list[Contract]] = relationship(back_populates="vendor")
    submissions: Mapped[list[Submission]] = relationship(back_populates="vendor")
    workspaces: Mapped[list[ProviderWorkspace]] = relationship(back_populates="vendor")


class Contract(TimestampMixin, Base):
    __tablename__ = "contracts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), nullable=False)
    vendor_id: Mapped[str] = mapped_column(ForeignKey("vendors.id"), nullable=False)
    external_reference: Mapped[str | None] = mapped_column(String(120))
    repse_folio: Mapped[str | None] = mapped_column(String(120))
    service_object: Mapped[str | None] = mapped_column(Text)
    registered_activity: Mapped[str | None] = mapped_column(Text)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    estimated_workers: Mapped[int | None] = mapped_column(Integer)
    work_location: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)

    client: Mapped[Client] = relationship(back_populates="contracts")
    vendor: Mapped[Vendor] = relationship(back_populates="contracts")
    submissions: Mapped[list[Submission]] = relationship(back_populates="contract")


class Period(TimestampMixin, Base):
    __tablename__ = "periods"
    __table_args__ = (UniqueConstraint("code", "period_type", name="uq_periods_code_type"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    # Canonical machine key for the period this row represents. Matches the
    # catalog's ``period_key``: ``YYYY-Mxx`` (monthly), ``YYYY-Bx`` (bimonthly,
    # x ∈ 1..6), ``YYYY-Qx`` (cuatrimestral, x ∈ 1..3), ``YYYY-A`` (annual).
    # Nullable for historic ``period_type`` rows (alta_inicial, contrato,
    # evento) that have no canonical key.
    period_key: Mapped[str | None] = mapped_column(String(20), index=True)
    year: Mapped[int | None] = mapped_column(Integer)
    month: Mapped[int | None] = mapped_column(Integer)
    period_type: Mapped[str] = mapped_column(String(40), nullable=False)
    starts_on: Mapped[date | None] = mapped_column(Date)
    ends_on: Mapped[date | None] = mapped_column(Date)
    due_on: Mapped[date | None] = mapped_column(Date)

    submissions: Mapped[list[Submission]] = relationship(back_populates="period")


class Institution(TimestampMixin, Base):
    __tablename__ = "institutions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    requirements: Mapped[list[Requirement]] = relationship(back_populates="institution")
    submissions: Mapped[list[Submission]] = relationship(back_populates="institution")


class Requirement(TimestampMixin, Base):
    __tablename__ = "requirements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), nullable=False)
    load_type: Mapped[str] = mapped_column(String(40), nullable=False)
    frequency: Mapped[str] = mapped_column(String(60), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(40), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    institution: Mapped[Institution] = relationship(back_populates="requirements")
    versions: Mapped[list[RequirementVersion]] = relationship(back_populates="requirement")
    submissions: Mapped[list[Submission]] = relationship(back_populates="requirement")


class RequirementVersion(TimestampMixin, Base):
    __tablename__ = "requirement_versions"
    __table_args__ = (
        UniqueConstraint(
            "requirement_id", "version", name="uq_requirement_versions_requirement_version"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    requirement_id: Mapped[str] = mapped_column(ForeignKey("requirements.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    legal_basis: Mapped[str | None] = mapped_column(Text)
    applicability_rule: Mapped[str | None] = mapped_column(Text)
    minimum_validation: Mapped[str | None] = mapped_column(Text)
    automatic_signals: Mapped[str | None] = mapped_column(Text)
    human_review_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    missing_state: Mapped[str | None] = mapped_column(String(120))
    temporal_rule: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    implementation_notes: Mapped[str | None] = mapped_column(Text)
    required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)

    requirement: Mapped[Requirement] = relationship(back_populates="versions")
    submissions: Mapped[list[Submission]] = relationship(back_populates="requirement_version")


class Submission(TimestampMixin, Base):
    __tablename__ = "submissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), nullable=False)
    vendor_id: Mapped[str] = mapped_column(ForeignKey("vendors.id"), nullable=False)
    contract_id: Mapped[str | None] = mapped_column(ForeignKey("contracts.id"))
    period_id: Mapped[str] = mapped_column(ForeignKey("periods.id"), nullable=False)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), nullable=False)
    requirement_id: Mapped[str] = mapped_column(ForeignKey("requirements.id"), nullable=False)
    requirement_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("requirement_versions.id")
    )
    load_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source: Mapped[str] = mapped_column(String(60), default="portal", nullable=False)
    status: Mapped[str] = mapped_column(
        String(40), default=DocumentStatus.PENDIENTE_REVISION.value, nullable=False
    )
    # Canonical denormalized keys, populated from the catalog at intake. Kept
    # alongside the requirement_id/requirement_version_id FKs so a submission
    # remains attributable even if requirements are renamed or migrated. Both
    # are nullable to keep historic rows valid; new intake paths must populate
    # them.
    requirement_code: Mapped[str | None] = mapped_column(String(80), index=True)
    period_key: Mapped[str | None] = mapped_column(String(20), index=True)
    comments: Mapped[str | None] = mapped_column(Text)
    submitted_by: Mapped[str | None] = mapped_column(String(255))
    # Replacement lineage (Phase 3). Points to the prior submission this
    # row replaces when a provider re-uploads after a rejection /
    # clarification / mismatch / expiry. ``evidence_slots`` walks the
    # lineage chain to decide which submission is "current" for an
    # obligation slot, so historical attempts can be kept verbatim for
    # the audit trail without dominating the slot view.
    supersedes_submission_id: Mapped[str | None] = mapped_column(
        ForeignKey("submissions.id"), index=True
    )

    client: Mapped[Client] = relationship(back_populates="submissions")
    vendor: Mapped[Vendor] = relationship(back_populates="submissions")
    contract: Mapped[Contract | None] = relationship(back_populates="submissions")
    period: Mapped[Period] = relationship(back_populates="submissions")
    institution: Mapped[Institution] = relationship(back_populates="submissions")
    requirement: Mapped[Requirement] = relationship(back_populates="submissions")
    requirement_version: Mapped[RequirementVersion | None] = relationship(
        back_populates="submissions"
    )
    documents: Mapped[list[Document]] = relationship(back_populates="submission")
    validations: Mapped[list[Validation]] = relationship(back_populates="submission")


class Document(TimestampMixin, Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id"), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(40), default=DocumentStatus.PENDIENTE_REVISION.value, nullable=False
    )
    ocr_status: Mapped[str] = mapped_column(String(40), default="not_started", nullable=False)

    submission: Mapped[Submission] = relationship(back_populates="documents")
    validations: Mapped[list[Validation]] = relationship(back_populates="document")
    status_history: Mapped[list[DocumentStatusHistory]] = relationship(back_populates="document")
    inspection: Mapped[DocumentInspection | None] = relationship(back_populates="document")


class Validation(TimestampMixin, Base):
    __tablename__ = "validations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id"), nullable=False)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id"))
    rule_code: Mapped[str] = mapped_column(String(120), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(60), nullable=False)
    result: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(40), default="info", nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    requires_human_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(255))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    submission: Mapped[Submission] = relationship(back_populates="validations")
    document: Mapped[Document | None] = relationship(back_populates="validations")


class ValidationEvent(Base):
    __tablename__ = "validation_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id"), nullable=False)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id"))
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    rule_code: Mapped[str | None] = mapped_column(String(120))
    result: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(40), default="info", nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    payload: Mapped[dict | None] = mapped_column(JSON)
    actor_type: Mapped[str] = mapped_column(String(60), default="system", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class DocumentInspection(TimestampMixin, Base):
    __tablename__ = "document_inspections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id"), unique=True, nullable=False
    )
    is_pdf: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_corrupt: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_encrypted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer)
    text_char_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    has_text: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_probably_scanned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    detected_institution: Mapped[str | None] = mapped_column(String(80))
    detected_document_type: Mapped[str | None] = mapped_column(String(120))
    detected_rfcs: Mapped[list | None] = mapped_column(JSON)
    detected_dates: Mapped[list | None] = mapped_column(JSON)
    period_mentions: Mapped[list | None] = mapped_column(JSON)
    requirement_match_confidence: Mapped[float | None] = mapped_column(Float)
    mismatch_reason: Mapped[str | None] = mapped_column(Text)
    inspection_error: Mapped[str | None] = mapped_column(Text)
    raw_metadata: Mapped[dict | None] = mapped_column(JSON)

    document: Mapped[Document] = relationship(back_populates="inspection")


class DocumentStatusHistory(Base):
    __tablename__ = "document_status_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), nullable=False)
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id"), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(40))
    to_status: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(255), default="system", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    document: Mapped[Document] = relationship(back_populates="status_history")


class ProviderWorkspace(TimestampMixin, Base):
    """Demo-grade provider session/workspace tying a vendor to a client+contract.

    This model represents the identity of "the provider currently using the
    portal." V1.2 does not implement real auth: an opaque ``access_token`` is
    issued at access time and stored client-side. V1.3 is expected to replace
    this with real authentication and add proper ownership/role checks.
    """

    __tablename__ = "provider_workspaces"
    # Bugfix (2026-05-21) — mirror migration 0013_canonicalize_persona_type
    # at the model layer so SQLite test fixtures get the same
    # constraint enforcement as production Postgres.
    __table_args__ = (
        UniqueConstraint("access_token", name="uq_provider_workspaces_token"),
        CheckConstraint(
            _PERSONA_TYPE_CHECK, name="ck_provider_workspaces_persona_type"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), nullable=False)
    vendor_id: Mapped[str] = mapped_column(ForeignKey("vendors.id"), nullable=False)
    contract_id: Mapped[str | None] = mapped_column(ForeignKey("contracts.id"))
    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    filial_name: Mapped[str | None] = mapped_column(String(255))
    persona_type: Mapped[str] = mapped_column(String(20), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))
    access_token: Mapped[str] = mapped_column(String(64), nullable=False)
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)

    client: Mapped[Client] = relationship()
    vendor: Mapped[Vendor] = relationship(back_populates="workspaces")
    contract: Mapped[Contract | None] = relationship()


class Organization(TimestampMixin, Base):
    """Tenant container introduced by the auth + RBAC patch.

    Orgs come in three kinds. ``internal`` is LegalShelf staff
    (reviewers and admins). ``client`` represents a company whose
    REPSE compliance we track on behalf of, and may be linked back
    to the legacy ``clients`` row to bridge the existing data model.
    ``vendor`` is reserved for the future where providers also get
    accounts; in V1 they still authenticate via ``ProviderWorkspace``
    access tokens.
    """

    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    client_id: Mapped[str | None] = mapped_column(ForeignKey("clients.id"))
    vendor_id: Mapped[str | None] = mapped_column(ForeignKey("vendors.id"))
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)

    memberships: Mapped[list[Membership]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )


class User(TimestampMixin, Base):
    """Real user account. Email + bcrypt password hash + status.

    Independent of ``ProviderWorkspace``: provider portal users still
    authenticate via opaque workspace tokens. ``User`` exists for
    LegalShelf staff (and, later, client / reviewer / vendor staff).
    """

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    memberships: Mapped[list[Membership]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    password_reset_tokens: Mapped[list[PasswordResetToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class PasswordResetToken(TimestampMixin, Base):
    """Single-use password reset token.

    ``token_hash`` stores SHA-256(raw_token), never the raw emailed
    token. ``email`` is denormalized so support/audit can understand
    the request even if the user's email changes later.
    """

    __tablename__ = "password_reset_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    delivery_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )
    delivery_error: Mapped[str | None] = mapped_column(Text)

    user: Mapped[User] = relationship(back_populates="password_reset_tokens")


class Membership(TimestampMixin, Base):
    """Join table between users and orgs, carrying a single role.

    A user with two roles in the same org has two rows. A user with
    access to two orgs has two rows. The role vocabulary starts at
    ``internal_admin``; ``reviewer`` and ``client_admin`` will be
    added by later patches when the surfaces that need them ship.
    """

    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "organization_id", "role", name="uq_memberships_user_org_role"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)

    user: Mapped[User] = relationship(back_populates="memberships")
    organization: Mapped[Organization] = relationship(back_populates="memberships")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[str | None] = mapped_column(String(120))
    actor_type: Mapped[str] = mapped_column(String(60), default="system", nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    before: Mapped[dict | None] = mapped_column(JSON)
    after: Mapped[dict | None] = mapped_column(JSON)
    event_metadata: Mapped[dict | None] = mapped_column("metadata", JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


# ─────────────────────────────────────────────────────────────────
# Phase 3 — Reports
#
# Models for the AI-orchestrated reports workspace. Migration: 0009.
# Full architecture: docs/REPORTS_ARCHITECTURE.md.
# Block catalog:    docs/REPORTS_BLOCK_REGISTRY.md.
# ─────────────────────────────────────────────────────────────────


class Report(TimestampMixin, Base):
    """A report entity. Owned by an organization, optionally scoped to
    a client + vendor pair.

    Audience gates who can see the report; the API layer enforces the
    matching role. The report itself never stores block content —
    that's the responsibility of ``ReportVersion.content_json``.

    See docs/REPORTS_ARCHITECTURE.md §4 for the full schema rationale.
    """

    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), nullable=False
    )
    client_id: Mapped[str | None] = mapped_column(ForeignKey("clients.id"))
    vendor_id: Mapped[str | None] = mapped_column(ForeignKey("vendors.id"))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    audience: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="draft", nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    # Pointer to the latest version. Not a DB-enforced FK because of
    # the cycle between reports and report_versions; the service
    # layer keeps it consistent.
    current_version_id: Mapped[str | None] = mapped_column(String(36))

    versions: Mapped[list[ReportVersion]] = relationship(
        back_populates="report",
        cascade="all, delete-orphan",
        foreign_keys="ReportVersion.report_id",
    )


class ReportVersion(Base):
    """Every persisted snapshot of a report. Block data lives inside
    ``content_json`` as a JSON tree.

    Versions are NOT created on every keystroke. Per spec §9.3:
        - Inline edits patch content_json in place, no new version.
        - AI generate / refinement turns: new version.
        - Manual save: new version with optional label.
        - Auto-version every N=20 edits OR 5 minutes (Phase 3.5).
    """

    __tablename__ = "report_versions"
    __table_args__ = (
        UniqueConstraint(
            "report_id", "version_number", name="uq_report_versions_report_version"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    report_id: Mapped[str] = mapped_column(
        ForeignKey("reports.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("report_versions.id")
    )
    label: Mapped[str | None] = mapped_column(String(120))
    content_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    plan_json: Mapped[dict | None] = mapped_column(JSON)
    generated_by: Mapped[str] = mapped_column(String(40), nullable=False)
    source_snapshot_id: Mapped[str | None] = mapped_column(
        ForeignKey("compliance_snapshots.id")
    )
    llm_metadata: Mapped[dict | None] = mapped_column(JSON)
    created_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    report: Mapped[Report] = relationship(
        back_populates="versions", foreign_keys=[report_id]
    )


class ReportConversation(Base):
    """Chat turns associated with a report's copilot.

    Each turn is one role's content. The full conversation is
    materialized by ordering on (report_id, turn_number). Older turns
    can be dropped from the LLM context but stay visible in the UI.
    """

    __tablename__ = "report_conversations"
    __table_args__ = (
        UniqueConstraint(
            "report_id", "turn_number", name="uq_report_conversations_report_turn"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    report_id: Mapped[str] = mapped_column(
        ForeignKey("reports.id", ondelete="CASCADE"), nullable=False
    )
    turn_number: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    content_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    attached_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("report_versions.id")
    )
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class ComplianceSnapshot(Base):
    """Frozen copy of the data the LLM saw at report-generation time.

    Used by Phase 3.3+. Lets a report be re-rendered identically next
    week (regulatory / audit) and lets the planner cache hit on the
    same data_hash.

    Lives outside ``reports`` because one snapshot can be reused
    across multiple versions or multiple reports (if the same scope +
    period is requested).
    """

    __tablename__ = "compliance_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id"), nullable=False
    )
    client_id: Mapped[str | None] = mapped_column(ForeignKey("clients.id"))
    vendor_id: Mapped[str | None] = mapped_column(ForeignKey("vendors.id"))
    scope_filter: Mapped[dict] = mapped_column(JSON, nullable=False)
    data_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    data_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    taken_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class ReportShare(Base):
    """Signed-link records for external sharing.

    The token itself is never stored. Only the SHA-256 hash. The
    consumer presents the raw token; the API hashes and looks up.
    """

    __tablename__ = "report_shares"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    report_id: Mapped[str] = mapped_column(
        ForeignKey("reports.id", ondelete="CASCADE"), nullable=False
    )
    version_id: Mapped[str] = mapped_column(
        ForeignKey("report_versions.id"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    audience: Mapped[str] = mapped_column(String(40), nullable=False)
    watermark: Mapped[str | None] = mapped_column(String(255))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    access_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ReportExport(Base):
    """Async export artifact (DOCX / PDF / PPTX / HTML).

    State machine: pending → rendering → ready | failed. Phase 3.6
    fills in the rendering worker.
    """

    __tablename__ = "report_exports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    report_id: Mapped[str] = mapped_column(
        ForeignKey("reports.id", ondelete="CASCADE"), nullable=False
    )
    version_id: Mapped[str] = mapped_column(
        ForeignKey("report_versions.id"), nullable=False
    )
    format: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="pending", nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(512))
    error_text: Mapped[str | None] = mapped_column(Text)
    bytes: Mapped[int | None] = mapped_column(Integer)
    requested_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ContactRequest(TimestampMixin, Base):
    """Inbound lead from the public landing-page contact form.

    Replaces the V1.x mock helper at ``apps/web/lib/mock/contact-requests.ts``
    that returned a fake folio without persisting. Persistence is the
    canonical truth; an optional Slack webhook delivery is fired by the
    service layer as a background task and never gates the response.

    Fields stay deliberately small. ``ip_hash`` is a SHA-256 of the
    submitter's client IP salted with ``AUTH_JWT_SECRET`` and truncated
    to 16 hex chars — enough to cluster suspicious activity without
    enabling reverse-IP lookup from a DB dump. ``source`` lets us tell
    landing-page submissions apart from any future embedded form.
    ``status`` starts ``new`` and is moved through ``reviewed``,
    ``contacted``, ``closed`` by the ops team (no admin UI ships in
    this PR — query the table directly until that lands).
    """

    __tablename__ = "contact_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    company: Mapped[str | None] = mapped_column(String(200))
    role: Mapped[str | None] = mapped_column(String(60))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(60), default="landing", nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="new", nullable=False)
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))


class FeedbackReport(TimestampMixin, Base):
    """Bug report or improvement suggestion from the in-app Reportar launcher.

    Persistence is canonical. Slack delivery is a side-effect notifier
    fired by ``feedback_service.deliver_to_slack`` as a BackgroundTask —
    if it fails or stub-mode is active, the row still exists and can be
    re-pushed.

    Two source modes share this table:

    * ``source='authenticated'`` — submitted via ``POST /api/v1/feedback``.
      ``user_id`` / ``user_email`` / ``user_full_name`` / ``user_roles``
      are populated from the JWT.
    * ``source='public'`` — submitted via ``POST /api/v1/feedback/public``
      from the marketing landing. User identity columns are NULL;
      ``contact_email`` (optional, supplier-provided) and ``ip_hash``
      (peppered SHA-256, same algorithm as ``ContactRequest``) carry the
      only attribution we have.

    Status lifecycle: ``new`` → ``triaged`` → ``in_progress`` →
    ``resolved`` (or ``wont_fix``). Admins move rows through this
    workflow from the ``/admin/feedback-reports`` triage queue.

    ``screenshot_storage_key`` points at the PNG persisted via the
    standard ``StorageService`` (S3/R2 in prod, local on dev). Storing
    the bytes ourselves means the screenshot survives Slack channel
    retention/deletion and we can render it inside the admin UI without
    needing Slack scopes on the browser session.

    ``slack_message_ts`` and ``slack_delivery_status`` are written back
    by the BackgroundTask. ``slack_delivery_error`` captures the last
    error string when delivery fails so triagers can see *why* without
    digging through Render logs.
    """

    __tablename__ = "feedback_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    """``bug`` | ``improvement`` — validated at the API boundary."""

    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Source + visibility
    source: Mapped[str] = mapped_column(
        String(20), default="authenticated", nullable=False
    )
    """``authenticated`` | ``public``."""
    is_public: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # Page context (captured by the launcher).
    url: Mapped[str | None] = mapped_column(String(2048))
    path: Mapped[str | None] = mapped_column(String(512))
    viewport: Mapped[str | None] = mapped_column(String(32))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    console_logs: Mapped[str | None] = mapped_column(Text)

    # Authenticated submitter (NULL on public reports).
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    user_email: Mapped[str | None] = mapped_column(String(254))
    user_full_name: Mapped[str | None] = mapped_column(String(200))
    user_roles: Mapped[str | None] = mapped_column(String(500))
    """Comma-separated active roles at submission time (denormalized snapshot)."""

    # Anonymous submitter (NULL on authenticated reports).
    contact_email: Mapped[str | None] = mapped_column(String(254))
    ip_hash: Mapped[str | None] = mapped_column(String(64))

    # Screenshot — bytes live in the storage backend; the row carries
    # the key + metadata. ``screenshot_size_bytes`` is duplicated from
    # the storage layer so list views can render "PNG · 184 KB" without
    # a HEAD call to S3.
    screenshot_storage_key: Mapped[str | None] = mapped_column(String(512))
    screenshot_size_bytes: Mapped[int | None] = mapped_column(Integer)

    # Slack side-effect status (written back by the BackgroundTask).
    slack_message_ts: Mapped[str | None] = mapped_column(String(64))
    slack_delivery_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )
    """``pending`` (queued) | ``sent`` | ``failed`` | ``skipped`` (no token configured)."""
    slack_delivery_error: Mapped[str | None] = mapped_column(Text)

    # Triage workflow.
    status: Mapped[str] = mapped_column(
        String(20), default="new", nullable=False
    )
    """``new`` | ``triaged`` | ``in_progress`` | ``resolved`` | ``wont_fix``."""
    resolution_note: Mapped[str | None] = mapped_column(Text)
    triaged_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    triaged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WiseEvent(Base):
    """Provider-side analytics event for the Wise copilot dock.

    Captures every meaningful dock interaction (mount, expand,
    collapse, suggestion click) so we can answer "did the empty-state
    hero + Wise dock actually move the time-to-first-upload needle?"
    Tiny by design — one row per event, FK-scoped to workspace so
    cross-tenant rollups stay safe.

    Conventions match the rest of the schema: 36-char id, timezone-
    aware timestamps, JSON payload for optional structured context
    (e.g. ``{"suggestion_id": "act-..."}`` for ``wise.suggestion_clicked``).
    """

    __tablename__ = "wise_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("provider_workspaces.id"), nullable=False, index=True
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True, index=True
    )
    # Free-form event identifier — ``wise.first_render``, ``wise.opened``,
    # ``wise.collapsed``, ``wise.suggestion_clicked``, etc. We don't
    # constrain to an enum at the DB layer so the frontend can ship
    # new event types without a schema migration.
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    payload: Mapped[dict | None] = mapped_column(JSON)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )
