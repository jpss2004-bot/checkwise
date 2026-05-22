"""Phase 1 — confidence-aware intake routing + boilerplate carve-out.

Pre-Phase-1 the prevalidation pipeline ignored
``requirement_match_confidence`` entirely and fired
``possible_institution_mismatch`` on documents that merely *referenced*
a sibling institution in boilerplate (Jorge Luna's 2026-05-21 feedback:
"Marca como Inconsistencia el archivo correcto"). These tests pin the
new behavior so any future tuning of thresholds or detector rules has
to come through this gate.

Scope: pure unit tests against
``app.services.submission_service.status_from_inspection`` and
``app.services.document_intelligence.analyze_document_text``. No DB,
no fixtures — the detector is deterministic at this layer.
"""

from __future__ import annotations

from app.constants.statuses import DocumentStatus
from app.services.document_intelligence import (
    DocumentSignals,
    _best_keyword_match,
    analyze_document_text,
)
from app.services.pdf_validation import PdfInspectionResult
from app.services.submission_service import status_from_inspection


def _ok_pdf() -> PdfInspectionResult:
    """A valid, readable PDF — the input shape the status branch expects."""
    return PdfInspectionResult(
        is_pdf=True,
        is_corrupt=False,
        is_encrypted=False,
        page_count=1,
        text_sample="placeholder",
        text_char_count=11,
        has_text=True,
        is_probably_scanned=False,
    )


# ---------------------------------------------------------------------------
# status_from_inspection — confidence buckets
# ---------------------------------------------------------------------------


def test_corrupt_pdf_always_requires_aclaracion() -> None:
    pdf = PdfInspectionResult(is_pdf=True, is_corrupt=True, error="boom")
    signals = DocumentSignals(requirement_match_confidence=0.95)

    assert status_from_inspection(pdf, signals) == DocumentStatus.REQUIERE_ACLARACION


def test_encrypted_pdf_always_requires_aclaracion() -> None:
    pdf = PdfInspectionResult(is_pdf=True, is_encrypted=True)
    signals = DocumentSignals(requirement_match_confidence=0.95)

    assert status_from_inspection(pdf, signals) == DocumentStatus.REQUIERE_ACLARACION


def test_high_confidence_clean_doc_is_prevalidado() -> None:
    signals = DocumentSignals(requirement_match_confidence=0.85, mismatch_reason=None)

    assert status_from_inspection(_ok_pdf(), signals) == DocumentStatus.PREVALIDADO


def test_at_prevalidation_floor_is_prevalidado() -> None:
    signals = DocumentSignals(requirement_match_confidence=0.70, mismatch_reason=None)

    assert status_from_inspection(_ok_pdf(), signals) == DocumentStatus.PREVALIDADO


def test_below_prevalidation_floor_routes_to_pendiente_revision() -> None:
    signals = DocumentSignals(requirement_match_confidence=0.69, mismatch_reason=None)

    assert status_from_inspection(_ok_pdf(), signals) == DocumentStatus.PENDIENTE_REVISION


def test_no_confidence_routes_to_pendiente_revision() -> None:
    signals = DocumentSignals(requirement_match_confidence=None, mismatch_reason=None)

    assert status_from_inspection(_ok_pdf(), signals) == DocumentStatus.PENDIENTE_REVISION


def test_high_confidence_mismatch_surfaces_to_provider() -> None:
    signals = DocumentSignals(
        requirement_match_confidence=0.8,
        mismatch_reason="doc parece X, esperado Y",
    )

    assert status_from_inspection(_ok_pdf(), signals) == DocumentStatus.POSIBLE_MISMATCH


def test_low_confidence_mismatch_routes_to_human_review() -> None:
    """A weak mismatch signal must not alarm the provider — route to review."""
    signals = DocumentSignals(
        requirement_match_confidence=0.30,
        mismatch_reason="doc parece X, esperado Y",
    )

    assert status_from_inspection(_ok_pdf(), signals) == DocumentStatus.PENDIENTE_REVISION


def test_at_mismatch_floor_still_surfaces_as_posible_mismatch() -> None:
    signals = DocumentSignals(
        requirement_match_confidence=0.50,
        mismatch_reason="doc parece X, esperado Y",
    )

    assert status_from_inspection(_ok_pdf(), signals) == DocumentStatus.POSIBLE_MISMATCH


