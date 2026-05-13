from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.catalogs import (
    DOCUMENT_STATUSES,
    INSTITUTIONS,
    LOAD_TYPES,
    REQUIREMENT_EXAMPLES,
    VALIDATION_RULES,
)
from app.core.compliance_catalog import (
    OnboardingRequirement,
    RecurringRequirement,
    lookup_onboarding_by_code,
    lookup_recurring_by_code,
)
from app.core.config import settings
from app.db.session import get_db
from app.models import (
    Client,
    Contract,
    Document,
    DocumentInspection,
    DocumentStatusHistory,
    Institution,
    Period,
    Requirement,
    RequirementVersion,
    Submission,
    Validation,
    Vendor,
)
from app.schemas.catalogs import CatalogResponse
from app.schemas.submissions import (
    DocumentInspectionSummary,
    DocumentSignalsSummary,
    SubmissionResponse,
    SupportInfo,
    ValidationEventSummary,
)
from app.services.audit_log import add_audit_event
from app.services.document_intelligence import DocumentSignals, analyze_document_text
from app.services.pdf_validation import PdfInspectionResult, inspect_pdf
from app.services.prevalidation import build_initial_validations
from app.services.storage import LocalStorageService, StoredFile
from app.services.validation_events import add_validation_event

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db)]
EvidenceFile = Annotated[UploadFile, File()]


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
    initial_status: Annotated[str, Form()] = "pendiente_revision",
    contract_reference: Annotated[str | None, Form()] = None,
    # Canonical IDs introduced by the Reconciliation Patch. Both optional for
    # the deprecation window (one minor version): when provided, the canonical
    # path takes precedence over ``requirement_name`` / ``period_code`` and
    # the submission is bound to the catalog. When absent, the legacy free-
    # text path runs with a deprecation event recorded against the submission.
    requirement_code: Annotated[str | None, Form()] = None,
    period_key: Annotated[str | None, Form()] = None,
) -> SubmissionResponse:
    _assert_pdf_upload(file)

    if initial_status != "pendiente_revision":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La carga inicial debe comenzar en pendiente_revision.",
        )

    valid_statuses = {item["code"] for item in DOCUMENT_STATUSES}
    if initial_status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Estado inválido."
        )

    valid_load_types = {item["code"] for item in LOAD_TYPES}
    if load_type not in valid_load_types:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Tipo de carga inválido."
        )

    valid_institutions = {item["code"] for item in INSTITUTIONS}
    if institution_code not in valid_institutions:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Institución inválida."
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

        client = _get_or_create_client(db, client_name.strip())
        institution = _get_or_create_institution(db, institution_code)
        vendor = _get_or_create_vendor(
            db, client.id, vendor_name.strip(), vendor_rfc.upper().strip()
        )
        resolved_requirement = _resolve_requirement(
            db,
            requirement_code=(requirement_code or "").strip() or None,
            requirement_name=requirement_name.strip(),
            institution_id=institution.id,
            institution_code=institution.code,
            load_type=load_type,
        )
        resolved_period = _resolve_period(
            db,
            period_key=(period_key or "").strip() or None,
            period_code=period_code.strip(),
            load_type=load_type,
        )
        contract = _get_or_create_contract(db, client.id, vendor.id, contract_reference)

        pdf_inspection = inspect_pdf(stored_file.path)
        document_signals = analyze_document_text(
            pdf_inspection.text_sample,
            expected_requirement=resolved_requirement.canonical_name,
            expected_institution=institution.code,
            expected_period=period_code.strip(),
        )
        final_status = _status_from_inspection(pdf_inspection, document_signals)

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
            status=final_status,
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
            status=final_status,
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
                to_status=final_status,
                reason="Carga inicial desde portal nativo CheckWise.",
                actor="system",
            )
        )
        validation_events = _add_native_intake_events(
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
                "status": final_status,
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
        status=final_status,
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
        message=_submission_message(final_status),
    )


def _assert_pdf_upload(file: UploadFile) -> None:
    filename = file.filename or ""
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="En esta fase solo se aceptan archivos PDF.",
        )

    if file.content_type and file.content_type not in {
        "application/pdf",
        "application/x-pdf",
        "application/octet-stream",
    }:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"El MIME type recibido no parece PDF: {file.content_type}.",
        )


def _status_from_inspection(
    pdf_inspection: PdfInspectionResult,
    document_signals: DocumentSignals,
) -> str:
    if not pdf_inspection.is_pdf or pdf_inspection.is_corrupt or pdf_inspection.is_encrypted:
        return "requiere_aclaracion"
    if document_signals.mismatch_reason:
        return "posible_mismatch"
    return "pendiente_revision"


