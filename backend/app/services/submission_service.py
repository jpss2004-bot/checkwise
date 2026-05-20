"""Submission-time orchestration: PDF gating, entity get-or-create,
status derivation, and the validation-event timeline written on intake.

These helpers used to live as private functions inside ``api/v1/endpoints.py``.
They were extracted so the router stays a thin shell over business logic and
the same helpers can be reused by future surfaces (importer, batch jobs,
re-validation flows).
"""

from __future__ import annotations

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants.institutions import INSTITUTION_LABELS, Institution
from app.constants.statuses import DocumentStatus
from app.core.config import settings
from app.models import (
    Client,
    Contract,
    Document,
    DocumentInspection,
    DocumentStatusHistory,
    Submission,
    Validation,
    Vendor,
)
from app.models import Institution as InstitutionModel
from app.schemas.submissions import (
    DocumentBatchEntry,
    DocumentInspectionSummary,
    DocumentSignalsSummary,
    MultiSubmissionResponse,
    SubmissionResponse,
    SupportInfo,
    ValidationEventSummary,
)
from app.services.audit_log import add_audit_event
from app.services.document_intelligence import DocumentSignals, analyze_document_text
from app.services.pdf_validation import PdfInspectionResult, inspect_pdf
from app.services.prevalidation import build_initial_validations
from app.services.requirement_service import ResolvedPeriod, ResolvedRequirement
from app.services.storage import StoredFile
from app.services.validation_events import add_validation_event

PDF_MIME_TYPES = frozenset(
    {
        "application/pdf",
        "application/x-pdf",
        "application/octet-stream",
    }
)


def assert_pdf_upload(file: UploadFile) -> None:
    """Reject anything that isn't a `.pdf` with a plausible MIME type."""
    filename = file.filename or ""
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="En esta fase solo se aceptan archivos PDF.",
        )

    if file.content_type and file.content_type not in PDF_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El MIME type recibido no parece PDF: {file.content_type}.",
        )


def status_from_inspection(
    pdf_inspection: PdfInspectionResult,
    document_signals: DocumentSignals,
) -> DocumentStatus:
    """Derive the initial submission status from PDF inspection + signals."""
    if not pdf_inspection.is_pdf or pdf_inspection.is_corrupt or pdf_inspection.is_encrypted:
        return DocumentStatus.REQUIERE_ACLARACION
    if document_signals.mismatch_reason:
        return DocumentStatus.POSIBLE_MISMATCH
    return DocumentStatus.PENDIENTE_REVISION


def submission_message(status_code: DocumentStatus | str) -> str:
    """Provider-facing copy for the API response after intake."""
    if status_code == DocumentStatus.REQUIERE_ACLARACION:
        return (
            "Carga recibida, pero el PDF requiere aclaración antes de revisión "
            "porque no pudo inspeccionarse correctamente."
        )
    if status_code == DocumentStatus.POSIBLE_MISMATCH:
        return (
            "Carga recibida con alerta de posible mismatch. Verifica el archivo o "
            "contacta soporte antes de continuar."
        )
    return "Carga recibida. El documento queda pendiente de revisión humana."


def get_or_create_client(db: Session, name: str) -> Client:
    client = db.scalar(select(Client).where(Client.name == name).limit(1))
    if client:
        return client
    client = Client(name=name, status="active")
    db.add(client)
    db.flush()
    return client


def get_or_create_vendor(db: Session, client_id: str, name: str, rfc: str) -> Vendor:
    vendor = db.scalar(
        select(Vendor).where(Vendor.client_id == client_id, Vendor.rfc == rfc).limit(1)
    )
    if vendor:
        if vendor.name != name:
            vendor.name = name
        return vendor
    vendor = Vendor(client_id=client_id, name=name, rfc=rfc, status="active")
    db.add(vendor)
    db.flush()
    return vendor


def get_or_create_institution(db: Session, code: str) -> InstitutionModel:
    institution = db.scalar(
        select(InstitutionModel).where(InstitutionModel.code == code).limit(1)
    )
    if institution:
        return institution
    label = INSTITUTION_LABELS[Institution(code)]
    institution = InstitutionModel(code=code, name=label)
    db.add(institution)
    db.flush()
    return institution


