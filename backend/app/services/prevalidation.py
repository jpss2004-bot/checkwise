from __future__ import annotations

from app.core.config import settings
from app.schemas.submissions import ValidationSignal
from app.services.document_intelligence import DocumentSignals
from app.services.pdf_validation import PdfInspectionResult
from app.services.storage import StoredFile


def build_initial_validations(
    stored_file: StoredFile,
    *,
    duplicate_found: bool,
    pdf_inspection: PdfInspectionResult | None = None,
    document_signals: DocumentSignals | None = None,
    human_review_required: bool = True,
) -> list[ValidationSignal]:
    allowed_type = stored_file.extension in settings.allowed_extensions_set
    max_size_ok = stored_file.size_bytes <= settings.MAX_UPLOAD_SIZE_BYTES

    return [
        ValidationSignal(
            rule_code="file_exists",
            rule_type="tecnica",
            result="pass" if stored_file.size_bytes > 0 else "fail",
            severity="info" if stored_file.size_bytes > 0 else "error",
            message="Archivo recibido y almacenado fuera de la base de datos.",
        ),
        ValidationSignal(
            rule_code="allowed_file_type",
            rule_type="tecnica",
            result="pass" if allowed_type else "fail",
            severity="info" if allowed_type else "error",
            message=(
                f"Extensión detectada: {stored_file.extension or 'sin extensión'}. "
                "En V1.1 solo se aceptan PDFs."
            ),
        ),
        ValidationSignal(
            rule_code="pdf_magic_header",
            rule_type="tecnica",
            result="pass" if pdf_inspection and pdf_inspection.is_pdf else "fail",
            severity="info" if pdf_inspection and pdf_inspection.is_pdf else "error",
            message=(
                "El archivo tiene cabecera PDF válida."
                if pdf_inspection and pdf_inspection.is_pdf
                else "El archivo no tiene estructura PDF válida."
            ),
        ),
        ValidationSignal(
            rule_code="pdf_encrypted",
            rule_type="tecnica",
            result="fail" if pdf_inspection and pdf_inspection.is_encrypted else "pass",
            severity="error" if pdf_inspection and pdf_inspection.is_encrypted else "info",
            message=(
                "El PDF parece estar protegido con contraseña o cifrado."
                if pdf_inspection and pdf_inspection.is_encrypted
                else "No se detectó bloqueo por contraseña."
            ),
            requires_human_review=bool(pdf_inspection and pdf_inspection.is_encrypted),
        ),
        ValidationSignal(
            rule_code="pdf_readable_text",
            rule_type="tecnica",
            result="pass" if pdf_inspection and pdf_inspection.has_text else "warning",
            severity="info" if pdf_inspection and pdf_inspection.has_text else "warning",
            message=(
                "Se detectó texto legible para análisis posterior."
                if pdf_inspection and pdf_inspection.has_text
                else "No se detectó texto suficiente; podría ser un PDF escaneado."
            ),
            requires_human_review=not bool(pdf_inspection and pdf_inspection.has_text),
        ),
        ValidationSignal(
            rule_code="max_file_size",
            rule_type="tecnica",
            result="pass" if max_size_ok else "fail",
            severity="info" if max_size_ok else "error",
            message=f"Tamaño registrado: {stored_file.size_bytes} bytes.",
        ),
        ValidationSignal(
            rule_code="sha256_hash",
            rule_type="tecnica",
            result="pass",
            severity="info",
            message=f"Hash SHA-256 calculado: {stored_file.sha256}.",
        ),
        ValidationSignal(
            rule_code="duplicate_hash",
            rule_type="tecnica",
            result="warning" if duplicate_found else "pass",
            severity="warning" if duplicate_found else "info",
            message=(
                "Ya existe un documento con el mismo hash; revisar si corresponde al mismo "
                "proveedor/periodo/requisito."
                if duplicate_found
                else "No se detectó duplicado por hash en la base actual."
            ),
            requires_human_review=duplicate_found,
        ),
        ValidationSignal(
            rule_code="vendor_match",
            rule_type="fiscal",
            result="pending",
            severity="warning",
            message="Pendiente de extracción/OCR para confirmar RFC y razón social del proveedor.",
            requires_human_review=True,
        ),
        ValidationSignal(
            rule_code="period_match",
            rule_type="temporal",
            result="pending",
            severity="warning",
            message=(
                "Pendiente de extracción/OCR para confirmar que el documento corresponde al "
                "periodo."
            ),
            requires_human_review=True,
        ),
        ValidationSignal(
            rule_code="requirement_match",
            rule_type="regulatoria",
            result=(
                "warning" if document_signals and document_signals.mismatch_reason else "pending"
            ),
            severity="warning",
            message=(
                document_signals.mismatch_reason
                if document_signals and document_signals.mismatch_reason
                else "Pendiente de revisión para confirmar que el archivo satisface el requisito."
            ),
            requires_human_review=True,
            confidence=(
                document_signals.requirement_match_confidence if document_signals else None
            ),
        ),
        ValidationSignal(
            rule_code="document_intelligence",
            rule_type="inteligencia",
            result="warning" if document_signals and document_signals.anomaly_codes else "pass",
            severity="warning" if document_signals and document_signals.anomaly_codes else "info",
            message=(
                "Se detectaron señales que requieren revisión: "
                + ", ".join(document_signals.anomaly_codes)
                if document_signals and document_signals.anomaly_codes
                else "No se detectaron anomalías determinísticas en esta fase."
            ),
            requires_human_review=bool(document_signals and document_signals.anomaly_codes),
            confidence=(
                document_signals.requirement_match_confidence if document_signals else None
            ),
        ),
        ValidationSignal(
            rule_code="human_review_required",
            rule_type="legal",
            result="required" if human_review_required else "not_required",
            severity="warning" if human_review_required else "info",
            message="La aprobación crítica requiere revisión humana autorizada.",
            requires_human_review=human_review_required,
        ),
    ]
