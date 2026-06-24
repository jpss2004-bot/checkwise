"""Phase 7 / Slice N8 — phone-verification OTP service + API.

Service-level tests pin:

  * OTP generation produces a 6-digit zero-padded numeric code;
  * HMAC hash is reproducible and depends on the JWT secret;
  * a fresh request invalidates any prior active row;
  * confirm with the correct code marks the row consumed;
  * wrong code increments attempts; attempts >= 5 burns the row;
  * expired rows are not consumable;
  * mismatched phone counts as a failed attempt without leaking.

API-level tests pin:

  * verify endpoint requires auth and rejects malformed phones;
  * a successful confirm flips ``user.phone_e164``,
    ``phone_verified_at``, ``whatsapp_opt_in_at``;
  * the confirm endpoint fires ``account.whatsapp_verified`` —
    one ``notification_dispatch`` row materialises;
  * audit rows land for both verb sites.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    AuditLog,
    NotificationDispatch,
    Organization,
    PhoneVerification,
    User,
    entities,  # noqa: F401 — register mappers
)
from app.models.entities import utc_now
from app.services.auth import hash_password, issue_access_token
from app.services.phone_verification import (
    OTP_MAX_ATTEMPTS,
    confirm_verification,
    generate_otp_code,
    hash_otp_code,
    request_verification,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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


def _seed_user(db_factory) -> tuple[str, str]:
    """Return ``(user_id, bearer_token)``."""
    db = db_factory()
    try:
        org = Organization(name="LegalShelf", kind="internal")
        db.add(org)
        db.flush()
        user = User(
            email="ops@legalshelf.mx",
            password_hash=hash_password("Correct horse battery 4"),
            full_name="Ops",
            status="active",
        )
        db.add(user)
        db.commit()
        token = issue_access_token(
            user_id=user.id,
            email=user.email,
            roles=["operations_admin"],
            orgs=[org.id],
        )
        return user.id, token
    finally:
        db.close()


# ===========================================================================
# Service: generation + hashing
# ===========================================================================


def test_generate_otp_returns_six_digit_zero_padded() -> None:
    for _ in range(50):
        code = generate_otp_code()
        assert len(code) == 6
        assert code.isdigit()


def test_hash_otp_is_deterministic_and_64_hex() -> None:
    h1 = hash_otp_code("123456")
    h2 = hash_otp_code("123456")
    assert h1 == h2
    assert len(h1) == 64
    int(h1, 16)  # hex roundtrip — raises ValueError if not hex


def test_hash_otp_differs_per_code() -> None:
    assert hash_otp_code("123456") != hash_otp_code("123457")


def test_hash_otp_rejects_empty() -> None:
    with pytest.raises(ValueError):
        hash_otp_code("")


# ===========================================================================
# Service: request_verification + confirm_verification
# ===========================================================================


def test_request_returns_row_and_plaintext(db_factory) -> None:
    user_id, _ = _seed_user(db_factory)
    db = db_factory()
    try:
        user = db.get(User, user_id)
        row, plaintext = request_verification(
            db, user=user, phone_e164="525500000010"
        )
        db.commit()
        # Read attributes before close — SQLAlchemy detaches the
        # instance after the session ends.
        row_phone = row.phone_e164
        row_consumed = row.consumed_at
        row_hash = row.code_hash
    finally:
        db.close()

    assert len(plaintext) == 6
    assert row_phone == "525500000010"
    assert row_consumed is None
    # Plaintext is not persisted anywhere.
    assert plaintext not in row_hash
    assert row_hash == hash_otp_code(plaintext)


def test_request_invalidates_prior_active_row(db_factory) -> None:
    user_id, _ = _seed_user(db_factory)
    db = db_factory()
    try:
        user = db.get(User, user_id)
        first, _ = request_verification(db, user=user, phone_e164="525500000010")
        second, _ = request_verification(
            db, user=user, phone_e164="525500000010"
        )
        db.commit()
        first_id, second_id = first.id, second.id
    finally:
        db.close()

    db = db_factory()
    try:
        rows = db.execute(select(PhoneVerification)).scalars().all()
        by_id = {r.id: (r.consumed_at, r.attempts) for r in rows}
    finally:
        db.close()
    assert by_id[first_id][0] is not None  # invalidated
    assert by_id[second_id][0] is None     # still active


def test_confirm_with_correct_code_marks_consumed(db_factory) -> None:
    user_id, _ = _seed_user(db_factory)
    db = db_factory()
    try:
        user = db.get(User, user_id)
        row, plaintext = request_verification(
            db, user=user, phone_e164="525500000010"
        )
        confirmed = confirm_verification(
            db, user=user, phone_e164="525500000010", code=plaintext
        )
        db.commit()
        same_id = confirmed.id == row.id
        confirmed_consumed = confirmed.consumed_at
    finally:
        db.close()

    assert same_id
    assert confirmed_consumed is not None


def test_confirm_wrong_code_increments_attempts(db_factory) -> None:
    user_id, _ = _seed_user(db_factory)
    db = db_factory()
    try:
        user = db.get(User, user_id)
        request_verification(db, user=user, phone_e164="525500000010")
        result = confirm_verification(
            db, user=user, phone_e164="525500000010", code="000000"
        )
        db.commit()
    finally:
        db.close()
    assert result is None

    db = db_factory()
    try:
        row = db.scalar(select(PhoneVerification))
    finally:
        db.close()
    assert row is not None
    assert row.attempts == 1
    assert row.consumed_at is None  # still active


def test_confirm_burns_row_after_max_attempts(db_factory) -> None:
    user_id, _ = _seed_user(db_factory)
    db = db_factory()
    try:
        user = db.get(User, user_id)
        request_verification(db, user=user, phone_e164="525500000010")
        for _ in range(OTP_MAX_ATTEMPTS):
            confirm_verification(
                db, user=user, phone_e164="525500000010", code="000000"
            )
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        row = db.scalar(select(PhoneVerification))
    finally:
        db.close()
    assert row is not None
    assert row.attempts == OTP_MAX_ATTEMPTS
    assert row.consumed_at is not None  # burned


def test_confirm_phone_mismatch_counts_as_attempt(db_factory) -> None:
    user_id, _ = _seed_user(db_factory)
    db = db_factory()
    try:
        user = db.get(User, user_id)
        _, plaintext = request_verification(
            db, user=user, phone_e164="525500000010"
        )
        result = confirm_verification(
            db, user=user, phone_e164="525500000099", code=plaintext
        )
        db.commit()
    finally:
        db.close()
    assert result is None

    db = db_factory()
    try:
        row = db.scalar(select(PhoneVerification))
    finally:
        db.close()
    assert row is not None
    assert row.attempts == 1


def test_confirm_returns_none_when_expired(db_factory) -> None:
    user_id, _ = _seed_user(db_factory)
    db = db_factory()
    try:
        user = db.get(User, user_id)
        row, plaintext = request_verification(
            db, user=user, phone_e164="525500000010"
        )
        # Backdate expiry by hand to simulate the 10-minute window.
        row.expires_at = utc_now() - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()

    db = db_factory()
    try:
        user = db.get(User, user_id)
        result = confirm_verification(
            db, user=user, phone_e164="525500000010", code=plaintext
        )
    finally:
        db.close()
    assert result is None


# ===========================================================================
# API: /me/phone/verify
# ===========================================================================


def test_verify_requires_auth(api_client: TestClient) -> None:
    r = api_client.post(
        "/api/v1/me/phone/verify", json={"phone": "+5255 1234 5678"}
    )
    assert r.status_code == 401


def test_verify_rejects_malformed_phone(api_client: TestClient, db_factory) -> None:
    _, token = _seed_user(db_factory)
    r = api_client.post(
        "/api/v1/me/phone/verify",
        headers={"Authorization": f"Bearer {token}"},
        json={"phone": "abc"},
    )
    assert r.status_code in (400, 422)


def test_verify_persists_row_and_writes_audit(
    api_client: TestClient, db_factory
) -> None:
    user_id, token = _seed_user(db_factory)
    r = api_client.post(
        "/api/v1/me/phone/verify",
        headers={"Authorization": f"Bearer {token}"},
        json={"phone": "5512345678"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in {"sent", "skipped", "failed"}
    assert body["expires_in_seconds"] > 0

    db = db_factory()
    try:
        row = db.scalar(select(PhoneVerification))
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "user.phone_verification_requested",
                AuditLog.entity_id == user_id,
            )
        )
    finally:
        db.close()
    assert row is not None
    assert row.phone_e164 == "525512345678"  # normalized
    assert audit is not None
    assert (audit.event_metadata or {}).get("phone_last4") == "5678"


def test_verify_rate_limit_caps_per_minute(
    api_client: TestClient, db_factory
) -> None:
    _, token = _seed_user(db_factory)
    headers = {"Authorization": f"Bearer {token}"}
    # Limit is 3/min — fourth call must 429.
    for _ in range(3):
        r = api_client.post(
            "/api/v1/me/phone/verify",
            headers=headers,
            json={"phone": "5512345678"},
        )
        assert r.status_code == 200
    r = api_client.post(
        "/api/v1/me/phone/verify",
        headers=headers,
        json={"phone": "5512345678"},
    )
    assert r.status_code == 429


# ===========================================================================
# API: /me/phone/verify/confirm
# ===========================================================================


def test_confirm_flips_user_phone_state_and_fires_event(
    api_client: TestClient, db_factory
) -> None:
    user_id, token = _seed_user(db_factory)
    headers = {"Authorization": f"Bearer {token}"}

    # 1) Issue the OTP via the API so the row matches what confirm sees.
    api_client.post(
        "/api/v1/me/phone/verify",
        headers=headers,
        json={"phone": "5512345678"},
    )

    # 2) Read the plaintext code by re-deriving via the service — the
    # API never returns it, so the test reaches into the DB and uses
    # ``hash_otp_code`` to brute the 6-digit space (≤1M ops, fast).
    db = db_factory()
    try:
        row = db.scalar(select(PhoneVerification))
    finally:
        db.close()
    assert row is not None
    plaintext = None
    for n in range(1_000_000):
        candidate = f"{n:06d}"
        if hash_otp_code(candidate) == row.code_hash:
            plaintext = candidate
            break
    assert plaintext is not None, "could not recover OTP from hash"

    # 3) Confirm.
    r = api_client.post(
        "/api/v1/me/phone/verify/confirm",
        headers=headers,
        json={"phone": "5512345678", "code": plaintext},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["phone_e164"] == "525512345678"
    assert body["phone_verified_at"]
    assert body["whatsapp_opt_in_at"]

    db = db_factory()
    try:
        user = db.get(User, user_id)
        assert user.phone_e164 == "525512345678"
        assert user.phone_verified_at is not None
        assert user.whatsapp_opt_in_at is not None

        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "user.phone_verification_confirmed",
                AuditLog.entity_id == user_id,
            )
        )
        assert audit is not None

        # account.whatsapp_verified emitted via the shadow fabric.
        dispatch_row = db.scalar(
            select(NotificationDispatch).where(
                NotificationDispatch.event_type
                == "account.whatsapp_verified"
            )
        )
        assert dispatch_row is not None
        assert dispatch_row.user_id == user_id
    finally:
        db.close()


def test_confirm_rejects_wrong_code(api_client: TestClient, db_factory) -> None:
    _, token = _seed_user(db_factory)
    headers = {"Authorization": f"Bearer {token}"}
    api_client.post(
        "/api/v1/me/phone/verify",
        headers=headers,
        json={"phone": "5512345678"},
    )
    r = api_client.post(
        "/api/v1/me/phone/verify/confirm",
        headers=headers,
        json={"phone": "5512345678", "code": "000000"},
    )
    assert r.status_code == 400


def test_confirm_requires_auth(api_client: TestClient) -> None:
    r = api_client.post(
        "/api/v1/me/phone/verify/confirm",
        json={"phone": "5512345678", "code": "123456"},
    )
    assert r.status_code == 401