def get_or_create_contract(
    db: Session, client_id: str, vendor_id: str, external_reference: str | None
) -> Contract | None:
    if not external_reference:
        return None
    contract = db.scalar(
        select(Contract)
        .where(
            Contract.client_id == client_id,
            Contract.vendor_id == vendor_id,
            Contract.external_reference == external_reference,
        )
        .limit(1)
    )
    if contract:
        return contract
    contract = Contract(
        client_id=client_id,
        vendor_id=vendor_id,
        external_reference=external_reference,
        status="active",
    )
    db.add(contract)
    db.flush()
    return contract


def add_native_intake_events(
    db: Session,
    *,
    submission_id: str,
    document_id: str,
    stored_file: StoredFile,
    duplicate_found: bool,
    pdf_inspection: PdfInspectionResult,
    document_signals: DocumentSignals,
    human_review_required: bool,
    requirement_used_legacy: bool = False,
    period_used_legacy: bool = False,
) -> list:
    """Write the per-step validation-event timeline for a native-intake submission."""
    events = [
        add_validation_event(
            db,
            submission_id=submission_id,
            document_id=document_id,
            event_type="upload_started",
            rule_code="native_intake",
            result="pass",
            message="El proveedor inició una carga documental en el portal nativo.",
            payload={"filename": stored_file.original_filename},
            actor_type="supplier",
        ),
        add_validation_event(
            db,
            submission_id=submission_id,
            document_id=document_id,
            event_type="file_received",
            rule_code="file_exists",
            result="pass" if stored_file.size_bytes > 0 else "fail",
            severity="info" if stored_file.size_bytes > 0 else "error",
            message="Archivo recibido y guardado en storage.",
            payload={"size_bytes": stored_file.size_bytes, "storage_key": stored_file.storage_key},
        ),
        add_validation_event(
            db,
            submission_id=submission_id,
            document_id=document_id,
            event_type="file_hash_generated",
            rule_code="sha256_hash",
            result="pass",
            message="Hash SHA-256 generado.",
            payload={"sha256": stored_file.sha256},
        ),
        add_validation_event(
            db,
            submission_id=submission_id,
            document_id=document_id,
            event_type="file_type_validated",
            rule_code="allowed_file_type",
            result="pass" if stored_file.extension == ".pdf" else "fail",
            severity="info" if stored_file.extension == ".pdf" else "error",
            message="Validación estricta PDF-only ejecutada.",
            payload={"extension": stored_file.extension, "mime_type": stored_file.mime_type},
        ),
        add_validation_event(
            db,
            submission_id=submission_id,
            document_id=document_id,
            event_type="pdf_inspected",
            rule_code="pdf_magic_header",
            result="fail" if pdf_inspection.is_corrupt else "pass",
            severity="error" if pdf_inspection.is_corrupt else "info",
            message=pdf_inspection.error or "PDF inspeccionado correctamente.",
            payload={
                "is_pdf": pdf_inspection.is_pdf,
                "is_corrupt": pdf_inspection.is_corrupt,
                "is_encrypted": pdf_inspection.is_encrypted,
                "page_count": pdf_inspection.page_count,
            },
        ),
        add_validation_event(
            db,
            submission_id=submission_id,
            document_id=document_id,
            event_type="text_extracted",
            rule_code="pdf_readable_text",
            result="pass" if pdf_inspection.has_text else "warning",
            severity="info" if pdf_inspection.has_text else "warning",
            message=(
                "Se extrajo texto del PDF."
                if pdf_inspection.has_text
                else "No se extrajo texto suficiente; podría requerir OCR."
            ),
            payload={"text_char_count": pdf_inspection.text_char_count},
        ),
        add_validation_event(
            db,
            submission_id=submission_id,
            document_id=document_id,
            event_type="human_review_required",
            rule_code="human_review_required",
            result="required" if human_review_required else "not_required",
            severity="warning" if human_review_required else "info",
            message="La revisión humana se mantiene obligatoria para aprobación crítica.",
        ),
        add_validation_event(
            db,
            submission_id=submission_id,
            document_id=document_id,
            event_type="supplier_confirmed_submission",
            rule_code="native_intake",
            result="pass",
            message="El proveedor confirmó el envío desde el intake nativo.",
            actor_type="supplier",
        ),
    ]

    if duplicate_found:
        events.append(
            add_validation_event(
                db,
                submission_id=submission_id,
                document_id=document_id,
                event_type="duplicate_detected",
                rule_code="duplicate_hash",
                result="warning",
                severity="warning",
                message="Se detectó un documento existente con el mismo SHA-256.",
                payload={"sha256": stored_file.sha256},
            )
        )

    if document_signals.mismatch_reason:
        events.append(
            add_validation_event(
                db,
                submission_id=submission_id,
                document_id=document_id,
                event_type="requirement_mismatch_detected",
                rule_code="requirement_match",
                result="warning",
                severity="warning",
                message=document_signals.mismatch_reason,
                confidence=document_signals.requirement_match_confidence,
                payload={
                    "detected_institution": document_signals.detected_institution,
                    "detected_document_type": document_signals.detected_document_type,
                    "anomaly_codes": document_signals.anomaly_codes,
                },
            )
        )

    if requirement_used_legacy:
        events.append(
            add_validation_event(
                db,
                submission_id=submission_id,
                document_id=document_id,
                event_type="legacy_requirement_intake",
                rule_code="canonical_requirement_code",
                result="warning",
                severity="warning",
                message=(
                    "Intake aceptado sin requirement_code canónico. La forma libre "
                    "queda deprecated; envía requirement_code desde el catálogo."
                ),
            )
        )

    if period_used_legacy:
        events.append(
            add_validation_event(
                db,
                submission_id=submission_id,
                document_id=document_id,
                event_type="legacy_period_intake",
                rule_code="canonical_period_key",
                result="warning",
                severity="warning",
                message=(
                    "Intake aceptado sin period_key canónico. La forma libre "
                    "queda deprecated; envía period_key desde el catálogo."
                ),
            )
        )

    return events


