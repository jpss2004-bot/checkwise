"""Submission-time orchestration: PDF gating, entity get-or-create,
status derivation, and the validation-event timeline written on intake.

These helpers used to live as private functions inside ``api/v1/endpoints.py``.
They were extracted so the router stays a thin shell over business logic and
the same helpers can be reused by future surfaces (importer, batch jobs,
re-validation flows).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from fastapi import BackgroundTasks, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.constants.institutions import INSTITUTION_LABELS, Institution
from app.constants.statuses import DocumentStatus
from app.core.config import settings
from app.db.session import SessionLocal
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
    MatchFeedback,
    MultiSubmissionResponse,
    SubmissionResponse,
    SupportInfo,
    ValidationEventSummary,
)
from app.services.audit_log import add_audit_event
from app.services.client_notifications import (
    notify_metadata_ready,
    notify_provider_uploaded,
)
from app.services.document_analysis.shadow_runner import run_shadow_analysis
from app.services.document_forensics import (
    analyze_pdf_forensics,
    rollup_authenticity_risk,
    severity_rank,
)
from app.services.document_intelligence import (
    RFC_ALIGNMENT_ABSENT,
    DocumentSignals,
    analyze_document_text,
)
from app.services.document_verification import extract_verification
from app.services.metadata_export import export_metadata_table_after_upload
from app.services.pdf_validation import (
    PdfInspectionResult,
    inspect_pdf,  # noqa: F401 — re-exported for legacy tools/scripts
    inspect_pdf_with_ocr_fallback,
)
from app.services.prevalidation import build_initial_validations
from app.services.provider_notifications import notify_provider_of_validation_complete
from app.services.requirement_service import ResolvedPeriod, ResolvedRequirement
from app.services.storage import StoredFile, get_storage_service
from app.services.validation_events import add_validation_event

logger = logging.getLogger(__name__)

PREVALIDATION_EVIDENCE_METADATA_KEY = "_prevalidation_evidence"


def _authenticity_columns_fail_open(
    path: Path,
    *,
    period_key: str | None,
    pdf_metadata: dict | None,
    detected_institution: str | None,
    extracted_text: str | None,
) -> tuple[str | None, list | None, dict | None, dict | None]:
    """Run the authenticity analyzer + QR/folio extractor; NEVER block.

    Returns the ``(authenticity_risk, risk_reasons, forensics,
    verification)`` quadruple for the :class:`DocumentInspection` row.
    Phase A forensics and Phase B verification each fail open on their
    own; their named reasons are MERGED (sorted high→info) and the
    verdict re-rolled through the shared
    ``rollup_authenticity_risk`` so one phase's medium finding elevates
    the same single reviewer-facing verdict. When NEITHER pass produced
    a result the verdict stays NULL ("sin analizar").

    Both analyzers are contracted to swallow everything, but intake
    mirrors the other fail-open steps (OCR, metadata export) with its
    own belt-and-suspenders try/except: on any failure all columns stay
    NULL and the upload proceeds untouched.
    """
    try:
        forensics_result = analyze_pdf_forensics(
            path, period_key=period_key, pdf_metadata=pdf_metadata
        )
        verification_result = extract_verification(
            path,
            detected_institution=detected_institution,
            extracted_text=extracted_text,
        )
        merged_reasons = sorted(
            [*forensics_result.reasons, *verification_result.reasons],
            key=lambda reason: severity_rank(reason.severity),
        )
        if forensics_result.analyzed or verification_result.analyzed:
            risk: str | None = rollup_authenticity_risk(merged_reasons)
        else:
            risk = None
        return (
            risk,
            [reason.as_dict() for reason in merged_reasons],
            forensics_result.forensics or None,
            verification_result.payload or None,
        )
    except Exception:  # noqa: BLE001 — analysis errors never block intake.
        logger.exception("Authenticity analysis failed open (file=%s)", path)
        return None, None, None, None


def _raw_metadata_with_evidence(
    pdf_metadata: dict | None,
    document_signals: DocumentSignals,
) -> dict:
    raw = dict(pdf_metadata or {})
    if document_signals.evidence:
        raw[PREVALIDATION_EVIDENCE_METADATA_KEY] = document_signals.evidence
    return raw


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

    # FILE-1 — content-sniff the magic bytes. Extension + MIME are both
    # client-controlled and trivially spoofable, so a genuine PDF must
    # also carry the ``%PDF-`` signature near the start of the file. This
    # blocks HTML / SVG / script / binary payloads renamed ``.pdf`` from
    # ever being persisted as "evidence" (they otherwise ride into the
    # expediente / audit ZIPs that clients and auditors download). The
    # PDF spec tolerates a little leading junk before the header, so we
    # scan the first 1 KiB rather than demanding the signature at offset
    # 0. The stream is rewound to 0 so the downstream save reads it whole.
    try:
        head = file.file.read(1024)
        file.file.seek(0)
    except Exception:  # noqa: BLE001 — unreadable stream; inspect_pdf backstop still routes non-PDFs to review
        head = b""
    if head and b"%PDF-" not in head:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo no es un PDF válido (no contiene la firma %PDF-).",
        )


# Phase 1 — confidence-aware intake routing. Pre-Phase-1 the function
# ignored ``requirement_match_confidence`` entirely: a 0.05-confidence
# document and a 0.95-confidence document both landed in
# ``pendiente_revision``, and any mismatch — however weak — surfaced as
# ``posible_mismatch`` to the provider. The thresholds below are the
# initial calibration; Phase 2 fixtures will let us retune them with
# evidence instead of intuition.
#
# Bucketing (no mismatch, valid PDF):
#   confidence >= 0.7  → PREVALIDADO          (auto-cleared for review)
#   confidence >= 0.4  → PENDIENTE_REVISION   (today's default)
#   confidence <  0.4  → PENDIENTE_REVISION   (queue, do not auto-clear)
# Bucketing (mismatch reason set):
#   confidence >= 0.5  → POSIBLE_MISMATCH     (surface to provider)
#   confidence <  0.5  → PENDIENTE_REVISION   (route to human review,
#                                             don't alarm the provider)
_PREVALIDATION_CONFIDENCE_FLOOR = 0.7
_MISMATCH_CONFIDENCE_FLOOR = 0.5

# Phase C — provider-facing soft match feedback. Below this
# ``requirement_match_confidence`` the upload response carries a
# ``MatchFeedback`` warning ("this doesn't look like the requested
# document — double-check the attachment"). Deliberately conservative:
# prod calibration showed the intake heuristic separates well at >= 0.5,
# so only quite-low scores warrant bothering the provider. An explicit
# ``mismatch_reason`` from DocumentSignals always triggers the feedback
# regardless of the score. The upload is NEVER blocked either way — it
# lands in the review queue exactly as before.
_MATCH_FEEDBACK_CONFIDENCE_FLOOR = 0.35


def build_match_feedback(
    document_signals: DocumentSignals,
    *,
    requirement_name: str,
) -> MatchFeedback | None:
    """Build the Phase C soft, match-only warning for the upload response.

    Returns ``None`` when there is no match concern. MATCH-ONLY by
    contract: this function reads exclusively the requirement-match
    signals (``mismatch_reason`` / ``requirement_match_confidence``).
    Authenticity / forensics / QR risk signals must never feed a
    provider-facing message — a risky document routes silently to
    review (anti-tipping contract, see ``MatchFeedback``).
    """
    confidence = document_signals.requirement_match_confidence
    next_steps = (
        "Verifica que adjuntaste el documento correcto; si es el correcto, "
        "no necesitas hacer nada — pasará a revisión normal."
    )
    if document_signals.mismatch_reason:
        # ``mismatch_reason`` is already plain provider-safe Spanish
        # ("El documento parece X, pero…"); reuse it and add the
        # requested-document name + the reassuring next step.
        warning = (
            f"{document_signals.mismatch_reason} "
            f"El documento solicitado es «{requirement_name}». {next_steps}"
        )
        return MatchFeedback(
            confidence=confidence,
            warning_es=warning,
            expected_label=requirement_name,
        )
    if confidence is not None and confidence < _MATCH_FEEDBACK_CONFIDENCE_FLOOR:
        warning = (
            f"Este archivo no parece ser «{requirement_name}». {next_steps}"
        )
        return MatchFeedback(
            confidence=confidence,
            warning_es=warning,
            expected_label=requirement_name,
        )
    return None


def status_from_inspection(
    pdf_inspection: PdfInspectionResult,
    document_signals: DocumentSignals,
) -> DocumentStatus:
    """Derive the initial submission status from PDF inspection + signals."""
    if not pdf_inspection.is_pdf or pdf_inspection.is_corrupt or pdf_inspection.is_encrypted:
        return DocumentStatus.REQUIERE_ACLARACION

    confidence = document_signals.requirement_match_confidence or 0.0
    # An ABSENT RFC (none detected) escalates to clarification. A concrete
    # RFC *mismatch* is deliberately advisory: it caps requirement_match
    # confidence (in document_intelligence) so the doc lands in human review
    # without a provider-facing "wrong company" accusation that RFC OCR noise
    # / homoclave variants could make wrongly. See
    # test_document_intelligence_rfc::test_rfc_mismatch_caps_confidence_*.
    if (
        document_signals.expected_rfc
        and document_signals.rfc_alignment == RFC_ALIGNMENT_ABSENT
    ):
        return DocumentStatus.REQUIERE_ACLARACION

    if document_signals.mismatch_reason:
        if confidence >= _MISMATCH_CONFIDENCE_FLOOR:
            return DocumentStatus.POSIBLE_MISMATCH
        return DocumentStatus.PENDIENTE_REVISION

    if confidence >= _PREVALIDATION_CONFIDENCE_FLOOR:
        return DocumentStatus.PREVALIDADO
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

    # Phase 3 — explicit OCR-fired audit event. Emitted only when
    # ``inspect_pdf_with_ocr_fallback`` actually invoked Document AI
    # (scanned PDF + configured client). Result is ``pass`` when OCR
    # returned usable text, ``fail`` when the call errored, ``warning``
    # when OCR ran but returned nothing. ``processor_name`` is included
    # in the payload so a reviewer can answer "which Document AI
    # processor produced this text" from the timeline alone, without
    # cross-referencing runtime config. Provider-facing UI never
    # surfaces this event — it's reviewer/auditor evidence only.
    if pdf_inspection.ocr_attempted:
        ocr_chars = pdf_inspection.ocr_text_char_count or 0
        if pdf_inspection.ocr_error:
            ocr_result = "fail"
            ocr_severity = "warning"
            ocr_message = (
                "OCR no pudo procesar el documento; el revisor humano "
                "lo evaluará manualmente."
            )
        elif ocr_chars > 0:
            ocr_result = "pass"
            ocr_severity = "info"
            ocr_message = "OCR extrajo texto del documento escaneado."
        else:
            ocr_result = "warning"
            ocr_severity = "warning"
            ocr_message = (
                "OCR procesó el documento pero no extrajo texto utilizable."
            )
        events.append(
            add_validation_event(
                db,
                submission_id=submission_id,
                document_id=document_id,
                event_type="ocr_performed",
                rule_code="ocr_fallback",
                result=ocr_result,
                severity=ocr_severity,
                message=ocr_message,
                payload={
                    "ocr_text_char_count": ocr_chars,
                    "ocr_error": pdf_inspection.ocr_error,
                    "processor_name": pdf_inspection.ocr_processor_name,
                },
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

# Friendly 409 surfaced when two near-simultaneous first-time uploads to
# the same evidence slot both try to insert a *genesis* submission
# (``supersedes_submission_id IS NULL``) and collide on the partial
# unique index ``ux_submissions_active_slot`` (migration 0035). Without a
# catch the loser's flush raises ``IntegrityError`` → unhandled 500 +
# poisoned session. See ``_add_genesis_submission`` below.
_DUPLICATE_SLOT_DETAIL = (
    "Otra carga para este proveedor, requisito y periodo se registró al "
    "mismo tiempo. Actualiza la página y, si ya aparece el documento, "
    "envíalo como reemplazo."
)


def _add_genesis_submission(db: Session, submission: Submission) -> None:
    """Insert a genesis submission, converting a slot-collision to a 409.

    Concurrency hardening (audit 2026-06-21, Batch 6): the genesis insert
    (``supersedes_submission_id IS NULL``) is guarded by the Postgres
    partial unique index ``ux_submissions_active_slot`` — one active
    genesis per ``(client_id, vendor_id, requirement_code,
    coalesce(period_key, ''))``. Two concurrent first-time uploads to the
    same slot both pass the wizard duplicate-check, both ``add`` a genesis
    row, and the second ``flush`` raises ``IntegrityError``. We run the
    insert in a ``SAVEPOINT`` so the failed flush rolls back only the
    nested transaction (the outer transaction / session stays usable),
    then re-raise as the existing-style 409 instead of a 500.

    Non-genesis rows (``supersedes_submission_id`` set) are NOT covered by
    the index, so they never collide here — the savepoint is a harmless
    no-op for them. On SQLite the index is intentionally absent (see
    ``entities.Submission``), so no ``IntegrityError`` is raised and the
    savepoint commits cleanly: single-threaded and test behavior is
    identical to the prior ``db.add``/``db.flush``.
    """
    try:
        with db.begin_nested():
            db.add(submission)
            db.flush()
    except IntegrityError as exc:
        # Only the active-slot collision maps to a friendly 409; any other
        # integrity failure is a genuine bug and should surface loudly.
        if "ux_submissions_active_slot" not in str(exc.orig):
            raise
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_DUPLICATE_SLOT_DETAIL,
        ) from exc


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
    background_tasks: BackgroundTasks | None = None,
    existing_submission: Submission | None = None,
    existing_document: Document | None = None,
) -> SubmissionResponse:
    """Run the shared back-half of a documentary intake.

    When ``existing_submission`` / ``existing_document`` are supplied
    (the async portal path), this transitions an already-persisted
    ``RECIBIDO`` receipt to its derived status and attaches every
    analysis side-effect to it — instead of creating new rows. The
    legacy synchronous path passes neither and creates the rows in one
    shot at the derived status. Everything after status derivation is
    identical for both paths.

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
    # Duplicate detection ignores the row this very upload just created:
    # the async portal path persists the Document (at ``recibido``) before
    # this finalize pass runs, so a document must never be flagged as a
    # duplicate of itself.
    #
    # Tenant isolation: the sha256 lookup is scoped to THIS client + vendor
    # via the Document → Submission join. An unscoped global match would
    # flag two unrelated tenants who upload the byte-identical public form
    # as duplicates of each other (cross-tenant file-existence leak + a
    # spurious review). A byte-identical re-upload only counts within the
    # same tenant slot.
    duplicate_query = (
        select(Document)
        .join(Submission, Submission.id == Document.submission_id)
        .where(
            Document.sha256 == stored_file.sha256,
            Submission.client_id == client.id,
            Submission.vendor_id == vendor.id,
        )
    )
    if existing_document is not None:
        duplicate_query = duplicate_query.where(Document.id != existing_document.id)
    duplicate = db.scalar(duplicate_query.limit(1))

    pdf_inspection = inspect_pdf_with_ocr_fallback(stored_file.path)
    document_signals = analyze_document_text(
        pdf_inspection.text_sample,
        expected_requirement=resolved_requirement.canonical_name,
        expected_institution=institution.code,
        expected_period=period_code,
        expected_rfc=vendor.rfc,
        expected_vendor_name=vendor.name,
        expected_client_name=client.name,
        expected_client_rfc=client.rfc,
    )
    final_status = status_from_inspection(pdf_inspection, document_signals)

    if existing_submission is not None and existing_document is not None:
        # Async portal path — transition the pre-persisted RECIBIDO
        # receipt to the derived status. ``prior_status`` (recibido)
        # becomes the ``from_status`` of the status-history row below.
        prior_status: str | None = existing_submission.status
        submission = existing_submission
        document = existing_document
        submission.status = final_status.value
        document.status = final_status.value
    else:
        # Legacy synchronous path — create the rows at the derived status.
        prior_status = None
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
        # SAVEPOINT-guarded insert: a concurrent first-time upload to the
        # same slot collides on ux_submissions_active_slot → friendly 409
        # instead of a 500. No-op for non-genesis rows and on SQLite.
        _add_genesis_submission(db, submission)

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

    # Phase A forensics + Phase B QR/folio verification. Reviewer-facing
    # verdict only: never alters statuses, validations or prevalidation
    # signals.
    authenticity_risk, risk_reasons, forensics_payload, verification_payload = (
        _authenticity_columns_fail_open(
            stored_file.path,
            period_key=resolved_period.canonical_period_key,
            pdf_metadata=pdf_inspection.metadata,
            detected_institution=document_signals.detected_institution,
            extracted_text=pdf_inspection.text_sample,
        )
    )

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
        expected_rfc=document_signals.expected_rfc,
        rfc_alignment=document_signals.rfc_alignment,
        detected_dates=document_signals.detected_dates,
        period_mentions=document_signals.period_mentions,
        requirement_match_confidence=document_signals.requirement_match_confidence,
        mismatch_reason=document_signals.mismatch_reason,
        inspection_error=pdf_inspection.error,
        raw_metadata=_raw_metadata_with_evidence(
            pdf_inspection.metadata,
            document_signals,
        ),
        authenticity_risk=authenticity_risk,
        risk_reasons=risk_reasons,
        forensics=forensics_payload,
        verification=verification_payload,
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
            from_status=prior_status,
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

    metadata_export = export_metadata_table_after_upload(
        stored_file=stored_file,
        client=client,
        vendor=vendor,
        contract=contract,
        institution=institution,
        resolved_requirement=resolved_requirement,
        resolved_period=resolved_period,
        document=document,
        detected_document_type=document_signals.detected_document_type,
        # Reuse the intake inspection + classifier signals so the metadata
        # export doesn't re-open the PDF and re-run analyze_document_text.
        pdf_inspection=pdf_inspection,
        document_signals=document_signals,
    )
    metadata_export_event = add_validation_event(
        db,
        submission_id=submission.id,
        document_id=document.id,
        event_type="metadata_table_exported",
        rule_code="metadata_table_export",
        result=metadata_export.status,
        severity="info" if metadata_export.status == "completed" else "warning",
        message=(
            "Metadata XLSX generado automáticamente."
            if metadata_export.status == "completed"
            else "No se pudo generar el Metadata XLSX automáticamente."
        ),
        payload={
            "document_type_code": metadata_export.document_type_code,
            "output_path": metadata_export.output_path,
            "latest_path": metadata_export.latest_path,
            "master_path": metadata_export.master_path,
            "reason": metadata_export.reason,
        },
        actor_type="system",
    )
    validation_events.append(metadata_export_event)

    notify_provider_uploaded(db, submission=submission, vendor=vendor)
    if metadata_export.status == "completed":
        notify_metadata_ready(
            db,
            submission=submission,
            vendor=vendor,
            master_path=metadata_export.master_path,
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
        "metadata_export": {
            "status": metadata_export.status,
            "document_type_code": metadata_export.document_type_code,
            "output_path": metadata_export.output_path,
            "latest_path": metadata_export.latest_path,
            "reason": metadata_export.reason,
        },
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

    # Phase 2 — schedule the background shadow analysis (Claude) after
    # the intake transaction has committed so the provider's wait time
    # is unaffected. The runner opens its own DB session and writes to
    # ``DocumentInspection.shadow_*``; failures never reach the caller.
    # When ``background_tasks`` is None (e.g., a test calling the helper
    # directly without a request scope) the shadow analysis is simply
    # skipped — the heuristic-driven row is already complete.
    if background_tasks is not None:
        background_tasks.add_task(
            run_shadow_analysis,
            document_id=document.id,
            submission_id=submission.id,
            pdf_path=str(stored_file.path),
            requirement_code=resolved_requirement.canonical_code,
            requirement_name=resolved_requirement.canonical_name,
            institution_code=institution.code,
            period_code=period_code,
            org_id=client.id,
            # Phase C — alto/crítico requirements always qualify for the
            # escalation tier (bounded by the escalation daily cap).
            requirement_risk_level=resolved_requirement.requirement.risk_level,
            # Phase 0 — situation context so the LLM can reason about
            # whether the document actually belongs to the expected
            # provider (the regex path already had this).
            expected_provider_rfc=vendor.rfc,
            expected_provider_name=vendor.name,
            expected_client_name=client.name,
            expected_client_rfc=client.rfc,
        )

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
            expected_rfc=document_signals.expected_rfc,
            rfc_alignment=document_signals.rfc_alignment,
            identity_alignment=document_signals.identity_alignment,
            detected_dates=document_signals.detected_dates,
            period_mentions=document_signals.period_mentions,
            period_alignment=document_signals.period_alignment,
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
        match_feedback=build_match_feedback(
            document_signals,
            requirement_name=resolved_requirement.canonical_name,
        ),
    )


