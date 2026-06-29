"""Behavior lock for ``_compute_compliance_history_6mo``.

Guards the audit perf refactor that collapses the per-month approval-rate
trend from 12 sequential COUNT queries into a single grouped query. The
contract: six-month window (oldest→newest), months with zero submissions
omitted, ``compliance_pct = round(approved / total * 100)``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.constants.statuses import DocumentStatus
from app.db.base import Base
from app.models.entities import (
    Client,
    Institution,
    Period,
    Requirement,
    Submission,
    Vendor,
)
from app.services.reports.blocks.data_fetchers import (
    _compute_compliance_history_6mo,
)
from app.core.time import today_mx


@pytest.fixture
def db_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def test_compliance_history_6mo_contract(db_factory):
    db = db_factory()
    today = today_mx()
    cur_y, cur_m = today.year, today.month
    pm, py = today.month - 1, today.year
    if pm == 0:
        pm, py = 12, py - 1

    client = Client(name="Cliente Trend", rfc="CTR260101AB1")
    db.add(client)
    db.flush()
    vendor = Vendor(client_id=client.id, name="Vendor Trend", rfc="VTR260101AB1")
    inst = Institution(code="IMSS-TREND", name="IMSS")
    period = Period(code="2026-TREND", period_type="mensual")
    db.add_all([vendor, inst, period])
    db.flush()
    req = Requirement(
        code="REQ-TREND",
        name="Requisito Trend",
        institution_id=inst.id,
        load_type="mensual",
        frequency="mensual",
        risk_level="medium",
    )
    db.add(req)
    db.flush()

    def mk(status_value: str, when: datetime) -> Submission:
        return Submission(
            client_id=client.id,
            vendor_id=vendor.id,
            period_id=period.id,
            institution_id=inst.id,
            requirement_id=req.id,
            load_type="mensual",
            status=status_value,
            created_at=when,
        )

    cur_dt = datetime(cur_y, cur_m, 15, 12, 0, tzinfo=UTC)
    pm_dt = datetime(py, pm, 15, 12, 0, tzinfo=UTC)
    db.add_all(
        [
            # current month: 2 approved / 3 total -> 67%
            mk(DocumentStatus.APROBADO.value, cur_dt),
            mk(DocumentStatus.APROBADO.value, cur_dt),
            mk(DocumentStatus.PENDIENTE_REVISION.value, cur_dt),
            # prior month: 1 approved / 2 total -> 50%
            mk(DocumentStatus.APROBADO.value, pm_dt),
            mk(DocumentStatus.PENDIENTE_REVISION.value, pm_dt),
        ]
    )
    db.commit()

    points = _compute_compliance_history_6mo(db, client.id)
    by_key = {p["month_key"]: p["compliance_pct"] for p in points}

    assert by_key.get(f"{cur_y:04d}-{cur_m:02d}") == 67
    assert by_key.get(f"{py:04d}-{pm:02d}") == 50
    # Zero-submission months are omitted (only the two seeded months appear),
    # and the series is ordered oldest -> newest.
    assert len(points) == 2
    keys = [p["month_key"] for p in points]
    assert keys == sorted(keys)


def test_compliance_history_6mo_empty_when_no_submissions(db_factory):
    db = db_factory()
    client = Client(name="Cliente Vacío", rfc="CVA260101AB1")
    db.add(client)
    db.commit()
    assert _compute_compliance_history_6mo(db, client.id) == []
