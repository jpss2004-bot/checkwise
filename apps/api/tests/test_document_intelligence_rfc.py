from __future__ import annotations

from pathlib import Path

from app.services.document_intelligence import (
    analyze_document_text,
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
    assert status.value == "prevalidado"
    assert vendor_match.result == "warning"
    assert "no coincide" in vendor_match.message
