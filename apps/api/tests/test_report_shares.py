"""Phase 10D — signed-link sharing for reports.

Covers:

* Pure ``mint_share`` / ``consume_share`` / ``revoke_share``
  service surface — token is hashed before storage, password is
  bcrypt-verifiable, revoke/expired/unknown raise distinct typed
  errors, access_count increments only on a successful consume.
* Bearer-auth endpoints:
    POST   /reports/{id}/shares    — happy path + 422 past expiry
                                      + 404 cross-tenant report.
    GET    /reports/{id}/shares    — lists active+revoked, never
                                      returns tokens / hashes.
    DELETE /reports/shares/{id}    — revokes (204), idempotent,
                                      404 cross-tenant.
* Public consume endpoints (no auth):
    GET  /r/{token}/info           — metadata probe; same 404/410
                                      contract as the render route.
    GET  /r/{token}                — renders HTML on success;
                                      404/410/401 on the failure
                                      modes; access_count bumps.
    POST /r/{token}/unlock         — sets the cookie on right pw;
                                      401 on wrong pw without
                                      pumping access_count.

No-enumeration discipline: unknown / expired / revoked tokens
all return the same body (``"Enlace no disponible."``). Only the
status code differs so the sender's recovery path is informed.
"""

from __future__ import annotations

import hashlib
from collections.abc import Generator
from datetime import UTC, datetime, timedelta

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
    ReportShare,
    ReportVersion,
    User,
    entities,  # noqa: F401 — register mappers
)
from app.services.auth import hash_password
from app.services.reports.sharing import (
    ShareError,
    ShareExpiredError,
    ShareNotFoundError,
    SharePasswordMismatchError,
    SharePasswordRequiredError,
    ShareRevokedError,
    consume_share,
    mint_share,
    revoke_share,
)

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


def _seed_minimal_report(
    db_factory, *, audience: str = "internal_only"
) -> dict:
    """Seed a user + org + report + version. Returns plain dict of IDs +
    email so tests can re-fetch in their own sessions without hitting
    the DetachedInstanceError trap of carrying ORM objects across
    session boundaries."""
    db = db_factory()
    try:
        org = Organization(name="Org", kind="internal")
        db.add(org)
        db.flush()
        user = User(
            email=f"u-{org.id[:6]}@e.test",
            password_hash=hash_password("LongPass!2026"),
            full_name="Sharer",
            status="active",
        )
        db.add(user)
        db.flush()
        db.add(
            Membership(
                user_id=user.id,
                organization_id=org.id,
                role="internal_admin",
                status="active",
            )
        )
        report = Report(
            organization_id=org.id,
            title="Reporte compartible",
            description="con descripción",
            audience=audience,
            created_by_user_id=user.id,
        )
        db.add(report)
        db.flush()
        version = ReportVersion(
            report_id=report.id,
            version_number=1,
            content_json={
                "blocks": [
                    {"id": "t", "type": "text", "config": {"title": "Hola", "body": "Mundo"}, "data": {}},
                ]
            },
            generated_by="manual",
            created_by_user_id=user.id,
        )
        db.add(version)
        db.flush()
        report.current_version_id = version.id
        db.commit()
        return {
            "report_id": report.id,
            "report_title": report.title,
            "report_audience": report.audience,
            "version_id": version.id,
            "user_id": user.id,
            "user_email": user.email,
            "org_id": org.id,
        }
    finally:
        db.close()


def _login(api_client: TestClient, email: str, password: str = "LongPass!2026") -> str:
    resp = api_client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ─── Service-layer tests ─────────────────────────────────────────


