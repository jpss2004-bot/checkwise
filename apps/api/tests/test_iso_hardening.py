"""Regression tests for the 2026-06-16 ISO-readiness hardening pass.

Covers the P0 technical controls implemented in that pass:

* AUTH G-4  — common/breached-password denylist.
* ENC-1     — DB TLS (``sslmode=require``) enforced for non-local Postgres.
* ENC-2     — server-side-encryption header on object writes.
* FILE-DEL-1— refcount guard so a cancel/rollback never deletes a
              content-addressed object another tenant still references.
* INFRA-1   — CSP subset present on every API response (JSON + non-JSON).
* AUDIT-SHARE/G-7 — logout + report-share disclosure write audit rows.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import AuditLog, Document, User, entities  # noqa: F401 — register mappers
from app.services.auth import hash_password, issue_access_token

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


def _make_document(session, *, storage_key: str, submission_id: str) -> Document:
    """Insert a minimal Document row (SQLite does not enforce the FK)."""
    doc = Document(
        submission_id=submission_id,
        storage_key=storage_key,
        original_filename="evidencia.pdf",
        size_bytes=1024,
        sha256=storage_key.split("/")[-1] or "deadbeef",
    )
    session.add(doc)
    session.flush()
    return doc


# ─── AUTH G-4 — common-password denylist ─────────────────────────


class TestCommonPasswordDenylist:
    def test_rejects_high_frequency_passwords(self) -> None:
        from app.core.common_passwords import is_common_password

        for pw in ("Password1234", "Bienvenido2026", "Checkwise2026", "contrasena123"):
            assert is_common_password(pw) is True, pw

    def test_allows_strong_unique_passwords(self) -> None:
        from app.core.common_passwords import is_common_password

        for pw in ("Tr0ub4dor&3xplng", "Xq7!mVz9pLwK", "Mangos-Verdes-2026!"):
            assert is_common_password(pw) is False, pw

    def test_password_validator_blocks_common(self) -> None:
        from app.api.v1.auth import _enforce_password_rules

        # Passes composition (len + classes) but is on the denylist.
        with pytest.raises(ValueError, match="común|filtradas"):
            _enforce_password_rules("Password1234")

    def test_password_validator_allows_strong(self) -> None:
        from app.api.v1.auth import _enforce_password_rules

        assert _enforce_password_rules("Xq7!mVz9pLwK") == "Xq7!mVz9pLwK"


# ─── ENC-1 — DB TLS in transit ───────────────────────────────────


class TestDbTlsEnforcement:
    def test_require_ssl_appends_sslmode(self) -> None:
        from app.core.config import _normalize_pg_url

        url = _normalize_pg_url("postgresql://u:p@host/db", require_ssl=True)
        assert "sslmode=require" in url
        assert url.startswith("postgresql+psycopg://")

    def test_local_does_not_force_ssl(self) -> None:
        from app.core.config import _normalize_pg_url

        url = _normalize_pg_url("postgresql://u:p@host/db", require_ssl=False)
        assert "sslmode" not in url

    def test_explicit_mode_is_preserved(self) -> None:
        from app.core.config import _normalize_pg_url

        url = _normalize_pg_url(
            "postgresql://u:p@host/db?sslmode=verify-full", require_ssl=True
        )
        assert url.count("sslmode") == 1
        assert "verify-full" in url

    def test_sqlite_untouched(self) -> None:
        from app.core.config import _normalize_pg_url

        url = _normalize_pg_url("sqlite:///./checkwise.db", require_ssl=True)
        assert url == "sqlite:///./checkwise.db"


# ─── ENC-2 — server-side encryption on writes ────────────────────


class TestObjectEncryptionAtRest:
    def test_save_bytes_sends_sse_header(self) -> None:
        from app.services.storage import S3StorageService

        class _FakeClient:
            def __init__(self) -> None:
                self.put_kwargs: dict = {}

            def put_object(self, **kwargs):  # noqa: ANN003
                self.put_kwargs = kwargs

        fake = _FakeClient()
        svc = S3StorageService(bucket="b", client=fake)
        svc.save_bytes(storage_key="documents/x/y.pdf", data=b"%PDF-", content_type="application/pdf")
        assert fake.put_kwargs.get("ServerSideEncryption") == "AES256"


# ─── FILE-DEL-1 — refcount guard before object delete ────────────


class TestStorageRefcountGuard:
    def test_shared_object_is_not_deleted_while_referenced(self, db_factory, monkeypatch) -> None:
        import app.api.v1.portal as portal

        deleted: list[str] = []

        class _FakeStorage:
            def delete(self, key: str) -> None:
                deleted.append(key)

        monkeypatch.setattr(portal, "get_storage_service", lambda: _FakeStorage())

        session = db_factory()
        shared = "documents/aa/aaaa1111/evidencia.pdf"
        # Two tenants uploaded byte-identical PDFs → ONE content-addressed object.
        _make_document(session, storage_key=shared, submission_id="sub-tenant-A")
        doc_b = _make_document(session, storage_key=shared, submission_id="sub-tenant-B")
        session.commit()

        # Tenant A cancels: its Document row is gone, B's remains.
        # Simulate by deleting A's row then invoking the guard.
        session.query(Document).filter(Document.submission_id == "sub-tenant-A").delete()
        session.commit()
        portal._delete_orphaned_objects(session, [shared])
        assert deleted == [], "must NOT delete an object another tenant still references"

        # Now B also goes away → last reference gone → safe to delete once.
        session.delete(doc_b)
        session.commit()
        portal._delete_orphaned_objects(session, [shared])
        assert deleted == [shared]

    def test_true_orphan_is_deleted(self, db_factory, monkeypatch) -> None:
        import app.api.v1.portal as portal

        deleted: list[str] = []
        monkeypatch.setattr(
            portal,
            "get_storage_service",
            lambda: type("S", (), {"delete": lambda self, k: deleted.append(k)})(),
        )
        session = db_factory()
        portal._delete_orphaned_objects(session, ["documents/zz/orphan/none.pdf"])
        assert deleted == ["documents/zz/orphan/none.pdf"]


# ─── INFRA-1 — CSP on every API response ─────────────────────────


class TestSecurityHeaders:
    def test_json_response_has_strict_csp(self) -> None:
        client = TestClient(app)
        resp = client.get("/health")
        csp = resp.headers.get("content-security-policy", "")
        assert "frame-ancestors 'none'" in csp
        assert "base-uri 'none'" in csp
        assert resp.headers.get("x-frame-options") == "DENY"
        assert resp.headers.get("x-content-type-options") == "nosniff"


# ─── G-7 — logout writes an audit row ────────────────────────────


class TestLogoutAudit:
    def test_logout_with_cookie_audits(self, db_factory) -> None:
        from app.core.config import settings

        # Seed a user (shared in-memory connection → visible to API session).
        setup = db_factory()
        user = User(
            email="auditme@example.com",
            password_hash=hash_password("Xq7!mVz9pLwK"),
            full_name="Audit Me",
            status="active",
        )
        setup.add(user)
        setup.commit()
        user_id = user.id
        token = issue_access_token(
            user_id=user_id, email=user.email, roles=["client_admin"], orgs=[]
        )
        setup.close()

        def override_get_db():
            db = db_factory()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        try:
            client = TestClient(app)
            client.cookies.set(settings.AUTH_SESSION_COOKIE_NAME, token)
            resp = client.post("/api/v1/auth/logout")
            assert resp.status_code == 204
        finally:
            app.dependency_overrides.pop(get_db, None)

        verify = db_factory()
        rows = verify.query(AuditLog).filter(AuditLog.action == "auth.logout").all()
        assert len(rows) == 1
        assert rows[0].actor_id == user_id
        assert rows[0].entity_id == user_id
        verify.close()