# ---------------------------------------------------------------------------
# Shared intake orchestration
# ---------------------------------------------------------------------------


# Audit-metadata values for the ``intake_source`` key. Distinguishes the
# two paths so an auditor can tell whether a submission came in through
# the legacy free-text endpoint (browser-posted tenant identity) or the
# tenant-safe workspace-scoped portal endpoint (workspace-derived
# identity). Kept in code rather than in the catalog so the labels can't
# drift between writer (here) and any reader.
INTAKE_SOURCE_LEGACY_NATIVE = "legacy_native_intake"
INTAKE_SOURCE_WORKSPACE_PORTAL = "workspace_portal_intake"

_INTAKE_HISTORY_REASON = {
    INTAKE_SOURCE_LEGACY_NATIVE: "Carga inicial desde portal nativo CheckWise.",
    INTAKE_SOURCE_WORKSPACE_PORTAL: (
        "Carga inicial desde portal del proveedor (workspace autenticado)."
    ),
}


def finalize_intake_submission(
    db: Session,
    *,
    stored_file: StoredFile,
    client: Client,
    vendor: Vendor,
    contract: Contract | None,
    institution: InstitutionModel,
    resolved_requirement: ResolvedRequirement,
    resolved_period: ResolvedPeriod,
    load_type: str,
    period_code: str,
    comments: str | None,
    submitted_by: str,
    intake_source: str,
    extra_audit_metadata: dict | None = None,
    supersedes_submission: Submission | None = None,
) -> SubmissionResponse:
    """Run the shared back-half of a documentary intake.

    Both ``POST /api/v1/submissions`` (legacy native intake, kept for the
    importer + dev paths) and ``POST /api/v1/portal/workspaces/{id}/submissions``
    (tenant-safe workspace-scoped intake) call this helper. The two
    endpoints differ only in how they resolve tenant identity
    (``client`` / ``vendor`` / ``contract``):

    * Legacy: get-or-create from browser-posted form fields.
      Tenant identity is NOT authoritative — kept for the importer
      and historic test paths.
    * Workspace: pre-loaded from the authenticated
      :class:`ProviderWorkspace`. Tenant identity is authoritative.

    Once tenant identity + requirement/period are resolved, the rest of
    the pipeline (PDF inspection, duplicate detection, validation
    signals, status derivation, audit log, response shaping) is
    identical, so it lives here. Adding a new intake surface in the
    future means resolving identity in the router and calling this same
    function — never duplicating the orchestration.

    ``intake_source`` MUST be one of ``INTAKE_SOURCE_LEGACY_NATIVE`` /
    ``INTAKE_SOURCE_WORKSPACE_PORTAL``. It is written to the audit-log
    metadata so an auditor can tell which path produced the row.
    """
    duplicate = db.scalar(
        select(Document).where(Document.sha256 == stored_file.sha256).limit(1)
    )

    pdf_inspection = inspect_pdf(stored_file.path)
    document_signals = analyze_document_text(
        pdf_inspection.text_sample,
        expected_requirement=resolved_requirement.canonical_name,
        expected_institution=institution.code,
        expected_period=period_code,
    )
    final_status = status_from_inspection(pdf_inspection, document_signals)

    submission = Submission(
        client_id=client.id,
        vendor_id=vendor.id,
        contract_id=contract.id if contract else None,
        period_id=resolved_period.period.id,
        institution_id=institution.id,
        requirement_id=resolved_requirement.requirement.id,
        requirement_version_id=resolved_requirement.requirement_version.id,
        requirement_code=resolved_requirement.canonical_code,
        period_key=resolved_period.canonical_period_key,
        load_type=load_type,
        source="portal",
        status=final_status.value,
        comments=comments,
        submitted_by=submitted_by,
        # Replacement lineage (Phase 3). Caller must have already
        # validated that the prior submission belongs to the same
        # tenant + slot and is in an eligible state before passing it
        # in; this layer trusts that decision and just persists the
        # FK + emits the lineage audit trail.
        supersedes_submission_id=(
            supersedes_submission.id if supersedes_submission is not None else None
        ),
    )
    db.add(submission)
    db.flush()

    document = Document(
        submission_id=submission.id,
        storage_key=stored_file.storage_key,
        original_filename=stored_file.original_filename,
        mime_type=stored_file.mime_type,
        size_bytes=stored_file.size_bytes,
        sha256=stored_file.sha256,
        status=final_status.value,
    )
    db.add(document)
    db.flush()

    inspection = DocumentInspection(
        document_id=document.id,
        is_pdf=pdf_inspection.is_pdf,
        is_corrupt=pdf_inspection.is_corrupt,
        is_encrypted=pdf_inspection.is_encrypted,
        page_count=pdf_inspection.page_count,
        text_char_count=pdf_inspection.text_char_count,
        has_text=pdf_inspection.has_text,
        is_probably_scanned=pdf_inspection.is_probably_scanned,
        detected_institution=document_signals.detected_institution,
        detected_document_type=document_signals.detected_document_type,
        detected_rfcs=document_signals.detected_rfcs,
        detected_dates=document_signals.detected_dates,
        period_mentions=document_signals.period_mentions,
        requirement_match_confidence=document_signals.requirement_match_confidence,
        mismatch_reason=document_signals.mismatch_reason,
        inspection_error=pdf_inspection.error,
        raw_metadata=pdf_inspection.metadata,
    )
    db.add(inspection)

    signals = build_initial_validations(
        stored_file,
        duplicate_found=duplicate is not None,
        pdf_inspection=pdf_inspection,
        document_signals=document_signals,
        human_review_required=resolved_requirement.requirement_version.human_review_required,
    )
    for signal in signals:
        db.add(
            Validation(
                submission_id=submission.id,
                document_id=document.id,
                rule_code=signal.rule_code,
                rule_type=signal.rule_type,
                result=signal.result,
                severity=signal.severity,
                message=signal.message,
                requires_human_review=signal.requires_human_review,
            )
        )

    history_reason = _INTAKE_HISTORY_REASON.get(
        intake_source, "Carga inicial desde flujo no clasificado."
    )
    db.add(
        DocumentStatusHistory(
            document_id=document.id,
            submission_id=submission.id,
            from_status=None,
            to_status=final_status.value,
            reason=history_reason,
            actor="system",
        )
    )

    validation_events = add_native_intake_events(
        db,
        submission_id=submission.id,
        document_id=document.id,
        stored_file=stored_file,
        duplicate_found=duplicate is not None,
        pdf_inspection=pdf_inspection,
        document_signals=document_signals,
        human_review_required=resolved_requirement.requirement_version.human_review_required,
        requirement_used_legacy=resolved_requirement.used_legacy,
        period_used_legacy=resolved_period.used_legacy,
    )

    # Phase 3 — replacement lineage. Two ValidationEvents (one per
    # affected submission) make the link visible in both timelines,
    # then a dedicated AuditLog row gives auditors a single query
    # ("show me everything that was a replacement").
    if supersedes_submission is not None:
        replacement_event = add_validation_event(
            db,
            submission_id=submission.id,
            document_id=document.id,
            event_type="submission_replacement_linked",
            rule_code="submission_replacement",
            result="pass",
            severity="info",
            message=(
                "Esta carga reemplaza una entrega anterior del mismo requisito "
                "para este proveedor y periodo."
            ),
            payload={
                "previous_submission_id": supersedes_submission.id,
                "previous_status": supersedes_submission.status,
            },
            actor_type="supplier",
        )
        validation_events.append(replacement_event)
        add_validation_event(
            db,
            submission_id=supersedes_submission.id,
            # The prior submission's own primary document, not the new
            # one — keeps the event correctly attributed in the prior
            # submission's timeline.
            document_id=None,
            event_type="submission_replaced",
            rule_code="submission_replacement",
            result="superseded",
            severity="info",
            message=(
                "Esta entrega fue reemplazada por una nueva carga del mismo "
                "requisito y periodo."
            ),
            payload={
                "new_submission_id": submission.id,
                "previous_status": supersedes_submission.status,
            },
            actor_type="system",
        )

    audit_metadata: dict = {
        # Kept for backward compatibility with existing audit consumers.
        "source": "native_intake",
        # Distinguishes the two intake surfaces. New in Phase 1.
        "intake_source": intake_source,
        "storage_key": stored_file.storage_key,
        "sha256": stored_file.sha256,
        "requirement_intake": (
            "legacy_free_text" if resolved_requirement.used_legacy else "canonical_code"
        ),
        "period_intake": (
            "legacy_period_code" if resolved_period.used_legacy else "canonical_period_key"
        ),
        "validation_events": [event.event_type for event in validation_events],
    }
    if supersedes_submission is not None:
        audit_metadata["supersedes_submission_id"] = supersedes_submission.id
    if extra_audit_metadata:
        audit_metadata.update(extra_audit_metadata)

    add_audit_event(
        db,
        action="submission.created",
        entity_type="submission",
        entity_id=submission.id,
        after={
            "client_id": client.id,
            "vendor_id": vendor.id,
            "period_id": resolved_period.period.id,
            "requirement_id": resolved_requirement.requirement.id,
            "requirement_code": resolved_requirement.canonical_code,
            "period_key": resolved_period.canonical_period_key,
            "status": final_status.value,
            "supersedes_submission_id": (
                supersedes_submission.id if supersedes_submission is not None else None
            ),
        },
        metadata=audit_metadata,
    )

    # Dedicated lineage audit-log row (Phase 3). Lets compliance reports
    # filter on ``action='submission.replacement_linked'`` directly
    # instead of mining the intake row's ``after.supersedes_*`` field.
    if supersedes_submission is not None:
        add_audit_event(
            db,
            action="submission.replacement_linked",
            entity_type="submission",
            entity_id=submission.id,
            metadata={
                "previous_submission_id": supersedes_submission.id,
                "new_submission_id": submission.id,
                "requirement_code": resolved_requirement.canonical_code,
                "period_key": resolved_period.canonical_period_key,
                # ``workspace_id`` is supplied by the workspace endpoint via
                # ``extra_audit_metadata``; the lookup tolerates its absence
                # (legacy endpoint never sets a workspace).
                "workspace_id": (extra_audit_metadata or {}).get("workspace_id"),
                "previous_status": supersedes_submission.status,
            },
        )

    db.commit()

    return SubmissionResponse(
        submission_id=submission.id,
        document_id=document.id,
        status=final_status.value,
        sha256=stored_file.sha256,
        storage_key=stored_file.storage_key,
        validations=signals,
        validation_events=[
            ValidationEventSummary(
                event_type=event.event_type,
                result=event.result,
                severity=event.severity,
                message=event.message,
                confidence=event.confidence,
            )
            for event in validation_events
        ],
        inspection=DocumentInspectionSummary(
            is_pdf=pdf_inspection.is_pdf,
            is_corrupt=pdf_inspection.is_corrupt,
            is_encrypted=pdf_inspection.is_encrypted,
            page_count=pdf_inspection.page_count,
            text_char_count=pdf_inspection.text_char_count,
            has_text=pdf_inspection.has_text,
            is_probably_scanned=pdf_inspection.is_probably_scanned,
        ),
        document_signals=DocumentSignalsSummary(
            detected_institution=document_signals.detected_institution,
            detected_document_type=document_signals.detected_document_type,
            detected_rfcs=document_signals.detected_rfcs,
            detected_dates=document_signals.detected_dates,
            period_mentions=document_signals.period_mentions,
            requirement_match_confidence=document_signals.requirement_match_confidence,
            mismatch_reason=document_signals.mismatch_reason,
            anomaly_codes=document_signals.anomaly_codes,
        ),
        support=SupportInfo(
            whatsapp_url=settings.SUPPORT_WHATSAPP_URL or None,
            qr_placeholder_url=settings.SUPPORT_QR_PLACEHOLDER_URL or None,
            message="Contacta soporte si no sabes qué documento subir o detectas una alerta.",
        ),
        message=submission_message(final_status),
    )


