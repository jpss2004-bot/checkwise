"""Build a local metadata review payload for one PDF using CheckWise rules.

This tool intentionally runs outside the CheckWise app/server. It imports the
real static metadata rulebook from ``app.core.metadata_rules`` and combines one
local PDF with optional synthetic/upload context JSON.

No database, AI, Google Sheets, credentials, or external services are used.
Local OCR can be enabled explicitly when a local Tesseract/Poppler toolchain is
installed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover - dependency is expected in backend pyproject
    PdfReader = None  # type: ignore[assignment]

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.metadata_rules import (  # noqa: E402
    RULEBOOK_VERSION,
    UnknownDocumentTypeError,
    all_metadata_rules,
    n8n_template_for_document_type,
    validate_metadata_rulebook,
)
from app.services.document_intelligence import (  # noqa: E402
    analyze_document_text,
    normalize_period_key,
)
from app.services.pdf_validation import inspect_pdf  # noqa: E402

PAYLOAD_TYPE = "checkwise_local_pdf_metadata_dry_run"
OCR_TEXT_SAMPLE_LIMIT = 6000

# Spanish month names for the human-readable "Fecha Completa" label
# (``DD de mes de AAAA``) and to build the 8-digit nomenclature date.
_SPANISH_MONTHS = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)

# Date fields whose value is "the document's date" — all resolve from the
# same conservatively-selected detected date (see ``_select_document_date``).
_DETECTED_DATE_FIELDS = frozenset(
    {"main_date", "issue_date", "expedition_date", "deed_date", "start_date"}
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _read_json_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Context JSON must be an object: {path}")
    return data


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _meaningful(value: Any) -> Any:
    """Return None for empty form values; preserve meaningful falsy values."""
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


def _compact_context(context: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in context.items() if _meaningful(value) is not None}


def _build_document_name_from_rulebook(
    *,
    context: dict[str, Any],
    template: dict[str, Any],
) -> str | None:
    pattern = template["document_type"].get("naming_pattern")
    if not pattern:
        return None
    values = {key: _meaningful(value) for key, value in context.items()}
    try:
        return pattern.format_map(_MissingNamePartDict(values))
    except KeyError:
        return None


class _MissingNamePartDict(dict):
    def __missing__(self, key: str) -> str:
        raise KeyError(key)


def inspect_local_pdf(pdf_path: str | Path) -> dict[str, Any]:
    """Return deterministic file/PDF metadata for one local PDF.

    This does not OCR and does not perform semantic content extraction. It only
    checks file-level facts that are safe to compute locally.
    """
    path = Path(pdf_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")
    if not path.is_file():
        raise ValueError(f"PDF path is not a file: {path}")

    guessed_mime = mimetypes.guess_type(path.name)[0]
    mime_type = guessed_mime or (
        "application/pdf" if path.suffix.lower() == ".pdf" else guessed_mime
    )

    with path.open("rb") as handle:
        first_bytes = handle.read(8)
    pdf_header_valid = first_bytes.startswith(b"%PDF-")

    page_count: int | None = None
    is_encrypted: bool | None = None
    pypdf_readable = False
    pdf_read_error: str | None = None

    if PdfReader is None:
        pdf_read_error = "pypdf is not available in this environment"
    else:
        try:
            reader = PdfReader(str(path))
            is_encrypted = bool(reader.is_encrypted)
            if is_encrypted:
                pdf_read_error = "PDF is encrypted; page count may be unavailable"
            else:
                page_count = len(reader.pages)
                pypdf_readable = True
        except Exception as exc:  # noqa: BLE001 - surfaced in dry-run JSON
            pdf_read_error = f"{exc.__class__.__name__}: {exc}"

    return {
        "pdf_path": str(path),
        "original_filename": path.name,
        "file_stem": path.stem,
        "sha256": _sha256_file(path),
        "mime_type": mime_type,
        "size_bytes": path.stat().st_size,
        "pdf_header_valid": pdf_header_valid,
        "page_count": page_count,
        "is_encrypted": is_encrypted,
        "pypdf_readable": pypdf_readable,
        "pdf_read_error": pdf_read_error,
        "inspection_method": "local_deterministic_file_inspection",
        "ocr_used": False,
        "ai_used": False,
        "external_services_used": False,
    }


def _parse_detected_date(value: str) -> tuple[int, int, int] | None:
    """Parse a detected date token into ``(year, month, day)``.

    Handles the Mexican ``DD/MM/AAAA`` (and ``DD-MM-AA``) convention plus
    ISO ``AAAA-MM-DD``. Returns ``None`` for anything ambiguous or invalid so
    the caller never fabricates a date.
    """
    token = (value or "").strip()
    iso = re.match(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$", token)
    if iso:
        year, month, day = int(iso.group(1)), int(iso.group(2)), int(iso.group(3))
    else:
        dmy = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})$", token)
        if not dmy:
            return None
        day, month, year = int(dmy.group(1)), int(dmy.group(2)), int(dmy.group(3))
        if year < 100:
            year += 2000
    if not (1 <= month <= 12 and 1 <= day <= 31 and 1900 <= year <= 2100):
        return None
    return year, month, day


def _select_document_date(
    *,
    context: dict[str, Any],
    detected_dates: list[str] | None,
) -> tuple[tuple[int, int, int], str, float] | None:
    """Conservatively pick the document's principal date from detected dates.

    Returns ``(parsed_date, raw_token, confidence)`` or ``None``. To avoid
    guessing on documents that contain many dates, a value is only returned
    when (a) exactly one distinct date was detected, or (b) exactly one
    detected date falls in the upload's expected period month. Everything
    else stays blank for the reviewer / AI tier.
    """
    parsed: list[tuple[tuple[int, int, int], str]] = []
    seen: set[tuple[int, int, int]] = set()
    for raw in detected_dates or []:
        candidate = _parse_detected_date(raw)
        if candidate is not None and candidate not in seen:
            seen.add(candidate)
            parsed.append((candidate, raw))
    if not parsed:
        return None
    if len(parsed) == 1:
        return parsed[0][0], parsed[0][1], 0.6

    expected = normalize_period_key(
        context.get("reported_period") or context.get("period_key")
    )
    if expected:
        year_str, month_str = expected.split("-")
        period = (int(year_str), int(month_str))
        in_period = [
            entry for entry in parsed if (entry[0][0], entry[0][1]) == period
        ]
        if len(in_period) == 1:
            return in_period[0][0], in_period[0][1], 0.7
    return None


def _full_date_label(parsed: tuple[int, int, int]) -> str:
    year, month, day = parsed
    return f"{day:02d} de {_SPANISH_MONTHS[month - 1]} de {year}"


def _date_8_digits(parsed: tuple[int, int, int]) -> str:
    year, month, day = parsed
    return f"{day:02d}{month:02d}{year:04d}"


def _participants_value(
    *, document_type: dict[str, Any], context: dict[str, Any]
) -> list[str] | None:
    """Derive the participant list from upload context.

    The provider is the subject of essentially every document type; contracts
    additionally name the client as the counterparty. Notaries, witnesses and
    other comparecientes are intentionally excluded (rulebook rule).
    """
    provider = _meaningful(context.get("provider_nomenclature")) or _meaningful(
        context.get("vendor_legal_name")
    )
    client = _meaningful(context.get("client_legal_name"))
    parties: list[str] = []
    if document_type.get("category") == "Contrato":
        if provider:
            parties.append(provider)
        if client:
            parties.append(client)
    elif provider:
        parties.append(provider)
    return parties or None


def _context_value_for_field(
    field_key: str,
    *,
    context: dict[str, Any],
    template: dict[str, Any],
    pdf_inspection: dict[str, Any],
    detected_dates: list[str] | None = None,
) -> tuple[Any, str | None, str, float]:
    """Return raw value, source, extraction method, confidence for a field."""
    document_type = template["document_type"]

    direct_context_keys = {
        "client_legal_name",
        "provider_nomenclature",
        "upload_form_month",
        "reported_period",
        "report_period",
    }
    context_value = _meaningful(context.get(field_key))
    if field_key in direct_context_keys and context_value is not None:
        return context_value, "upload_context", "upload_context", 1.0

    if field_key == "document_name":
        proposed = _meaningful(context.get("proposed_document_name"))
        if proposed is not None:
            return proposed, "upload_context", "upload_context", 1.0
        rulebook_name = _build_document_name_from_rulebook(context=context, template=template)
        if rulebook_name is not None:
            return rulebook_name, "rulebook_naming_pattern", "rulebook_fixed_value", 1.0
        return pdf_inspection["file_stem"], "pdf_filename", "local_file_inspection", 0.7

    if field_key == "pdf_file_name":
        value = _meaningful(context.get("proposed_pdf_file_name")) or pdf_inspection[
            "original_filename"
        ]
        return value, "upload_context_or_pdf_filename", "local_file_inspection", 1.0

    if field_key == "area_interna":
        return "Compliance", "rulebook_fixed_value", "rulebook_fixed_value", 1.0

    if field_key == "document_category":
        return document_type["category"], "rulebook_fixed_value", "rulebook_fixed_value", 1.0

    if field_key == "document_subtype":
        return document_type["subtype"], "rulebook_fixed_value", "rulebook_fixed_value", 1.0

    if field_key == "tags":
        tags = document_type.get("fixed_tags") or []
        if tags:
            return list(tags), "rulebook_fixed_tags", "rulebook_fixed_value", 1.0
        return None, None, "pending_human_review", 0.0

    if field_key == "document_institution_name":
        value = _meaningful(context.get("expected_institution")) or document_type.get("institution")
        return value, "upload_context_or_rulebook", "upload_context", 1.0

    if field_key == "pdf_quality_ocr":
        value = {
            "pdf_header_valid": pdf_inspection["pdf_header_valid"],
            "pypdf_readable": pdf_inspection["pypdf_readable"],
            "page_count": pdf_inspection["page_count"],
            "pdf_read_error": pdf_inspection["pdf_read_error"],
            "ocr_confirmed": False,
            "note": "No OCR performed. This is only local deterministic PDF inspection.",
        }
        return value, "local_file_inspection", "local_file_inspection", 0.8

    # ── Participant fields derived from upload context ────────────────────
    # The provider/client identities are known at upload time, so these
    # fields no longer need OCR/AI for the common case. The reviewer still
    # confirms (status stays ``*_needs_review``).
    if field_key == "participants":
        participants = _participants_value(document_type=document_type, context=context)
        if participants:
            return participants, "upload_context", "context", 0.9
        return None, None, "pending_human_review", 0.0

    if field_key in {"provider_participant", "society_participant", "taxpayer_name"}:
        provider = _meaningful(context.get("provider_nomenclature")) or _meaningful(
            context.get("vendor_legal_name")
        )
        if provider is not None:
            return provider, "upload_context", "context", 0.85
        return None, None, "pending_human_review", 0.0

    if field_key == "client_participant":
        client = _meaningful(context.get("client_legal_name"))
        if client is not None:
            return client, "upload_context", "context", 0.85
        return None, None, "pending_human_review", 0.0

    # ── Fixed description from the rulebook (e.g. CSF, TIP) ───────────────
    if field_key == "description":
        fixed = document_type.get("fixed_description")
        if fixed:
            return fixed, "rulebook_fixed_value", "rulebook_fixed_value", 1.0
        return None, None, "pending_human_review", 0.0

    # ── Date fields from conservatively-selected detected dates ───────────
    if field_key in _DETECTED_DATE_FIELDS:
        selected = _select_document_date(context=context, detected_dates=detected_dates)
        if selected is not None:
            _parsed, raw_token, confidence = selected
            return raw_token, "pdf_detected_dates", "pdf_text", confidence
        return None, None, "pending_human_review", 0.0

    if field_key in {"full_date_label", "date_8_digits"}:
        selected = _select_document_date(context=context, detected_dates=detected_dates)
        if selected is not None:
            parsed, _raw_token, confidence = selected
            value = (
                _full_date_label(parsed)
                if field_key == "full_date_label"
                else _date_8_digits(parsed)
            )
            return value, "pdf_detected_dates", "deterministic", confidence
        return None, None, "pending_human_review", 0.0

    return None, None, "pending_human_review", 0.0


def _build_review_item(
    field: dict[str, Any],
    *,
    context: dict[str, Any],
    template: dict[str, Any],
    pdf_inspection: dict[str, Any],
    field_suggestions: dict[str, dict[str, Any]] | None = None,
    detected_dates: list[str] | None = None,
) -> dict[str, Any]:
    field_key = field["key"]
    raw_value, source, extraction_method, confidence = _context_value_for_field(
        field_key,
        context=context,
        template=template,
        pdf_inspection=pdf_inspection,
        detected_dates=detected_dates,
    )
    status = "prefilled_needs_review" if raw_value is not None else "pending"
    if field_key == "pdf_quality_ocr":
        status = "deterministic_inspection_needs_review"

    reviewer_notes: str | None = None
    # Phase 3 — fill an otherwise-pending field from an AI comprehension
    # suggestion. Never overrides a deterministic value, and never an
    # approval: the status stays ``*_needs_review`` so the reviewer confirms.
    if raw_value is None and field_suggestions and field_key in field_suggestions:
        suggestion = field_suggestions[field_key]
        suggested_value = suggestion.get("value")
        if suggested_value not in (None, ""):
            raw_value = suggested_value
            source = "ai_comprehension"
            extraction_method = "ai_assisted"
            confidence = suggestion.get("confidence") or 0.0
            status = "prefilled_needs_review"
            reviewer_notes = suggestion.get("evidence") or None

    return {
        "field_key": field_key,
        "field_label": field["label"],
        "requirement_level": field["requirement_level"],
        "description": field["description"],
        "raw_value": raw_value,
        "normalized_value": raw_value,
        "reviewed_value": None,
        "status": status,
        "confidence": confidence,
        "extraction_method": extraction_method,
        "source": source,
        "human_review_required": field["human_review_required"],
        "reviewer_notes": reviewer_notes,
    }


def _fields_for_review(template: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the actionable fields (required + conditional + optional).

    De-duplicates by field key (preserving first occurrence) so a field that
    appears in more than one bucket yields a single review item.
    """
    fields: list[dict[str, Any]] = []
    seen: set[str] = set()
    for bucket in ("required", "conditional", "optional"):
        for field in template["fields"].get(bucket, []):
            key = field["key"]
            if key in seen:
                continue
            seen.add(key)
            fields.append(field)
    return fields


