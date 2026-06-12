from __future__ import annotations

from app.core.config import settings
from app.schemas.submissions import ValidationSignal
from app.services.document_intelligence import (
    PERIOD_ALIGNMENT_ABSENT,
    PERIOD_ALIGNMENT_MATCH,
    PERIOD_ALIGNMENT_MISMATCH,
    PERIOD_ALIGNMENT_NO_EXPECTED,
    RFC_ALIGNMENT_ABSENT,
    RFC_ALIGNMENT_HOMOCLAVE_MISMATCH,
    RFC_ALIGNMENT_MATCH,
    RFC_ALIGNMENT_MISMATCH,
    RFC_ALIGNMENT_NO_EXPECTED,
    DocumentSignals,
)
from app.services.pdf_validation import PdfInspectionResult
from app.services.storage import StoredFile


def _format_megabytes(size_bytes: int) -> str:
    """Render a byte count as a provider-friendly MB string.

    Stage 2.6 (BL-T9) — providers should not see raw byte counts.
    ``2400123`` becomes ``"2.4 MB"``; small files round to one
    decimal so the helper text reads naturally on a 500-KB PDF.
    """
    mb = size_bytes / 1_048_576  # 1024 * 1024
    return f"{mb:.1f} MB"


def _vendor_match_signal(document_signals: DocumentSignals | None) -> ValidationSignal:
    alignment = document_signals.rfc_alignment if document_signals else None
    if alignment == RFC_ALIGNMENT_MATCH:
        return ValidationSignal(
            rule_code="vendor_match",
            rule_type="fiscal",
            result="pass",
            severity="info",
            message="El RFC detectado coincide con el proveedor.",
            requires_human_review=True,
        )
    if alignment == RFC_ALIGNMENT_HOMOCLAVE_MISMATCH:
        return ValidationSignal(
            rule_code="vendor_match",
            rule_type="fiscal",
            result="warning",
            severity="warning",
            message=(
                "Detectamos un RFC con el mismo núcleo del proveedor, "
                "pero distinta homoclave. Un revisor lo confirmará."
            ),
            requires_human_review=True,
        )
    if alignment == RFC_ALIGNMENT_MISMATCH:
        return ValidationSignal(
            rule_code="vendor_match",
            rule_type="fiscal",
            result="warning",
            severity="warning",
            message=(
                "El RFC detectado no coincide con el proveedor. "
                "Un revisor lo validará antes de decidir."
            ),
            requires_human_review=True,
        )
    if alignment == RFC_ALIGNMENT_ABSENT:
        return ValidationSignal(
            rule_code="vendor_match",
            rule_type="fiscal",
            result="fail",
            severity="error",
            message=(
                "No pudimos detectar un RFC en el documento. Sube una versión "
                "más clara o el archivo correcto para poder prevalidarlo."
            ),
            requires_human_review=True,
        )
    elif alignment == RFC_ALIGNMENT_NO_EXPECTED:
        message = (
            "El proveedor no tiene RFC registrado para comparar. "
            "Un revisor lo confirmará."
        )
    else:
        message = (
            "Pendiente: un revisor confirmará que el RFC y la razón "
            "social coincidan con el proveedor."
        )
    return ValidationSignal(
        rule_code="vendor_match",
        rule_type="fiscal",
        result="pending",
        severity="warning",
        message=message,
        requires_human_review=True,
    )


