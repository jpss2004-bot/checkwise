#!/usr/bin/env python3
"""Export CheckWise PDF metadata review rows to CSV or XLSX.

This is the native replacement for the n8n spreadsheet prototype. It uses the
real CheckWise metadata rulebook plus the local PDF dry-run builder, then emits
one spreadsheet row per metadata field. No database writes, AI calls, Google
Sheets calls, or legal approvals happen here.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import zipfile
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.metadata_rules import (  # noqa: E402
    UnknownDocumentTypeError,
    validate_metadata_rulebook,
)
from tools.test_pdf_metadata_dry_run import (  # noqa: E402
    build_pdf_metadata_dry_run_payload,
)

METADATA_TABLE_SCHEMA_VERSION = "2026.05.native-metadata-table-v1"

FIELD_ROW_COLUMNS = [
    "schema_version",
    "generated_at",
    "metadata_rules_version",
    "submission_id",
    "document_id",
    "document_type_code",
    "document_type_name",
    "institution",
    "client_legal_name",
    "provider_nomenclature",
    "original_filename",
    "sha256",
    "page_count",
    "validation_status",
    "detected_institution",
    "detected_document_type",
    "detected_rfcs",
    "detected_dates",
    "period_mentions",
    "requirement_match_confidence",
    "mismatch_reason",
    "anomaly_codes",
    "ocr_status",
    "ocr_used",
    "field_key",
    "field_label",
    "requirement_level",
    "allowed_extraction_methods",
    "raw_value",
    "normalized_value",
    "confidence",
    "extraction_method",
    "source",
    "review_status",
    "human_review_required",
    "reviewer_notes",
]


def _read_json_file(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Context JSON must contain an object: {path}")
    return payload


def _json_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _field_rows_from_template(payload: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Return all rulebook fields, enriched with any extracted review item."""
    items_by_key = {item["field_key"]: item for item in payload["review_items"]}
    rows: list[tuple[str, dict[str, Any]]] = []
    for bucket in ("required", "conditional", "optional", "blank"):
        for field in payload["template"]["fields"].get(bucket, []):
            item = dict(items_by_key.get(field["key"], {}))
            item.setdefault("field_key", field["key"])
            item.setdefault("field_label", field["label"])
            item.setdefault("requirement_level", field["requirement_level"])
            item.setdefault("raw_value", None)
            item.setdefault("normalized_value", None)
            item.setdefault("confidence", 0.0)
            item.setdefault("extraction_method", "not_extracted")
            item.setdefault("source", None)
            item.setdefault(
                "status",
                "not_required" if field["requirement_level"] == "blank" else "pending",
            )
            item.setdefault("human_review_required", field["human_review_required"])
            item.setdefault("reviewer_notes", None)
            item["allowed_extraction_methods"] = field["extraction_methods"]
            rows.append((bucket, item))
    return rows


def build_metadata_field_rows(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Flatten a PDF metadata payload into spreadsheet-ready field rows."""
    deterministic = payload["deterministic_file_metadata"]
    document_type = payload["template"]["document_type"]
    context = payload["context"]
    intelligence = payload.get("intelligence", {})
    text_extraction = intelligence.get("pdf_text_extraction") or {}
    signals = text_extraction.get("signals") or {}
    ocr = intelligence.get("ocr") or {}

    base = {
        "schema_version": METADATA_TABLE_SCHEMA_VERSION,
        "generated_at": payload["generated_at"],
        "metadata_rules_version": payload["metadata_rules_version"],
        "submission_id": payload.get("submission_id") or context.get("submission_id"),
        "document_id": payload.get("document_id") or context.get("document_id"),
        "document_type_code": payload["document_type_code"],
        "document_type_name": document_type["name"],
        "institution": document_type["institution"],
        "client_legal_name": context.get("client_legal_name"),
        "provider_nomenclature": context.get("provider_nomenclature"),
        "original_filename": deterministic["original_filename"],
        "sha256": deterministic["sha256"],
        "page_count": deterministic["page_count"],
        "validation_status": payload["validation_result"]["status"],
        "detected_institution": signals.get("detected_institution"),
        "detected_document_type": signals.get("detected_document_type"),
        "detected_rfcs": signals.get("detected_rfcs"),
        "detected_dates": signals.get("detected_dates"),
        "period_mentions": signals.get("period_mentions"),
        "requirement_match_confidence": signals.get("requirement_match_confidence"),
        "mismatch_reason": signals.get("mismatch_reason"),
        "anomaly_codes": signals.get("anomaly_codes"),
        "ocr_status": ocr.get("status"),
        "ocr_used": ocr.get("ocr_used", False),
    }

    rows: list[dict[str, str]] = []
    for bucket, item in _field_rows_from_template(payload):
        row = {
            **base,
            "field_key": item["field_key"],
            "field_label": item["field_label"],
            "requirement_level": bucket,
            "allowed_extraction_methods": item.get("allowed_extraction_methods"),
            "raw_value": item.get("raw_value"),
            "normalized_value": item.get("normalized_value"),
            "confidence": item.get("confidence"),
            "extraction_method": item.get("extraction_method"),
            "source": item.get("source"),
            "review_status": item.get("status"),
            "human_review_required": item.get("human_review_required"),
            "reviewer_notes": item.get("reviewer_notes"),
        }
        rows.append({column: _json_cell(row.get(column)) for column in FIELD_ROW_COLUMNS})
    return rows


def write_csv(rows: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELD_ROW_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_xlsx(rows: list[dict[str, str]], output_path: Path) -> None:
    """Write a minimal XLSX workbook without adding an openpyxl dependency."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet_xml = _worksheet_xml(rows)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types_xml())
        archive.writestr("_rels/.rels", _root_rels_xml())
        archive.writestr("xl/workbook.xml", _workbook_xml())
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_rels_xml())
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)


