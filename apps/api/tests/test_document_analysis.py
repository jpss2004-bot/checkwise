"""Phase 2 — document_analysis package tests.

Covers the provider boundary, the heuristic adapter, the prompt
registry, the spend limiter, the shadow runner, and the Anthropic
provider with a mocked SDK. The intake-level wiring test (that the
workspace upload route actually queues a BackgroundTask) lives in
``test_submissions.py`` so it shares the existing ``api_client`` setup.

No test in this file makes a real network call. The Anthropic SDK is
either mocked or omitted; the provider is constructed with an inline
API key so ``conftest.py``'s ``ANTHROPIC_API_KEY=""`` enforcement does
not affect construction. The factory tests rely on the conftest's
forced-empty key as a precondition.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pypdf import PdfWriter

from app.core.config import settings
from app.services.document_analysis import (
    AnalysisResult,
    build_document_analysis_provider,
)
from app.services.document_analysis.anthropic_provider import (
    _RECORD_TOOL,
    AnthropicDocumentAnalysisProvider,
)
from app.services.document_analysis.base import ProviderUnavailableError
from app.services.document_analysis.heuristic import (
    HeuristicDocumentAnalysisProvider,
)
from app.services.document_analysis.prompt_registry import (
    all_supported_slugs,
    get_prompt_for_requirement,
)
from app.services.document_analysis.spend_limiter import (
    check_org_daily_quota,
    reset_daily_quota,
)
from app.services.document_intelligence import DocumentSignals

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _blank_pdf_path(tmp_path: Path, name: str = "doc.pdf") -> Path:
    out = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(out)
    path = tmp_path / name
    path.write_bytes(out.getvalue())
    return path


@pytest.fixture(autouse=True)
def _reset_spend_buckets() -> None:
    reset_daily_quota()


# ---------------------------------------------------------------------------
# Prompt registry
# ---------------------------------------------------------------------------


class TestPromptRegistry:
    def test_all_four_initial_slugs_load_successfully(self):
        slugs = all_supported_slugs()
        assert set(slugs) == {"csf_sat", "opinion_32d_sat", "repse_stps", "imss_pago"}

    def test_csf_requirement_resolves_to_csf_prompt(self):
        bundle = get_prompt_for_requirement(
            requirement_code="REC-SAT-CSF-2026",
            requirement_name="Constancia de Situación Fiscal",
        )
        assert bundle.version == "csf_sat.v1"
        assert "Constancia de Situación Fiscal" in bundle.system_prompt

    def test_opinion_32d_requirement_resolves_to_opinion_prompt(self):
        bundle = get_prompt_for_requirement(
            requirement_code="REC-SAT-OPINION-32D-2026",
            requirement_name="Opinión de Cumplimiento de Obligaciones Fiscales",
        )
        assert bundle.version == "opinion_32d.v1"
        assert "Opinión" in bundle.system_prompt

    def test_repse_requirement_resolves_to_repse_prompt(self):
        bundle = get_prompt_for_requirement(
            requirement_code="REC-STPS-REPSE-2026",
            requirement_name="Constancia REPSE",
        )
        assert bundle.version == "repse_stps.v1"

    def test_imss_pago_requirement_resolves_to_imss_prompt(self):
        bundle = get_prompt_for_requirement(
            requirement_code="REC-IMSS-PAGO-2026-M04",
            requirement_name="IMSS — Comprobante de pago bancario",
        )
        assert bundle.version == "imss_pago.v1"

    def test_unknown_requirement_falls_back_to_base(self):
        bundle = get_prompt_for_requirement(
            requirement_code="REC-CFDI-NOMINA-2026-M04",
            requirement_name="Recibo CFDI de Nómina",
        )
        assert bundle.version == "base.v1"

    def test_empty_requirement_code_falls_back_to_base(self):
        bundle = get_prompt_for_requirement(
            requirement_code=None,
            requirement_name="documento generico",
        )
        assert bundle.version == "base.v1"

    def test_record_tool_schema_required_fields_match_signals(self):
        # Smoke test on the tool schema — every required field in
        # the Pydantic-like spec must be present, and the union of
        # enums must include the heuristic-friendly values so the
        # diff UI does not show spurious "unknown" rows.
        required = set(_RECORD_TOOL["input_schema"]["required"])
        expected = {
            "detected_institution",
            "detected_document_type",
            "detected_rfcs",
            "detected_dates",
            "period_mentions",
            "requirement_match_confidence",
            "mismatch_reason",
            "anomaly_codes",
            "summary_for_reviewer",
        }
        assert required == expected


# ---------------------------------------------------------------------------
# Heuristic adapter
# ---------------------------------------------------------------------------


class TestHeuristicProvider:
    def test_provider_id_is_stable(self):
        provider = HeuristicDocumentAnalysisProvider()
        assert provider.provider_id == "heuristic:v1"

    def test_returns_signals_on_success(self, tmp_path):
        provider = HeuristicDocumentAnalysisProvider()
        path = _blank_pdf_path(tmp_path)
        result = provider.analyze(
            pdf_path=path,
            requirement_code="REC-SAT-CSF-2026",
            requirement_name="Constancia de Situación Fiscal",
            institution_code="sat",
            period_code="2026-01",
        )
        # Blank PDF has no text — heuristic returns a DocumentSignals
        # with anomaly_codes set; the key invariant for the adapter
        # is that signals is populated (not None) and error is None.
        assert result.error is None
        assert result.signals is not None
        assert result.prompt_version is None
        assert result.latency_ms >= 0

    def test_returns_error_when_path_missing(self, tmp_path):
        provider = HeuristicDocumentAnalysisProvider()
        result = provider.analyze(
            pdf_path=tmp_path / "missing.pdf",
            requirement_code="REC-SAT-CSF-2026",
            requirement_name="CSF",
            institution_code="sat",
            period_code="2026-01",
        )
        assert result.signals is None
        assert result.error is not None
        assert result.error.startswith("heuristic_error:")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestFactory:
    def test_disabled_returns_none(self, monkeypatch):
        monkeypatch.setattr(settings, "DOCUMENT_ANALYSIS_PROVIDER", "disabled")
        assert build_document_analysis_provider() is None

    def test_empty_string_returns_none(self, monkeypatch):
        monkeypatch.setattr(settings, "DOCUMENT_ANALYSIS_PROVIDER", "")
        assert build_document_analysis_provider() is None

    def test_unknown_value_returns_none(self, monkeypatch):
        monkeypatch.setattr(settings, "DOCUMENT_ANALYSIS_PROVIDER", "magic-ml")
        assert build_document_analysis_provider() is None

    def test_heuristic_returns_heuristic_provider(self, monkeypatch):
        monkeypatch.setattr(settings, "DOCUMENT_ANALYSIS_PROVIDER", "heuristic")
        provider = build_document_analysis_provider()
        assert isinstance(provider, HeuristicDocumentAnalysisProvider)

    def test_anthropic_without_key_falls_back_to_heuristic(self, monkeypatch):
        # ``conftest.py`` already clears ANTHROPIC_API_KEY for the
        # session; we re-assert it to keep this test self-documenting.
        monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
        monkeypatch.setattr(settings, "DOCUMENT_ANALYSIS_PROVIDER", "anthropic")
        provider = build_document_analysis_provider()
        assert isinstance(provider, HeuristicDocumentAnalysisProvider)

    def test_anthropic_with_key_returns_anthropic_provider(self, monkeypatch):
        monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setattr(settings, "DOCUMENT_ANALYSIS_PROVIDER", "anthropic")
        provider = build_document_analysis_provider()
        assert isinstance(provider, AnthropicDocumentAnalysisProvider)
        assert provider.provider_id.startswith("anthropic:")


# ---------------------------------------------------------------------------
# Anthropic provider — preflight + mocked SDK
# ---------------------------------------------------------------------------


def _build_provider_with_mock_client(monkeypatch, client_mock: MagicMock) -> AnthropicDocumentAnalysisProvider:
    """Construct an AnthropicDocumentAnalysisProvider whose SDK client is mocked."""
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-test")
    provider = AnthropicDocumentAnalysisProvider(api_key="sk-test")
    provider._client = client_mock  # noqa: SLF001 — test injection seam
    return provider


def _mock_anthropic_response(
    *,
    tool_input: dict | None = None,
    include_tool_use: bool = True,
    stop_reason: str = "end_turn",
) -> Any:
    blocks: list[Any] = []
    if include_tool_use:
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = _RECORD_TOOL["name"]
        tool_block.input = tool_input or {
            "detected_institution": "sat",
            "detected_document_type": "csf",
            "detected_rfcs": ["ABCD010203XYZ"],
            "detected_dates": ["2026-04-01"],
            "period_mentions": [],
            "requirement_match_confidence": 0.92,
            "mismatch_reason": None,
            "anomaly_codes": [],
            "summary_for_reviewer": "CSF vigente del proveedor esperado.",
        }
        blocks.append(tool_block)

    response = MagicMock()
    response.content = blocks
    response.stop_reason = stop_reason
    response.model = "claude-sonnet-4-6"
    usage = MagicMock()
    usage.model_dump.return_value = {"input_tokens": 100, "output_tokens": 50}
    response.usage = usage
    return response


class TestAnthropicProviderConstruction:
    def test_construction_requires_api_key(self, monkeypatch):
        monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
        with pytest.raises(ProviderUnavailableError):
            AnthropicDocumentAnalysisProvider()

    def test_provider_id_includes_configured_model(self, monkeypatch):
        monkeypatch.setattr(settings, "DOCUMENT_ANALYSIS_MODEL", "claude-opus-4-8")
        provider = AnthropicDocumentAnalysisProvider(api_key="sk-test")
        assert provider.provider_id == "anthropic:claude-opus-4-8"


class TestAnthropicProviderPreflight:
    def test_missing_file_returns_unsupported(self, monkeypatch, tmp_path):
        provider = AnthropicDocumentAnalysisProvider(api_key="sk-test")
        result = provider.analyze(
            pdf_path=tmp_path / "missing.pdf",
            requirement_code="REC-SAT-CSF-2026",
            requirement_name="CSF",
            institution_code="sat",
            period_code="2026-01",
        )
        assert result.signals is None
        assert result.error == "unsupported_size_or_type"

    def test_oversized_file_returns_unsupported(self, monkeypatch, tmp_path):
        monkeypatch.setattr(settings, "DOCUMENT_ANALYSIS_MAX_FILE_MB", 1)
        path = tmp_path / "big.pdf"
        path.write_bytes(b"%PDF-1.4\n" + b"x" * (2 * 1024 * 1024))
        provider = AnthropicDocumentAnalysisProvider(api_key="sk-test")
        result = provider.analyze(
            pdf_path=path,
            requirement_code="REC-SAT-CSF-2026",
            requirement_name="CSF",
            institution_code="sat",
            period_code="2026-01",
        )
        assert result.error == "unsupported_size_or_type"


class TestAnthropicProviderResponseHandling:
    def test_happy_path_returns_parsed_signals(self, monkeypatch, tmp_path):
        client = MagicMock()
        client.with_options.return_value.messages.create.return_value = (
            _mock_anthropic_response()
        )
        provider = _build_provider_with_mock_client(monkeypatch, client)
        result = provider.analyze(
            pdf_path=_blank_pdf_path(tmp_path),
            requirement_code="REC-SAT-CSF-2026",
            requirement_name="Constancia de Situación Fiscal",
            institution_code="sat",
            period_code="2026-01",
        )
        assert result.error is None
        assert isinstance(result.signals, DocumentSignals)
        assert result.signals.detected_institution == "sat"
        assert result.signals.detected_document_type == "csf"
        assert result.signals.requirement_match_confidence == pytest.approx(0.92)
        assert result.signals.detected_rfcs == ["ABCD010203XYZ"]
        assert result.prompt_version == "csf_sat.v1"
        assert result.raw_meta is not None
        assert result.raw_meta.get("summary_for_reviewer")

    def test_no_tool_use_returns_malformed(self, monkeypatch, tmp_path):
        client = MagicMock()
        client.with_options.return_value.messages.create.return_value = (
            _mock_anthropic_response(include_tool_use=False)
        )
        provider = _build_provider_with_mock_client(monkeypatch, client)
        result = provider.analyze(
            pdf_path=_blank_pdf_path(tmp_path),
            requirement_code="REC-SAT-CSF-2026",
            requirement_name="CSF",
            institution_code="sat",
            period_code="2026-01",
        )
        assert result.error == "malformed_response"
        assert result.signals is None

    def test_timeout_returns_timeout_error(self, monkeypatch, tmp_path):
        class _APITimeoutError(Exception):
            pass

        client = MagicMock()
        client.with_options.return_value.messages.create.side_effect = _APITimeoutError(
            "timed out"
        )
        provider = _build_provider_with_mock_client(monkeypatch, client)
        result = provider.analyze(
            pdf_path=_blank_pdf_path(tmp_path),
            requirement_code="REC-SAT-CSF-2026",
            requirement_name="CSF",
            institution_code="sat",
            period_code="2026-01",
        )
        assert result.error == "timeout"
        assert result.signals is None

    def test_generic_exception_returns_provider_error(self, monkeypatch, tmp_path):
        client = MagicMock()
        client.with_options.return_value.messages.create.side_effect = RuntimeError(
            "kaboom"
        )
        provider = _build_provider_with_mock_client(monkeypatch, client)
        result = provider.analyze(
            pdf_path=_blank_pdf_path(tmp_path),
            requirement_code="REC-SAT-CSF-2026",
            requirement_name="CSF",
            institution_code="sat",
            period_code="2026-01",
        )
        assert result.error == "provider_error:RuntimeError"
        assert result.signals is None


# ---------------------------------------------------------------------------
# Spend limiter
# ---------------------------------------------------------------------------


class TestSpendLimiter:
    def test_cap_zero_always_allows(self, monkeypatch):
        monkeypatch.setattr(settings, "DOCUMENT_ANALYSIS_DAILY_CAP_PER_ORG", 0)
        for _ in range(10):
            assert check_org_daily_quota("org-1") is True

    def test_cap_one_blocks_second_call_for_same_org(self, monkeypatch):
        monkeypatch.setattr(settings, "DOCUMENT_ANALYSIS_DAILY_CAP_PER_ORG", 1)
        assert check_org_daily_quota("org-1") is True
        assert check_org_daily_quota("org-1") is False

    def test_different_orgs_have_independent_buckets(self, monkeypatch):
        monkeypatch.setattr(settings, "DOCUMENT_ANALYSIS_DAILY_CAP_PER_ORG", 1)
        assert check_org_daily_quota("org-a") is True
        assert check_org_daily_quota("org-b") is True

    def test_org_none_lands_in_shared_bucket(self, monkeypatch):
        monkeypatch.setattr(settings, "DOCUMENT_ANALYSIS_DAILY_CAP_PER_ORG", 1)
        assert check_org_daily_quota(None) is True
        assert check_org_daily_quota(None) is False


# ---------------------------------------------------------------------------
# Shadow runner — end-to-end persistence with a mocked provider
# ---------------------------------------------------------------------------


class TestShadowRunner:
    @pytest.fixture
    def db_setup(self, tmp_path):
        """Build an in-memory SQLite DB and a Submission/Document/Inspection row.

        The shadow runner opens its own session via SessionLocal, so
        the fixture overrides ``SessionLocal`` to bind to the test
        engine. Returns the document_id + submission_id the runner is
        expected to update.
        """
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        from app.db import session as session_module
        from app.db.base import Base
        from app.models import Document, DocumentInspection, Submission

        engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        Base.metadata.create_all(bind=engine)

        original_session_local = session_module.SessionLocal
        session_module.SessionLocal = TestingSession

        # Patch the import path the runner uses at module load.
        from app.services.document_analysis import shadow_runner as runner_module

        original_runner_session = runner_module.SessionLocal
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
                is_probably_scanned=False,
            )
            db.add(inspection)
            db.commit()
            ids = {"document_id": doc.id, "submission_id": sub.id}
        finally:
            db.close()

        yield ids

        session_module.SessionLocal = original_session_local
        runner_module.SessionLocal = original_runner_session

    def test_disabled_provider_is_noop(self, monkeypatch, tmp_path, db_setup):
        monkeypatch.setattr(settings, "DOCUMENT_ANALYSIS_PROVIDER", "disabled")
        from app.services.document_analysis.shadow_runner import run_shadow_analysis

        # Should return cleanly without writing anything.
        run_shadow_analysis(
            document_id=db_setup["document_id"],
            submission_id=db_setup["submission_id"],
            pdf_path=str(_blank_pdf_path(tmp_path)),
            requirement_code="REC-SAT-CSF-2026",
            requirement_name="CSF",
            institution_code="sat",
            period_code="2026-01",
            org_id="cli-1",
        )

        from app.db.session import SessionLocal
        from app.models import DocumentInspection

        db = SessionLocal()
        try:
            insp = db.query(DocumentInspection).first()
            assert insp.shadow_provider_id is None
            assert insp.shadow_completed_at is None
        finally:
            db.close()

    def test_successful_provider_persists_shadow_columns(
        self, monkeypatch, tmp_path, db_setup
    ):
        signals = DocumentSignals(
            detected_institution="sat",
            detected_document_type="csf",
            detected_rfcs=["AAAA010101AAA"],
            detected_dates=["2026-04-01"],
            period_mentions=[],
            requirement_match_confidence=0.91,
            mismatch_reason=None,
            anomaly_codes=[],
        )
        fake_result = AnalysisResult(
            provider_id="anthropic:claude-sonnet-4-6",
            prompt_version="csf_sat.v1",
            latency_ms=2500,
            signals=signals,
            error=None,
            raw_meta={"stop_reason": "end_turn"},
        )

        fake_provider = MagicMock()
        fake_provider.provider_id = "anthropic:claude-sonnet-4-6"
        fake_provider.analyze.return_value = fake_result

        with patch(
            "app.services.document_analysis.shadow_runner.build_document_analysis_provider",
            return_value=fake_provider,
        ):
            from app.services.document_analysis.shadow_runner import (
                run_shadow_analysis,
            )

            run_shadow_analysis(
                document_id=db_setup["document_id"],
                submission_id=db_setup["submission_id"],
                pdf_path=str(_blank_pdf_path(tmp_path)),
                requirement_code="REC-SAT-CSF-2026",
                requirement_name="CSF",
                institution_code="sat",
                period_code="2026-01",
                org_id="cli-1",
            )

        from app.db.session import SessionLocal
        from app.models import DocumentInspection, ValidationEvent

        db = SessionLocal()
        try:
            insp = db.query(DocumentInspection).first()
            assert insp.shadow_provider_id == "anthropic:claude-sonnet-4-6"
            assert insp.shadow_prompt_version == "csf_sat.v1"
            assert insp.shadow_confidence == pytest.approx(0.91)
            assert insp.shadow_latency_ms == 2500
            assert insp.shadow_error is None
            assert insp.shadow_completed_at is not None
            assert insp.shadow_signals["detected_institution"] == "sat"
            assert insp.shadow_signals["_meta"]["stop_reason"] == "end_turn"

            events = db.query(ValidationEvent).all()
            shadow_events = [e for e in events if e.event_type == "shadow_analysis_completed"]
            assert len(shadow_events) == 1
            assert shadow_events[0].result == "pass"
            assert shadow_events[0].payload["provider_id"] == "anthropic:claude-sonnet-4-6"
        finally:
            db.close()

    def test_provider_error_persists_shadow_error(self, monkeypatch, tmp_path, db_setup):
        fake_provider = MagicMock()
        fake_provider.provider_id = "anthropic:claude-sonnet-4-6"
        fake_provider.analyze.return_value = AnalysisResult(
            provider_id="anthropic:claude-sonnet-4-6",
            prompt_version="csf_sat.v1",
            latency_ms=120,
            signals=None,
            error="timeout",
        )

        with patch(
            "app.services.document_analysis.shadow_runner.build_document_analysis_provider",
            return_value=fake_provider,
        ):
            from app.services.document_analysis.shadow_runner import (
                run_shadow_analysis,
            )

            run_shadow_analysis(
                document_id=db_setup["document_id"],
                submission_id=db_setup["submission_id"],
                pdf_path=str(_blank_pdf_path(tmp_path)),
                requirement_code="REC-SAT-CSF-2026",
                requirement_name="CSF",
                institution_code="sat",
                period_code="2026-01",
                org_id="cli-1",
            )

        from app.db.session import SessionLocal
        from app.models import DocumentInspection, ValidationEvent

        db = SessionLocal()
        try:
            insp = db.query(DocumentInspection).first()
            assert insp.shadow_error == "timeout"
            assert insp.shadow_signals is None
            assert insp.shadow_completed_at is not None
            events = db.query(ValidationEvent).filter_by(
                event_type="shadow_analysis_completed"
            ).all()
            assert events[0].result == "warning"
        finally:
            db.close()

    def test_org_outside_pilot_allowlist_is_silent_noop(
        self, monkeypatch, tmp_path, db_setup
    ):
        monkeypatch.setattr(
            settings, "DOCUMENT_ANALYSIS_PILOT_ORG_IDS", "allowed-org-1, allowed-org-2"
        )
        fake_provider = MagicMock()
        fake_provider.provider_id = "anthropic:claude-sonnet-4-6"

        with patch(
            "app.services.document_analysis.shadow_runner.build_document_analysis_provider",
            return_value=fake_provider,
        ):
            from app.services.document_analysis.shadow_runner import (
                run_shadow_analysis,
            )

            run_shadow_analysis(
                document_id=db_setup["document_id"],
                submission_id=db_setup["submission_id"],
                pdf_path=str(_blank_pdf_path(tmp_path)),
                requirement_code="REC-SAT-CSF-2026",
                requirement_name="CSF",
                institution_code="sat",
                period_code="2026-01",
                org_id="some-other-org",
            )

        # No provider call, no shadow row written.
        fake_provider.analyze.assert_not_called()
        from app.db.session import SessionLocal
        from app.models import DocumentInspection

        db = SessionLocal()
        try:
            insp = db.query(DocumentInspection).first()
            assert insp.shadow_provider_id is None
            assert insp.shadow_completed_at is None
            assert insp.shadow_error is None
        finally:
            db.close()

    def test_org_inside_pilot_allowlist_runs_normally(
        self, monkeypatch, tmp_path, db_setup
    ):
        monkeypatch.setattr(
            settings, "DOCUMENT_ANALYSIS_PILOT_ORG_IDS", " cli-1 , other-org "
        )
        fake_provider = MagicMock()
        fake_provider.provider_id = "anthropic:claude-sonnet-4-6"
        fake_provider.analyze.return_value = AnalysisResult(
            provider_id="anthropic:claude-sonnet-4-6",
            prompt_version="csf_sat.v1",
            latency_ms=1234,
            signals=DocumentSignals(
                detected_institution="sat",
                detected_document_type="csf",
                requirement_match_confidence=0.9,
            ),
            error=None,
        )

        with patch(
            "app.services.document_analysis.shadow_runner.build_document_analysis_provider",
            return_value=fake_provider,
        ):
            from app.services.document_analysis.shadow_runner import (
                run_shadow_analysis,
            )

            run_shadow_analysis(
                document_id=db_setup["document_id"],
                submission_id=db_setup["submission_id"],
                pdf_path=str(_blank_pdf_path(tmp_path)),
                requirement_code="REC-SAT-CSF-2026",
                requirement_name="CSF",
                institution_code="sat",
                period_code="2026-01",
                org_id="cli-1",
            )

        fake_provider.analyze.assert_called_once()
        from app.db.session import SessionLocal
        from app.models import DocumentInspection

        db = SessionLocal()
        try:
            insp = db.query(DocumentInspection).first()
            assert insp.shadow_provider_id == "anthropic:claude-sonnet-4-6"
            assert insp.shadow_completed_at is not None
        finally:
            db.close()

    def test_empty_pilot_allowlist_means_unrestricted(
        self, monkeypatch, tmp_path, db_setup
    ):
        monkeypatch.setattr(settings, "DOCUMENT_ANALYSIS_PILOT_ORG_IDS", "")
        fake_provider = MagicMock()
        fake_provider.provider_id = "anthropic:claude-sonnet-4-6"
        fake_provider.analyze.return_value = AnalysisResult(
            provider_id="anthropic:claude-sonnet-4-6",
            prompt_version="csf_sat.v1",
            latency_ms=10,
            signals=DocumentSignals(),
            error=None,
        )

        with patch(
            "app.services.document_analysis.shadow_runner.build_document_analysis_provider",
            return_value=fake_provider,
        ):
            from app.services.document_analysis.shadow_runner import (
                run_shadow_analysis,
            )

            run_shadow_analysis(
                document_id=db_setup["document_id"],
                submission_id=db_setup["submission_id"],
                pdf_path=str(_blank_pdf_path(tmp_path)),
                requirement_code="REC-SAT-CSF-2026",
                requirement_name="CSF",
                institution_code="sat",
                period_code="2026-01",
                org_id="any-org-id",
            )

        fake_provider.analyze.assert_called_once()

    def test_daily_cap_skips_provider_call_and_persists_marker(
        self, monkeypatch, tmp_path, db_setup
    ):
        monkeypatch.setattr(settings, "DOCUMENT_ANALYSIS_DAILY_CAP_PER_ORG", 1)
        # Pre-consume the bucket.
        assert check_org_daily_quota("cli-1") is True

        fake_provider = MagicMock()
        fake_provider.provider_id = "anthropic:claude-sonnet-4-6"

        with patch(
            "app.services.document_analysis.shadow_runner.build_document_analysis_provider",
            return_value=fake_provider,
        ):
            from app.services.document_analysis.shadow_runner import (
                run_shadow_analysis,
            )

            run_shadow_analysis(
                document_id=db_setup["document_id"],
                submission_id=db_setup["submission_id"],
                pdf_path=str(_blank_pdf_path(tmp_path)),
                requirement_code="REC-SAT-CSF-2026",
                requirement_name="CSF",
                institution_code="sat",
                period_code="2026-01",
                org_id="cli-1",
            )

        # Provider was NEVER asked to analyze.
        fake_provider.analyze.assert_not_called()

        from app.db.session import SessionLocal
        from app.models import DocumentInspection

        db = SessionLocal()
        try:
            insp = db.query(DocumentInspection).first()
            assert insp.shadow_error == "daily_cap_exceeded"
            assert insp.shadow_signals is None
            assert insp.shadow_completed_at is not None
        finally:
            db.close()
