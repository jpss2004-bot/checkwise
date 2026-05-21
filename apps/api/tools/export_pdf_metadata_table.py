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
    "document_group",
    "document_category",
    "document_subtype",
    "document_frequency",
    "document_hierarchy",
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
    "field_description",
    "rule_source_section",
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

REVIEW_COLUMNS = [
    "Seccion",
    "Campo",
    "Regla LegalShelf",
    "Valor extraido / propuesto",
    "Confianza",
    "Estado",
    "Metodo / fuente",
    "Accion sugerida",
]

RAW_SHEET_NAME = "03 Datos"


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
            item.setdefault("field_description", field["description"])
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
        "document_group": document_type["group"],
        "document_category": document_type["category"],
        "document_subtype": document_type["subtype"],
        "document_frequency": document_type["frequency"],
        "document_hierarchy": document_type["hierarchy"],
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
            "field_description": item.get("field_description"),
            "rule_source_section": document_type.get("source_section"),
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
    """Write a guided XLSX workbook without adding an openpyxl dependency."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    worksheets = _build_workbook_sheets(rows)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types_xml(len(worksheets)))
        archive.writestr("_rels/.rels", _root_rels_xml())
        archive.writestr("xl/workbook.xml", _workbook_xml([sheet["name"] for sheet in worksheets]))
        archive.writestr("xl/styles.xml", _styles_xml())
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_rels_xml(len(worksheets)))
        for index, sheet in enumerate(worksheets, start=1):
            archive.writestr(
                f"xl/worksheets/sheet{index}.xml",
                _worksheet_xml(
                    sheet["rows"],
                    styles=sheet["styles"],
                    widths=sheet["widths"],
                    freeze=sheet.get("freeze", True),
                    autofilter=sheet.get("autofilter", True),
                ),
            )


def _content_types_xml(sheet_count: int) -> str:
    sheet_overrides = "\n".join(
        f'  <Override PartName="/xl/worksheets/sheet{index}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, sheet_count + 1)
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
{sheet_overrides}
</Types>"""


def _root_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""


