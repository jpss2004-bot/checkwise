"""Phase D — image tamper forensics on scanned documents.

Unit coverage builds synthetic scans with Pillow (seeded PRNG, fully
deterministic, no fixtures from disk) and wraps them in a hand-rolled
minimal PDF that embeds the EXACT JPEG bytes as a DCTDecode XObject —
Pillow's own PDF writer re-encodes the raster, which would destroy the
compression-history differential the ELA check measures.

Integration coverage drives the shadow runner end-to-end with the
heavy analysis mocked, asserting the Phase-C-style merge semantics
(strip-and-replace under the image codes, coexistence with LLM
reasons, fail-open everywhere).
"""

from __future__ import annotations

import io
import random
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from app.core import config as config_module
from app.services.document_analysis.base import AnalysisResult, DocumentSignals
from app.services.document_analysis.spend_limiter import reset_daily_quota
from app.services.document_forensics import (
    SEVERITY_MEDIUM,
    RiskReason,
)
from app.services.document_image_forensics import (
    COPY_MOVE_CODE,
    ELA_ANOMALY_CODE,
    ImageTamperResult,
    analyze_image_tampering,
)

settings = config_module.settings


@pytest.fixture(autouse=True)
def _reset_spend_buckets() -> None:
    reset_daily_quota()


# ---------------------------------------------------------------------------
# Synthetic-scan builders
# ---------------------------------------------------------------------------


