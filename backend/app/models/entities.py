from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
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
    reports: Mapped[list[Report]] = relationship(back_populates="client")


class Vendor(TimestampMixin, Base):
    __tablename__ = "vendors"
    __table_args__ = (UniqueConstraint("client_id", "rfc", name="uq_vendors_client_rfc"),)

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
    reports: Mapped[list[Report]] = relationship(back_populates="period")


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
    status: Mapped[str] = mapped_column(String(40), default="pendiente_revision", nullable=False)
    # Canonical denormalized keys, populated from the catalog at intake. Kept
    # alongside the requirement_id/requirement_version_id FKs so a submission
    # remains attributable even if requirements are renamed or migrated. Both
    # are nullable to keep historic rows valid; new intake paths must populate
    # them.
    requirement_code: Mapped[str | None] = mapped_column(String(80), index=True)
    period_key: Mapped[str | None] = mapped_column(String(20), index=True)
    comments: Mapped[str | None] = mapped_column(Text)
    submitted_by: Mapped[str | None] = mapped_column(String(255))

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
    status: Mapped[str] = mapped_column(String(40), default="pendiente_revision", nullable=False)
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


class Report(TimestampMixin, Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), nullable=False)
    period_id: Mapped[str] = mapped_column(ForeignKey("periods.id"), nullable=False)
    report_type: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="draft", nullable=False)
    score: Mapped[float | None] = mapped_column(Float)
    file_url: Mapped[str | None] = mapped_column(String(500))
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    client: Mapped[Client] = relationship(back_populates="reports")
    period: Mapped[Period] = relationship(back_populates="reports")


class ProviderWorkspace(TimestampMixin, Base):
    """Demo-grade provider session/workspace tying a vendor to a client+contract.

    This model represents the identity of "the provider currently using the
    portal." V1.2 does not implement real auth: an opaque ``access_token`` is
    issued at access time and stored client-side. V1.3 is expected to replace
    this with real authentication and add proper ownership/role checks.
    """

    __tablename__ = "provider_workspaces"
    __table_args__ = (UniqueConstraint("access_token", name="uq_provider_workspaces_token"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), nullable=False)
    vendor_id: Mapped[str] = mapped_column(ForeignKey("vendors.id"), nullable=False)
    contract_id: Mapped[str | None] = mapped_column(ForeignKey("contracts.id"))
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
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    memberships: Mapped[list[Membership]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


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
