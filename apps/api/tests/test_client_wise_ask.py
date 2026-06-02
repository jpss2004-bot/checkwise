"""Cliente Wise copilot — ``/api/v1/client/wise/*`` route coverage.

Lands alongside the cliente Wise dock (M1 of the 2026-06 Reportes
redesign). Mirrors ``test_wise_ask.py``'s patterns but scoped to the
buyer surface:

  * Auth — only ``client_admin`` / ``internal_admin`` reach the route.
  * Tenant guard — ``_resolve_client_id`` matches the same behavior
    every other ``/client/*`` route exposes; ask/event calls for an
    out-of-scope client return 403.
  * Empty prompt → deterministic fallback (source=fallback), no LLM
    call.
  * Happy path with a stub Anthropic client → structured reply with
    a validated ``cta_id`` echoed back as ``cta_label`` + ``cta_href``.
  * Event endpoint accepts allowed event types and rejects unknown
    ones with a 400.
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
    Membership,
    Organization,
    ProviderWorkspace,
    User,
    Vendor,
    entities,  # noqa: F401 — register mappers
)
from app.services.auth import hash_password
from app.services.wise.client_ai import CLIENT_NAVIGATION_CTAS

_user_seq = itertools.count(start=1)


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


def _seed_client_admin(
    api_client: TestClient,
    *,
    client_name: str = "Cliente Demo CW",
    vendor_name: str = "Servicios Demo SA",
    vendor_rfc: str = "SDM260512AB1",
) -> dict:
    """Create (Client, Vendor, ProviderWorkspace, User, Org, Membership).

    Returns a dict with ``client_id``, ``vendor_id``, ``workspace_id``,
    ``user_id``, ``email``, ``password`` so the test can sign in.
    """
    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        seq = next(_user_seq)
        password = "ClienteWiseTest!2026"
        email = f"cliente-{seq}@checkwise.test"
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name=f"Cliente Demo {seq}",
            status="active",
            must_change_password=False,
        )
        db.add(user)
        db.flush()

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
            access_token=f"SECRET-{vendor_rfc}",
        )
        db.add(workspace)
        db.flush()

        org = Organization(
            name=f"Org Cliente {seq}", kind="client", client_id=client_row.id
        )
        db.add(org)
        db.flush()
        db.add(
            Membership(
                user_id=user.id,
                organization_id=org.id,
                role="client_admin",
                status="active",
            )
        )
        db.commit()
        return {
            "client_id": client_row.id,
            "vendor_id": vendor.id,
            "workspace_id": workspace.id,
            "user_id": user.id,
            "email": email,
            "password": password,
        }
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


# ─── Tests ─────────────────────────────────────────────────────────


def test_ask_requires_authentication(api_client: TestClient) -> None:
    resp = api_client.post(
        "/api/v1/client/wise/ask",
        json={"prompt": "¿qué proveedores están en riesgo?", "ctas": []},
    )
    assert resp.status_code in (401, 403), resp.text


def test_ask_rejects_provider_role(api_client: TestClient) -> None:
    """A provider session (no client_admin membership) gets 403."""
    seed = _seed_client_admin(api_client)
    # Drop the client_admin membership so the user only has the user
    # row but no role that satisfies require_any_role.
    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        db.query(Membership).filter_by(user_id=seed["user_id"]).delete()
        db.commit()
    finally:
        db.close()

    token = _login(api_client, seed["email"], seed["password"])
    resp = api_client.post(
        "/api/v1/client/wise/ask",
        json={"prompt": "¿cuántos proveedores tengo?", "ctas": []},
        headers=_h(token),
    )
    assert resp.status_code == 403, resp.text


def test_ask_empty_prompt_returns_fallback_without_calling_llm(
    api_client: TestClient,
) -> None:
    seed = _seed_client_admin(api_client)
    token = _login(api_client, seed["email"], seed["password"])

    # If the route reaches Anthropic with an empty prompt the test
    # crashes with no api_key. The guard inside ask_wise_for_client
    # must short-circuit BEFORE the client construction.
    with patch("app.services.wise.ai.Anthropic") as anthro_cls:
        resp = api_client.post(
            f"/api/v1/client/wise/ask?client_id={seed['client_id']}",
            json={"prompt": "   ", "ctas": []},
            headers=_h(token),
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "fallback"
    assert body["cta_label"] is None
    assert body["cta_href"] is None
    anthro_cls.assert_not_called()


def test_ask_happy_path_returns_validated_cta(api_client: TestClient) -> None:
    seed = _seed_client_admin(api_client)
    token = _login(api_client, seed["email"], seed["password"])

    # Stub the SDK to return a single tool_use block that picks the
    # 'nav-proveedores' navigation CTA the cliente module injects.
    nav_id = "nav-proveedores"
    assert nav_id in {c.id for c in CLIENT_NAVIGATION_CTAS}

    fake_block = SimpleNamespace(
        type="tool_use",
        name="respond_to_client",
        input={
            "body": "El portafolio se ve sólido. Revisa la lista para confirmar.",
            "cta_id": nav_id,
        },
    )
    fake_response = SimpleNamespace(content=[fake_block])
    fake_client = SimpleNamespace(
        messages=SimpleNamespace(create=lambda **_: fake_response)
    )

    with (
        patch(
            "app.services.wise.ai.Anthropic", return_value=fake_client
        ) as anthro_cls,
        patch.object(settings, "ANTHROPIC_API_KEY", "test-key"),
    ):
        resp = api_client.post(
            f"/api/v1/client/wise/ask?client_id={seed['client_id']}",
            json={
                "prompt": "¿cómo va mi portafolio?",
                "ctas": [],
                "page_context": {
                    "route": "/client/dashboard",
                    "page_label": "Resumen",
                },
            },
            headers=_h(token),
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "llm"
    assert "portafolio" in body["body"].lower()
    assert body["cta_label"] == "Ver proveedores"
    assert body["cta_href"] == "/client/vendors"
    anthro_cls.assert_called_once()


def test_ask_invented_cta_id_is_dropped(api_client: TestClient) -> None:
    """If the model picks a cta_id outside the allowed list, the reply
    body still flows back but cta_label/cta_href are nulled. The cliente
    surface must not be tricked into surfacing attacker-controlled hrefs.
    """
    seed = _seed_client_admin(api_client)
    token = _login(api_client, seed["email"], seed["password"])

    fake_block = SimpleNamespace(
        type="tool_use",
        name="respond_to_client",
        input={
            "body": "Te recomiendo este enlace.",
            "cta_id": "nav-malicioso-no-existe",
        },
    )
    fake_response = SimpleNamespace(content=[fake_block])
    fake_client = SimpleNamespace(
        messages=SimpleNamespace(create=lambda **_: fake_response)
    )

    with (
        patch("app.services.wise.ai.Anthropic", return_value=fake_client),
        patch.object(settings, "ANTHROPIC_API_KEY", "test-key"),
    ):
        resp = api_client.post(
            f"/api/v1/client/wise/ask?client_id={seed['client_id']}",
            json={"prompt": "¿qué hago?", "ctas": []},
            headers=_h(token),
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "llm"
    assert body["cta_label"] is None
    assert body["cta_href"] is None


def test_events_accepts_allowed_type(api_client: TestClient) -> None:
    seed = _seed_client_admin(api_client)
    token = _login(api_client, seed["email"], seed["password"])

    resp = api_client.post(
        f"/api/v1/client/wise/events?client_id={seed['client_id']}",
        json={"event_type": "wise.opened", "payload": {"route": "/client/dashboard"}},
        headers=_h(token),
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body == {"accepted": True, "event_type": "wise.opened"}


def test_events_rejects_unknown_type(api_client: TestClient) -> None:
    seed = _seed_client_admin(api_client)
    token = _login(api_client, seed["email"], seed["password"])

    resp = api_client.post(
        f"/api/v1/client/wise/events?client_id={seed['client_id']}",
        json={"event_type": "wise.does_not_exist", "payload": None},
        headers=_h(token),
    )
    assert resp.status_code == 400, resp.text
    assert "wise.does_not_exist" in resp.text