@dataclass(frozen=True)
class IntakeReceipt:
    """Lean acknowledgement returned the instant an upload is persisted.

    The heavy validation pipeline (OCR, forensics, status derivation,
    metadata export) runs afterward in
    ``finalize_intake_submission_background``; this receipt is what the
    provider's request returns so the wizard can confirm "recibido"
    without waiting on any of it.
    """

    submission_id: str
    document_id: str
    status: str
    sha256: str
    storage_key: str


def persist_intake_receipt(
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
    comments: str | None,
    submitted_by: str,
    intake_source: str,
    supersedes_submission: Submission | None = None,
    extra_audit_metadata: dict | None = None,
) -> IntakeReceipt:
    """Persist a pre-validation intake receipt and commit immediately.

    The provider's upload request returns the moment this commits. The
    row starts at ``RECIBIDO`` ("En revisión") so it shows on the
    dashboard / calendar / submissions right away while
    ``finalize_intake_submission_background`` runs the heavy pipeline and
    transitions it to its derived status.
    """
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
        status=DocumentStatus.RECIBIDO.value,
        comments=comments,
        submitted_by=submitted_by,
        supersedes_submission_id=(
            supersedes_submission.id if supersedes_submission is not None else None
        ),
    )
    # SAVEPOINT-guarded insert (async receipt path). Two near-simultaneous
    # first-time uploads to the same slot both persist a genesis RECIBIDO
    # receipt; the loser collides on ux_submissions_active_slot and gets a
    # friendly 409 instead of a 500 + poisoned session. Non-genesis
    # (replacement) receipts are exempt from the index and pass through.
    _add_genesis_submission(db, submission)

    document = Document(
        submission_id=submission.id,
        storage_key=stored_file.storage_key,
        original_filename=stored_file.original_filename,
        mime_type=stored_file.mime_type,
        size_bytes=stored_file.size_bytes,
        sha256=stored_file.sha256,
        status=DocumentStatus.RECIBIDO.value,
    )
    db.add(document)
    db.flush()

    db.add(
        DocumentStatusHistory(
            document_id=document.id,
            submission_id=submission.id,
            from_status=None,
            to_status=DocumentStatus.RECIBIDO.value,
            reason="Carga recibida; validación en proceso.",
            actor="system",
        )
    )

    audit_metadata: dict = {
        "source": "native_intake",
        "intake_source": intake_source,
        "storage_key": stored_file.storage_key,
        "sha256": stored_file.sha256,
        "phase": "receipt",
    }
    if supersedes_submission is not None:
        audit_metadata["supersedes_submission_id"] = supersedes_submission.id
    if extra_audit_metadata:
        audit_metadata.update(extra_audit_metadata)

    add_audit_event(
        db,
        action="submission.received",
        entity_type="submission",
        entity_id=submission.id,
        after={
            "client_id": client.id,
            "vendor_id": vendor.id,
            "requirement_code": resolved_requirement.canonical_code,
            "period_key": resolved_period.canonical_period_key,
            "status": DocumentStatus.RECIBIDO.value,
        },
        metadata=audit_metadata,
    )

    db.commit()

    return IntakeReceipt(
        submission_id=submission.id,
        document_id=document.id,
        status=DocumentStatus.RECIBIDO.value,
        sha256=stored_file.sha256,
        storage_key=stored_file.storage_key,
    )