def _field_value(review_items: list[dict[str, Any]], field_key: str) -> Any:
    for item in review_items:
        if item["field_key"] == field_key:
            return item["raw_value"]
    return None


def _build_pdf_text_extraction(pdf_path: str | Path, template: dict[str, Any]) -> dict[str, Any]:
    inspection = inspect_pdf(Path(pdf_path).expanduser().resolve(), max_text_pages=5)
    expected_requirement = template["document_type"]["name"]
    expected_institution = template["document_type"]["institution"]
    signals = analyze_document_text(
        inspection.text_sample,
        expected_requirement=expected_requirement,
        expected_institution=expected_institution,
        expected_period="",
    )
    return {
        "pdf_text_extraction_used": True,
        "method": "pypdf_extract_text",
        "ocr_used": False,
        "text_char_count": inspection.text_char_count,
        "has_text": inspection.has_text,
        "is_probably_scanned": inspection.is_probably_scanned,
        "text_sample": inspection.text_sample,
        "signals": {
            "detected_institution": signals.detected_institution,
            "detected_document_type": signals.detected_document_type,
            "detected_rfcs": signals.detected_rfcs,
            "detected_dates": signals.detected_dates,
            "period_mentions": signals.period_mentions,
            "requirement_match_confidence": signals.requirement_match_confidence,
            "mismatch_reason": signals.mismatch_reason,
            "anomaly_codes": signals.anomaly_codes,
        },
    }


