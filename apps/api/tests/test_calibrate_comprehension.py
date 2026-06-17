"""Unit tests for the Phase-4 comprehension calibration harness.

Covers the pure metric functions on tiny hand-asserted datasets (verdict
precision, confidence thresholds, AUC, the graduation-rule math) plus the
tolerant ``_extract_comprehension`` reader. No DB — the metric functions
take plain ``ComprehensionRecord`` lists and the extractor takes a simple
namespace.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts.calibrate_comprehension import (
    ComprehensionRecord,
    _extract_comprehension,
    compute_group_metrics,
    confidence_threshold_metrics,
    coverage_stats,
    graduation_simulation,
    rank_auc,
    verdict_confusion,
)


def _rec(
    *,
    approved: bool,
    verdict: str | None = "satisfied",
    confidence: float | None = 0.95,
    has_comprehension: bool = True,
    code: str = "REC-X",
) -> ComprehensionRecord:
    return ComprehensionRecord(
        submission_id="s",
        document_id="d",
        requirement_code=code,
        status="aprobado" if approved else "rechazado",
        human_approved=approved,
        has_comprehension=has_comprehension,
        obligation_verdict=verdict if has_comprehension else None,
        obligation_confidence=confidence if has_comprehension else None,
        validity="valid",
        currency_ok=True,
        discrepancy_count=0,
    )


class TestVerdictConfusion:
    def test_satisfied_and_not_satisfied_precision(self):
        records = [
            _rec(approved=True, verdict="satisfied"),
            _rec(approved=True, verdict="satisfied"),
            _rec(approved=False, verdict="satisfied"),  # model wrong here
            _rec(approved=False, verdict="not_satisfied"),
            _rec(approved=False, verdict="not_satisfied"),
        ]
        conf = verdict_confusion(records)
        assert conf["judged"] == 5
        # 2 of 3 "satisfied" were approved.
        assert conf["satisfied_precision"] == pytest.approx(2 / 3)
        # 2 of 2 "not_satisfied" were rejected.
        assert conf["not_satisfied_precision"] == pytest.approx(1.0)
        assert conf["matrix"]["satisfied"] == {"approved": 2, "rejected": 1}

    def test_excludes_records_without_comprehension(self):
        records = [
            _rec(approved=True, has_comprehension=False),
            _rec(approved=True, verdict="satisfied"),
        ]
        conf = verdict_confusion(records)
        assert conf["judged"] == 1


class TestGraduationSimulation:
    def test_meets_bar_when_satisfied_high_conf_all_approved(self):
        records = [_rec(approved=True, confidence=0.95) for _ in range(20)]
        sim = graduation_simulation(records, confidence_threshold=0.9)
        assert sim["cleared"] == 20
        assert sim["precision"] == pytest.approx(1.0)
        assert sim["meets_bar"] is True

    def test_one_false_positive_breaks_the_99_bar(self):
        records = [_rec(approved=True, confidence=0.95) for _ in range(50)]
        records.append(_rec(approved=False, verdict="satisfied", confidence=0.95))
        sim = graduation_simulation(records, confidence_threshold=0.9)
        assert sim["cleared"] == 51
        assert sim["precision"] == pytest.approx(50 / 51)
        assert sim["meets_bar"] is False  # 0.980 < 0.99

    def test_below_threshold_is_not_cleared(self):
        records = [_rec(approved=True, confidence=0.5)]
        sim = graduation_simulation(records, confidence_threshold=0.9)
        assert sim["cleared"] == 0
        # No evidence → precision None → does not meet the bar.
        assert sim["precision"] is None
        assert sim["meets_bar"] is False

    def test_non_satisfied_verdicts_never_clear(self):
        records = [
            _rec(approved=True, verdict="partial", confidence=0.99),
            _rec(approved=True, verdict="not_satisfied", confidence=0.99),
            _rec(approved=True, verdict="indeterminate", confidence=0.99),
        ]
        sim = graduation_simulation(records, confidence_threshold=0.9)
        assert sim["cleared"] == 0


class TestThresholds:
    def test_precision_recall_at_thresholds(self):
        records = [
            _rec(approved=True, verdict="satisfied", confidence=0.95),
            _rec(approved=True, verdict="satisfied", confidence=0.6),
            _rec(approved=False, verdict="satisfied", confidence=0.95),
        ]
        rows = {r["threshold"]: r for r in confidence_threshold_metrics(records)}
        # At 0.9: predicted = the two conf>=0.9 satisfied (1 approved, 1 not).
        assert rows[0.9]["predicted_positive"] == 2
        assert rows[0.9]["precision"] == pytest.approx(0.5)
        # recall = approved-predicted / all-approved-scored (2 approved total).
        assert rows[0.9]["recall"] == pytest.approx(0.5)


class TestAuc:
    def test_perfect_separation(self):
        records = [
            _rec(approved=True, confidence=0.9),
            _rec(approved=True, confidence=0.8),
            _rec(approved=False, confidence=0.3),
        ]
        assert rank_auc(records) == pytest.approx(1.0)

    def test_none_when_one_class_empty(self):
        records = [_rec(approved=True, confidence=0.9)]
        assert rank_auc(records) is None


class TestCoverage:
    def test_counts(self):
        records = [
            _rec(approved=True, has_comprehension=True),
            _rec(approved=False, has_comprehension=False),
        ]
        cov = coverage_stats(records)
        assert cov["records"] == 2
        assert cov["with_comprehension"] == 1
        assert cov["missing_comprehension"] == 1


class TestExtractComprehension:
    def test_extracts_full_comprehension(self):
        inspection = SimpleNamespace(
            shadow_signals={
                "comprehension": {
                    "obligation_satisfaction": {
                        "verdict": "not_satisfied",
                        "confidence": 0.9,
                        "reasoning": "x",
                    },
                    "status_assessment": {
                        "validity": "expired",
                        "currency_ok": False,
                        "reasoning": "y",
                    },
                    "discrepancies": [{"issue": "a"}, {"issue": "b"}],
                }
            }
        )
        out = _extract_comprehension(inspection)
        assert out["has_comprehension"] is True
        assert out["obligation_verdict"] == "not_satisfied"
        assert out["obligation_confidence"] == pytest.approx(0.9)
        assert out["validity"] == "expired"
        assert out["currency_ok"] is False
        assert out["discrepancy_count"] == 2

    def test_no_comprehension_key(self):
        inspection = SimpleNamespace(shadow_signals={"anomaly_codes": []})
        out = _extract_comprehension(inspection)
        assert out["has_comprehension"] is False
        assert out["obligation_verdict"] is None

    def test_none_inspection_and_none_signals(self):
        assert _extract_comprehension(None)["has_comprehension"] is False
        assert (
            _extract_comprehension(SimpleNamespace(shadow_signals=None))[
                "has_comprehension"
            ]
            is False
        )


def test_compute_group_metrics_smoke():
    records = [
        _rec(approved=True, verdict="satisfied", confidence=0.95),
        _rec(approved=False, verdict="not_satisfied", confidence=0.2),
    ]
    m = compute_group_metrics(records)
    assert m["outcomes"] == {"records": 2, "approved": 1, "rejected": 1}
    assert "graduation" in m and "thresholds" in m and "verdict_confusion" in m
