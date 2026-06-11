"""Document-revalidation Phase A — pure-local PDF authenticity forensics.

Covers ``app.services.document_forensics.analyze_pdf_forensics``: the
named-reason checks (suspicious generator, edited after creation,
incremental updates, created before the claimed period, embedded
JavaScript, stripped metadata), the risk rollup (clean / suspicious /
high_risk), and the swallow-everything contract (garbage bytes never
raise — an analysis failure must NEVER block an upload).

Test PDFs are built in-test with ``pypdf.PdfWriter`` (metadata via
``add_metadata``); the stripped-metadata case uses a hand-assembled
minimal PDF because pypdf's writer cannot emit a text layer and always
stamps a ``/Producer``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfWriter

from app.services.document_forensics import (
    SUSPICIOUS_GENERATORS,
    ForensicsResult,
    analyze_pdf_forensics,
    parse_pdf_date,
)

# ---------------------------------------------------------------------------
# PDF builders
# ---------------------------------------------------------------------------


def _write_pdf(
    tmp_path: Path,
    name: str,
    *,
    metadata: dict[str, str] | None = None,
    with_js: bool = False,
) -> Path:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    if with_js:
        writer.add_js("app.alert('hola');")
    if metadata is not None:
        writer.add_metadata(metadata)
    path = tmp_path / name
    with path.open("wb") as fh:
        writer.write(fh)
    return path


def _minimal_text_pdf_bytes() -> bytes:
    """Hand-assembled single-page PDF with a text layer and NO /Info dict.

    pypdf's writer always stamps ``/Producer: pypdf`` and cannot draw
    text, so the stripped-metadata check (digitally generated + no
    Producer + no CreationDate) needs a manually built file. Offsets in
    the xref table are computed, so the file is structurally valid.
    """
    stream = (
        b"BT /F1 18 Tf 72 720 Td "
        b"(Constancia de situacion fiscal SAT ejercicio 2026) Tj ET"
    )
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length "
        + str(len(stream)).encode()
        + b" >>\nstream\n"
        + stream
        + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_pos = len(out)
    out += b"xref\n0 6\n0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n"
        + str(xref_pos).encode()
        + b"\n%%EOF\n"
    )
    return bytes(out)


def _append_incremental_save(path: Path) -> None:
    """Append a second ``startxref … %%EOF`` tail, as an incremental save does.

    pypdf resolves the trailer from the *last* ``startxref`` in the
    file, so the appended tail re-points at the original xref table —
    structurally what a real editor's incremental update looks like
    (minus new objects), and it keeps the file parseable.
    """
    data = path.read_bytes()
    tail_start = data.rfind(b"startxref")
    assert tail_start != -1
    path.write_bytes(data + b"\n% incremental save\n" + data[tail_start:])


def _analyze(path: Path, *, period_key: str | None = None) -> ForensicsResult:
    return analyze_pdf_forensics(path, period_key=period_key, pdf_metadata=None)


def _codes(result: ForensicsResult) -> set[str]:
    return {reason.code for reason in result.reasons}


# ---------------------------------------------------------------------------
# Clean baseline
# ---------------------------------------------------------------------------


def test_clean_document_rolls_up_clean(tmp_path: Path) -> None:
    path = _write_pdf(
        tmp_path,
        "clean.pdf",
        metadata={
            "/Producer": "SAT - Servicio de Administración Tributaria",
            "/CreationDate": "D:20260410120000",
            "/ModDate": "D:20260410120100",  # 1 min jitter — under threshold
        },
    )
    result = _analyze(path, period_key="2026-M04")
    assert result.risk == "clean"
    assert result.analyzed is True
    assert result.reasons == []
    assert result.forensics["eof_count"] == 1
    assert result.forensics["has_javascript"] is False


# ---------------------------------------------------------------------------
# Suspicious generator
# ---------------------------------------------------------------------------


def test_canva_producer_is_suspicious_with_named_reason(tmp_path: Path) -> None:
    path = _write_pdf(tmp_path, "canva.pdf", metadata={"/Producer": "Canva"})
    result = _analyze(path)
    assert result.risk == "suspicious"
    reason = next(r for r in result.reasons if r.code == "suspicious_generator")
    assert reason.severity == "medium"
    assert "Canva" in reason.detail_es
    assert "documentos oficiales" in reason.detail_es


@pytest.mark.parametrize(
    "producer",
    [
        "Microsoft Word 2016",
        "Adobe Photoshop 25.0",
        "iLovePDF",
        "LibreOffice 7.6 Writer",
        "Foxit PDF Editor 13.0",
    ],
)
def test_consumer_editors_are_flagged(tmp_path: Path, producer: str) -> None:
    path = _write_pdf(tmp_path, "editor.pdf", metadata={"/Producer": producer})
    result = _analyze(path)
    assert "suspicious_generator" in _codes(result)
    assert result.risk == "suspicious"


def test_creator_field_is_also_checked(tmp_path: Path) -> None:
    path = _write_pdf(
        tmp_path,
        "creator.pdf",
        metadata={"/Producer": "Acrobat Distiller", "/Creator": "Canva"},
    )
    assert "suspicious_generator" in _codes(_analyze(path))


def test_suspicious_generator_list_is_exported() -> None:
    # The module constant is part of the reviewer-facing contract.
    assert "canva" in SUSPICIOUS_GENERATORS
    assert "ilovepdf" in SUSPICIOUS_GENERATORS


# ---------------------------------------------------------------------------
# Edited after creation (ModDate gap + incremental updates)
# ---------------------------------------------------------------------------


def test_moddate_after_creation_flags_edited(tmp_path: Path) -> None:
    path = _write_pdf(
        tmp_path,
        "edited.pdf",
        metadata={
            "/Producer": "Acrobat Distiller",
            "/CreationDate": "D:20260401120000",
            "/ModDate": "D:20260401150000",  # +3 h
        },
    )
    result = _analyze(path)
    assert result.risk == "suspicious"
    reason = next(r for r in result.reasons if r.code == "edited_after_creation")
    assert reason.severity == "medium"
    assert "01/04/2026 12:00" in reason.detail_es
    assert "01/04/2026 15:00" in reason.detail_es


def test_moddate_gap_over_30_days_is_high_risk(tmp_path: Path) -> None:
    path = _write_pdf(
        tmp_path,
        "edited-late.pdf",
        metadata={
            "/Producer": "Acrobat Distiller",
            "/CreationDate": "D:20260101120000",
            "/ModDate": "D:20260315120000",  # +73 days
        },
    )
    result = _analyze(path)
    assert result.risk == "high_risk"
    reason = next(r for r in result.reasons if r.code == "edited_after_creation")
    assert reason.severity == "high"


def test_multiple_eof_markers_flag_incremental_update(tmp_path: Path) -> None:
    path = _write_pdf(
        tmp_path, "incremental.pdf", metadata={"/Producer": "Acrobat Distiller"}
    )
    _append_incremental_save(path)
    result = _analyze(path)
    assert result.forensics["eof_count"] == 2
    assert result.forensics["incremental_updates"] == 1
    assert result.risk == "suspicious"
    reason = next(r for r in result.reasons if r.code == "edited_after_creation")
    assert reason.severity == "medium"
    assert "escrituras incrementales" in reason.detail_es


def test_moddate_and_incremental_emit_one_combined_reason(tmp_path: Path) -> None:
    """Both edit signals fire → ONE reason at the higher severity."""
    path = _write_pdf(
        tmp_path,
        "both.pdf",
        metadata={
            "/Producer": "Acrobat Distiller",
            "/CreationDate": "D:20260101120000",
            "/ModDate": "D:20260315120000",  # high (>30 d)
        },
    )
    _append_incremental_save(path)
    result = _analyze(path)
    edit_reasons = [r for r in result.reasons if r.code == "edited_after_creation"]
    assert len(edit_reasons) == 1
    assert edit_reasons[0].severity == "high"
    assert result.forensics["eof_count"] == 2  # raw counts preserved


# ---------------------------------------------------------------------------
# Created before the claimed period
# ---------------------------------------------------------------------------


def test_created_before_period_is_high_risk(tmp_path: Path) -> None:
    # Declaration for April created in February — impossible.
    path = _write_pdf(
        tmp_path,
        "early.pdf",
        metadata={
            "/Producer": "Acrobat Distiller",
            "/CreationDate": "D:20260210090000",
        },
    )
    result = _analyze(path, period_key="2026-M04")
    assert result.risk == "high_risk"
    reason = next(r for r in result.reasons if r.code == "created_before_period")
    assert reason.severity == "high"
    assert "2026-M04" in reason.detail_es


def test_created_inside_period_is_not_flagged(tmp_path: Path) -> None:
    path = _write_pdf(
        tmp_path,
        "ok-period.pdf",
        metadata={
            "/Producer": "Acrobat Distiller",
            "/CreationDate": "D:20260415090000",
        },
    )
    result = _analyze(path, period_key="2026-M04")
    assert "created_before_period" not in _codes(result)
    assert result.risk == "clean"


def test_grace_window_just_before_period_is_tolerated(tmp_path: Path) -> None:
    # March 29 for an April period — inside the small grace window.
    path = _write_pdf(
        tmp_path,
        "grace.pdf",
        metadata={
            "/Producer": "Acrobat Distiller",
            "/CreationDate": "D:20260329090000",
        },
    )
    result = _analyze(path, period_key="2026-M04")
    assert "created_before_period" not in _codes(result)


def test_non_monthly_period_keys_skip_the_check(tmp_path: Path) -> None:
    path = _write_pdf(
        tmp_path,
        "bimestral.pdf",
        metadata={
            "/Producer": "Acrobat Distiller",
            "/CreationDate": "D:20250101090000",
        },
    )
    # Bimester / annual / onboarding keys carry different period
    # semantics — the analyzer must not guess.
    for period_key in ("2026-B1", "2026-Q1", "2026-A", "onb-repse-2026", None):
        result = _analyze(path, period_key=period_key)
        assert "created_before_period" not in _codes(result), period_key


# ---------------------------------------------------------------------------
# Embedded JavaScript
# ---------------------------------------------------------------------------


def test_embedded_javascript_is_high_risk(tmp_path: Path) -> None:
    path = _write_pdf(tmp_path, "js.pdf", with_js=True)
    result = _analyze(path)
    assert result.risk == "high_risk"
    assert result.forensics["has_javascript"] is True
    reason = next(r for r in result.reasons if r.code == "embedded_javascript")
    assert reason.severity == "high"
    assert "JavaScript" in reason.detail_es


# ---------------------------------------------------------------------------
# Stripped metadata (info — never elevates alone)
# ---------------------------------------------------------------------------


def test_stripped_metadata_is_info_and_does_not_elevate(tmp_path: Path) -> None:
    path = tmp_path / "stripped.pdf"
    path.write_bytes(_minimal_text_pdf_bytes())
    result = _analyze(path)
    reason = next(r for r in result.reasons if r.code == "stripped_metadata")
    assert reason.severity == "info"
    assert result.risk == "clean"  # info alone never elevates
    assert result.forensics["has_text_layer"] is True
    assert result.forensics["producer"] is None


# ---------------------------------------------------------------------------
# Fail-open contract + plumbing
# ---------------------------------------------------------------------------


def test_garbage_bytes_never_raise(tmp_path: Path) -> None:
    path = tmp_path / "renamed.pdf"
    path.write_bytes(b"esto no es un PDF, es un .txt renombrado\n")
    result = analyze_pdf_forensics(path, period_key="2026-M04", pdf_metadata=None)
    assert result.risk is None
    assert result.analyzed is False
    assert "forensics_error" in result.forensics


def test_missing_file_never_raises(tmp_path: Path) -> None:
    result = analyze_pdf_forensics(
        tmp_path / "no-existe.pdf", period_key=None, pdf_metadata=None
    )
    assert result.risk is None
    assert "forensics_error" in result.forensics


def test_caller_metadata_is_reused(tmp_path: Path) -> None:
    """When intake already extracted metadata, the analyzer trusts it."""
    path = _write_pdf(tmp_path, "meta.pdf")  # actual producer: pypdf
    result = analyze_pdf_forensics(
        path, period_key=None, pdf_metadata={"/Producer": "Canva"}
    )
    assert "suspicious_generator" in _codes(result)
    assert result.forensics["producer"] == "Canva"


def test_reasons_sorted_high_to_info(tmp_path: Path) -> None:
    path = _write_pdf(
        tmp_path,
        "multi.pdf",
        metadata={"/Producer": "Canva", "/CreationDate": "D:20260110090000"},
        with_js=True,
    )
    result = _analyze(path, period_key="2026-M04")
    assert result.risk == "high_risk"
    severities = [r.severity for r in result.reasons]
    assert severities == sorted(
        severities, key=lambda s: {"high": 0, "medium": 1, "info": 2}[s]
    )
    assert result.reasons[0].severity == "high"


def test_reasons_payload_is_json_ready(tmp_path: Path) -> None:
    path = _write_pdf(tmp_path, "payload.pdf", metadata={"/Producer": "Canva"})
    result = _analyze(path)
    payload = result.reasons_payload()
    assert payload == [
        {
            "code": "suspicious_generator",
            "severity": "medium",
            "detail_es": payload[0]["detail_es"],
        }
    ]
    assert "Canva" in payload[0]["detail_es"]


@pytest.mark.parametrize(
    ("raw", "expected_prefix"),
    [
        ("D:20260401120000", "2026-04-01T12:00:00"),
        ("D:20260401120000-06'00'", "2026-04-01T12:00:00"),
        ("20260401", "2026-04-01T00:00:00"),
        ("D:2026", "2026-01-01T00:00:00"),
    ],
)
def test_parse_pdf_date_defensive_formats(raw: str, expected_prefix: str) -> None:
    parsed = parse_pdf_date(raw)
    assert parsed is not None
    assert parsed.isoformat().startswith(expected_prefix)


@pytest.mark.parametrize("raw", [None, "", "sin fecha", "D:0000xx"])
def test_parse_pdf_date_garbage_returns_none(raw: str | None) -> None:
    assert parse_pdf_date(raw) is None
