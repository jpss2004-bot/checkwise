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

import asyncio
import json
from datetime import UTC
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

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

    def test_deep_tier_emits_field_suggestions_when_schema_supplied(
        self, monkeypatch, tmp_path
    ):
        payload = {
            "detected_institution": "sat",
            "detected_document_type": "csf",
            "detected_rfcs": [],
            "detected_dates": [],
            "period_mentions": [],
            "requirement_match_confidence": 0.9,
            "mismatch_reason": None,
            "anomaly_codes": [],
            "summary_for_reviewer": "ok",
            "field_suggestions": [
                {
                    "field_key": "main_date",
                    "value": "2024-03-07",
                    "confidence": 1.4,  # clamped to 1.0
                    "evidence": "fecha de emisión",
                },
                {"field_key": "", "value": "x", "confidence": 0.9, "evidence": ""},  # dropped
            ],
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
            metadata_field_schema=[
                {
                    "field_key": "main_date",
                    "label": "Fecha principal",
                    "requirement_level": "required",
                    "description": "Fecha del documento",
                }
            ],
        )
        assert result.error is None
        assert result.field_suggestions == [
            {
                "field_key": "main_date",
                "value": "2024-03-07",
                "confidence": 1.0,
                "evidence": "fecha de emisión",
            }
        ]
        create_kwargs = client.with_options.return_value.messages.create.call_args.kwargs
        schema_props = create_kwargs["output_config"]["format"]["schema"]["properties"]
        assert "field_suggestions" in schema_props
        user_text = create_kwargs["messages"][0]["content"][-1]["text"]
        assert "main_date" in user_text
        assert "field_suggestions" in user_text

    def test_field_suggestion_prompt_allows_generated_description(self):
        provider = AnthropicDocumentAnalysisProvider(
            api_key="sk-test", model="claude-sonnet-4-6", deep_authenticity=True
        )
        with_description = provider._build_user_prompt(  # noqa: SLF001 — prompt unit
            requirement_name="CSF",
            institution_code="sat",
            period_code="2026-01",
            metadata_field_schema=[
                {
                    "field_key": "description",
                    "label": "Descripción",
                    "requirement_level": "conditional",
                    "description": "Texto fijo, listado de anexos o vacío.",
                },
            ],
        )
        # The description field may be generated when the document lacks one.
        assert "REDÁCTALA" in with_description
        assert "description" in with_description

        without_description = provider._build_user_prompt(  # noqa: SLF001
            requirement_name="CSF",
            institution_code="sat",
            period_code="2026-01",
            metadata_field_schema=[
                {
                    "field_key": "main_date",
                    "label": "Fecha principal",
                    "requirement_level": "required",
                    "description": "Fecha del documento",
                },
            ],
        )
        # The generation exception only appears when `description` is in scope.
        assert "REDÁCTALA" not in without_description

    def test_deep_tier_without_schema_omits_field_suggestions(
        self, monkeypatch, tmp_path
    ):
        client = MagicMock()
        client.with_options.return_value.messages.create.return_value = (
            _mock_structured_response()
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
        assert result.field_suggestions is None
        create_kwargs = client.with_options.return_value.messages.create.call_args.kwargs
        schema_props = create_kwargs["output_config"]["format"]["schema"]["properties"]
        assert "field_suggestions" not in schema_props

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


class TestComprehensionFieldSuggestionGating:
    """Phase 3/4 — the metadata field-suggestion feature is gated dark."""

    def test_schema_is_none_when_feature_disabled(self, monkeypatch):
        from app.services.document_analysis import shadow_runner as sr

        monkeypatch.setattr(settings, "COMPREHENSION_FIELD_SUGGESTIONS_ENABLED", False)
        monkeypatch.setattr(settings, "COMPREHENSION_UNLOCKED_REQUIREMENT_CODES", "*")
        assert (
            sr._metadata_field_schema_for(
                requirement_code="constancia_situacion_fiscal",
                requirement_name="Constancia de Situación Fiscal",
                institution_code="sat",
            )
            is None
        )

    def test_schema_is_none_when_code_not_unlocked(self, monkeypatch):
        from app.services.document_analysis import shadow_runner as sr

        monkeypatch.setattr(settings, "COMPREHENSION_FIELD_SUGGESTIONS_ENABLED", True)
        monkeypatch.setattr(
            settings, "COMPREHENSION_UNLOCKED_REQUIREMENT_CODES", "registro_repse"
        )
        assert (
            sr._metadata_field_schema_for(
                requirement_code="constancia_situacion_fiscal",
                requirement_name="Constancia de Situación Fiscal",
                institution_code="sat",
            )
            is None
        )

    def test_schema_returns_ai_assisted_fields_when_unlocked(self, monkeypatch):
        from app.services.document_analysis import shadow_runner as sr

        monkeypatch.setattr(settings, "COMPREHENSION_FIELD_SUGGESTIONS_ENABLED", True)
        monkeypatch.setattr(
            settings,
            "COMPREHENSION_UNLOCKED_REQUIREMENT_CODES",
            "constancia_situacion_fiscal",
        )
        schema = sr._metadata_field_schema_for(
            requirement_code="constancia_situacion_fiscal",
            requirement_name="Constancia de Situación Fiscal",
            institution_code="sat",
        )
        assert schema is not None
        keys = {field["field_key"] for field in schema}
        assert "main_date" in keys
        assert all({"field_key", "label", "description"} <= set(f) for f in schema)

    def test_wildcard_unlocks_all_codes(self, monkeypatch):
        from app.services.document_analysis import shadow_runner as sr

        monkeypatch.setattr(settings, "COMPREHENSION_FIELD_SUGGESTIONS_ENABLED", True)
        monkeypatch.setattr(settings, "COMPREHENSION_UNLOCKED_REQUIREMENT_CODES", "*")
        schema = sr._metadata_field_schema_for(
            requirement_code="registro_repse",
            requirement_name="Registro REPSE",
            institution_code="stps_repse",
        )
        assert schema is not None and schema

    def test_enrich_is_noop_when_disabled(self, monkeypatch):
        from app.services.document_analysis import shadow_runner as sr

        monkeypatch.setattr(settings, "COMPREHENSION_FIELD_SUGGESTIONS_ENABLED", False)
        called = {"n": 0}

        def _boom(**_kwargs):
            called["n"] += 1
            raise AssertionError("reexport must not run when disabled")

        monkeypatch.setattr(
            "app.services.metadata_export.reexport_metadata_with_field_suggestions",
            _boom,
        )
        sr._maybe_enrich_metadata(
            document_id="doc_1",
            pdf_path="/tmp/x.pdf",
            field_suggestions=[{"field_key": "main_date", "value": "x", "confidence": 1.0}],
        )
        assert called["n"] == 0

    def test_enrich_drops_low_confidence_suggestions(self, monkeypatch):
        from app.services.document_analysis import shadow_runner as sr

        monkeypatch.setattr(settings, "COMPREHENSION_FIELD_SUGGESTIONS_ENABLED", True)
        monkeypatch.setattr(
            settings, "COMPREHENSION_FIELD_SUGGESTION_MIN_CONFIDENCE", 0.8
        )
        captured = {"suggestions": None}

        def _capture(*, document_id, pdf_path, field_suggestions):
            captured["suggestions"] = field_suggestions
            from app.services.metadata_export import MetadataExportResult

            return MetadataExportResult(status="completed")

        monkeypatch.setattr(
            "app.services.metadata_export.reexport_metadata_with_field_suggestions",
            _capture,
        )
        sr._maybe_enrich_metadata(
            document_id="doc_1",
            pdf_path="/tmp/x.pdf",
            field_suggestions=[
                {"field_key": "main_date", "value": "ok", "confidence": 0.9},
                {"field_key": "participants", "value": "low", "confidence": 0.3},
                {"field_key": "issue_date", "value": "none", "confidence": None},
            ],
        )
        assert captured["suggestions"] == [
            {"field_key": "main_date", "value": "ok", "confidence": 0.9}
        ]


# ---------------------------------------------------------------------------
# High-stakes escalation gate (DOCUMENT_ANALYSIS_GATE_HIGH_STAKES_ESCALATION)
# ---------------------------------------------------------------------------


def _hs_triage(confidence: float | None = 0.9, authenticity: dict | None = None):
    return _tier_result(
        provider_id="anthropic:claude-haiku-4-5",
        confidence=confidence,
        authenticity=authenticity,
    )


def _gate_on(monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(
        settings, "DOCUMENT_ANALYSIS_GATE_HIGH_STAKES_ESCALATION", True
    )


def test_escalation_gate_off_high_stakes_always_escalates() -> None:
    from app.services.document_analysis.shadow_runner import _escalation_triggers

    triggers = _escalation_triggers(
        _hs_triage(confidence=0.95),
        requirement_risk_level="alto",
        current_authenticity_risk=None,
        org_id="o",
    )
    assert "requirement_risk_level" in triggers  # default behavior unchanged


def test_escalation_gate_on_skips_clean_confident_high_stakes(monkeypatch) -> None:
    from app.services.document_analysis.shadow_runner import _escalation_triggers

    _gate_on(monkeypatch)
    triggers = _escalation_triggers(
        _hs_triage(confidence=0.95),
        requirement_risk_level="critico",
        current_authenticity_risk=None,
        org_id="o",
    )
    assert triggers == []  # clean + confident + gated → no escalation


def test_escalation_gate_on_escalates_mid_confidence(monkeypatch) -> None:
    from app.services.document_analysis.shadow_runner import _escalation_triggers

    _gate_on(monkeypatch)
    # 0.6 is above the base 0.5 bar (so low_match_confidence does NOT fire) but
    # below the stricter 0.85 high-stakes bar.
    triggers = _escalation_triggers(
        _hs_triage(confidence=0.6),
        requirement_risk_level="alto",
        current_authenticity_risk=None,
        org_id="o",
    )
    assert "high_stakes_low_confidence" in triggers
    assert "low_match_confidence" not in triggers


def test_escalation_gate_on_escalates_when_no_confidence(monkeypatch) -> None:
    from app.services.document_analysis.shadow_runner import _escalation_triggers

    _gate_on(monkeypatch)
    triggers = _escalation_triggers(
        _hs_triage(confidence=None),
        requirement_risk_level="alto",
        current_authenticity_risk=None,
        org_id="o",
    )
    assert "high_stakes_low_confidence" in triggers


def test_escalation_gate_on_keeps_per_doc_signal(monkeypatch) -> None:
    from app.services.document_analysis.shadow_runner import _escalation_triggers

    _gate_on(monkeypatch)
    # Clean + confident triage, but intake forensics already flagged the doc →
    # escalation still happens via deterministic_risk, just not via risk_level.
    triggers = _escalation_triggers(
        _hs_triage(confidence=0.95),
        requirement_risk_level="alto",
        current_authenticity_risk="suspicious",
        org_id="o",
    )
    assert "deterministic_risk" in triggers
    assert "requirement_risk_level" not in triggers


def test_escalation_gate_on_org_override(monkeypatch) -> None:
    from app.core.config import settings
    from app.services.document_analysis.shadow_runner import _escalation_triggers

    _gate_on(monkeypatch)
    monkeypatch.setattr(
        settings, "DOCUMENT_ANALYSIS_ALWAYS_ESCALATE_ORG_IDS", " vip-org "
    )
    triggers = _escalation_triggers(
        _hs_triage(confidence=0.95),
        requirement_risk_level="alto",
        current_authenticity_risk=None,
        org_id="vip-org",
    )
    assert "requirement_risk_level" in triggers  # cohort exempt from the gate


def test_escalation_gate_on_ignores_non_high_stakes(monkeypatch) -> None:
    from app.services.document_analysis.shadow_runner import _escalation_triggers

    _gate_on(monkeypatch)
    triggers = _escalation_triggers(
        _hs_triage(confidence=0.95),
        requirement_risk_level="medium",
        current_authenticity_risk=None,
        org_id="o",
    )
    assert triggers == []  # medium never escalates on risk level


# ---------------------------------------------------------------------------
# A1 — triage-skip (DOCUMENT_ANALYSIS_TRIAGE_SKIP_ENABLED)
# ---------------------------------------------------------------------------


def _enable_triage_skip(monkeypatch, *, sampling_rate=0.0, min_confidence=0.85):
    monkeypatch.setattr(settings, "DOCUMENT_ANALYSIS_TRIAGE_SKIP_ENABLED", True)
    monkeypatch.setattr(
        settings, "DOCUMENT_ANALYSIS_TRIAGE_SKIP_SAMPLING_RATE", sampling_rate
    )
    monkeypatch.setattr(
        settings, "DOCUMENT_ANALYSIS_TRIAGE_SKIP_MIN_CONFIDENCE", min_confidence
    )


class TestTriageSkipSampling:
    """``_triage_skip_sampled`` — the monitoring-sample draw."""

    def test_rate_zero_never_samples(self, monkeypatch):
        from app.services.document_analysis.shadow_runner import _triage_skip_sampled

        monkeypatch.setattr(
            settings, "DOCUMENT_ANALYSIS_TRIAGE_SKIP_SAMPLING_RATE", 0.0
        )
        assert _triage_skip_sampled() is False

    def test_rate_one_always_samples(self, monkeypatch):
        from app.services.document_analysis.shadow_runner import _triage_skip_sampled

        monkeypatch.setattr(
            settings, "DOCUMENT_ANALYSIS_TRIAGE_SKIP_SAMPLING_RATE", 1.0
        )
        assert _triage_skip_sampled() is True

    def test_rate_mid_uses_uniform_draw(self, monkeypatch):
        from app.services.document_analysis import shadow_runner

        monkeypatch.setattr(
            settings, "DOCUMENT_ANALYSIS_TRIAGE_SKIP_SAMPLING_RATE", 0.5
        )
        monkeypatch.setattr(shadow_runner.random, "random", lambda: 0.4)
        assert shadow_runner._triage_skip_sampled() is True
        monkeypatch.setattr(shadow_runner.random, "random", lambda: 0.6)
        assert shadow_runner._triage_skip_sampled() is False


class TestTriageSkipDecision(_ShadowDbSetupMixin):
    """``_triage_skip_decision`` — the eligibility predicate."""

    _CLEAN = dict(
        is_pdf=True,
        is_corrupt=False,
        is_encrypted=False,
        inspection_error=None,
        has_text=True,
        is_probably_scanned=False,
        authenticity_risk="clean",
        risk_reasons=None,
        mismatch_reason=None,
        rfc_alignment="match",
        requirement_match_confidence=0.9,
    )

    def _set_inspection(self, **fields):
        from app.db.session import SessionLocal
        from app.models import DocumentInspection

        db = SessionLocal()
        try:
            insp = db.query(DocumentInspection).first()
            for key, value in fields.items():
                setattr(insp, key, value)
            db.commit()
        finally:
            db.close()

    def _decide(self, db_setup, *, requirement_risk_level=None):
        from app.services.document_analysis.shadow_runner import (
            _triage_skip_decision,
        )

        return _triage_skip_decision(
            db_setup["document_id"],
            requirement_risk_level=requirement_risk_level,
        )

    def test_clean_aligned_born_digital_is_eligible(self, monkeypatch, db_setup):
        _enable_triage_skip(monkeypatch)
        self._set_inspection(**self._CLEAN)
        decision = self._decide(db_setup)
        assert decision.eligible is True
        assert decision.snapshot["reason"] == "heuristic_clean_aligned"
        assert decision.snapshot["heuristic_confidence"] == pytest.approx(0.9)

    def test_already_completed_run_never_eligible(self, monkeypatch, db_setup):
        # Idempotency guard: a doc that already has a completed shadow run is
        # never downgraded to a skip (no clobber of real audit data).
        from datetime import datetime

        _enable_triage_skip(monkeypatch)
        self._set_inspection(
            **{
                **self._CLEAN,
                "shadow_completed_at": datetime(2026, 1, 1, tzinfo=UTC),
            }
        )
        assert self._decide(db_setup).eligible is False

    def test_high_stakes_requirement_never_eligible(self, monkeypatch, db_setup):
        _enable_triage_skip(monkeypatch)
        self._set_inspection(**self._CLEAN)
        for level in ("alto", "critico", "crítico", "ALTO"):
            assert self._decide(db_setup, requirement_risk_level=level).eligible is False
        # ...but a non-high-stakes level still qualifies.
        assert self._decide(db_setup, requirement_risk_level="medium").eligible is True

    def test_authenticity_not_clean_blocks(self, monkeypatch, db_setup):
        _enable_triage_skip(monkeypatch)
        for risk in ("suspicious", "high_risk", None):
            self._set_inspection(**{**self._CLEAN, "authenticity_risk": risk})
            assert self._decide(db_setup).eligible is False

    def test_medium_risk_reason_blocks(self, monkeypatch, db_setup):
        _enable_triage_skip(monkeypatch)
        self._set_inspection(
            **{
                **self._CLEAN,
                "risk_reasons": [
                    {"code": "x", "severity": "medium", "detail_es": "y"}
                ],
            }
        )
        assert self._decide(db_setup).eligible is False

    def test_low_confidence_blocks(self, monkeypatch, db_setup):
        _enable_triage_skip(monkeypatch)
        self._set_inspection(**{**self._CLEAN, "requirement_match_confidence": 0.84})
        assert self._decide(db_setup).eligible is False
        self._set_inspection(**{**self._CLEAN, "requirement_match_confidence": None})
        assert self._decide(db_setup).eligible is False

    def test_rfc_alignment_blocks(self, monkeypatch, db_setup):
        _enable_triage_skip(monkeypatch)
        for alignment in ("mismatch", "homoclave_mismatch", "absent"):
            self._set_inspection(**{**self._CLEAN, "rfc_alignment": alignment})
            assert self._decide(db_setup).eligible is False
        # ``no_expected`` (no provider RFC to match) is allowed.
        self._set_inspection(**{**self._CLEAN, "rfc_alignment": "no_expected"})
        assert self._decide(db_setup).eligible is True

    def test_scanned_or_no_text_blocks(self, monkeypatch, db_setup):
        _enable_triage_skip(monkeypatch)
        self._set_inspection(**{**self._CLEAN, "is_probably_scanned": True})
        assert self._decide(db_setup).eligible is False
        self._set_inspection(**{**self._CLEAN, "has_text": False})
        assert self._decide(db_setup).eligible is False

    def test_mismatch_reason_blocks(self, monkeypatch, db_setup):
        _enable_triage_skip(monkeypatch)
        self._set_inspection(**{**self._CLEAN, "mismatch_reason": "tipo no coincide"})
        assert self._decide(db_setup).eligible is False

    def test_structural_problems_block(self, monkeypatch, db_setup):
        _enable_triage_skip(monkeypatch)
        for field in ("is_corrupt", "is_encrypted"):
            self._set_inspection(**{**self._CLEAN, field: True})
            assert self._decide(db_setup).eligible is False
        self._set_inspection(**{**self._CLEAN, "is_pdf": False})
        assert self._decide(db_setup).eligible is False
        self._set_inspection(**{**self._CLEAN, "inspection_error": "boom"})
        assert self._decide(db_setup).eligible is False

    def test_missing_inspection_is_fail_safe(self, monkeypatch, db_setup):
        _enable_triage_skip(monkeypatch)
        from app.services.document_analysis.shadow_runner import (
            _triage_skip_decision,
        )

        assert _triage_skip_decision("does-not-exist", requirement_risk_level=None).eligible is False


class TestTriageSkipRunner(_ShadowDbSetupMixin):
    """``run_shadow_analysis`` end-to-end with triage-skip on/off."""

    _CLEAN = TestTriageSkipDecision._CLEAN

    def _set_clean(self):
        from app.db.session import SessionLocal
        from app.models import DocumentInspection

        db = SessionLocal()
        try:
            insp = db.query(DocumentInspection).first()
            for key, value in self._CLEAN.items():
                setattr(insp, key, value)
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

    def _events(self, event_type):
        from app.db.session import SessionLocal
        from app.models import ValidationEvent

        db = SessionLocal()
        try:
            return [
                e
                for e in db.query(ValidationEvent).all()
                if e.event_type == event_type
            ]
        finally:
            db.close()

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

    def test_flag_off_runs_triage(self, monkeypatch, tmp_path, db_setup):
        # Skip disabled (default) → triage runs even on a clean+aligned doc.
        self._set_clean()
        triage = _triage_provider(
            _tier_result(
                provider_id="anthropic:claude-haiku-4-5",
                confidence=0.9,
                authenticity=_CLEAN_AUTH,
            )
        )
        with patch(
            "app.services.document_analysis.shadow_runner.build_document_analysis_provider",
            side_effect=_tiered_factory(triage, None),
        ):
            self._run(db_setup, tmp_path)

        triage.analyze.assert_called_once()
        assert self._inspection().shadow_provider_id == "anthropic:claude-haiku-4-5"
        assert self._events("shadow_analysis_skipped") == []

    def test_skip_eligible_does_not_call_provider(
        self, monkeypatch, tmp_path, db_setup
    ):
        _enable_triage_skip(monkeypatch, sampling_rate=0.0)
        self._set_clean()
        triage = _triage_provider(
            _tier_result(provider_id="anthropic:claude-haiku-4-5")
        )
        with patch(
            "app.services.document_analysis.shadow_runner.build_document_analysis_provider",
            side_effect=_tiered_factory(triage, None),
        ):
            self._run(db_setup, tmp_path)

        triage.analyze.assert_not_called()
        insp = self._inspection()
        # No shadow_* completion columns are stamped → the doc stays
        # reprocess-eligible and never poses as a completed clean run.
        assert insp.shadow_provider_id is None
        assert insp.shadow_completed_at is None
        assert insp.shadow_error is None
        assert insp.shadow_confidence is None
        # The skip is recorded only via the signals annotation + the event.
        assert insp.shadow_signals["_triage_skip"]["reason"] == "heuristic_clean_aligned"
        # Deterministic verdict untouched.
        assert insp.authenticity_risk == "clean"
        skipped = self._events("shadow_analysis_skipped")
        assert len(skipped) == 1
        assert skipped[0].result == "pass"
        # No completed event — the AI never ran.
        assert self._events("shadow_analysis_completed") == []

    def test_skip_preserves_prior_real_shadow_run(
        self, monkeypatch, tmp_path, db_setup
    ):
        # Idempotency: a re-invocation must NOT downgrade an already-completed
        # real shadow run to a skip (which would clobber the audit blob + KPI).
        _enable_triage_skip(monkeypatch, sampling_rate=0.0)
        self._set_clean()
        from datetime import datetime

        from app.db.session import SessionLocal
        from app.models import DocumentInspection

        db = SessionLocal()
        try:
            insp = db.query(DocumentInspection).first()
            insp.shadow_provider_id = "anthropic:claude-sonnet-4-6"
            insp.shadow_completed_at = datetime(2026, 1, 1, tzinfo=UTC)
            insp.shadow_signals = {"comprehension": {"verdict": "ok"}}
            db.commit()
        finally:
            db.close()

        triage = _triage_provider(
            _tier_result(provider_id="anthropic:claude-haiku-4-5", authenticity=_CLEAN_AUTH)
        )
        escalation = _escalation_provider(
            _tier_result(provider_id="anthropic:claude-sonnet-4-6")
        )
        with patch(
            "app.services.document_analysis.shadow_runner.build_document_analysis_provider",
            side_effect=_tiered_factory(triage, escalation),
        ):
            self._run(db_setup, tmp_path)

        # Not skipped — the doc already had a completed run, so triage re-ran
        # the normal path instead of being downgraded to a skip marker.
        triage.analyze.assert_called_once()
        assert self._events("shadow_analysis_skipped") == []
        assert self._inspection().shadow_provider_id == "anthropic:claude-haiku-4-5"

    def test_skip_falls_through_when_persist_fails(
        self, monkeypatch, tmp_path, db_setup
    ):
        # A persistence failure on the skip marker must fall through to running
        # the triage, never silently lose the document's pass.
        _enable_triage_skip(monkeypatch, sampling_rate=0.0)
        self._set_clean()
        monkeypatch.setattr(
            "app.services.document_analysis.shadow_runner._persist_triage_skip",
            lambda **kwargs: False,
        )
        triage = _triage_provider(
            _tier_result(provider_id="anthropic:claude-haiku-4-5", authenticity=_CLEAN_AUTH)
        )
        with patch(
            "app.services.document_analysis.shadow_runner.build_document_analysis_provider",
            side_effect=_tiered_factory(triage, None),
        ):
            self._run(db_setup, tmp_path)

        triage.analyze.assert_called_once()
        assert self._inspection().shadow_provider_id == "anthropic:claude-haiku-4-5"

    def test_skip_does_not_trigger_auto_approval(
        self, monkeypatch, tmp_path, db_setup
    ):
        _enable_triage_skip(monkeypatch, sampling_rate=0.0)
        self._set_clean()
        triage = _triage_provider(
            _tier_result(provider_id="anthropic:claude-haiku-4-5")
        )
        approve = MagicMock()
        monkeypatch.setattr(
            "app.services.auto_approval.maybe_auto_approve", approve
        )
        with patch(
            "app.services.document_analysis.shadow_runner.build_document_analysis_provider",
            side_effect=_tiered_factory(triage, None),
        ):
            self._run(db_setup, tmp_path)

        approve.assert_not_called()

    def test_ineligible_doc_runs_triage_and_auto_approves(
        self, monkeypatch, tmp_path, db_setup
    ):
        # Contrast: a NON-eligible doc (suspicious) keeps the normal path,
        # which DOES reach the auto-approval hook.
        _enable_triage_skip(monkeypatch, sampling_rate=0.0)
        self._set_clean()
        from app.db.session import SessionLocal
        from app.models import DocumentInspection

        db = SessionLocal()
        try:
            db.query(DocumentInspection).first().authenticity_risk = "suspicious"
            db.commit()
        finally:
            db.close()
        triage = _triage_provider(
            _tier_result(provider_id="anthropic:claude-haiku-4-5", authenticity=_CLEAN_AUTH)
        )
        escalation = _escalation_provider(
            _tier_result(provider_id="anthropic:claude-sonnet-4-6")
        )
        approve = MagicMock()
        monkeypatch.setattr(
            "app.services.auto_approval.maybe_auto_approve", approve
        )
        with patch(
            "app.services.document_analysis.shadow_runner.build_document_analysis_provider",
            side_effect=_tiered_factory(triage, escalation),
        ):
            self._run(db_setup, tmp_path)

        triage.analyze.assert_called_once()
        approve.assert_called_once()
        assert self._events("shadow_analysis_skipped") == []

    def test_sampled_runs_triage_and_records_agreement(
        self, monkeypatch, tmp_path, db_setup
    ):
        # sampling_rate=1.0 → always sample → never skip, but record agreement.
        _enable_triage_skip(monkeypatch, sampling_rate=1.0)
        self._set_clean()
        triage = _triage_provider(
            _tier_result(
                provider_id="anthropic:claude-haiku-4-5",
                confidence=0.9,
                authenticity=_CLEAN_AUTH,
            )
        )
        with patch(
            "app.services.document_analysis.shadow_runner.build_document_analysis_provider",
            side_effect=_tiered_factory(triage, None),
        ):
            self._run(db_setup, tmp_path)

        triage.analyze.assert_called_once()
        assert self._inspection().shadow_provider_id == "anthropic:claude-haiku-4-5"
        assert self._events("shadow_analysis_skipped") == []
        sample = self._events("triage_skip_sample")
        assert len(sample) == 1
        assert sample[0].result == "pass"
        assert sample[0].payload["agreed"] is True

    def test_sampled_records_disagreement(self, monkeypatch, tmp_path, db_setup):
        _enable_triage_skip(monkeypatch, sampling_rate=1.0)
        self._set_clean()
        flagged_auth = {"concerns": [{"concern": "sello dudoso", "severity": "medium"}]}
        triage = _triage_provider(
            _tier_result(
                provider_id="anthropic:claude-haiku-4-5",
                confidence=0.9,
                authenticity=flagged_auth,
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

        sample = self._events("triage_skip_sample")
        assert len(sample) == 1
        assert sample[0].result == "warning"
        assert sample[0].payload["agreed"] is False
        assert sample[0].payload["ai_flagged"] is True

    def test_sampled_low_ai_match_is_disagreement(
        self, monkeypatch, tmp_path, db_setup
    ):
        # AI says "doesn't match the requirement" (conf < 0.5) with no
        # authenticity concern → counts as DISAGREEMENT (the normal path would
        # have escalated on low_match_confidence), not silent agreement.
        _enable_triage_skip(monkeypatch, sampling_rate=1.0)
        self._set_clean()
        triage = _triage_provider(
            _tier_result(
                provider_id="anthropic:claude-haiku-4-5",
                confidence=0.2,
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

        sample = self._events("triage_skip_sample")
        assert len(sample) == 1
        assert sample[0].result == "warning"
        assert sample[0].payload["agreed"] is False
        assert sample[0].payload["ai_low_match"] is True
        assert sample[0].payload["ai_flagged"] is False

    def test_sampled_provider_error_is_unavailable_not_disagreement(
        self, monkeypatch, tmp_path, db_setup
    ):
        # A provider outage must NOT be recorded as substantive disagreement —
        # it lands in its own ai_unavailable bucket with agreed=None.
        _enable_triage_skip(monkeypatch, sampling_rate=1.0)
        self._set_clean()
        triage = _triage_provider(
            _tier_result(
                provider_id="anthropic:claude-haiku-4-5",
                error="timeout",
                with_signals=False,
            )
        )
        with patch(
            "app.services.document_analysis.shadow_runner.build_document_analysis_provider",
            side_effect=_tiered_factory(triage, None),
        ):
            self._run(db_setup, tmp_path)

        sample = self._events("triage_skip_sample")
        assert len(sample) == 1
        assert sample[0].payload["ai_unavailable"] is True
        assert sample[0].payload["agreed"] is None
        assert sample[0].payload["ai_flagged"] is False


# ---------------------------------------------------------------------------
# A2 — Anthropic concurrency ceiling + circuit breaker
# ---------------------------------------------------------------------------


def _enable_breaker(
    monkeypatch,
    *,
    max_concurrent=4,
    acquire_timeout=0.0,
    threshold=3,
    cooldown=30.0,
):
    monkeypatch.setattr(settings, "ANTHROPIC_CONCURRENCY_BREAKER_ENABLED", True)
    monkeypatch.setattr(settings, "ANTHROPIC_MAX_CONCURRENT_REQUESTS", max_concurrent)
    monkeypatch.setattr(
        settings, "ANTHROPIC_CONCURRENCY_ACQUIRE_TIMEOUT_SECONDS", acquire_timeout
    )
    monkeypatch.setattr(settings, "ANTHROPIC_BREAKER_FAILURE_THRESHOLD", threshold)
    monkeypatch.setattr(settings, "ANTHROPIC_BREAKER_COOLDOWN_SECONDS", cooldown)


class _Boom(Exception):
    pass


class TestConcurrencyBreaker:
    @pytest.fixture(autouse=True)
    def _reset_breaker(self):
        from app.services.document_analysis.concurrency_breaker import (
            anthropic_concurrency_breaker,
        )

        anthropic_concurrency_breaker.reset()
        yield
        anthropic_concurrency_breaker.reset()

    def test_disabled_is_passthrough(self, monkeypatch):
        from app.services.document_analysis.concurrency_breaker import (
            anthropic_concurrency_breaker as b,
        )

        monkeypatch.setattr(settings, "ANTHROPIC_CONCURRENCY_BREAKER_ENABLED", False)
        # Many "failures" while disabled never open the breaker or build a sem.
        for _ in range(10):
            try:
                with b.guard():
                    raise _Boom()
            except _Boom:
                pass
        assert b._is_open() is False
        assert b._semaphore is None

    def test_semaphore_fast_fails_when_full(self, monkeypatch):
        from app.services.document_analysis.concurrency_breaker import (
            ConcurrencyExhaustedError,
        )
        from app.services.document_analysis.concurrency_breaker import (
            anthropic_concurrency_breaker as b,
        )

        _enable_breaker(monkeypatch, max_concurrent=1, acquire_timeout=0.0)
        held = b.guard()
        held.__enter__()  # occupy the only slot
        try:
            with pytest.raises(ConcurrencyExhaustedError):
                with b.guard():
                    pass
        finally:
            held.__exit__(None, None, None)
        # After release the slot is free again.
        with b.guard():
            pass

    def test_breaker_opens_after_consecutive_failures(self, monkeypatch):
        from app.services.document_analysis.concurrency_breaker import (
            BreakerOpenError,
        )
        from app.services.document_analysis.concurrency_breaker import (
            anthropic_concurrency_breaker as b,
        )

        _enable_breaker(monkeypatch, max_concurrent=4, threshold=3, cooldown=60.0)
        for _ in range(3):
            try:
                with b.guard():
                    raise _Boom()
            except _Boom:
                pass
        assert b._is_open() is True
        with pytest.raises(BreakerOpenError):
            with b.guard():
                raise AssertionError("body must not run while breaker is open")

    def test_success_resets_failure_count(self, monkeypatch):
        from app.services.document_analysis.concurrency_breaker import (
            anthropic_concurrency_breaker as b,
        )

        _enable_breaker(monkeypatch, threshold=3, cooldown=60.0)
        for _ in range(2):
            try:
                with b.guard():
                    raise _Boom()
            except _Boom:
                pass
        with b.guard():
            pass  # success → reset
        for _ in range(2):
            try:
                with b.guard():
                    raise _Boom()
            except _Boom:
                pass
        # Only 2 consecutive after the reset — below the threshold of 3.
        assert b._is_open() is False

    def test_concurrency_exhaustion_is_not_a_breaker_failure(self, monkeypatch):
        from app.services.document_analysis.concurrency_breaker import (
            ConcurrencyExhaustedError,
        )
        from app.services.document_analysis.concurrency_breaker import (
            anthropic_concurrency_breaker as b,
        )

        _enable_breaker(
            monkeypatch, max_concurrent=1, acquire_timeout=0.0, threshold=2
        )
        held = b.guard()
        held.__enter__()
        try:
            for _ in range(5):
                with pytest.raises(ConcurrencyExhaustedError):
                    with b.guard():
                        pass
        finally:
            held.__exit__(None, None, None)
        # Local backpressure never moves the upstream-failure counter.
        assert b._is_open() is False

    def test_cooldown_half_open_allows_trial(self, monkeypatch):
        from app.services.document_analysis import concurrency_breaker as mod

        b = mod.anthropic_concurrency_breaker
        _enable_breaker(monkeypatch, threshold=1, cooldown=30.0)
        clock = {"t": 1000.0}
        monkeypatch.setattr(mod.time, "monotonic", lambda: clock["t"])
        try:
            with b.guard():
                raise _Boom()
        except _Boom:
            pass
        assert b._is_open() is True
        clock["t"] += 31.0  # advance past the cooldown window
        assert b._is_open() is False  # half-open
        with b.guard():
            pass  # trial call admitted

    # -- integration through the provider --------------------------------

    def test_provider_returns_breaker_open(self, monkeypatch, tmp_path):
        client = MagicMock()
        client.with_options.return_value.messages.create.side_effect = _Boom()
        provider = _build_provider_with_mock_client(monkeypatch, client)
        _enable_breaker(monkeypatch, threshold=1, cooldown=60.0)

        r1 = provider.analyze(
            pdf_path=_blank_pdf_path(tmp_path),
            requirement_code="REC-SAT-CSF-2026",
            requirement_name="CSF",
            institution_code="sat",
            period_code="2026-01",
        )
        assert r1.error.startswith("provider_error")

        create = client.with_options.return_value.messages.create
        create.reset_mock()
        r2 = provider.analyze(
            pdf_path=_blank_pdf_path(tmp_path),
            requirement_code="REC-SAT-CSF-2026",
            requirement_name="CSF",
            institution_code="sat",
            period_code="2026-01",
        )
        assert r2.error == "breaker_open"
        create.assert_not_called()  # short-circuited, no upstream call

    def test_provider_returns_concurrency_exhausted(self, monkeypatch, tmp_path):
        from app.services.document_analysis.concurrency_breaker import (
            anthropic_concurrency_breaker as b,
        )

        client = MagicMock()
        client.with_options.return_value.messages.create.return_value = (
            _mock_anthropic_response()
        )
        provider = _build_provider_with_mock_client(monkeypatch, client)
        _enable_breaker(monkeypatch, max_concurrent=1, acquire_timeout=0.0)

        sem = b._get_semaphore()
        sem.acquire()  # occupy the only slot from "another request"
        try:
            result = provider.analyze(
                pdf_path=_blank_pdf_path(tmp_path),
                requirement_code="REC-SAT-CSF-2026",
                requirement_name="CSF",
                institution_code="sat",
                period_code="2026-01",
            )
        finally:
            sem.release()
        assert result.error == "concurrency_exhausted"
        client.with_options.return_value.messages.create.assert_not_called()

    def test_provider_passthrough_when_disabled(self, monkeypatch, tmp_path):
        from app.services.document_analysis.concurrency_breaker import (
            anthropic_concurrency_breaker as b,
        )

        monkeypatch.setattr(
            settings, "ANTHROPIC_CONCURRENCY_BREAKER_ENABLED", False
        )
        client = MagicMock()
        client.with_options.return_value.messages.create.side_effect = _Boom()
        provider = _build_provider_with_mock_client(monkeypatch, client)
        result = provider.analyze(
            pdf_path=_blank_pdf_path(tmp_path),
            requirement_code="REC-SAT-CSF-2026",
            requirement_name="CSF",
            institution_code="sat",
            period_code="2026-01",
        )
        # Categorised normally; breaker untouched (no sem, not open).
        assert result.error.startswith("provider_error")
        assert b._is_open() is False
        assert b._semaphore is None

    # -- review fixes: failure-accounting discrimination -----------------

    def test_predicate_neutral_error_does_not_count(self, monkeypatch):
        from app.services.document_analysis.concurrency_breaker import (
            anthropic_concurrency_breaker as b,
        )

        _enable_breaker(monkeypatch, threshold=1, cooldown=60.0)
        for _ in range(3):
            try:
                with b.guard(is_failure=lambda exc: False):
                    raise _Boom()
            except _Boom:
                pass
        # A predicate-neutral error never moves the breaker.
        assert b._is_open() is False
        assert b._consecutive_failures == 0

    def test_base_exception_is_breaker_neutral(self, monkeypatch):
        from app.services.document_analysis.concurrency_breaker import (
            anthropic_concurrency_breaker as b,
        )

        class _BaseBoom(BaseException):
            pass

        _enable_breaker(monkeypatch, threshold=1, cooldown=60.0)
        try:
            with b.guard():
                raise _BaseBoom()
        except _BaseBoom:
            pass
        # Cancellation/shutdown-class unwinds never move the failure counter.
        assert b._consecutive_failures == 0
        assert b._is_open() is False

    def test_enabled_snapshot_off_to_on_does_not_record(self, monkeypatch):
        from app.services.document_analysis.concurrency_breaker import (
            anthropic_concurrency_breaker as b,
        )

        monkeypatch.setattr(
            settings, "ANTHROPIC_CONCURRENCY_BREAKER_ENABLED", False
        )
        guard = b.guard()
        guard.__enter__()  # snapshots _active=False (pass-through)
        # Operator flips the flag ON mid-call.
        monkeypatch.setattr(
            settings, "ANTHROPIC_CONCURRENCY_BREAKER_ENABLED", True
        )
        guard.__exit__(_Boom, _Boom(), None)
        # The call never participated in admission → it must not record.
        assert b._consecutive_failures == 0
        assert b._is_open() is False

    def test_provider_4xx_does_not_open_breaker(self, monkeypatch, tmp_path):
        from app.services.document_analysis.concurrency_breaker import (
            anthropic_concurrency_breaker as b,
        )

        class _BadRequest(Exception):
            status_code = 400

        client = MagicMock()
        client.with_options.return_value.messages.create.side_effect = _BadRequest()
        provider = _build_provider_with_mock_client(monkeypatch, client)
        _enable_breaker(monkeypatch, threshold=1, cooldown=60.0)

        create = client.with_options.return_value.messages.create
        for _ in range(3):
            result = provider.analyze(
                pdf_path=_blank_pdf_path(tmp_path),
                requirement_code="REC-SAT-CSF-2026",
                requirement_name="CSF",
                institution_code="sat",
                period_code="2026-01",
            )
            # The real, fixable error stays visible — not masked as breaker_open.
            assert result.error == "provider_error:_BadRequest"
        # A deterministic 4xx never opens the breaker; every call still tried.
        assert b._is_open() is False
        assert create.call_count == 3

    def test_provider_5xx_opens_breaker(self, monkeypatch, tmp_path):
        from app.services.document_analysis.concurrency_breaker import (
            anthropic_concurrency_breaker as b,
        )

        class _ServerError(Exception):
            status_code = 503

        client = MagicMock()
        client.with_options.return_value.messages.create.side_effect = _ServerError()
        provider = _build_provider_with_mock_client(monkeypatch, client)
        _enable_breaker(monkeypatch, threshold=1, cooldown=60.0)

        r1 = provider.analyze(
            pdf_path=_blank_pdf_path(tmp_path),
            requirement_code="REC-SAT-CSF-2026",
            requirement_name="CSF",
            institution_code="sat",
            period_code="2026-01",
        )
        assert r1.error == "provider_error:_ServerError"
        # 5xx IS an upstream-health signal → breaker opens; next call fast-fails.
        assert b._is_open() is True
        create = client.with_options.return_value.messages.create
        create.reset_mock()
        r2 = provider.analyze(
            pdf_path=_blank_pdf_path(tmp_path),
            requirement_code="REC-SAT-CSF-2026",
            requirement_name="CSF",
            institution_code="sat",
            period_code="2026-01",
        )
        assert r2.error == "breaker_open"
        create.assert_not_called()


# ---------------------------------------------------------------------------
# A3 — async provider path (DOCUMENT_ANALYSIS_ASYNC_PROVIDER_ENABLED)
# ---------------------------------------------------------------------------


def _async_provider(provider_id, result):
    p = MagicMock()
    p.provider_id = provider_id
    p.analyze_async = AsyncMock(return_value=result)
    return p


def _async_tiered_factory(triage, escalation):
    def build(tier: str = "triage"):
        return triage if tier == "triage" else escalation

    return build


class TestAsyncBreakerGuard:
    @pytest.fixture(autouse=True)
    def _reset_breaker(self):
        from app.services.document_analysis.concurrency_breaker import (
            anthropic_concurrency_breaker,
        )

        anthropic_concurrency_breaker.reset()
        yield
        anthropic_concurrency_breaker.reset()

    def test_async_guard_breaker_open(self, monkeypatch):
        from app.services.document_analysis.concurrency_breaker import (
            BreakerOpenError,
        )
        from app.services.document_analysis.concurrency_breaker import (
            anthropic_concurrency_breaker as b,
        )

        _enable_breaker(monkeypatch, threshold=1, cooldown=60.0)
        try:
            with b.guard():
                raise _Boom()
        except _Boom:
            pass
        assert b._is_open() is True

        async def go():
            async with b.async_guard():
                raise AssertionError("body must not run while breaker is open")

        with pytest.raises(BreakerOpenError):
            asyncio.run(go())

    def test_async_guard_concurrency_exhausted(self, monkeypatch):
        from app.services.document_analysis.concurrency_breaker import (
            ConcurrencyExhaustedError,
        )
        from app.services.document_analysis.concurrency_breaker import (
            anthropic_concurrency_breaker as b,
        )

        _enable_breaker(monkeypatch, max_concurrent=1, acquire_timeout=0.0)
        sem = b._get_semaphore()
        sem.acquire()

        async def go():
            async with b.async_guard():
                pass

        try:
            with pytest.raises(ConcurrencyExhaustedError):
                asyncio.run(go())
        finally:
            sem.release()

    def test_async_guard_records_failure_and_opens(self, monkeypatch):
        from app.services.document_analysis.concurrency_breaker import (
            anthropic_concurrency_breaker as b,
        )

        _enable_breaker(monkeypatch, threshold=1, cooldown=60.0)

        async def go():
            async with b.async_guard():
                raise _Boom()

        try:
            asyncio.run(go())
        except _Boom:
            pass
        assert b._is_open() is True

    def test_async_guard_disabled_passthrough(self, monkeypatch):
        from app.services.document_analysis.concurrency_breaker import (
            anthropic_concurrency_breaker as b,
        )

        monkeypatch.setattr(
            settings, "ANTHROPIC_CONCURRENCY_BREAKER_ENABLED", False
        )
        ran = []

        async def go():
            async with b.async_guard():
                ran.append(1)

        asyncio.run(go())
        assert ran == [1]
        assert b._semaphore is None

    def test_async_guard_cancellation_does_not_leak_permit(self, monkeypatch):
        from app.services.document_analysis.concurrency_breaker import (
            anthropic_concurrency_breaker as b,
        )

        _enable_breaker(monkeypatch, max_concurrent=1, acquire_timeout=10.0)
        sem = b._get_semaphore()
        sem.acquire()  # saturate: 0 permits free, so the guard must poll-wait

        async def waiter():
            async with b.async_guard():
                pass

        async def driver():
            task = asyncio.ensure_future(waiter())
            await asyncio.sleep(0.12)  # let it poll a couple of times
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        asyncio.run(driver())
        # The cancelled waiter never held a permit (non-blocking poll, no orphan
        # thread). Releasing the saturating permit leaves EXACTLY one free.
        sem.release()
        assert sem.acquire(blocking=False) is True
        assert sem.acquire(blocking=False) is False
        sem.release()


class TestAnalyzeAsync:
    @pytest.fixture(autouse=True)
    def _reset_breaker(self):
        from app.services.document_analysis.concurrency_breaker import (
            anthropic_concurrency_breaker,
        )

        anthropic_concurrency_breaker.reset()
        yield
        anthropic_concurrency_breaker.reset()

    def _provider(self, monkeypatch, async_client):
        monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-test")
        provider = AnthropicDocumentAnalysisProvider(api_key="sk-test")
        # The async client's httpx pool must be closed after every call.
        async_client.close = AsyncMock()
        provider._async_client = async_client
        return provider

    def test_happy_path_awaits_async_client(self, monkeypatch, tmp_path):
        client = MagicMock()
        client.with_options.return_value.messages.create = AsyncMock(
            return_value=_mock_anthropic_response()
        )
        provider = self._provider(monkeypatch, client)
        result = asyncio.run(
            provider.analyze_async(
                pdf_path=_blank_pdf_path(tmp_path),
                requirement_code="REC-SAT-CSF-2026",
                requirement_name="CSF",
                institution_code="sat",
                period_code="2026-01",
            )
        )
        assert result.error is None
        assert result.signals.detected_institution == "sat"
        client.with_options.return_value.messages.create.assert_awaited_once()
        # The httpx pool is closed (no per-run connection-pool leak) and the
        # cached handle is dropped.
        client.close.assert_awaited_once()
        assert provider._async_client is None

    def test_async_client_closed_even_on_error(self, monkeypatch, tmp_path):
        client = MagicMock()
        client.with_options.return_value.messages.create = AsyncMock(
            side_effect=RuntimeError("boom")
        )
        provider = self._provider(monkeypatch, client)
        result = asyncio.run(
            provider.analyze_async(
                pdf_path=_blank_pdf_path(tmp_path),
                requirement_code="REC-SAT-CSF-2026",
                requirement_name="CSF",
                institution_code="sat",
                period_code="2026-01",
            )
        )
        assert result.error.startswith("provider_error")
        client.close.assert_awaited_once()

    def test_error_path_returns_failure(self, monkeypatch, tmp_path):
        client = MagicMock()
        client.with_options.return_value.messages.create = AsyncMock(
            side_effect=RuntimeError("boom")
        )
        provider = self._provider(monkeypatch, client)
        result = asyncio.run(
            provider.analyze_async(
                pdf_path=_blank_pdf_path(tmp_path),
                requirement_code="REC-SAT-CSF-2026",
                requirement_name="CSF",
                institution_code="sat",
                period_code="2026-01",
            )
        )
        assert result.signals is None
        assert result.error.startswith("provider_error")

    def test_preflight_failure_skips_call(self, monkeypatch, tmp_path):
        client = MagicMock()
        client.with_options.return_value.messages.create = AsyncMock()
        provider = self._provider(monkeypatch, client)
        result = asyncio.run(
            provider.analyze_async(
                pdf_path=tmp_path / "missing.pdf",
                requirement_code="REC-SAT-CSF-2026",
                requirement_name="CSF",
                institution_code="sat",
                period_code="2026-01",
            )
        )
        assert result.error == "unsupported_size_or_type"
        client.with_options.return_value.messages.create.assert_not_awaited()


class TestAsyncShadowRunner(_ShadowDbSetupMixin):
    def _inspection(self):
        from app.db.session import SessionLocal
        from app.models import DocumentInspection

        db = SessionLocal()
        try:
            return db.query(DocumentInspection).first()
        finally:
            db.close()

    def test_async_runner_persists_shadow_columns(
        self, monkeypatch, tmp_path, db_setup
    ):
        from app.services.document_analysis.shadow_runner import (
            run_shadow_analysis_async,
        )

        result = _tier_result(
            provider_id="anthropic:claude-haiku-4-5",
            confidence=0.9,
            authenticity=_CLEAN_AUTH,
        )
        triage = _async_provider("anthropic:claude-haiku-4-5", result)
        with patch(
            "app.services.document_analysis.shadow_runner.build_document_analysis_provider",
            side_effect=_async_tiered_factory(triage, None),
        ):
            asyncio.run(
                run_shadow_analysis_async(
                    document_id=db_setup["document_id"],
                    submission_id=db_setup["submission_id"],
                    pdf_path=str(_blank_pdf_path(tmp_path)),
                    requirement_code="REC-SAT-CSF-2026",
                    requirement_name="CSF",
                    institution_code="sat",
                    period_code="2026-01",
                    org_id="cli-1",
                )
            )

        triage.analyze_async.assert_awaited_once()
        insp = self._inspection()
        assert insp.shadow_provider_id == "anthropic:claude-haiku-4-5"
        assert insp.shadow_completed_at is not None
        assert insp.shadow_error is None

    def test_async_runner_honours_triage_skip(self, monkeypatch, tmp_path, db_setup):
        from app.services.document_analysis.shadow_runner import (
            run_shadow_analysis_async,
        )

        _enable_triage_skip(monkeypatch, sampling_rate=0.0)
        # Put the inspection into the clean+aligned eligible state.
        from app.db.session import SessionLocal
        from app.models import DocumentInspection

        db = SessionLocal()
        try:
            insp = db.query(DocumentInspection).first()
            for key, value in TestTriageSkipDecision._CLEAN.items():
                setattr(insp, key, value)
            db.commit()
        finally:
            db.close()

        triage = _async_provider(
            "anthropic:claude-haiku-4-5",
            _tier_result(provider_id="anthropic:claude-haiku-4-5"),
        )
        with patch(
            "app.services.document_analysis.shadow_runner.build_document_analysis_provider",
            side_effect=_async_tiered_factory(triage, None),
        ):
            asyncio.run(
                run_shadow_analysis_async(
                    document_id=db_setup["document_id"],
                    submission_id=db_setup["submission_id"],
                    pdf_path=str(_blank_pdf_path(tmp_path)),
                    requirement_code="REC-SAT-CSF-2026",
                    requirement_name="CSF",
                    institution_code="sat",
                    period_code="2026-01",
                    org_id="cli-1",
                )
            )

        triage.analyze_async.assert_not_awaited()
        insp = self._inspection()
        assert insp.shadow_provider_id is None
        assert insp.shadow_signals["_triage_skip"]["reason"] == "heuristic_clean_aligned"


class TestAsyncDispatch:
    def test_shadow_runner_selector(self, monkeypatch):
        from app.services import submission_service as ss

        monkeypatch.setattr(
            settings, "DOCUMENT_ANALYSIS_ASYNC_PROVIDER_ENABLED", True
        )
        assert ss._shadow_runner_for_background() is ss.run_shadow_analysis_async
        monkeypatch.setattr(
            settings, "DOCUMENT_ANALYSIS_ASYNC_PROVIDER_ENABLED", False
        )
        assert ss._shadow_runner_for_background() is ss.run_shadow_analysis

    def test_finalize_async_awaits_shadow_then_cleans_up(self, monkeypatch):
        from app.services import submission_service as ss

        fake_args = {
            "document_id": "d",
            "submission_id": "s",
            "pdf_path": "/tmp/x.pdf",
            "requirement_code": None,
            "requirement_name": "r",
            "institution_code": "i",
            "period_code": "p",
            "org_id": "o",
        }
        monkeypatch.setattr(
            ss,
            "finalize_intake_submission_background",
            lambda **kw: (fake_args, Path("/tmp/x.pdf")),
        )
        awaited = []

        async def fake_runner(**kw):
            awaited.append(kw)

        monkeypatch.setattr(ss, "run_shadow_analysis_async", fake_runner)
        cleaned = []
        monkeypatch.setattr(
            ss, "_cleanup_materialized_temp", lambda p: cleaned.append(p)
        )
        asyncio.run(
            ss.finalize_intake_submission_background_async(
                submission_id="s", storage_key="k", intake_source="x"
            )
        )
        assert awaited == [fake_args]
        assert cleaned == [Path("/tmp/x.pdf")]

    def test_finalize_async_noop_when_core_returns_none(self, monkeypatch):
        from app.services import submission_service as ss

        monkeypatch.setattr(
            ss, "finalize_intake_submission_background", lambda **kw: None
        )
        awaited = []

        async def fake_runner(**kw):
            awaited.append(kw)

        monkeypatch.setattr(ss, "run_shadow_analysis_async", fake_runner)
        cleaned = []
        monkeypatch.setattr(
            ss, "_cleanup_materialized_temp", lambda p: cleaned.append(p)
        )
        asyncio.run(
            ss.finalize_intake_submission_background_async(
                submission_id="s", storage_key="k", intake_source="x"
            )
        )
        assert awaited == []
        assert cleaned == []


# ---------------------------------------------------------------------------
# B3 — expediente-first batching (DOCUMENT_ANALYSIS_BATCH_ESCALATION_ENABLED)
# ---------------------------------------------------------------------------


class TestBatchEscalation(_ShadowDbSetupMixin):
    def _enable(self, monkeypatch, *, batch=True, expediente=True, debounce=6):
        monkeypatch.setattr(
            settings, "DOCUMENT_ANALYSIS_BATCH_ESCALATION_ENABLED", batch
        )
        monkeypatch.setattr(settings, "DOCUMENT_ANALYSIS_EXPEDIENTE_ENABLED", expediente)
        monkeypatch.setattr(
            settings, "DOCUMENT_ANALYSIS_EXPEDIENTE_DEBOUNCE_HOURS", debounce
        )

    def _seed_recent_assessment(self, db_setup):
        from app.db.session import SessionLocal
        from app.models import ExpedienteAssessment

        db = SessionLocal()
        try:
            db.add(
                ExpedienteAssessment(
                    client_id="cli-1",
                    vendor_id="ven-1",
                    period_id="per-1",
                    error=None,
                )
            )
            db.commit()
        finally:
            db.close()

    def _add_sibling_doc(self, submission_id):
        from app.db.session import SessionLocal
        from app.models import Document

        db = SessionLocal()
        try:
            db.add(
                Document(
                    submission_id=submission_id,
                    storage_key="local/test2.pdf",
                    original_filename="test2.pdf",
                    size_bytes=1024,
                    sha256="beefdead",
                    status="pendiente_revision",
                )
            )
            db.commit()
        finally:
            db.close()

    def _decide(self, submission_id):
        from app.services.document_analysis.shadow_runner import (
            _should_batch_escalation,
        )

        return _should_batch_escalation(submission_id)

    def _inspection(self):
        from app.db.session import SessionLocal
        from app.models import DocumentInspection

        db = SessionLocal()
        try:
            return db.query(DocumentInspection).first()
        finally:
            db.close()

    # -- predicate ------------------------------------------------------

    def test_predicate_flag_off(self, monkeypatch, db_setup):
        self._enable(monkeypatch, batch=False)
        self._add_sibling_doc(db_setup["submission_id"])
        assert self._decide(db_setup["submission_id"]) is False

    def test_predicate_requires_expediente(self, monkeypatch, db_setup):
        # Never defer the deep pass when there is no expediente to catch it.
        self._enable(monkeypatch, batch=True, expediente=False)
        self._add_sibling_doc(db_setup["submission_id"])
        assert self._decide(db_setup["submission_id"]) is False

    def test_predicate_single_doc_not_a_bundle(self, monkeypatch, db_setup):
        self._enable(monkeypatch)
        assert self._decide(db_setup["submission_id"]) is False  # only 1 document

    def test_predicate_bundle(self, monkeypatch, db_setup):
        self._enable(monkeypatch)
        self._add_sibling_doc(db_setup["submission_id"])
        assert self._decide(db_setup["submission_id"]) is True

    def test_predicate_debounce_disabled_falls_back(self, monkeypatch, db_setup):
        # Without a debounce window batching would fan out one expediente per
        # doc → don't batch.
        self._enable(monkeypatch, debounce=0)
        self._add_sibling_doc(db_setup["submission_id"])
        assert self._decide(db_setup["submission_id"]) is False

    def test_predicate_recently_assessed_falls_back(self, monkeypatch, db_setup):
        # The load-bearing safety guard: a recent expediente assessment means the
        # after-deep-run trigger would be DEBOUNCED, so deferring would lose the
        # deep pass → don't defer, run the per-doc escalation.
        self._enable(monkeypatch)
        self._add_sibling_doc(db_setup["submission_id"])
        self._seed_recent_assessment(db_setup)
        assert self._decide(db_setup["submission_id"]) is False

    # -- integration ----------------------------------------------------

    def _run(self, db_setup, tmp_path, triage, escalation):
        from app.services.document_analysis.shadow_runner import run_shadow_analysis

        with patch(
            "app.services.document_analysis.shadow_runner.build_document_analysis_provider",
            side_effect=_tiered_factory(triage, escalation),
        ):
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

    def _flagged_triage(self):
        return _triage_provider(
            _tier_result(
                provider_id="anthropic:claude-haiku-4-5",
                authenticity={"concerns": [{"concern": "sello", "severity": "medium"}]},
            )
        )

    def test_bundle_skips_per_doc_escalation_and_triggers_expediente(
        self, monkeypatch, tmp_path, db_setup
    ):
        self._enable(monkeypatch)
        self._add_sibling_doc(db_setup["submission_id"])
        exped = MagicMock()
        monkeypatch.setattr(
            "app.services.document_analysis.shadow_runner.run_expediente_assessment",
            exped,
        )
        triage = self._flagged_triage()
        escalation = _escalation_provider(
            _tier_result(provider_id="anthropic:claude-sonnet-4-6")
        )
        self._run(db_setup, tmp_path, triage, escalation)

        # Per-doc deep pass skipped; the single expediente pass is triggered.
        escalation.analyze.assert_not_called()
        exped.assert_called_once()
        tiers = self._inspection().shadow_signals["_tiers"]
        assert tiers["escalation"]["skipped"] == "batched_to_expediente"

    def test_single_doc_still_runs_per_doc_escalation(
        self, monkeypatch, tmp_path, db_setup
    ):
        # Batch flag on, but a single-doc submission is NOT a bundle → the
        # per-doc escalation runs exactly as before (no regression).
        self._enable(monkeypatch)
        monkeypatch.setattr(
            "app.services.document_analysis.shadow_runner.run_expediente_assessment",
            MagicMock(),
        )
        triage = self._flagged_triage()
        escalation = _escalation_provider(
            _tier_result(provider_id="anthropic:claude-sonnet-4-6", authenticity=_CLEAN_AUTH)
        )
        self._run(db_setup, tmp_path, triage, escalation)

        escalation.analyze.assert_called_once()
        tiers = self._inspection().shadow_signals["_tiers"]
        assert "skipped" not in tiers["escalation"]

    def test_flag_off_bundle_runs_per_doc_escalation(
        self, monkeypatch, tmp_path, db_setup
    ):
        # Default-OFF: a bundle still escalates per-document (unchanged).
        self._enable(monkeypatch, batch=False)
        self._add_sibling_doc(db_setup["submission_id"])
        monkeypatch.setattr(
            "app.services.document_analysis.shadow_runner.run_expediente_assessment",
            MagicMock(),
        )
        triage = self._flagged_triage()
        escalation = _escalation_provider(
            _tier_result(provider_id="anthropic:claude-sonnet-4-6", authenticity=_CLEAN_AUTH)
        )
        self._run(db_setup, tmp_path, triage, escalation)
        escalation.analyze.assert_called_once()

    def test_bundle_with_recent_assessment_runs_per_doc(
        self, monkeypatch, tmp_path, db_setup
    ):
        # The deep-analysis-loss guard, end to end: a bundle whose expediente
        # would be DEBOUNCED must NOT defer — the per-doc escalation runs so the
        # document is never left with only triage.
        self._enable(monkeypatch)
        self._add_sibling_doc(db_setup["submission_id"])
        self._seed_recent_assessment(db_setup)
        monkeypatch.setattr(
            "app.services.document_analysis.shadow_runner.run_expediente_assessment",
            MagicMock(),
        )
        triage = self._flagged_triage()
        escalation = _escalation_provider(
            _tier_result(provider_id="anthropic:claude-sonnet-4-6", authenticity=_CLEAN_AUTH)
        )
        self._run(db_setup, tmp_path, triage, escalation)
        # Fell back to the per-doc deep pass (no silent loss).
        escalation.analyze.assert_called_once()
        tiers = self._inspection().shadow_signals["_tiers"]
        assert "skipped" not in tiers["escalation"]
