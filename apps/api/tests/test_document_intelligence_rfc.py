from __future__ import annotations

from pathlib import Path

from app.services.document_intelligence import (
    analyze_document_text,
    compute_identity_alignment,
    compute_period_alignment,
    compute_rfc_alignment,
    extract_rfcs,
)
from app.services.pdf_validation import PdfInspectionResult
from app.services.prevalidation import build_initial_validations
from app.services.storage import StoredFile
from app.services.submission_service import status_from_inspection


def test_rfc_extraction_recovers_ocr_spaced_rfc() -> None:
    text = "Constancia SAT. RFC: ABC - 010203 - XY1. Opinion de cumplimiento."

    assert "ABC010203XY1" in extract_rfcs(text)
    signals = analyze_document_text(
        text,
        expected_requirement="Opinión de cumplimiento SAT",
        expected_institution="sat",
        expected_period="2026-M01",
        expected_rfc="ABC010203XY1",
    )

    assert signals.rfc_alignment == "match"
    assert signals.expected_rfc == "ABC010203XY1"


def test_rfc_extraction_recovers_labeled_and_compacted_rfc() -> None:
    text = "Registro Federal de Contribuyentes: A B C 0 1 0 2 0 3 X Y 1"

    assert "ABC010203XY1" in extract_rfcs(text)


def test_rfc_alignment_distinguishes_homoclave_and_mismatch() -> None:
    assert compute_rfc_alignment(["ABC010203ZZ9"], "ABC010203XY1") == "homoclave_mismatch"
    assert compute_rfc_alignment(["DEF010203XY1"], "ABC010203XY1") == "mismatch"
    assert compute_rfc_alignment([], "ABC010203XY1") == "absent"
    assert compute_rfc_alignment(["ABC010203XY1"], None) == "no_expected"


def test_rfc_mismatch_is_advisory_and_updates_vendor_match_signal() -> None:
    signals = analyze_document_text(
        "Opinion de cumplimiento SAT RFC DEF010203XY1 enero 2026",
        expected_requirement="Opinión de cumplimiento SAT",
        expected_institution="sat",
        expected_period="2026-M01",
        expected_rfc="ABC010203XY1",
    )
    inspection = PdfInspectionResult(
        is_pdf=True,
        page_count=1,
        text_sample="ok",
        text_char_count=100,
        has_text=True,
    )
    stored_file = StoredFile(
        storage_key="local://test.pdf",
        path=Path("test.pdf"),
        original_filename="test.pdf",
        mime_type="application/pdf",
        size_bytes=1024,
        sha256="a" * 64,
        extension=".pdf",
    )

    status = status_from_inspection(inspection, signals)
    vendor_match = next(
        signal
        for signal in build_initial_validations(
            stored_file,
            duplicate_found=False,
            pdf_inspection=inspection,
            document_signals=signals,
        )
        if signal.rule_code == "vendor_match"
    )

    assert signals.rfc_alignment == "mismatch"
    assert signals.mismatch_reason is None
    assert status.value == "pendiente_revision"
    assert vendor_match.result == "warning"
    assert "no coincide" in vendor_match.message


def test_missing_expected_rfc_requires_clarification() -> None:
    signals = analyze_document_text(
        "Opinion de cumplimiento SAT enero 2026 sin dato fiscal visible",
        expected_requirement="Opinión de cumplimiento SAT",
        expected_institution="sat",
        expected_period="2026-M01",
        expected_rfc="ABC010203XY1",
    )
    inspection = PdfInspectionResult(
        is_pdf=True,
        page_count=1,
        text_sample="ok",
        text_char_count=100,
        has_text=True,
    )
    stored_file = StoredFile(
        storage_key="local://test.pdf",
        path=Path("test.pdf"),
        original_filename="test.pdf",
        mime_type="application/pdf",
        size_bytes=1024,
        sha256="a" * 64,
        extension=".pdf",
    )
    vendor_match = next(
        signal
        for signal in build_initial_validations(
            stored_file,
            duplicate_found=False,
            pdf_inspection=inspection,
            document_signals=signals,
        )
        if signal.rule_code == "vendor_match"
    )

    assert signals.rfc_alignment == "absent"
    assert status_from_inspection(inspection, signals).value == "requiere_aclaracion"
    assert vendor_match.result == "fail"
    assert vendor_match.severity == "error"


def test_rfc_mismatch_caps_confidence_without_provider_facing_mismatch() -> None:
    signals = analyze_document_text(
        "Resumen de liquidacion IMSS RFC DEF010203XY1 periodo enero 2026",
        expected_requirement="Resumen de liquidación IMSS",
        expected_institution="imss",
        expected_period="2026-M01",
        expected_rfc="ABC010203XY1",
        expected_vendor_name="Servicios ABC",
        expected_client_name="Cliente Demo",
        expected_client_rfc="CLI010203AB1",
    )
    status = status_from_inspection(
        PdfInspectionResult(is_pdf=True, page_count=1, text_sample="ok", text_char_count=100, has_text=True),
        signals,
    )

    assert signals.rfc_alignment == "mismatch"
    assert signals.identity_alignment == "mismatch"
    assert signals.mismatch_reason is None
    assert signals.requirement_match_confidence is not None
    assert signals.requirement_match_confidence < 0.7
    assert status.value == "pendiente_revision"


def test_client_identity_does_not_count_as_provider_identity() -> None:
    assert (
        compute_identity_alignment(
            ["CLI010203AB1"],
            "Liquidacion de Cliente Demo RFC CLI010203AB1",
            expected_provider_rfc="ABC010203XY1",
            expected_provider_name="Servicios ABC",
            expected_client_rfc="CLI010203AB1",
            expected_client_name="Cliente Demo",
        )
        == "client_match"
    )


def test_period_alignment_understands_month_name() -> None:
    text = "Resumen de liquidacion del periodo enero de 2026."

    assert compute_period_alignment("2026-M01", text) == "match"


def test_liquidation_summary_builds_provider_evidence() -> None:
    signals = analyze_document_text(
        (
            "Instituto Mexicano del Seguro Social. Resumen de liquidacion "
            "cuotas obrero patronales. Registro patronal A123456789. "
            "RFC ABC010203XY1. Periodo enero de 2026."
        ),
        expected_requirement="Resumen de liquidación IMSS",
        expected_institution="imss",
        expected_period="2026-M01",
        expected_rfc="ABC010203XY1",
        expected_vendor_name="Servicios ABC",
        expected_client_name="Cliente Demo",
        expected_client_rfc="CLI010203AB1",
    )

    assert signals.detected_document_type == "imss_liquidacion"
    assert signals.rfc_alignment == "match"
    assert signals.identity_alignment == "match"
    assert signals.period_alignment == "match"
    assert signals.requirement_match_confidence is not None
    assert signals.requirement_match_confidence >= 0.7
    assert signals.evidence is not None
    assert signals.evidence["expected"]["provider"]["rfc"] == "ABC010203XY1"
    assert signals.evidence["extracted"]["identifiers"]["rfcs"] == ["ABC010203XY1"]
    assert signals.evidence["alignment"]["provider_identity"] == "match"