def finalize_intake_submission_background(
    *,
    submission_id: str,
    storage_key: str,
    intake_source: str,
) -> None:
    """Run the heavy intake pipeline for a ``RECIBIDO`` receipt, off-request.

    Mirrors ``run_shadow_analysis``: queued as a FastAPI BackgroundTask
    (and re-run by the reconcile cron), opens its own DB session, takes
    only primitive ids, and NEVER raises into the worker. It loads the
    receipt rows, re-materializes the PDF from durable storage (so it
    works even after the request's temp file is gone — e.g. from the
    cron), re-resolves requirement/period (idempotent get-or-create),
    runs ``finalize_intake_submission`` against the existing rows to
    transition ``recibido → derived`` and attach every analysis
    side-effect, emits the provider verdict notification, then runs
    shadow analysis inline.

    Idempotent: a receipt already past ``RECIBIDO`` (finalized by a prior
    run, or by the inline task racing the reconcile cron) is skipped.
    """
    from app.models import ProviderWorkspace
    from app.services.requirement_service import resolve_period, resolve_requirement

    db = SessionLocal()
    materialized_path: Path | None = None
    shadow_args: dict | None = None
    try:
        submission = db.get(Submission, submission_id)
        if submission is None:
            logger.warning(
                "Intake finalize: submission %s not found; skipping.", submission_id
            )
            return
        if submission.status != DocumentStatus.RECIBIDO.value:
            # Already finalized (inline task + reconcile cron raced, or a
            # reviewer already acted). Nothing to do.
            return
        document = submission.documents[0] if submission.documents else None
        if document is None:
            logger.warning(
                "Intake finalize: submission %s has no document; skipping.",
                submission_id,
            )
            return

        client = submission.client
        vendor = submission.vendor
        contract = submission.contract
        institution = submission.institution

        resolved_requirement = resolve_requirement(
            db,
            requirement_code=submission.requirement_code,
            requirement_name=(
                submission.requirement.name if submission.requirement else ""
            ),
            institution_id=institution.id,
            institution_code=institution.code,
            load_type=submission.load_type,
        )
        period_code = (
            submission.period.code if submission.period else submission.period_key
        )
        resolved_period = resolve_period(
            db,
            period_key=submission.period_key,
            period_code=period_code,
            load_type=submission.load_type,
        )

        storage = get_storage_service()
        materialized_path = storage.open_for_read(storage_key)
        stored_file = StoredFile(
            storage_key=storage_key,
            path=materialized_path,
            original_filename=document.original_filename,
            mime_type=document.mime_type,
            size_bytes=document.size_bytes or 0,
            sha256=document.sha256,
            extension=Path(document.original_filename or "").suffix.lower(),
        )

        supersedes = (
            db.get(Submission, submission.supersedes_submission_id)
            if submission.supersedes_submission_id
            else None
        )
        workspace = db.scalar(
            select(ProviderWorkspace).where(
                ProviderWorkspace.client_id == submission.client_id,
                ProviderWorkspace.vendor_id == submission.vendor_id,
            )
        )

        response = finalize_intake_submission(
            db,
            stored_file=stored_file,
            client=client,
            vendor=vendor,
            contract=contract,
            institution=institution,
            resolved_requirement=resolved_requirement,
            resolved_period=resolved_period,
            load_type=submission.load_type,
            period_code=period_code,
            comments=submission.comments,
            submitted_by=submission.submitted_by,
            intake_source=intake_source,
            extra_audit_metadata=(
                {"workspace_id": workspace.id} if workspace is not None else None
            ),
            supersedes_submission=supersedes,
            background_tasks=None,
            existing_submission=submission,
            existing_document=document,
        )

        # Provider verdict notification — the provider's own-upload result.
        # Lifecycle status + the soft requirement-match warning only (the
        # same anti-tipping contract the response honors; ``match_feedback``
        # carries no authenticity/forensic signal). Skipped silently when no
        # workspace matches (legacy / partial seed data).
        notify_provider_of_validation_complete(
            db,
            submission=submission,
            workspace_id=workspace.id if workspace is not None else None,
            match_warning=(
                response.match_feedback.warning_es
                if response.match_feedback is not None
                else None
            ),
        )
        db.commit()

        # Capture the shadow-analysis args while the session + file are
        # live; the call runs after this block so a shadow failure can
        # never roll back the finalize commit above.
        shadow_args = {
            "document_id": document.id,
            "submission_id": submission.id,
            "pdf_path": str(materialized_path),
            "requirement_code": resolved_requirement.canonical_code,
            "requirement_name": resolved_requirement.canonical_name,
            "institution_code": institution.code,
            "period_code": period_code,
            "org_id": client.id,
            "requirement_risk_level": resolved_requirement.requirement.risk_level,
            "expected_provider_rfc": vendor.rfc,
            "expected_provider_name": vendor.name,
            "expected_client_name": client.name,
            "expected_client_rfc": client.rfc,
        }
    except Exception:  # noqa: BLE001 — a background failure must never crash the worker
        logger.exception("Intake finalize failed for submission %s", submission_id)
        db.rollback()
        shadow_args = None
    finally:
        db.close()

    # Shadow analysis (own session, never raises) runs AFTER the finalize
    # commit and before temp cleanup so the materialized PDF is still
    # present. Mirrors the synchronous path's scheduled shadow run.
    if shadow_args is not None:
        run_shadow_analysis(**shadow_args)

    # Clean up the S3 temp download; the local backend hands back the
    # durable path, which must never be unlinked.
    if (
        materialized_path is not None
        and (settings.STORAGE_BACKEND or "local").strip().lower() == "s3"
    ):
        try:
            materialized_path.unlink(missing_ok=True)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Stage 2.7-b — Multi-document submission orchestration
