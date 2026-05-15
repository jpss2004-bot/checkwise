#!/usr/bin/env python3
"""Build local n8n review payload fixtures from CheckWise metadata templates.

This tool is intentionally offline and deterministic. It performs no database
writes, no OCR, no AI calls, and no Google Sheets writes. It only combines:

1. a fake/local upload context JSON, and
2. the static metadata rulebook template for a document type,

into a review payload that n8n can use while the workflow is being designed.

Typical usage from the backend folder:

    python tools/build_n8n_review_payload.py \
      --context fixtures/n8n/sample_upload_context_acuse_sisub.json \
      --stdout

    python tools/build_n8n_review_payload.py \
      --context fixtures/n8n/sample_upload_context_acuse_sisub.json \
      --output tmp/n8n_review_payloads/acuse_sisub_review_payload.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

try:
    from app.core.metadata_rules import (  # noqa: E402
        UnknownDocumentTypeError,
        metadata_rule_by_code,
    )
    from tools.export_n8n_metadata_templates import (  # noqa: E402
        build_n8n_export_template,
        utc_now_iso,
    )
except ModuleNotFoundError as exc:  # pragma: no cover - defensive CLI message
    raise SystemExit(
        "Could not import the metadata rulebook/exporter. Apply the rulebook and "
        "n8n template exporter patches first, then run this tool from the backend "
        "folder or the full CheckWise repo root."
    ) from exc

REVIEW_PAYLOAD_SCHEMA_VERSION = "2026.05.n8n-review-fixture-v1"
DEFAULT_OUTPUT_DIR = Path("tmp/n8n_review_payloads")

# These keys are operational context, not PDF-extracted metadata. They should be
# available from the upload/submission event or from a local test fixture.
FALLBACK_REQUIRED_CONTEXT_KEYS = [
    "submission_id",
    "document_id",
    "client_id",
    "client_legal_name",
    "vendor_id",
    "vendor_legal_name",
    "provider_nomenclature",
    "requirement_id",
    "period_id",
    "original_filename",
    "sha256",
    "uploaded_at",
]

# These metadata fields can be safely populated from context/rulebook defaults in
# this patch. Anything requiring PDF text/OCR/AI remains blank and pending review.
CONTEXT_FIELD_KEYS = {
    "client_legal_name",
    "provider_nomenclature",
    "upload_form_month",
    "reported_period",
    "report_period",
    "report_upload_date",
    "annexes",
    "prior_registration_annexes",
    "is_current_for_report_year",
}

RULEBOOK_DEFAULT_FIELD_KEYS = {
    "area_interna",
    "document_category",
    "document_subtype",
    "tags",
    "related_documents",
}

PROPOSED_CONTEXT_FIELD_ALIASES = {
    "document_name": "proposed_document_name",
    "pdf_file_name": "proposed_pdf_file_name",
    "full_date_label": "proposed_full_date_label",
    "date_8_digits": "proposed_date_8_digits",
}


def read_json(path: Path) -> dict[str, Any]:
    """Read a JSON object from disk."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"Context file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in context file {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"Context file must contain one JSON object: {path}")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write a UTF-8 pretty JSON file, creating parent folders as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def infer_document_type_code(context: dict[str, Any], explicit_code: str | None) -> str:
    """Resolve the document type code from CLI argument or upload context."""
    code = explicit_code or context.get("document_type_code") or context.get("expected_document_type_code")
    if not isinstance(code, str) or not code.strip():
        raise SystemExit(
            "Missing document type. Provide --document-type or include "
            "document_type_code/expected_document_type_code in the context JSON."
        )
    return code.strip()


def required_context_keys_from_template(template: dict[str, Any]) -> list[str]:
    """Read required context keys from the n8n template contract."""
    try:
        keys = template["n8n"]["input_context_contract"]["required_context_keys"]
    except KeyError:
        return list(FALLBACK_REQUIRED_CONTEXT_KEYS)
    if not isinstance(keys, list):
        return list(FALLBACK_REQUIRED_CONTEXT_KEYS)
    return [str(key) for key in keys]


