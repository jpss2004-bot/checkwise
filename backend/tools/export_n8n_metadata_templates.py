#!/usr/bin/env python3
"""Export static CheckWise metadata rulebook templates for n8n prototypes.

This script intentionally performs no OCR, no AI calls, no database writes, and
no Google Sheets writes. It only converts the static metadata rulebook catalog
into JSON files that n8n can consume while the workflow is being prototyped.

Typical usage from the backend folder:

    python tools/export_n8n_metadata_templates.py --list
    python tools/export_n8n_metadata_templates.py --document-type acuse_sisub --stdout
    python tools/export_n8n_metadata_templates.py --all --output tmp/n8n_templates
    python tools/export_n8n_metadata_templates.py --all --single-file \
      --output tmp/n8n_templates/checkwise_n8n_metadata_templates.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

try:
    from app.core.metadata_rules import (  # noqa: E402
        RULEBOOK_SOURCE,
        RULEBOOK_TITLE,
        RULEBOOK_VERSION,
        UnknownDocumentTypeError,
        all_metadata_rules,
        n8n_template_for_document_type,
        validate_metadata_rulebook,
    )
except ModuleNotFoundError as exc:  # pragma: no cover - defensive CLI message
    raise SystemExit(
        "Could not import app.core.metadata_rules. Apply the metadata rulebook "
        "catalog patch first, then run this exporter from the backend folder "
        "or the full CheckWise repo root."
    ) from exc

TEMPLATE_SCHEMA_VERSION = "2026.05.n8n-template-v1"
DEFAULT_OUTPUT_DIR = Path("tmp/n8n_metadata_templates")


def utc_now_iso() -> str:
    """Return an export timestamp in stable ISO-8601 UTC format."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def compact_rule_summary(rule_dict: dict[str, Any]) -> dict[str, Any]:
    """Return the small catalog row that n8n can use in dropdowns or routing."""
    return {
        "code": rule_dict["code"],
        "name": rule_dict["name"],
        "group": rule_dict["group"],
        "category": rule_dict["category"],
        "subtype": rule_dict["subtype"],
        "institution": rule_dict["institution"],
        "frequency": rule_dict["frequency"],
        "hierarchy": rule_dict["hierarchy"],
        "human_review_required": rule_dict["human_review_required"],
        "legal_approval_allowed": rule_dict["legal_approval_allowed"],
    }


def field_keys_by_bucket(template: dict[str, Any]) -> dict[str, list[str]]:
    """Return field keys split by requirement bucket."""
    fields = template["fields"]
    return {
        "required": [field["key"] for field in fields["required"]],
        "optional": [field["key"] for field in fields["optional"]],
        "conditional": [field["key"] for field in fields["conditional"]],
        "blank": [field["key"] for field in fields["blank"]],
    }


