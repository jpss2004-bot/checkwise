"""M2 — Spanish error contract.

The 2026-05-25 sale-readiness audit (and the parallel backend hardening
pass) flagged English error leaks on auth / feedback / metadata-dry-run
/ reports / reviewer routes. After the M2 localization, every error
returned from these surfaces must be Spanish so pilot users never see
"Invalid credentials" or "Submission not found".

These tests pin the contract at the API boundary — one focused
assertion per error path. A regression that reverts a string back to
English fails the relevant case here before the localized copy ships
to a pilot user.

The auth-side ``"Credenciales inválidas."`` is also pinned in
``test_auth.py::test_login_unknown_email_returns_401_with_generic_detail``
to defend the unknown-user-vs-bad-password indistinguishability; this
file complements that with the rest of the surface.
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
from app.models import entities  # noqa: F401


@pytest.fixture
def api_client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db() -> Generator[Session, None, None]:
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# ─── auth ────────────────────────────────────────────────────────


def test_auth_missing_authorization_header_is_spanish(
    api_client: TestClient,
) -> None:
    resp = api_client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Falta el encabezado de autorización."


def test_auth_invalid_authorization_header_is_spanish(
    api_client: TestClient,
) -> None:
    resp = api_client.get(
        "/api/v1/auth/me", headers={"Authorization": "Token abc"}
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Encabezado de autorización inválido."


def test_auth_bad_credentials_is_spanish(api_client: TestClient) -> None:
    resp = api_client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@cw.test", "password": "anything"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Credenciales inválidas."


# ─── metadata-dry-run ────────────────────────────────────────────


def test_metadata_dry_run_unknown_doc_type_is_spanish(
    api_client: TestClient,
) -> None:
    """Echo the offending code (does_not_exist) so the n8n operator
    can see what they rejected — surrounding copy is Spanish."""
    resp = api_client.post(
        "/api/v1/metadata-dry-run/pdf",
        data={"document_type_code": "does_not_exist"},
        files={"file": ("x.pdf", b"%PDF-1.4\n%EOF\n", "application/pdf")},
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail.startswith("Tipo de documento desconocido:")
    assert "does_not_exist" in detail


def test_metadata_dry_run_bad_json_context_is_spanish(
    api_client: TestClient,
) -> None:
    resp = api_client.post(
        "/api/v1/metadata-dry-run/pdf",
        data={
            "document_type_code": "acuse_sisub",
            "context_json": "not-json",
        },
        files={"file": ("x.pdf", b"%PDF-1.4\n%EOF\n", "application/pdf")},
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "context_json" in detail
    assert "JSON válido" in detail


# ─── reviewer ────────────────────────────────────────────────────


def test_reviewer_missing_submission_is_spanish_via_auth_guard(
    api_client: TestClient,
) -> None:
    """The reviewer routes are gated by ``require_any_role`` so an
    unauthenticated probe gets a localized auth error before the
    handler runs. The handler-level "Envío no encontrado." would
    require a reviewer JWT; that path is already exercised by
    ``test_reviewer.py``. Here we just verify the gate's Spanish
    output."""
    resp = api_client.get("/api/v1/reviewer/submissions/does-not-exist")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Falta el encabezado de autorización."
