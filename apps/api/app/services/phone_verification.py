"""Phase 7 / Slice N8 — phone-verification OTP service.

Generates 6-digit numeric codes, stores their HMAC-SHA256 hash, and
validates inbound confirmation attempts. The plaintext code only
lives in the user's phone (delivered via WhatsApp) and in the
request body during confirm — never on disk.

Contract:

  * :func:`request_verification` — creates a fresh row, invalidates
    any prior active rows for the user, returns ``(row, plaintext_code)``.
    The plaintext is the caller's responsibility to send out-of-band
    via WhatsApp (or, in dev, to log for the operator).

  * :func:`confirm_verification` — locates the active row, validates
    the inbound code via constant-time HMAC comparison, increments
    the attempts counter on failure, and on success marks
    ``consumed_at`` and returns the row.

Brute-force defenses:

  * ``OTP_MAX_ATTEMPTS`` (5) — exceeding the cap auto-invalidates
    the active row; the caller sees the same 400 as "no active
    code" so the failure modes converge.
  * ``OTP_TTL_SECONDS`` (600) — codes expire 10 minutes after issue.
  * The sliding-window rate limiter ``phone_verify_limiter`` caps
    request rate per user; see :mod:`app.api.v1.me`.

Hashing: HMAC-SHA256 keyed on ``settings.AUTH_JWT_SECRET``. Short
OTPs are not amenable to per-row salt + slow hash without a UX
cost (verify gets sluggish); HMAC + the attempts counter is the
established pattern. A DB leak does not give an attacker usable
codes — they would need the JWT secret, and at that point the
attacker can mint sessions directly.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import PhoneVerification, User
from app.models.entities import utc_now


def _as_utc(value: datetime) -> datetime:
    """Normalize a (possibly naive, SQLite-roundtripped) datetime to
    timezone-aware UTC. Postgres preserves the tz on
    ``DateTime(timezone=True)``; SQLite strips it. This helper keeps
    the comparison portable."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)

OTP_LENGTH = 6
OTP_TTL_SECONDS = 600  # 10 minutes
OTP_MAX_ATTEMPTS = 5


def generate_otp_code() -> str:
    """Six-digit numeric code, zero-padded.

    ``secrets.randbelow`` uses the OS CSPRNG so the codes are not
    predictable from one another.
    """
    n = secrets.randbelow(10**OTP_LENGTH)
    return f"{n:0{OTP_LENGTH}d}"


def hash_otp_code(code: str) -> str:
    """HMAC-SHA256(code, key=AUTH_JWT_SECRET) → hex string.

    Constant-time to compute (HMAC is fixed-cost per input). Result
    is 64 hex chars — matches the ``code_hash`` column width.
    """
    if not code:
        raise ValueError("OTP code is empty")
    key = settings.AUTH_JWT_SECRET.encode("utf-8")
    return hmac.new(key, code.encode("utf-8"), hashlib.sha256).hexdigest()


def request_verification(
    db: Session, *, user: User, phone_e164: str
) -> tuple[PhoneVerification, str]:
    """Create a new verification row + return the plaintext code.

    Invalidates any prior active verifications for the user by
    setting their ``consumed_at`` to now — they are now historical
    and the new row is canonical. Caller is responsible for the
    out-of-band send and for committing the transaction.
    """
    now = utc_now()
    _invalidate_active_rows(db, user_id=user.id, now=now)

    plaintext = generate_otp_code()
    row = PhoneVerification(
        user_id=user.id,
        phone_e164=phone_e164,
        code_hash=hash_otp_code(plaintext),
        expires_at=now + timedelta(seconds=OTP_TTL_SECONDS),
    )
    db.add(row)
    db.flush()
    return row, plaintext


def confirm_verification(
    db: Session, *, user: User, phone_e164: str, code: str
) -> PhoneVerification | None:
    """Validate an inbound code attempt.

    Returns the row on success (caller should set ``user.phone_e164``,
    ``phone_verified_at``, ``whatsapp_opt_in_at`` and commit). Returns
    ``None`` on every failure mode — expired, consumed, wrong code,
    attempts-exceeded, no active row, or phone mismatch. The convergent
    failure response keeps a probing attacker blind to which condition
    actually fired.
    """
    now = utc_now()
    row = db.scalar(
        select(PhoneVerification)
        .where(
            PhoneVerification.user_id == user.id,
            PhoneVerification.consumed_at.is_(None),
        )
        .order_by(PhoneVerification.created_at.desc())
        .limit(1)
    )
    if row is None:
        return None
    if _as_utc(row.expires_at) <= now:
        return None
    if row.attempts >= OTP_MAX_ATTEMPTS:
        # Already at the cap — burn the row defensively.
        row.consumed_at = now
        return None
    if row.phone_e164 != phone_e164:
        # Phone in the request body doesn't match the row we issued.
        # Count this as an attempt; do not leak which mismatch.
        row.attempts += 1
        return None

    expected = row.code_hash
    candidate = hash_otp_code(code)
    if not hmac.compare_digest(expected, candidate):
        row.attempts += 1
        if row.attempts >= OTP_MAX_ATTEMPTS:
            row.consumed_at = now
        return None

    row.consumed_at = now
    return row


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _invalidate_active_rows(db: Session, *, user_id: str, now) -> None:
    """Mark every prior active row consumed.

    Done in Python rather than a bulk UPDATE so the rows go through
    the ORM and tests can assert on the resulting state without an
    explicit refresh. The set is bounded (a user rarely has more
    than one active row), so the cost is negligible.
    """
    rows = db.scalars(
        select(PhoneVerification).where(
            PhoneVerification.user_id == user_id,
            PhoneVerification.consumed_at.is_(None),
        )
    ).all()
    for row in rows:
        row.consumed_at = now
