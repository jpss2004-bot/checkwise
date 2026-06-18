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
    # Review items now cover required + conditional + optional fields (deduped),
    # not just required — so conditional fields like ``description`` can be
    # filled by the deterministic layer or the AI tier instead of vanishing.
    assert payload["review_item_count"] == len(
        dict.fromkeys(
            rule.required_field_keys + rule.conditional_field_keys + rule.optional_field_keys
        )
    )
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
    # No readable dates in the blank fixture → date fields stay blank.
    assert by_key["issue_date"]["status"] == "pending"
    # Participants are now derived from the upload context (the provider).
    assert by_key["participants"]["status"] == "prefilled_needs_review"
    assert by_key["participants"]["raw_value"] == ["SEGURIDAD PRI"]
    # ``description`` is a conditional field with no rulebook-fixed text for
    # this type; it is now present as a review item (was previously dropped).
    assert by_key["description"]["status"] == "pending"
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
    # Contract participants are derived from context: provider + client.
    assert by_key["provider_participant"]["raw_value"] == "ARTURO VILLAGRÁN JIMÉNEZ"
    assert by_key["client_participant"]["raw_value"] == "CLIENTE DEMO, S.A. DE C.V."
    assert by_key["participants"]["raw_value"] == [
        "ARTURO VILLAGRÁN JIMÉNEZ",
        "CLIENTE DEMO, S.A. DE C.V.",
    ]
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


def test_field_suggestions_fill_pending_but_not_deterministic(tmp_path: Path) -> None:
    pdf_path = tmp_path / "csf.pdf"
    _write_blank_pdf(pdf_path)
    payload = build_pdf_metadata_dry_run_payload(
        pdf_path=pdf_path,
        document_type_code="constancia_situacion_fiscal",
        context={"client_legal_name": "X", "provider_nomenclature": "Y"},
        include_intelligence=True,
        field_suggestions={
            "main_date": {
                "value": "2024-03-07",
                "confidence": 0.9,
                "evidence": "fecha de emisión",
            },
            # A deterministic field — the suggestion must be ignored.
            "document_name": {"value": "WRONG", "confidence": 0.99, "evidence": "x"},
        },
    )
    by_key = {item["field_key"]: item for item in payload["review_items"]}

    main_date = by_key["main_date"]
    assert main_date["raw_value"] == "2024-03-07"
    assert main_date["status"] == "prefilled_needs_review"
    assert main_date["source"] == "ai_comprehension"
    assert main_date["extraction_method"] == "ai_assisted"
    assert main_date["confidence"] == 0.9
    assert main_date["reviewer_notes"] == "fecha de emisión"

    # The deterministic rulebook value wins; the suggestion never overrides it.
    assert by_key["document_name"]["raw_value"] != "WRONG"
    assert by_key["document_name"]["source"] != "ai_comprehension"

    # The standalone n8n AI node is superseded, and the dry-run ran no AI.
    assert (
        payload["intelligence"]["ai_extraction_request"]["status"]
        == "fulfilled_by_comprehension"
    )
    assert payload["safety"]["ai_used"] is False


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


def test_parse_detected_date_handles_mexican_and_iso_formats() -> None:
    assert dry_run_tool._parse_detected_date("07/03/2024") == (2024, 3, 7)
    assert dry_run_tool._parse_detected_date("9-5-24") == (2024, 5, 9)
    assert dry_run_tool._parse_detected_date("2024-05-09") == (2024, 5, 9)
    # Invalid / ambiguous tokens never fabricate a date.
    assert dry_run_tool._parse_detected_date("31/13/2024") is None
    assert dry_run_tool._parse_detected_date("not a date") is None


def test_select_document_date_is_conservative() -> None:
    ctx = {"reported_period": "2025-M03", "period_key": "2025-M03"}
    # A single detected date is used.
    assert dry_run_tool._select_document_date(
        context=ctx, detected_dates=["12/03/2025"]
    ) == ((2025, 3, 12), "12/03/2025", 0.6)
    # With several dates, only the one inside the expected period is chosen.
    assert dry_run_tool._select_document_date(
        context=ctx, detected_dates=["01/01/2024", "12/03/2025", "28/02/2025"]
    ) == ((2025, 3, 12), "12/03/2025", 0.7)
    # Genuinely ambiguous → no value (better blank than wrong).
    assert (
        dry_run_tool._select_document_date(
            context=ctx, detected_dates=["15/06/2025", "20/09/2025"]
        )
        is None
    )
    assert (
        dry_run_tool._select_document_date(context=ctx, detected_dates=[]) is None
    )


def test_detected_dates_fill_date_fields_via_precomputed_signals(tmp_path: Path) -> None:
    """Dates from the intake classifier flow into main_date + derived labels."""
    pdf_path = tmp_path / "csf.pdf"
    _write_blank_pdf(pdf_path)
    precomputed = {
        "pdf_text_extraction_used": True,
        "method": "reused_prevalidation_inspection",
        "ocr_used": False,
        "text_char_count": 100,
        "has_text": True,
        "is_probably_scanned": False,
        "text_sample": "",
        "signals": {
            "detected_institution": "sat",
            "detected_document_type": "constancia_situacion_fiscal",
            "detected_rfcs": [],
            "detected_dates": ["07/03/2024"],
            "period_mentions": [],
            "requirement_match_confidence": 0.9,
            "mismatch_reason": None,
            "anomaly_codes": [],
        },
    }
    payload = build_pdf_metadata_dry_run_payload(
        pdf_path=pdf_path,
        document_type_code="constancia_situacion_fiscal",
        context={
            "client_legal_name": "CLIENTE DEMO, S.A. DE C.V.",
            "provider_nomenclature": "SEGURIDAD PRI",
            "expected_institution": "sat",
        },
        include_intelligence=True,
        precomputed_text_extraction=precomputed,
    )
    by_key = {item["field_key"]: item for item in payload["review_items"]}
    assert by_key["main_date"]["raw_value"] == "07/03/2024"
    assert by_key["issue_date"]["raw_value"] == "07/03/2024"
    assert by_key["full_date_label"]["raw_value"] == "07 de marzo de 2024"
    assert by_key["date_8_digits"]["raw_value"] == "07032024"
    assert by_key["taxpayer_name"]["raw_value"] == "SEGURIDAD PRI"
    # CSF carries a rulebook-fixed description.
    assert by_key["description"]["raw_value"] == "Constancia de Situación Fiscal"
