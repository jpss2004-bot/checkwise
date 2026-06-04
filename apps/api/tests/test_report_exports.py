"""Phase 10A — report export pipeline.

Covers:

* Pure ``render_report_html`` shape — produces self-contained UTF-8
  HTML, escapes user data, walks block payloads recursively.
* ``start_report_export`` — validates format, creates pending row,
  raises ``ReportExportError`` on unsupported formats.
* ``run_report_export`` — happy path (pending → ready, storage written,
  bytes recorded) and failure path (renderer raises → status="failed"
  + error_text set, never re-raises).
* Endpoints:
    POST /reports/{id}/exports               — happy path + 422 on bad
                                                 format + 404 on
                                                 unknown report.
    GET  /reports/exports/{id}               — happy path + 404 cross
                                                 tenant.
    GET  /reports/exports/{id}/download      — 409 when not ready, 200
                                                 + HTML bytes when ready.
* Permission gate: cross-tenant export ids return 404 (no enumeration).

Storage backend: LocalStorageService writes under a tmpdir per the
default test config. The download endpoint streams via FileResponse.
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
    Report,
    ReportExport,
    ReportVersion,
    User,
    entities,  # noqa: F401 — register mappers
)
from app.services.auth import hash_password
from app.services.reports.export import (
    SUPPORTED_FORMATS,
    ReportExportError,
    render_report_html,
    render_report_pdf,
    run_report_export,
    start_report_export,
)


def _playwright_available() -> bool:
    """Phase 10B — PDF tests need a real Chromium install.

    CI / lightweight envs that skip ``playwright install chromium``
    should still pass the rest of the suite. We treat both
    ``ImportError`` (package missing) and ``RuntimeError`` (browser
    binary missing — Playwright surfaces this with a helpful
    "Looks like Playwright was just installed" message) as "skip".
    """
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        return False
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox"])
            browser.close()
        return True
    except Exception:
        return False


_PLAYWRIGHT_OK = _playwright_available()

# ─── Fixtures ────────────────────────────────────────────────────


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
def api_client(db_factory, monkeypatch) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        db = db_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # The export's background task opens a fresh ``SessionLocal()`` so the
    # request lifecycle doesn't constrain it. Tests run against an
    # in-memory SQLite via ``db_factory`` — SessionLocal() points
    # elsewhere — so we redirect the bg-task to the test's session
    # factory for the duration of this fixture.
    from app.api.v1 import reports as reports_module
    from app.services.reports import export as export_module

    def patched_bg(export_id: str) -> None:
        db = db_factory()
        try:
            export_module.run_report_export(db, export_id)
            db.commit()
        finally:
            db.close()

    monkeypatch.setattr(
        reports_module, "_run_report_export_with_fresh_session", patched_bg
    )

    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _seed_user(
    db_factory,
    *,
    email: str,
    role: str = "internal_admin",
    org_kind: str = "internal",
    org_name: str = "Test Org",
) -> tuple[str, str, str]:
    """Returns (password, email, organization_id)."""
    db = db_factory()
    try:
        password = "ExportTest!2026"
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name="Export Test",
            status="active",
        )
        db.add(user)
        db.flush()
        org = Organization(name=org_name, kind=org_kind)
        db.add(org)
        db.flush()
        db.add(
            Membership(
                user_id=user.id,
                organization_id=org.id,
                role=role,
                status="active",
            )
        )
        db.commit()
        return password, user.email, org.id
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


def _create_report_with_blocks(api_client: TestClient, token: str) -> str:
    """Create a report with a representative mix of blocks. Returns id."""
    canvas = {
        "schema_version": 1,
        "blocks": [
            {
                "id": "b1",
                "type": "text",
                "config": {"title": "Resumen", "body": "Hola <mundo>"},
                "data": {},
            },
            {"id": "b2", "type": "divider", "config": {}, "data": {}},
            {
                "id": "b3",
                "type": "kpi_strip",
                "config": {"title": "Métricas clave"},
                "data": {
                    "resolved": [
                        {"metric_key": "approved_pct", "value": 73, "trend_pct_vs_prior": -4},
                        {"metric_key": "vendors_at_risk", "value": 2, "trend_pct_vs_prior": None},
                    ],
                    "fetched_at": "2026-05-23T12:00:00Z",
                },
                "ai_summary": {"text": "El cumplimiento bajó 4 puntos."},
            },
        ],
        "global": {},
    }
    resp = api_client.post(
        "/api/v1/reports",
        headers=_h(token),
        json={
            "title": "Reporte de prueba",
            "description": "<script>alert(1)</script>",
            "audience": "internal_only",
            "initial_content_json": canvas,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ─── Pure rendering ──────────────────────────────────────────────


def test_supported_formats_pin() -> None:
    """Slice 10A shipped HTML; 10B added PDF. Excel (10C) was removed —
    no client need for spreadsheet exports. Updating this assertion is
    the canonical "I am adding/removing a format on purpose" gate."""
    assert SUPPORTED_FORMATS == ("html", "pdf")


def test_render_report_html_escapes_user_data(db_factory) -> None:
    """Title, description, text block body, and dict keys / values all
    flow through html.escape — no raw HTML can leak from user data."""
    db = db_factory()
    try:
        org = Organization(name="o", kind="internal")
        db.add(org)
        db.flush()
        user = User(email="u@e.test", password_hash="x", full_name="u", status="active")
        db.add(user)
        db.flush()
        report = Report(
            organization_id=org.id,
            title="<b>Title</b>",
            description="<script>alert(1)</script>",
            audience="internal_only",
            created_by_user_id=user.id,
        )
        db.add(report)
        db.flush()
        version = ReportVersion(
            report_id=report.id,
            version_number=1,
            content_json={
                "blocks": [
                    {
                        "id": "x",
                        "type": "text",
                        "config": {"title": "<i>t</i>", "body": "user <evil>"},
                        "data": {},
                    },
                    {
                        "id": "y",
                        "type": "kpi_strip",
                        "config": {},
                        "data": {"<key>": "<value>"},
                    },
                ]
            },
            generated_by="manual",
            created_by_user_id=user.id,
        )
        db.add(version)
        db.commit()

        html_bytes = render_report_html(report, version)
        text = html_bytes.decode("utf-8")

        # Self-contained
        assert text.startswith("<!doctype html>")
        assert "</html>" in text
        # User strings escaped
        assert "<script>alert(1)</script>" not in text
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in text
        assert "&lt;b&gt;Title&lt;/b&gt;" in text
        assert "&lt;i&gt;t&lt;/i&gt;" in text
        assert "user &lt;evil&gt;" in text
        assert "&lt;key&gt;" in text
        # Block markup present
        assert "<section class=\"block\"" in text
        # No external assets (sanity check the inline style block)
        assert "<style>" in text
        assert "src=\"http" not in text
        assert "href=\"http" not in text
    finally:
        db.close()


def test_render_report_html_handles_empty_block_list(db_factory) -> None:
    db = db_factory()
    try:
        org = Organization(name="o", kind="internal")
        db.add(org)
        db.flush()
        user = User(email="u2@e.test", password_hash="x", full_name="u", status="active")
        db.add(user)
        db.flush()
        report = Report(
            organization_id=org.id,
            title="Empty",
            description=None,
            audience="internal_only",
            created_by_user_id=user.id,
        )
        db.add(report)
        db.flush()
        version = ReportVersion(
            report_id=report.id,
            version_number=1,
            content_json={"blocks": []},
            generated_by="manual",
            created_by_user_id=user.id,
        )
        db.add(version)
        db.commit()

        text = render_report_html(report, version).decode("utf-8")
        assert "Sin bloques" not in text  # we don't say "sin bloques"
        # The empty-state copy contains "no tiene bloques aún".
        assert "no tiene bloques aún" in text
    finally:
        db.close()


def test_render_report_html_truncates_large_lists(db_factory) -> None:
    """A 1000-item list in a block payload should be capped at 200
    entries with a truncation marker — otherwise a vendor_risk_matrix
    block with many vendors inflates the HTML 10x."""
    db = db_factory()
    try:
        org = Organization(name="o", kind="internal")
        db.add(org)
        db.flush()
        user = User(email="u3@e.test", password_hash="x", full_name="u", status="active")
        db.add(user)
        db.flush()
        report = Report(
            organization_id=org.id,
            title="Big",
            audience="internal_only",
            created_by_user_id=user.id,
        )
        db.add(report)
        db.flush()
        version = ReportVersion(
            report_id=report.id,
            version_number=1,
            content_json={
                "blocks": [
                    {
                        "id": "vrm",
                        "type": "vendor_risk_matrix",
                        "config": {},
                        "data": {"vendors": [{"name": f"v{i}"} for i in range(1000)]},
                    }
                ]
            },
            generated_by="manual",
            created_by_user_id=user.id,
        )
        db.add(version)
        db.commit()

        text = render_report_html(report, version).decode("utf-8")
        # Truncation marker is present
        assert "_truncated" in text
        # The first item is rendered…
        assert "v0" in text
        # …and the 999th is not (capped at 200).
        assert "v999" not in text
    finally:
        db.close()


# ─── State machine ───────────────────────────────────────────────


def test_start_report_export_rejects_unsupported_format(db_factory) -> None:
    db = db_factory()
    try:
        org = Organization(name="o", kind="internal")
        db.add(org)
        db.flush()
        user = User(email="u4@e.test", password_hash="x", full_name="u", status="active")
        db.add(user)
        db.flush()
        report = Report(
            organization_id=org.id,
            title="T",
            audience="internal_only",
            created_by_user_id=user.id,
        )
        db.add(report)
        db.flush()
        version = ReportVersion(
            report_id=report.id,
            version_number=1,
            content_json={"blocks": []},
            generated_by="manual",
            created_by_user_id=user.id,
        )
        db.add(version)
        db.commit()

        with pytest.raises(ReportExportError):
            start_report_export(
                db,
                report=report,
                version=version,
                format="docx",  # supported set is html/pdf; docx remains unsupported
                requested_by_user_id=user.id,
            )
        # No row created
        assert db.scalar(select(ReportExport)) is None
    finally:
        db.close()


def test_run_report_export_happy_path_writes_artifact(
    db_factory, tmp_path, monkeypatch
) -> None:
    """pending → rendering → ready, storage_key set, bytes recorded."""
    # Force local storage backend, scoped to tmp_path.
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path))
    # Reset cached singleton so the env vars take effect.
    from app.services import storage as storage_module
    storage_module._SERVICE = None  # type: ignore[attr-defined]

    db = db_factory()
    try:
        org = Organization(name="o", kind="internal")
        db.add(org)
        db.flush()
        user = User(email="u5@e.test", password_hash="x", full_name="u", status="active")
        db.add(user)
        db.flush()
        report = Report(
            organization_id=org.id,
            title="Happy",
            audience="internal_only",
            created_by_user_id=user.id,
        )
        db.add(report)
        db.flush()
        version = ReportVersion(
            report_id=report.id,
            version_number=1,
            content_json={"blocks": [{"id": "b", "type": "text", "config": {"body": "hi"}, "data": {}}]},
            generated_by="manual",
            created_by_user_id=user.id,
        )
        db.add(version)
        db.commit()

        export = start_report_export(
            db, report=report, version=version, format="html", requested_by_user_id=user.id
        )
        db.commit()
        export_id = export.id

        run_report_export(db, export_id)
        db.commit()

        # Re-fetch
        export = db.get(ReportExport, export_id)
        assert export is not None
        assert export.status == "ready"
        assert export.storage_key is not None
        assert export.storage_key.startswith(f"report-exports/{report.id}/")
        assert export.bytes is not None and export.bytes > 0
        assert export.error_text is None
        assert export.ready_at is not None
    finally:
        db.close()


def test_run_report_export_failure_path_persists_error(db_factory, monkeypatch) -> None:
    """A renderer crash sets status=failed + error_text, never raises."""
    db = db_factory()
    try:
        org = Organization(name="o", kind="internal")
        db.add(org)
        db.flush()
        user = User(email="u6@e.test", password_hash="x", full_name="u", status="active")
        db.add(user)
        db.flush()
        report = Report(
            organization_id=org.id,
            title="Boom",
            audience="internal_only",
            created_by_user_id=user.id,
        )
        db.add(report)
        db.flush()
        version = ReportVersion(
            report_id=report.id,
            version_number=1,
            content_json={"blocks": []},
            generated_by="manual",
            created_by_user_id=user.id,
        )
        db.add(version)
        db.commit()

        export = start_report_export(
            db, report=report, version=version, format="html", requested_by_user_id=user.id
        )
        db.commit()
        export_id = export.id

        # Force the renderer to raise.
        from app.services.reports import export as export_module

        monkeypatch.setattr(
            export_module,
            "render_report_html",
            lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError("simulated")),
        )

        # Must not raise.
        run_report_export(db, export_id)
        db.commit()

        export = db.get(ReportExport, export_id)
        assert export is not None
        assert export.status == "failed"
        assert export.error_text is not None
        assert "simulated" in export.error_text
        assert export.storage_key is None
    finally:
        db.close()


# ─── Endpoints — happy path + auth ───────────────────────────────


def test_post_export_404_for_unknown_report(api_client, db_factory) -> None:
    pw, email, _ = _seed_user(db_factory, email="admin@exp.test")
    token = _login(api_client, email, pw)
    resp = api_client.post(
        "/api/v1/reports/does-not-exist/exports",
        headers=_h(token),
        json={"format": "html"},
    )
    assert resp.status_code == 404


def test_post_export_422_for_bad_format(api_client, db_factory) -> None:
    pw, email, _ = _seed_user(db_factory, email="admin2@exp.test")
    token = _login(api_client, email, pw)
    report_id = _create_report_with_blocks(api_client, token)
    resp = api_client.post(
        f"/api/v1/reports/{report_id}/exports",
        headers=_h(token),
        json={"format": "docx"},  # supported set is html/pdf; docx remains unsupported
    )
    assert resp.status_code == 422
    # The detail string includes the supported-formats list so
    # consumers can self-correct. Both currently-supported values
    # should appear.
    detail = resp.json()["detail"]
    assert "html" in detail
    assert "pdf" in detail


def test_post_export_creates_pending_row_and_returns_201(api_client, db_factory) -> None:
    pw, email, _ = _seed_user(db_factory, email="admin3@exp.test")
    token = _login(api_client, email, pw)
    report_id = _create_report_with_blocks(api_client, token)

    resp = api_client.post(
        f"/api/v1/reports/{report_id}/exports",
        headers=_h(token),
        json={"format": "html"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["report_id"] == report_id
    assert body["format"] == "html"
    # TestClient invokes BackgroundTasks synchronously after the response,
    # so the row may already be ready by the time we read it — that's OK.
    # The assertion is just that the row exists and is in a valid state.
    assert body["status"] in {"pending", "rendering", "ready", "failed"}


def test_get_export_returns_ready_status_after_background_runs(
    api_client, db_factory
) -> None:
    """TestClient drains BackgroundTasks after the response. By the
    time we issue the GET, status should be 'ready' (or 'failed' if
    the renderer crashed)."""
    pw, email, _ = _seed_user(db_factory, email="admin4@exp.test")
    token = _login(api_client, email, pw)
    report_id = _create_report_with_blocks(api_client, token)

    create = api_client.post(
        f"/api/v1/reports/{report_id}/exports",
        headers=_h(token),
        json={"format": "html"},
    )
    export_id = create.json()["id"]

    resp = api_client.get(f"/api/v1/reports/exports/{export_id}", headers=_h(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == export_id
    assert body["status"] == "ready"
    assert body["bytes"] is not None and body["bytes"] > 0


def test_download_export_returns_html_bytes(api_client, db_factory) -> None:
    pw, email, _ = _seed_user(db_factory, email="admin5@exp.test")
    token = _login(api_client, email, pw)
    report_id = _create_report_with_blocks(api_client, token)

    create = api_client.post(
        f"/api/v1/reports/{report_id}/exports",
        headers=_h(token),
        json={"format": "html"},
    )
    export_id = create.json()["id"]

    resp = api_client.get(
        f"/api/v1/reports/exports/{export_id}/download", headers=_h(token)
    )
    assert resp.status_code == 200
    # Content-Type carries the html mime type.
    assert resp.headers["content-type"].startswith("text/html")
    # Disposition is attachment.
    assert "attachment" in resp.headers.get("content-disposition", "")
    body = resp.text
    assert body.startswith("<!doctype html>")
    # Block from our seed report renders through.
    assert "Resumen" in body
    # User input was escaped (the description had a <script> tag).
    assert "<script>alert" not in body
    assert "&lt;script&gt;alert" in body


def test_download_returns_409_for_unready_export(api_client, db_factory) -> None:
    """A row stuck in 'pending' (or 'rendering') is a 409, not a 200
    with empty bytes."""
    pw, email, _ = _seed_user(db_factory, email="admin6@exp.test")
    token = _login(api_client, email, pw)
    report_id = _create_report_with_blocks(api_client, token)

    # Insert a pending row directly without the background task.
    db = next(iter(app.dependency_overrides[get_db]()))
    pending = ReportExport(
        report_id=report_id,
        version_id=(db.scalar(select(ReportVersion).where(ReportVersion.report_id == report_id))).id,
        format="html",
        status="pending",
        requested_by_user_id=(db.scalar(select(User).where(User.email == email))).id,
    )
    db.add(pending)
    db.commit()
    export_id = pending.id

    resp = api_client.get(
        f"/api/v1/reports/exports/{export_id}/download", headers=_h(token)
    )
    assert resp.status_code == 409
    assert "ready" in resp.json()["detail"]


def test_get_export_404_for_cross_tenant(api_client, db_factory) -> None:
    """User in org A cannot see an export belonging to a report in org B.

    Both users are internal_admin (the simplest setup for a cross-tenant
    test — both can write internal_only reports, scoped to their own
    org). The test creates a report owned by A, exports it as A, then
    confirms B's calls 404 (no enumeration).
    """
    pw_a, email_a, org_a = _seed_user(
        db_factory, email="aa@exp.test", role="internal_admin",
        org_kind="internal", org_name="Org A",
    )
    # B is a client_admin — their visible_audiences() is {client_facing}
    # only, so an internal_only report owned by A is invisible to B
    # even though both users are real / authenticated. That's the
    # correct shape of the cross-tenant gate.
    pw_b, email_b, _ = _seed_user(
        db_factory, email="bb@exp.test", role="client_admin",
        org_kind="client", org_name="Org B",
    )
    token_a = _login(api_client, email_a, pw_a)
    token_b = _login(api_client, email_b, pw_b)

    # Owned by A.
    create = api_client.post(
        f"/api/v1/reports?organization_id={org_a}",
        headers=_h(token_a),
        json={"title": "Owned by A", "audience": "internal_only"},
    )
    assert create.status_code == 201, create.text
    report_id = create.json()["id"]
    export_create = api_client.post(
        f"/api/v1/reports/{report_id}/exports",
        headers=_h(token_a),
        json={"format": "html"},
    )
    assert export_create.status_code == 201
    export_id = export_create.json()["id"]

    # B can't see it.
    resp = api_client.get(
        f"/api/v1/reports/exports/{export_id}", headers=_h(token_b)
    )
    assert resp.status_code == 404
    resp_dl = api_client.get(
        f"/api/v1/reports/exports/{export_id}/download", headers=_h(token_b)
    )
    assert resp_dl.status_code == 404


def test_get_export_401_when_unauthenticated(api_client, db_factory) -> None:
    """No JWT → 401 from the auth dependency."""
    # Create the export through a logged-in admin first.
    pw, email, _ = _seed_user(db_factory, email="admin7@exp.test")
    token = _login(api_client, email, pw)
    report_id = _create_report_with_blocks(api_client, token)
    create = api_client.post(
        f"/api/v1/reports/{report_id}/exports",
        headers=_h(token),
        json={"format": "html"},
    )
    export_id = create.json()["id"]

    resp = api_client.get(f"/api/v1/reports/exports/{export_id}")
    assert resp.status_code == 401
    resp_dl = api_client.get(f"/api/v1/reports/exports/{export_id}/download")
    assert resp_dl.status_code == 401


def test_post_export_with_explicit_version_id(api_client, db_factory) -> None:
    """Caller can pin a specific version_id; mismatched report→version
    returns 404 (no enumeration)."""
    pw, email, _ = _seed_user(db_factory, email="admin8@exp.test")
    token = _login(api_client, email, pw)
    report_id = _create_report_with_blocks(api_client, token)
    # Get the actual version id
    detail = api_client.get(f"/api/v1/reports/{report_id}", headers=_h(token)).json()
    version_id = detail["current_version"]["id"]

    ok = api_client.post(
        f"/api/v1/reports/{report_id}/exports",
        headers=_h(token),
        json={"format": "html", "version_id": version_id},
    )
    assert ok.status_code == 201

    # A made-up version id returns 404.
    bad = api_client.post(
        f"/api/v1/reports/{report_id}/exports",
        headers=_h(token),
        json={"format": "html", "version_id": "made-up-version"},
    )
    assert bad.status_code == 404


def test_payload_is_valid_json_compatible_html(api_client, db_factory) -> None:
    """Sanity check that the rendered HTML contains the same JSON-y
    data as the source blocks — no silent data loss when payloads
    contain nested dicts / lists / numbers."""
    pw, email, _ = _seed_user(db_factory, email="admin9@exp.test")
    token = _login(api_client, email, pw)
    report_id = _create_report_with_blocks(api_client, token)
    create = api_client.post(
        f"/api/v1/reports/{report_id}/exports",
        headers=_h(token),
        json={"format": "html"},
    )
    export_id = create.json()["id"]
    resp = api_client.get(
        f"/api/v1/reports/exports/{export_id}/download", headers=_h(token)
    )
    body = resp.text
    # KPI strip data should render every metric_key.
    assert "approved_pct" in body
    assert "vendors_at_risk" in body
    assert "73" in body
    # AI summary surfaced too.
    assert "El cumplimiento bajó 4 puntos." in body
    # Sanity: response is valid bytes (decodable as utf-8) without crashing.
    json.dumps({"len": len(body)})  # just to assert no exception in json layer


# ─── Phase 10B — PDF rendering ───────────────────────────────────


@pytest.mark.skipif(
    not _PLAYWRIGHT_OK,
    reason="Playwright chromium not installed; run 'playwright install chromium' to enable.",
)
def test_render_report_pdf_returns_pdf_bytes(db_factory) -> None:
    """The renderer produces real PDF bytes (PDF magic header + size)."""
    db = db_factory()
    try:
        org = Organization(name="o", kind="internal")
        db.add(org)
        db.flush()
        user = User(
            email="pdf-test@e.test", password_hash="x", full_name="u", status="active"
        )
        db.add(user)
        db.flush()
        report = Report(
            organization_id=org.id,
            title="PDF Test",
            description="Slice 10B coverage",
            audience="internal_only",
            created_by_user_id=user.id,
        )
        db.add(report)
        db.flush()
        version = ReportVersion(
            report_id=report.id,
            version_number=1,
            content_json={
                "blocks": [
                    {
                        "id": "t1",
                        "type": "text",
                        "config": {"title": "Resumen", "body": "Texto"},
                        "data": {},
                    },
                    {
                        "id": "k1",
                        "type": "kpi_strip",
                        "config": {"title": "Métricas"},
                        "data": {
                            "resolved": [
                                {"metric_key": "approved_pct", "value": 73, "trend_pct_vs_prior": None},
                            ],
                            "fetched_at": "2026-05-23T12:00:00Z",
                        },
                    },
                ]
            },
            generated_by="manual",
            created_by_user_id=user.id,
        )
        db.add(version)
        db.commit()

        pdf = render_report_pdf(report, version)
        # PDF magic header.
        assert pdf.startswith(b"%PDF-"), pdf[:16]
        # Non-trivial size — a one-page PDF should be at least ~5KB
        # once Chromium has embedded fonts + the inline CSS.
        assert len(pdf) > 5_000, f"PDF only {len(pdf)} bytes — likely empty"
        # End-of-file marker is present (PDFs end with %%EOF).
        assert b"%%EOF" in pdf[-128:]
    finally:
        db.close()


@pytest.mark.skipif(
    not _PLAYWRIGHT_OK,
    reason="Playwright chromium not installed; run 'playwright install chromium' to enable.",
)
def test_post_pdf_export_creates_pdf_artifact(api_client, db_factory) -> None:
    """Full endpoint chain with format=pdf: create → poll → download
    returns a valid PDF blob via the same plumbing as HTML."""
    pw, email, _ = _seed_user(db_factory, email="pdf-e2e@exp.test")
    token = _login(api_client, email, pw)
    report_id = _create_report_with_blocks(api_client, token)

    create = api_client.post(
        f"/api/v1/reports/{report_id}/exports",
        headers=_h(token),
        json={"format": "pdf"},
    )
    assert create.status_code == 201, create.text
    body = create.json()
    assert body["format"] == "pdf"
    export_id = body["id"]

    # Poll endpoint should report ready (TestClient drains BackgroundTasks
    # synchronously after the response — same as the HTML path).
    poll = api_client.get(
        f"/api/v1/reports/exports/{export_id}", headers=_h(token)
    )
    assert poll.status_code == 200
    assert poll.json()["status"] == "ready"

    # Download streams the PDF bytes with the right content type.
    dl = api_client.get(
        f"/api/v1/reports/exports/{export_id}/download", headers=_h(token)
    )
    assert dl.status_code == 200
    assert dl.headers["content-type"].startswith("application/pdf")
    assert ".pdf" in dl.headers.get("content-disposition", "")
    assert dl.content.startswith(b"%PDF-"), dl.content[:16]
    assert b"%%EOF" in dl.content[-128:]
