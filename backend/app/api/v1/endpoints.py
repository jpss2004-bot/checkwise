"""Core API: health, catalogs, and the native-intake submission endpoint.

The intake helpers (entity get-or-create, status derivation, validation
event timeline, requirement + period resolution) live in
``app.services.submission_service`` and ``app.services.requirement_service``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.constants.statuses import DocumentStatus
from app.core.catalogs import (
    DOCUMENT_STATUSES,
    INSTITUTIONS,
    LOAD_TYPES,
    REQUIREMENT_EXAMPLES,
    VALIDATION_RULES,
)
from app.core.config import settings
from app.db.session import get_db
from app.models import Document, DocumentInspection, DocumentStatusHistory, Submission, Validation
from app.schemas.catalogs import CatalogResponse
from app.schemas.submissions import (
    DocumentInspectionSummary,
    DocumentSignalsSummary,
    SubmissionResponse,
    SupportInfo,
    ValidationEventSummary,
)
from app.services.audit_log import add_audit_event
from app.services.document_intelligence import analyze_document_text
from app.services.pdf_validation import inspect_pdf
from app.services.prevalidation import build_initial_validations
from app.services.requirement_service import resolve_period, resolve_requirement
from app.services.storage import LocalStorageService
from app.services.submission_service import (
    add_native_intake_events,
    assert_pdf_upload,
    get_or_create_client,
    get_or_create_contract,
    get_or_create_institution,
    get_or_create_vendor,
    status_from_inspection,
    submission_message,
)

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db)]
EvidenceFile = Annotated[UploadFile, File()]

VALID_DOCUMENT_STATUSES = frozenset(item["code"] for item in DOCUMENT_STATUSES)
VALID_LOAD_TYPES = frozenset(item["code"] for item in LOAD_TYPES)
VALID_INSTITUTION_CODES = frozenset(item["code"] for item in INSTITUTIONS)


@router.get("/health", tags=["system"])
def api_health() -> dict[str, str]:
    return {"status": "ok", "service": "checkwise-api"}


@router.get("/health/db", tags=["system"])
def db_health(db: DbSession) -> dict[str, str]:
    db.execute(text("select 1"))
    return {"status": "ok", "database": "reachable"}


@router.get("/catalogs", response_model=CatalogResponse, tags=["catalogs"])
def get_catalogs() -> CatalogResponse:
    return CatalogResponse(
        document_statuses=DOCUMENT_STATUSES,
        load_types=LOAD_TYPES,
        institutions=INSTITUTIONS,
        validation_rules=VALIDATION_RULES,
        requirement_examples=REQUIREMENT_EXAMPLES,
    )


@router.post(
    "/submissions",
    response_model=SubmissionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["submissions"],
)
async def create_submission(
    client_name: Annotated[str, Form(min_length=2)],
    vendor_name: Annotated[str, Form(min_length=2)],
    vendor_rfc: Annotated[str, Form(min_length=12, max_length=13)],
    period_code: Annotated[str, Form(min_length=4)],
    load_type: Annotated[str, Form()],
    institution_code: Annotated[str, Form()],
    requirement_name: Annotated[str, Form(min_length=2)],
    file: EvidenceFile,
    db: DbSession,
    comments: Annotated[str | None, Form()] = None,
    initial_status: Annotated[str, Form()] = DocumentStatus.PENDIENTE_REVISION.value,
    contract_reference: Annotated[str | None, Form()] = None,
    # Canonical IDs introduced by the Reconciliation Patch. Both optional for
    # the deprecation window (one minor version): when provided, the canonical
    # path takes precedence over ``requirement_name`` / ``period_code`` and
    # the submission is bound to the catalog. When absent, the legacy free-
    # text path runs with a deprecation event recorded against the submission.
    requirement_code: Annotated[str | None, Form()] = None,
    period_key: Annotated[str | None, Form()] = None,
) -> SubmissionResponse:
    assert_pdf_upload(file)

    if initial_status != DocumentStatus.PENDIENTE_REVISION:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="La carga inicial debe comenzar en pendiente_revision.",
        )

    if initial_status not in VALID_DOCUMENT_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Estado inválido."
        )

    if load_type not in VALID_LOAD_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Tipo de carga inválido."
        )

    if institution_code not in VALID_INSTITUTION_CODES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Institución inválida."
        )

    storage = LocalStorageService()
    try:
        stored_file = await storage.save_upload(file)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        duplicate = db.scalar(
            select(Document).where(Document.sha256 == stored_file.sha256).limit(1)
        )

        client = get_or_create_client(db, client_name.strip())
        institution = get_or_create_institution(db, institution_code)
        vendor = get_or_create_vendor(
            db, client.id, vendor_name.strip(), vendor_rfc.upper().strip()
        )
        resolved_requirement = resolve_requirement(
            db,
            requirement_code=(requirement_code or "").strip() or None,
            requirement_name=requirement_name.strip(),
            institution_id=institution.id,
            institution_code=institution.code,
            load_type=load_type,
        )
        resolved_period = resolve_period(
            db,
            period_key=(period_key or "").strip() or None,
            period_code=period_code.strip(),
            load_type=load_type,
        )
        contract = get_or_create_contract(db, client.id, vendor.id, contract_reference)

        pdf_inspection = inspect_pdf(stored_file.path)
        document_signals = analyze_document_text(
            pdf_inspection.text_sample,
            expected_requirement=resolved_requirement.canonical_name,
            expected_institution=institution.code,
            expected_period=period_code.strip(),
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
            submitted_by="local-form",
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

        db.add(
            DocumentStatusHistory(
                document_id=document.id,
                submission_id=submission.id,
                from_status=None,
                to_status=final_status.value,
                reason="Carga inicial desde portal nativo CheckWise.",
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
            },
            metadata={
                "source": "native_intake",
                "storage_key": stored_file.storage_key,
                "sha256": stored_file.sha256,
                "requirement_intake": (
                    "legacy_free_text" if resolved_requirement.used_legacy else "canonical_code"
                ),
                "period_intake": (
                    "legacy_period_code"
                    if resolved_period.used_legacy
                    else "canonical_period_key"
                ),
                "validation_events": [event.event_type for event in validation_events],
            },
        )

        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No fue posible registrar la carga documental.",
        ) from exc

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