def _pdf_with_jpeg(
    path: Path, jpeg: bytes, width: int, height: int, colorspace: str = "DeviceGray"
) -> Path:
    """Minimal one-page PDF embedding ``jpeg`` verbatim as DCTDecode.

    Byte-exact embedding is the point: the analysis must decode the
    same pixels the test encoded, with the same compression history.
    """
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []

    def write_obj(number: int, body: bytes, stream: bytes | None = None) -> None:
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % number)
        out.write(body)
        if stream is not None:
            out.write(b"\nstream\n")
            out.write(stream)
            out.write(b"\nendstream")
        out.write(b"\nendobj\n")

    content = b"q 612 0 0 792 0 0 cm /Im0 Do Q"
    write_obj(1, b"<< /Type /Catalog /Pages 2 0 R >>")
    write_obj(2, b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    write_obj(
        3,
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>",
    )
    write_obj(
        4,
        b"<< /Type /XObject /Subtype /Image /Width %d /Height %d "
        b"/ColorSpace /%s /BitsPerComponent 8 /Filter /DCTDecode "
        b"/Length %d >>" % (width, height, colorspace.encode(), len(jpeg)),
        jpeg,
    )
    write_obj(5, b"<< /Length %d >>" % len(content), content)
    xref_pos = out.tell()
    out.write(b"xref\n0 6\n0000000000 65535 f \n")
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    out.write(
        b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % xref_pos
    )
    path.write_bytes(out.getvalue())
    return path


def _noise_image(w: int, h: int, seed: int = 11, lo: int = 100, hi: int = 170):
    """Scan-like grayscale noise from a FIXED-seed PRNG (deterministic)."""
    rng = random.Random(seed)
    img = Image.new("L", (w, h))
    img.putdata([rng.randint(lo, hi) for _ in range(w * h)])
    return img


def _jpeg_bytes(img, quality: int, subsampling: int | None = None) -> bytes:
    buf = io.BytesIO()
    kwargs: dict = {"quality": quality}
    if subsampling is not None:
        kwargs["subsampling"] = subsampling
    img.save(buf, "JPEG", **kwargs)
    return buf.getvalue()


def _jpeg_roundtrip(img, quality: int):
    out = Image.open(io.BytesIO(_jpeg_bytes(img, quality)))
    out.load()
    return out


def _color_checker(w: int = 96, h: int = 96):
    """Saturated 1px red/blue checker — fresh digital detail that a
    standard chroma-subsampled q90 re-encode cannot reproduce."""
    patch = Image.new("RGB", (w, h))
    patch.putdata(
        [
            (255, 0, 0) if (x + y) % 2 else (0, 0, 255)
            for y in range(h)
            for x in range(w)
        ]
    )
    return patch


def _reason_codes(result: ImageTamperResult) -> list[str]:
    return [reason.code for reason in result.reasons]


# ---------------------------------------------------------------------------
# Unit — analyze_image_tampering on synthetic PDFs
# ---------------------------------------------------------------------------


class TestAnalyzeImageTampering:
    def test_clean_scan_has_zero_reasons(self, tmp_path):
        base = _noise_image(900, 1200)
        pdf = _pdf_with_jpeg(
            tmp_path / "clean.pdf", _jpeg_bytes(base, 85), 900, 1200
        )
        result = analyze_image_tampering(pdf)
        assert result.analyzed is True
        assert result.error is None
        assert result.reasons == []
        assert result.evidence["pages"][0]["page"] == 1
        assert result.evidence["pages"][0]["source_format"] == "JPEG"
        assert isinstance(result.evidence["duration_ms"], int)

    def test_copy_move_forgery_is_flagged_once_with_offset(self, tmp_path):
        forged = _noise_image(900, 1200)
        # Clone a 64px region within the page. The offset is a multiple
        # of 8 so the cloned blocks share the JPEG block grid phase and
        # decode pixel-identically (as real digital copy-paste does).
        region = forged.crop((48, 48, 112, 112))
        forged.paste(region, (304, 400))
        pdf = _pdf_with_jpeg(
            tmp_path / "forged.pdf", _jpeg_bytes(forged, 85), 900, 1200
        )
        result = analyze_image_tampering(pdf)
        assert result.analyzed is True
        assert _reason_codes(result) == [COPY_MOVE_CODE]
        reason = result.reasons[0]
        assert reason.severity == SEVERITY_MEDIUM
        assert "página 1" in reason.detail_es
        evidence = result.evidence["copy_move"]
        assert evidence["offset"] == [304 - 48, 400 - 48]
        assert evidence["pair_count"] >= 4

    def test_white_page_with_duplicated_blank_regions_does_not_flag(
        self, tmp_path
    ):
        # Uniform white duplicates trivially; the variance floor must
        # refuse to hash those blocks at all.
        white = Image.new("L", (900, 1200), 252)
        blank = white.crop((0, 0, 64, 64))
        white.paste(blank, (304, 400))
        pdf = _pdf_with_jpeg(
            tmp_path / "white.pdf", _jpeg_bytes(white, 85), 900, 1200
        )
        result = analyze_image_tampering(pdf)
        assert result.analyzed is True
        assert result.reasons == []
        assert result.evidence["pages"][0]["copy_move"]["blocks_hashed"] == 0

    def test_ela_flags_fresh_spliced_patch(self, tmp_path):
        # A q85-compressed scan with a freshly-drawn high-contrast
        # digital patch spliced in, re-encoded at high quality (q95,
        # 4:4:4 — the forger preserving their work). The patch carries
        # detail a standard q90 re-encode cannot reproduce, so its
        # cells show an error level inconsistent with the scan.
        base = _jpeg_roundtrip(_noise_image(900, 1200).convert("RGB"), 85)
        spliced = base.copy()
        spliced.paste(_color_checker(), (320, 512))
        pdf = _pdf_with_jpeg(
            tmp_path / "spliced.pdf",
            _jpeg_bytes(spliced, 95, subsampling=0),
            900,
            1200,
            colorspace="DeviceRGB",
        )
        result = analyze_image_tampering(pdf)
        assert result.analyzed is True
        assert ELA_ANOMALY_CODE in _reason_codes(result)
        reason = next(r for r in result.reasons if r.code == ELA_ANOMALY_CODE)
        assert reason.severity == SEVERITY_MEDIUM
        assert "página 1" in reason.detail_es
        evidence = result.evidence["ela"]
        assert evidence["cluster_size"] >= 2
        assert evidence["median_cell_error"] <= 10.0
        # The cluster sits where the patch was pasted (32px cells).
        assert [320 // 32, 512 // 32] in evidence["cluster_cells"]

    def test_uniformly_recompressed_scan_does_not_flag(self, tmp_path):
        # Whole image re-encoded twice (q85 then q90): error is uniform,
        # not localized — aggressive recompression, not tampering.
        twice = _jpeg_roundtrip(_jpeg_roundtrip(_noise_image(900, 1200), 85), 90)
        pdf = _pdf_with_jpeg(
            tmp_path / "recompressed.pdf", _jpeg_bytes(twice, 90), 900, 1200
        )
        result = analyze_image_tampering(pdf)
        assert result.analyzed is True
        assert result.reasons == []

    def test_global_high_error_skips_ela_instead_of_flagging(self, tmp_path):
        # EVERY cell carries unreproducible detail (whole page is fresh
        # saturated checker): the global-median guard must read this as
        # aggressive-recompression-style uniform error and skip.
        full = _color_checker(900, 1200)
        pdf = _pdf_with_jpeg(
            tmp_path / "uniform_high.pdf",
            _jpeg_bytes(full, 95, subsampling=0),
            900,
            1200,
            colorspace="DeviceRGB",
        )
        result = analyze_image_tampering(pdf)
        assert result.analyzed is True
        assert result.reasons == []
        assert (
            result.evidence["pages"][0]["ela"]["skipped"] == "global_error_high"
        )

    def test_small_images_are_skipped(self, tmp_path):
        tiny = _noise_image(280, 600)  # < 300px on one edge
        pdf = _pdf_with_jpeg(tmp_path / "tiny.pdf", _jpeg_bytes(tiny, 85), 280, 600)
        result = analyze_image_tampering(pdf)
        assert result.analyzed is True
        assert result.reasons == []
        assert result.evidence["pages"][0]["skipped"] == "no_scan_image"

    def test_garbage_file_fails_open(self, tmp_path):
        garbage = tmp_path / "garbage.pdf"
        garbage.write_bytes(b"this is definitely not a pdf")
        result = analyze_image_tampering(garbage)
        assert result.analyzed is False
        assert result.error
        assert result.reasons == []

    def test_missing_file_fails_open(self, tmp_path):
        result = analyze_image_tampering(tmp_path / "nope.pdf")
        assert result.analyzed is False
        assert result.error

    def test_severity_never_exceeds_medium(self, tmp_path):
        # Both checks firing on one document still tops out at medium
        # per reason (→ Sospechoso max, never Alto riesgo alone).
        base = _jpeg_roundtrip(_noise_image(900, 1200).convert("RGB"), 85)
        forged = base.copy()
        forged.paste(_color_checker(), (320, 512))
        region = forged.crop((48, 48, 112, 112))
        forged.paste(region, (304, 800))
        pdf = _pdf_with_jpeg(
            tmp_path / "double.pdf",
            _jpeg_bytes(forged, 95, subsampling=0),
            900,
            1200,
            colorspace="DeviceRGB",
        )
        result = analyze_image_tampering(pdf)
        assert result.analyzed is True
        assert result.reasons  # at least one finding
        assert all(reason.severity == SEVERITY_MEDIUM for reason in result.reasons)

    def test_downscale_keeps_oversized_scans_inside_budget(self, tmp_path):
        # A 2480px-wide scan must be downscaled before the pixel loops;
        # the whole document must stay well inside the ~2s budget.
        big = _noise_image(1240, 1750).resize((2480, 3500))
        pdf = _pdf_with_jpeg(
            tmp_path / "big.pdf", _jpeg_bytes(big, 85), 2480, 3500
        )
        result = analyze_image_tampering(pdf)
        assert result.analyzed is True
        page = result.evidence["pages"][0]
        assert max(page["analyzed_size"]) <= 1200
        assert result.evidence["duration_ms"] < 2000
        print(f"\n[perf] oversized scan analyzed in {result.evidence['duration_ms']} ms")


# ---------------------------------------------------------------------------
# Integration — shadow runner escalation path (heavy analysis mocked)
# ---------------------------------------------------------------------------


def _copy_move_result() -> ImageTamperResult:
    return ImageTamperResult(
        analyzed=True,
        reasons=[
            RiskReason(
                code=COPY_MOVE_CODE,
                severity=SEVERITY_MEDIUM,
                detail_es=(
                    "Forense de imagen: se detectaron regiones duplicadas "
                    "dentro de la página 1 — patrón típico de copiar-y-pegar."
                ),
            )
        ],
        evidence={"copy_move": {"offset": [256, 352], "pair_count": 49}, "duration_ms": 57},
    )


def _provider(result: AnalysisResult) -> MagicMock:
    provider = MagicMock()
    provider.provider_id = result.provider_id
    provider.analyze.return_value = result
    return provider


def _triage_result(*, confidence: float = 0.9, authenticity: dict | None = None):
    return AnalysisResult(
        provider_id="anthropic:claude-haiku-4-5",
        prompt_version="base.v2",
        latency_ms=10,
        signals=DocumentSignals(
            detected_institution="sat",
            detected_document_type="csf",
            requirement_match_confidence=confidence,
        ),
        error=None,
        authenticity=authenticity
        or {"concerns": [], "looks_fabricated": False, "confidence": 0.95},
    )


class TestShadowRunnerImageForensics:
    @pytest.fixture
    def db_setup(self):
        """In-memory DB + Submission/Document/Inspection rows.

        Mirrors the fixture in ``tests/test_document_analysis.py`` —
        the runner opens its own ``SessionLocal``, so both the session
        module and the runner module get the test sessionmaker.
        """
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        from app.db import session as session_module
        from app.db.base import Base
        from app.models import Document, DocumentInspection, Submission
        from app.services.document_analysis import shadow_runner as runner_module

        engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        Base.metadata.create_all(bind=engine)

        original_session_local = session_module.SessionLocal
        original_runner_session = runner_module.SessionLocal
        session_module.SessionLocal = TestingSession
        runner_module.SessionLocal = TestingSession

        db = TestingSession()
        try:
            sub = Submission(
                client_id="cli-1",
                vendor_id="ven-1",
                period_id="per-1",
                institution_id="ins-1",
                requirement_id="req-1",
                load_type="mensual",
                source="portal",
                status="pendiente_revision",
            )
            db.add(sub)
            db.flush()
            doc = Document(
                submission_id=sub.id,
                storage_key="local/test.pdf",
                original_filename="test.pdf",
                size_bytes=1024,
                sha256="deadbeef",
                status="pendiente_revision",
            )
            db.add(doc)
            db.flush()
            inspection = DocumentInspection(
                document_id=doc.id,
                is_pdf=True,
                page_count=1,
                text_char_count=0,
                has_text=False,
                is_probably_scanned=True,
            )
            db.add(inspection)
            db.commit()
            ids = {"document_id": doc.id, "submission_id": sub.id}
        finally:
            db.close()

        yield ids

        session_module.SessionLocal = original_session_local
        runner_module.SessionLocal = original_runner_session

    def _set_inspection(self, *, scanned=True, risk=None, reasons=None):
        from app.db.session import SessionLocal
        from app.models import DocumentInspection

        db = SessionLocal()
        try:
            insp = db.query(DocumentInspection).first()
            insp.is_probably_scanned = scanned
            insp.authenticity_risk = risk
            insp.risk_reasons = reasons
            db.commit()
        finally:
            db.close()

    def _inspection(self):
        from app.db.session import SessionLocal
        from app.models import DocumentInspection

        db = SessionLocal()
        try:
            return db.query(DocumentInspection).first()
        finally:
            db.close()

    def _run(self, db_setup, tmp_path, *, triage: AnalysisResult):
        """Drive the runner with a mocked triage and NO escalation
        provider (skip marker) — image forensics must run regardless."""
        from io import BytesIO

        from pypdf import PdfWriter

        from app.services.document_analysis.shadow_runner import run_shadow_analysis

        buf = BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        writer.write(buf)
        pdf_path = tmp_path / "doc.pdf"
        pdf_path.write_bytes(buf.getvalue())

        provider = _provider(triage)
        with patch(
            "app.services.document_analysis.shadow_runner.build_document_analysis_provider",
            side_effect=lambda tier="triage": provider if tier == "triage" else None,
        ):
            run_shadow_analysis(
                document_id=db_setup["document_id"],
                submission_id=db_setup["submission_id"],
                pdf_path=str(pdf_path),
                requirement_code="REC-SAT-CSF-2026",
                requirement_name="CSF",
                institution_code="sat",
                period_code="2026-01",
                org_id="cli-1",
            )

    def test_escalation_on_scanned_doc_runs_and_merges_image_reasons(
        self, tmp_path, db_setup
    ):
        # Clean-forensics scanned doc; low triage confidence fires the
        # escalation gate; mocked copy-move finding must flip the
        # verdict clean → suspicious.
        self._set_inspection(scanned=True, risk="clean", reasons=[])
        with patch(
            "app.services.document_analysis.shadow_runner.analyze_image_tampering",
            return_value=_copy_move_result(),
        ) as analyze_mock:
            self._run(db_setup, tmp_path, triage=_triage_result(confidence=0.3))

        analyze_mock.assert_called_once()
        insp = self._inspection()
        codes = [r["code"] for r in insp.risk_reasons]
        assert codes == [COPY_MOVE_CODE]
        assert insp.authenticity_risk == "suspicious"
        forensics_meta = insp.shadow_signals["_tiers"]["image_forensics"]
        assert forensics_meta == {"ran": True, "findings": 1, "duration_ms": 57}
        assert insp.forensics["image_forensics"]["copy_move"]["offset"] == [256, 352]

    def test_non_scanned_doc_skips_image_forensics(self, tmp_path, db_setup):
        self._set_inspection(scanned=False, risk="clean", reasons=[])
        with patch(
            "app.services.document_analysis.shadow_runner.analyze_image_tampering",
            return_value=_copy_move_result(),
        ) as analyze_mock:
            self._run(db_setup, tmp_path, triage=_triage_result(confidence=0.3))

        analyze_mock.assert_not_called()
        insp = self._inspection()
        assert insp.authenticity_risk == "clean"
        assert insp.risk_reasons == []
        assert insp.shadow_signals["_tiers"]["image_forensics"] == {
            "ran": False,
            "skipped": "not_scanned",
        }

    def test_no_escalation_triggers_means_no_image_forensics(
        self, tmp_path, db_setup
    ):
        # Confident clean triage on a clean doc: no escalation gate, so
        # the CPU-heavy pass must not run at all.
        self._set_inspection(scanned=True, risk="clean", reasons=[])
        with patch(
            "app.services.document_analysis.shadow_runner.analyze_image_tampering",
            return_value=_copy_move_result(),
        ) as analyze_mock:
            self._run(db_setup, tmp_path, triage=_triage_result(confidence=0.9))

        analyze_mock.assert_not_called()
        insp = self._inspection()
        assert "_tiers" not in (insp.shadow_signals or {})
        assert insp.risk_reasons == []

    def test_rerun_strips_and_replaces_image_reasons(self, tmp_path, db_setup):
        self._set_inspection(scanned=True, risk="clean", reasons=[])
        with patch(
            "app.services.document_analysis.shadow_runner.analyze_image_tampering",
            return_value=_copy_move_result(),
        ):
            self._run(db_setup, tmp_path, triage=_triage_result(confidence=0.3))
            self._run(db_setup, tmp_path, triage=_triage_result(confidence=0.3))

        insp = self._inspection()
        copy_move = [r for r in insp.risk_reasons if r["code"] == COPY_MOVE_CODE]
        assert len(copy_move) == 1  # strip-and-replace, never accumulate
        assert insp.authenticity_risk == "suspicious"

    def test_clean_rerun_strips_stale_image_reasons(self, tmp_path, db_setup):
        self._set_inspection(scanned=True, risk="clean", reasons=[])
        with patch(
            "app.services.document_analysis.shadow_runner.analyze_image_tampering",
            return_value=_copy_move_result(),
        ):
            self._run(db_setup, tmp_path, triage=_triage_result(confidence=0.3))
        with patch(
            "app.services.document_analysis.shadow_runner.analyze_image_tampering",
            return_value=ImageTamperResult(
                analyzed=True, reasons=[], evidence={"pages": [], "duration_ms": 3}
            ),
        ):
            self._run(db_setup, tmp_path, triage=_triage_result(confidence=0.3))

        insp = self._inspection()
        assert [r for r in insp.risk_reasons if r["code"] == COPY_MOVE_CODE] == []
        assert insp.authenticity_risk == "clean"

    def test_llm_and_image_reasons_coexist(self, tmp_path, db_setup):
        self._set_inspection(scanned=True, risk="clean", reasons=[])
        triage = _triage_result(
            confidence=0.9,
            authenticity={
                "concerns": [
                    {"concern": "Tipografía inconsistente", "severity": "medium"}
                ],
                "looks_fabricated": False,
                "confidence": 0.4,
            },
        )
        with patch(
            "app.services.document_analysis.shadow_runner.analyze_image_tampering",
            return_value=_copy_move_result(),
        ):
            self._run(db_setup, tmp_path, triage=triage)

        insp = self._inspection()
        codes = sorted(r["code"] for r in insp.risk_reasons)
        assert codes == sorted([COPY_MOVE_CODE, "llm_authenticity_concern"])
        assert insp.authenticity_risk == "suspicious"

    def test_image_forensics_failure_fails_open(self, tmp_path, db_setup):
        self._set_inspection(scanned=True, risk="clean", reasons=[])
        with patch(
            "app.services.document_analysis.shadow_runner.analyze_image_tampering",
            side_effect=RuntimeError("kaboom"),
        ):
            # Must not raise.
            self._run(db_setup, tmp_path, triage=_triage_result(confidence=0.3))

        insp = self._inspection()
        # Verdict untouched — an analysis error NEVER marks a document.
        assert insp.authenticity_risk == "clean"
        assert insp.risk_reasons == []
        meta = insp.shadow_signals["_tiers"]["image_forensics"]
        assert meta["ran"] is False
        assert meta["skipped"] == "error:RuntimeError"

    def test_analysis_failed_open_result_is_recorded_as_skip(
        self, tmp_path, db_setup
    ):
        self._set_inspection(scanned=True, risk="clean", reasons=[])
        failed = ImageTamperResult(
            analyzed=False,
            reasons=[],
            evidence={"error": "broken container", "duration_ms": 5},
            error="broken container",
        )
        with patch(
            "app.services.document_analysis.shadow_runner.analyze_image_tampering",
            return_value=failed,
        ):
            self._run(db_setup, tmp_path, triage=_triage_result(confidence=0.3))

        insp = self._inspection()
        assert insp.authenticity_risk == "clean"
        assert insp.risk_reasons == []
        assert insp.shadow_signals["_tiers"]["image_forensics"] == {
            "ran": False,
            "skipped": "broken container",
            "duration_ms": 5,
        }
