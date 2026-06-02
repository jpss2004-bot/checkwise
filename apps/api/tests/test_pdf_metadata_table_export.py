from __future__ import annotations

import csv
import json
import zipfile
from pathlib import Path

from pypdf import PdfWriter

from app.core.metadata_rules import metadata_rule_by_code, n8n_template_for_document_type
from tools.export_pdf_metadata_table import (
    FIELD_ROW_COLUMNS,
    METADATA_TABLE_SCHEMA_VERSION,
    build_metadata_field_rows,
    export_pdf_metadata_table,
    main,
    read_metadata_field_rows_from_xlsx,
    write_client_master_xlsx,
)
from tools.test_pdf_metadata_dry_run import build_pdf_metadata_dry_run_payload


def _write_blank_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with path.open("wb") as handle:
        writer.write(handle)


def _context() -> dict[str, str]:
    return {
        "submission_id": "sub-table-001",
        "document_id": "doc-table-001",
        "client_legal_name": "CLIENTE DEMO, S.A. DE C.V.",
        "provider_nomenclature": "SEGURIDAD PRI",
        "expected_institution": "infonavit",
        "upload_form_month": "Mayo",
        "period_key": "2026-M05",
        "reported_period": "Cuatrimestre inmediato anterior",
        "proposed_document_name": "SEGURIDAD PRI Acuse SISUB Mayo",
    }


def test_metadata_rows_include_complete_rulebook_fields(tmp_path: Path) -> None:
    pdf_path = tmp_path / "acuse.pdf"
    _write_blank_pdf(pdf_path)

    payload = build_pdf_metadata_dry_run_payload(
        pdf_path=pdf_path,
        document_type_code="acuse_sisub",
        context=_context(),
        include_intelligence=True,
    )

    rows = build_metadata_field_rows(payload)
    template = n8n_template_for_document_type("acuse_sisub")
    expected_count = sum(
        len(template["fields"][bucket])
        for bucket in ("required", "conditional", "optional", "blank")
    )

    assert len(rows) == expected_count
    assert set(rows[0]) == set(FIELD_ROW_COLUMNS)
    assert rows[0]["schema_version"] == METADATA_TABLE_SCHEMA_VERSION

    by_key = {row["field_key"]: row for row in rows}
    assert by_key["document_name"]["raw_value"] == "SEGURIDAD PRI Acuse SISUB Mayo"
    assert by_key["document_name"]["review_status"] == "prefilled_needs_review"
    assert by_key["main_date"]["review_status"] == "pending"
    assert by_key["related_documents"]["requirement_level"] == "blank"

    rule = metadata_rule_by_code("acuse_sisub")
    assert by_key["tags"]["raw_value"] == json.dumps(
        list(rule.fixed_tags),
        ensure_ascii=False,
        sort_keys=True,
    )


def test_export_pdf_metadata_table_writes_csv(tmp_path: Path) -> None:
    pdf_path = tmp_path / "acuse.pdf"
    output_path = tmp_path / "metadata.csv"
    _write_blank_pdf(pdf_path)

    rows = export_pdf_metadata_table(
        pdf_path=pdf_path,
        document_type_code="acuse_sisub",
        context=_context(),
        output_path=output_path,
        output_format="csv",
        include_intelligence=False,
    )

    assert output_path.exists()
    with output_path.open("r", encoding="utf-8", newline="") as handle:
        loaded = list(csv.DictReader(handle))

    assert len(loaded) == len(rows)
    assert loaded[0]["document_id"] == "doc-table-001"
    assert loaded[0]["document_type_code"] == "acuse_sisub"
    assert "field_key" in loaded[0]