def test_mint_share_hashes_token_and_password(db_factory) -> None:
    seed = _seed_minimal_report(db_factory)
    db = db_factory()
    try:
        report = db.get(Report, seed["report_id"])
        version = db.get(ReportVersion, seed["version_id"])
        user = db.get(User, seed["user_id"])
        row, raw_token = mint_share(
            db,
            report=report,
            version=version,
            audience=report.audience,
            requested_by=user,
            password="sup3r-s3cret",
        )
        db.commit()
        # Token returned exactly once, NEVER stored.
        assert isinstance(raw_token, str)
        assert len(raw_token) > 30
        expected_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        assert row.token_hash == expected_hash
        # Password is bcrypt-hashed, not stored plaintext.
        assert row.password_hash is not None
        assert row.password_hash != "sup3r-s3cret"
        assert row.password_hash.startswith("$2")  # bcrypt prefix
        # Counters start at zero.
        assert row.access_count == 0
        assert row.last_accessed_at is None
        assert row.revoked_at is None
    finally:
        db.close()


def test_consume_share_increments_counter_on_success(db_factory) -> None:
    seed = _seed_minimal_report(db_factory)
    db = db_factory()
    try:
        report = db.get(Report, seed["report_id"])
        version = db.get(ReportVersion, seed["version_id"])
        user = db.get(User, seed["user_id"])
        _, raw = mint_share(
            db, report=report, version=version, audience=report.audience, requested_by=user
        )
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        share = consume_share(db, token=raw)
        db.commit()
        assert share.access_count == 1
        assert share.last_accessed_at is not None
    finally:
        db.close()


def test_consume_share_unknown_revoked_expired(db_factory) -> None:
    seed = _seed_minimal_report(db_factory)
    past = datetime.now(UTC) - timedelta(hours=1)
    future = datetime.now(UTC) + timedelta(hours=1)

    db = db_factory()
    try:
        report = db.get(Report, seed["report_id"])
        version = db.get(ReportVersion, seed["version_id"])
        user = db.get(User, seed["user_id"])
        # Three shares with distinct lifecycle states.
        _, raw_active = mint_share(
            db, report=report, version=version, audience=report.audience,
            requested_by=user, expires_at=future,
        )
        revoked, raw_revoked = mint_share(
            db, report=report, version=version, audience=report.audience, requested_by=user,
        )
        revoke_share(db, share=revoked)
        _, raw_expired = mint_share(
            db, report=report, version=version, audience=report.audience,
            requested_by=user, expires_at=past,
        )
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        # Unknown
        with pytest.raises(ShareNotFoundError):
            consume_share(db, token="totally-bogus-token")
        # Revoked
        with pytest.raises(ShareRevokedError):
            consume_share(db, token=raw_revoked)
        # Expired
        with pytest.raises(ShareExpiredError):
            consume_share(db, token=raw_expired)
        # Active succeeds
        share = consume_share(db, token=raw_active)
        assert share.access_count == 1
        db.commit()
    finally:
        db.close()


def test_consume_share_password_paths(db_factory) -> None:
    seed = _seed_minimal_report(db_factory)
    db = db_factory()
    try:
        report = db.get(Report, seed["report_id"])
        version = db.get(ReportVersion, seed["version_id"])
        user = db.get(User, seed["user_id"])
        _, raw = mint_share(
            db, report=report, version=version, audience=report.audience,
            requested_by=user, password="correct-horse",
        )
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        # No password
        with pytest.raises(SharePasswordRequiredError):
            consume_share(db, token=raw)
        # Wrong password
        with pytest.raises(SharePasswordMismatchError):
            consume_share(db, token=raw, password="wrong")
        # Right password — and access_count should be exactly 1
        # because the two failures above must NOT have bumped it.
        share = consume_share(db, token=raw, password="correct-horse")
        assert share.access_count == 1
        db.commit()
    finally:
        db.close()


def test_revoke_share_is_idempotent(db_factory) -> None:
    seed = _seed_minimal_report(db_factory)
    db = db_factory()
    try:
        report = db.get(Report, seed["report_id"])
        version = db.get(ReportVersion, seed["version_id"])
        user = db.get(User, seed["user_id"])
        share, _ = mint_share(
            db, report=report, version=version, audience=report.audience, requested_by=user
        )
        first_at = datetime.now(UTC)
        revoke_share(db, share=share, now=first_at)
        assert share.revoked_at == first_at
        # Re-revoke is a no-op — revoked_at stays at the original moment.
        revoke_share(db, share=share, now=first_at + timedelta(hours=1))
        assert share.revoked_at == first_at
    finally:
        db.close()