# ---------------------------------------------------------------------------
# analyze_document_text — boilerplate carve-out
# ---------------------------------------------------------------------------


def test_sat_opinion_mentioning_imss_in_boilerplate_does_not_mismatch() -> None:
    """A SAT 32-D that boilerplate-references IMSS must not fire as mismatch.

    Jorge Luna 2026-05-21 — the most-reported false positive. The
    detector picks ``imss`` as the *best* match because ``IMSS`` shows
    up more often than ``SAT`` in the cross-institution annex, but the
    document is the correct SAT opinión. Expected outcome:
    ``possible_institution_mismatch`` is suppressed, no
    ``mismatch_reason`` is emitted, confidence stays credited.
    """
    text = (
        "Opinión de cumplimiento de obligaciones fiscales 32-D emitida por el SAT. "
        "Servicio de Administración Tributaria certifica al contribuyente. "
        "Para consultar tu situación ante el IMSS, IMSS, IMSS, IMSS, IMSS, "
        "acude a la ventanilla del Instituto Mexicano del Seguro Social."
    )

    signals = analyze_document_text(
        text,
        expected_requirement="Opinión de cumplimiento de obligaciones fiscales SAT",
        expected_institution="sat",
        expected_period="2026-04",
    )

    assert signals.mismatch_reason is None
    assert "possible_institution_mismatch" not in signals.anomaly_codes
    # SAT is mentioned, so the institution axis should be credited.
    assert signals.requirement_match_confidence is not None
    assert signals.requirement_match_confidence >= 0.3


def test_unrelated_institution_still_fires_mismatch() -> None:
    """When the expected institution is fully absent, fire the mismatch.

    Uses a free-text requirement that does NOT trigger the doc-type
    ladder (`_expected_document_type` returns None for "certificación
    general"), so the institution mismatch path is the one under test.
    """
    text = (
        "Comprobante general de pago al instituto mexicano del seguro social. "
        "Detalle administrativo."
    )

    signals = analyze_document_text(
        text,
        expected_requirement="Certificación general del proveedor",
        expected_institution="stps_repse",
        expected_period="2026-04",
    )

    assert signals.mismatch_reason is not None
    assert "possible_institution_mismatch" in signals.anomaly_codes


def test_period_anomaly_fires_when_no_mismatch_blocks_it() -> None:
    """When boilerplate suppresses the institution mismatch, period_not_confirmed
    must still fire if the expected period is missing."""
    text = (
        "Opinión de cumplimiento 32-D. SAT. Servicio de Administración Tributaria. "
        "Referencia al IMSS en boilerplate."
    )

    signals = analyze_document_text(
        text,
        expected_requirement="Opinión de cumplimiento SAT",
        expected_institution="sat",
        expected_period="2026-04",
    )

    assert signals.mismatch_reason is None
    assert "period_not_confirmed" in signals.anomaly_codes


# ---------------------------------------------------------------------------
# _best_keyword_match — tie behavior
# ---------------------------------------------------------------------------


def test_best_keyword_match_returns_unique_winner() -> None:
    """Counter is distinct-keywords-matched, not raw occurrences — two
    different SAT keywords beats a single IMSS keyword."""
    text = "sat servicio de administracion tributaria imss"
    keyword_map = {
        "sat": ["sat", "servicio de administracion tributaria"],
        "imss": ["imss"],
    }

    assert _best_keyword_match(text, keyword_map) == "sat"


def test_best_keyword_match_returns_none_on_zero_score() -> None:
    keyword_map = {
        "sat": ["sat"],
        "imss": ["imss"],
    }

    assert _best_keyword_match("documento sin keywords reconocidos", keyword_map) is None


def test_best_keyword_match_returns_none_on_positive_tie() -> None:
    """Pre-Phase-1 this would silently return ``sat`` via insertion order.

    On a positive-score tie there is no winner; the detector must say
    so instead of leaking dict insertion order as a verdict.
    """
    text = "sat e imss aparecen una vez cada uno"
    keyword_map = {
        "sat": ["sat"],
        "imss": ["imss"],
    }

    assert _best_keyword_match(text, keyword_map) is None
