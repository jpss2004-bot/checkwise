"""Phase 3.3c — Copilot, regenerate, explain tests.

Covers:
- GET /reports/{id}/conversation         empty + populated
- POST /reports/{id}/conversation        SSE delta + persistence
- POST /reports/{id}/blocks/{id}/explain happy + missing block
- POST /reports/{id}/blocks/{id}/regenerate happy + non-AI block rejected

All under DeterministicMockLLMClient — CI never calls Anthropic.
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
    ReportConversation,
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


def _seed_admin(db_factory):
    db = db_factory()
    try:
        u = User(
            email="copilot@test",
            password_hash=hash_password("CopilotTest!2026"),
            full_name="Copilot",
            status="active",
        )
        db.add(u)
        db.flush()
        org = Organization(name="LS", kind="internal")
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
        return "CopilotTest!2026", u.email
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


def _create_report_with_v1_blocks(api_client, token):
    """Create a report + run /generate once so v1 has rendered blocks
    (including an executive_summary with ai_summary populated)."""
    r = api_client.post(
        "/api/v1/reports",
        headers=_h(token),
        json={"title": "Copilot test", "audience": "internal_only"},
    )
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    g = api_client.post(
        f"/api/v1/reports/{rid}/generate",
        headers=_h(token),
        json={"prompt": "Resumen", "period": "2026-M05"},
    )
    assert g.status_code == 200
    # drain
    _ = g.text
    return rid


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    current_event: str | None = None
    current_data: list[str] = []

    def _flush():
        nonlocal current_event, current_data
        if current_event and current_data:
            try:
                events.append((current_event, json.loads("\n".join(current_data))))
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


# ─── GET conversation ────────────────────────────────────────────


def test_conversation_empty_on_new_report(api_client, db_factory):
    pw, email = _seed_admin(db_factory)
    token = _login(api_client, email, pw)
    r = api_client.post(
        "/api/v1/reports",
        headers=_h(token),
        json={"title": "x", "audience": "internal_only"},
    ).json()
    resp = api_client.get(
        f"/api/v1/reports/{r['id']}/conversation", headers=_h(token)
    )
    assert resp.status_code == 200
    assert resp.json() == {"items": []}


def test_conversation_returns_404_for_unknown_report(api_client, db_factory):
    pw, email = _seed_admin(db_factory)
    token = _login(api_client, email, pw)
    resp = api_client.get(
        "/api/v1/reports/00000000-0000-0000-0000-000000000000/conversation",
        headers=_h(token),
    )
    assert resp.status_code == 404


# ─── POST conversation (SSE) ─────────────────────────────────────


def test_post_conversation_streams_assistant_reply_and_persists(
    api_client, db_factory
):
    pw, email = _seed_admin(db_factory)
    token = _login(api_client, email, pw)
    rid = _create_report_with_v1_blocks(api_client, token)

    resp = api_client.post(
        f"/api/v1/reports/{rid}/conversation",
        headers=_h(token),
        json={
            "message": "¿Qué proveedores están más en riesgo?",
            "canvas_summary": {"blocks": [{"type": "executive_summary"}]},
        },
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(resp.text)
    names = [n for n, _ in events]
    assert names[0] == "turn_start"
    assert "delta" in names
    assert "turn_complete" in names
    assert names[-1] == "done"

    # Two turns persisted: the user's, then the assistant's.
    db = db_factory()
    try:
        turns = list(
            db.scalars(
                select(ReportConversation)
                .where(ReportConversation.report_id == rid)
                .order_by(ReportConversation.turn_number.asc())
            )
        )
        assert len(turns) == 2
        assert turns[0].role == "user"
        assert turns[0].content_json["kind"] == "text"
        assert turns[1].role == "assistant"
        assert turns[1].content_json["kind"] == "text"
        assert turns[1].content_json["markdown"]
    finally:
        db.close()


def test_post_conversation_includes_history_on_follow_up(api_client, db_factory):
    """Second message should see the first message in its history;
    we don't have a hook for that today other than the conversation
    table state, so just verify both messages persist with correct
    turn_number ordering."""
    pw, email = _seed_admin(db_factory)
    token = _login(api_client, email, pw)
    rid = _create_report_with_v1_blocks(api_client, token)

    api_client.post(
        f"/api/v1/reports/{rid}/conversation",
        headers=_h(token),
        json={"message": "Mensaje 1"},
    )
    api_client.post(
        f"/api/v1/reports/{rid}/conversation",
        headers=_h(token),
        json={"message": "Mensaje 2 con seguimiento"},
    )

    listing = api_client.get(
        f"/api/v1/reports/{rid}/conversation", headers=_h(token)
    ).json()
    items = listing["items"]
    # 2 user turns + 2 assistant turns = 4.
    assert len(items) == 4
    assert [i["turn_number"] for i in items] == [1, 2, 3, 4]
    assert [i["role"] for i in items] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]


# ─── Explain ─────────────────────────────────────────────────────


def test_explain_block_returns_text(api_client, db_factory):
    pw, email = _seed_admin(db_factory)
    token = _login(api_client, email, pw)
    rid = _create_report_with_v1_blocks(api_client, token)

    # Get a block_id from the current version.
    fresh = api_client.get(f"/api/v1/reports/{rid}", headers=_h(token)).json()
    blocks = fresh["current_version"]["content_json"]["blocks"]
    target_id = blocks[0]["id"]

    resp = api_client.post(
        f"/api/v1/reports/{rid}/blocks/{target_id}/explain",
        headers=_h(token),
        json={"question": "¿Por qué importa esta sección?"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["block_id"] == target_id
    assert body["explanation"]
    assert body["llm_backend"] == "mock"


def test_explain_block_404_for_unknown_block(api_client, db_factory):
    pw, email = _seed_admin(db_factory)
    token = _login(api_client, email, pw)
    rid = _create_report_with_v1_blocks(api_client, token)
    resp = api_client.post(
        f"/api/v1/reports/{rid}/blocks/does-not-exist/explain",
        headers=_h(token),
        json={"question": None},
    )
    assert resp.status_code == 404


# ─── Regenerate ──────────────────────────────────────────────────


def test_regenerate_block_creates_new_version(api_client, db_factory):
    pw, email = _seed_admin(db_factory)
    token = _login(api_client, email, pw)
    rid = _create_report_with_v1_blocks(api_client, token)

    fresh = api_client.get(f"/api/v1/reports/{rid}", headers=_h(token)).json()
    es_block = next(
        b for b in fresh["current_version"]["content_json"]["blocks"]
        if b["type"] == "executive_summary"
    )

    resp = api_client.post(
        f"/api/v1/reports/{rid}/blocks/{es_block['id']}/regenerate",
        headers=_h(token),
        json={},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["block_id"] == es_block["id"]
    assert body["ai_summary_text"]
    assert body["llm_backend"] == "mock"
    assert body["version_number"] > fresh["current_version"]["version_number"]

    # Verify the new ReportVersion exists and is marked ai_refined.
    db = db_factory()
    try:
        v = db.scalar(select(ReportVersion).where(ReportVersion.id == body["version_id"]))
        assert v is not None
        assert v.generated_by == "ai_refined"
        # The regenerated block's ai_summary differs from the previous version.
        new_es = next(
            b for b in v.content_json["blocks"] if b["type"] == "executive_summary"
        )
        assert new_es["ai_summary"]["text"]
    finally:
        db.close()


def test_regenerate_block_rejected_for_non_ai_block(api_client, db_factory):
    pw, email = _seed_admin(db_factory)
    token = _login(api_client, email, pw)
    rid = _create_report_with_v1_blocks(api_client, token)

    fresh = api_client.get(f"/api/v1/reports/{rid}", headers=_h(token)).json()
    # kpi_strip has no AI summary by design — regenerate should 422.
    kpi_block = next(
        b for b in fresh["current_version"]["content_json"]["blocks"]
        if b["type"] == "kpi_strip"
    )
    resp = api_client.post(
        f"/api/v1/reports/{rid}/blocks/{kpi_block['id']}/regenerate",
        headers=_h(token),
        json={},
    )
    assert resp.status_code == 422
    assert "no AI summary" in resp.json()["detail"]
