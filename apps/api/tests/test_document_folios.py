"""Phase 2 keystone — document_folios model, intake population helper, and
the backfill. Pure in-memory SQLite; never touches a real DB."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
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
from app.services.document_folios import folio_pairs, persist_document_folios
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


# --- migration sanity ---


def test_migration_chains_off_base_head() -> None:
    path = Path(__file__).resolve().parents[1] / (
        "alembic/versions/0059_document_folio_index.py"
    )
    spec = importlib.util.spec_from_file_location("m0059", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == "0059_document_folio_index"
    assert mod.down_revision == "0055_perf_indexes_trgm_search_and_renewals"
