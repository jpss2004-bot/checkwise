"""R6 — copilot block-composition suggestions.

Covers POST /api/v1/reports/{id}/copilot/suggest-blocks across:
- happy path: queued mock returns two valid suggestions with rationales
- 404 on unknown report
- unknown block type emitted by the model is dropped server-side
- invalid config (fails catalog JSON schema) is dropped
- empty rationale is dropped (UI never sees a card without explanation)
- singleton dedup: executive_summary already on the canvas → skipped

All under DeterministicMockLLMClient — CI never calls Anthropic.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    Membership,
    Organization,
    User,
    entities,  # noqa: F401
)
from app.services.auth import hash_password
from app.services.reports.llm.base import PlannerToolCall
from app.services.reports.llm.mock_client import DeterministicMockLLMClient


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
        sess = db_factory()
        try:
            yield sess
        finally:
            sess.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _seed_admin(db_factory):
    db = db_factory()
    try:
        u = User(
            email="suggest@test",
            password_hash=hash_password("SuggestTest!2026"),
            full_name="Suggest",
            status="active",
        )
        db.add(u)
        db.flush()
        org = Organization(name="LS-Suggest", kind="internal")
        db.add(org)
        db.flush()
        db.add(
            Membership(
                user_id=u.id,
                organization_id=org.id,
                role="internal_admin",
                status="active",
            )
        )
        db.commit()
        return "SuggestTest!2026", u.email
    finally:
        db.close()


def _login(api_client, email, pw):
    resp = api_client.post(
        "/api/v1/auth/login", json={"email": email, "password": pw}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _create_report(api_client, token, audience: str = "internal_only") -> str:
    r = api_client.post(
        "/api/v1/reports",
        headers=_h(token),
        json={"title": "Suggest test", "audience": audience},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _with_mock(mock, api_client, db_factory, body_factory):
    """Patch get_llm_client in the reports module to return ``mock``
    for one request. Mirrors the helper used by the planner test."""
    from app.api.v1 import reports as reports_module

    # Restore get_db override since we cleared it on entry.
    def override_get_db() -> Generator[Session, None, None]:
        sess = db_factory()
        try:
            yield sess
        finally:
            sess.close()

    app.dependency_overrides[get_db] = override_get_db
    target = reports_module.__dict__
    original = target["get_llm_client"]
    target["get_llm_client"] = lambda: mock
    try:
        return body_factory(api_client)
    finally:
        target["get_llm_client"] = original


# ─── Happy path ──────────────────────────────────────────────────


def test_suggest_blocks_returns_validated_suggestions_with_rationale(
    api_client, db_factory
):
    pw, email = _seed_admin(db_factory)
    token = _login(api_client, email, pw)
    rid = _create_report(api_client, token)

    mock = DeterministicMockLLMClient()
    mock.next_plan(
        [
            PlannerToolCall(
                id="s1",
                name="kpi_strip",
                arguments={
                    "metrics": [
                        {
                            "label": "Cumplimiento",
                            "metric_key": "completion_pct",
                            "format": "percent",
                        }
                    ],
                    "_rationale": "Da una métrica de un vistazo arriba del lienzo.",
                },
            ),
            PlannerToolCall(
                id="s2",
                name="prioritized_actions",
                arguments={
                    "max_actions": 3,
                    "_rationale": "Lista accionable para cerrar el periodo.",
                },
            ),
        ],
        rationale="Dos refuerzos para el reporte.",
    )

    def _do(client):
        return client.post(
            f"/api/v1/reports/{rid}/copilot/suggest-blocks",
            headers=_h(token),
            json={
                "intent": "Sugiéreme bloques para reforzar este reporte",
                "canvas_summary": {"blocks": [{"type": "executive_summary"}]},
            },
        )

    resp = _with_mock(mock, api_client, db_factory, _do)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    types = [s["type"] for s in body["suggestions"]]
    assert types == ["kpi_strip", "prioritized_actions"]
    # Rationale lifted out of the args, not left in config.
    assert all(s["rationale"] for s in body["suggestions"])
    assert all("_rationale" not in s["config"] for s in body["suggestions"])
    assert body["llm_backend"] == "mock"


# ─── Validation drops ────────────────────────────────────────────


def test_suggest_blocks_drops_unknown_type(api_client, db_factory):
    pw, email = _seed_admin(db_factory)
    token = _login(api_client, email, pw)
    rid = _create_report(api_client, token)

    mock = DeterministicMockLLMClient()
    mock.next_plan(
        [
            PlannerToolCall(
                id="bad",
                name="space_station_status",  # not in the registry
                arguments={"_rationale": "irrelevante"},
            ),
            PlannerToolCall(
                id="good",
                name="kpi_strip",
                arguments={
                    "metrics": [
                        {
                            "label": "Cumplimiento",
                            "metric_key": "completion_pct",
                            "format": "percent",
                        }
                    ],
                    "_rationale": "Métrica clave.",
                },
            ),
        ]
    )

    def _do(client):
        return client.post(
            f"/api/v1/reports/{rid}/copilot/suggest-blocks",
            headers=_h(token),
            json={
                "intent": "Refuerza el reporte",
                "canvas_summary": {"blocks": []},
            },
        )

    resp = _with_mock(mock, api_client, db_factory, _do)
    assert resp.status_code == 200, resp.text
    types = [s["type"] for s in resp.json()["suggestions"]]
    assert types == ["kpi_strip"]


def test_suggest_blocks_drops_invalid_config(api_client, db_factory):
    pw, email = _seed_admin(db_factory)
    token = _login(api_client, email, pw)
    rid = _create_report(api_client, token)

    mock = DeterministicMockLLMClient()
    mock.next_plan(
        [
            PlannerToolCall(
                id="bad",
                name="kpi_strip",
                # ``metrics`` is required by the catalog schema; omit it.
                arguments={"_rationale": "Métrica que el modelo olvidó."},
            ),
            PlannerToolCall(
                id="good",
                name="text",
                arguments={
                    "body": "Cierre del periodo.",
                    "_rationale": "Cierra con una conclusión narrativa.",
                },
            ),
        ]
    )

    def _do(client):
        return client.post(
            f"/api/v1/reports/{rid}/copilot/suggest-blocks",
            headers=_h(token),
            json={"intent": "Refuerza", "canvas_summary": {"blocks": []}},
        )

    resp = _with_mock(mock, api_client, db_factory, _do)
    assert resp.status_code == 200, resp.text
    types = [s["type"] for s in resp.json()["suggestions"]]
    assert types == ["text"]


def test_suggest_blocks_drops_empty_rationale(api_client, db_factory):
    pw, email = _seed_admin(db_factory)
    token = _login(api_client, email, pw)
    rid = _create_report(api_client, token)

    mock = DeterministicMockLLMClient()
    mock.next_plan(
        [
            PlannerToolCall(
                id="naked",
                name="divider",
                arguments={"label": "Detalle"},  # no rationale at all
            ),
            PlannerToolCall(
                id="ok",
                name="divider",
                arguments={
                    "label": "Cierre",
                    "_rationale": "Separa visualmente el cierre del cuerpo.",
                },
            ),
        ]
    )

    def _do(client):
        return client.post(
            f"/api/v1/reports/{rid}/copilot/suggest-blocks",
            headers=_h(token),
            json={"intent": "Estructura", "canvas_summary": {"blocks": []}},
        )

    resp = _with_mock(mock, api_client, db_factory, _do)
    assert resp.status_code == 200, resp.text
    suggestions = resp.json()["suggestions"]
    assert len(suggestions) == 1
    assert suggestions[0]["config"]["label"] == "Cierre"


def test_suggest_blocks_dedups_singletons(api_client, db_factory):
    pw, email = _seed_admin(db_factory)
    token = _login(api_client, email, pw)
    rid = _create_report(api_client, token)

    mock = DeterministicMockLLMClient()
    mock.next_plan(
        [
            PlannerToolCall(
                id="dup",
                name="executive_summary",
                arguments={
                    "focus": "compliance",
                    "include_metrics": True,
                    "_rationale": "Resumen ejecutivo de apertura.",
                },
            ),
            PlannerToolCall(
                id="ok",
                name="kpi_strip",
                arguments={
                    "metrics": [
                        {
                            "label": "Cumplimiento",
                            "metric_key": "completion_pct",
                            "format": "percent",
                        }
                    ],
                    "_rationale": "Métrica de apertura.",
                },
            ),
        ]
    )

    def _do(client):
        return client.post(
            f"/api/v1/reports/{rid}/copilot/suggest-blocks",
            headers=_h(token),
            json={
                "intent": "Refuerza",
                "canvas_summary": {
                    "blocks": [{"type": "executive_summary"}]
                },
            },
        )

    resp = _with_mock(mock, api_client, db_factory, _do)
    assert resp.status_code == 200, resp.text
    types = [s["type"] for s in resp.json()["suggestions"]]
    assert "executive_summary" not in types
    assert "kpi_strip" in types


# ─── 404 ─────────────────────────────────────────────────────────


def test_suggest_blocks_404_for_unknown_report(api_client, db_factory):
    pw, email = _seed_admin(db_factory)
    token = _login(api_client, email, pw)
    resp = api_client.post(
        "/api/v1/reports/00000000-0000-0000-0000-000000000000"
        "/copilot/suggest-blocks",
        headers=_h(token),
        json={"intent": "x", "canvas_summary": {"blocks": []}},
    )
    assert resp.status_code == 404