def validate_upload_context(context: dict[str, Any], required_keys: list[str]) -> list[str]:
    """Return validation errors for missing/blank required context values."""
    errors: list[str] = []
    for key in required_keys:
        value = context.get(key)
        if value is None or value == "":
            errors.append(f"Missing required context key: {key}")
    return errors


def field_buckets(template: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Return fields flattened with their requirement bucket."""
    fields = template["fields"]
    rows: list[tuple[str, dict[str, Any]]] = []
    for bucket in ("required", "optional", "conditional", "blank"):
        for field in fields.get(bucket, []):
            rows.append((bucket, field))
    return rows


def suggested_value_for_field(
    field_key: str,
    *,
    context: dict[str, Any],
    document_type: dict[str, Any],
) -> tuple[Any, str, float, str]:
    """Return value, method, confidence, and note for template-only review items.

    This function deliberately does not inspect file content. It only copies safe
    context values or deterministic rulebook defaults. Unknown fields are left
    blank for human/OCR/AI stages later.
    """
    if field_key in context and context[field_key] not in (None, ""):
        return context[field_key], "context", 1.0, "Copied from upload context fixture."

    alias_key = PROPOSED_CONTEXT_FIELD_ALIASES.get(field_key)
    if alias_key and context.get(alias_key) not in (None, ""):
        return (
            context[alias_key],
            "context_proposed_value",
            0.8,
            "Proposed by local fixture only; reviewer must confirm.",
        )

    if field_key == "area_interna":
        return "Compliance", "rulebook_default", 1.0, "Static value defined by metadata rulebook."
    if field_key == "document_category":
        return document_type["category"], "rulebook_default", 1.0, "Copied from document type rule."
    if field_key == "document_subtype":
        return document_type["subtype"], "rulebook_default", 1.0, "Copied from document type rule."
    if field_key == "tags":
        return document_type.get("fixed_tags", []), "rulebook_default", 1.0, "Copied from document type rule."
    if field_key == "related_documents":
        return "", "rulebook_blank", 1.0, "PDF commonly instructs this field to remain blank/N/A."

    if field_key in CONTEXT_FIELD_KEYS:
        return None, "missing_context", 0.0, "Expected from context later; not present in this fixture."
    if field_key in RULEBOOK_DEFAULT_FIELD_KEYS:
        return None, "missing_rulebook_default", 0.0, "Expected rulebook default was unavailable."

    return None, "template_only", 0.0, "No OCR, PDF parsing, AI, or human correction performed in this patch."


def review_status_for_field(field: dict[str, Any], value: Any, method: str) -> str:
    """Return a conservative review status for one item."""
    if field.get("requirement_level") == "blank" and value == "":
        return "not_required"
    if field.get("human_review_required") is False and method in {"context", "rulebook_default", "rulebook_blank"}:
        return "context_ready"
    return "pending"


def build_review_items(
    *,
    context: dict[str, Any],
    template: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build one review item per metadata field in the selected template."""
    document_type = template["document_type"]
    review_items: list[dict[str, Any]] = []
    for bucket, field in field_buckets(template):
        field_key = field["key"]
        value, method, confidence, note = suggested_value_for_field(
            field_key,
            context=context,
            document_type=document_type,
        )
        review_items.append(
            {
                "submission_id": context["submission_id"],
                "document_id": context["document_id"],
                "client_id": context["client_id"],
                "vendor_id": context["vendor_id"],
                "requirement_id": context["requirement_id"],
                "period_id": context["period_id"],
                "document_type_code": document_type["code"],
                "field_key": field_key,
                "field_label": field["label"],
                "requirement_level": bucket,
                "field_description": field["description"],
                "allowed_extraction_methods": field["extraction_methods"],
                "raw_value": value,
                "normalized_value": value,
                "confidence": confidence,
                "extraction_method": method,
                "source_page": None,
                "source_text_snippet": None,
                "review_status": review_status_for_field(field, value, method),
                "reviewed_value": None,
                "reviewer_decision": None,
                "review_notes": note,
                "human_review_required": field["human_review_required"],
            }
        )
    return review_items


def summarize_review_items(review_items: list[dict[str, Any]]) -> dict[str, Any]:
    """Return counts useful for n8n assertions and manual inspection."""
    by_status: dict[str, int] = {}
    by_requirement: dict[str, int] = {}
    for item in review_items:
        by_status[item["review_status"]] = by_status.get(item["review_status"], 0) + 1
        by_requirement[item["requirement_level"]] = by_requirement.get(item["requirement_level"], 0) + 1
    return {
        "review_item_count": len(review_items),
        "review_status_counts": by_status,
        "requirement_level_counts": by_requirement,
        "pending_count": by_status.get("pending", 0),
        "context_ready_count": by_status.get("context_ready", 0),
        "not_required_count": by_status.get("not_required", 0),
    }


def build_n8n_review_payload(
    *,
    context: dict[str, Any],
    document_type_code: str,
    context_source: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic n8n review payload from upload context + rulebook."""
    generated_at = generated_at or utc_now_iso()
    template = build_n8n_export_template(document_type_code, generated_at=generated_at)
    document_type = template["document_type"]
    required_keys = required_context_keys_from_template(template)
    context_errors = validate_upload_context(context, required_keys)
    if context_errors:
        raise ValueError("Invalid upload context: " + "; ".join(context_errors))

    # Validate the document type early for clearer failures if the exporter changes.
    metadata_rule_by_code(document_type_code)

    review_items = build_review_items(context=context, template=template)
    return {
        "payload_kind": "checkwise_n8n_review_payload_fixture",
        "schema_version": REVIEW_PAYLOAD_SCHEMA_VERSION,
        "generated_at": generated_at,
        "source": {
            "context_source": context_source,
            "template_schema_version": template["schema_version"],
            "rulebook": template["rulebook"],
        },
        "workflow_stage": "local_fixture_after_upload_before_ocr_ai_sheets",
        "upload_context": context,
        "document_type": document_type,
        "routing": {
            "n8n_route_key": document_type["code"],
            "institution": document_type["institution"],
            "frequency": document_type["frequency"],
            "group": document_type["group"],
            "requires_human_review": document_type["human_review_required"],
            "legal_approval_allowed": False,
        },
        "review_items": review_items,
        "summary": summarize_review_items(review_items),
        "safety_controls": {
            "no_db_migration_in_this_patch": True,
            "no_ocr_in_this_patch": True,
            "no_ai_in_this_patch": True,
            "no_google_sheets_in_this_patch": True,
            "no_file_content_extraction_in_this_patch": True,
            "final_approval_must_be_human": True,
        },
        "warnings": [
            "This is a local fixture payload for n8n workflow design only.",
            "Values with extraction_method=template_only are intentionally blank.",
            "Do not treat this payload as legal approval or compliance approval.",
            "Do not connect this fixture directly to Google Sheets until export rules are approved.",
        ],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Build local CheckWise n8n review payload fixtures from upload context JSON."
    )
    parser.add_argument(
        "--context",
        type=Path,
        required=True,
        help="Path to a local fake upload context JSON file.",
    )
    parser.add_argument(
        "--document-type",
        help="Optional document type code. Defaults to document_type_code in the context JSON.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSON file. Defaults to tmp/n8n_review_payloads/<document_type>_review_payload.json.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print JSON to stdout instead of writing a file.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    args = parse_args(argv or sys.argv[1:])
    context = read_json(args.context)
    document_type_code = infer_document_type_code(context, args.document_type)

    try:
        payload = build_n8n_review_payload(
            context=context,
            document_type_code=document_type_code,
            context_source=str(args.context),
        )
    except UnknownDocumentTypeError as exc:
        raise SystemExit(str(exc)) from exc
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    if args.stdout:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    output_path = args.output or DEFAULT_OUTPUT_DIR / f"{document_type_code}_review_payload.json"
    write_json(output_path, payload)
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