def _available_tesseract_languages() -> list[str]:
    tesseract = shutil.which("tesseract")
    if not tesseract:
        return []
    try:
        result = subprocess.run(
            [tesseract, "--list-langs"],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip() and not line.startswith("List of available languages")
    ]


def _preferred_ocr_language() -> str | None:
    languages = set(_available_tesseract_languages())
    if {"spa", "eng"}.issubset(languages):
        return "spa+eng"
    if "spa" in languages:
        return "spa"
    if "eng" in languages:
        return "eng"
    return sorted(languages)[0] if languages else None


def _run_local_tesseract_ocr(
    pdf_path: str | Path,
    *,
    max_pages: int = 3,
) -> dict[str, Any]:
    tesseract = shutil.which("tesseract")
    pdftoppm = shutil.which("pdftoppm")
    if not tesseract or not pdftoppm:
        missing = [
            name
            for name, path in (("tesseract", tesseract), ("pdftoppm", pdftoppm))
            if not path
        ]
        return {
            "ocr_used": False,
            "status": "not_configured",
            "engine": "tesseract",
            "reason": f"Missing local OCR dependency: {', '.join(missing)}",
            "install_hint": "brew install tesseract tesseract-lang poppler",
            "ocr_recommended": None,
        }

    language = _preferred_ocr_language()
    with tempfile.TemporaryDirectory(prefix="checkwise-local-ocr-") as temp_dir:
        prefix = Path(temp_dir) / "page"
        try:
            subprocess.run(
                [
                    pdftoppm,
                    "-f",
                    "1",
                    "-l",
                    str(max_pages),
                    "-r",
                    "200",
                    "-png",
                    str(Path(pdf_path).expanduser().resolve()),
                    str(prefix),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=90,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return {
                "ocr_used": False,
                "status": "failed",
                "engine": "tesseract",
                "reason": f"PDF rasterization failed: {exc}",
                "ocr_recommended": None,
            }

        images = sorted(Path(temp_dir).glob("page-*.png"))
        if not images:
            return {
                "ocr_used": False,
                "status": "failed",
                "engine": "tesseract",
                "reason": "PDF rasterization produced no page images.",
                "ocr_recommended": None,
            }

        text_parts: list[str] = []
        errors: list[str] = []
        for image in images:
            command = [tesseract, str(image), "stdout"]
            if language:
                command.extend(["-l", language])
            try:
                result = subprocess.run(
                    command,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=90,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                errors.append(f"{image.name}: {exc}")
                continue
            if result.stdout.strip():
                text_parts.append(result.stdout.strip())

    extracted_text = "\n\n".join(text_parts).strip()
    return {
        "ocr_used": True,
        "status": "completed" if extracted_text else "completed_no_text",
        "engine": "tesseract",
        "language": language,
        "page_count_processed": len(images),
        "text_char_count": len(extracted_text),
        "text_sample": extracted_text[:OCR_TEXT_SAMPLE_LIMIT],
        "errors": errors,
        "ocr_recommended": None,
    }


def _build_ocr_status(
    text_extraction: dict[str, Any],
    *,
    pdf_path: str | Path,
    enable_ocr: bool,
) -> dict[str, Any]:
    ocr_recommended = bool(text_extraction["is_probably_scanned"])
    if enable_ocr:
        result = _run_local_tesseract_ocr(pdf_path)
        result["ocr_recommended"] = ocr_recommended
        return result
    return {
        "ocr_used": False,
        "status": "not_configured",
        "engine": None,
        "reason": (
            "No local OCR engine is configured. Install/configure an OCR service before enabling "
            "image-based extraction."
        ),
        "ocr_recommended": ocr_recommended,
    }


def _build_ai_extraction_request(
    *,
    context: dict[str, Any],
    template: dict[str, Any],
    review_items: list[dict[str, Any]],
    text_extraction: dict[str, Any],
    ocr_status: dict[str, Any] | None = None,
    suggestions_applied: bool = False,
) -> dict[str, Any]:
    field_schema = [
        {
            "field_key": item["field_key"],
            "field_label": item["field_label"],
            "requirement_level": item["requirement_level"],
            "current_value": item["raw_value"],
            "status": item["status"],
            "human_review_required": item["human_review_required"],
        }
        for item in review_items
    ]
    text_sample = text_extraction["text_sample"]
    if ocr_status and ocr_status.get("text_sample"):
        text_sample = "\n\n".join(
            part for part in [text_sample, ocr_status["text_sample"]] if part
        )

    return {
        "ai_used": False,
        # Phase 3 — when the deep comprehension tier already supplied
        # suggestions (the live path), the standalone n8n AI node is
        # superseded: the in-house pass is the AI source. The envelope is
        # still emitted (CLI/dry-run with no suggestions keep the original
        # hand-off) but flagged so consumers don't double-call a model.
        "status": (
            "fulfilled_by_comprehension" if suggestions_applied else "ready_for_n8n_ai_node"
        ),
        "recommended_model_policy": (
            "Use a model configured in n8n credentials; keep output JSON-only."
        ),
        "system_prompt": (
            "You assist CheckWise reviewers by suggesting metadata from document text. "
            "Do not approve legal sufficiency. Do not invent values. Return only JSON."
        ),
        "user_payload": {
            "task": "Suggest metadata values for pending review fields.",
            "document_type": template["document_type"],
            "context": context,
            "fields": field_schema,
            "text_sample": text_sample[:OCR_TEXT_SAMPLE_LIMIT],
            "ocr_status": ocr_status,
            "output_contract": {
                "field_suggestions": [
                    {
                        "field_key": "string",
                        "suggested_value": "string | array | object | null",
                        "evidence": "short quote or explanation from supplied text",
                        "confidence": "number between 0 and 1",
                        "requires_human_review": True,
                    }
                ],
                "document_level_notes": ["string"],
                "cannot_determine": ["field_key"],
            },
        },
    }


def _build_google_sheets_row(
    *,
    payload: dict[str, Any],
    review_items: list[dict[str, Any]],
    text_extraction: dict[str, Any] | None,
) -> dict[str, Any]:
    pending_fields = [item["field_key"] for item in review_items if item["status"] == "pending"]
    prefilled_fields = [item["field_key"] for item in review_items if item["status"] != "pending"]
    deterministic = payload["deterministic_file_metadata"]
    safety = payload["safety"]
    template_doc = payload["template"]["document_type"]
    return {
        "generated_at": payload["generated_at"],
        "metadata_rules_version": payload["metadata_rules_version"],
        "document_type_code": payload["document_type_code"],
        "document_type_name": template_doc["name"],
        "institution": template_doc["institution"],
        "client_legal_name": payload["context"].get("client_legal_name"),
        "provider_nomenclature": payload["context"].get("provider_nomenclature"),
        "document_name": _field_value(review_items, "document_name"),
        "document_category": _field_value(review_items, "document_category"),
        "document_subtype": _field_value(review_items, "document_subtype"),
        "upload_form_month": _field_value(review_items, "upload_form_month"),
        "reported_period": _field_value(review_items, "reported_period"),
        "original_filename": deterministic["original_filename"],
        "sha256": deterministic["sha256"],
        "page_count": deterministic["page_count"],
        "pdf_header_valid": deterministic["pdf_header_valid"],
        "pypdf_readable": deterministic["pypdf_readable"],
        "validation_status": payload["validation_result"]["status"],
        "review_item_count": payload["review_item_count"],
        "prefilled_review_fields": ", ".join(prefilled_fields),
        "pending_review_fields": ", ".join(pending_fields),
        "human_review_required": safety["human_review_required"],
        "legal_approval_allowed": safety["legal_approval_allowed"],
        "ocr_used": safety["ocr_used"],
        "ai_used": safety["ai_used"],
        "google_sheets_used": safety["google_sheets_used"],
        "pdf_text_extraction_used": bool(text_extraction),
        "pdf_text_char_count": (text_extraction or {}).get("text_char_count"),
        "is_probably_scanned": (text_extraction or {}).get("is_probably_scanned"),
    }


def build_pdf_metadata_dry_run_payload(
    *,
    pdf_path: str | Path,
    document_type_code: str,
    context: dict[str, Any] | None = None,
    include_intelligence: bool = False,
    enable_ocr: bool = False,
    precomputed_text_extraction: dict[str, Any] | None = None,
    field_suggestions: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a review payload for one PDF using the real metadata rulebook.

    ``precomputed_text_extraction`` lets a caller that already extracted the
    PDF text and ran the pre-validation classifier (i.e. the live intake path)
    hand those results in, so this function does not re-open the PDF and
    re-run ``analyze_document_text`` a second time. It must match the shape
    returned by ``_build_pdf_text_extraction``. When ``None`` (CLI / dry-run /
    tests) the text is extracted here exactly as before.

    ``field_suggestions`` (Phase 3) maps ``field_key -> {value, confidence,
    evidence}`` produced by the deep comprehension tier. Pending
    ``ai_assisted`` fields are prefilled from it as ``prefilled_needs_review``
    — never an approval. When ``None`` the fields stay blank exactly as before.
    """
    context = _compact_context(dict(context or {}))
    pdf_inspection = inspect_local_pdf(pdf_path)
    template = n8n_template_for_document_type(document_type_code)
    rulebook_problems = validate_metadata_rulebook()

    context.setdefault("document_type_code", document_type_code)
    context.setdefault("expected_document_type_code", document_type_code)
    context.setdefault("original_filename", pdf_inspection["original_filename"])
    context.setdefault("sha256", pdf_inspection["sha256"])
    context.setdefault("mime_type", pdf_inspection["mime_type"])
    context.setdefault("size_bytes", pdf_inspection["size_bytes"])
    context.setdefault("page_count", pdf_inspection["page_count"])

    safety = {
        "legal_approval_allowed": False,
        "ocr_used": False,
        "ai_used": False,
        "google_sheets_used": False,
        "external_services_used": False,
        "db_used": False,
        "production_upload_flow_used": False,
        "human_review_required": True,
    }

    # Build the text-extraction package first so its detected dates are
    # available to the deterministic date derivation below.
    text_extraction: dict[str, Any] | None = None
    ocr_status: dict[str, Any] | None = None
    detected_dates: list[str] = []
    if include_intelligence:
        if precomputed_text_extraction is not None:
            text_extraction = precomputed_text_extraction
        else:
            text_extraction = _build_pdf_text_extraction(pdf_path, template)
        detected_dates = list((text_extraction.get("signals") or {}).get("detected_dates") or [])
        ocr_status = _build_ocr_status(
            text_extraction,
            pdf_path=pdf_path,
            enable_ocr=enable_ocr,
        )
        safety["ocr_used"] = bool(ocr_status["ocr_used"])

    # Build review items for every field the reviewer can act on: required,
    # conditional and optional. Conditional/optional fields were previously
    # skipped entirely, which silently dropped both deterministic values and
    # AI suggestions for them (e.g. ``description``). ``blank`` fields stay
    # out — the rulebook says they are intentionally empty.
    review_items = [
        _build_review_item(
            field,
            context=context,
            template=template,
            pdf_inspection=pdf_inspection,
            field_suggestions=field_suggestions,
            detected_dates=detected_dates,
        )
        for field in _fields_for_review(template)
    ]

    validation_errors: list[str] = []
    if rulebook_problems:
        validation_errors.extend(rulebook_problems)
    if template["controls"]["legal_approval_allowed"]:
        validation_errors.append("Rulebook template unexpectedly allows legal approval")
    if safety["ocr_used"] and not enable_ocr:
        validation_errors.append("OCR ran even though enable_ocr was false")
    if safety["ai_used"] or safety["google_sheets_used"]:
        validation_errors.append("Dry run safety controls were violated")
    if not pdf_inspection["pdf_header_valid"]:
        validation_errors.append("File does not start with a valid PDF header")

    validation_result = {
        "status": "passed" if not validation_errors else "needs_review",
        "checked_at": _utc_now_iso(),
        "errors": validation_errors,
        "checks": [
            "real metadata_rules.py imported",
            f"rulebook version is {RULEBOOK_VERSION}",
            "local PDF inspected deterministically",
            "legal approval disabled",
            (
                "local OCR completed"
                if safety["ocr_used"]
                else "OCR disabled" if not enable_ocr else "OCR requested but not completed"
            ),
            "AI disabled",
            "Google Sheets disabled",
            "production upload/submission flow not used",
            "human review required",
        ],
    }

    payload = {
        "payload_type": PAYLOAD_TYPE,
        "generated_at": _utc_now_iso(),
        "metadata_rules_version": template["rulebook"]["version"],
        "document_type_code": document_type_code,
        "submission_id": context.get("submission_id"),
        "document_id": context.get("document_id"),
        "context": context,
        "template": template,
        "review_item_count": len(review_items),
        "review_items": review_items,
        "deterministic_file_metadata": pdf_inspection,
        "safety": safety,
        "validation_result": validation_result,
    }
    if include_intelligence:
        if text_extraction is None or ocr_status is None:
            raise RuntimeError("Intelligence package was requested but not prepared.")
        payload["intelligence"] = {
            "pdf_text_extraction": text_extraction,
            "ocr": ocr_status,
            "ai_extraction_request": _build_ai_extraction_request(
                context=context,
                template=template,
                review_items=review_items,
                text_extraction=text_extraction,
                ocr_status=ocr_status,
                suggestions_applied=bool(field_suggestions),
            ),
            "google_sheets": {
                "google_sheets_used": False,
                "status": "row_ready_for_n8n_google_sheets_node",
                "row": _build_google_sheets_row(
                    payload=payload,
                    review_items=review_items,
                    text_extraction=text_extraction,
                ),
            },
        }
    return payload


def list_document_type_codes() -> list[str]:
    return [rule.code for rule in all_metadata_rules(include_annexes=True)]


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a local CheckWise metadata dry-run payload for one PDF."
    )
    parser.add_argument("--pdf", help="Path to a local PDF to inspect.")
    parser.add_argument("--document-type", help="Metadata rule code, e.g. acuse_sisub.")
    parser.add_argument("--context-json", help="Optional upload/context JSON file.")
    parser.add_argument("--output", help="Optional output JSON path. Prints to stdout if omitted.")
    parser.add_argument(
        "--list-document-types",
        action="store_true",
        help="List document type codes from the real metadata rulebook and exit.",
    )
    parser.add_argument(
        "--validate-rulebook",
        action="store_true",
        help="Validate the real metadata rulebook before running.",
    )
    parser.add_argument(
        "--include-intelligence",
        action="store_true",
        help="Include PDF text, OCR status, AI request, and Google Sheets row packages.",
    )
    parser.add_argument(
        "--enable-ocr",
        action="store_true",
        help="Run local Tesseract OCR when --include-intelligence is also set.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])

    if args.list_document_types:
        for code in list_document_type_codes():
            print(code)
        return 0

    if args.validate_rulebook:
        problems = validate_metadata_rulebook()
        if problems:
            print(json.dumps({"status": "failed", "problems": problems}, indent=2), file=sys.stderr)
            return 2

    if not args.pdf or not args.document_type:
        print(
            "ERROR: --pdf and --document-type are required unless listing types.",
            file=sys.stderr,
        )
        return 2

    context: dict[str, Any] = {}
    if args.context_json:
        context = _read_json_file(Path(args.context_json).expanduser())

    try:
        payload = build_pdf_metadata_dry_run_payload(
            pdf_path=args.pdf,
            document_type_code=args.document_type,
            context=context,
            include_intelligence=args.include_intelligence,
            enable_ocr=args.enable_ocr,
        )
    except UnknownDocumentTypeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    output_text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        output_path = Path(args.output).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output_text + "\n", encoding="utf-8")
        print(f"Wrote local PDF metadata dry-run payload: {output_path}")
    else:
        print(output_text)

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
