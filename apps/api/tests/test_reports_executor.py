"""Phase 3.3b — Executor + SSE generation tests.

Coverage:
- Happy-path streaming: SSE event sequence + final ReportVersion shape.
- Audience-based PII redaction at the per-block boundary.
- ai_recommendation block receives upstream summaries (proves the
  in-flight grounding wiring).
- ReportVersion persistence pinned to the snapshot id.

The SSE response is read line-by-line via TestClient's stream API,
parsed into (event_name, data) tuples for assertions.
"""

from __future__ import annotations

import json
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    Membership,
    Organization,
    ReportVersion,
    User,
    entities,  # noqa: F401
)
from app.services.auth import hash_password


@pytest.fixture(autouse=True)
def force_mock(monkeypatch):
    monkeypatch.setenv("CHECKWISE_LLM_BACKEND", "mock")
    from app.core import config as cfg

    cfg.get_settings.cache_clear()


@pytest.fixture
def db_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def api_client(db_factory) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        db = db_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _seed_admin(db_factory) -> tuple[str, str]:
    db = db_factory()
    try:
        u = User(
            email="exec@gen.test",
            password_hash=hash_password("ExecTest!2026"),
            full_name="Exec",
            status="active",
        )
        db.add(u)
        db.flush()
        org = Organization(name="LS", kind="internal")
        db.add(org)
        db.flush()
        db.add(
            Membership(
                user_id=u.id, organization_id=org.id, role="internal_admin", status="active"
            )
        )
        db.commit()
        return "ExecTest!2026", u.email
    finally:
        db.close()


def _login(api_client, email: str, pw: str) -> str:
    resp = api_client.post("/api/v1/auth/login", json={"email": email, "password": pw})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    """Parse a 'text/event-stream' response body into (event, data) tuples."""
    events: list[tuple[str, dict]] = []
    current_event: str | None = None
    current_data: list[str] = []

    def _flush() -> None:
        nonlocal current_event, current_data
        if current_event and current_data:
            payload = "\n".join(current_data)
            try:
                events.append((current_event, json.loads(payload)))
            except json.JSONDecodeError:
                pass
        current_event = None
        current_data = []

    for line in text.splitlines():
        if not line:
            _flush()
            continue
        if line.startswith("event: "):
            current_event = line.removeprefix("event: ").strip()
        elif line.startswith("data: "):
            current_data.append(line.removeprefix("data: "))
    _flush()
    return events


# ─── Happy path ──────────────────────────────────────────────────


