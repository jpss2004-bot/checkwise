"""Wise copilot — LLM ask endpoint coverage (Phase 3).

Covers ``POST /api/v1/portal/workspaces/{id}/wise/ask`` and the
underlying ``app.services.wise.ai.ask_wise`` service after the
Phase-3 refactor that moved context assembly server-side.

The Anthropic SDK is replaced with a stub that returns a fixed
tool-use response so the tests stay hermetic — no network, no API
key needed. Context-assembly helpers from ``app.services.wise.context``
are exercised against real in-memory DB fixtures (no mocks) so we
catch any drift between the slot service and the assembled context.
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
    NAVIGATION_CTAS,
    WiseCta,
    WisePageContext,
    ask_wise,
)
from app.services.wise.context import (
    build_static_context,
    build_workspace_context,
    render_static_block,
    render_workspace_block,
)

_user_seq = itertools.count(start=1)


# ─── Test fixture ──────────────────────────────────────────────────


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


def _stub_anthropic(body: str, cta_id: str | None) -> SimpleNamespace:
    class _Block:
        type = "tool_use"
        name = "respond_to_provider"
        input = {"body": body, "cta_id": cta_id or ""}

    return SimpleNamespace(content=[_Block()])


# ─── Context-assembly tests (no Anthropic) ─────────────────────────


def test_workspace_context_includes_all_required_slots(
    api_client: TestClient,
) -> None:
    """The assembled context must walk every onboarding + calendar
    slot for the workspace, even when nothing has been uploaded. This
    is what lets Wise answer "qué me falta?" accurately."""
    ws = _setup_workspace(api_client)
    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        workspace = db.get(ProviderWorkspace, ws["workspace_id"])
        assert workspace is not None
        ctx = build_workspace_context(db, workspace)
    finally:
        db.close()

    # Brand-new workspace has at least one required onboarding slot
    # (the persona-moral expediente is non-empty in production catalogs).
    assert ctx.onboarding_slots, "expected at least one onboarding slot"
    # Every onboarding slot has a Spanish state label so the model
    # doesn't have to translate the raw enum.
    for slot in ctx.onboarding_slots:
        assert slot.state_label_es, slot
        assert slot.kind == "onboarding"

    # Calendar slots are surfaced for the active year.
    assert ctx.calendar_slots, "expected at least one calendar slot"
    for slot in ctx.calendar_slots:
        assert slot.kind == "calendar"

    # Recent uploads list is empty for a brand-new workspace.
    assert ctx.recent_uploads == ()
    assert ctx.vendor_name == "Servicios Ask SA"
    assert ctx.persona_type == "moral"
    assert ctx.onboarding_completed is False


def test_static_context_includes_glossary_and_catalog() -> None:
    """The static block must carry CheckWise's glossary + the full
    REPSE catalog guidance so Wise can answer 'qué es X?' /
    'dónde lo obtengo?' without inventing answers."""
    ctx = build_static_context()
    # The glossary describes CheckWise (the platform), not Wise (the
    # copilot) — Wise's persona lives in the system rules prompt.
    assert "CheckWise" in ctx.glossary
    assert "expediente inicial" in ctx.glossary.lower()
    assert "semáforo" in ctx.glossary.lower() or "semaforo" in ctx.glossary.lower()
    assert ctx.catalog_entries, "expected at least one catalog entry"
    # Catalog must include both onboarding (expediente_inicial) and
    # recurring (calendario) entries so it covers the whole REPSE
    # surface, not just one half.
    sections = {entry.section for entry in ctx.catalog_entries}
    assert "expediente_inicial" in sections
    assert "calendario" in sections


def test_render_static_block_groups_by_institution() -> None:
    """The rendered static block is what the model actually reads —
    confirm the four canonical institutions appear so Wise can
    answer questions about each authority."""
    ctx = build_static_context()
    rendered = render_static_block(ctx)
    for marker in ("## SAT", "## IMSS", "## INFONAVIT", "## STPS / REPSE"):
        assert marker in rendered, f"missing section: {marker}"


def test_render_workspace_block_shows_state_in_spanish(
    api_client: TestClient,
) -> None:
    ws = _setup_workspace(api_client)
    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        workspace = db.get(ProviderWorkspace, ws["workspace_id"])
        assert workspace is not None
        ctx = build_workspace_context(db, workspace)
    finally:
        db.close()

    rendered = render_workspace_block(ctx)
    # The Spanish surface vocabulary must show up so the model
    # doesn't reinvent it.
    assert "Razón social" in rendered or "Razon social" in rendered
    assert "Cumplimiento global" in rendered
    assert "pendiente (sin subir)" in rendered  # brand-new workspace


# ─── Service-level tests (mocked Anthropic, real context) ──────────


def test_service_returns_llm_reply_with_valid_cta(api_client: TestClient) -> None:
    ws = _setup_workspace(api_client)
    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        workspace = db.get(ProviderWorkspace, ws["workspace_id"])
        assert workspace is not None
        workspace_ctx = build_workspace_context(db, workspace)
    finally:
        db.close()
    static_ctx = build_static_context()
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
        workspace=workspace_ctx,
        static=static_ctx,
        ctas=ctas,
        client=FakeClient(),  # type: ignore[arg-type]
    )
    assert result.source == "llm"
    assert "Constancia" in result.body
    assert result.cta_id == "act-constancia"
    assert result.cta_label == "Subir documento"


def test_service_passes_cache_control_on_static_block(
    api_client: TestClient,
) -> None:
    """The static system block must be marked ``cache_control:
    {type: 'ephemeral'}`` so Anthropic prompt caching kicks in.
    Catches the regression where a refactor accidentally drops the
    cache hint and per-question cost balloons."""
    ws = _setup_workspace(api_client)
    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        workspace = db.get(ProviderWorkspace, ws["workspace_id"])
        assert workspace is not None
        workspace_ctx = build_workspace_context(db, workspace)
    finally:
        db.close()
    static_ctx = build_static_context()

    captured: dict = {}

    class FakeClient:
        def __init__(self) -> None:
            def create(**kwargs):
                captured.update(kwargs)
                return _stub_anthropic(body="OK", cta_id=None)

            self.messages = SimpleNamespace(create=create)

    ask_wise(
        prompt="x",
        workspace=workspace_ctx,
        static=static_ctx,
        ctas=[],
        client=FakeClient(),  # type: ignore[arg-type]
    )

    system_param = captured.get("system")
    assert isinstance(system_param, list), system_param
    # Two blocks: rules (no cache) + static (cached).
    assert len(system_param) == 2
    assert system_param[0].get("cache_control") is None
    assert system_param[1].get("cache_control") == {"type": "ephemeral"}


def test_service_drops_invented_cta_id(api_client: TestClient) -> None:
    ws = _setup_workspace(api_client)
    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        workspace = db.get(ProviderWorkspace, ws["workspace_id"])
        assert workspace is not None
        workspace_ctx = build_workspace_context(db, workspace)
    finally:
        db.close()
    static_ctx = build_static_context()

    class FakeClient:
        def __init__(self) -> None:
            self.messages = SimpleNamespace(
                create=lambda **_: _stub_anthropic(
                    body="Estás al día.", cta_id="cta-i-made-up"
                )
            )

    result = ask_wise(
        prompt="cómo voy?",
        workspace=workspace_ctx,
        static=static_ctx,
        ctas=[],
        client=FakeClient(),  # type: ignore[arg-type]
    )
    assert result.source == "llm"
    assert result.body == "Estás al día."
    assert result.cta_id is None
    assert result.cta_label is None
    assert result.cta_href is None


def test_service_falls_back_when_no_api_key(api_client: TestClient) -> None:
    ws = _setup_workspace(api_client)
    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        workspace = db.get(ProviderWorkspace, ws["workspace_id"])
        assert workspace is not None
        workspace_ctx = build_workspace_context(db, workspace)
    finally:
        db.close()
    static_ctx = build_static_context()

    result = ask_wise(
        prompt="¿qué sigue?",
        workspace=workspace_ctx,
        static=static_ctx,
        ctas=[],
        api_key="",
    )
    assert result.source == "fallback"
    assert result.body  # non-empty


def test_service_rejects_too_long_prompt(api_client: TestClient) -> None:
    ws = _setup_workspace(api_client)
    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        workspace = db.get(ProviderWorkspace, ws["workspace_id"])
        assert workspace is not None
        workspace_ctx = build_workspace_context(db, workspace)
    finally:
        db.close()
    static_ctx = build_static_context()
    result = ask_wise(
        prompt="a" * 600,
        workspace=workspace_ctx,
        static=static_ctx,
        ctas=[],
        api_key="",
    )
    assert result.source == "fallback"
    assert "muy larga" in result.body


# ─── Endpoint tests ────────────────────────────────────────────────


def test_ask_endpoint_returns_llm_reply(api_client: TestClient) -> None:
    """Happy path: endpoint assembles full context server-side and
    surfaces the model's structured reply."""
    ws = _setup_workspace(api_client)

    class FakeClient:
        def __init__(self, **_: object) -> None:
            self.messages = SimpleNamespace(
                create=lambda **_: _stub_anthropic(
                    body="Llevas 0 documentos cargados y te quedan 5 obligatorios por subir.",
                    cta_id="act-onboarding-constancia",
                )
            )

    with patch("app.services.wise.ai.Anthropic", FakeClient), patch.object(
        settings, "ANTHROPIC_API_KEY", "test-key"
    ):
        response = api_client.post(
            f"/api/v1/portal/workspaces/{ws['workspace_id']}/wise/ask",
            json={
                "prompt": "Puedo visualizar cuantos documentos llevo cargados en plataforma?",
                "ctas": _ctas(),
            },
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source"] == "llm"
    assert "0 documentos" in body["body"]
    assert body["cta_label"] == "Subir documento"


def test_ask_endpoint_accepts_legacy_digest_field_for_compat(
    api_client: TestClient,
) -> None:
    """Phase 2.b clients still send ``digest`` — the new endpoint
    must ignore it without 422-ing them out."""
    ws = _setup_workspace(api_client)
    with patch.object(settings, "ANTHROPIC_API_KEY", ""):
        response = api_client.post(
            f"/api/v1/portal/workspaces/{ws['workspace_id']}/wise/ask",
            json={
                "prompt": "¿cómo voy?",
                "ctas": _ctas(),
                "digest": {
                    "vendor_name": "anything",
                    "persona_type": "moral",
                    "onboarding_completed": False,
                    "compliance_pct": 0,
                    "on_track": 0,
                    "total_tracked": 1,
                    "needs_action": 1,
                    "in_review": 0,
                    "completed_required": 0,
                    "total_required": 1,
                    "approved_count": 0,
                    "pending_count": 1,
                    "rejected_count": 0,
                    "expired_count": 0,
                    "next_action_titles": [],
                    "upcoming_deadline_titles": [],
                },
            },
        )
    assert response.status_code == 200, response.text


def test_ask_endpoint_falls_back_when_key_missing(api_client: TestClient) -> None:
    ws = _setup_workspace(api_client)
    with patch.object(settings, "ANTHROPIC_API_KEY", ""):
        response = api_client.post(
            f"/api/v1/portal/workspaces/{ws['workspace_id']}/wise/ask",
            json={
                "prompt": "¿cómo voy?",
                "ctas": _ctas(),
            },
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source"] == "fallback"


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
        json={"prompt": "x", "ctas": []},
        headers={"Authorization": f"Bearer {ws_b['bearer']}"},
    )
    assert cross.status_code == 403


def test_ask_endpoint_rejects_too_long_prompt_at_validation(
    api_client: TestClient,
) -> None:
    ws = _setup_workspace(api_client)
    response = api_client.post(
        f"/api/v1/portal/workspaces/{ws['workspace_id']}/wise/ask",
        json={
            "prompt": "x" * 600,
            "ctas": _ctas(),
        },
    )
    assert response.status_code == 422


# ─── Phase 4: navigation CTAs + page context ───────────────────────


def test_service_merges_navigation_ctas_into_allowed_list(
    api_client: TestClient,
) -> None:
    """The service must inject ``NAVIGATION_CTAS`` into every call
    so the model can attach a button to any portal page instead of
    writing a literal path string in the reply. Reported by a
    tester after Wise said "Todo está en /portal/onboarding"
    instead of giving them a clickable link."""
    ws = _setup_workspace(api_client)
    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        workspace = db.get(ProviderWorkspace, ws["workspace_id"])
        assert workspace is not None
        workspace_ctx = build_workspace_context(db, workspace)
    finally:
        db.close()
    static_ctx = build_static_context()
    captured: dict = {}

    class FakeClient:
        def __init__(self) -> None:
            def create(**kwargs):
                captured.update(kwargs)
                # Model picks the nav CTA the user needs.
                return _stub_anthropic(body="Ve al expediente.", cta_id="nav-onboarding")

            self.messages = SimpleNamespace(create=create)

    result = ask_wise(
        prompt="por dónde empiezo?",
        workspace=workspace_ctx,
        static=static_ctx,
        ctas=[],  # caller passes no contextual CTAs; nav must still work
        client=FakeClient(),  # type: ignore[arg-type]
    )
    assert result.source == "llm"
    assert result.cta_id == "nav-onboarding"
    assert result.cta_href == "/portal/onboarding"
    # The user-message block sent to the model must enumerate every
    # nav CTA id so the model has them as options.
    messages = captured.get("messages") or []
    assert messages
    user_content = messages[0].get("content", "")
    for nav in NAVIGATION_CTAS:
        assert nav.id in user_content, (
            f"nav CTA {nav.id!r} missing from prompt"
        )


def test_service_renders_page_context_when_provided(
    api_client: TestClient,
) -> None:
    """When the dock ships a ``page_context``, the prompt must
    surface the route + page label + any specific task descriptor
    (requirement, submission, period) so Wise can answer "qué pongo
    aquí?" without the user re-stating where they are."""
    ws = _setup_workspace(api_client)
    factory = api_client.app.state.testing_session  # type: ignore[attr-defined]
    db: Session = factory()
    try:
        workspace = db.get(ProviderWorkspace, ws["workspace_id"])
        assert workspace is not None
        workspace_ctx = build_workspace_context(db, workspace)
    finally:
        db.close()
    static_ctx = build_static_context()
    captured: dict = {}

    class FakeClient:
        def __init__(self) -> None:
            def create(**kwargs):
                captured.update(kwargs)
                return _stub_anthropic(body="OK", cta_id=None)

            self.messages = SimpleNamespace(create=create)

    page = WisePageContext(
        route="/portal/upload",
        page_label="Cargar documento",
        requirement_code="REC-INFONAVIT-2026-03-comprobante-de-pago-bancario",
        requirement_name="Acuse INFONAVIT B1 2026",
        period_key="2026-B1",
    )
    ask_wise(
        prompt="qué pongo aquí?",
        workspace=workspace_ctx,
        static=static_ctx,
        ctas=[],
        page_context=page,
        client=FakeClient(),  # type: ignore[arg-type]
    )
    user_content = captured["messages"][0]["content"]
    assert "Página actual del usuario" in user_content
    assert "/portal/upload" in user_content
    assert "Cargar documento" in user_content
    assert "Acuse INFONAVIT B1 2026" in user_content
    assert "2026-B1" in user_content


def test_ask_endpoint_accepts_page_context(api_client: TestClient) -> None:
    """End-to-end: dock ships page_context in the request and the
    endpoint plumbs it through to the service."""
    ws = _setup_workspace(api_client)

    captured: dict = {}

    class FakeClient:
        def __init__(self, **_: object) -> None:
            def create(**kwargs):
                captured.update(kwargs)
                return _stub_anthropic(body="OK", cta_id=None)

            self.messages = SimpleNamespace(create=create)

    with patch("app.services.wise.ai.Anthropic", FakeClient), patch.object(
        settings, "ANTHROPIC_API_KEY", "test-key"
    ):
        response = api_client.post(
            f"/api/v1/portal/workspaces/{ws['workspace_id']}/wise/ask",
            json={
                "prompt": "qué hay aquí?",
                "ctas": [],
                "page_context": {
                    "route": "/portal/calendar",
                    "page_label": "Calendario REPSE",
                },
            },
        )
    assert response.status_code == 200, response.text
    user_content = captured["messages"][0]["content"]
    assert "/portal/calendar" in user_content
    assert "Calendario REPSE" in user_content