def _period_match_signal(document_signals: DocumentSignals | None) -> ValidationSignal:
    alignment = document_signals.period_alignment if document_signals else None
    if alignment == PERIOD_ALIGNMENT_MATCH:
        return ValidationSignal(
            rule_code="period_match",
            rule_type="temporal",
            result="pass",
            severity="info",
            message="El periodo detectado coincide con el periodo esperado.",
            requires_human_review=True,
        )
    if alignment == PERIOD_ALIGNMENT_MISMATCH:
        return ValidationSignal(
            rule_code="period_match",
            rule_type="temporal",
            result="warning",
            severity="warning",
            message=(
                "El periodo detectado no coincide con el periodo esperado. "
                "Un revisor lo validará antes de decidir."
            ),
            requires_human_review=True,
        )
    if alignment == PERIOD_ALIGNMENT_ABSENT:
        message = "No detectamos el periodo esperado en el documento. Un revisor lo confirmará."
    elif alignment == PERIOD_ALIGNMENT_NO_EXPECTED:
        message = "No hay periodo esperado registrado para comparar. Un revisor lo confirmará."
    else:
        message = (
            "Pendiente: un revisor confirmará que el documento "
            "corresponde al periodo."
        )
    return ValidationSignal(
        rule_code="period_match",
        rule_type="temporal",
        result="pending",
        severity="warning",
        message=message,
        requires_human_review=True,
    )


