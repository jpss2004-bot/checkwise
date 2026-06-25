"""B1 — live SAT CFDI folio verification (scaffolding) tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
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
    _build_expresion,
    _fmt_total,
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


def _seed(
    db_factory, *, cfdi_uuid: str | None = "UUID-ABC", authenticity_risk=None, verification=None
):
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
                document_id=doc.id,
                is_pdf=True,
                authenticity_risk=authenticity_risk,
                verification=verification,
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
            select(DocumentInspection).where(DocumentInspection.document_id == document_id)
        )
    finally:
        db.close()


# -- SAT client -------------------------------------------------------------


def test_stub_client_returns_canned_status(monkeypatch):
    monkeypatch.setattr(settings, "SAT_CFDI_STUB_STATUS", "vigente")
    r = StubSATCFDIClient().consultar(cfdi_uuid="U", emisor_rfc="E", receptor_rfc="R")
    assert r.status == "vigente"
    assert r.source == "stub"


def test_stub_unknown_status_falls_back(monkeypatch):
    monkeypatch.setattr(settings, "SAT_CFDI_STUB_STATUS", "garbage")
    assert (
        StubSATCFDIClient().consultar(cfdi_uuid="U", emisor_rfc="E", receptor_rfc="R").status
        == "not_verifiable"
    )


def test_build_client_defaults_to_stub(monkeypatch):
    monkeypatch.setattr(settings, "SAT_CFDI_CLIENT_MODE", "stub")
    assert isinstance(build_sat_cfdi_client(), StubSATCFDIClient)


def test_build_client_returns_live_when_mode_live(monkeypatch):
    monkeypatch.setattr(settings, "SAT_CFDI_CLIENT_MODE", "live")
    assert isinstance(build_sat_cfdi_client(), LiveSATCFDIClient)


# -- live client (SOAP over httpx.MockTransport — no network) ----------------


def _soap_body(*, estado="", codigo="", efos="200") -> str:
    return (
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
        '<ConsultaResponse xmlns="http://tempuri.org/">'
        '<ConsultaResult xmlns:a="http://schemas.datacontract.org/2004/07/Sat.Cfdi">'
        f"<a:CodigoEstatus>{codigo}</a:CodigoEstatus>"
        "<a:EsCancelable>No cancelable</a:EsCancelable>"
        f"<a:Estado>{estado}</a:Estado>"
        "<a:EstatusCancelacion></a:EstatusCancelacion>"
        f"<a:ValidacionEFOS>{efos}</a:ValidacionEFOS>"
        "</ConsultaResult></ConsultaResponse></s:Body></s:Envelope>"
    )


def _live_client(handler) -> LiveSATCFDIClient:
    return LiveSATCFDIClient(transport=httpx.MockTransport(handler))


def _consult(client):
    return client.consultar(
        cfdi_uuid="UUID-1",
        emisor_rfc="EMI010101AA1",
        receptor_rfc="REC020202BB2",
        total="1234.56",
    )


@pytest.mark.parametrize(
    "estado,codigo,expected",
    [
        ("Vigente", "S - Comprobante obtenido satisfactoriamente", "vigente"),
        ("Cancelado", "S - Comprobante obtenido satisfactoriamente", "cancelado"),
        ("No Encontrado", "N - 602: Comprobante no encontrado", "no_existe"),
        ("", "N - 602: Comprobante no encontrado", "no_existe"),
        # 601 = malformed expresion (likely our input) → never flag the doc.
        ("", "N - 601: La expresion impresa proporcionada no es valida", "not_verifiable"),
        # S code but no usable Estado → can't be sure → fail open.
        ("", "S - Comprobante obtenido satisfactoriamente", "not_verifiable"),
    ],
)
def test_live_maps_sat_status(estado, codigo, expected):
    client = _live_client(
        lambda req: httpx.Response(200, text=_soap_body(estado=estado, codigo=codigo))
    )
    r = _consult(client)
    assert r.status == expected
    assert r.source == "sat_cfdi_live"


def test_live_captures_efos_in_raw():
    client = _live_client(
        lambda req: httpx.Response(200, text=_soap_body(estado="Vigente", efos="100"))
    )
    r = _consult(client)
    assert r.raw["ValidacionEFOS"] == "100"
    assert r.raw["Estado"] == "Vigente"


def test_live_http_500_fails_open():
    client = _live_client(lambda req: httpx.Response(500, text="error"))
    assert _consult(client).status == "not_verifiable"


def test_live_timeout_fails_open():
    def _boom(req):
        raise httpx.TimeoutException("slow", request=req)

    r = _consult(_live_client(_boom))
    assert r.status == "not_verifiable"
    assert r.raw["error"] == "TimeoutException"


def test_live_connect_error_fails_open():
    def _boom(req):
        raise httpx.ConnectError("down", request=req)

    assert _consult(_live_client(_boom)).status == "not_verifiable"


def test_live_soap_fault_fails_open():
    fault = (
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
        "<s:Fault><faultstring>boom</faultstring></s:Fault>"
        "</s:Body></s:Envelope>"
    )
    client = _live_client(lambda req: httpx.Response(200, text=fault))
    assert _consult(client).status == "not_verifiable"


def test_live_malformed_xml_fails_open():
    client = _live_client(lambda req: httpx.Response(200, text="not xml <<<"))
    r = _consult(client)
    assert r.status == "not_verifiable"
    assert "parse_error" in r.raw


def test_live_request_shape_is_correct():
    captured = {}

    def _handler(req):
        captured["url"] = str(req.url)
        captured["action"] = req.headers.get("SOAPAction")
        captured["body"] = req.content.decode("utf-8")
        return httpx.Response(200, text=_soap_body(estado="Vigente"))

    _consult(_live_client(_handler))
    assert captured["url"].endswith("ConsultaCFDIService.svc")
    assert captured["action"] == "http://tempuri.org/IConsultaCFDIService/Consulta"
    assert "expresionImpresa" in captured["body"]
    assert "re=EMI010101AA1" in captured["body"]
    assert "rr=REC020202BB2" in captured["body"]
    assert "tt=1234.56" in captured["body"]
    assert "id=UUID-1" in captured["body"]


def test_build_expresion_omits_total_when_absent():
    expr = _build_expresion(cfdi_uuid="U", emisor_rfc="E", receptor_rfc="R", total=None)
    assert expr == "?re=E&rr=R&id=U"
    assert "tt=" not in expr


def test_fmt_total_strips_separators():
    assert _fmt_total(" 1,234.56 ") == "1234.56"
    assert _fmt_total(None) == ""


# -- QR-sourced expresion (total wiring) ------------------------------------


_SAT_QR_URL = (
    "https://verificacfd.facturaelectronica.sat.gob.mx/default.aspx"
    "?id={uuid}&re={re}&rr={rr}&tt={tt}&fe=AbCdEf12"
)


def _qr_verification(uuid="UUID-ABC", re="EMI010101AA1", rr="REC020202BB2", tt="1234.56"):
    return {
        "qr_codes": [
            {"content": _SAT_QR_URL.format(uuid=uuid, re=re, rr=rr, tt=tt), "is_url": True}
        ]
    }


def test_sat_qr_params_extracts_expresion():
    # match is case-insensitive on the UUID
    qr = fv._sat_qr_params(_qr_verification(), "uuid-abc")
    assert qr == {"re": "EMI010101AA1", "rr": "REC020202BB2", "tt": "1234.56"}


def test_sat_qr_params_none_when_uuid_mismatch():
    assert fv._sat_qr_params(_qr_verification(uuid="OTHER"), "UUID-ABC") is None


def test_sat_qr_params_none_without_usable_qr():
    assert fv._sat_qr_params(None, "UUID-ABC") is None
    assert fv._sat_qr_params({"qr_codes": []}, "UUID-ABC") is None
    # a QR with the right id but no re/rr (not a CFDI verification QR) is ignored
    assert (
        fv._sat_qr_params({"qr_codes": [{"content": "https://x.mx/?id=UUID-ABC"}]}, "UUID-ABC")
        is None
    )


def test_gather_inputs_prefers_qr_expresion(db_factory):
    doc_id = _seed(
        db_factory,
        cfdi_uuid="UUID-ABC",
        verification=_qr_verification(
            uuid="UUID-ABC", re="QRE940101AAA", rr="QRR950202BBB", tt="9999.99"
        ),
    )
    db = db_factory()
    try:
        inputs = fv._gather_inputs(db, doc_id)
    finally:
        db.close()
    assert inputs.cfdi_uuid == "UUID-ABC"
    assert inputs.emisor_rfc == "QRE940101AAA"
    assert inputs.receptor_rfc == "QRR950202BBB"
    assert inputs.total == "9999.99"


def test_gather_inputs_falls_back_without_qr(db_factory):
    doc_id = _seed(db_factory, cfdi_uuid="UUID-ABC", verification=None)
    db = db_factory()
    try:
        inputs = fv._gather_inputs(db, doc_id)
    finally:
        db.close()
    assert inputs.cfdi_uuid == "UUID-ABC"
    assert inputs.total is None
    # falls back to the vendor/client RFCs (normalized, non-empty)
    assert inputs.emisor_rfc and inputs.receptor_rfc


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
        insp = db.scalar(select(DocumentInspection).where(DocumentInspection.document_id == doc_id))
        insp.risk_reasons = [{"code": "producer_blocklisted", "severity": "high", "detail_es": "x"}]
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
    monkeypatch.setattr(fv, "_lookup_cache", MagicMock(side_effect=RuntimeError("db down")))
    db = db_factory()
    try:
        out = fv.verify_document_folio(db, doc_id)
    finally:
        db.close()
    assert out["verified"] is True
    assert out["status"] == "no_existe"
    assert out["from_cache"] is False
