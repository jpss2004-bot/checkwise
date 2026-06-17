from __future__ import annotations

import json
from pathlib import Path

from pypdf import PdfWriter

from app.core.metadata_rules import RULEBOOK_VERSION, metadata_rule_by_code
from tools import test_pdf_metadata_dry_run as dry_run_tool
from tools.test_pdf_metadata_dry_run import (
    build_pdf_metadata_dry_run_payload,
    inspect_local_pdf,
    list_document_type_codes,
    main,
)


def _write_blank_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with path.open("wb") as handle:
        writer.write(handle)


def test_inspect_local_pdf_returns_deterministic_file_metadata(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    _write_blank_pdf(pdf_path)

    inspection = inspect_local_pdf(pdf_path)

    assert inspection["original_filename"] == "sample.pdf"
    assert inspection["mime_type"] == "application/pdf"
    assert inspection["pdf_header_valid"] is True
    assert inspection["page_count"] == 1
    assert inspection["pypdf_readable"] is True
    assert len(inspection["sha256"]) == 64
    assert inspection["ocr_used"] is False
    assert inspection["ai_used"] is False
    assert inspection["external_services_used"] is False


def test_payload_uses_real_rulebook_for_acuse_sisub(tmp_path: Path) -> None:
    pdf_path = tmp_path / "SEGURIDAD_PRI_Acuse_SISUB_Mayo.pdf"
    _write_blank_pdf(pdf_path)
    context = {
        "submission_id": "sub_fixture_acuse_sisub_001",
        "document_id": "doc_fixture_acuse_sisub_001",
        "client_legal_name": "CLIENTE DEMO, S.A. DE C.V.",
        "provider_nomenclature": "SEGURIDAD PRI",
        "expected_institution": "infonavit",
        "upload_form_month": "Mayo",
        "reported_period": "Cuatrimestre inmediato anterior",
        "proposed_document_name": "SEGURIDAD PRI Acuse SISUB Mayo",
        "proposed_pdf_file_name": "SEGURIDAD PRI Acuse SISUB Mayo.pdf",
    }

    payload = build_pdf_metadata_dry_run_payload(
        pdf_path=pdf_path,
        document_type_code="acuse_sisub",
        context=context,
    )

    rule = metadata_rule_by_code("acuse_sisub")
    assert payload["payload_type"] == "checkwise_local_pdf_metadata_dry_run"
    assert payload["metadata_rules_version"] == RULEBOOK_VERSION
    assert payload["document_type_code"] == "acuse_sisub"
    assert payload["review_item_count"] == len(rule.required_field_keys)
    assert payload["template"]["document_type"]["code"] == "acuse_sisub"
    assert payload["validation_result"]["status"] == "passed"
    assert payload["safety"] == {
        "legal_approval_allowed": False,
        "ocr_used": False,
        "ai_used": False,
        "google_sheets_used": False,
        "external_services_used": False,
        "db_used": False,
        "production_upload_flow_used": False,
        "human_review_required": True,
    }

    by_key = {item["field_key"]: item for item in payload["review_items"]}
    assert by_key["document_name"]["raw_value"] == "SEGURIDAD PRI Acuse SISUB Mayo"
    assert by_key["area_interna"]["raw_value"] == "Compliance"
    assert by_key["document_category"]["raw_value"] == "Formatos"
    assert by_key["document_subtype"]["raw_value"] == "Comprobante"
    assert by_key["upload_form_month"]["raw_value"] == "Mayo"
    assert by_key["reported_period"]["raw_value"] == "Cuatrimestre inmediato anterior"
    assert by_key["tags"]["raw_value"] == list(rule.fixed_tags)
    assert by_key["issue_date"]["status"] == "pending"
    assert by_key["participants"]["status"] == "pending"
    assert by_key["pdf_quality_ocr"]["raw_value"]["ocr_confirmed"] is False


def test_payload_uses_real_rulebook_for_contract(tmp_path: Path) -> None:
    pdf_path = tmp_path / "Contrato.pdf"
    _write_blank_pdf(pdf_path)

    payload = build_pdf_metadata_dry_run_payload(
        pdf_path=pdf_path,
        document_type_code="contrato_prestacion_servicios",
        context={
            "client_legal_name": "CLIENTE DEMO, S.A. DE C.V.",
            "provider_nomenclature": "ARTURO VILLAGRÁN JIMÉNEZ",
            "proposed_document_name": "ARTURO VILLAGRÁN JIMÉNEZ Contrato Prestación Servicios",
        },
    )

    by_key = {item["field_key"]: item for item in payload["review_items"]}
    assert by_key["document_category"]["raw_value"] == "Contrato"
    assert by_key["document_subtype"]["raw_value"] == "Prestación de Servicios"
    assert by_key["start_date"]["status"] == "pending"
    assert by_key["provider_participant"]["status"] == "pending"
    assert payload["validation_result"]["status"] == "passed"


def test_payload_ignores_empty_form_values_and_uses_rulebook_naming(tmp_path: Path) -> None:
    pdf_path = tmp_path / "human-med-acuse-icsoe-septiembre.pdf"
    _write_blank_pdf(pdf_path)

    payload = build_pdf_metadata_dry_run_payload(
        pdf_path=pdf_path,
        document_type_code="acuse_icsoe",
        context={
            "client_legal_name": "CLIENTE DEMO, S.A. DE C.V.",
            "provider_nomenclature": "HUMAN MED",
            "upload_form_month": "Septiembre",
            "reported_period": "",
        },
    )

    rule = metadata_rule_by_code("acuse_icsoe")
    by_key = {item["field_key"]: item for item in payload["review_items"]}
    assert "reported_period" not in payload["context"]
    assert by_key["document_name"]["raw_value"] == "HUMAN MED Acuse ICSOE Septiembre"
    assert by_key["document_name"]["source"] == "rulebook_naming_pattern"
    assert by_key["reported_period"]["status"] == "pending"
    assert by_key["tags"]["raw_value"] == list(rule.fixed_tags)
    assert by_key["tags"]["source"] == "rulebook_fixed_tags"
    assert payload["validation_result"]["status"] == "passed"


def test_payload_can_include_intelligence_package(tmp_path: Path) -> None:
    pdf_path = tmp_path / "human-med-acuse-icsoe-septiembre.pdf"
    _write_blank_pdf(pdf_path)

    payload = build_pdf_metadata_dry_run_payload(
        pdf_path=pdf_path,
        document_type_code="acuse_icsoe",
        context={
            "client_legal_name": "CLIENTE DEMO, S.A. DE C.V.",
            "provider_nomenclature": "HUMAN MED",
            "upload_form_month": "Septiembre",
        },
        include_intelligence=True,
    )

    intelligence = payload["intelligence"]
    assert intelligence["pdf_text_extraction"]["pdf_text_extraction_used"] is True
    assert intelligence["pdf_text_extraction"]["ocr_used"] is False
    assert intelligence["ocr"]["status"] == "not_configured"
    assert intelligence["ocr"]["ocr_used"] is False
    assert intelligence["ai_extraction_request"]["status"] == "ready_for_n8n_ai_node"
    assert intelligence["ai_extraction_request"]["ai_used"] is False
    assert intelligence["google_sheets"]["status"] == "row_ready_for_n8n_google_sheets_node"
    assert intelligence["google_sheets"]["google_sheets_used"] is False
    assert intelligence["google_sheets"]["row"]["document_type_code"] == "acuse_icsoe"
    assert intelligence["google_sheets"]["row"]["legal_approval_allowed"] is False


def test_payload_can_run_opt_in_local_ocr(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pdf_path = tmp_path / "human-med-acuse-icsoe-septiembre.pdf"
    _write_blank_pdf(pdf_path)

    def fake_ocr(pdf_path: str | Path, *, max_pages: int = 3) -> dict[str, object]:
        return {
            "ocr_used": True,
            "status": "completed",
            "engine": "tesseract",
            "language": "spa+eng",
            "page_count_processed": 1,
            "text_char_count": 19,
            "text_sample": "acuse icsoe example",
            "errors": [],
            "ocr_recommended": False,
        }

    monkeypatch.setattr(dry_run_tool, "_run_local_tesseract_ocr", fake_ocr)

    payload = build_pdf_metadata_dry_run_payload(
        pdf_path=pdf_path,
        document_type_code="acuse_icsoe",
        include_intelligence=True,
        enable_ocr=True,
    )

    assert payload["safety"]["ocr_used"] is True
    assert payload["validation_result"]["status"] == "passed"
    assert payload["intelligence"]["ocr"]["status"] == "completed"
    assert "acuse icsoe example" in payload["intelligence"]["ai_extraction_request"][
        "user_payload"
    ]["text_sample"]


def test_precomputed_intelligence_is_reused_without_reparsing(monkeypatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "csf.pdf"
    _write_blank_pdf(pdf_path)

    def _must_not_run(*_args, **_kwargs):
        raise AssertionError(
            "_build_pdf_text_extraction must not run when intelligence is precomputed"
        )

    monkeypatch.setattr(dry_run_tool, "_build_pdf_text_extraction", _must_not_run)

    precomputed = {
        "pdf_text_extraction_used": True,
        "method": "reused_prevalidation_inspection",
        "ocr_used": False,
        "text_char_count": 30,
        "has_text": True,
        "is_probably_scanned": False,
        "text_sample": "constancia de situacion fiscal",
        "signals": {
            "detected_institution": "sat",
            "detected_document_type": "constancia_situacion_fiscal",
            "detected_rfcs": ["XAXX010101000"],
            "detected_dates": [],
            "period_mentions": [],
            "requirement_match_confidence": 0.9,
            "mismatch_reason": None,
            "anomaly_codes": [],
        },
    }

    payload = build_pdf_metadata_dry_run_payload(
        pdf_path=pdf_path,
        document_type_code="constancia_situacion_fiscal",
        include_intelligence=True,
        precomputed_text_extraction=precomputed,
    )

    assert payload["intelligence"]["pdf_text_extraction"] is precomputed
    assert payload["safety"]["ocr_used"] is False
    assert payload["validation_result"]["status"] == "passed"
    # The reused intake text still reaches the AI hand-off envelope.
    assert (
        "constancia de situacion fiscal"
        in payload["intelligence"]["ai_extraction_request"]["user_payload"]["text_sample"]
    )


def test_cli_writes_output_file(tmp_path: Path) -> None:
    pdf_path = tmp_path / "sample.pdf"
    context_path = tmp_path / "context.json"
    output_path = tmp_path / "out" / "payload.json"
    _write_blank_pdf(pdf_path)
    context_path.write_text(
        json.dumps(
            {
                "client_legal_name": "CLIENTE DEMO, S.A. DE C.V.",
                "provider_nomenclature": "SEGURIDAD PRI",
                "proposed_document_name": "SEGURIDAD PRI Acuse SISUB Mayo",
            }
        ),
        encoding="utf-8",
    )

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
            "--validate-rulebook",
        ]
    )

    assert exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["document_type_code"] == "acuse_sisub"
    assert payload["validation_result"]["status"] == "passed"


def test_list_document_type_codes_comes_from_rulebook() -> None:
    codes = list_document_type_codes()
    assert "acuse_sisub" in codes
    assert "contrato_prestacion_servicios" in codes
    assert "registro_repse" in codes
