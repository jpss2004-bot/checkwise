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

import json
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
    _COMPREHENSION_OUTPUT_FORMAT,
    _RECORD_TOOL,
    AnthropicDocumentAnalysisProvider,
)
from app.services.document_analysis.base import ProviderUnavailableError
from app.services.document_analysis.heuristic import (
    HeuristicDocumentAnalysisProvider,
)
from app.services.document_analysis.prompt_registry import (
    all_supported_slugs,
    get_comprehension_prompt_for_requirement,
    get_escalation_prompt,
    get_prompt_for_requirement,
)
from app.services.document_analysis.spend_limiter import (
    check_org_daily_quota,
    check_org_escalation_daily_quota,
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
        assert bundle.version == "csf_sat.v2"
        assert "Constancia de Situación Fiscal" in bundle.system_prompt

    def test_opinion_32d_requirement_resolves_to_opinion_prompt(self):
        bundle = get_prompt_for_requirement(
            requirement_code="REC-SAT-OPINION-32D-2026",
            requirement_name="Opinión de Cumplimiento de Obligaciones Fiscales",
        )
        assert bundle.version == "opinion_32d.v2"
        assert "Opinión" in bundle.system_prompt

    def test_repse_requirement_resolves_to_repse_prompt(self):
        bundle = get_prompt_for_requirement(
            requirement_code="REC-STPS-REPSE-2026",
            requirement_name="Constancia REPSE",
        )
        assert bundle.version == "repse_stps.v2"

    def test_imss_pago_requirement_resolves_to_imss_prompt(self):
        bundle = get_prompt_for_requirement(
            requirement_code="REC-IMSS-PAGO-2026-M04",
            requirement_name="IMSS — Comprobante de pago bancario",
        )
        assert bundle.version == "imss_pago.v2"

    def test_unknown_requirement_falls_back_to_base(self):
        bundle = get_prompt_for_requirement(
            requirement_code="REC-CFDI-NOMINA-2026-M04",
            requirement_name="Recibo CFDI de Nómina",
        )
        assert bundle.version == "base.v2"

    def test_empty_requirement_code_falls_back_to_base(self):
        bundle = get_prompt_for_requirement(
            requirement_code=None,
            requirement_name="documento generico",
        )
        assert bundle.version == "base.v2"

    def test_escalation_prompt_loads_and_is_authenticity_focused(self):
        bundle = get_escalation_prompt()
        assert bundle.version == "authenticity_deep.v1"
        assert "autenticidad" in bundle.system_prompt.lower()
        # The escalation prompt is internal — never listed as a
        # requirement slug.
        assert "authenticity_deep" not in all_supported_slugs()

    def test_deep_tier_resolves_requirement_specific_v3_prompts(self):
        cases = [
            ("REC-SAT-CSF-2026", "Constancia de Situación Fiscal", "csf_sat.v3"),
            (
                "REC-SAT-OPINION-32D-2026",
                "Opinión de Cumplimiento de Obligaciones Fiscales",
                "opinion_32d.v3",
            ),
            ("REC-STPS-REPSE-2026", "Constancia REPSE", "repse_stps.v3"),
            ("REC-IMSS-PAGO-2026-M04", "IMSS — Comprobante de pago", "imss_pago.v3"),
            ("REC-CFDI-NOMINA-2026", "Recibo CFDI de Nómina", "base.v3"),
        ]
        for code, name, expected_version in cases:
            bundle = get_comprehension_prompt_for_requirement(
                requirement_code=code, requirement_name=name
            )
            assert bundle.version == expected_version
            # v3 prompts must carry the comprehension contract.
            assert "document_understanding" in bundle.system_prompt

    def test_comprehension_format_schema_shape(self):
        schema = _COMPREHENSION_OUTPUT_FORMAT["schema"]
        # Extraction fields + the comprehension object are all required.
        assert "document_understanding" in schema["required"]
        for field in (
            "detected_institution",
            "requirement_match_confidence",
            "authenticity_concerns",
        ):
            assert field in schema["required"]
        du = schema["properties"]["document_understanding"]
        assert set(du["required"]) == {
            "purpose",
            "key_facts",
            "status_assessment",
            "obligation_satisfaction",
            "discrepancies",
        }
        assert du["properties"]["obligation_satisfaction"]["properties"]["verdict"][
            "enum"
        ] == ["satisfied", "partial", "not_satisfied", "indeterminate"]
        # Structured outputs reject numeric range constraints — the base
        # confidence field must have been stripped by the deep schema.
        assert "minimum" not in schema["properties"]["requirement_match_confidence"]

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
            # Phase C — authenticity judgment (additive).
            "authenticity_concerns",
            "looks_fabricated",
            "authenticity_confidence",
        }
        assert required == expected

    def test_authenticity_concern_severity_enum_is_low_medium_only(self):
        # The agreed policy caps LLM severities at medium — the schema
        # must not allow the model to emit "high".
        concern_schema = _RECORD_TOOL["input_schema"]["properties"][
            "authenticity_concerns"
        ]["items"]["properties"]["severity"]
        assert concern_schema["enum"] == ["low", "medium"]


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

    def test_triage_tier_uses_triage_model(self, monkeypatch):
        monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setattr(settings, "DOCUMENT_ANALYSIS_PROVIDER", "anthropic")
        provider = build_document_analysis_provider(tier="triage")
        assert isinstance(provider, AnthropicDocumentAnalysisProvider)
        # Default DOCUMENT_ANALYSIS_TRIAGE_MODEL is claude-haiku-4-5.
        assert provider.provider_id == "anthropic:claude-haiku-4-5"
        assert provider._deep_authenticity is False  # noqa: SLF001

    def test_escalation_tier_uses_escalation_model_and_deep_prompt(
        self, monkeypatch
    ):
        monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setattr(settings, "DOCUMENT_ANALYSIS_PROVIDER", "anthropic")
        provider = build_document_analysis_provider(tier="escalation")
        assert isinstance(provider, AnthropicDocumentAnalysisProvider)
        # Escalation keeps the historical DOCUMENT_ANALYSIS_MODEL
        # setting (default claude-sonnet-4-6) for Render env compat.
        assert provider.provider_id == "anthropic:claude-sonnet-4-6"
        assert provider._deep_authenticity is True  # noqa: SLF001

    def test_escalation_tier_without_key_returns_none_not_heuristic(
        self, monkeypatch
    ):
        monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
        monkeypatch.setattr(settings, "DOCUMENT_ANALYSIS_PROVIDER", "anthropic")
        assert build_document_analysis_provider(tier="escalation") is None

    def test_heuristic_provider_has_no_escalation_tier(self, monkeypatch):
        monkeypatch.setattr(settings, "DOCUMENT_ANALYSIS_PROVIDER", "heuristic")
        assert build_document_analysis_provider(tier="escalation") is None


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


