"""Phase 2 keystone — document_folios model, intake population helper, and
the backfill. Pure in-memory SQLite; never touches a real DB."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import (
    Client,
    Document,
    DocumentFolio,
    DocumentInspection,
    Institution,
    Period,
    Requirement,
    RequirementVersion,
    Submission,
    Vendor,
)
from app.services.document_folios import (
    apply_cross_period_reason,
    apply_cross_tenant_reason,
    cross_period_folio_reason,
    cross_tenant_folio_reason,
    folio_pairs,
    persist_document_folios,
)
from scripts.backfill_document_folios import run as run_backfill

VERIF = {
    "folios": [
        {"kind": "cfdi_uuid", "value": "ABC-123"},
        {"kind": "sat_opinion_folio", "value": "F999"},
    ],
    "qr_codes": [],
}
_EXPECTED = [("cfdi_uuid", "ABC-123"), ("sat_opinion_folio", "F999")]

_SEED = 0


@pytest.fixture
def db_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _seed_document(db_factory, *, verification=None) -> tuple[str, str, str, str]:
    """Seed client/vendor/period/submission/document (+ inspection when
    ``verification`` given). Returns (document_id, client_id, vendor_id,
    period_id)."""
    global _SEED
    _SEED += 1
    n = _SEED
    db = db_factory()
    try:
        client = Client(name=f"C{n}", rfc=f"CL{n:03d}260101AB"[:13])
        db.add(client)
        db.flush()
        vendor = Vendor(client_id=client.id, name=f"V{n}", rfc=f"VD{n:03d}260101XY"[:13])
        db.add(vendor)
        db.flush()
        inst = db.scalar(select(Institution).where(Institution.code == "sat"))
        if inst is None:
            inst = Institution(code="sat", name="SAT")
            db.add(inst)
            db.flush()
        req = Requirement(
            code=f"r:{n}",
            name=f"Req {n}",
            institution_id=inst.id,
            load_type="mensual",
            frequency="mensual",
            risk_level="medium",
            current_version=1,
        )
        db.add(req)
        db.flush()
        rv = RequirementVersion(requirement_id=req.id, version=1)
        db.add(rv)
        db.flush()
        period = Period(
            code=f"2026-M{n:02d}",
            year=2026,
            period_type="mensual",
            period_key=f"2026-M{n:02d}",
        )
        db.add(period)
        db.flush()
        sub = Submission(
            client_id=client.id,
            vendor_id=vendor.id,
            institution_id=inst.id,
            requirement_id=req.id,
            requirement_version_id=rv.id,
            period_id=period.id,
            status="pendiente_revision",
            load_type="mensual",
            requirement_code=req.code,
            period_key=period.period_key,
        )
        db.add(sub)
        db.flush()
        doc = Document(
            submission_id=sub.id,
            storage_key=f"local://{sub.id}.pdf",
            original_filename="x.pdf",
            mime_type="application/pdf",
            size_bytes=1024,
            sha256="a" * 64,
        )
        db.add(doc)
        db.flush()
        if verification is not None:
            db.add(
                DocumentInspection(
                    document_id=doc.id, is_pdf=True, verification=verification
                )
            )
        ids = (doc.id, client.id, vendor.id, period.id)
        db.commit()
        return ids
    finally:
        db.close()


def _folios(db_factory, document_id: str) -> list[tuple[str, str]]:
    db = db_factory()
    try:
        return sorted(
            (f.kind, f.value)
            for f in db.scalars(
                select(DocumentFolio).where(DocumentFolio.document_id == document_id)
            )
        )
    finally:
        db.close()


# --- folio_pairs robustness ---


@pytest.mark.parametrize(
    "bad",
    [
        None,
        {},
        {"folios": None},
        {"folios": "nope"},
        {"folios": [None, 7, "x"]},
        {"folios": [{"kind": "k"}, {"value": "v"}, {"kind": "", "value": "v"}]},
    ],
)
def test_folio_pairs_tolerates_garbage(bad) -> None:
    assert folio_pairs(bad) == []


def test_folio_pairs_dedupes_and_truncates() -> None:
    v = {
        "folios": [
            {"kind": "cfdi_uuid", "value": "A"},
            {"kind": "cfdi_uuid", "value": "A"},
            {"kind": "k" * 60, "value": "v" * 200},
        ]
    }
    pairs = folio_pairs(v)
    assert pairs.count(("cfdi_uuid", "A")) == 1
    assert len(pairs[1][0]) == 40 and len(pairs[1][1]) == 120


# --- persist_document_folios ---


def test_persist_inserts_and_is_idempotent(db_factory) -> None:
    doc_id, client_id, vendor_id, period_id = _seed_document(db_factory)
    db = db_factory()
    try:
        n1 = persist_document_folios(
            db,
            document_id=doc_id,
            client_id=client_id,
            vendor_id=vendor_id,
            period_id=period_id,
            verification=VERIF,
        )
        db.commit()
        n2 = persist_document_folios(
            db,
            document_id=doc_id,
            client_id=client_id,
            vendor_id=vendor_id,
            period_id=period_id,
            verification=VERIF,
        )
        db.commit()
    finally:
        db.close()
    assert n1 == 2
    assert n2 == 0  # idempotent
    assert _folios(db_factory, doc_id) == _EXPECTED


def test_persist_no_folios_is_noop(db_factory) -> None:
    doc_id, client_id, vendor_id, period_id = _seed_document(db_factory)
    db = db_factory()
    try:
        added = persist_document_folios(
            db,
            document_id=doc_id,
            client_id=client_id,
            vendor_id=vendor_id,
            period_id=period_id,
            verification={"folios": []},
        )
        db.commit()
    finally:
        db.close()
    assert added == 0
    assert _folios(db_factory, doc_id) == []


# --- backfill ---


def test_backfill_apply_populates_and_is_idempotent(db_factory) -> None:
    doc_id, *_ = _seed_document(db_factory, verification=VERIF)
    _seed_document(db_factory, verification={"folios": []})  # scanned, no folios
    _seed_document(db_factory, verification=None)  # no inspection → not scanned

    db = db_factory()
    try:
        scanned, docs_new, added = run_backfill(db, apply=True, batch_size=10)
    finally:
        db.close()
    assert (scanned, docs_new, added) == (2, 1, 2)
    assert _folios(db_factory, doc_id) == _EXPECTED

    db = db_factory()
    try:
        _, _, added2 = run_backfill(db, apply=True, batch_size=10)
    finally:
        db.close()
    assert added2 == 0  # idempotent re-run


def test_backfill_dry_run_writes_nothing(db_factory) -> None:
    doc_id, *_ = _seed_document(db_factory, verification=VERIF)
    db = db_factory()
    try:
        _, _, added = run_backfill(db, apply=False, batch_size=10)
    finally:
        db.close()
    assert added == 2  # would-add count
    assert _folios(db_factory, doc_id) == []  # but nothing written


def test_backfill_multi_batch_visits_every_row(db_factory) -> None:
    """Keyset paging over the random-uuid id PK must visit EVERY inspection
    across many tiny batches — proving random ids are valid keyset cursors
    (a unique total order is all keyset pagination requires)."""
    doc_ids = [
        _seed_document(
            db_factory,
            verification={"folios": [{"kind": "cfdi_uuid", "value": f"U-{i}"}]},
        )[0]
        for i in range(7)
    ]
    db = db_factory()
    try:
        scanned, docs_new, added = run_backfill(db, apply=True, batch_size=1)
    finally:
        db.close()
    assert (scanned, docs_new, added) == (7, 7, 7)  # nothing skipped or repeated
    for i, doc_id in enumerate(doc_ids):
        assert _folios(db_factory, doc_id) == [("cfdi_uuid", f"U-{i}")]


# --- cross-tenant recycled-document detection ---


_CFDI = {"folios": [{"kind": "cfdi_uuid", "value": "UUID-XYZ"}], "qr_codes": []}


def _enable_cross_tenant(monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "CROSS_TENANT_RECYCLED_DETECTION_ENABLED", True)


def _index_folio_under_new_client(db_factory, *, value: str = "UUID-XYZ") -> str:
    """Create a doc under a fresh client and index its cfdi_uuid folio. Returns
    that client's id."""
    doc_id, client_id, vendor_id, period_id = _seed_document(db_factory)
    db = db_factory()
    try:
        persist_document_folios(
            db,
            document_id=doc_id,
            client_id=client_id,
            vendor_id=vendor_id,
            period_id=period_id,
            verification={"folios": [{"kind": "cfdi_uuid", "value": value}]},
        )
        db.commit()
    finally:
        db.close()
    return client_id


