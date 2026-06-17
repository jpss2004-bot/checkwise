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
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
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
    # Junta 2026-05-23 — RFC + email + nombre son los tres datos
    # mínimos al dar de alta un cliente. Nullable a nivel de DB para
    # que las filas legacy sin email sigan válidas; la API y el
    # formulario admin lo exigen para nuevos registros.
    email: Mapped[str | None] = mapped_column(String(254))
    responsible_name: Mapped[str | None] = mapped_column(String(255))
    # Junta 2026-05-23 — el cliente_admin completa estos campos en
    # /client/onboarding después de que el admin hace el preload con
    # RFC/email/nombre. ``onboarding_completed_at`` se setea en el
    # primer guardado para apagar el banner de "termina tu alta" en
    # el dashboard.
    industry: Mapped[str | None] = mapped_column(String(120))
    fiscal_address: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(30))
    notes: Mapped[str | None] = mapped_column(Text)
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)

    vendors: Mapped[list[Vendor]] = relationship(back_populates="client")
    contracts: Mapped[list[Contract]] = relationship(back_populates="client")
    submissions: Mapped[list[Submission]] = relationship(back_populates="client")
    notifications: Mapped[list[ClientNotification]] = relationship(back_populates="client")


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
    # Vendor-level contact phone. Added in migration 0017 so the
    # admin correction-request approval flow can auto-apply a
    # provider's contact_phone change to the canonical row instead
    # of leaving the admin to copy-paste from Slack.
    contact_phone: Mapped[str | None] = mapped_column(String(30))
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

    # Hot-path indexes for the evidence-slot engine and the client
    # portfolio views. Postgres does NOT auto-index foreign keys, so
    # without these every slot build (``WHERE client_id=? AND
    # vendor_id=?``) and every status/period filter full-scans the
    # whole submissions table. See migration 0034.
    __table_args__ = (
        Index("ix_submissions_client_vendor", "client_id", "vendor_id"),
        Index("ix_submissions_client_status", "client_id", "status"),
        Index("ix_submissions_period_id", "period_id"),
        Index("ix_submissions_requirement_id", "requirement_id"),
        # PERF-7 (audit 2026-06-15, migration 0046). vendor-only predicate
        # (the (client_id, vendor_id) composite can't serve it) + the
        # client-scoped ORDER BY created_at DESC lists / history ranges.
        Index("ix_submissions_vendor_id", "vendor_id"),
        Index("ix_submissions_client_created", "client_id", "created_at"),
    )
    # NOTE: a unique partial index ``ux_submissions_active_slot`` enforces
    # "one active-genesis submission per evidence slot" in Postgres — see
    # migration 0035. It is intentionally NOT declared here: the test
    # schema (``create_all`` on SQLite) seeds parallel-genesis rows to
    # exercise the read engine's defensive recency-tiebreak for legacy /
    # codeless data, which the constraint exempts. The invariant the
    # constraint protects is upheld by the auto-supersede write path
    # (``portal._resolve_supersedes_submission``), which IS covered by
    # endpoint tests.

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

    # ``submission_id`` is the most common join in the app (documents per
    # submission); ``status`` backs status-filtered queues. Neither was
    # indexed before migration 0034.
    __table_args__ = (
        Index("ix_documents_submission_id", "submission_id"),
        Index("ix_documents_status", "status"),
    )

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
    expected_rfc: Mapped[str | None] = mapped_column(String(13))
    rfc_alignment: Mapped[str | None] = mapped_column(String(40))
    detected_dates: Mapped[list | None] = mapped_column(JSON)
    period_mentions: Mapped[list | None] = mapped_column(JSON)
    requirement_match_confidence: Mapped[float | None] = mapped_column(Float)
    mismatch_reason: Mapped[str | None] = mapped_column(Text)
    inspection_error: Mapped[str | None] = mapped_column(Text)
    raw_metadata: Mapped[dict | None] = mapped_column(JSON)

    # Phase 2 — shadow-mode AI analysis. Populated by the
    # ``document_analysis.shadow_runner`` BackgroundTask after the
    # intake transaction commits. ``shadow_completed_at IS NULL``
    # means "no run yet"; non-null with ``shadow_error IS NOT NULL``
    # means "run finished but did not produce signals". The
    # heuristic-driven columns above remain the source of truth for
    # user-visible status throughout shadow mode.
    shadow_provider_id: Mapped[str | None] = mapped_column(String(120))
    shadow_prompt_version: Mapped[str | None] = mapped_column(String(60))
    shadow_signals: Mapped[dict | None] = mapped_column(JSON)
    shadow_confidence: Mapped[float | None] = mapped_column(Float)
    shadow_latency_ms: Mapped[int | None] = mapped_column(Integer)
    shadow_error: Mapped[str | None] = mapped_column(Text)
    shadow_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Phase A — document-revalidation authenticity verdict, produced by
    # ``document_forensics.analyze_pdf_forensics`` at intake. Reviewer-
    # facing only: it never alters statuses or prevalidation signals.
    # ``authenticity_risk`` is "clean" | "suspicious" | "high_risk";
    # NULL means *not analyzed* (legacy rows, or the analyzer failed —
    # intake fails open). ``risk_reasons`` is a list of
    # ``{"code", "severity", "detail_es"}`` sorted high→info;
    # ``forensics`` keeps the raw findings dict (producer, dates,
    # %%EOF count, JavaScript flags, …) as evidence.
    authenticity_risk: Mapped[str | None] = mapped_column(String(20))
    risk_reasons: Mapped[list | None] = mapped_column(JSON)
    forensics: Mapped[dict | None] = mapped_column(JSON)

    # Phase B — QR/folio verification anchors, produced by
    # ``document_verification.extract_verification`` at intake. Shape:
    # ``{"qr_codes": [...], "folios": [...], "pages_scanned": int,
    # "images_scanned": int, "error": str|None}``. NULL means *not
    # analyzed* (legacy rows, or intake failed open before the
    # extractor ran). Verification risk reasons are MERGED into
    # ``risk_reasons`` above and folded into the ``authenticity_risk``
    # rollup — this column only keeps the extracted anchors/evidence.
    verification: Mapped[dict | None] = mapped_column(JSON)

    document: Mapped[Document] = relationship(back_populates="inspection")