def build_n8n_export_template(
    document_type_code: str,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build one deterministic n8n-ready template for a document type.

    The result is a JSON contract. It does not contain real extracted provider
    data, and it does not attempt to parse a PDF.
    """
    base_template = n8n_template_for_document_type(document_type_code)
    rule = base_template["document_type"]
    generated_at = generated_at or utc_now_iso()
    field_order = field_keys_by_bucket(base_template)

    return {
        "template_kind": "checkwise_n8n_metadata_template",
        "schema_version": TEMPLATE_SCHEMA_VERSION,
        "generated_at": generated_at,
        "rulebook": base_template["rulebook"],
        "document_type": rule,
        "fields": base_template["fields"],
        "field_order": field_order,
        "n8n": {
            "purpose": (
                "Use this template to build a deterministic metadata extraction "
                "review item after a CheckWise upload has been received."
            ),
            "recommended_workflow_stage": "after_upload_before_ocr_ai_or_sheets",
            "input_context_contract": {
                "required_context_keys": [
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
                ],
                "conditional_context_keys": [
                    "upload_form_month",
                    "reported_period",
                    "expected_document_type_code",
                    "expected_institution",
                ],
                "optional_context_keys": [
                    "source_form",
                    "source_row_id",
                    "mime_type",
                    "size_bytes",
                    "page_count",
                    "storage_key",
                    "file_url_for_reviewer",
                ],
            },
            "output_item_contract": {
                "one_item_per": "metadata_field",
                "suggested_item_shape": {
                    "submission_id": "string_from_context",
                    "document_id": "string_from_context",
                    "document_type_code": rule["code"],
                    "field_key": "string_from_template",
                    "field_label": "string_from_template",
                    "requirement_level": "required_optional_conditional_or_blank",
                    "raw_value": None,
                    "normalized_value": None,
                    "confidence": 0.0,
                    "extraction_method": "template_only",
                    "source_page": None,
                    "source_text_snippet": None,
                    "review_status": "pending",
                    "reviewed_value": None,
                    "review_notes": None,
                },
            },
            "review_controls": {
                "human_review_required": rule["human_review_required"],
                "legal_approval_allowed": rule["legal_approval_allowed"],
                "metadata_review_status_default": "pending",
                "compliance_approval_status_default": "not_evaluated",
                "final_approval_must_be_human": True,
            },
        },
        "safety_controls": base_template["controls"],
        "warnings": [
            "This template does not extract document content.",
            "This template must not be treated as legal approval.",
            "n8n should orchestrate the workflow; the CheckWise rulebook remains the source of truth.",
            "Do not add live Google Sheets writes until review/export rules are explicitly approved.",
        ],
    }


def build_catalog_index(*, include_annexes: bool, generated_at: str | None = None) -> dict[str, Any]:
    """Build a compact index for n8n routing/dropdown use."""
    generated_at = generated_at or utc_now_iso()
    rules = all_metadata_rules(include_annexes=include_annexes)
    return {
        "template_kind": "checkwise_n8n_metadata_template_index",
        "schema_version": TEMPLATE_SCHEMA_VERSION,
        "generated_at": generated_at,
        "rulebook": {
            "source": RULEBOOK_SOURCE,
            "version": RULEBOOK_VERSION,
            "title": RULEBOOK_TITLE,
        },
        "include_annexes": include_annexes,
        "document_type_count": len(rules),
        "document_types": [compact_rule_summary(rule.to_dict()) for rule in rules],
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write a UTF-8 pretty JSON file, creating parent folders as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def export_one(document_type_code: str, output: Path | None, *, stdout: bool) -> int:
    """Export one document type template."""
    payload = build_n8n_export_template(document_type_code)
    if stdout:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    output_path = output or DEFAULT_OUTPUT_DIR / "document_types" / f"{document_type_code}.json"
    write_json(output_path, payload)
    print(f"Wrote {output_path}")
    return 0


def export_all(
    output: Path,
    *,
    include_annexes: bool,
    single_file: bool,
    stdout: bool,
) -> int:
    """Export all document type templates."""
    generated_at = utc_now_iso()
    rules = all_metadata_rules(include_annexes=include_annexes)
    templates = [
        build_n8n_export_template(rule.code, generated_at=generated_at)
        for rule in rules
    ]
    index = build_catalog_index(include_annexes=include_annexes, generated_at=generated_at)

    if single_file:
        payload = {
            "template_kind": "checkwise_n8n_metadata_template_bundle",
            "schema_version": TEMPLATE_SCHEMA_VERSION,
            "generated_at": generated_at,
            "index": index,
            "templates": templates,
        }
        if stdout:
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        output_path = output
        if output_path.suffix.lower() != ".json":
            output_path = output_path / "checkwise_n8n_metadata_templates.json"
        write_json(output_path, payload)
        print(f"Wrote {output_path}")
        return 0

    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "catalog_index.json", index)
    for template in templates:
        code = template["document_type"]["code"]
        write_json(output / "document_types" / f"{code}.json", template)
    print(f"Wrote {len(templates)} templates under {output}")
    return 0


def list_document_types(*, include_annexes: bool) -> int:
    """Print available document type codes."""
    for rule in all_metadata_rules(include_annexes=include_annexes):
        print(f"{rule.code}\t{rule.name}")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Export static CheckWise metadata rulebook JSON templates for n8n."
    )
    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument(
        "--list",
        action="store_true",
        help="List available document type codes and names.",
    )
    action_group.add_argument(
        "--document-type",
        help="Export one document type template by code, for example acuse_sisub.",
    )
    action_group.add_argument(
        "--all",
        action="store_true",
        help="Export templates for all principal document types.",
    )
    parser.add_argument(
        "--include-annexes",
        action="store_true",
        help="Include explicit annex document type rules when exporting or listing.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output file or directory. Defaults to tmp/n8n_metadata_templates.",
    )
    parser.add_argument(
        "--single-file",
        action="store_true",
        help="With --all, write one JSON bundle instead of many files.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print JSON to stdout instead of writing files.",
    )
    parser.add_argument(
        "--validate-rulebook",
        action="store_true",
        help="Validate the static rulebook before exporting.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    args = parse_args(argv or sys.argv[1:])

    if args.validate_rulebook:
        problems = validate_metadata_rulebook()
        if problems:
            for problem in problems:
                print(f"ERROR: {problem}", file=sys.stderr)
            return 2

    try:
        if args.list:
            return list_document_types(include_annexes=args.include_annexes)
        if args.document_type:
            return export_one(args.document_type, args.output, stdout=args.stdout)
        if args.all:
            output = args.output or DEFAULT_OUTPUT_DIR
            return export_all(
                output,
                include_annexes=args.include_annexes,
                single_file=args.single_file,
                stdout=args.stdout,
            )
    except UnknownDocumentTypeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
