"""Phase 2 — expediente-level situational assessment tests.

Covers the pure context assembly, the current-submission (supersede leaf)
logic, tolerant normalisation of the model's output, the structured-output
schema, the mocked LLM pass, and the entry-point gating. No test makes a
real network call or requires a seeded database — the ORM-dependent loader
(`_load_context`) is exercised via its pure inputs.
"""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from app.core.config import settings
from app.services.document_analysis.expediente import (
    _EXPEDIENTE_OUTPUT_FORMAT,
    _current_submissions,
    analyze_expediente,
    build_expediente_context,
    normalise_assessment,
    run_expediente_assessment,
)


def _mock_expediente_response(payload: dict | None = None) -> Any:
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = json.dumps(
        payload
        or {
            "coherence": "minor_issues",
            "summary_for_reviewer": "El expediente es mayormente coherente.",
            "findings": [
                {
                    "code": "headcount_inconsistency",
                    "severity": "medium",
                    "detail_es": "El IMSS reporta 3 trabajadores; el contrato estima 12.",
                    "evidence": "IMSS: 3; contrato.trabajadores_estimados: 12.",
                }
            ],
            "coverage_gaps": [],
        }
    )
    response = MagicMock()
    response.content = [text_block]
    response.stop_reason = "end_turn"
    response.model = "claude-sonnet-4-6"
    usage = MagicMock()
    usage.model_dump.return_value = {"input_tokens": 800, "output_tokens": 200}
    response.usage = usage
    return response


def _client_returning(response: Any) -> MagicMock:
    client = MagicMock()
    client.with_options.return_value.messages.create.return_value = response
    return client


