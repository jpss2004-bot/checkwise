from __future__ import annotations

from app.core.metadata_rules import metadata_rule_by_code
from app.services.document_intelligence import DocumentSignals
from app.services.metadata_export import (
    _CLASSIFIER_TO_METADATA_CODE,
    _text_extraction_from_prevalidation,
)
from app.services.pdf_validation import PdfInspectionResult


def test_text_extraction_from_prevalidation_matches_intelligence_shape() -> None:
    inspection = PdfInspectionResult(
        is_pdf=True,
        page_count=2,
        text_sample="constancia de situacion fiscal demo",
        text_char_count=35,
        has_text=True,
        is_probably_scanned=False,
    )
    signals = DocumentSignals(
        detected_institution="sat",
        detected_document_type="constancia_situacion_fiscal",
        detected_rfcs=["XAXX010101000"],
        requirement_match_confidence=0.91,
        anomaly_codes=["period_not_confirmed"],
    )

    extraction = _text_extraction_from_prevalidation(inspection, signals)

    # ocr_used stays False so the dry-run safety check (OCR requires
    # enable_ocr) holds even when intake itself OCR'd a scan.
    assert extraction["ocr_used"] is False
    assert extraction["method"] == "reused_prevalidation_inspection"
    assert extraction["text_sample"] == "constancia de situacion fiscal demo"
    assert extraction["has_text"] is True
    assert extraction["is_probably_scanned"] is False
    assert extraction["text_char_count"] == 35
    assert extraction["signals"]["detected_institution"] == "sat"
    assert extraction["signals"]["detected_document_type"] == "constancia_situacion_fiscal"
    assert extraction["signals"]["detected_rfcs"] == ["XAXX010101000"]
    assert extraction["signals"]["requirement_match_confidence"] == 0.91
    assert extraction["signals"]["anomaly_codes"] == ["period_not_confirmed"]

    # The shape must line up with what build_pdf_metadata_dry_run_payload
    # consumes from _build_pdf_text_extraction; drift here silently breaks
    # the reuse path.
    assert set(extraction) == {
        "pdf_text_extraction_used",
        "method",
        "ocr_used",
        "text_char_count",
        "has_text",
        "is_probably_scanned",
        "text_sample",
        "signals",
    }
    assert set(extraction["signals"]) == {
        "detected_institution",
        "detected_document_type",
        "detected_rfcs",
        "detected_dates",
        "period_mentions",
        "requirement_match_confidence",
        "mismatch_reason",
        "anomaly_codes",
    }


def test_classifier_bridge_targets_are_real_rule_codes() -> None:
    # A bridge entry pointing at a non-existent rule code would raise only at
    # upload time; assert every target resolves now.
    for classifier_code, metadata_code in _CLASSIFIER_TO_METADATA_CODE.items():
        rule = metadata_rule_by_code(metadata_code)
        assert rule.code == metadata_code, classifier_code


def test_ai_assisted_field_schema_selects_ai_fields_only() -> None:
    from app.core.metadata_rules import ai_assisted_field_schema_for_document_type

    schema = ai_assisted_field_schema_for_document_type("constancia_situacion_fiscal")
    keys = {field["field_key"] for field in schema}
    assert "main_date" in keys
    assert "taxpayer_name" in keys
    # Deterministic-only fields (no ``ai_assisted`` method) are excluded.
    assert "area_interna" not in keys
    for field in schema:
        assert set(field) == {"field_key", "label", "requirement_level", "description"}


def test_suggestions_by_key_indexes_and_last_write_wins() -> None:
    from app.services.metadata_export import _suggestions_by_key

    out = _suggestions_by_key(
        [
            {"field_key": "main_date", "value": "a"},
            {"field_key": "main_date", "value": "b"},
            {"field_key": "", "value": "dropped"},
        ]
    )
    assert out == {"main_date": {"field_key": "main_date", "value": "b"}}


def test_text_extraction_from_inspection_shape() -> None:
    from app.models import DocumentInspection
    from app.services.metadata_export import _text_extraction_from_inspection

    inspection = DocumentInspection(
        document_id="d1",
        is_pdf=True,
        detected_institution="sat",
        detected_document_type="constancia_situacion_fiscal",
        detected_rfcs=["XAXX010101000"],
        requirement_match_confidence=0.8,
        text_char_count=10,
        has_text=True,
        is_probably_scanned=False,
    )
    extraction = _text_extraction_from_inspection(inspection)
    assert extraction["ocr_used"] is False
    assert extraction["method"] == "reused_inspection_row"
    assert extraction["text_sample"] == ""
    assert extraction["signals"]["detected_institution"] == "sat"
    assert extraction["signals"]["detected_rfcs"] == ["XAXX010101000"]
    assert set(extraction) == {
        "pdf_text_extraction_used",
        "method",
        "ocr_used",
        "text_char_count",
        "has_text",
        "is_probably_scanned",
        "text_sample",
        "signals",
    }
