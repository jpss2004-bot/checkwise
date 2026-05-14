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
from app.models import Client, Contract, Vendor
from app.models import Institution as InstitutionModel
from app.services.document_intelligence import DocumentSignals
from app.services.pdf_validation import PdfInspectionResult
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