def _reason(db_factory, **kwargs):
    db = db_factory()
    try:
        return cross_tenant_folio_reason(db, **kwargs)
    finally:
        db.close()


def test_cross_tenant_flags_other_clients_uuid(db_factory, monkeypatch) -> None:
    _enable_cross_tenant(monkeypatch)
    _index_folio_under_new_client(db_factory, value="UUID-XYZ")
    reason = _reason(
        db_factory, client_id="me", verification=_CFDI, detected_institution="sat"
    )
    assert reason is not None
    assert reason.code == "cross_tenant_reuse"
    assert reason.severity == "medium"
    assert "1 otro" in reason.detail_es  # count-only, no tenant identity


def test_cross_tenant_off_by_default(db_factory) -> None:
    _index_folio_under_new_client(db_factory)
    assert (
        _reason(
            db_factory, client_id="me", verification=_CFDI, detected_institution="sat"
        )
        is None
    )


def test_cross_tenant_only_sat_imss(db_factory, monkeypatch) -> None:
    _enable_cross_tenant(monkeypatch)
    _index_folio_under_new_client(db_factory)
    assert (
        _reason(
            db_factory,
            client_id="me",
            verification=_CFDI,
            detected_institution="infonavit",
        )
        is None
    )


def test_cross_tenant_ignores_same_client(db_factory, monkeypatch) -> None:
    _enable_cross_tenant(monkeypatch)
    owner = _index_folio_under_new_client(db_factory, value="UUID-SAME")
    # Querying AS the owning client → its own folio is excluded → no self-flag.
    assert (
        _reason(
            db_factory,
            client_id=owner,
            verification={"folios": [{"kind": "cfdi_uuid", "value": "UUID-SAME"}]},
            detected_institution="sat",
        )
        is None
    )