# ---------------------------------------------------------------------------
# Stage 2.7-b — Multi-document submission orchestration
# ---------------------------------------------------------------------------
#
# The data model already supports 1 Submission → N Documents
# (``Submission.documents`` 1:N from ``backend/app/models/entities.py:222``).
# The provider portal's batch endpoint at
# ``POST /portal/workspaces/{id}/submissions/batch`` uses this helper to
# persist a single Submission row with N Documents under it for cases
# where a provider must attach a contract + annex, or a CFDI + its
# acuse, as one logical entry against the same requirement+period slot.
#
# Atomic semantics: every Document is created inside the same DB
# transaction. If any file fails PDF inspection or storage write, the
# router rolls back and the entire submission is dropped — no partial
# rows, no orphaned PDFs. The per-file derivation matches the single-
# file path (``status_from_inspection``); the Submission's overall
# status is the *worst* (most actionable) per-doc status.
#
# Status priority (worst → best):
#   REQUIERE_ACLARACION  →  POSIBLE_MISMATCH  →  PENDIENTE_REVISION


_SUBMISSION_STATUS_PRIORITY: dict[str, int] = {
    DocumentStatus.REQUIERE_ACLARACION.value: 3,
    DocumentStatus.POSIBLE_MISMATCH.value: 2,
    DocumentStatus.PENDIENTE_REVISION.value: 1,
}


