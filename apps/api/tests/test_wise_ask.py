"""Wise copilot — LLM ask endpoint coverage.

Covers ``POST /api/v1/portal/workspaces/{id}/wise/ask`` and the
underlying ``app.services.wise.ai.ask_wise`` service. The Anthropic
SDK is replaced with a stub that returns a fixed tool-use response
so the tests stay hermetic — no network, no API key needed.
"""

from __future__ import annotations

import itertools
from collections.abc import Generator
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    Client,
    ProviderWorkspace,
    User,
    Vendor,
    entities,  # noqa: F401 — register mappers
)
from app.services.auth import hash_password, issue_access_token
from app.services.wise.ai import (
    WiseCta,
    WiseStateDigest,
    ask_wise,
)

_user_seq = itertools.count(start=1)


# ─── Test fixture (mirrors the test_wise_events.py fixture) ────────


@pytest.fixture
def api_client(tmp_path) -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    previous_storage = settings.LOCAL_STORAGE_PATH
    settings.LOCAL_STORAGE_PATH = str(tmp_path / "storage")

    def override_get_db() -> Generator[Session, None, None]:
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.app.state.testing_session = testing_session  # type: ignore[attr-defined]
    try:
        yield client
    finally:
        app.dependency_overrides.clear()
        settings.LOCAL_STORAGE_PATH = previous_storage