def test_cross_tenant_needs_a_cfdi_uuid(db_factory, monkeypatch) -> None:
    _enable_cross_tenant(monkeypatch)
    _index_folio_under_new_client(db_factory)
    # Only an opinion folio (no fiscal UUID) → no cross-tenant check.
    assert (
        _reason(
            db_factory,
            client_id="me",
            verification={"folios": [{"kind": "sat_opinion_folio", "value": "F1"}]},
            detected_institution="sat",
        )
        is None
    )


def test_cross_tenant_counts_distinct_clients(db_factory, monkeypatch) -> None:
    _enable_cross_tenant(monkeypatch)
    _index_folio_under_new_client(db_factory, value="UUID-XYZ")
    _index_folio_under_new_client(db_factory, value="UUID-XYZ")  # 2nd other client
    reason = _reason(
        db_factory, client_id="me", verification=_CFDI, detected_institution="sat"
    )
    assert reason is not None and "2 otro" in reason.detail_es


def test_apply_elevates_clean_to_suspicious(db_factory, monkeypatch) -> None:
    _enable_cross_tenant(monkeypatch)
    _index_folio_under_new_client(db_factory)
    db = db_factory()
    try:
        risk, reasons = apply_cross_tenant_reason(
            db,
            client_id="me",
            verification=_CFDI,
            detected_institution="sat",
            authenticity_risk="clean",
            risk_reasons=[],
        )
    finally:
        db.close()
    assert risk == "suspicious"
    assert any(r["code"] == "cross_tenant_reuse" for r in reasons)


def test_apply_does_not_downgrade_high_risk(db_factory, monkeypatch) -> None:
    _enable_cross_tenant(monkeypatch)
    _index_folio_under_new_client(db_factory)
    db = db_factory()
    try:
        risk, reasons = apply_cross_tenant_reason(
            db,
            client_id="me",
            verification=_CFDI,
            detected_institution="sat",
            authenticity_risk="high_risk",
            risk_reasons=[{"code": "f", "severity": "high", "detail_es": "x"}],
        )
    finally:
        db.close()
    assert risk == "high_risk"  # a medium reason never downgrades
    assert reasons[0]["severity"] == "high"  # stays severity-sorted


def test_apply_unchanged_without_collision(db_factory, monkeypatch) -> None:
    _enable_cross_tenant(monkeypatch)  # enabled, but nothing indexed → no match
    db = db_factory()
    try:
        risk, reasons = apply_cross_tenant_reason(
            db,
            client_id="me",
            verification=_CFDI,
            detected_institution="sat",
            authenticity_risk="clean",
            risk_reasons=[],
        )
    finally:
        db.close()
    assert risk == "clean" and reasons == []


def test_apply_cross_tenant_failopen_recovers_session(db_factory, monkeypatch) -> None:
    """A DB error in the cross-tenant read must NOT poison the intake
    transaction: the SAVEPOINT rolls back to a usable session so the
    surrounding commit still succeeds (true fail-open)."""
    from app.services import document_folios as df

    _enable_cross_tenant(monkeypatch)  # reach the savepoint-guarded read path

    def _boom(db, **_kwargs):
        # A real failed statement — this is what poisons the session if it
        # isn't SAVEPOINT-isolated.
        db.execute(text("SELECT * FROM table_that_does_not_exist"))

    monkeypatch.setattr(df, "cross_tenant_folio_reason", _boom)

    db = db_factory()
    try:
        db.add(Client(name="Pending", rfc="PEND260101AB"[:13]))  # intake in flight
        risk, reasons = apply_cross_tenant_reason(
            db,
            client_id="me",
            verification=_CFDI,
            detected_institution="sat",
            authenticity_risk="clean",
            risk_reasons=[],
        )
        assert (risk, reasons) == ("clean", [])  # unchanged — failed open
        db.commit()  # MUST succeed: the session was not left poisoned
        assert db.scalar(select(Client).where(Client.name == "Pending")) is not None
    finally:
        db.close()