def test_share_error_hierarchy() -> None:
    """All typed errors descend from ShareError so the API layer can
    catch them with a single except-clause when it wants to."""
    assert issubclass(ShareNotFoundError, ShareError)
    assert issubclass(ShareRevokedError, ShareError)
    assert issubclass(ShareExpiredError, ShareError)
    assert issubclass(SharePasswordRequiredError, ShareError)
    assert issubclass(SharePasswordMismatchError, ShareError)


# ─── Bearer endpoints ────────────────────────────────────────────


def _mint_via_api(api_client: TestClient, token: str, report_id: str, **kwargs) -> dict:
    resp = api_client.post(
        f"/api/v1/reports/{report_id}/shares",
        headers=_h(token),
        json=kwargs,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_post_share_returns_token_and_url(api_client, db_factory) -> None:
    seed = _seed_minimal_report(db_factory)
    token = _login(api_client, seed["user_email"])
    body = _mint_via_api(api_client, token, seed["report_id"])
    assert "token" in body
    assert "url" in body
    assert body["url"].endswith("/api/v1/r/" + body["token"])
    share = body["share"]
    assert share["report_id"] == seed["report_id"]
    assert share["access_count"] == 0
    assert share["has_password"] is False
    assert share["revoked_at"] is None
    # Token / hash NEVER appears inside the share payload itself.
    assert "token_hash" not in share
    assert "password_hash" not in share


def test_post_share_with_password_sets_has_password_flag(api_client, db_factory) -> None:
    seed = _seed_minimal_report(db_factory)
    token = _login(api_client, seed["user_email"])
    body = _mint_via_api(api_client, token, seed["report_id"], password="sup3r-s3cret")
    assert body["share"]["has_password"] is True


def test_post_share_rejects_past_expires_at(api_client, db_factory) -> None:
    seed = _seed_minimal_report(db_factory)
    token = _login(api_client, seed["user_email"])
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    resp = api_client.post(
        f"/api/v1/reports/{seed['report_id']}/shares",
        headers=_h(token),
        json={"expires_at": past},
    )
    assert resp.status_code == 422
    assert "futura" in resp.json()["detail"].lower()


def test_post_share_404_for_unknown_report(api_client, db_factory) -> None:
    seed = _seed_minimal_report(db_factory)
    token = _login(api_client, seed["user_email"])
    resp = api_client.post(
        "/api/v1/reports/does-not-exist/shares",
        headers=_h(token),
        json={},
    )
    assert resp.status_code == 404


def test_get_shares_lists_active_and_revoked_without_tokens(api_client, db_factory) -> None:
    seed = _seed_minimal_report(db_factory)
    token = _login(api_client, seed["user_email"])
    active = _mint_via_api(api_client, token, seed["report_id"])
    to_revoke = _mint_via_api(api_client, token, seed["report_id"])
    api_client.delete(
        f"/api/v1/reports/shares/{to_revoke['share']['id']}", headers=_h(token)
    )

    resp = api_client.get(
        f"/api/v1/reports/{seed['report_id']}/shares", headers=_h(token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 2
    by_id = {it["id"]: it for it in body["items"]}
    assert by_id[active["share"]["id"]]["revoked_at"] is None
    assert by_id[to_revoke["share"]["id"]]["revoked_at"] is not None
    # No tokens / hashes in the list response, ever.
    for item in body["items"]:
        assert "token" not in item
        assert "token_hash" not in item
        assert "password_hash" not in item


def test_delete_share_is_idempotent(api_client, db_factory) -> None:
    seed = _seed_minimal_report(db_factory)
    token = _login(api_client, seed["user_email"])
    body = _mint_via_api(api_client, token, seed["report_id"])
    sid = body["share"]["id"]
    first = api_client.delete(f"/api/v1/reports/shares/{sid}", headers=_h(token))
    assert first.status_code == 204
    second = api_client.delete(f"/api/v1/reports/shares/{sid}", headers=_h(token))
    assert second.status_code == 204


def test_delete_share_404_for_unknown_id(api_client, db_factory) -> None:
    seed = _seed_minimal_report(db_factory)
    token = _login(api_client, seed["user_email"])
    resp = api_client.delete(
        "/api/v1/reports/shares/does-not-exist", headers=_h(token)
    )
    assert resp.status_code == 404


def test_delete_share_404_cross_tenant(api_client, db_factory) -> None:
    """A user in org B cannot revoke a share whose parent report
    belongs to org A. 404 because the get_report gate fails first
    — no enumeration of share ids."""
    seed_a = _seed_minimal_report(db_factory)
    # Mint as A
    tok_a = _login(api_client, seed_a["user_email"])
    body = _mint_via_api(api_client, tok_a, seed_a["report_id"])
    sid = body["share"]["id"]
    # Seed an unrelated client_admin user B
    db = db_factory()
    try:
        org_b = Organization(name="Org B", kind="client")
        db.add(org_b)
        db.flush()
        user_b = User(
            email="b@e.test",
            password_hash=hash_password("LongPass!2026"),
            full_name="B",
            status="active",
        )
        db.add(user_b)
        db.flush()
        db.add(
            Membership(
                user_id=user_b.id,
                organization_id=org_b.id,
                role="client_admin",
                status="active",
            )
        )
        db.commit()
    finally:
        db.close()
    tok_b = _login(api_client, "b@e.test")
    resp = api_client.delete(
        f"/api/v1/reports/shares/{sid}", headers=_h(tok_b)
    )
    assert resp.status_code == 404


# ─── Public consume endpoints ────────────────────────────────────


def test_public_get_renders_html(api_client, db_factory) -> None:
    seed = _seed_minimal_report(db_factory)
    auth_tok = _login(api_client, seed["user_email"])
    body = _mint_via_api(api_client, auth_tok, seed["report_id"])
    raw_token = body["token"]

    resp = api_client.get(f"/api/v1/r/{raw_token}")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert resp.headers["cache-control"] == "no-store"
    assert resp.text.startswith("<!doctype html>")
    assert "Reporte compartible" in resp.text  # title from the seed
    assert "Mundo" in resp.text  # block body


def test_public_get_404_for_unknown_token(api_client, db_factory) -> None:
    _seed_minimal_report(db_factory)
    resp = api_client.get("/api/v1/r/totally-fake-token")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Enlace no disponible."


def test_public_get_410_for_revoked(api_client, db_factory) -> None:
    seed = _seed_minimal_report(db_factory)
    auth_tok = _login(api_client, seed["user_email"])
    body = _mint_via_api(api_client, auth_tok, seed["report_id"])
    api_client.delete(
        f"/api/v1/reports/shares/{body['share']['id']}", headers=_h(auth_tok)
    )
    resp = api_client.get(f"/api/v1/r/{body['token']}")
    assert resp.status_code == 410


def test_public_get_410_for_expired(api_client, db_factory) -> None:
    """Mint with future expiry; manually rewind the row to simulate
    expiry; consume returns 410."""
    seed = _seed_minimal_report(db_factory)
    auth_tok = _login(api_client, seed["user_email"])
    future = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    body = _mint_via_api(api_client, auth_tok, seed["report_id"], expires_at=future)

    # Rewind expires_at to the past via direct DB write.
    db = db_factory()
    try:
        row = db.scalar(
            select(ReportShare).where(ReportShare.id == body["share"]["id"])
        )
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    finally:
        db.close()

    resp = api_client.get(f"/api/v1/r/{body['token']}")
    assert resp.status_code == 410


def test_public_get_401_when_password_required(api_client, db_factory) -> None:
    seed = _seed_minimal_report(db_factory)
    auth_tok = _login(api_client, seed["user_email"])
    body = _mint_via_api(api_client, auth_tok, seed["report_id"], password="correct-horse")

    # No unlock cookie → 401 password_required
    resp = api_client.get(f"/api/v1/r/{body['token']}")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "password_required"


def test_unlock_with_right_password_sets_cookie_and_unblocks_get(
    api_client, db_factory
) -> None:
    seed = _seed_minimal_report(db_factory)
    auth_tok = _login(api_client, seed["user_email"])
    body = _mint_via_api(api_client, auth_tok, seed["report_id"], password="correct-horse")

    unlock = api_client.post(
        f"/api/v1/r/{body['token']}/unlock",
        json={"password": "correct-horse"},
    )
    assert unlock.status_code == 200
    # Subsequent GET on the same TestClient (cookie persists) → 200
    resp = api_client.get(f"/api/v1/r/{body['token']}")
    assert resp.status_code == 200
    assert resp.text.startswith("<!doctype html>")


def test_unlock_with_wrong_password_returns_401_and_does_not_bump_counter(
    api_client, db_factory
) -> None:
    seed = _seed_minimal_report(db_factory)
    auth_tok = _login(api_client, seed["user_email"])
    body = _mint_via_api(api_client, auth_tok, seed["report_id"], password="correct-horse")

    unlock = api_client.post(
        f"/api/v1/r/{body['token']}/unlock",
        json={"password": "wrong"},
    )
    assert unlock.status_code == 401
    assert unlock.json()["detail"] == "password_invalid"

    # access_count must still be 0 — brute-force attempts don't pump
    # the counter (the consume side-effects are rolled back on auth
    # failure).
    db = db_factory()
    try:
        row = db.scalar(
            select(ReportShare).where(ReportShare.id == body["share"]["id"])
        )
        assert row.access_count == 0
    finally:
        db.close()


def test_info_endpoint_returns_metadata_only(api_client, db_factory) -> None:
    seed = _seed_minimal_report(db_factory)
    auth_tok = _login(api_client, seed["user_email"])
    body = _mint_via_api(api_client, auth_tok, seed["report_id"], password="sup3r-s3cret")
    resp = api_client.get(f"/api/v1/r/{body['token']}/info")
    assert resp.status_code == 200
    info = resp.json()
    assert info["audience"] == seed["report_audience"]
    assert info["has_password"] is True
    assert info["title"] == seed["report_title"]
    # No body, no token.
    assert "body" not in info
    assert "token" not in info


def test_info_endpoint_404_for_unknown(api_client, db_factory) -> None:
    _seed_minimal_report(db_factory)
    resp = api_client.get("/api/v1/r/bogus-token/info")
    assert resp.status_code == 404


def test_info_endpoint_410_for_revoked(api_client, db_factory) -> None:
    seed = _seed_minimal_report(db_factory)
    auth_tok = _login(api_client, seed["user_email"])
    body = _mint_via_api(api_client, auth_tok, seed["report_id"])
    api_client.delete(
        f"/api/v1/reports/shares/{body['share']['id']}", headers=_h(auth_tok)
    )
    resp = api_client.get(f"/api/v1/r/{body['token']}/info")
    assert resp.status_code == 410


def test_access_count_increments_on_each_consume(api_client, db_factory) -> None:
    seed = _seed_minimal_report(db_factory)
    auth_tok = _login(api_client, seed["user_email"])
    body = _mint_via_api(api_client, auth_tok, seed["report_id"])

    # Consume 3 times — public, no auth.
    for _ in range(3):
        ok = api_client.get(f"/api/v1/r/{body['token']}")
        assert ok.status_code == 200

    # access_count surfaces on the bearer-auth GET endpoint.
    listed = api_client.get(
        f"/api/v1/reports/{seed['report_id']}/shares", headers=_h(auth_tok)
    ).json()
    assert listed["items"][0]["access_count"] == 3
    assert listed["items"][0]["last_accessed_at"] is not None