# ---------------------------------------------------------------------------
#
# The data model already supports 1 Submission → N Documents
# (``Submission.documents`` 1:N from ``apps/api/app/models/entities.py:222``).
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
#   REQUIERE_ACLARACION  →  POSIBLE_MISMATCH  →  PENDIENTE_REVISION  →  PREVALIDADO


_SUBMISSION_STATUS_PRIORITY: dict[str, int] = {
    DocumentStatus.REQUIERE_ACLARACION.value: 4,
    DocumentStatus.POSIBLE_MISMATCH.value: 3,
    DocumentStatus.PENDIENTE_REVISION.value: 2,
    DocumentStatus.PREVALIDADO.value: 1,
}


def _worst_status(statuses: list[DocumentStatus]) -> DocumentStatus:
    """Return the most actionable (= highest priority) status from the batch.

    Returns ``PENDIENTE_REVISION`` for an empty input — never ``PREVALIDADO``,
    because an empty batch is not evidence of a clean upload.
    """
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
    background_tasks: BackgroundTasks | None = None,
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
        # Tenant isolation: scope the sha256 lookup to THIS client + vendor
        # via the Document → Submission join so a byte-identical upload from
        # an unrelated tenant never flags this batch as a duplicate (and
        # vice-versa). See the single-file path for the full rationale.
        duplicate = db.scalar(
            select(Document)
            .join(Submission, Submission.id == Document.submission_id)
            .where(
                Document.sha256 == stored.sha256,
                Submission.client_id == client.id,
                Submission.vendor_id == vendor.id,
            )
            .limit(1)
        )
        pdf_inspection = inspect_pdf_with_ocr_fallback(stored.path)
        document_signals = analyze_document_text(
            pdf_inspection.text_sample,
            expected_requirement=resolved_requirement.canonical_name,
            expected_institution=institution.code,
            expected_period=period_code,
            expected_rfc=vendor.rfc,
            expected_vendor_name=vendor.name,
            expected_client_name=client.name,
            expected_client_rfc=client.rfc,
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
    # Master-table paths for documents whose metadata export completed —
    # used to fire one ``notify_metadata_ready`` after the loop.
    metadata_master_paths: list[str | None] = []
    shadow_batch: list[tuple[str, str]] = []  # (document_id, pdf_path) for post-commit scheduling
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
        shadow_batch.append((document.id, str(stored.path)))

        # Phase A forensics + Phase B QR/folio verification (reviewer-
        # facing verdict only; see the single-file site for the
        # fail-open contract).
        authenticity_risk, risk_reasons, forensics_payload, verification_payload = (
            _authenticity_columns_fail_open(
                stored.path,
                period_key=resolved_period.canonical_period_key,
                pdf_metadata=pdf_inspection.metadata,
                detected_institution=document_signals.detected_institution,
                extracted_text=pdf_inspection.text_sample,
            )
        )

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
            expected_rfc=document_signals.expected_rfc,
            rfc_alignment=document_signals.rfc_alignment,
            detected_dates=document_signals.detected_dates,
            period_mentions=document_signals.period_mentions,
            requirement_match_confidence=document_signals.requirement_match_confidence,
            mismatch_reason=document_signals.mismatch_reason,
            inspection_error=pdf_inspection.error,
            raw_metadata=_raw_metadata_with_evidence(
                pdf_inspection.metadata,
                document_signals,
            ),
            authenticity_risk=authenticity_risk,
            risk_reasons=risk_reasons,
            forensics=forensics_payload,
            verification=verification_payload,
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

        # Metadata XLSX / master row — mirrors the single-file
        # ``finalize_intake_submission`` path so batch-uploaded documents
        # are visible on /client/metadata. Each document uses ITS OWN
        # inspection + classifier signals (not the batch's), reusing them
        # so the export never re-opens the PDF or re-runs the classifier.
        metadata_export = export_metadata_table_after_upload(
            stored_file=stored,
            client=client,
            vendor=vendor,
            contract=contract,
            institution=institution,
            resolved_requirement=resolved_requirement,
            resolved_period=resolved_period,
            document=document,
            detected_document_type=document_signals.detected_document_type,
            pdf_inspection=pdf_inspection,
            document_signals=document_signals,
        )
        metadata_export_event = add_validation_event(
            db,
            submission_id=submission.id,
            document_id=document.id,
            event_type="metadata_table_exported",
            rule_code="metadata_table_export",
            result=metadata_export.status,
            severity="info" if metadata_export.status == "completed" else "warning",
            message=(
                "Metadata XLSX generado automáticamente."
                if metadata_export.status == "completed"
                else "No se pudo generar el Metadata XLSX automáticamente."
            ),
            payload={
                "document_type_code": metadata_export.document_type_code,
                "output_path": metadata_export.output_path,
                "latest_path": metadata_export.latest_path,
                "master_path": metadata_export.master_path,
                "reason": metadata_export.reason,
            },
            actor_type="system",
        )
        validation_events.append(metadata_export_event)
        if metadata_export.status == "completed":
            metadata_master_paths.append(metadata_export.master_path)

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
                    expected_rfc=document_signals.expected_rfc,
                    rfc_alignment=document_signals.rfc_alignment,
                    identity_alignment=document_signals.identity_alignment,
                    detected_dates=document_signals.detected_dates,
                    period_mentions=document_signals.period_mentions,
                    period_alignment=document_signals.period_alignment,
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
                match_feedback=build_match_feedback(
                    document_signals,
                    requirement_name=resolved_requirement.canonical_name,
                ),
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

    notify_provider_uploaded(
        db,
        submission=submission,
        vendor=vendor,
        document_count=len(documents_payload),
    )

    # Fire one metadata-ready notification for the batch when at least one
    # document's export completed — all documents append to the same
    # client-wide master, so a single notification (using the last
    # completed master path) mirrors the single-file path's intent.
    if metadata_master_paths:
        notify_metadata_ready(
            db,
            submission=submission,
            vendor=vendor,
            master_path=metadata_master_paths[-1],
        )

    db.commit()

    # Phase 2 — schedule shadow analysis per attached document after
    # the multi-doc transaction commits. Each document gets its own
    # background run so a failure on one does not affect the others.
    # The runner persists ``shadow_*`` columns on each
    # DocumentInspection row independently; the user-visible flow is
    # unchanged.
    if background_tasks is not None:
        for doc_id, pdf_path in shadow_batch:
            background_tasks.add_task(
                run_shadow_analysis,
                document_id=doc_id,
                submission_id=submission.id,
                pdf_path=pdf_path,
                requirement_code=resolved_requirement.canonical_code,
                requirement_name=resolved_requirement.canonical_name,
                institution_code=institution.code,
                period_code=period_code,
                org_id=client.id,
                # Phase C — alto/crítico requirements always qualify for
                # the escalation tier (bounded by the escalation cap).
                requirement_risk_level=resolved_requirement.requirement.risk_level,
                # Phase 0 — situation context (see single-submission path).
                expected_provider_rfc=vendor.rfc,
                expected_provider_name=vendor.name,
                expected_client_name=client.name,
                expected_client_rfc=client.rfc,
            )

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
