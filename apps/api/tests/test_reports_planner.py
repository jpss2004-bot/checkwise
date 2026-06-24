"""Phase 3.3a — AI Planner tests.

Two test files in 3.3a:

- ``test_reports_planner.py``   (this) — happy-path coverage.
- ``test_reports_ai_safety.py`` — the safety suite. Tests cross-tenant
  isolation, prompt injection, hallucinated tool names, hallucinated
  IDs, empty-context behavior, audience redaction.

Both use the DeterministicMockLLMClient so behavior is reproducible.
The real Anthropic client is exercised only in local integration runs
when ANTHROPIC_API_KEY is set; CI never calls Anthropic.
"""

from __future__ import annotations

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
    ComplianceSnapshot,
    Membership,
    Organization,
    User,
    entities,  # noqa: F401 — register mappers
)
from app.services.auth import hash_password
from app.services.reports.llm.base import PlannerToolCall
from app.services.reports.llm.factory import get_llm_client
from app.services.reports.llm.mock_client import DeterministicMockLLMClient

# ─── Fixtures ────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def force_mock_llm(monkeypatch):
    """Every test runs against the deterministic mock. CI never calls
    Anthropic; tests stay free + reproducible.
    """
    monkeypatch.setenv("CHECKWISE_LLM_BACKEND", "mock")
    # Bust the cached settings so the env var actually takes effect.
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


# ─── Test helpers ────────────────────────────────────────────────


def _seed_admin(db_factory) -> tuple[str, str]:
    """Returns (password, email) of a seeded internal_admin user."""
    db = db_factory()
    try:
        user = User(
            email="adm@planner.test",
            password_hash=hash_password("PlannerTest!2026"),
            full_name="Planner Admin",
            status="active",
        )
        db.add(user)
        db.flush()
        org = Organization(name="LegalShelf Internal", kind="internal")
        db.add(org)
        db.flush()
        db.add(
            Membership(
                user_id=user.id, organization_id=org.id, role="operations_admin", status="active"
            )
        )
        db.commit()
        return "PlannerTest!2026", user.email
    finally:
        db.close()