def _mock_structured_response(
    payload: dict | None = None,
    *,
    include_thinking: bool = True,
) -> Any:
    """Deep-tier response: schema-valid JSON in a text block (optionally
    preceded by a thinking block, which the parser must skip)."""
    blocks: list[Any] = []
    if include_thinking:
        thinking_block = MagicMock()
        thinking_block.type = "thinking"
        thinking_block.thinking = "Razonando sobre el documento..."
        blocks.append(thinking_block)
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = json.dumps(
        payload
        or {
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
    )
    blocks.append(text_block)

    response = MagicMock()
    response.content = blocks
    response.stop_reason = "end_turn"
    response.model = "claude-sonnet-4-6"
    usage = MagicMock()
    usage.model_dump.return_value = {"input_tokens": 200, "output_tokens": 120}
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
        assert result.prompt_version == "csf_sat.v2"
        assert result.raw_meta is not None
        assert result.raw_meta.get("summary_for_reviewer")
        # No authenticity fields in the payload → no judgment recorded.
        assert result.authenticity is None

    def test_authenticity_fields_are_parsed(self, monkeypatch, tmp_path):
        client = MagicMock()
        client.with_options.return_value.messages.create.return_value = (
            _mock_anthropic_response(
                tool_input={
                    "detected_institution": "sat",
                    "detected_document_type": "csf",
                    "detected_rfcs": [],
                    "detected_dates": [],
                    "period_mentions": [],
                    "requirement_match_confidence": 0.8,
                    "mismatch_reason": None,
                    "anomaly_codes": [],
                    "summary_for_reviewer": "ok",
                    "authenticity_concerns": [
                        {"concern": "Tipografía inconsistente", "severity": "medium"},
                        {"concern": "Folio ausente", "severity": "low"},
                        {"concern": "", "severity": "low"},  # dropped — empty
                    ],
                    "looks_fabricated": False,
                    "authenticity_confidence": 0.4,
                }
            )
        )
        provider = _build_provider_with_mock_client(monkeypatch, client)
        result = provider.analyze(
            pdf_path=_blank_pdf_path(tmp_path),
            requirement_code="REC-SAT-CSF-2026",
            requirement_name="CSF",
            institution_code="sat",
            period_code="2026-01",
        )
        assert result.error is None
        assert result.authenticity == {
            "concerns": [
                {"concern": "Tipografía inconsistente", "severity": "medium"},
                {"concern": "Folio ausente", "severity": "low"},
            ],
            "looks_fabricated": False,
            "confidence": 0.4,
        }

    def test_escalation_tier_uses_deep_prompt_and_structured_reasoning(
        self, monkeypatch, tmp_path
    ):
        client = MagicMock()
        client.with_options.return_value.messages.create.return_value = (
            _mock_structured_response()
        )
        monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-test")
        provider = AnthropicDocumentAnalysisProvider(
            api_key="sk-test",
            model="claude-sonnet-4-6",
            deep_authenticity=True,
        )
        provider._client = client  # noqa: SLF001 — test injection seam
        result = provider.analyze(
            pdf_path=_blank_pdf_path(tmp_path),
            requirement_code="REC-SAT-CSF-2026",
            requirement_name="CSF",
            institution_code="sat",
            period_code="2026-01",
        )
        assert result.error is None
        assert result.signals is not None
        assert result.signals.detected_document_type == "csf"
        # Phase 1 — the deep tier is requirement-aware: a CSF upload uses
        # the per-type v3 comprehension prompt, not the generic
        # authenticity_deep prompt.
        assert result.prompt_version == "csf_sat.v3"

        create_kwargs = client.with_options.return_value.messages.create.call_args.kwargs
        system_text = create_kwargs["system"][0]["text"]
        # The v3 prompt carries both the comprehension contract and the
        # authenticity guidance.
        assert "document_understanding" in system_text
        assert "autenticidad" in system_text.lower()
        assert "Constancia de Situación Fiscal" in system_text
        assert create_kwargs["model"] == "claude-sonnet-4-6"
        # Reasoning + structured outputs replace the forced tool call
        # (forced tool_choice is incompatible with thinking).
        assert create_kwargs["thinking"] == {"type": "adaptive"}
        assert create_kwargs["output_config"]["effort"] == "high"
        assert create_kwargs["output_config"]["format"]["type"] == "json_schema"
        assert "tool_choice" not in create_kwargs
        assert "tools" not in create_kwargs

    def test_deep_tier_non_json_text_is_malformed(self, monkeypatch, tmp_path):
        client = MagicMock()
        bad = _mock_structured_response()
        bad.content[-1].text = "lo siento, no pude analizar el documento"
        client.with_options.return_value.messages.create.return_value = bad
        monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-test")
        provider = AnthropicDocumentAnalysisProvider(
            api_key="sk-test", model="claude-sonnet-4-6", deep_authenticity=True
        )
        provider._client = client  # noqa: SLF001 — test injection seam
        result = provider.analyze(
            pdf_path=_blank_pdf_path(tmp_path),
            requirement_code="REC-SAT-CSF-2026",
            requirement_name="CSF",
            institution_code="sat",
            period_code="2026-01",
        )
        assert result.error == "malformed_response"
        assert result.signals is None

    def test_user_prompt_includes_provider_and_client_context(
        self, monkeypatch, tmp_path
    ):
        client = MagicMock()
        client.with_options.return_value.messages.create.return_value = (
            _mock_anthropic_response()
        )
        provider = _build_provider_with_mock_client(monkeypatch, client)
        provider.analyze(
            pdf_path=_blank_pdf_path(tmp_path),
            requirement_code="REC-SAT-CSF-2026",
            requirement_name="CSF",
            institution_code="sat",
            period_code="2026-01",
            expected_provider_rfc="ABCD010203XYZ",
            expected_provider_name="ACME Servicios SA de CV",
            expected_client_name="Cliente Demo SA",
            expected_client_rfc="XAXX010101000",
        )
        create_kwargs = client.with_options.return_value.messages.create.call_args.kwargs
        user_text = create_kwargs["messages"][0]["content"][1]["text"]
        assert "ACME Servicios SA de CV" in user_text
        assert "ABCD010203XYZ" in user_text
        # Client is named as contratante, explicitly not the document titular.
        assert "Cliente Demo SA" in user_text
        assert "contratante" in user_text.lower()

    def test_deep_tier_parses_comprehension_obligation(self, monkeypatch, tmp_path):
        # The star case: an authentic, correctly-typed Opinión 32-D whose
        # sentido is Negativo — the document is real and the right type,
        # but it does NOT satisfy the obligation. Pure extraction would
        # call this a match; comprehension catches the real situation.
        payload = {
            "detected_institution": "sat",
            "detected_document_type": "opinion_cumplimiento_sat",
            "detected_rfcs": ["ABCD010203XYZ"],
            "detected_dates": ["2026-04-01"],
            "period_mentions": [],
            "requirement_match_confidence": 0.95,
            "mismatch_reason": None,
            "anomaly_codes": [],
            "summary_for_reviewer": "Opinión negativa del proveedor esperado.",
            "authenticity_concerns": [],
            "looks_fabricated": False,
            "authenticity_confidence": 0.95,
            "document_understanding": {
                "purpose": "Opinión 32-D del cumplimiento fiscal del proveedor.",
                "key_facts": [
                    {"label": "Sentido de la opinión", "value": "Negativo"},
                    {"label": "RFC del contribuyente", "value": "ABCD010203XYZ"},
                    {"label": "", "value": "dropped"},  # malformed → dropped
                ],
                "status_assessment": {
                    "validity": "valid",
                    "currency_ok": True,
                    "reasoning": "Vigente para el periodo esperado.",
                },
                "obligation_satisfaction": {
                    "verdict": "not_satisfied",
                    "confidence": 0.9,
                    "reasoning": "Una opinión negativa indica incumplimiento.",
                },
                "discrepancies": [
                    {
                        "issue": "Sentido negativo",
                        "severity": "high",
                        "evidence": "El documento indica 'Negativo'.",
                    }
                ],
            },
        }
        client = MagicMock()
        client.with_options.return_value.messages.create.return_value = (
            _mock_structured_response(payload)
        )
        monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-test")
        provider = AnthropicDocumentAnalysisProvider(
            api_key="sk-test", model="claude-sonnet-4-6", deep_authenticity=True
        )
        provider._client = client  # noqa: SLF001 — test injection seam
        result = provider.analyze(
            pdf_path=_blank_pdf_path(tmp_path),
            requirement_code="REC-SAT-OPINION-32D-2026",
            requirement_name="Opinión de Cumplimiento de Obligaciones Fiscales",
            institution_code="sat",
            period_code="2026-04",
        )
        assert result.error is None
        comp = result.comprehension
        assert comp is not None
        assert comp["obligation_satisfaction"]["verdict"] == "not_satisfied"
        assert comp["obligation_satisfaction"]["confidence"] == pytest.approx(0.9)
        assert comp["status_assessment"]["validity"] == "valid"
        assert comp["status_assessment"]["currency_ok"] is True
        labels = [kf["label"] for kf in comp["key_facts"]]
        assert "Sentido de la opinión" in labels
        assert "" not in labels  # malformed key_fact dropped
        assert comp["discrepancies"][0]["severity"] == "high"

    def test_deep_tier_normalises_bad_comprehension_values(self, monkeypatch, tmp_path):
        payload = {
            "detected_institution": "sat",
            "detected_document_type": "csf",
            "detected_rfcs": [],
            "detected_dates": [],
            "period_mentions": [],
            "requirement_match_confidence": 0.5,
            "mismatch_reason": None,
            "anomaly_codes": [],
            "summary_for_reviewer": "x",
            "document_understanding": {
                "purpose": "x",
                "key_facts": [],
                "status_assessment": {
                    "validity": "garbage",
                    "currency_ok": "maybe",
                    "reasoning": "",
                },
                "obligation_satisfaction": {
                    "verdict": "nope",
                    "confidence": "not-a-number",
                    "reasoning": "",
                },
                "discrepancies": [
                    {"issue": "y", "severity": "catastrophic", "evidence": ""}
                ],
            },
        }
        client = MagicMock()
        client.with_options.return_value.messages.create.return_value = (
            _mock_structured_response(payload)
        )
        monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-test")
        provider = AnthropicDocumentAnalysisProvider(
            api_key="sk-test", model="claude-sonnet-4-6", deep_authenticity=True
        )
        provider._client = client  # noqa: SLF001 — test injection seam
        result = provider.analyze(
            pdf_path=_blank_pdf_path(tmp_path),
            requirement_code="REC-SAT-CSF-2026",
            requirement_name="CSF",
            institution_code="sat",
            period_code="2026-01",
        )
        comp = result.comprehension
        assert comp["status_assessment"]["validity"] == "indeterminate"
        assert comp["status_assessment"]["currency_ok"] is None
        assert comp["obligation_satisfaction"]["verdict"] == "indeterminate"
        assert comp["obligation_satisfaction"]["confidence"] is None
        assert comp["discrepancies"][0]["severity"] == "medium"  # bad enum → medium

    def test_triage_tier_has_no_comprehension(self, monkeypatch, tmp_path):
        client = MagicMock()
        client.with_options.return_value.messages.create.return_value = (
            _mock_anthropic_response()
        )
        provider = _build_provider_with_mock_client(monkeypatch, client)
        result = provider.analyze(
            pdf_path=_blank_pdf_path(tmp_path),
            requirement_code="REC-SAT-CSF-2026",
            requirement_name="CSF",
            institution_code="sat",
            period_code="2026-01",
        )
        assert result.comprehension is None

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

    def test_escalation_cap_zero_always_allows(self, monkeypatch):
        monkeypatch.setattr(
            settings, "DOCUMENT_ANALYSIS_ESCALATION_DAILY_CAP_PER_ORG", 0
        )
        for _ in range(10):
            assert check_org_escalation_daily_quota("org-1") is True

    def test_escalation_cap_one_blocks_second_call(self, monkeypatch):
        monkeypatch.setattr(
            settings, "DOCUMENT_ANALYSIS_ESCALATION_DAILY_CAP_PER_ORG", 1
        )
        assert check_org_escalation_daily_quota("org-1") is True
        assert check_org_escalation_daily_quota("org-1") is False

    def test_triage_and_escalation_buckets_are_independent(self, monkeypatch):
        monkeypatch.setattr(settings, "DOCUMENT_ANALYSIS_DAILY_CAP_PER_ORG", 1)
        monkeypatch.setattr(
            settings, "DOCUMENT_ANALYSIS_ESCALATION_DAILY_CAP_PER_ORG", 1
        )
        # Consuming the triage bucket must not deplete escalation.
        assert check_org_daily_quota("org-1") is True
        assert check_org_daily_quota("org-1") is False
        assert check_org_escalation_daily_quota("org-1") is True


# ---------------------------------------------------------------------------
# Shadow runner — end-to-end persistence with a mocked provider
# ---------------------------------------------------------------------------


class _ShadowDbSetupMixin:
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


class TestShadowRunner(_ShadowDbSetupMixin):
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


# ---------------------------------------------------------------------------
# Phase C — tiered escalation (triage → escalation) in the shadow runner
# ---------------------------------------------------------------------------


def _tier_result(
    *,
    provider_id: str,
    prompt_version: str = "csf_sat.v2",
    confidence: float | None = 0.9,
    authenticity: dict | None = None,
    error: str | None = None,
    with_signals: bool = True,
) -> AnalysisResult:
    signals = (
        DocumentSignals(
            detected_institution="sat",
            detected_document_type="csf",
            requirement_match_confidence=confidence,
        )
        if with_signals
        else None
    )
    return AnalysisResult(
        provider_id=provider_id,
        prompt_version=prompt_version,
        latency_ms=10,
        signals=signals,
        error=error,
        authenticity=authenticity,
    )


def _triage_provider(result: AnalysisResult) -> MagicMock:
    provider = MagicMock()
    provider.provider_id = "anthropic:claude-haiku-4-5"
    provider.analyze.return_value = result
    return provider


def _escalation_provider(result: AnalysisResult) -> MagicMock:
    provider = MagicMock()
    provider.provider_id = "anthropic:claude-sonnet-4-6"
    provider.analyze.return_value = result
    return provider


def _tiered_factory(triage, escalation):
    """Tier-aware stand-in for ``build_document_analysis_provider``."""

    def build(tier: str = "triage"):
        return triage if tier == "triage" else escalation

    return build


_CLEAN_AUTH = {"concerns": [], "looks_fabricated": False, "confidence": 0.95}


class TestShadowRunnerTiering(_ShadowDbSetupMixin):
    def _run(self, db_setup, tmp_path, *, requirement_risk_level=None):
        from app.services.document_analysis.shadow_runner import run_shadow_analysis

        run_shadow_analysis(
            document_id=db_setup["document_id"],
            submission_id=db_setup["submission_id"],
            pdf_path=str(_blank_pdf_path(tmp_path)),
            requirement_code="REC-SAT-CSF-2026",
            requirement_name="CSF",
            institution_code="sat",
            period_code="2026-01",
            org_id="cli-1",
            requirement_risk_level=requirement_risk_level,
        )

    def _inspection(self):
        from app.db.session import SessionLocal
        from app.models import DocumentInspection

        db = SessionLocal()
        try:
            return db.query(DocumentInspection).first()
        finally:
            db.close()

    def _set_inspection_risk(self, risk, reasons=None):
        from app.db.session import SessionLocal
        from app.models import DocumentInspection

        db = SessionLocal()
        try:
            insp = db.query(DocumentInspection).first()
            insp.authenticity_risk = risk
            insp.risk_reasons = reasons
            db.commit()
        finally:
            db.close()

    # -- no escalation on a clean, confident triage -------------------

    def test_clean_confident_triage_does_not_escalate(
        self, monkeypatch, tmp_path, db_setup
    ):
        triage = _triage_provider(
            _tier_result(
                provider_id="anthropic:claude-haiku-4-5",
                confidence=0.9,
                authenticity=_CLEAN_AUTH,
            )
        )
        escalation = _escalation_provider(
            _tier_result(provider_id="anthropic:claude-sonnet-4-6")
        )
        with patch(
            "app.services.document_analysis.shadow_runner.build_document_analysis_provider",
            side_effect=_tiered_factory(triage, escalation),
        ):
            self._run(db_setup, tmp_path)

        triage.analyze.assert_called_once()
        escalation.analyze.assert_not_called()
        insp = self._inspection()
        assert insp.shadow_provider_id == "anthropic:claude-haiku-4-5"
        # No escalation decision → no _tiers bookkeeping.
        assert "_tiers" not in (insp.shadow_signals or {})

    # -- trigger (a): triage authenticity flags ------------------------

    def test_triage_authenticity_concerns_trigger_escalation(
        self, monkeypatch, tmp_path, db_setup
    ):
        triage = _triage_provider(
            _tier_result(
                provider_id="anthropic:claude-haiku-4-5",
                confidence=0.9,
                authenticity={
                    "concerns": [
                        {"concern": "Tipografía inconsistente", "severity": "medium"}
                    ],
                    "looks_fabricated": False,
                    "confidence": 0.5,
                },
            )
        )
        escalation = _escalation_provider(
            _tier_result(
                provider_id="anthropic:claude-sonnet-4-6",
                prompt_version="authenticity_deep.v1",
                authenticity={
                    "concerns": [
                        {"concern": "Sello digital ausente", "severity": "medium"}
                    ],
                    "looks_fabricated": True,
                    "confidence": 0.2,
                },
            )
        )
        with patch(
            "app.services.document_analysis.shadow_runner.build_document_analysis_provider",
            side_effect=_tiered_factory(triage, escalation),
        ):
            self._run(db_setup, tmp_path)

        escalation.analyze.assert_called_once()
        insp = self._inspection()
        # Escalation SUPERSEDES triage for the stored shadow columns.
        assert insp.shadow_provider_id == "anthropic:claude-sonnet-4-6"
        assert insp.shadow_prompt_version == "authenticity_deep.v1"
        tiers = insp.shadow_signals["_tiers"]
        assert tiers["triage"]["provider_id"] == "anthropic:claude-haiku-4-5"
        assert tiers["escalation"]["provider_id"] == "anthropic:claude-sonnet-4-6"
        assert "llm_flags" in tiers["escalation"]["triggers"]

    def test_triage_looks_fabricated_alone_triggers_escalation(
        self, monkeypatch, tmp_path, db_setup
    ):
        triage = _triage_provider(
            _tier_result(
                provider_id="anthropic:claude-haiku-4-5",
                confidence=0.9,
                authenticity={
                    "concerns": [],
                    "looks_fabricated": True,
                    "confidence": 0.3,
                },
            )
        )
        escalation = _escalation_provider(
            _tier_result(provider_id="anthropic:claude-sonnet-4-6")
        )
        with patch(
            "app.services.document_analysis.shadow_runner.build_document_analysis_provider",
            side_effect=_tiered_factory(triage, escalation),
        ):
            self._run(db_setup, tmp_path)
        escalation.analyze.assert_called_once()

    # -- trigger (b): low triage match confidence ----------------------

    def test_low_triage_confidence_triggers_escalation(
        self, monkeypatch, tmp_path, db_setup
    ):
        triage = _triage_provider(
            _tier_result(
                provider_id="anthropic:claude-haiku-4-5",
                confidence=0.3,
                authenticity=_CLEAN_AUTH,
            )
        )
        escalation = _escalation_provider(
            _tier_result(provider_id="anthropic:claude-sonnet-4-6")
        )
        with patch(
            "app.services.document_analysis.shadow_runner.build_document_analysis_provider",
            side_effect=_tiered_factory(triage, escalation),
        ):
            self._run(db_setup, tmp_path)
        escalation.analyze.assert_called_once()
        insp = self._inspection()
        triggers = insp.shadow_signals["_tiers"]["escalation"]["triggers"]
        assert triggers == ["low_match_confidence"]

    # -- trigger (c): deterministic verdict already suspicious ---------

    def test_deterministic_suspicious_verdict_triggers_escalation(
        self, monkeypatch, tmp_path, db_setup
    ):
        self._set_inspection_risk(
            "suspicious",
            [{"code": "metadata_edit_gap", "severity": "medium", "detail_es": "x"}],
        )
        triage = _triage_provider(
            _tier_result(
                provider_id="anthropic:claude-haiku-4-5",
                confidence=0.9,
                authenticity=_CLEAN_AUTH,
            )
        )
        escalation = _escalation_provider(
            _tier_result(provider_id="anthropic:claude-sonnet-4-6")
        )
        with patch(
            "app.services.document_analysis.shadow_runner.build_document_analysis_provider",
            side_effect=_tiered_factory(triage, escalation),
        ):
            self._run(db_setup, tmp_path)
        escalation.analyze.assert_called_once()
        insp = self._inspection()
        triggers = insp.shadow_signals["_tiers"]["escalation"]["triggers"]
        assert triggers == ["deterministic_risk"]

    # -- trigger (d): requirement risk level alto/crítico --------------

    def test_alto_requirement_risk_level_triggers_escalation(
        self, monkeypatch, tmp_path, db_setup
    ):
        triage = _triage_provider(
            _tier_result(
                provider_id="anthropic:claude-haiku-4-5",
                confidence=0.9,
                authenticity=_CLEAN_AUTH,
            )
        )
        escalation = _escalation_provider(
            _tier_result(provider_id="anthropic:claude-sonnet-4-6")
        )
        with patch(
            "app.services.document_analysis.shadow_runner.build_document_analysis_provider",
            side_effect=_tiered_factory(triage, escalation),
        ):
            self._run(db_setup, tmp_path, requirement_risk_level="alto")
        escalation.analyze.assert_called_once()
        insp = self._inspection()
        triggers = insp.shadow_signals["_tiers"]["escalation"]["triggers"]
        assert triggers == ["requirement_risk_level"]

    def test_critico_requirement_risk_level_triggers_escalation(
        self, monkeypatch, tmp_path, db_setup
    ):
        triage = _triage_provider(
            _tier_result(
                provider_id="anthropic:claude-haiku-4-5",
                confidence=0.9,
                authenticity=_CLEAN_AUTH,
            )
        )
        escalation = _escalation_provider(
            _tier_result(provider_id="anthropic:claude-sonnet-4-6")
        )
        with patch(
            "app.services.document_analysis.shadow_runner.build_document_analysis_provider",
            side_effect=_tiered_factory(triage, escalation),
        ):
            self._run(db_setup, tmp_path, requirement_risk_level="Crítico")
        escalation.analyze.assert_called_once()

    # -- escalation cap exhaustion: graceful skip ----------------------

    def test_escalation_cap_exhaustion_keeps_triage_result(
        self, monkeypatch, tmp_path, db_setup
    ):
        monkeypatch.setattr(
            settings, "DOCUMENT_ANALYSIS_ESCALATION_DAILY_CAP_PER_ORG", 1
        )
        # Pre-consume the escalation bucket for this org.
        assert check_org_escalation_daily_quota("cli-1") is True

        triage = _triage_provider(
            _tier_result(
                provider_id="anthropic:claude-haiku-4-5",
                confidence=0.3,  # trigger fires
                authenticity=_CLEAN_AUTH,
            )
        )
        escalation = _escalation_provider(
            _tier_result(provider_id="anthropic:claude-sonnet-4-6")
        )
        with patch(
            "app.services.document_analysis.shadow_runner.build_document_analysis_provider",
            side_effect=_tiered_factory(triage, escalation),
        ):
            self._run(db_setup, tmp_path)

        escalation.analyze.assert_not_called()
        insp = self._inspection()
        # Triage result stands; the skip is noted in _tiers.
        assert insp.shadow_provider_id == "anthropic:claude-haiku-4-5"
        assert insp.shadow_error is None
        tiers = insp.shadow_signals["_tiers"]
        assert tiers["escalation"]["skipped"] == "daily_cap_exceeded"
        assert tiers["escalation"]["triggers"] == ["low_match_confidence"]

    # -- escalation provider failure: triage result stands -------------

    def test_escalation_error_falls_back_to_triage_result(
        self, monkeypatch, tmp_path, db_setup
    ):
        triage = _triage_provider(
            _tier_result(
                provider_id="anthropic:claude-haiku-4-5",
                confidence=0.3,
                authenticity=_CLEAN_AUTH,
            )
        )
        escalation = _escalation_provider(
            _tier_result(
                provider_id="anthropic:claude-sonnet-4-6",
                error="timeout",
                with_signals=False,
            )
        )
        with patch(
            "app.services.document_analysis.shadow_runner.build_document_analysis_provider",
            side_effect=_tiered_factory(triage, escalation),
        ):
            self._run(db_setup, tmp_path)

        escalation.analyze.assert_called_once()
        insp = self._inspection()
        assert insp.shadow_provider_id == "anthropic:claude-haiku-4-5"
        assert insp.shadow_error is None
        assert insp.shadow_signals["_tiers"]["escalation"]["error"] == "timeout"

    # -- fail-open: a raising provider never blocks or marks -----------

    def test_provider_exception_fails_open(self, monkeypatch, tmp_path, db_setup):
        triage = MagicMock()
        triage.provider_id = "anthropic:claude-haiku-4-5"
        triage.analyze.side_effect = RuntimeError("kaboom")
        with patch(
            "app.services.document_analysis.shadow_runner.build_document_analysis_provider",
            side_effect=_tiered_factory(triage, MagicMock()),
        ):
            # Must not raise.
            self._run(db_setup, tmp_path)
        insp = self._inspection()
        assert insp.shadow_error == "provider_error:RuntimeError"
        # The verdict columns are untouched — LLM failure NEVER marks a
        # document.
        assert insp.authenticity_risk is None
        assert insp.risk_reasons is None

    # -- merge end-to-end through the runner ---------------------------

    def test_llm_concern_re_rolls_clean_verdict_to_suspicious(
        self, monkeypatch, tmp_path, db_setup
    ):
        self._set_inspection_risk("clean", [])
        triage = _triage_provider(
            _tier_result(
                provider_id="anthropic:claude-haiku-4-5",
                confidence=0.9,
                authenticity={
                    "concerns": [
                        {"concern": "Cifras incoherentes", "severity": "medium"}
                    ],
                    "looks_fabricated": False,
                    "confidence": 0.4,
                },
            )
        )
        # Escalation is unavailable → graceful skip; triage merges.
        with patch(
            "app.services.document_analysis.shadow_runner.build_document_analysis_provider",
            side_effect=lambda tier="triage": triage if tier == "triage" else None,
        ):
            self._run(db_setup, tmp_path)

        insp = self._inspection()
        assert insp.authenticity_risk == "suspicious"
        llm = [
            r for r in insp.risk_reasons if r["code"] == "llm_authenticity_concern"
        ]
        assert len(llm) == 1
        assert llm[0]["severity"] == "medium"
        assert llm[0]["detail_es"] == "IA: Cifras incoherentes"
        assert insp.shadow_signals["_tiers"]["escalation"]["skipped"] == (
            "provider_unavailable"
        )

    def test_rerun_does_not_accumulate_llm_reasons(
        self, monkeypatch, tmp_path, db_setup
    ):
        self._set_inspection_risk(
            "clean",
            [{"code": "pdf_text_layer", "severity": "info", "detail_es": "ok"}],
        )
        triage = _triage_provider(
            _tier_result(
                provider_id="anthropic:claude-haiku-4-5",
                confidence=0.9,
                authenticity={
                    "concerns": [
                        {"concern": "Folio ausente", "severity": "medium"}
                    ],
                    "looks_fabricated": False,
                    "confidence": 0.4,
                },
            )
        )
        with patch(
            "app.services.document_analysis.shadow_runner.build_document_analysis_provider",
            side_effect=lambda tier="triage": triage if tier == "triage" else None,
        ):
            self._run(db_setup, tmp_path)
            self._run(db_setup, tmp_path)  # idempotent re-run

        insp = self._inspection()
        llm = [
            r for r in insp.risk_reasons if r["code"] == "llm_authenticity_concern"
        ]
        deterministic = [
            r for r in insp.risk_reasons if r["code"] == "pdf_text_layer"
        ]
        assert len(llm) == 1  # strip-and-replace, never accumulate
        assert len(deterministic) == 1  # deterministic reasons untouched
        assert insp.authenticity_risk == "suspicious"


# ---------------------------------------------------------------------------
# Phase C — _merge_llm_authenticity unit behaviour (no DB needed)
# ---------------------------------------------------------------------------


class TestMergeLlmAuthenticity:
    def _inspection(self, *, risk=None, reasons=None):
        from app.models import DocumentInspection

        insp = DocumentInspection(
            document_id="doc-1",
            is_pdf=True,
            page_count=1,
            text_char_count=0,
            has_text=False,
            is_probably_scanned=False,
        )
        insp.authenticity_risk = risk
        insp.risk_reasons = reasons
        return insp

    def _result(self, authenticity):
        return AnalysisResult(
            provider_id="anthropic:claude-haiku-4-5",
            prompt_version="base.v2",
            latency_ms=1,
            signals=None,
            authenticity=authenticity,
        )

    def test_no_authenticity_judgment_is_a_noop(self):
        from app.services.document_analysis.shadow_runner import (
            _merge_llm_authenticity,
        )

        reasons = [{"code": "x", "severity": "medium", "detail_es": "d"}]
        insp = self._inspection(risk="suspicious", reasons=reasons)
        _merge_llm_authenticity(insp, self._result(None))
        assert insp.authenticity_risk == "suspicious"
        assert insp.risk_reasons == reasons

    def test_clean_llm_result_leaves_deterministic_verdict_untouched(self):
        from app.services.document_analysis.shadow_runner import (
            _merge_llm_authenticity,
        )

        reasons = [
            {"code": "metadata_edit_gap", "severity": "medium", "detail_es": "d"}
        ]
        insp = self._inspection(risk="suspicious", reasons=list(reasons))
        _merge_llm_authenticity(
            insp,
            self._result(
                {"concerns": [], "looks_fabricated": False, "confidence": 0.95}
            ),
        )
        assert insp.authenticity_risk == "suspicious"
        assert insp.risk_reasons == reasons

    def test_clean_llm_result_never_flips_unanalyzed_row_to_clean(self):
        from app.services.document_analysis.shadow_runner import (
            _merge_llm_authenticity,
        )

        insp = self._inspection(risk=None, reasons=None)
        _merge_llm_authenticity(
            insp,
            self._result(
                {"concerns": [], "looks_fabricated": False, "confidence": 0.9}
            ),
        )
        assert insp.authenticity_risk is None  # still "sin analizar"
        assert insp.risk_reasons is None

    def test_low_severity_maps_to_info_and_does_not_flag(self):
        from app.services.document_analysis.shadow_runner import (
            _merge_llm_authenticity,
        )

        insp = self._inspection(risk="clean", reasons=[])
        _merge_llm_authenticity(
            insp,
            self._result(
                {
                    "concerns": [{"concern": "Detalle menor", "severity": "low"}],
                    "looks_fabricated": False,
                    "confidence": 0.8,
                }
            ),
        )
        assert insp.risk_reasons == [
            {
                "code": "llm_authenticity_concern",
                "severity": "info",
                "detail_es": "IA: Detalle menor",
            }
        ]
        # info-only reasons keep the verdict clean — the medium cap
        # means LLM output alone can flag, never high_risk.
        assert insp.authenticity_risk == "clean"

    def test_looks_fabricated_without_concerns_adds_single_medium_reason(self):
        from app.services.document_analysis.shadow_runner import (
            _merge_llm_authenticity,
        )

        insp = self._inspection(risk="clean", reasons=[])
        _merge_llm_authenticity(
            insp,
            self._result(
                {"concerns": [], "looks_fabricated": True, "confidence": 0.2}
            ),
        )
        assert insp.risk_reasons == [
            {
                "code": "llm_authenticity_concern",
                "severity": "medium",
                "detail_es": (
                    "IA: El análisis de IA considera que el documento "
                    "podría ser fabricado."
                ),
            }
        ]
        assert insp.authenticity_risk == "suspicious"

    def test_llm_reasons_never_exceed_medium(self):
        from app.services.document_analysis.shadow_runner import (
            _merge_llm_authenticity,
        )

        insp = self._inspection(risk="clean", reasons=[])
        _merge_llm_authenticity(
            insp,
            self._result(
                {
                    "concerns": [
                        {"concern": "Señal A", "severity": "medium"},
                        {"concern": "Señal B", "severity": "medium"},
                    ],
                    "looks_fabricated": True,
                    "confidence": 0.1,
                }
            ),
        )
        # Even with multiple medium concerns + a fabricated verdict the
        # rollup tops out at suspicious — never high_risk from LLM alone.
        assert insp.authenticity_risk == "suspicious"
        assert all(r["severity"] == "medium" for r in insp.risk_reasons)

    def test_deterministic_high_reason_keeps_high_risk_after_merge(self):
        from app.services.document_analysis.shadow_runner import (
            _merge_llm_authenticity,
        )

        insp = self._inspection(
            risk="high_risk",
            reasons=[
                {"code": "javascript_embedded", "severity": "high", "detail_es": "js"}
            ],
        )
        _merge_llm_authenticity(
            insp,
            self._result(
                {
                    "concerns": [{"concern": "Folio ausente", "severity": "low"}],
                    "looks_fabricated": False,
                    "confidence": 0.6,
                }
            ),
        )
        assert insp.authenticity_risk == "high_risk"
        # Sorted high → info, deterministic reason verbatim first.
        assert insp.risk_reasons[0]["code"] == "javascript_embedded"
        assert insp.risk_reasons[1]["detail_es"] == "IA: Folio ausente"

    def test_stale_llm_reasons_are_stripped_on_clean_rerun(self):
        from app.services.document_analysis.shadow_runner import (
            _merge_llm_authenticity,
        )

        insp = self._inspection(
            risk="suspicious",
            reasons=[
                {
                    "code": "llm_authenticity_concern",
                    "severity": "medium",
                    "detail_es": "IA: vieja señal",
                }
            ],
        )
        _merge_llm_authenticity(
            insp,
            self._result(
                {"concerns": [], "looks_fabricated": False, "confidence": 0.95}
            ),
        )
        # The clean re-run removes the stale reason and re-rolls down.
        assert insp.risk_reasons == []
        assert insp.authenticity_risk == "clean"