def _workbook_xml(sheet_names: list[str]) -> str:
    sheets = "\n".join(
        f'    <sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, name in enumerate(sheet_names, start=1)
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
{sheets}
  </sheets>
</workbook>"""


def _workbook_rels_xml(sheet_count: int) -> str:
    sheet_relationships = "\n".join(
        f'  <Relationship Id="rId{index}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        f'Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, sheet_count + 1)
    )
    styles_id = sheet_count + 1
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
{sheet_relationships}
  <Relationship Id="rId{styles_id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""


def _worksheet_xml(
    rows: list[list[str]],
    *,
    styles: list[list[int]],
    widths: list[int],
    freeze: bool,
    autofilter: bool,
) -> str:
    xml_rows = [
        _xlsx_row(index, row, styles[index - 1] if index - 1 < len(styles) else [])
        for index, row in enumerate(rows, start=1)
    ]
    cols = "".join(
        f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
        for index, width in enumerate(widths, start=1)
    )
    pane = (
        '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" '
        'activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        if freeze
        else '<sheetViews><sheetView workbookViewId="0"/></sheetViews>'
    )
    ref = f"A1:{_column_name(max(len(row) for row in rows) if rows else 1)}{len(rows)}"
    autofilter_xml = f'<autoFilter ref="{ref}"/>' if autofilter and len(rows) > 1 else ""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">\n'
        f"  {pane}\n"
        f"  <cols>{cols}</cols>\n"
        "  <sheetData>\n"
        + "\n".join(xml_rows)
        + "\n  </sheetData>\n"
        f"  {autofilter_xml}\n"
        "</worksheet>"
    )


def _xlsx_row(row_index: int, values: list[str], styles: list[int]) -> str:
    cells = []
    for column_index, value in enumerate(values, start=1):
        ref = f"{_column_name(column_index)}{row_index}"
        style = styles[column_index - 1] if column_index - 1 < len(styles) else 0
        style_attr = f' s="{style}"' if style else ""
        cells.append(
            f'<c r="{ref}"{style_attr} t="inlineStr"><is><t>{escape(value)}</t></is></c>'
        )
    return f'    <row r="{row_index}">' + "".join(cells) + "</row>"


def _column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _build_workbook_sheets(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    return [
        _guide_sheet(rows),
        _review_sheet(rows),
        _signals_sheet(rows),
        _raw_data_sheet(rows),
    ]


def _guide_sheet(rows: list[dict[str, str]]) -> dict[str, Any]:
    first = rows[0] if rows else {}
    counts = _status_counts(rows)
    guide_rows = [
        ["CheckWise Metadata Review", "", "", ""],
        ["Que es este libro", "Revision guiada de metadata documental generada al subir un PDF.", "", ""],
        ["Fuente de reglas", "CW & LS- PROPUESTA MD SIMPLIFICADA.docx.pdf", "", ""],
        ["Cliente", first.get("client_legal_name", ""), "Proveedor", first.get("provider_nomenclature", "")],
        ["Documento esperado", first.get("document_type_name", ""), "Institucion", first.get("institution", "")],
        ["Periodo", first.get("period_mentions", "") or first.get("document_frequency", ""), "Archivo", first.get("original_filename", "")],
        ["Estado general", _overall_status_label(rows), "Campos pendientes", str(counts.get("pending", 0))],
        ["Mismatch", first.get("mismatch_reason", "") or "Sin mismatch automatico detectado", "", ""],
        ["Como revisarlo", "1. Confirma documento esperado vs detectado. 2. Revisa RFCs/fechas/periodos. 3. Atiende campos pendientes. 4. Comparte solo cuando LegalShelf lo haya validado.", "", ""],
        ["Principio LegalShelf", "La metadata es para consulta del cliente CheckWise; la aprobacion legal sigue requiriendo revision humana.", "", ""],
    ]
    styles = [[1, 1, 1, 1]] + [[9, 10, 9, 10] for _ in guide_rows[1:]]
    return {
        "name": "00 Guia",
        "rows": guide_rows,
        "styles": styles,
        "widths": [24, 72, 22, 48],
        "freeze": False,
        "autofilter": False,
    }


def _review_sheet(rows: list[dict[str, str]]) -> dict[str, Any]:
    review_rows = [REVIEW_COLUMNS]
    styles = [[3] * len(REVIEW_COLUMNS)]
    for row in rows:
        status = row.get("review_status", "")
        style = _style_for_status(status)
        value = row.get("normalized_value") or row.get("raw_value") or "(pendiente)"
        review_rows.append(
            [
                row.get("requirement_level", ""),
                row.get("field_label", ""),
                row.get("field_description", ""),
                value,
                row.get("confidence", ""),
                status,
                " / ".join(part for part in [row.get("extraction_method", ""), row.get("source", "")] if part),
                _action_for_status(status),
            ]
        )
        styles.append([style] * len(REVIEW_COLUMNS))
    return {
        "name": "01 Revision",
        "rows": review_rows,
        "styles": styles,
        "widths": [16, 34, 76, 54, 12, 24, 34, 60],
        "freeze": True,
        "autofilter": True,
    }


def _signals_sheet(rows: list[dict[str, str]]) -> dict[str, Any]:
    first = rows[0] if rows else {}
    signal_rows = [
        ["Senal", "Valor detectado", "Como usarlo"],
        ["Documento esperado", first.get("document_type_name", ""), "Debe coincidir con lo que el proveedor eligio en el portal."],
        ["Documento detectado", first.get("detected_document_type", ""), "Si difiere, revisar posible carga equivocada."],
        ["Institucion esperada", first.get("institution", ""), "SAT, IMSS, INFONAVIT, STPS/REPSE o interno."],
        ["Institucion detectada", first.get("detected_institution", ""), "Debe coincidir con la institucion esperada."],
        ["RFCs detectados", first.get("detected_rfcs", ""), "Comparar contra RFC del proveedor y, cuando aplique, cliente."],
        ["Fechas detectadas", first.get("detected_dates", ""), "Usarlas para validar fecha principal, periodo reportado y vigencia."],
        ["Periodos mencionados", first.get("period_mentions", ""), "Comparar contra el periodo del calendario CheckWise."],
        ["Confianza de match", first.get("requirement_match_confidence", ""), "Baja confianza requiere revision LegalShelf."],
        ["Mismatch", first.get("mismatch_reason", ""), "Si existe, no compartir como correcto sin revisar."],
        ["Codigos de anomalia", first.get("anomaly_codes", ""), "Senales internas para priorizar revision."],
        ["OCR", first.get("ocr_status", ""), "El PDF fuente exige buena calidad y proceso OCR."],
    ]
    styles = [[3, 3, 3]] + [[9, 10, 10] for _ in signal_rows[1:]]
    if first.get("mismatch_reason"):
        styles[9] = [7, 7, 7]
    return {
        "name": "02 Senales",
        "rows": signal_rows,
        "styles": styles,
        "widths": [28, 70, 80],
        "freeze": True,
        "autofilter": False,
    }


def _raw_data_sheet(rows: list[dict[str, str]]) -> dict[str, Any]:
    data_rows = [FIELD_ROW_COLUMNS]
    data_rows.extend([[row[column] for column in FIELD_ROW_COLUMNS] for row in rows])
    styles = [[3] * len(FIELD_ROW_COLUMNS)] + [[10] * len(FIELD_ROW_COLUMNS) for _ in rows]
    return {
        "name": RAW_SHEET_NAME,
        "rows": data_rows,
        "styles": styles,
        "widths": [18] * len(FIELD_ROW_COLUMNS),
        "freeze": True,
        "autofilter": True,
    }


def _status_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = row.get("review_status", "")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _overall_status_label(rows: list[dict[str, str]]) -> str:
    counts = _status_counts(rows)
    if counts.get("pending", 0):
        return "Requiere revision"
    if any(row.get("mismatch_reason") for row in rows):
        return "Posible mismatch"
    return "Listo para validacion LegalShelf"


def _style_for_status(status: str) -> int:
    if status in {"context_ready", "not_required"}:
        return 4
    if status in {"prefilled_needs_review", "deterministic_inspection_needs_review"}:
        return 5
    if status == "pending":
        return 6
    return 10


def _action_for_status(status: str) -> str:
    if status == "pending":
        return "Extraer con OCR/IA o capturar manualmente antes de compartir."
    if status in {"prefilled_needs_review", "deterministic_inspection_needs_review"}:
        return "Confirmar contra el PDF fuente."
    if status in {"context_ready", "not_required"}:
        return "Sin accion, salvo control de calidad."
    return "Revisar segun criterio LegalShelf."


def _styles_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="5">
    <font><sz val="11"/><color rgb="FF1F2937"/><name val="Arial"/></font>
    <font><b/><sz val="16"/><color rgb="FFFFFFFF"/><name val="Arial"/></font>
    <font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Arial"/></font>
    <font><b/><sz val="11"/><color rgb="FF013557"/><name val="Arial"/></font>
    <font><sz val="11"/><color rgb="FF1F2937"/><name val="Arial"/></font>
  </fonts>
  <fills count="8">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF013557"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF02558A"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFE7F8F6"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFFFF4D6"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFFFFBEB"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFFEE2E2"/><bgColor indexed="64"/></patternFill></fill>
  </fills>
  <borders count="2">
    <border><left/><right/><top/><bottom/><diagonal/></border>
    <border><left style="thin"><color rgb="FFD7DEE8"/></left><right style="thin"><color rgb="FFD7DEE8"/></right><top style="thin"><color rgb="FFD7DEE8"/></top><bottom style="thin"><color rgb="FFD7DEE8"/></bottom><diagonal/></border>
  </borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="11">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"><alignment wrapText="1"/></xf>
    <xf numFmtId="0" fontId="2" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"><alignment wrapText="1"/></xf>
    <xf numFmtId="0" fontId="2" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"><alignment wrapText="1"/></xf>
    <xf numFmtId="0" fontId="4" fillId="4" borderId="1" xfId="0" applyFill="1" applyBorder="1"><alignment wrapText="1" vertical="top"/></xf>
    <xf numFmtId="0" fontId="4" fillId="5" borderId="1" xfId="0" applyFill="1" applyBorder="1"><alignment wrapText="1" vertical="top"/></xf>
    <xf numFmtId="0" fontId="4" fillId="6" borderId="1" xfId="0" applyFill="1" applyBorder="1"><alignment wrapText="1" vertical="top"/></xf>
    <xf numFmtId="0" fontId="4" fillId="7" borderId="1" xfId="0" applyFill="1" applyBorder="1"><alignment wrapText="1" vertical="top"/></xf>
    <xf numFmtId="0" fontId="3" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1"><alignment wrapText="1" vertical="top"/></xf>
    <xf numFmtId="0" fontId="3" fillId="4" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"><alignment wrapText="1" vertical="top"/></xf>
    <xf numFmtId="0" fontId="4" fillId="0" borderId="1" xfId="0" applyBorder="1"><alignment wrapText="1" vertical="top"/></xf>
  </cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""


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