# --- cross-period folio-reuse detection ---


_CFDI1 = {"folios": [{"kind": "cfdi_uuid", "value": "U-1"}], "qr_codes": []}


def _enable_cross_period(monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "CROSS_PERIOD_REUSE_DETECTION_ENABLED", True)


def _index_cfdi_for_vendor(db_factory, *, value: str = "U-1") -> tuple[str, str]:
    """Seed a doc and index its cfdi_uuid. Returns (vendor_id, period_id)."""
    doc_id, client_id, vendor_id, period_id = _seed_document(db_factory)
    db = db_factory()
    try:
        persist_document_folios(
            db,
            document_id=doc_id,
            client_id=client_id,
            vendor_id=vendor_id,
            period_id=period_id,
            verification={"folios": [{"kind": "cfdi_uuid", "value": value}]},
        )
        db.commit()
    finally:
        db.close()
    return vendor_id, period_id


def _period_reason(db_factory, **kwargs):
    db = db_factory()
    try:
        return cross_period_folio_reason(db, **kwargs)
    finally:
        db.close()


def test_cross_period_flags_reuse_same_vendor_other_period(
    db_factory, monkeypatch
) -> None:
    _enable_cross_period(monkeypatch)
    vendor_id, _period_id = _index_cfdi_for_vendor(db_factory, value="U-1")
    reason = _period_reason(
        db_factory, vendor_id=vendor_id, period_id="other-period", verification=_CFDI1
    )
    assert reason is not None
    assert reason.code == "cross_period_folio_reuse"
    assert reason.severity == "high"
    assert "1 periodo" in reason.detail_es


def test_cross_period_off_by_default(db_factory) -> None:
    vendor_id, _ = _index_cfdi_for_vendor(db_factory)
    assert (
        _period_reason(
            db_factory, vendor_id=vendor_id, period_id="other", verification=_CFDI1
        )
        is None
    )


def test_cross_period_ignores_same_period(db_factory, monkeypatch) -> None:
    _enable_cross_period(monkeypatch)
    vendor_id, period_id = _index_cfdi_for_vendor(db_factory, value="U-SAME")
    # Same period as the indexed folio (re-upload / replacement) → no self-flag.
    assert (
        _period_reason(
            db_factory,
            vendor_id=vendor_id,
            period_id=period_id,
            verification={"folios": [{"kind": "cfdi_uuid", "value": "U-SAME"}]},
        )
        is None
    )


def test_cross_period_ignores_other_vendor(db_factory, monkeypatch) -> None:
    _enable_cross_period(monkeypatch)
    _index_cfdi_for_vendor(db_factory, value="U-1")
    # A DIFFERENT vendor reusing the UUID is the cross-tenant case, not this one.
    assert (
        _period_reason(
            db_factory, vendor_id="other-vendor", period_id="p", verification=_CFDI1
        )
        is None
    )


def test_cross_period_needs_period_and_cfdi(db_factory, monkeypatch) -> None:
    _enable_cross_period(monkeypatch)
    vendor_id, _ = _index_cfdi_for_vendor(db_factory)
    assert (
        _period_reason(
            db_factory, vendor_id=vendor_id, period_id=None, verification=_CFDI1
        )
        is None
    )
    assert (
        _period_reason(
            db_factory,
            vendor_id=vendor_id,
            period_id="p",
            verification={"folios": [{"kind": "sat_opinion_folio", "value": "F"}]},
        )
        is None
    )


def test_apply_cross_period_elevates_to_high(db_factory, monkeypatch) -> None:
    _enable_cross_period(monkeypatch)
    vendor_id, _ = _index_cfdi_for_vendor(db_factory, value="U-1")
    db = db_factory()
    try:
        risk, reasons = apply_cross_period_reason(
            db,
            vendor_id=vendor_id,
            period_id="other",
            verification=_CFDI1,
            authenticity_risk="clean",
            risk_reasons=[],
        )
    finally:
        db.close()
    assert risk == "high_risk"
    assert any(r["code"] == "cross_period_folio_reuse" for r in reasons)


# --- migration sanity ---


def test_migration_chains_off_base_head() -> None:
    path = Path(__file__).resolve().parents[1] / (
        "alembic/versions/0061_document_folio_index.py"
    )
    spec = importlib.util.spec_from_file_location("m0059", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == "0061_document_folio_index"
    # Rechained onto main's head at integration (was 0055 on the folio branch).
    assert mod.down_revision == "0060_rename_rbac_roles"