def _setup_workspace(
    api_client: TestClient,
    *,
    vendor_name: str = "Servicios Ask SA",
    vendor_rfc: str = "ASK260512AB1",
    client_name: str = "Cliente Ask Demo",
    fresh_client: TestClient | None = None,
) -> dict:
    target_client = fresh_client or api_client
    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        seq = next(_user_seq)
        user = User(
            email=f"ask-{seq}@checkwise.test",
            password_hash=hash_password("CheckWiseTest!2026"),
            full_name=vendor_name,
            status="active",
            must_change_password=False,
        )
        db.add(user)
        db.flush()
        client_row = db.query(Client).filter_by(name=client_name).first()
        if client_row is None:
            client_row = Client(name=client_name)
            db.add(client_row)
            db.flush()
        vendor = Vendor(
            client_id=client_row.id,
            name=vendor_name,
            rfc=vendor_rfc.upper(),
            persona_type="moral",
        )
        db.add(vendor)
        db.flush()
        workspace = ProviderWorkspace(
            client_id=client_row.id,
            vendor_id=vendor.id,
            owner_user_id=user.id,
            persona_type="moral",
            display_name=vendor_name,
            access_token="placeholder",
        )
        db.add(workspace)
        db.commit()
        ws_id, user_id, user_email = workspace.id, user.id, user.email
    finally:
        db.close()

    token = issue_access_token(user_id=user_id, email=user_email, roles=[], orgs=[])
    target_client.cookies.clear()
    enter = target_client.post(
        "/api/v1/portal/enter",
        json={"workspace_id": ws_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert enter.status_code == 200, enter.text
    return {"workspace_id": ws_id, "bearer": token, "user_id": user_id}


def _digest_dict() -> dict:
    """A minimal-but-realistic state digest the dock would send."""
    return {
        "vendor_name": "Servicios Ask SA",
        "persona_type": "moral",
        "onboarding_completed": False,
        "compliance_pct": 35,
        "on_track": 5,
        "total_tracked": 14,
        "needs_action": 2,
        "in_review": 3,
        "completed_required": 4,
        "total_required": 9,
        "approved_count": 4,
        "pending_count": 5,
        "rejected_count": 1,
        "expired_count": 0,
        "next_action_titles": ["Sube tu Constancia Fiscal"],
        "upcoming_deadline_titles": ["INFONAVIT B1 2026"],
    }


def _ctas() -> list[dict]:
    return [
        {
            "id": "act-onboarding-constancia",
            "label": "Subir documento",
            "href": "/portal/upload?requirement_code=onboarding_constancia",
            "description": "Sube tu Constancia Fiscal",
        },
        {
            "id": "due-infonavit-b1",
            "label": "Ver obligación",
            "href": "/portal/upload?requirement_code=infonavit_b1",
            "description": "INFONAVIT B1 2026 — vence pronto",
        },
    ]


# ─── Service-level unit tests (no FastAPI) ─────────────────────────


def _stub_anthropic(body: str, cta_id: str | None) -> SimpleNamespace:
    """Build a SimpleNamespace mimicking the anthropic SDK
    ``messages.create`` return shape: an object with a ``content``
    list of tool-use blocks."""

    class _Block:
        type = "tool_use"
        name = "respond_to_provider"
        input = {"body": body, "cta_id": cta_id or ""}

    return SimpleNamespace(content=[_Block()])


def test_service_returns_llm_reply_with_valid_cta() -> None:
    digest = WiseStateDigest(
        vendor_name="Servicios Ask SA",
        persona_type="moral",
        onboarding_completed=False,
        compliance_pct=35,
        on_track=5,
        total_tracked=14,
        needs_action=2,
        in_review=3,
        completed_required=4,
        total_required=9,
        approved_count=4,
        pending_count=5,
        rejected_count=1,
        expired_count=0,
        next_action_titles=("Sube tu Constancia",),
        upcoming_deadline_titles=("INFONAVIT B1",),
    )
    ctas = [
        WiseCta(
            id="act-constancia",
            label="Subir documento",
            href="/portal/upload?requirement_code=constancia",
            description="Sube tu Constancia",
        ),
    ]

    class FakeClient:
        def __init__(self) -> None:
            self.messages = SimpleNamespace(
                create=lambda **_: _stub_anthropic(
                    body="Te recomiendo subir tu Constancia primero.",
                    cta_id="act-constancia",
                )
            )

    result = ask_wise(
        prompt="¿qué hago primero?",
        digest=digest,
        ctas=ctas,
        client=FakeClient(),  # type: ignore[arg-type]
    )
    assert result.source == "llm"
    assert "Constancia" in result.body
    assert result.cta_id == "act-constancia"
    assert result.cta_label == "Subir documento"
    assert result.cta_href == "/portal/upload?requirement_code=constancia"


def test_service_drops_invented_cta_id() -> None:
    digest = WiseStateDigest(
        vendor_name="X",
        persona_type="moral",
        onboarding_completed=True,
        compliance_pct=100,
        on_track=10,
        total_tracked=10,
        needs_action=0,
        in_review=0,
        completed_required=10,
        total_required=10,
        approved_count=10,
        pending_count=0,
        rejected_count=0,
        expired_count=0,
        next_action_titles=(),
        upcoming_deadline_titles=(),
    )

    class FakeClient:
        def __init__(self) -> None:
            self.messages = SimpleNamespace(
                create=lambda **_: _stub_anthropic(
                    body="Estás al día.", cta_id="cta-i-made-up"
                )
            )

    result = ask_wise(
        prompt="cómo voy?",
        digest=digest,
        ctas=[],
        client=FakeClient(),  # type: ignore[arg-type]
    )
    # Body survives, invented cta is silently dropped.
    assert result.source == "llm"
    assert result.body == "Estás al día."
    assert result.cta_id is None
    assert result.cta_label is None
    assert result.cta_href is None


def test_service_falls_back_when_no_api_key() -> None:
    digest = WiseStateDigest(
        vendor_name="X",
        persona_type="moral",
        onboarding_completed=False,
        compliance_pct=0,
        on_track=0,
        total_tracked=1,
        needs_action=1,
        in_review=0,
        completed_required=0,
        total_required=1,
        approved_count=0,
        pending_count=1,
        rejected_count=0,
        expired_count=0,
        next_action_titles=(),
        upcoming_deadline_titles=(),
    )
    # api_key="" forces the no-key fallback path even if the test
    # environment happens to have ANTHROPIC_API_KEY set globally.
    result = ask_wise(
        prompt="¿qué sigue?",
        digest=digest,
        ctas=[],
        api_key="",
    )
    assert result.source == "fallback"
    assert result.cta_href is None
    assert result.body  # non-empty user-facing copy


def test_service_rejects_too_long_prompt() -> None:
    digest = WiseStateDigest(
        vendor_name="X",
        persona_type="moral",
        onboarding_completed=False,
        compliance_pct=0,
        on_track=0,
        total_tracked=1,
        needs_action=0,
        in_review=0,
        completed_required=0,
        total_required=1,
        approved_count=0,
        pending_count=1,
        rejected_count=0,
        expired_count=0,
        next_action_titles=(),
        upcoming_deadline_titles=(),
    )
    result = ask_wise(prompt="a" * 600, digest=digest, ctas=[], api_key="")
    assert result.source == "fallback"
    assert "muy larga" in result.body


# ─── Endpoint-level tests ──────────────────────────────────────────


def test_ask_endpoint_returns_llm_reply(api_client: TestClient) -> None:
    """Happy path: the endpoint persists nothing but echoes the
    service's structured reply back to the dock."""
    ws = _setup_workspace(api_client)

    class FakeClient:
        def __init__(self, **_: object) -> None:
            self.messages = SimpleNamespace(
                create=lambda **_: _stub_anthropic(
                    body="Sí — tu expediente va al 35% y te quedan 5 documentos por subir.",
                    cta_id="act-onboarding-constancia",
                )
            )

    with patch("app.services.wise.ai.Anthropic", FakeClient), patch.object(
        settings, "ANTHROPIC_API_KEY", "test-key"
    ):
        response = api_client.post(
            f"/api/v1/portal/workspaces/{ws['workspace_id']}/wise/ask",
            json={
                "prompt": "¿cómo voy con mis uploads del expediente inicial?",
                "digest": _digest_dict(),
                "ctas": _ctas(),
            },
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source"] == "llm"
    assert "35%" in body["body"]
    assert body["cta_label"] == "Subir documento"
    assert body["cta_href"] == "/portal/upload?requirement_code=onboarding_constancia"


def test_ask_endpoint_falls_back_when_key_missing(api_client: TestClient) -> None:
    ws = _setup_workspace(api_client)
    with patch.object(settings, "ANTHROPIC_API_KEY", ""):
        response = api_client.post(
            f"/api/v1/portal/workspaces/{ws['workspace_id']}/wise/ask",
            json={
                "prompt": "¿cómo voy?",
                "digest": _digest_dict(),
                "ctas": _ctas(),
            },
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source"] == "fallback"
    assert body["cta_label"] is None
    assert body["cta_href"] is None


def test_ask_endpoint_rejects_foreign_workspace(api_client: TestClient) -> None:
    ws_a = _setup_workspace(api_client)
    fresh = TestClient(api_client.app)
    fresh.app.state.testing_session = api_client.app.state.testing_session  # type: ignore[attr-defined]
    ws_b = _setup_workspace(
        api_client,
        vendor_name="Otro Ask SA",
        vendor_rfc="OTH260512AB1",
        fresh_client=fresh,
    )

    cross = fresh.post(
        f"/api/v1/portal/workspaces/{ws_a['workspace_id']}/wise/ask",
        json={"prompt": "x", "digest": _digest_dict(), "ctas": []},
        headers={"Authorization": f"Bearer {ws_b['bearer']}"},
    )
    assert cross.status_code == 403


def test_ask_endpoint_rejects_too_long_prompt_at_validation(
    api_client: TestClient,
) -> None:
    """Pydantic enforces the 500-char ceiling at the schema layer —
    we never even reach the service."""
    ws = _setup_workspace(api_client)
    response = api_client.post(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/wise/ask",
        json={
            "prompt": "x" * 600,
            "digest": _digest_dict(),
            "ctas": _ctas(),
        },
    )
    assert response.status_code == 422
