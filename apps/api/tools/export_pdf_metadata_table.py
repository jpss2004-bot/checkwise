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
from xml.etree import ElementTree as ET
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
    "period_key",
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

# Spanish display labels for the raw-data sheet header row. Dict keys
# stay snake_case throughout the pipeline (consumers depend on the
# stable identifiers); only the header row printed in the XLSX uses
# these friendlier labels. A snake_case column with no Spanish entry
# below falls back to the raw key so a new column added on the
# backend stands out as untranslated until a label lands here.
FIELD_ROW_COLUMN_LABELS_ES: dict[str, str] = {
    "schema_version": "Versión del esquema",
    "generated_at": "Generado",
    "metadata_rules_version": "Versión de las reglas",
    "submission_id": "ID de envío",
    "document_id": "ID del documento",
    "document_type_code": "Código del tipo",
    "document_type_name": "Tipo de documento",
    "document_group": "Grupo",
    "document_category": "Categoría",
    "document_subtype": "Subtipo",
    "document_frequency": "Frecuencia",
    "document_hierarchy": "Jerarquía",
    "institution": "Institución",
    "client_legal_name": "Cliente",
    "provider_nomenclature": "Proveedor",
    "period_key": "Periodo",
    "original_filename": "Archivo",
    "sha256": "Hash SHA-256",
    "page_count": "Páginas",
    "validation_status": "Estado de validación",
    "detected_institution": "Institución detectada",
    "detected_document_type": "Tipo de documento detectado",
    "detected_rfcs": "RFCs detectados",
    "detected_dates": "Fechas detectadas",
    "period_mentions": "Periodos mencionados",
    "requirement_match_confidence": "Confianza de coincidencia",
    "mismatch_reason": "Razón de no coincidencia",
    "anomaly_codes": "Códigos de anomalía",
    "ocr_status": "Estado del OCR",
    "ocr_used": "OCR utilizado",
    "field_key": "Clave del campo",
    "field_label": "Nombre del campo",
    "field_description": "Descripción del campo",
    "rule_source_section": "Sección de la regla",
    "requirement_level": "Nivel del requisito",
    "allowed_extraction_methods": "Métodos de extracción permitidos",
    "raw_value": "Valor extraído",
    "normalized_value": "Valor normalizado",
    "confidence": "Confianza",
    "extraction_method": "Método de extracción",
    "source": "Fuente",
    "review_status": "Estado de revisión",
    "human_review_required": "Requiere revisión humana",
    "reviewer_notes": "Notas del revisor",
}


def _field_row_header_labels() -> list[str]:
    """Spanish header row for the raw data sheet, falling back to the
    snake_case key when a new column lacks a translation."""
    return [FIELD_ROW_COLUMN_LABELS_ES.get(col, col) for col in FIELD_ROW_COLUMNS]


# Plain-Spanish translations for anomaly codes that may appear inside
# the `anomaly_codes` column. Internal codes only become user-facing
# when surfaced in the raw sheet or signals sheet; this map gives them
# a readable form. Untranslated codes pass through unchanged so a new
# code stands out in QA.
ANOMALY_CODE_LABELS_ES: dict[str, str] = {
    "possible_document_type_mismatch": "Posible tipo de documento incorrecto",
    "possible_institution_mismatch": "Posible institución incorrecta",
    "period_not_confirmed": "Periodo no confirmado",
    "pdf_without_readable_text": "PDF sin texto legible",
    "expiration_visible_in_past": "Vigencia ya vencida",
    "rfc_not_present": "RFC esperado no encontrado",
    "signature_or_stamp_missing": "Falta firma o sello",
}


def _humanize_anomaly_codes(raw: str | None) -> str:
    """Translate a comma-joined anomaly_codes string to plain Spanish."""
    if not raw:
        return ""
    parts = [chunk.strip() for chunk in str(raw).split(",") if chunk.strip()]
    return ", ".join(ANOMALY_CODE_LABELS_ES.get(code, code) for code in parts)


def _format_confidence(raw: object) -> str:
    """Render a 0.0-1.0 confidence float as a percent for human readers.

    Empty / non-numeric values pass through unchanged so the raw column
    remains traceable. Used by the signals sheet — the raw data sheet
    keeps the float because consumers may parse it programmatically.
    """
    if raw in (None, ""):
        return ""
    try:
        value = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return str(raw)
    if value < 0 or value > 1:
        return str(raw)
    return f"{round(value * 100)}%"

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