def test_export_pdf_metadata_table_writes_guided_xlsx(tmp_path: Path) -> None:
    pdf_path = tmp_path / "acuse.pdf"
    output_path = tmp_path / "metadata.xlsx"
    _write_blank_pdf(pdf_path)

    rows = export_pdf_metadata_table(
        pdf_path=pdf_path,
        document_type_code="acuse_sisub",
        context=_context(),
        output_path=output_path,
        output_format="xlsx",
        include_intelligence=False,
    )

    assert rows
    with zipfile.ZipFile(output_path, "r") as archive:
        names = set(archive.namelist())
        workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
        guide_xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        review_xml = archive.read("xl/worksheets/sheet2.xml").decode("utf-8")
        signals_xml = archive.read("xl/worksheets/sheet3.xml").decode("utf-8")
        raw_xml = archive.read("xl/worksheets/sheet4.xml").decode("utf-8")

    assert "[Content_Types].xml" in names
    assert "xl/workbook.xml" in names
    assert "xl/styles.xml" in names
    assert "xl/worksheets/sheet1.xml" in names
    assert "xl/worksheets/sheet2.xml" in names
    assert "xl/worksheets/sheet3.xml" in names
    assert "xl/worksheets/sheet4.xml" in names

    for sheet_name in ("00 Guia", "01 Revision", "02 Senales", "03 Datos"):
        assert sheet_name in workbook_xml

    assert "CheckWise Metadata Review" in guide_xml
    assert "Documento esperado" in guide_xml
    assert "SEGURIDAD PRI" in guide_xml

    assert "Regla LegalShelf" in review_xml
    assert "Accion sugerida" in review_xml
    assert "SEGURIDAD PRI Acuse SISUB Mayo" in review_xml

    assert "Documento esperado" in signals_xml
    assert "Institucion esperada" in signals_xml

    # 2026-06-02 vocabulary pass: raw-sheet header row now uses Spanish
    # display labels ("Código del tipo" instead of "document_type_code").
    # The dict keys + cell values are unchanged so loaded_rows below
    # still reads back the snake_case keys for backwards compat.
    assert "Código del tipo" in raw_xml
    assert "acuse_sisub" in raw_xml

    loaded_rows = read_metadata_field_rows_from_xlsx(output_path)
    assert len(loaded_rows) == len(rows)
    assert loaded_rows[0]["document_type_code"] == "acuse_sisub"


def test_client_master_xlsx_keeps_shareable_metadata_only(tmp_path: Path) -> None:
    pdf_path = tmp_path / "acuse.pdf"
    output_path = tmp_path / "master.xlsx"
    _write_blank_pdf(pdf_path)

    payload = build_pdf_metadata_dry_run_payload(
        pdf_path=pdf_path,
        document_type_code="acuse_sisub",
        context=_context(),
        include_intelligence=False,
    )
    rows = build_metadata_field_rows(payload)
    write_client_master_xlsx(rows, output_path, client_name="CLIENTE DEMO, S.A. DE C.V.")

    with zipfile.ZipFile(output_path, "r") as archive:
        workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
        guide_xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        metadata_xml = archive.read("xl/worksheets/sheet2.xml").decode("utf-8")

    assert "00 Guia" in workbook_xml
    assert "01 Metadata" in workbook_xml
    assert "Metadata documental del cliente" in guide_xml
    assert "Nombre del documento" in metadata_xml
    assert "Tipo de documento" in metadata_xml
    assert "SEGURIDAD PRI Acuse SISUB Mayo" in metadata_xml
    assert "2026-M05" in metadata_xml
    assert "sha256" not in metadata_xml
    assert "Confianza" not in metadata_xml
    assert "Mismatch" not in metadata_xml
    assert "Estado" not in metadata_xml


def test_cli_writes_csv_file(tmp_path: Path) -> None:
    pdf_path = tmp_path / "acuse.pdf"
    context_path = tmp_path / "context.json"
    output_path = tmp_path / "out" / "metadata.csv"
    _write_blank_pdf(pdf_path)
    context_path.write_text(json.dumps(_context()), encoding="utf-8")

    exit_code = main(
        [
            "--pdf",
            str(pdf_path),
            "--document-type",
            "acuse_sisub",
            "--context-json",
            str(context_path),
            "--output",
            str(output_path),
            "--format",
            "csv",
            "--no-intelligence",
            "--validate-rulebook",
        ]
    )

    assert exit_code == 0
    assert output_path.exists()