def _content_types_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>"""


def _root_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""


def _workbook_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="metadata_fields" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>"""


def _workbook_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>"""


def _worksheet_xml(rows: list[dict[str, str]]) -> str:
    xml_rows = [_xlsx_row(1, FIELD_ROW_COLUMNS)]
    for index, row in enumerate(rows, start=2):
        xml_rows.append(_xlsx_row(index, [row[column] for column in FIELD_ROW_COLUMNS]))
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">\n'
        "  <sheetData>\n"
        + "\n".join(xml_rows)
        + "\n  </sheetData>\n"
        "</worksheet>"
    )


def _xlsx_row(row_index: int, values: list[str]) -> str:
    cells = []
    for column_index, value in enumerate(values, start=1):
        ref = f"{_column_name(column_index)}{row_index}"
        cells.append(
            f'<c r="{ref}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
        )
    return f'    <row r="{row_index}">' + "".join(cells) + "</row>"


def _column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def export_pdf_metadata_table(
    *,
    pdf_path: str | Path,
    document_type_code: str,
    context: dict[str, Any] | None,
    output_path: str | Path,
    output_format: str | None = None,
    include_intelligence: bool = True,
    enable_ocr: bool = False,
) -> list[dict[str, str]]:
    payload = build_pdf_metadata_dry_run_payload(
        pdf_path=pdf_path,
        document_type_code=document_type_code,
        context=context or {},
        include_intelligence=include_intelligence,
        enable_ocr=enable_ocr,
    )
    rows = build_metadata_field_rows(payload)
    path = Path(output_path).expanduser()
    fmt = (output_format or path.suffix.lstrip(".") or "csv").lower()
    if fmt == "csv":
        write_csv(rows, path)
    elif fmt == "xlsx":
        write_xlsx(rows, path)
    else:
        raise ValueError("output_format must be 'csv' or 'xlsx'.")
    return rows


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export CheckWise PDF metadata review rows to CSV or XLSX."
    )
    parser.add_argument("--pdf", required=True, help="Path to the uploaded/local PDF.")
    parser.add_argument("--document-type", required=True, help="Metadata rule code.")
    parser.add_argument("--context-json", help="Optional upload/submission context JSON.")
    parser.add_argument("--output", required=True, help="Destination .csv or .xlsx file.")
    parser.add_argument("--format", choices=["csv", "xlsx"], help="Override output format.")
    parser.add_argument(
        "--no-intelligence",
        action="store_true",
        help="Skip PDF text extraction and mismatch signal package.",
    )
    parser.add_argument(
        "--enable-ocr",
        action="store_true",
        help="Run local Tesseract OCR when intelligence is enabled.",
    )
    parser.add_argument(
        "--validate-rulebook",
        action="store_true",
        help="Validate metadata_rules.py before exporting.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    if args.validate_rulebook:
        problems = validate_metadata_rulebook()
        if problems:
            print(json.dumps({"status": "failed", "problems": problems}, indent=2), file=sys.stderr)
            return 2

    context: dict[str, Any] = {}
    if args.context_json:
        context = _read_json_file(Path(args.context_json).expanduser())

    try:
        rows = export_pdf_metadata_table(
            pdf_path=args.pdf,
            document_type_code=args.document_type,
            context=context,
            output_path=args.output,
            output_format=args.format,
            include_intelligence=not args.no_intelligence,
            enable_ocr=args.enable_ocr,
        )
    except (UnknownDocumentTypeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"Wrote {len(rows)} metadata field rows: {Path(args.output).expanduser()}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