class DocumentStatusHistory(Base):
    __tablename__ = "document_status_history"

    # Audit-trail lookups are by document (chronological) or submission.
    __table_args__ = (
        Index("ix_doc_status_history_document", "document_id", "created_at"),
        Index("ix_doc_status_history_submission", "submission_id"),
    )

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
        # PERF (2026-06-17, migration 0048) — vendor-only lookups
        # (resolve_workspace_for_vendor, on nearly every compliance path)
        # cannot use the (client_id, vendor_id) composite below.
        Index("ix_provider_workspaces_vendor_id", "vendor_id"),
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
    # Set by PATCH /portal/me/profile the first time the provider
    # confirms their profile on /portal/entra-a-tu-espacio. The
    # frontend uses presence/absence to branch between the first-visit
    # confirmation gate copy and the returning-user settings view.
    profile_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    # Phase 1 / Slice 1A — legal consent gate. The provider cannot
    # finish ``/portal/entra-a-tu-espacio`` until they accept the three
    # legal notices (privacidad, términos, consentimiento). The version
    # string pins the accepted document set so a future legal-approved
    # version can supersede this one cleanly.
    legal_consent_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    legal_consent_version: Mapped[str | None] = mapped_column(String(120))
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
    # Multi-user (2026-06-10) — maximum active memberships this org may
    # hold. 3 for ``kind='client'`` (1 primary owner + 2 secondaries);
    # NULL means "no cap" (internal staff org). The cap is data so a
    # future subscription tier can lift it per-org without a deploy.
    # The service-layer check treats NULL on a *client* org as the
    # default 3 defensively.
    seat_limit: Mapped[int | None] = mapped_column(Integer)
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
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        # Mirrors the migration-level CHECK so SQLite test fixtures
        # (which run create_all rather than Alembic) reject bad
        # contact_preference values consistently with prod Postgres.
        CheckConstraint(
            "contact_preference IN ('email', 'whatsapp', 'both')",
            name="ck_users_contact_preference",
        ),
        # Partial index over live rows: the default directory query
        # (migration 0042) is ``WHERE deleted_at IS NULL ORDER BY
        # created_at DESC``. Indexing only live rows keeps it small and
        # excludes the growing soft-deleted tail. ``sqlite_where`` twin
        # so create_all test fixtures build an equivalent index.
        Index(
            "ix_users_active_created",
            "created_at",
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Account lockout (migration 0045). ``failed_login_count`` counts
    # CONSECUTIVE failed logins; once it hits the configured threshold the
    # account is locked until ``locked_until`` and the counter resets. A
    # successful login or any password change clears both.
    failed_login_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Editable profile fields surfaced on /portal/entra-a-tu-espacio.
    # Phone and job_title are optional; contact_preference defaults to
    # email so existing rows stay valid after migration 0016 backfills
    # via the server_default.
    phone: Mapped[str | None] = mapped_column(String(30))
    job_title: Mapped[str | None] = mapped_column(String(120))
    contact_preference: Mapped[str] = mapped_column(
        String(20), default="email", nullable=False
    )
    # Phase 7 / Slice N2 — WhatsApp identity. ``phone_e164`` is the
    # normalized form the dispatcher uses; ``phone_verified_at`` and
    # ``whatsapp_opt_in_at`` gate WhatsApp delivery in
    # :mod:`app.services.notifications.routing`. All nullable until
    # the alta OTP flow (Slice N8) populates them.
    phone_e164: Mapped[str | None] = mapped_column(String(20))
    phone_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    whatsapp_opt_in_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    # Client-side legal consent (v2+). Mirrors the provider gate, but
    # stored per-user because a client_admin accepts the legal package
    # once per version regardless of how many client orgs they manage.
    # Providers keep their own per-workspace columns on ProviderWorkspace;
    # these are read only by the client gate (``app.api.v1.client``).
    legal_consent_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    legal_consent_version: Mapped[str | None] = mapped_column(String(120))
    # Soft-delete (migration 0042, platform rework Phase 0 2026-06-13).
    # A soft-deleted account is hidden from the /platform/users directory
    # and blocked from login (``get_current_user`` already rejects any
    # status != 'active'), but the row is retained so an accidental delete
    # is recoverable for a window before a purge cron hard-deletes it.
    # ``deleted_by_user_id`` is the internal operator who performed the
    # delete — a plain id, NOT an FK, so the actor can themselves be
    # deleted later without orphaning the reference (mirrors
    # ``AuditLog.actor_id``). ``deletion_reason`` is their optional note.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by_user_id: Mapped[str | None] = mapped_column(String(36))
    deletion_reason: Mapped[str | None] = mapped_column(String(200))

    memberships: Mapped[list[Membership]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    password_reset_tokens: Mapped[list[PasswordResetToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    notification_preferences: Mapped[list[UserNotificationPreference]] = relationship(
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


class PasswordHistory(Base):
    """Rolling history of a user's prior bcrypt hashes (audit #10).

    Migration ``0029_password_history``. The service writes one row
    per password change with the OLD hash (the one being replaced)
    and trims the user's history to the most recent
    ``PASSWORD_HISTORY_DEPTH`` entries. On every change we
    bcrypt-verify the new plaintext against each retained hash and
    reject 422 if any matches — preventing the "reset to the same
    password I had before" anti-pattern that compliance audits flag.

    Why a separate table instead of a JSON column on ``User``:
      * bcrypt hashes are 60 bytes each; storing N=5 in a column is
        fine in PG but the audit trail (creation timestamps + a
        clean delete-on-cascade) lives more naturally in its own
        relation.
      * Tunability: bumping the depth from 5 → 10 is a one-line
        constant change in the service; no schema migration.
    """

    __tablename__ = "password_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class Membership(TimestampMixin, Base):
    """Join table between users and orgs, carrying a single role.

    A user with two roles in the same org has two rows. A user with
    access to two orgs has two rows. The role vocabulary starts at
    ``internal_admin``; ``reviewer`` and ``client_admin`` will be
    added by later patches when the surfaces that need them ship.
    """

    __tablename__ = "memberships"
    # The partial unique index mirrors migration 0037 with a
    # ``sqlite_where`` twin so SQLite test fixtures (``create_all``)
    # enforce the one-active-primary-per-org invariant consistently
    # with production Postgres.
    __table_args__ = (
        UniqueConstraint(
            "user_id", "organization_id", "role", name="uq_memberships_user_org_role"
        ),
        Index(
            "ux_memberships_primary_per_org",
            "organization_id",
            unique=True,
            postgresql_where=text("is_primary AND status = 'active'"),
            sqlite_where=text("is_primary AND status = 'active'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    # Multi-user (2026-06-10) — marks the Primary Account Owner of a
    # client org. The owner manages the org's other seats (invite,
    # disable, remove); secondaries carry the same ``client_admin``
    # role so every existing gate keeps working. At most one *active*
    # primary per org (removed/disabled rows keep the flag for the
    # historical record while a successor is designated).
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)

    user: Mapped[User] = relationship(back_populates="memberships")
    organization: Mapped[Organization] = relationship(back_populates="memberships")


class AuditLog(Base):
    __tablename__ = "audit_log"

    # Entity audit-trail reconstruction filters by (entity_type,
    # entity_id); actor timelines filter by actor_id. Both full-scanned
    # the append-only log before migration 0034.
    __table_args__ = (
        Index("ix_audit_log_entity", "entity_type", "entity_id"),
        Index("ix_audit_log_actor", "actor_id"),
        # PERF (2026-06-17, migration 0048) — explorer filters by action and
        # orders by created_at DESC; the ops dashboard scans an action-scoped
        # slice every load. audit_log is append-only and grows without bound.
        Index("ix_audit_log_action_created", "action", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[str | None] = mapped_column(String(120))
    actor_type: Mapped[str] = mapped_column(String(60), default="system", nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    before: Mapped[dict | None] = mapped_column(JSON)
    after: Mapped[dict | None] = mapped_column(JSON)
    event_metadata: Mapped[dict | None] = mapped_column("metadata", JSON)
    # Request provenance (migration 0043, platform rework Phase 0). Both
    # best-effort and nullable: captured from the first ``X-Forwarded-For``
    # hop (Render terminates TLS ahead of uvicorn). NULL on
    # system-originated events and on rows written before this column.
    # ``ip_address`` is sized for an IPv6 literal (45 chars).
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(512))
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
    # PERF (2026-06-17, migration 0049) — list_reports filters by
    # organization_id (= or IN) and orders by updated_at DESC; the composite
    # serves the org-scoped list + sort.
    __table_args__ = (
        Index("ix_reports_org_updated", "organization_id", "updated_at"),
    )

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
    """Analytics event for the Wise copilot dock (provider OR cliente).

    Captures every meaningful dock interaction (mount, expand,
    collapse, suggestion click, question, feedback) so we can answer
    "did the empty-state hero + Wise dock actually move the time-to-
    first-upload needle?" Tiny by design — one row per event, anchored
    to a workspace (provider) or a client (cliente).

    Conventions match the rest of the schema: 36-char id, timezone-
    aware timestamps, JSON payload for optional structured context
    (e.g. ``{"suggestion_id": "act-..."}`` for ``wise.suggestion_clicked``).
    """

    __tablename__ = "wise_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    # Tenant anchor: provider events set ``workspace_id``, cliente events
    # set ``client_id`` (the buyer reasons over a portfolio, not one
    # workspace). Exactly one is populated. ``workspace_id`` became
    # nullable in migration 0041, which added ``client_id`` so the
    # cliente dock can persist instead of log-only.
    workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("provider_workspaces.id"), nullable=True, index=True
    )
    client_id: Mapped[str | None] = mapped_column(
        ForeignKey("clients.id"), nullable=True, index=True
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


class ProviderNotification(Base):
    """Provider-facing notification generated from reviewer-decision events.

    Phase 4 / Slice 4B — portal-side analogue of
    ``ClientNotification``. Keyed on ``workspace_id`` (the tenant
    boundary on the portal side) so the inbox naturally scopes to a
    single provider. Severity is in the schema from day 1 so the
    semáforo treatment ships without a follow-up evolution.
    """

    __tablename__ = "provider_notifications"
    # PERF (2026-06-17, migration 0049) — the inbox lists
    # ``WHERE workspace_id = ? [AND read_at IS NULL] ORDER BY created_at DESC``;
    # the composite serves the filter + the sort from one index.
    __table_args__ = (
        Index(
            "ix_provider_notifications_workspace_created",
            "workspace_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("provider_workspaces.id"), nullable=False, index=True
    )
    submission_id: Mapped[str | None] = mapped_column(
        ForeignKey("submissions.id"), nullable=True, index=True
    )
    notification_type: Mapped[str] = mapped_column(
        String(80), nullable=False, index=True
    )
    severity: Mapped[str] = mapped_column(
        String(20), default="info", nullable=False
    )
    # Phase 7 / Slice N9b — canonical Phase 7 vocabulary (``renewal``,
    # ``reporting``, ``verification``, ``account``, ``admin``, ``other``).
    # Defaults to empty string at the migration boundary; emitters
    # populate it via :func:`app.services.notifications.categorize.derive_category`
    # or set it explicitly.
    category: Mapped[str] = mapped_column(
        String(20), default="", nullable=False
    )
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    action_url: Mapped[str | None] = mapped_column(String(512))
    payload: Mapped[dict | None] = mapped_column(JSON)
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )


class ClientNotification(Base):
    """Client-facing notification generated from provider/document events."""

    __tablename__ = "client_notifications"
    # PERF (2026-06-17, migration 0049) — the inbox lists
    # ``WHERE client_id = ? [AND read_at IS NULL] ORDER BY created_at DESC``;
    # the composite serves the filter + the sort from one index.
    __table_args__ = (
        Index("ix_client_notifications_client_created", "client_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    client_id: Mapped[str] = mapped_column(
        ForeignKey("clients.id"), nullable=False, index=True
    )
    vendor_id: Mapped[str | None] = mapped_column(
        ForeignKey("vendors.id"), nullable=True, index=True
    )
    submission_id: Mapped[str | None] = mapped_column(
        ForeignKey("submissions.id"), nullable=True, index=True
    )
    notification_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    action_url: Mapped[str | None] = mapped_column(String(512))
    payload: Mapped[dict | None] = mapped_column(JSON)
    # Phase 4 / Slice 4A — semáforo discriminator. Canonical values:
    # ``green`` (approved / complete), ``yellow`` (pending / in
    # review / due soon), ``red`` (rejected / missing / expired),
    # ``info`` (background automation, non-actionable). Stored
    # explicitly per row so a future notification type can pick its
    # own severity without a global mapping update.
    severity: Mapped[str] = mapped_column(
        String(20), default="info", nullable=False
    )
    # Phase 7 / Slice N9b — canonical Phase 7 vocabulary. See
    # the ``ProviderNotification.category`` docstring above.
    category: Mapped[str] = mapped_column(
        String(20), default="", nullable=False
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )

    client: Mapped[Client] = relationship(back_populates="notifications")


class ClientNotificationRead(Base):
    """Per-user read mark for a client notification.

    Multi-user (2026-06-10). ``ClientNotification`` rows are scoped to
    the *client*, so the parent ``read_at`` column conflates read
    state once an org has more than one user: user A marking a row
    read would mark it read for user B. One row here per
    ``(notification_id, user_id)`` gives each user an independent
    read state. Absence of a row means "unread for that user" — the
    table stays sparse and needs no backfill.

    The notification endpoints switch from ``read_at`` to this table
    in a follow-up patch; until then the legacy column keeps the
    current single-user behavior intact.
    """

    __tablename__ = "client_notification_reads"
    __table_args__ = (Index("ix_client_notification_reads_user", "user_id"),)

    notification_id: Mapped[str] = mapped_column(
        ForeignKey("client_notifications.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class RenewalReminder(Base):
    """Per-cycle, per-threshold idempotency anchor for renewal notifications.

    Phase 6 / Slice 6B. One row per
    ``(workspace_id, requirement_code, cycle_anchor_date, threshold_days)``.
    The unique constraint is the entire dedupe mechanism — the
    renewal dispatcher inserts first and uses ``IntegrityError`` to
    detect "already emitted, skip". The dispatcher writes both the
    client and the provider notification only after the
    ``RenewalReminder`` insert succeeds, so the two notification
    surfaces stay in lockstep.

    ``cycle_anchor_date`` is the day the standing approved submission
    became evidence (the value returned by
    :func:`app.services.evidence_slots.renewal_anchor_date`). A
    follow-up approved upload changes the anchor → new cycle → all
    threshold slots reset under the new anchor and fire again as that
    cycle progresses. The historical reminders for the prior cycle
    stay on the table as the audit record of what was sent.
    """

    __tablename__ = "renewal_reminders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("provider_workspaces.id"), nullable=False
    )
    requirement_code: Mapped[str] = mapped_column(String(80), nullable=False)
    cycle_anchor_date: Mapped[date] = mapped_column(Date, nullable=False)
    threshold_days: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "requirement_code",
            "cycle_anchor_date",
            "threshold_days",
            name="uq_renewal_reminders_cycle_threshold",
        ),
    )


class NotificationDispatch(Base):
    """Phase 7 / Slice N1 — idempotency anchor for the unified fabric.

    One row per ``(user_id, event_type, dedupe_key)`` triple. The
    unique constraint is the dedupe mechanism — the dispatcher
    inserts first, and an ``IntegrityError`` on collision tells it
    "already dispatched, skip". This is the same pattern as
    :class:`RenewalReminder`, generalized so every event in the
    Phase 7 catalog uses one table.

    ``user_id`` is intentionally NOT a foreign key to ``users``: the
    recipient model is heterogeneous (provider workspaces have no
    ``User`` row), and ``recipient_role`` is the discriminator.

    The channel-attempt columns (``email_status`` / ``whatsapp_status``
    + their reasons) are populated by Slice N4 once routing and
    delivery wire in. At N1 they stay NULL.
    """

    __tablename__ = "notification_dispatch"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    recipient_role: Mapped[str] = mapped_column(String(40), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSON)
    inapp_id: Mapped[str | None] = mapped_column(String(36))
    email_status: Mapped[str | None] = mapped_column(String(20))
    email_reason: Mapped[str | None] = mapped_column(String(120))
    whatsapp_status: Mapped[str | None] = mapped_column(String(20))
    whatsapp_reason: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "event_type",
            "dedupe_key",
            name="uq_notification_dispatch_recipient_event",
        ),
    )


class UserNotificationPreference(Base):
    """Per-user, per-category mute matrix.

    Phase 7 / Slice N2. Composite primary key on
    ``(user_id, category)``. A row exists only when the user has
    overridden the catalog default — absence means "no override"
    and the routing layer treats both mute flags as ``False``.
    Keeping the table sparse keeps the common-case query cheap and
    avoids a backfill on user creation.

    Note: ``category_email_muted`` does NOT silence ``critical``-tier
    events. The routing function in
    :mod:`app.services.notifications.routing` enforces the
    critical-email-unmuteable rule regardless of what this row says.
    The mute flag is therefore an honest representation of the
    user's *intent*; the dispatcher applies policy on top.
    """

    __tablename__ = "user_notification_preferences"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    category: Mapped[str] = mapped_column(String(40), primary_key=True)
    email_muted: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    whatsapp_muted: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="notification_preferences")


class NotificationTemplateVersion(Base):
    """Versioned copy for one (event_type, channel, locale).

    Phase 7 / Slice N3. The dispatcher will look up the row with
    ``is_active=true`` at render time and substitute ``{{var}}``
    placeholders from the envelope payload (see
    :mod:`app.services.notifications.rendering`).

    The "at most one active per key" invariant is enforced at the
    application layer (admin API runs the demote + promote inside
    a transaction), not via a partial unique index, so the table
    works on SQLite (used in tests) and Postgres alike.

    ``subject`` is email-only. ``meta_template_name`` is WhatsApp-
    only and points at the pre-approved template name registered
    with Meta. Both are nullable.
    """

    __tablename__ = "notification_template_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    locale: Mapped[str] = mapped_column(
        String(10), nullable=False, default="es-MX"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    subject: Mapped[str | None] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    meta_template_name: Mapped[str | None] = mapped_column(String(80))
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "event_type",
            "channel",
            "locale",
            "version",
            name="uq_notif_templates_event_channel_locale_version",
        ),
    )


class PhoneVerification(Base):
    """Phase 7 / Slice N8 — short-lived OTP record.

    One row per verification attempt. The User can have multiple
    historical rows; only the most recent ``consumed_at IS NULL AND
    expires_at > now()`` row is "active". The application enforces
    that at most one row is active by invalidating prior rows when
    a fresh ``request_verification`` lands.

    ``code_hash`` is HMAC-SHA256 of the plaintext code keyed on the
    server's JWT secret. The plaintext only lives in the user's
    phone (sent out-of-band via WhatsApp) and the inbound confirm
    request body — never on disk.
    """

    __tablename__ = "phone_verifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    phone_e164: Mapped[str] = mapped_column(String(20), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )


class ExpedienteAssessment(TimestampMixin, Base):
    """Phase 2 — expediente-level situational assessment.

    Where ``DocumentInspection.shadow_signals['comprehension']`` (Phase 1)
    reasons about ONE document, this row reasons about the WHOLE situation
    for a provider in a period: cross-document coherence (does the IMSS
    headcount match the contract's ``estimated_workers``, is the REPSE
    authorized activity consistent with the contracted service, do the
    periods/entities cohere across documents) plus obligation coverage
    gaps.

    Reviewer-facing and additive — like the shadow columns it never alters
    user-visible status. One row per assessment run; re-runs append
    (history), newest by ``created_at``.
    """

    __tablename__ = "expediente_assessments"
    __table_args__ = (
        Index(
            "ix_expediente_assessments_scope",
            "client_id",
            "vendor_id",
            "period_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), nullable=False)
    vendor_id: Mapped[str] = mapped_column(ForeignKey("vendors.id"), nullable=False)
    period_id: Mapped[str | None] = mapped_column(ForeignKey("periods.id"))
    contract_id: Mapped[str | None] = mapped_column(ForeignKey("contracts.id"))

    # LLM provenance, mirroring the ``DocumentInspection.shadow_*`` columns.
    provider_id: Mapped[str | None] = mapped_column(String(120))
    prompt_version: Mapped[str | None] = mapped_column(String(60))

    # Overall situational read: "coherent" | "minor_issues" |
    # "incoherent" | "indeterminate". NULL when the run errored.
    coherence: Mapped[str | None] = mapped_column(String(20))
    # list of {code, severity, detail_es, evidence} — cross-document
    # situational findings (headcount mismatch, activity inconsistency,
    # period incoherence, entity mismatch, contract-window mismatch, ...).
    findings: Mapped[list | None] = mapped_column(JSON)
    # list of {requirement_code, detail_es} — obligations the situation
    # implies but that are missing or unsatisfied in the assessed set.
    coverage_gaps: Mapped[list | None] = mapped_column(JSON)
    # The documents that were part of this assessment (audit trail).
    document_ids: Mapped[list | None] = mapped_column(JSON)
    summary_for_reviewer: Mapped[str | None] = mapped_column(Text)

    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
