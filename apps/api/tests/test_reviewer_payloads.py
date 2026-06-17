"""Phase 3 — reviewer detail payload builders.

Unit tests for the two reviewer payload helpers that surface the
comprehension (Phase 1) and the expediente situational assessment
(Phase 2) on the reviewer detail endpoint. Self-contained: the
expediente builder runs against a standalone in-memory engine with only
the ``ExpedienteAssessment`` table (no FK seeding required).
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.v1.reviewer import (
    _build_expediente_payload,
    _build_shadow_analysis_payload,
)
from app.db.base import Base
from app.models import ExpedienteAssessment


def _inspection(shadow_signals) -> SimpleNamespace:  # noqa: ANN001
    return SimpleNamespace(
        detected_institution="sat",
        detected_document_type="csf",
        detected_rfcs=["ABCD010203XYZ"],
        expected_rfc="ABCD010203XYZ",
        rfc_alignment="match",
        detected_dates=["2026-04-01"],
        period_mentions=[],
        requirement_match_confidence=0.9,
        mismatch_reason=None,
        updated_at=None,
        shadow_provider_id="anthropic:claude-sonnet-4-6",
        shadow_prompt_version="csf_sat.v3",
        shadow_completed_at=None,
        shadow_latency_ms=1200,
        shadow_error=None,
        shadow_confidence=0.9,
        shadow_signals=shadow_signals,
    )


class TestShadowComprehensionSurfacing:
    def test_comprehension_is_surfaced_explicitly(self):
        comprehension = {
            "purpose": "CSF del proveedor.",
            "obligation_satisfaction": {
                "verdict": "satisfied",
                "confidence": 0.9,
                "reasoning": "RFC coincide y es reciente.",
            },
        }
        payload = _build_shadow_analysis_payload(
            _inspection({"comprehension": comprehension, "anomaly_codes": []})
        )
        assert payload["shadow"]["comprehension"] == comprehension

    def test_comprehension_none_when_absent(self):
        payload = _build_shadow_analysis_payload(
            _inspection({"anomaly_codes": []})  # no comprehension key
        )
        assert payload["shadow"]["comprehension"] is None

    def test_comprehension_none_when_signals_missing(self):
        payload = _build_shadow_analysis_payload(_inspection(None))
        assert payload["shadow"]["comprehension"] is None

    def test_none_inspection_returns_none(self):
        assert _build_shadow_analysis_payload(None) is None


class TestExpedientePayload:
    def _session(self) -> Session:
        eng = create_engine("sqlite://")
        Base.metadata.create_all(eng, tables=[ExpedienteAssessment.__table__])
        return Session(eng)

    def test_returns_latest_non_errored(self):
        submission = SimpleNamespace(client_id="c", vendor_id="v", period_id="p")
        with self._session() as db:
            db.add(
                ExpedienteAssessment(
                    client_id="c",
                    vendor_id="v",
                    period_id="p",
                    coherence="coherent",
                    summary_for_reviewer="viejo",
                    document_ids=["d1"],
                    created_at=datetime(2026, 1, 1, tzinfo=UTC),
                )
            )
            db.add(
                ExpedienteAssessment(
                    client_id="c",
                    vendor_id="v",
                    period_id="p",
                    coherence="minor_issues",
                    summary_for_reviewer="nuevo",
                    findings=[
                        {
                            "code": "headcount_inconsistency",
                            "severity": "medium",
                            "detail_es": "x",
                            "evidence": "y",
                        }
                    ],
                    coverage_gaps=[],
                    document_ids=["d1", "d2", "d3"],
                    created_at=datetime(2026, 2, 1, tzinfo=UTC),
                )
            )
            # Newest by time but errored → must be excluded.
            db.add(
                ExpedienteAssessment(
                    client_id="c",
                    vendor_id="v",
                    period_id="p",
                    error="timeout",
                    document_ids=[],
                    created_at=datetime(2026, 3, 1, tzinfo=UTC),
                )
            )
            db.commit()

            payload = _build_expediente_payload(db, submission)
            assert payload is not None
            assert payload["coherence"] == "minor_issues"  # latest non-errored
            assert payload["summary_for_reviewer"] == "nuevo"
            assert payload["document_count"] == 3
            assert payload["findings"][0]["code"] == "headcount_inconsistency"

    def test_none_when_no_assessment(self):
        submission = SimpleNamespace(client_id="c", vendor_id="v", period_id="p")
        with self._session() as db:
            assert _build_expediente_payload(db, submission) is None

    def test_scoped_to_submission(self):
        submission = SimpleNamespace(client_id="c", vendor_id="v", period_id="p")
        with self._session() as db:
            db.add(
                ExpedienteAssessment(
                    client_id="other",
                    vendor_id="v",
                    period_id="p",
                    coherence="coherent",
                    document_ids=["d"],
                    created_at=datetime(2026, 2, 1, tzinfo=UTC),
                )
            )
            db.commit()
            # Different client → not returned for this submission's scope.
            assert _build_expediente_payload(db, submission) is None
