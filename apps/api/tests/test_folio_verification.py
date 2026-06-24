"""B1 — live SAT CFDI folio verification (scaffolding) tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.models import (
    Client,
    Document,
    DocumentFolio,
    DocumentInspection,
    FolioVerification,
    Institution,
    Period,
    Requirement,
    RequirementVersion,
    Submission,
    Vendor,
)
from app.services import folio_verification as fv
from app.services.sat_cfdi_client import (
    LiveSATCFDIClient,
    StubSATCFDIClient,
    build_sat_cfdi_client,
)

_SEED = 0


@pytest.fixture
def db_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _seed(db_factory, *, cfdi_uuid: str | None = "UUID-ABC", authenticity_risk=None):
    global _SEED
    _SEED += 1
    n = _SEED
    db = db_factory()
    try:
        client = Client(name=f"C{n}", rfc=f"CLI{n:03d}600101AB"[:13])
        db.add(client)
        db.flush()
        vendor = Vendor(client_id=client.id, name=f"V{n}", rfc=f"VEN{n:03d}600101XY"[:13])
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
        db.add(
            DocumentInspection(
                document_id=doc.id, is_pdf=True, authenticity_risk=authenticity_risk
            )
        )
        if cfdi_uuid:
            db.add(
                DocumentFolio(
                    document_id=doc.id,
                    client_id=client.id,
                    vendor_id=vendor.id,
                    period_id=period.id,
                    kind="cfdi_uuid",
                    value=cfdi_uuid,
                )
            )
        db.commit()
        return doc.id
    finally:
        db.close()


def _enable(monkeypatch, *, status="not_verifiable"):
    monkeypatch.setattr(settings, "SAT_CFDI_VERIFICATION_ENABLED", True)
    monkeypatch.setattr(settings, "SAT_CFDI_CLIENT_MODE", "stub")
    monkeypatch.setattr(settings, "SAT_CFDI_STUB_STATUS", status)


def _inspection(db_factory, document_id):
    db = db_factory()
    try:
        return db.scalar(
            select(DocumentInspection).where(
                DocumentInspection.document_id == document_id
            )
        )
    finally:
        db.close()


# -- SAT client -------------------------------------------------------------


def test_stub_client_returns_canned_status(monkeypatch):
    monkeypatch.setattr(settings, "SAT_CFDI_STUB_STATUS", "vigente")
    r = StubSATCFDIClient().consultar(
        cfdi_uuid="U", emisor_rfc="E", receptor_rfc="R"
    )
    assert r.status == "vigente"
    assert r.source == "stub"


def test_stub_unknown_status_falls_back(monkeypatch):
    monkeypatch.setattr(settings, "SAT_CFDI_STUB_STATUS", "garbage")
    assert StubSATCFDIClient().consultar(
        cfdi_uuid="U", emisor_rfc="E", receptor_rfc="R"
    ).status == "not_verifiable"


def test_build_client_defaults_to_stub(monkeypatch):
    monkeypatch.setattr(settings, "SAT_CFDI_CLIENT_MODE", "stub")
    assert isinstance(build_sat_cfdi_client(), StubSATCFDIClient)


def test_live_client_is_a_skeleton_that_raises(monkeypatch):
    monkeypatch.setattr(settings, "SAT_CFDI_CLIENT_MODE", "live")
    client = build_sat_cfdi_client()
    assert isinstance(client, LiveSATCFDIClient)
    with pytest.raises(NotImplementedError):
        client.consultar(cfdi_uuid="U", emisor_rfc="E", receptor_rfc="R")


# -- worker -----------------------------------------------------------------


def test_disabled_is_noop(db_factory, monkeypatch):
    monkeypatch.setattr(settings, "SAT_CFDI_VERIFICATION_ENABLED", False)
    doc_id = _seed(db_factory)
    db = db_factory()
    try:
        out = fv.verify_document_folio(db, doc_id)
    finally:
        db.close()
    assert out == {"verified": False, "status": "disabled"}
    # No cache row written.
    db = db_factory()
    try:
        assert db.scalar(select(FolioVerification)) is None
    finally:
        db.close()


def test_no_cfdi_uuid_is_not_verifiable(db_factory, monkeypatch):
    _enable(monkeypatch, status="no_existe")
    doc_id = _seed(db_factory, cfdi_uuid=None)
    db = db_factory()
    try:
        out = fv.verify_document_folio(db, doc_id)
    finally:
        db.close()
    assert out["status"] == "not_verifiable"
    assert out.get("reason") == "no_cfdi_uuid"
    # Never elevated → still no authenticity verdict.
    assert _inspection(db_factory, doc_id).authenticity_risk is None


def test_vigente_does_not_change_verdict(db_factory, monkeypatch):
    _enable(monkeypatch, status="vigente")
    doc_id = _seed(db_factory)
    db = db_factory()
    try:
        out = fv.verify_document_folio(db, doc_id)
    finally:
        db.close()
    assert out["status"] == "vigente"
    assert out["authenticity_elevated"] is False
    insp = _inspection(db_factory, doc_id)
    assert insp.authenticity_risk is None
    assert not (insp.risk_reasons or [])
    # Result is cached.
    db = db_factory()
    try:
        cached = db.scalar(select(FolioVerification))
        assert cached.status == "vigente"
        assert cached.source == "stub"
    finally:
        db.close()


@pytest.mark.parametrize("bad_status", ["no_existe", "cancelado"])
def test_invalidating_status_elevates_high(db_factory, monkeypatch, bad_status):
    _enable(monkeypatch, status=bad_status)
    doc_id = _seed(db_factory)
    db = db_factory()
    try:
        out = fv.verify_document_folio(db, doc_id)
    finally:
        db.close()
    assert out["status"] == bad_status
    assert out["authenticity_elevated"] is True
    insp = _inspection(db_factory, doc_id)
    assert insp.authenticity_risk == "high_risk"
    codes = [r["code"] for r in insp.risk_reasons]
    assert "folio_not_found_at_sat" in codes


def test_not_verifiable_does_not_change_verdict(db_factory, monkeypatch):
    _enable(monkeypatch, status="not_verifiable")
    doc_id = _seed(db_factory)
    db = db_factory()
    try:
        out = fv.verify_document_folio(db, doc_id)
    finally:
        db.close()
    assert out["status"] == "not_verifiable"
    assert out["authenticity_elevated"] is False
    assert _inspection(db_factory, doc_id).authenticity_risk is None


def test_cache_hit_skips_client_call(db_factory, monkeypatch):
    _enable(monkeypatch, status="no_existe")
    doc_id = _seed(db_factory)
    # First call populates the cache.
    db = db_factory()
    try:
        first = fv.verify_document_folio(db, doc_id)
    finally:
        db.close()
    assert first["from_cache"] is False

    # Second call must NOT build/call the client (cache hit, not stale).
    spy = MagicMock(side_effect=AssertionError("client must not be called on cache hit"))
    monkeypatch.setattr(fv, "build_sat_cfdi_client", spy)
    db = db_factory()
    try:
        second = fv.verify_document_folio(db, doc_id)
    finally:
        db.close()
    assert second["from_cache"] is True
    assert second["status"] == "no_existe"


def test_force_refresh_requeries(db_factory, monkeypatch):
    _enable(monkeypatch, status="vigente")
    doc_id = _seed(db_factory)
    db = db_factory()
    try:
        fv.verify_document_folio(db, doc_id)
    finally:
        db.close()
    # Flip the canned status; force_refresh must re-query and re-cache.
    monkeypatch.setattr(settings, "SAT_CFDI_STUB_STATUS", "cancelado")
    db = db_factory()
    try:
        out = fv.verify_document_folio(db, doc_id, force_refresh=True)
    finally:
        db.close()
    assert out["from_cache"] is False
    assert out["status"] == "cancelado"
    assert _inspection(db_factory, doc_id).authenticity_risk == "high_risk"


def test_reverify_vigente_removes_prior_flag(db_factory, monkeypatch):
    _enable(monkeypatch, status="no_existe")
    doc_id = _seed(db_factory)
    db = db_factory()
    try:
        fv.verify_document_folio(db, doc_id)
    finally:
        db.close()
    assert _inspection(db_factory, doc_id).authenticity_risk == "high_risk"

    # SAT later confirms it vigente → the stale HIGH flag must be removed and the
    # verdict re-rolled (no other reasons → back to clean, never left high).
    monkeypatch.setattr(settings, "SAT_CFDI_STUB_STATUS", "vigente")
    db = db_factory()
    try:
        out = fv.verify_document_folio(db, doc_id, force_refresh=True)
    finally:
        db.close()
    assert out["authenticity_elevated"] is False
    insp = _inspection(db_factory, doc_id)
    assert insp.authenticity_risk == "clean"
    assert "folio_not_found_at_sat" not in [r["code"] for r in (insp.risk_reasons or [])]


def test_failopen_on_client_error(db_factory, monkeypatch):
    _enable(monkeypatch, status="no_existe")
    doc_id = _seed(db_factory)
    boom = MagicMock()
    boom.consultar.side_effect = RuntimeError("network down")
    monkeypatch.setattr(fv, "build_sat_cfdi_client", lambda: boom)
    db = db_factory()
    try:
        out = fv.verify_document_folio(db, doc_id)
    finally:
        db.close()
    # Falls open to not_verifiable; verdict untouched.
    assert out["status"] == "not_verifiable"
    assert out["authenticity_elevated"] is False
    assert _inspection(db_factory, doc_id).authenticity_risk is None


def test_reverify_does_not_clobber_other_reasons(db_factory, monkeypatch):
    # A pre-existing forensics HIGH reason must survive a vigente re-verify.
    _enable(monkeypatch, status="vigente")
    doc_id = _seed(db_factory, authenticity_risk="high_risk")
    db = db_factory()
    try:
        insp = db.scalar(
            select(DocumentInspection).where(
                DocumentInspection.document_id == doc_id
            )
        )
        insp.risk_reasons = [
            {"code": "producer_blocklisted", "severity": "high", "detail_es": "x"}
        ]
        db.commit()
    finally:
        db.close()
    db = db_factory()
    try:
        fv.verify_document_folio(db, doc_id)
    finally:
        db.close()
    insp = _inspection(db_factory, doc_id)
    # vigente added no reason and stripped none → forensics verdict intact.
    assert insp.authenticity_risk == "high_risk"
    assert [r["code"] for r in insp.risk_reasons] == ["producer_blocklisted"]


def test_cache_lookup_failure_falls_open_to_consult(db_factory, monkeypatch):
    # A DB-level error on the cache SELECT must not crash the worker — it falls
    # through to a fresh consult (the documented "never raises" contract).
    _enable(monkeypatch, status="no_existe")
    doc_id = _seed(db_factory)
    monkeypatch.setattr(
        fv, "_lookup_cache", MagicMock(side_effect=RuntimeError("db down"))
    )
    db = db_factory()
    try:
        out = fv.verify_document_folio(db, doc_id)
    finally:
        db.close()
    assert out["verified"] is True
    assert out["status"] == "no_existe"
    assert out["from_cache"] is False