def _login(api_client: TestClient, email: str, password: str) -> str:
    resp = api_client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_report(
    api_client: TestClient, token: str, *, title: str = "Test report"
) -> str:
    resp = api_client.post(
        "/api/v1/reports",
        headers=_h(token),
        json={"title": title, "audience": "internal_only"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ─── Happy path ──────────────────────────────────────────────────


def test_plan_endpoint_returns_structured_plan(
    api_client: TestClient, db_factory
) -> None:
    pw, email = _seed_admin(db_factory)
    token = _login(api_client, email, pw)
    report_id = _create_report(api_client, token)

    resp = api_client.post(
        f"/api/v1/reports/{report_id}/plan",
        headers=_h(token),
        json={
            "prompt": "Genera un reporte mensual de cumplimiento REPSE para los proveedores con SAT pendiente."
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Shape
    assert isinstance(body["blocks"], list)
    assert len(body["blocks"]) >= 1
    assert body["llm_backend"] == "mock"
    assert body["snapshot_id"]
    assert body["audience"] == "internal_only"
    assert "vendors_total" in body["scope_hint"]["metrics"]

    # Default mock plan includes executive_summary (always; carries
    # its own KPI ribbon via ``include_metrics=True``) + risk matrix
    # when SAT keyword is present. M3 (2026-06-02) dropped the
    # standalone kpi_strip closer to avoid duplicating the in-block
    # ribbon on the cliente Resumen ejecutivo surface.
    types = [b["type"] for b in body["blocks"]]
    assert types[0] == "executive_summary"
    assert "vendor_risk_matrix" in types
    assert "kpi_strip" not in types

    # First block config validates against its catalog schema (mocked
    # values are catalog-compliant by construction).
    es = next(b for b in body["blocks"] if b["type"] == "executive_summary")
    assert es["config"]["focus"] in ("compliance", "risk", "expediente", "audit", "custom")
    assert isinstance(es["config"]["include_metrics"], bool)


def test_plan_persists_compliance_snapshot(
    api_client: TestClient, db_factory
) -> None:
    """The Context Assembler must persist a snapshot before the LLM
    call so the plan is auditable."""
    pw, email = _seed_admin(db_factory)
    token = _login(api_client, email, pw)
    report_id = _create_report(api_client, token)

    resp = api_client.post(
        f"/api/v1/reports/{report_id}/plan",
        headers=_h(token),
        json={"prompt": "Resumen ejecutivo de mayo 2026", "period": "2026-M05"},
    )
    assert resp.status_code == 200
    snapshot_id = resp.json()["snapshot_id"]

    db = db_factory()
    try:
        snap = db.scalar(
            select(ComplianceSnapshot).where(ComplianceSnapshot.id == snapshot_id)
        )
        assert snap is not None
        assert snap.scope_filter["period"] == "2026-M05"
        assert snap.scope_filter["audience"] == "internal_only"
        assert snap.data_hash, "data_hash must be set"
        assert snap.row_count >= 0
    finally:
        db.close()


def test_plan_explicit_via_queued_mock(api_client: TestClient, db_factory) -> None:
    """Push a specific plan into the mock and assert it survives
    validation + reaches the response intact. Confirms the mock's
    public ``next_plan`` API works end-to-end."""
    pw, email = _seed_admin(db_factory)
    token = _login(api_client, email, pw)
    report_id = _create_report(api_client, token)

    # Patch get_llm_client to return a configured mock for this call.
    mock = DeterministicMockLLMClient()
    mock.next_plan(
        [
            PlannerToolCall(
                id="b1",
                name="executive_summary",
                arguments={"focus": "audit", "include_metrics": False},
            ),
            PlannerToolCall(
                id="b2",
                name="text",
                arguments={"heading": "Contexto", "body": "Auditoría trimestral."},
            ),
        ],
        rationale="Plan auditado.",
    )

    from app.api.v1 import reports as reports_module

    app.dependency_overrides.clear()
    # Override get_db (was cleared) — re-bind for this test.
    def override_get_db() -> Generator[Session, None, None]:
        sess = db_factory()
        try:
            yield sess
        finally:
            sess.close()
    app.dependency_overrides[get_db] = override_get_db
    monkeypatch_target = reports_module.__dict__
    original = monkeypatch_target["get_llm_client"]
    monkeypatch_target["get_llm_client"] = lambda: mock
    try:
        resp = api_client.post(
            f"/api/v1/reports/{report_id}/plan",
            headers=_h(token),
            json={"prompt": "Audita el trimestre."},
        )
    finally:
        monkeypatch_target["get_llm_client"] = original
        app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    body = resp.json()
    types = [b["type"] for b in body["blocks"]]
    assert types == ["executive_summary", "text"]
    assert body["rationale"] == "Plan auditado."


# ─── Validation ──────────────────────────────────────────────────


def test_plan_rejects_unknown_report(api_client: TestClient, db_factory) -> None:
    pw, email = _seed_admin(db_factory)
    token = _login(api_client, email, pw)

    resp = api_client.post(
        "/api/v1/reports/00000000-0000-0000-0000-000000000000/plan",
        headers=_h(token),
        json={"prompt": "x"},
    )
    assert resp.status_code == 404


def test_plan_requires_auth(api_client: TestClient) -> None:
    resp = api_client.post(
        "/api/v1/reports/00000000-0000-0000-0000-000000000000/plan",
        json={"prompt": "x"},
    )
    assert resp.status_code == 401


def test_factory_returns_mock_when_backend_env_set() -> None:
    """When CHECKWISE_LLM_BACKEND=mock the factory returns the mock
    regardless of whether ANTHROPIC_API_KEY is present."""
    client = get_llm_client()
    assert client.name == "mock"