CLIENT_MASTER_COLUMNS = [
    "Cliente",
    "Proveedor",
    "Periodo",
    "Nombre del documento",
    "Tipo de documento",
    "Subtipo",
    "Institucion",
    "Fecha principal",
    "Participantes",
    "Descripcion",
    "Anexos",
    "Etiquetas",
    "Archivo PDF",
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
        "period_key": context.get("period_key") or context.get("reported_period"),
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
    _write_xlsx_workbook(_build_workbook_sheets(rows), output_path)


def write_client_master_xlsx(
    rows: list[dict[str, str]], output_path: Path, *, client_name: str | None = None
) -> None:
    """Write the shareable per-client LegalShelf metadata workbook."""
    _write_xlsx_workbook(_build_client_master_sheets(rows, client_name=client_name), output_path)


def read_metadata_field_rows_from_xlsx(path: str | Path) -> list[dict[str, str]]:
    """Read the raw metadata rows from a CheckWise generated XLSX workbook.

    The XLSX header row uses Spanish display labels (2026-06-02 vocabulary
    pass), but consumers of this function expect the stable snake_case
    dict keys for backwards compatibility. We translate Spanish headers
    back to their snake_case equivalents on the way out; unknown headers
    pass through unchanged so a future column addition is still readable.
    """
    workbook_path = Path(path).expanduser()
    with zipfile.ZipFile(workbook_path, "r") as archive:
        workbook_xml = archive.read("xl/workbook.xml")
        sheet_names = _xlsx_sheet_names(workbook_xml)
        try:
            sheet_index = sheet_names.index(RAW_SHEET_NAME) + 1
        except ValueError:
            raise ValueError(f"Workbook does not contain {RAW_SHEET_NAME!r}: {workbook_path}") from None
        rows = _xlsx_sheet_rows(archive.read(f"xl/worksheets/sheet{sheet_index}.xml"))
    if not rows:
        return []
    spanish_to_snake = {label: key for key, label in FIELD_ROW_COLUMN_LABELS_ES.items()}
    headers = [spanish_to_snake.get(h, h) for h in rows[0]]
    return [
        {
            header: values[index] if index < len(values) else ""
            for index, header in enumerate(headers)
            if header
        }
        for values in rows[1:]
    ]


def _write_xlsx_workbook(worksheets: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
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


def _xlsx_sheet_names(workbook_xml: bytes) -> list[str]:
    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    root = ET.fromstring(workbook_xml)
    return [
        sheet.attrib.get("name", f"Sheet {index}")
        for index, sheet in enumerate(root.findall(".//x:sheet", namespace), start=1)
    ]


def _xlsx_sheet_rows(worksheet_xml: bytes) -> list[list[str]]:
    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    root = ET.fromstring(worksheet_xml)
    parsed_rows: list[list[str]] = []
    for row in root.findall(".//x:sheetData/x:row", namespace):
        values: list[str] = []
        for cell in row.findall("x:c", namespace):
            column_index = _xlsx_column_index(cell.attrib.get("r", "A1")) - 1
            while len(values) <= column_index:
                values.append("")
            values[column_index] = _xlsx_cell_text(cell, namespace)
        while values and values[-1] == "":
            values.pop()
        parsed_rows.append(values)
    return parsed_rows


def _xlsx_column_index(cell_ref: str) -> int:
    index = 0
    for char in cell_ref:
        if not char.isalpha():
            break
        index = index * 26 + (ord(char.upper()) - 64)
    return max(index, 1)


def _xlsx_cell_text(cell: ET.Element, namespace: dict[str, str]) -> str:
    inline = cell.find("x:is", namespace)
    if inline is not None:
        return "".join(node.text or "" for node in inline.findall(".//x:t", namespace))
    value = cell.find("x:v", namespace)
    return value.text if value is not None and value.text is not None else ""


def _build_workbook_sheets(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    return [
        _guide_sheet(rows),
        _review_sheet(rows),
        _signals_sheet(rows),
        _raw_data_sheet(rows),
    ]


def _build_client_master_sheets(
    rows: list[dict[str, str]], *, client_name: str | None
) -> list[dict[str, Any]]:
    documents = _client_document_summary_rows(rows)
    return [
        _client_master_guide_sheet(documents, client_name=client_name),
        _client_metadata_sheet(documents),
    ]


def _client_master_guide_sheet(
    rows: list[dict[str, str]], *, client_name: str | None
) -> dict[str, Any]:
    first = rows[0] if rows else {}
    guide_rows = [
        ["Metadata documental del cliente", "", "", ""],
        ["Cliente", client_name or first.get("Cliente", ""), "Documentos", str(len(rows))],
        ["Contenido", "Resumen de metadatos de los documentos cargados por sus proveedores.", "", ""],
        ["Formato", "Una fila por documento cargado.", "Fuente", "CheckWise"],
    ]
    return {
        "name": "00 Guia",
        "rows": guide_rows,
        "styles": [[1, 1, 1, 1]] + [[9, 10, 9, 10] for _ in guide_rows[1:]],
        "widths": [24, 76, 22, 40],
        "freeze": False,
        "autofilter": False,
    }


def _client_metadata_sheet(rows: list[dict[str, str]]) -> dict[str, Any]:
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            row.get("Proveedor", ""),
            row.get("Periodo", ""),
            row.get("Nombre del documento", ""),
        ),
    )
    metadata_rows = [CLIENT_MASTER_COLUMNS]
    styles = [[3] * len(CLIENT_MASTER_COLUMNS)]
    for row in sorted_rows:
        metadata_rows.append([row.get(column, "") for column in CLIENT_MASTER_COLUMNS])
        styles.append([10] * len(CLIENT_MASTER_COLUMNS))
    return {
        "name": "01 Metadata",
        "rows": metadata_rows,
        "styles": styles,
        "widths": [30, 30, 18, 40, 24, 26, 20, 24, 44, 52, 36, 44, 34],
        "freeze": True,
        "autofilter": True,
    }


def _client_document_summary_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    grouped: dict[tuple[str, str, str], list[dict[str, str]]] = {}
    for row in rows:
        key = (
            row.get("submission_id", ""),
            row.get("document_id", ""),
            row.get("document_type_code", ""),
        )
        grouped.setdefault(key, []).append(row)
    summaries = [_client_document_summary(group_rows) for group_rows in grouped.values()]
    return sorted(
        summaries,
        key=lambda row: (
            row.get("Cliente", ""),
            row.get("Proveedor", ""),
            row.get("Periodo", ""),
            row.get("Nombre del documento", ""),
        ),
    )


def _client_document_summary(rows: list[dict[str, str]]) -> dict[str, str]:
    first = rows[0] if rows else {}
    by_key = {row.get("field_key", ""): row for row in rows}
    return {
        "Cliente": first.get("client_legal_name", ""),
        "Proveedor": first.get("provider_nomenclature", ""),
        "Periodo": first.get("period_key", "") or _clean_field_value(by_key.get("reported_period")) or first.get("document_frequency", ""),
        "Nombre del documento": _clean_field_value(by_key.get("document_name")) or first.get("document_type_name", ""),
        "Tipo de documento": _clean_field_value(by_key.get("document_category")) or first.get("document_category", ""),
        "Subtipo": _clean_field_value(by_key.get("document_subtype")) or first.get("document_subtype", ""),
        "Institucion": _clean_field_value(by_key.get("document_institution_name")) or first.get("institution", ""),
        "Fecha principal": (
            _clean_field_value(by_key.get("main_date"))
            or _clean_field_value(by_key.get("full_date_label"))
            or _clean_field_value(by_key.get("issue_date"))
            or _clean_field_value(by_key.get("expedition_date"))
            or _clean_field_value(by_key.get("deed_date"))
            or _clean_field_value(by_key.get("start_date"))
        ),
        "Participantes": (
            _clean_field_value(by_key.get("participants"))
            or _clean_field_value(by_key.get("provider_participant"))
            or _clean_field_value(by_key.get("client_participant"))
            or _clean_field_value(by_key.get("taxpayer_name"))
        ),
        "Descripcion": _clean_field_value(by_key.get("description")),
        "Anexos": _clean_field_value(by_key.get("annexes")),
        "Etiquetas": _clean_field_value(by_key.get("tags")),
        "Archivo PDF": _clean_field_value(by_key.get("pdf_file_name")) or first.get("original_filename", ""),
    }


def _clean_field_value(row: dict[str, str] | None) -> str:
    if not row:
        return ""
    if row.get("review_status") == "pending":
        return ""
    value = row.get("normalized_value") or row.get("raw_value") or ""
    if value in {"(pendiente)", "null", "None"}:
        return ""
    return _human_readable_cell(value)


def _human_readable_cell(value: str) -> str:
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value
    if isinstance(parsed, list):
        return "; ".join(str(item) for item in parsed if item not in (None, ""))
    if isinstance(parsed, dict):
        return "; ".join(f"{key}: {val}" for key, val in parsed.items() if val not in (None, ""))
    if parsed is None:
        return ""
    return str(parsed)


def _guide_sheet(rows: list[dict[str, str]]) -> dict[str, Any]:
    first = rows[0] if rows else {}
    counts = _status_counts(rows)
    guide_rows = [
        ["CheckWise Metadata Review", "", "", ""],
        ["Que es este libro", "Revision guiada de metadata documental generada al subir un PDF.", "", ""],
        ["Fuente de reglas", "CW & LS- PROPUESTA MD SIMPLIFICADA.docx.pdf", "", ""],
        ["Cliente", first.get("client_legal_name", ""), "Proveedor", first.get("provider_nomenclature", "")],
        ["Documento esperado", first.get("document_type_name", ""), "Institucion", first.get("institution", "")],
        ["Periodo", first.get("period_key", "") or first.get("period_mentions", "") or first.get("document_frequency", ""), "Archivo", first.get("original_filename", "")],
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
        ["Confianza de match", _format_confidence(first.get("requirement_match_confidence", "")), "Baja confianza requiere revision LegalShelf."],
        ["Mismatch", first.get("mismatch_reason", ""), "Si existe, no compartir como correcto sin revisar."],
        ["Codigos de anomalia", _humanize_anomaly_codes(first.get("anomaly_codes", "")), "Senales internas para priorizar revision."],
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
    # Header row uses Spanish display labels so admin reviewers see
    # "Institución detectada" instead of "detected_institution"; the
    # underlying column order + cell values stay identical so any
    # downstream consumer that parses by column position is unaffected.
    data_rows = [_field_row_header_labels()]
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