def _worst_status(statuses: list[DocumentStatus]) -> DocumentStatus:
    """Return the most actionable (= highest priority) status from the batch."""
    if not statuses:
        return DocumentStatus.PENDIENTE_REVISION
    return max(
        statuses,
        key=lambda s: _SUBMISSION_STATUS_PRIORITY.get(s.value, 0),
    )


def finalize_multi_document_submission(
    db: Session,
    *,
    stored_files: list[StoredFile],
    client: Client,
    vendor: Vendor,
    contract: Contract | None,
    institution: InstitutionModel,
    resolved_requirement: ResolvedRequirement,
    resolved_period: ResolvedPeriod,
    load_type: str,
    period_code: str,
    comments: str | None,
    submitted_by: str,
    intake_source: str,
    extra_audit_metadata: dict | None = None,
    supersedes_submission: Submission | None = None,
) -> MultiSubmissionResponse:
    """Persist 1 Submission with N Document children inside one transaction.

    Mirrors the single-file ``finalize_intake_submission`` pipeline for
    every per-document side effect (PDF inspection, classifier signals,
    duplicate detection, Validation rows, DocumentStatusHistory, the
    native-intake ValidationEvent timeline). The Submission row is
    created once; its overall status is the worst-case across the
    batch's per-document statuses.

    Caller responsibilities (the router enforces):
      * ``stored_files`` contains 1 ≤ N ≤ 5 entries.
      * Aggregate ``size_bytes`` ≤ ``MULTI_FILE_TOTAL_BYTES_CAP`` (30 MB).
      * Tenant identity has been resolved from the
        ``ProviderWorkspace`` row.

    Atomicity: a single ``db.commit()`` runs at the end. Any exception
    raised inside the function leaves the transaction open and the
    caller is expected to ``db.rollback()`` it.
    """
    if not stored_files:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Adjunta al menos un archivo.",
        )

    # Pre-inspect every file so we can derive the Submission's overall
    # status before persisting any rows. This also lets us short-circuit
    # before writing to storage if a downstream invariant is going to
    # reject the batch — but storage writes already happened in the
    # router, so this is the last chance to catch a structural problem
    # before we touch the DB.
    inspections: list[tuple[StoredFile, PdfInspectionResult, DocumentSignals, DocumentStatus]] = []
    duplicate_flags: list[bool] = []
    for stored in stored_files:
        duplicate = db.scalar(
            select(Document).where(Document.sha256 == stored.sha256).limit(1)
        )
        pdf_inspection = inspect_pdf(stored.path)
        document_signals = analyze_document_text(
            pdf_inspection.text_sample,
            expected_requirement=resolved_requirement.canonical_name,
            expected_institution=institution.code,
            expected_period=period_code,
        )
        per_file_status = status_from_inspection(pdf_inspection, document_signals)
        inspections.append((stored, pdf_inspection, document_signals, per_file_status))
        duplicate_flags.append(duplicate is not None)

    overall_status = _worst_status([s for _, _, _, s in inspections])

    submission = Submission(
        client_id=client.id,
        vendor_id=vendor.id,
        contract_id=contract.id if contract else None,
        period_id=resolved_period.period.id,
        institution_id=institution.id,
        requirement_id=resolved_requirement.requirement.id,
        requirement_version_id=resolved_requirement.requirement_version.id,
        requirement_code=resolved_requirement.canonical_code,
        period_key=resolved_period.canonical_period_key,
        load_type=load_type,
        source="portal",
        status=overall_status.value,
        comments=comments,
        submitted_by=submitted_by,
        supersedes_submission_id=(
            supersedes_submission.id if supersedes_submission is not None else None
        ),
    )
    db.add(submission)
    db.flush()

    history_reason = _INTAKE_HISTORY_REASON.get(
        intake_source, "Carga inicial desde flujo no clasificado."
    )

    documents_payload: list[DocumentBatchEntry] = []
    aggregated_event_types: list[str] = []
    for (stored, pdf_inspection, document_signals, per_file_status), duplicate_found in zip(
        inspections, duplicate_flags, strict=True
    ):
        document = Document(
            submission_id=submission.id,
            storage_key=stored.storage_key,
            original_filename=stored.original_filename,
            mime_type=stored.mime_type,
            size_bytes=stored.size_bytes,
            sha256=stored.sha256,
            status=per_file_status.value,
        )
        db.add(document)
        db.flush()

        inspection_row = DocumentInspection(
            document_id=document.id,
            is_pdf=pdf_inspection.is_pdf,
            is_corrupt=pdf_inspection.is_corrupt,
            is_encrypted=pdf_inspection.is_encrypted,
            page_count=pdf_inspection.page_count,
            text_char_count=pdf_inspection.text_char_count,
            has_text=pdf_inspection.has_text,
            is_probably_scanned=pdf_inspection.is_probably_scanned,
            detected_institution=document_signals.detected_institution,
            detected_document_type=document_signals.detected_document_type,
            detected_rfcs=document_signals.detected_rfcs,
            detected_dates=document_signals.detected_dates,
            period_mentions=document_signals.period_mentions,
            requirement_match_confidence=document_signals.requirement_match_confidence,
            mismatch_reason=document_signals.mismatch_reason,
            inspection_error=pdf_inspection.error,
            raw_metadata=pdf_inspection.metadata,
        )
        db.add(inspection_row)

        signals = build_initial_validations(
            stored,
            duplicate_found=duplicate_found,
            pdf_inspection=pdf_inspection,
            document_signals=document_signals,
            human_review_required=resolved_requirement.requirement_version.human_review_required,
        )
        for signal in signals:
            db.add(
                Validation(
                    submission_id=submission.id,
                    document_id=document.id,
                    rule_code=signal.rule_code,
                    rule_type=signal.rule_type,
                    result=signal.result,
                    severity=signal.severity,
                    message=signal.message,
                    requires_human_review=signal.requires_human_review,
                )
            )

        db.add(
            DocumentStatusHistory(
                document_id=document.id,
                submission_id=submission.id,
                from_status=None,
                to_status=per_file_status.value,
                reason=history_reason,
                actor="system",
            )
        )

        validation_events = add_native_intake_events(
            db,
            submission_id=submission.id,
            document_id=document.id,
            stored_file=stored,
            duplicate_found=duplicate_found,
            pdf_inspection=pdf_inspection,
            document_signals=document_signals,
            human_review_required=resolved_requirement.requirement_version.human_review_required,
            requirement_used_legacy=resolved_requirement.used_legacy,
            period_used_legacy=resolved_period.used_legacy,
        )
        aggregated_event_types.extend(event.event_type for event in validation_events)

        documents_payload.append(
            DocumentBatchEntry(
                document_id=document.id,
                original_filename=stored.original_filename,
                sha256=stored.sha256,
                storage_key=stored.storage_key,
                status=per_file_status.value,
                inspection=DocumentInspectionSummary(
                    is_pdf=pdf_inspection.is_pdf,
                    is_corrupt=pdf_inspection.is_corrupt,
                    is_encrypted=pdf_inspection.is_encrypted,
                    page_count=pdf_inspection.page_count,
                    text_char_count=pdf_inspection.text_char_count,
                    has_text=pdf_inspection.has_text,
                    is_probably_scanned=pdf_inspection.is_probably_scanned,
                ),
                document_signals=DocumentSignalsSummary(
                    detected_institution=document_signals.detected_institution,
                    detected_document_type=document_signals.detected_document_type,
                    detected_rfcs=document_signals.detected_rfcs,
                    detected_dates=document_signals.detected_dates,
                    period_mentions=document_signals.period_mentions,
                    requirement_match_confidence=document_signals.requirement_match_confidence,
                    mismatch_reason=document_signals.mismatch_reason,
                    anomaly_codes=document_signals.anomaly_codes,
                ),
                validations=signals,
                validation_events=[
                    ValidationEventSummary(
                        event_type=event.event_type,
                        result=event.result,
                        severity=event.severity,
                        message=event.message,
                        confidence=event.confidence,
                    )
                    for event in validation_events
                ],
            )
        )

    # Phase 3 replacement-lineage events fire once at the Submission
    # level — the replaced prior is the entire submission, not one of
    # the new documents. We attach the new event to the first document
    # so the timeline has a canonical anchor.
    if supersedes_submission is not None:
        first_document_id = documents_payload[0].document_id
        add_validation_event(
            db,
            submission_id=submission.id,
            document_id=first_document_id,
            event_type="submission_replacement_linked",
            rule_code="submission_replacement",
            result="pass",
            severity="info",
            message=(
                "Esta carga reemplaza una entrega anterior del mismo requisito "
                "para este proveedor y periodo."
            ),
            payload={
                "previous_submission_id": supersedes_submission.id,
                "previous_status": supersedes_submission.status,
                "document_count": len(documents_payload),
            },
            actor_type="supplier",
        )
        add_validation_event(
            db,
            submission_id=supersedes_submission.id,
            document_id=None,
            event_type="submission_replaced",
            rule_code="submission_replacement",
            result="superseded",
            severity="info",
            message=(
                "Esta entrega fue reemplazada por una nueva carga del mismo "
                "requisito y periodo."
            ),
            payload={
                "new_submission_id": submission.id,
                "previous_status": supersedes_submission.status,
            },
            actor_type="system",
        )

    audit_metadata: dict = {
        "source": "native_intake",
        "intake_source": intake_source,
        "document_count": len(documents_payload),
        "total_size_bytes": sum(s.size_bytes for s, _, _, _ in inspections),
        "storage_keys": [s.storage_key for s, _, _, _ in inspections],
        "sha256_list": [s.sha256 for s, _, _, _ in inspections],
        "requirement_intake": (
            "legacy_free_text" if resolved_requirement.used_legacy else "canonical_code"
        ),
        "period_intake": (
            "legacy_period_code" if resolved_period.used_legacy else "canonical_period_key"
        ),
        "validation_events": aggregated_event_types,
        "multi_file_upload": True,
    }
    if supersedes_submission is not None:
        audit_metadata["supersedes_submission_id"] = supersedes_submission.id
    if extra_audit_metadata:
        audit_metadata.update(extra_audit_metadata)

    add_audit_event(
        db,
        action="submission.created",
        entity_type="submission",
        entity_id=submission.id,
        after={
            "client_id": client.id,
            "vendor_id": vendor.id,
            "period_id": resolved_period.period.id,
            "requirement_id": resolved_requirement.requirement.id,
            "requirement_code": resolved_requirement.canonical_code,
            "period_key": resolved_period.canonical_period_key,
            "status": overall_status.value,
            "supersedes_submission_id": (
                supersedes_submission.id if supersedes_submission is not None else None
            ),
            "document_count": len(documents_payload),
        },
        metadata=audit_metadata,
    )

    if supersedes_submission is not None:
        add_audit_event(
            db,
            action="submission.replacement_linked",
            entity_type="submission",
            entity_id=submission.id,
            metadata={
                "previous_submission_id": supersedes_submission.id,
                "new_submission_id": submission.id,
                "requirement_code": resolved_requirement.canonical_code,
                "period_key": resolved_period.canonical_period_key,
                "workspace_id": (extra_audit_metadata or {}).get("workspace_id"),
                "previous_status": supersedes_submission.status,
                "document_count": len(documents_payload),
            },
        )

    db.commit()

    return MultiSubmissionResponse(
        submission_id=submission.id,
        status=overall_status.value,
        documents=documents_payload,
        support=SupportInfo(
            whatsapp_url=settings.SUPPORT_WHATSAPP_URL or None,
            qr_placeholder_url=settings.SUPPORT_QR_PLACEHOLDER_URL or None,
            message="Contacta soporte si no sabes qué documento subir o detectas una alerta.",
        ),
        message=submission_message(overall_status),
    )