class TestContextAssembly:
    def test_build_context_includes_contract_and_documents(self):
        vendor = SimpleNamespace(name="ACME SA", rfc="ABC010101AB1", repse_id="REP123")
        client = SimpleNamespace(name="Cliente Demo", rfc="XAXX010101000")
        period = SimpleNamespace(period_key="2026-M04", code="abril 2026")
        contract = SimpleNamespace(
            service_object="Servicios de limpieza",
            registered_activity="Limpieza de inmuebles",
            repse_folio="ABC01/2024/1234",
            estimated_workers=12,
            work_location="CDMX",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        ctx = build_expediente_context(
            vendor=vendor,
            client=client,
            period=period,
            contract=contract,
            document_entries=[{"document_id": "d1"}],
        )
        assert ctx["proveedor"]["rfc"] == "ABC010101AB1"
        assert ctx["cliente"]["nombre"] == "Cliente Demo"
        assert ctx["periodo"]["period_key"] == "2026-M04"
        assert ctx["contrato"]["trabajadores_estimados"] == 12
        assert ctx["contrato"]["vigencia"]["inicio"] == "2026-01-01"
        assert ctx["contrato"]["vigencia"]["fin"] == "2026-12-31"
        assert ctx["documentos"] == [{"document_id": "d1"}]

    def test_build_context_handles_no_contract(self):
        vendor = SimpleNamespace(name="ACME", rfc="ABC010101AB1", repse_id=None)
        client = SimpleNamespace(name="Cliente", rfc=None)
        period = SimpleNamespace(period_key="2026-M04", code="abril 2026")
        ctx = build_expediente_context(
            vendor=vendor,
            client=client,
            period=period,
            contract=None,
            document_entries=[],
        )
        assert ctx["contrato"] is None
        assert ctx["documentos"] == []

    def test_current_submissions_keeps_leaf_of_chain(self):
        first = SimpleNamespace(id="a", supersedes_submission_id=None)
        replacement = SimpleNamespace(id="b", supersedes_submission_id="a")
        unrelated = SimpleNamespace(id="c", supersedes_submission_id=None)
        current = _current_submissions([first, replacement, unrelated])
        ids = {s.id for s in current}
        assert ids == {"b", "c"}  # "a" was superseded by "b"


class TestNormalisation:
    def test_normalise_defaults_bad_enums(self):
        result = normalise_assessment(
            {
                "coherence": "totally-bogus",
                "summary_for_reviewer": "  resumen  ",
                "findings": [
                    {
                        "code": "made_up_code",
                        "severity": "apocalyptic",
                        "detail_es": "algo",
                        "evidence": "x",
                    }
                ],
                "coverage_gaps": [],
            }
        )
        assert result["coherence"] == "indeterminate"
        assert result["summary_for_reviewer"] == "resumen"
        assert result["findings"][0]["code"] == "other"
        assert result["findings"][0]["severity"] == "medium"

    def test_normalise_drops_empty_findings_and_gaps(self):
        result = normalise_assessment(
            {
                "coherence": "coherent",
                "summary_for_reviewer": "",
                "findings": [
                    {"code": "other", "severity": "low", "detail_es": "", "evidence": ""},
                    "not-a-dict",
                ],
                "coverage_gaps": [
                    {"requirement_code": "REC-X", "detail_es": ""},
                    {"requirement_code": "REC-Y", "detail_es": "Falta el pago IMSS."},
                ],
            }
        )
        assert result["coherence"] == "coherent"
        assert result["summary_for_reviewer"] is None
        assert result["findings"] == []  # empty detail dropped
        assert len(result["coverage_gaps"]) == 1
        assert result["coverage_gaps"][0]["requirement_code"] == "REC-Y"

    def test_output_format_schema_shape(self):
        schema = _EXPEDIENTE_OUTPUT_FORMAT["schema"]
        assert set(schema["required"]) == {
            "coherence",
            "summary_for_reviewer",
            "findings",
            "coverage_gaps",
        }
        assert schema["properties"]["coherence"]["enum"] == [
            "coherent",
            "minor_issues",
            "incoherent",
            "indeterminate",
        ]
        assert schema["additionalProperties"] is False


class TestAnalyzeExpediente:
    def test_parses_structured_assessment(self):
        client = _client_returning(_mock_expediente_response())
        assessment, raw_meta, error = analyze_expediente(client, {"documentos": []})
        assert error is None
        assert assessment["coherence"] == "minor_issues"
        assert assessment["findings"][0]["code"] == "headcount_inconsistency"
        assert raw_meta["model"] == "claude-sonnet-4-6"
        # Reasoning + structured outputs are requested.
        create_kwargs = client.with_options.return_value.messages.create.call_args.kwargs
        assert create_kwargs["thinking"] == {"type": "adaptive"}
        assert create_kwargs["output_config"]["format"]["type"] == "json_schema"

    def test_timeout_is_categorised(self):
        class _APITimeoutError(Exception):
            pass

        client = MagicMock()
        client.with_options.return_value.messages.create.side_effect = (
            _APITimeoutError("timed out")
        )
        assessment, _raw_meta, error = analyze_expediente(client, {})
        assert assessment is None
        assert error == "timeout"

    def test_non_json_text_is_malformed(self):
        bad = _mock_expediente_response()
        bad.content[-1].text = "no pude analizar el expediente"
        client = _client_returning(bad)
        assessment, _raw_meta, error = analyze_expediente(client, {})
        assert assessment is None
        assert error == "malformed_response"


class TestEntryPointGating:
    def test_disabled_is_noop(self, monkeypatch):
        monkeypatch.setattr(settings, "DOCUMENT_ANALYSIS_EXPEDIENTE_ENABLED", False)
        # Should return without touching the DB or the provider.
        run_expediente_assessment(
            client_id="c", vendor_id="v", period_id="p", org_id="o"
        )

    def test_provider_disabled_is_noop(self, monkeypatch):
        monkeypatch.setattr(settings, "DOCUMENT_ANALYSIS_EXPEDIENTE_ENABLED", True)
        monkeypatch.setattr(settings, "DOCUMENT_ANALYSIS_PROVIDER", "disabled")
        run_expediente_assessment(
            client_id="c", vendor_id="v", period_id="p", org_id="o"
        )

    def test_escalation_cap_skips_before_db(self, monkeypatch):
        monkeypatch.setattr(settings, "DOCUMENT_ANALYSIS_EXPEDIENTE_ENABLED", True)
        monkeypatch.setattr(settings, "DOCUMENT_ANALYSIS_PROVIDER", "anthropic")
        monkeypatch.setattr(
            "app.services.document_analysis.expediente.check_org_escalation_daily_quota",
            lambda org_id: False,
        )
        # If the cap gate works, SessionLocal is never constructed.
        sentinel = MagicMock(side_effect=AssertionError("DB must not be touched"))
        monkeypatch.setattr(
            "app.services.document_analysis.expediente.SessionLocal", sentinel
        )
        run_expediente_assessment(
            client_id="c", vendor_id="v", period_id="p", org_id="o"
        )
        sentinel.assert_not_called()
