"""Unit tests for the Phase-A calibration harness.

Covers the pure metric functions on a tiny known dataset (precision /
recall / AUC / auto-approve math asserted by hand) plus a light pass of
the DB-replay loop (``collect_records``) against the in-memory test DB,
seeded the same way ``tests/test_reviewer.py`` seeds decided
submissions.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import (
    Client,
    Document,
    DocumentInspection,
    Institution,
    Period,
    Requirement,
    Submission,
    Vendor,
    entities,  # noqa: F401 — register all tables on Base.metadata
)
from scripts.calibrate_document_verdicts import (
    CalibrationRecord,
    authenticity_confusion,
    auto_approve_simulation,
    build_report,
    collect_records,
    compute_group_metrics,
    coverage_stats,
    rank_auc,
    threshold_metrics,
    top_risk_reasons,
    verification_stats,
)

# ---------------------------------------------------------------------------
# Pure metric functions — known tiny dataset
# ---------------------------------------------------------------------------


def _rec(
    *,
    approved: bool,
    confidence: float | None = None,
    risk: str | None = None,
    code: str = "sat:declaracion_iva:mensual",
    source: str | None = None,
    reasons: list[str] | None = None,
) -> CalibrationRecord:
    return CalibrationRecord(
        submission_id="s",
        document_id="d",
        requirement_code=code,
        period_key="2026-M03",
        status="aprobado" if approved else "rechazado",
        human_approved=approved,
        match_confidence=confidence,
        confidence_source=source or ("heuristic" if confidence is not None else None),
        authenticity_risk=risk,
        risk_reason_codes=reasons or [],
    )


# 4 approved scored [0.98, 0.96, 0.85, 0.60], 2 rejected scored [0.75, 0.40],
# 1 approved with no confidence at all (legacy).
TINY = [
    _rec(approved=True, confidence=0.98, risk="clean"),
    _rec(approved=True, confidence=0.96, risk="clean"),
    _rec(approved=True, confidence=0.85, risk="suspicious", reasons=["generador_sospechoso"]),
    _rec(approved=True, confidence=0.60, risk="clean"),
    _rec(approved=False, confidence=0.75, risk="clean"),
    _rec(approved=False, confidence=0.40, risk="high_risk", reasons=["generador_sospechoso", "js_embebido"]),
    _rec(approved=True, confidence=None, risk=None),  # legacy gap
]


def test_threshold_metrics_known_dataset() -> None:
    rows = {row["threshold"]: row for row in threshold_metrics(TINY)}

    # t=0.5: cleared = [0.98, 0.96, 0.85, 0.60 approved; 0.75 rejected]
    at_50 = rows[0.5]
    assert (at_50["tp"], at_50["fp"], at_50["fn"], at_50["tn"]) == (4, 1, 0, 1)
    assert at_50["precision"] == pytest.approx(4 / 5)
    assert at_50["recall"] == pytest.approx(1.0)

    # t=0.8: cleared = [0.98, 0.96, 0.85] all approved.
    at_80 = rows[0.8]
    assert (at_80["tp"], at_80["fp"]) == (3, 0)
    assert at_80["precision"] == pytest.approx(1.0)
    assert at_80["recall"] == pytest.approx(3 / 4)

    # t=0.97: only 0.98 clears (>= comparison: 0.96 < 0.97).
    at_97 = rows[0.97]
    assert (at_97["tp"], at_97["fp"]) == (1, 0)
    assert at_97["precision"] == pytest.approx(1.0)
    assert at_97["recall"] == pytest.approx(1 / 4)


def test_threshold_metrics_empty_denominators_are_none() -> None:
    only_rejected = [_rec(approved=False, confidence=0.3)]
    rows = threshold_metrics(only_rejected)
    for row in rows:
        assert row["recall"] is None  # no positives at all
        if row["predicted_positive"] == 0:
            assert row["precision"] is None


def test_rank_auc_known_values() -> None:
    # Perfect separation → 1.0
    perfect = [
        _rec(approved=True, confidence=0.9),
        _rec(approved=True, confidence=0.8),
        _rec(approved=False, confidence=0.2),
    ]
    assert rank_auc(perfect) == pytest.approx(1.0)

    # Hand-computed: pos=[0.9, 0.5], neg=[0.5, 0.7]
    # pairs: (0.9 vs 0.5)=1, (0.9 vs 0.7)=1, (0.5 vs 0.5)=0.5, (0.5 vs 0.7)=0
    # AUC = 2.5 / 4 = 0.625
    mixed = [
        _rec(approved=True, confidence=0.9),
        _rec(approved=True, confidence=0.5),
        _rec(approved=False, confidence=0.5),
        _rec(approved=False, confidence=0.7),
    ]
    assert rank_auc(mixed) == pytest.approx(0.625)

    # Single class → undefined.
    assert rank_auc([_rec(approved=True, confidence=0.9)]) is None
    # Unscored records do not participate.
    assert rank_auc([_rec(approved=True, confidence=None)]) is None


def test_authenticity_confusion_known_dataset() -> None:
    auth = authenticity_confusion(TINY)
    assert auth["judged"] == 6  # one legacy record had no verdict
    assert auth["matrix"]["clean"] == {"approved": 3, "rejected": 1}
    assert auth["matrix"]["suspicious"] == {"approved": 1, "rejected": 0}
    assert auth["matrix"]["high_risk"] == {"approved": 0, "rejected": 1}
    # 1 of 4 judged-approved docs was flagged.
    assert auth["false_positive_rate"] == pytest.approx(1 / 4)
    # 1 of 2 rejected docs came back clean.
    assert auth["rejected_clean_rate"] == pytest.approx(1 / 2)


def test_auto_approve_simulation_math() -> None:
    sim = auto_approve_simulation(TINY)
    # Only 0.98-clean clears (0.96 < 0.97; 0.75-clean is below threshold).
    assert sim["cleared"] == 1
    assert sim["cleared_approved"] == 1
    assert sim["precision"] == pytest.approx(1.0)
    assert sim["meets_bar"] is True
    # 5 approved total (incl. the legacy gap), 1 cleared.
    assert sim["approved_clearance"] == pytest.approx(1 / 5)


def test_auto_approve_rule_never_fires_does_not_meet_bar() -> None:
    sim = auto_approve_simulation([_rec(approved=True, confidence=0.5, risk="clean")])
    assert sim["cleared"] == 0
    assert sim["precision"] is None
    assert sim["meets_bar"] is False


def test_auto_approve_rejected_clearance_breaks_bar() -> None:
    records = [
        _rec(approved=True, confidence=0.99, risk="clean"),
        _rec(approved=False, confidence=0.99, risk="clean"),  # the rule misfires
    ]
    sim = auto_approve_simulation(records)
    assert sim["precision"] == pytest.approx(0.5)
    assert sim["meets_bar"] is False
    # Risk != clean blocks the rule even at high confidence.
    blocked = auto_approve_simulation(
        [_rec(approved=True, confidence=0.99, risk="suspicious")]
    )
    assert blocked["cleared"] == 0


def test_coverage_and_reasons() -> None:
    cov = coverage_stats(TINY)
    assert cov["records"] == 7
    assert cov["missing_confidence"] == 1
    assert cov["missing_authenticity"] == 1
    reasons = top_risk_reasons(TINY)
    assert reasons[0] == ("generador_sospechoso", 2)
    assert ("js_embebido", 1) in reasons


def test_verification_stats_phase_b() -> None:
    """qr_found_rate / qr_official_rate / folio kind counts (Phase B)."""
    records = [
        # Scanned, one official QR, a CFDI folio.
        _rec(approved=True, confidence=0.9, risk="clean"),
        _rec(approved=True, confidence=0.9, risk="clean"),
        _rec(approved=False, confidence=0.2, risk="clean"),
        _rec(approved=True, confidence=0.9, risk="clean"),  # not scanned
    ]
    records[0].qr_count = 1
    records[0].qr_all_official = True
    records[0].folio_kinds = ["cfdi_uuid", "sat_opinion_folio"]
    records[1].qr_count = 2
    records[1].qr_all_official = False  # one QR off-domain
    records[1].folio_kinds = ["cfdi_uuid"]
    records[2].qr_count = 0
    records[2].qr_all_official = None

    stats = verification_stats(records)
    assert stats["scanned"] == 3  # the 4th record was never scanned
    assert stats["qr_found"] == 2
    assert stats["qr_found_rate"] == pytest.approx(2 / 3)
    assert stats["qr_all_official"] == 1
    assert stats["qr_official_rate"] == pytest.approx(1 / 2)
    assert stats["folio_kinds"] == {"cfdi_uuid": 2, "sat_opinion_folio": 1}

    # No scans at all (run without --recompute-forensics): rates are n/a.
    empty = verification_stats([_rec(approved=True)])
    assert empty["scanned"] == 0
    assert empty["qr_found_rate"] is None
    assert empty["qr_official_rate"] is None
    assert empty["folio_kinds"] == {}


def test_compute_group_metrics_bundle_shape() -> None:
    bundle = compute_group_metrics(TINY)
    assert bundle["outcomes"] == {"records": 7, "approved": 5, "rejected": 2}
    assert {row["threshold"] for row in bundle["thresholds"]} == {
        0.5, 0.7, 0.8, 0.9, 0.95, 0.97,
    }
    assert 0.0 <= bundle["auc"] <= 1.0


# ---------------------------------------------------------------------------
# DB replay loop — in-memory test DB (pattern from tests/test_reviewer.py)
# ---------------------------------------------------------------------------


@pytest.fixture
def db_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


_SEED_COUNTER = 0


def _seed_decided_submission(
    db_factory,
    *,
    status_: str,
    requirement_code: str = "sat:declaracion_iva:mensual",
    period_key: str = "2026-M03",
    shadow_confidence: float | None = None,
    match_confidence: float | None = None,
    authenticity_risk: str | None = None,
    risk_reasons: list | None = None,
    with_inspection: bool = True,
) -> tuple[str, str]:
    """Minimum row graph for one decided submission + document (+inspection)."""
    global _SEED_COUNTER
    _SEED_COUNTER += 1
    suffix = _SEED_COUNTER

    db = db_factory()
    try:
        client = Client(name=f"Cliente Cal {suffix}", rfc=f"CC{suffix:03d}260101AB"[:13])
        db.add(client)
        db.flush()
        vendor = Vendor(
            client_id=client.id, name=f"Proveedor Cal {suffix}", rfc=f"VC{suffix:03d}260101XY"[:13]
        )
        db.add(vendor)
        db.flush()
        institution = db.scalar(select(Institution).where(Institution.code == "sat"))
        if institution is None:
            institution = Institution(code="sat", name="SAT")
            db.add(institution)
            db.flush()
        requirement = db.scalar(
            select(Requirement).where(Requirement.code == requirement_code)
        )
        if requirement is None:
            requirement = Requirement(
                code=requirement_code,
                name=requirement_code,
                institution_id=institution.id,
                load_type="mensual",
                frequency="mensual",
                risk_level="medium",
                current_version=1,
            )
            db.add(requirement)
            db.flush()
        period = db.scalar(
            select(Period).where(Period.code == period_key, Period.period_type == "mensual")
        )
        if period is None:
            period = Period(
                code=period_key,
                year=2026,
                month=int(period_key.split("-M")[-1]),
                period_type="mensual",
                period_key=period_key,
            )
            db.add(period)
            db.flush()
        submission = Submission(
            client_id=client.id,
            vendor_id=vendor.id,
            institution_id=institution.id,
            requirement_id=requirement.id,
            period_id=period.id,
            status=status_,
            load_type="mensual",
            requirement_code=requirement_code,
            period_key=period_key,
        )
        db.add(submission)
        db.flush()
        document = Document(
            submission_id=submission.id,
            storage_key=f"documents/ca/{submission.id}/cal.pdf",
            original_filename="cal.pdf",
            mime_type="application/pdf",
            size_bytes=1024,
            sha256=f"{suffix:064d}"[:64],
        )
        db.add(document)
        db.flush()
        if with_inspection:
            db.add(
                DocumentInspection(
                    document_id=document.id,
                    is_pdf=True,
                    shadow_confidence=shadow_confidence,
                    requirement_match_confidence=match_confidence,
                    authenticity_risk=authenticity_risk,
                    risk_reasons=risk_reasons,
                )
            )
        db.commit()
        return submission.id, client.id
    finally:
        db.close()


def test_collect_records_replays_terminal_statuses_only(db_factory) -> None:
    _seed_decided_submission(
        db_factory, status_="aprobado", shadow_confidence=0.98,
        match_confidence=0.6, authenticity_risk="clean",
    )
    _seed_decided_submission(
        db_factory, status_="excepcion_legal", match_confidence=0.7,
        authenticity_risk="clean",
    )
    _seed_decided_submission(
        db_factory, status_="rechazado", match_confidence=0.4,
        authenticity_risk="suspicious",
        risk_reasons=[{"code": "generador_sospechoso", "severity": "medium", "detail_es": "x"}],
    )
    _seed_decided_submission(db_factory, status_="requiere_aclaracion")  # ambiguous
    _seed_decided_submission(db_factory, status_="pendiente_revision")  # not terminal
    _seed_decided_submission(  # legacy: no inspection row at all
        db_factory, status_="aprobado", with_inspection=False,
    )

    db = db_factory()
    try:
        records, meta = collect_records(db)
    finally:
        db.close()

    assert len(records) == 4  # 3 decided + 1 legacy decided; ambiguous/pending out
    assert meta["ambiguous_excluded"] == 1
    by_status = {r.status for r in records}
    assert by_status == {"aprobado", "excepcion_legal", "rechazado"}

    # shadow_confidence preferred over the heuristic when both exist.
    shadow = next(r for r in records if r.confidence_source == "shadow")
    assert shadow.match_confidence == pytest.approx(0.98)
    # excepcion_legal counts as a human approval.
    exception = next(r for r in records if r.status == "excepcion_legal")
    assert exception.human_approved is True
    assert exception.confidence_source == "heuristic"
    # Rejected row carries its risk verdict + named reason codes.
    rejected = next(r for r in records if r.status == "rechazado")
    assert rejected.authenticity_risk == "suspicious"
    assert rejected.risk_reason_codes == ["generador_sospechoso"]
    # Legacy row lands as a pure coverage gap.
    legacy = next(r for r in records if r.match_confidence is None)
    assert legacy.authenticity_risk is None


def test_collect_records_filters_and_limit(db_factory) -> None:
    _, client_id = _seed_decided_submission(
        db_factory, status_="aprobado", match_confidence=0.9,
        requirement_code="imss:sua:mensual",
    )
    _seed_decided_submission(
        db_factory, status_="rechazado", match_confidence=0.2,
        requirement_code="sat:opinion_cumplimiento:mensual",
    )

    db = db_factory()
    try:
        by_code, _ = collect_records(db, requirement_code="imss:sua:mensual")
        by_client, _ = collect_records(db, client_id=client_id)
        capped, _ = collect_records(db, limit=1)
    finally:
        db.close()

    assert [r.requirement_code for r in by_code] == ["imss:sua:mensual"]
    assert [r.requirement_code for r in by_client] == ["imss:sua:mensual"]
    assert len(capped) == 1


def test_build_report_renders_markdown_and_json(db_factory) -> None:
    _seed_decided_submission(
        db_factory, status_="aprobado", shadow_confidence=0.99, authenticity_risk="clean",
    )
    _seed_decided_submission(
        db_factory, status_="rechazado", match_confidence=0.3, authenticity_risk="clean",
    )
    db = db_factory()
    try:
        records, meta = collect_records(db)
    finally:
        db.close()

    from datetime import UTC, datetime

    markdown, payload = build_report(
        records,
        replay_meta=meta,
        filters={"limit": None},
        generated_at=datetime.now(UTC),
    )
    assert "Calibración de veredictos documentales" in markdown
    assert "requiere_aclaracion" in markdown  # ambiguous count surfaced
    assert "Caveat" in markdown  # rejection-reason caveat in the header
    assert payload["overall"]["outcomes"] == {"records": 2, "approved": 1, "rejected": 1}
    assert "sat:declaracion_iva:mensual" in payload["per_requirement_code"]
    # The 0.99-clean approved doc clears; the 0.3 rejected doc does not.
    assert payload["overall"]["auto_approve"]["precision"] == pytest.approx(1.0)
    assert payload["overall"]["auto_approve"]["meets_bar"] is True
