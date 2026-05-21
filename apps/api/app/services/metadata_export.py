from __future__ import annotations

import re
import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.metadata_rules import all_metadata_rules, metadata_rule_by_code
from app.models import Client, Contract, Document, Vendor
from app.models import Institution as InstitutionModel
from app.services.requirement_service import ResolvedPeriod, ResolvedRequirement
from app.services.storage import StoredFile
from tools.export_pdf_metadata_table import export_pdf_metadata_table


@dataclass(frozen=True)
class MetadataExportResult:
    status: str
    document_type_code: str | None = None
    output_path: str | None = None
    latest_path: str | None = None
    reason: str | None = None


_CLASSIFIER_TO_METADATA_CODE = {
    "contrato": "contrato_prestacion_servicios",
    "repse_constancia": "registro_repse",
}


def export_metadata_table_after_upload(
    *,
    stored_file: StoredFile,
    client: Client,
    vendor: Vendor,
    contract: Contract | None,
    institution: InstitutionModel,
    resolved_requirement: ResolvedRequirement,
    resolved_period: ResolvedPeriod,
    document: Document,
    detected_document_type: str | None,
) -> MetadataExportResult:
    """Create the automatic XLSX metadata table for a submitted PDF.

    This function is deliberately best-effort: metadata export should be
    visible to LegalShelf but must never block the provider's upload.
    Callers record the returned status as a ValidationEvent.
    """
    if not settings.AUTO_METADATA_EXPORT_ENABLED:
        return MetadataExportResult(status="skipped", reason="automatic export disabled")

    document_type_code = resolve_metadata_document_type_code(
        requirement_code=resolved_requirement.canonical_code,
        requirement_name=resolved_requirement.canonical_name,
        institution_code=institution.code,
        filename=stored_file.original_filename,
        detected_document_type=detected_document_type,
    )
    if document_type_code is None:
        return MetadataExportResult(
            status="skipped",
            reason="metadata document type could not be resolved",
        )

    output_dir = _export_directory(
        client_name=client.name,
        vendor_name=vendor.name,
        period_key=resolved_period.canonical_period_key,
        document_type_code=document_type_code,
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"{document.submission_id}_{document.id}_metadata.xlsx"
    latest_path = output_dir / "latest_metadata.xlsx"
    context = _metadata_context(
        client=client,
        vendor=vendor,
        contract=contract,
        institution=institution,
        resolved_requirement=resolved_requirement,
        resolved_period=resolved_period,
        document=document,
        stored_file=stored_file,
        document_type_code=document_type_code,
    )

    try:
        export_pdf_metadata_table(
            pdf_path=stored_file.path,
            document_type_code=document_type_code,
            context=context,
            output_path=output_path,
            output_format="xlsx",
            include_intelligence=True,
            enable_ocr=False,
        )
        shutil.copyfile(output_path, latest_path)
    except Exception as exc:  # noqa: BLE001 - surfaced as telemetry, not a provider error
        return MetadataExportResult(
            status="failed",
            document_type_code=document_type_code,
            reason=f"{exc.__class__.__name__}: {exc}",
        )

    return MetadataExportResult(
        status="completed",
        document_type_code=document_type_code,
        output_path=str(output_path),
        latest_path=str(latest_path),
    )


def resolve_metadata_document_type_code(
    *,
    requirement_code: str | None,
    requirement_name: str,
    institution_code: str,
    filename: str,
    detected_document_type: str | None = None,
) -> str | None:
    """Map the upload requirement to a metadata-rule document type."""
    if requirement_code:
        maybe_metadata_code = requirement_code.strip().lower()
        try:
            metadata_rule_by_code(maybe_metadata_code)
            return maybe_metadata_code
        except KeyError:
            pass

    if detected_document_type in _CLASSIFIER_TO_METADATA_CODE:
        return _CLASSIFIER_TO_METADATA_CODE[detected_document_type]

    normalized_name = _normalize(requirement_name)
    normalized_filename = _normalize(Path(filename).stem.replace("_", " "))
    institution = institution_code.strip().lower()

    candidates = [
        rule
        for rule in all_metadata_rules(include_annexes=True)
        if rule.institution == institution or rule.institution == "interno_cliente"
    ]
    scored: list[tuple[int, str]] = []
    for rule in candidates:
        rule_name = _normalize(rule.name)
        rule_code = _normalize(rule.code.replace("_", " "))
        score = 0
        if normalized_name == rule_name:
            score += 100
        if normalized_name and (normalized_name in rule_name or rule_name in normalized_name):
            score += 70
        if normalized_name and _token_overlap(normalized_name, rule_name) >= 0.6:
            score += 45
        if rule_code and rule_code in normalized_filename:
            score += 35
        if rule_name and _token_overlap(normalized_filename, rule_name) >= 0.6:
            score += 25
        if score:
            scored.append((score, rule.code))

    if not scored:
        return None
    scored.sort(reverse=True)
    return scored[0][1]


def _metadata_context(
    *,
    client: Client,
    vendor: Vendor,
    contract: Contract | None,
    institution: InstitutionModel,
    resolved_requirement: ResolvedRequirement,
    resolved_period: ResolvedPeriod,
    document: Document,
    stored_file: StoredFile,
    document_type_code: str,
) -> dict[str, Any]:
    period_key = resolved_period.canonical_period_key
    return {
        "submission_id": document.submission_id,
        "document_id": document.id,
        "client_id": client.id,
        "client_legal_name": client.name,
        "vendor_id": vendor.id,
        "vendor_legal_name": vendor.name,
        "vendor_rfc": vendor.rfc,
        "provider_nomenclature": vendor.name,
        "contract_id": contract.id if contract else None,
        "contract_reference": contract.external_reference if contract else None,
        "requirement_id": resolved_requirement.requirement.id,
        "requirement_code": resolved_requirement.canonical_code,
        "requirement_name": resolved_requirement.canonical_name,
        "period_id": resolved_period.period.id,
        "period_key": period_key,
        "document_type_code": document_type_code,
        "expected_document_type_code": document_type_code,
        "expected_institution": institution.code,
        "upload_form_month": _period_month_label(period_key),
        "reported_period": period_key,
        "original_filename": stored_file.original_filename,
        "sha256": stored_file.sha256,
        "mime_type": stored_file.mime_type,
        "size_bytes": stored_file.size_bytes,
        "storage_key": stored_file.storage_key,
        "proposed_pdf_file_name": stored_file.original_filename,
    }


def _export_directory(
    *,
    client_name: str,
    vendor_name: str,
    period_key: str | None,
    document_type_code: str,
) -> Path:
    return (
        Path(settings.METADATA_EXPORT_PATH)
        / _slug(client_name)
        / _slug(vendor_name)
        / _slug(period_key or "alta-inicial")
        / _slug(document_type_code)
    )


def _period_month_label(period_key: str | None) -> str | None:
    if not period_key or "-M" not in period_key:
        return None
    try:
        month = int(period_key.split("-M", 1)[1])
    except ValueError:
        return None
    months = (
        "Enero",
        "Febrero",
        "Marzo",
        "Abril",
        "Mayo",
        "Junio",
        "Julio",
        "Agosto",
        "Septiembre",
        "Octubre",
        "Noviembre",
        "Diciembre",
    )
    if 1 <= month <= 12:
        return months[month - 1]
    return None


def _token_overlap(left: str, right: str) -> float:
    left_tokens = {token for token in left.split() if len(token) > 2}
    right_tokens = {token for token in right.split() if len(token) > 2}
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(len(left_tokens), len(right_tokens), 1)


def _normalize(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", re.sub(r"[^a-zA-Z0-9]+", " ", ascii_text).lower()).strip()


def _slug(value: str) -> str:
    normalized = _normalize(value)
    return re.sub(r"[^a-z0-9-]+", "-", normalized.replace(" ", "-")).strip("-") or "unknown"