def _submission_message(status_code: str) -> str:
    if status_code == "requiere_aclaracion":
        return (
            "Carga recibida, pero el PDF requiere aclaración antes de revisión "
            "porque no pudo inspeccionarse correctamente."
        )
    if status_code == "posible_mismatch":
        return (
            "Carga recibida con alerta de posible mismatch. Verifica el archivo o "
            "contacta soporte antes de continuar."
        )
    return "Carga recibida. El documento queda pendiente de revisión humana."


def _add_native_intake_events(
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


def _get_or_create_client(db: Session, name: str) -> Client:
    client = db.scalar(select(Client).where(Client.name == name).limit(1))
    if client:
        return client
    client = Client(name=name, status="active")
    db.add(client)
    db.flush()
    return client


def _get_or_create_vendor(db: Session, client_id: str, name: str, rfc: str) -> Vendor:
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


def _get_or_create_institution(db: Session, code: str) -> Institution:
    institution = db.scalar(select(Institution).where(Institution.code == code).limit(1))
    if institution:
        return institution
    label = next(item["label"] for item in INSTITUTIONS if item["code"] == code)
    institution = Institution(code=code, name=label)
    db.add(institution)
    db.flush()
    return institution


def _get_or_create_period(
    db: Session,
    *,
    code: str,
    period_type: str,
    period_key: str | None = None,
) -> Period:
    # Prefer canonical-key lookup: if the catalog says this is ``2026-B1``,
    # an existing row carrying that key is the right Period regardless of how
    # legacy code spelled the ``code`` field.
    period: Period | None = None
    if period_key:
        period = db.scalar(select(Period).where(Period.period_key == period_key).limit(1))
    if period is None:
        period = db.scalar(
            select(Period).where(Period.code == code, Period.period_type == period_type).limit(1)
        )
    if period is not None:
        # Backfill canonical key onto pre-existing legacy rows so subsequent
        # lookups go through the fast path.
        if period_key and not period.period_key:
            period.period_key = period_key
        return period

    year, month = _parse_year_month(code)
    period = Period(
        code=code,
        year=year,
        month=month,
        period_type=period_type,
        period_key=period_key,
    )
    db.add(period)
    db.flush()
    return period


def _get_or_create_requirement(
    db: Session,
    *,
    institution_id: str,
    institution_code: str,
    load_type: str,
    requirement_name: str,
) -> tuple[Requirement, RequirementVersion]:
    code = _requirement_code(institution_code, load_type, requirement_name)
    requirement = db.scalar(select(Requirement).where(Requirement.code == code).limit(1))
    if not requirement:
        requirement = Requirement(
            code=code,
            name=requirement_name,
            institution_id=institution_id,
            load_type=load_type,
            frequency=load_type,
            risk_level="alto",
            current_version=1,
        )
        db.add(requirement)
        db.flush()

    version = db.scalar(
        select(RequirementVersion)
        .where(
            RequirementVersion.requirement_id == requirement.id,
            RequirementVersion.version == requirement.current_version,
        )
        .limit(1)
    )
    if not version:
        version = RequirementVersion(
            requirement_id=requirement.id,
            version=requirement.current_version,
            legal_basis="Pendiente de semilla completa desde matriz regulatoria REPSE 2026.",
            applicability_rule="Aplica según cliente, proveedor, contrato, periodo e institución.",
            minimum_validation="Archivo legible, tipo permitido, hash calculado y revisión humana.",
            automatic_signals=(
                "archivo existe; tipo permitido; tamaño máximo; hash; duplicado por hash"
            ),
            human_review_required=True,
            missing_state="pendiente_revision",
            implementation_notes=(
                "Requisito creado desde carga inicial; debe reconciliarse con catálogo oficial."
            ),
        )
        db.add(version)
        db.flush()
    return requirement, version


def _get_or_create_contract(
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


def _parse_year_month(code: str) -> tuple[int | None, int | None]:
    match = re.search(r"(20\d{2})[-/ ]?(0?[1-9]|1[0-2])?", code)
    if not match:
        return None, None
    year = int(match.group(1))
    month = int(match.group(2)) if match.group(2) else None
    return year, month


def _requirement_code(institution_code: str, load_type: str, name: str) -> str:
    slug = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "-", slug).strip("-").upper()
    slug = slug[:34] or "REQUISITO"
    return f"REQ-{institution_code.upper()}-{load_type.upper()}-{slug}"


@dataclass(frozen=True)
class _ResolvedRequirement:
    """Result of resolving a submission requirement, canonical or legacy."""

    requirement: Requirement
    requirement_version: RequirementVersion
    canonical_name: str
    canonical_code: str | None
    used_legacy: bool


@dataclass(frozen=True)
class _ResolvedPeriod:
    """Result of resolving a submission period, canonical or legacy."""

    period: Period
    canonical_period_key: str | None
    used_legacy: bool


def _lookup_canonical_requirement(
    code: str,
) -> RecurringRequirement | OnboardingRequirement | None:
    """Resolve a canonical requirement_code against the in-code catalog."""
    rec = lookup_recurring_by_code(code)
    if rec is not None:
        return rec
    return lookup_onboarding_by_code(code)


def _get_requirement_for_catalog_item(
    db: Session,
    catalog_item: RecurringRequirement | OnboardingRequirement,
    *,
    institution_id: str,
) -> tuple[Requirement, RequirementVersion]:
    """Find or create the DB row mirroring a canonical catalog item."""
    requirement = db.scalar(
        select(Requirement).where(Requirement.code == catalog_item.code).limit(1)
    )
    if requirement is None:
        if isinstance(catalog_item, RecurringRequirement):
            frequency = catalog_item.frequency
            load_type_value = catalog_item.frequency
        else:
            frequency = "alta_inicial"
            load_type_value = "alta_inicial"
        requirement = Requirement(
            code=catalog_item.code,
            name=catalog_item.name,
            institution_id=institution_id,
            load_type=load_type_value,
            frequency=frequency,
            risk_level="alto",
            current_version=1,
        )
        db.add(requirement)
        db.flush()

    version = db.scalar(
        select(RequirementVersion)
        .where(
            RequirementVersion.requirement_id == requirement.id,
            RequirementVersion.version == requirement.current_version,
        )
        .limit(1)
    )
    if version is None:
        version = RequirementVersion(
            requirement_id=requirement.id,
            version=requirement.current_version,
            legal_basis=(
                "Sembrado desde compliance_catalog en el flujo de Reconciliación "
                "(canonical_code)."
            ),
            applicability_rule=(
                "Aplica según cliente, proveedor, contrato, periodo e institución."
            ),
            minimum_validation=(
                "Archivo legible, tipo permitido, hash calculado y revisión humana."
            ),
            automatic_signals=(
                "archivo existe; tipo permitido; tamaño máximo; hash; duplicado por hash"
            ),
            human_review_required=True,
            missing_state="pendiente_revision",
            implementation_notes=(
                "Requisito creado desde canonical_code. La semilla completa de "
                "requirement_versions ocurrirá en una migración posterior."
            ),
        )
        db.add(version)
        db.flush()
    return requirement, version


def _resolve_requirement(
    db: Session,
    *,
    requirement_code: str | None,
    requirement_name: str,
    institution_id: str,
    institution_code: str,
    load_type: str,
) -> _ResolvedRequirement:
    """Resolve a requirement from canonical code when present, else legacy."""
    if requirement_code:
        catalog_item = _lookup_canonical_requirement(requirement_code)
        if catalog_item is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"requirement_code desconocido: {requirement_code}",
            )
        requirement, version = _get_requirement_for_catalog_item(
            db, catalog_item, institution_id=institution_id
        )
        return _ResolvedRequirement(
            requirement=requirement,
            requirement_version=version,
            canonical_name=catalog_item.name,
            canonical_code=catalog_item.code,
            used_legacy=False,
        )

    requirement, version = _get_or_create_requirement(
        db,
        institution_id=institution_id,
        institution_code=institution_code,
        load_type=load_type,
        requirement_name=requirement_name,
    )
    return _ResolvedRequirement(
        requirement=requirement,
        requirement_version=version,
        canonical_name=requirement_name,
        canonical_code=None,
        used_legacy=True,
    )


def _resolve_period(
    db: Session,
    *,
    period_key: str | None,
    period_code: str,
    load_type: str,
) -> _ResolvedPeriod:
    """Resolve a Period from canonical key when present, else legacy code."""
    canonical_key = period_key.strip() if period_key else None
    period = _get_or_create_period(
        db,
        code=period_code,
        period_type=load_type,
        period_key=canonical_key,
    )
    return _ResolvedPeriod(
        period=period,
        canonical_period_key=canonical_key,
        used_legacy=canonical_key is None,
    )