def build_initial_validations(
    stored_file: StoredFile,
    *,
    duplicate_found: bool,
    pdf_inspection: PdfInspectionResult | None = None,
    document_signals: DocumentSignals | None = None,
    human_review_required: bool = True,
) -> list[ValidationSignal]:
    """Build the provider-facing validation summary for an upload.

    Stage 2.6 (BL-T9, 2026-05-20) — the ``message`` strings are
    written for a non-technical compliance officer. Engineer dialect
    (hash, OCR, extraction, anomaly codes, byte counts) lives in the
    Document / DocumentInspection / DocumentSignals rows for QA and
    reviewer surfaces; this list never leaks it through the API.
    """
    allowed_type = stored_file.extension in settings.allowed_extensions_set
    max_size_ok = stored_file.size_bytes <= settings.MAX_UPLOAD_SIZE_BYTES
    file_extension = stored_file.extension or "sin extensión"
    max_size_mb = _format_megabytes(settings.MAX_UPLOAD_SIZE_BYTES)
    file_size_mb = _format_megabytes(stored_file.size_bytes)
    anomaly_count = (
        len(document_signals.anomaly_codes)
        if document_signals and document_signals.anomaly_codes
        else 0
    )

    return [
        ValidationSignal(
            rule_code="file_exists",
            rule_type="tecnica",
            result="pass" if stored_file.size_bytes > 0 else "fail",
            severity="info" if stored_file.size_bytes > 0 else "error",
            message=(
                "Archivo recibido y guardado correctamente."
                if stored_file.size_bytes > 0
                else "El archivo no se recibió. Vuelve a intentarlo."
            ),
        ),
        ValidationSignal(
            rule_code="allowed_file_type",
            rule_type="tecnica",
            result="pass" if allowed_type else "fail",
            severity="info" if allowed_type else "error",
            message=(
                "El archivo es un PDF, que es el formato aceptado."
                if allowed_type
                else (
                    f"El archivo {file_extension} no es un PDF. "
                    "Por ahora solo aceptamos PDFs."
                )
            ),
        ),
        ValidationSignal(
            rule_code="pdf_magic_header",
            rule_type="tecnica",
            result="pass" if pdf_inspection and pdf_inspection.is_pdf else "fail",
            severity="info" if pdf_inspection and pdf_inspection.is_pdf else "error",
            message=(
                "El archivo es un PDF válido."
                if pdf_inspection and pdf_inspection.is_pdf
                else (
                    "El archivo no parece ser un PDF válido. "
                    "Revisa el documento e inténtalo de nuevo."
                )
            ),
        ),
        ValidationSignal(
            rule_code="pdf_encrypted",
            rule_type="tecnica",
            result="fail" if pdf_inspection and pdf_inspection.is_encrypted else "pass",
            severity="error" if pdf_inspection and pdf_inspection.is_encrypted else "info",
            message=(
                "El PDF tiene contraseña. Pide la versión sin contraseña "
                "antes de subirlo."
                if pdf_inspection and pdf_inspection.is_encrypted
                else "El PDF se abre sin contraseña."
            ),
            requires_human_review=bool(pdf_inspection and pdf_inspection.is_encrypted),
        ),
        ValidationSignal(
            rule_code="pdf_readable_text",
            rule_type="tecnica",
            result="pass" if pdf_inspection and pdf_inspection.has_text else "warning",
            severity="info" if pdf_inspection and pdf_inspection.has_text else "warning",
            message=(
                "El documento tiene texto legible."
                if pdf_inspection and pdf_inspection.has_text
                else (
                    "No detectamos texto en el documento. Si es un escaneo, "
                    "asegúrate de que se lea con claridad."
                )
            ),
            requires_human_review=not bool(pdf_inspection and pdf_inspection.has_text),
        ),
        ValidationSignal(
            rule_code="max_file_size",
            rule_type="tecnica",
            result="pass" if max_size_ok else "fail",
            severity="info" if max_size_ok else "error",
            message=(
                f"Tamaño del archivo: {file_size_mb}."
                if max_size_ok
                else (
                    f"El archivo pesa {file_size_mb}. El límite máximo es "
                    f"{max_size_mb}. Comprime el documento o sepáralo en "
                    "varias partes."
                )
            ),
        ),
        ValidationSignal(
            rule_code="sha256_hash",
            rule_type="tecnica",
            result="pass",
            severity="info",
            message=(
                "Guardamos una huella única del archivo para evitar duplicados."
            ),
        ),
        ValidationSignal(
            rule_code="duplicate_hash",
            rule_type="tecnica",
            result="warning" if duplicate_found else "pass",
            severity="warning" if duplicate_found else "info",
            message=(
                "Detectamos que este archivo ya se subió antes. Verifica si "
                "corresponde al mismo proveedor, periodo y requisito."
                if duplicate_found
                else "Este archivo no se ha subido antes."
            ),
            requires_human_review=duplicate_found,
        ),
        _vendor_match_signal(document_signals),
        _period_match_signal(document_signals),
        ValidationSignal(
            rule_code="requirement_match",
            rule_type="regulatoria",
            result=(
                "warning" if document_signals and document_signals.mismatch_reason else "pending"
            ),
            severity="warning",
            message=(
                # ``mismatch_reason`` is already plain Spanish — phrased
                # as "El documento parece 'X', pero el requisito sugiere
                # 'Y'." (see document_intelligence.py). The frontend
                # wraps it with a "Posible discrepancia detectada"
                # heading; we don't double-prefix it here.
                document_signals.mismatch_reason
                if document_signals and document_signals.mismatch_reason
                else (
                    "Pendiente de revisión para confirmar que el archivo "
                    "satisface el requisito."
                )
            ),
            requires_human_review=True,
            confidence=(
                document_signals.requirement_match_confidence if document_signals else None
            ),
        ),
        ValidationSignal(
            rule_code="document_intelligence",
            rule_type="inteligencia",
            result="warning" if anomaly_count else "pass",
            severity="warning" if anomaly_count else "info",
            message=(
                # Provider-facing message stays count-based — the raw
                # anomaly codes (engineer dialect like
                # "possible_document_type_mismatch") are preserved in
                # ``DocumentSignalsSummary.anomaly_codes`` for the
                # reviewer surface. Providers see what they need to
                # act on: "necesita revisión".
                "Detectamos señales que necesitan que un revisor "
                "las valide antes de aprobar el documento."
                if anomaly_count
                else "No detectamos señales que necesiten revisión adicional."
            ),
            requires_human_review=bool(anomaly_count),
            confidence=(
                document_signals.requirement_match_confidence if document_signals else None
            ),
        ),
        ValidationSignal(
            rule_code="human_review_required",
            rule_type="legal",
            result="required" if human_review_required else "not_required",
            severity="warning" if human_review_required else "info",
            message=(
                "Este documento necesita la revisión de un especialista "
                "antes de aprobarse."
                if human_review_required
                else "No requiere revisión humana adicional."
            ),
            requires_human_review=human_review_required,
        ),
    ]