def test_generate_streams_full_event_sequence(api_client, db_factory) -> None:
    pw, email = _seed_admin(db_factory)
    token = _login(api_client, email, pw)
    rep = api_client.post(
        "/api/v1/reports",
        headers=_h(token),
        json={"title": "Stream test", "audience": "internal_only"},
    ).json()
    report_id = rep["id"]

    resp = api_client.post(
        f"/api/v1/reports/{report_id}/generate",
        headers=_h(token),
        json={"prompt": "Resumen REPSE de mayo con riesgo SAT", "period": "2026-M05"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(resp.text)
    names = [name for name, _ in events]

    # First event is the plan; last is done.
    assert names[0] == "plan"
    assert names[-1] == "done"
    # version_saved is the second-to-last event (executor emits it
    # immediately before done).
    assert names[-2] == "version_saved"

    # Each block in the plan must produce block_start → block_data →
    # block_complete in order.
    plan_event = next(e for e in events if e[0] == "plan")
    plan_blocks = plan_event[1]["plan"]["blocks"]
    for block in plan_blocks:
        ids_in_block = [
            n for n, d in events if d.get("block_id") == block["id"]
        ]
        # At minimum: block_start, block_data, block_complete.
        # Some blocks add ai_summary_delta chunks in between.
        assert ids_in_block[:2] == ["block_start", "block_data"]
        assert "block_complete" in ids_in_block

    # A ReportVersion was persisted with version_number = 2 (initial v1
    # came from the report-create endpoint).
    saved = next(e for e in events if e[0] == "version_saved")[1]
    assert saved["version_number"] == 2

    # The persisted version content_json has the rendered blocks.
    db = db_factory()
    try:
        v = db.scalar(
            select(ReportVersion).where(ReportVersion.id == saved["version_id"])
        )
        assert v is not None
        assert v.generated_by == "ai"
        assert v.plan_json is not None
        rendered = v.content_json["blocks"]
        assert len(rendered) == len(plan_blocks)
        # executive_summary should carry an ai_summary (mock client
        # yields canned text).
        es = next((b for b in rendered if b["type"] == "executive_summary"), None)
        assert es is not None
        assert es["ai_summary"] is not None
        assert es["ai_summary"]["text"]  # non-empty
    finally:
        db.close()


def test_generate_persists_version_pinned_to_snapshot(api_client, db_factory) -> None:
    pw, email = _seed_admin(db_factory)
    token = _login(api_client, email, pw)
    rep = api_client.post(
        "/api/v1/reports",
        headers=_h(token),
        json={"title": "Snap test", "audience": "internal_only"},
    ).json()

    resp = api_client.post(
        f"/api/v1/reports/{rep['id']}/generate",
        headers=_h(token),
        json={"prompt": "Resumen"},
    )
    events = _parse_sse(resp.text)
    done = next(e for e in events if e[0] == "done")[1]
    saved = next(e for e in events if e[0] == "version_saved")[1]
    assert done["snapshot_id"]

    db = db_factory()
    try:
        v = db.scalar(
            select(ReportVersion).where(ReportVersion.id == saved["version_id"])
        )
        assert v is not None
        assert v.source_snapshot_id == done["snapshot_id"]
    finally:
        db.close()


def test_executor_redact_masks_vendor_identity_by_audience() -> None:
    """Unit test of the executor's vendor-identity sanitizer.

    Vendor name/RFC in structured block data are masked only for the
    audiences that must not see *named* providers:

      • internal_only  → pass through (staff see everything).
      • client_facing  → pass through (the client owns its own
        providers; a nameless matrix is useless — 2026-06 fix).
      • vendor_facing  → masked (a provider must not receive a
        portfolio of *other* named vendors).
      • external_signed → masked (public/signed surfaces stay
        conservative).
    """
    from app.constants.reports import ReportAudience
    from app.services.reports.executor import _redact_for_audience

    def fresh_matrix() -> dict:
        return {
            "rows": [
                {
                    "vendor_id": "v1",
                    "vendor_name": "Distribuidora Nogal",
                    "vendor_rfc": "DNG890101AB1",
                    "risk_score": 75,
                    "cells": {},
                    "last_event_at": "",
                },
            ],
            "totals": {},
        }

    # internal_only + client_facing: pass through unchanged (same ref).
    for audience in (
        ReportAudience.INTERNAL_ONLY,
        ReportAudience.CLIENT_FACING,
    ):
        data = fresh_matrix()
        assert (
            _redact_for_audience("vendor_risk_matrix", data, audience) is data
        ), f"{audience} must see named providers"

    # vendor_facing + external_signed: vendor_name + vendor_rfc -> None.
    for audience in (
        ReportAudience.VENDOR_FACING,
        ReportAudience.EXTERNAL_SIGNED,
    ):
        data = fresh_matrix()
        redacted = _redact_for_audience("vendor_risk_matrix", data, audience)
        assert redacted is not None
        assert redacted["rows"][0]["vendor_name"] is None, audience
        assert redacted["rows"][0]["vendor_rfc"] is None, audience
        # Risk score still present (not identity).
        assert redacted["rows"][0]["risk_score"] == 75
        # Original untouched (deep-copied before masking).
        assert data["rows"][0]["vendor_name"] == "Distribuidora Nogal"

    # compliance_overview carries the same vendor identity under
    # ``by_vendor.*`` — masked for vendor_facing, kept for client_facing.
    def fresh_overview() -> dict:
        return {
            "by_vendor": [
                {"vendor_id": "v1", "vendor_name": "Nogal", "vendor_rfc": "DNG1", "compliance_pct": 40},
            ],
        }

    kept = _redact_for_audience(
        "compliance_overview", fresh_overview(), ReportAudience.CLIENT_FACING
    )
    assert kept["by_vendor"][0]["vendor_name"] == "Nogal"
    masked = _redact_for_audience(
        "compliance_overview", fresh_overview(), ReportAudience.VENDOR_FACING
    )
    assert masked["by_vendor"][0]["vendor_name"] is None
    assert masked["by_vendor"][0]["vendor_rfc"] is None
    # Non-identity field survives.
    assert masked["by_vendor"][0]["compliance_pct"] == 40


def test_executor_redact_handles_executive_summary_scope_label() -> None:
    from app.constants.reports import ReportAudience
    from app.services.reports.executor import _redact_for_audience

    es_data = {
        "period_label": "2026-M05",
        "scope_label": "ACME SA · Distribuidora Nogal",
        "headline_metrics": {"completion_pct": 72},
    }

    # client_facing keeps the scope label (the client owns this scope).
    kept = _redact_for_audience(
        "executive_summary", es_data, ReportAudience.CLIENT_FACING
    )
    assert kept is es_data
    assert kept["scope_label"] == "ACME SA · Distribuidora Nogal"

    # vendor_facing masks it (a provider must not see the client/portfolio
    # label of a report it doesn't own).
    redacted = _redact_for_audience(
        "executive_summary", es_data, ReportAudience.VENDOR_FACING
    )
    assert redacted is not None
    assert redacted["scope_label"] is None
    # period_label survives — not identity.
    assert redacted["period_label"] == "2026-M05"
    assert redacted["headline_metrics"]["completion_pct"] == 72


def test_generate_rejects_unknown_report(api_client, db_factory) -> None:
    pw, email = _seed_admin(db_factory)
    token = _login(api_client, email, pw)

    resp = api_client.post(
        "/api/v1/reports/00000000-0000-0000-0000-000000000000/generate",
        headers=_h(token),
        json={"prompt": "x"},
    )
    assert resp.status_code == 404


def test_exec_summary_sentence_is_name_free_and_scope_aware() -> None:
    """The deterministic cover recap is templated from computed values
    (no LLM) and carries no client/vendor name, so it's safe for every
    audience and the factual headline can't be hallucinated."""
    from app.constants.reports import ReportAudience
    from app.services.reports.blocks.data_fetchers import _exec_summary_sentence
    from app.services.reports.context import ReportScope

    client_scope = ReportScope(
        organization_id="o",
        audience=ReportAudience.CLIENT_FACING,
        client_id="c",
        vendor_id=None,
        period="2026-M05",
    )
    s = _exec_summary_sentence(
        scope=client_scope,
        completion_pct=72,
        vendors_at_risk=3,
        submissions_in_review=4,
    )
    assert "72%" in s
    assert "el portafolio" in s
    assert "3 proveedores requieren atención" in s
    assert "4 documentos en revisión" in s
    # Name-free: the recap never embeds a client/vendor label.
    assert "·" not in s

    vendor_scope = ReportScope(
        organization_id="o",
        audience=ReportAudience.VENDOR_FACING,
        client_id="c",
        vendor_id="v",
        period="2026-M05",
    )
    sv = _exec_summary_sentence(
        scope=vendor_scope,
        completion_pct=50,
        vendors_at_risk=3,
        submissions_in_review=0,
    )
    assert "tu expediente" in sv
    assert "50%" in sv
    # The 'proveedores' clause is suppressed at vendor scope.
    assert "proveedores" not in sv


def test_completion_and_risk_applies_tenant_scope() -> None:
    """Regression: _completion_and_risk once reassigned a loop local with
    .where(...) (a no-op on immutable statements), so its counts ran
    UNSCOPED across all tenants. Assert every count statement now carries
    the client_id filter."""
    from app.constants.reports import ReportAudience
    from app.services.reports.blocks.data_fetchers import _completion_and_risk
    from app.services.reports.context import ReportScope

    class _SpyDB:
        def __init__(self) -> None:
            self.stmts: list = []

        def scalar(self, stmt):  # noqa: ANN001
            self.stmts.append(stmt)
            return 0

    spy = _SpyDB()
    scope = ReportScope(
        organization_id="o",
        audience=ReportAudience.CLIENT_FACING,
        client_id="CID-UNIQ-123",
        vendor_id=None,
    )
    _completion_and_risk(spy, scope)
    assert len(spy.stmts) == 3
    for stmt in spy.stmts:
        sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "CID-UNIQ-123" in sql, "client scope must be applied to every count"
