"""Phase 10D — server-side signed-link sharing for reports.

Lets a logged-in user mint a public URL for a specific
``ReportVersion`` that an unauthenticated recipient can open in a
browser. Reuses the schema scaffolded in migration 0009_reports_core
(``report_shares`` table) — every column the model defines
(``token_hash``, ``audience``, ``watermark``, ``password_hash``,
``expires_at``, ``revoked_at``, ``last_accessed_at``, ``access_count``)
is wired here without a new migration.

Token model:
  * 32-byte URL-safe token from :mod:`secrets`. The raw value is
    returned ONCE from :func:`mint_share` and never persisted —
    only the SHA-256 hash lives in the DB.
  * Lookup at consume time is SHA-256(presented_token) → indexed
    column. Constant-time relative to the token contents because
    we never compare raw tokens, only their digests.
  * Same pattern the password-reset flow uses
    (``hash_password_reset_token``). Kept independent so the two
    surfaces evolve separately.

Optional password challenge:
  * Per-link bcrypt hash stored in ``password_hash``. Consume
    checks via :func:`verify_password`.
  * The router exposes an "unlock" endpoint that issues a
    short-lived signed cookie so the recipient doesn't re-enter
    the password on every page refresh.

Lifecycle:
  * Revoke sets ``revoked_at = now()``. The row stays in the
    table as an audit record of "this token existed and was
    explicitly turned off". A revoked row never resolves; the
    consume path returns the same not-available error as an
    expired row so an attacker can't probe revocation state.
  * Expired rows (``expires_at < now()``) behave identically to
    revoked ones at the consume site.
  * Unknown tokens return the same shape — no enumeration.

Out of scope here (will land later):
  * Watermark rendering on the consumed HTML (column exists; no
    UI yet for the sender to set it).
  * One-time-use semantics / view-count cap.
  * Email-the-link flow.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import UTC, datetime
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Report, ReportShare, ReportVersion, User
from app.models.entities import utc_now
from app.services.auth import hash_password, verify_password

logger = logging.getLogger(__name__)


# 32 bytes → 43-character URL-safe base64 token. Plenty of entropy
# (~256 bits) and short enough to embed in an email signature line.
SHARE_TOKEN_BYTES: Final[int] = 32


class ShareError(Exception):
    """Base class so the API layer can catch all share-flow errors."""


class ShareNotFoundError(ShareError):
    """Token doesn't match any row. Maps to 404 — never confirm existence."""


class ShareRevokedError(ShareError):
    """Token is valid but the sender revoked it. Maps to 410."""


class ShareExpiredError(ShareError):
    """Token is valid but its expires_at has passed. Maps to 410."""


class SharePasswordRequiredError(ShareError):
    """Token requires a password and the caller didn't supply one. Maps to 401."""


class SharePasswordMismatchError(ShareError):
    """Token requires a password and the caller's was wrong. Maps to 401."""


def _hash_token(token: str) -> str:
    """SHA-256 hex digest of the raw token. Same shape as ``token_hash``
    in the DB column (length=64)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Mint
# ---------------------------------------------------------------------------


def mint_share(
    db: Session,
    *,
    report: Report,
    version: ReportVersion,
    audience: str,
    requested_by: User,
    expires_at: datetime | None = None,
    password: str | None = None,
    watermark: str | None = None,
) -> tuple[ReportShare, str]:
    """Create a share link. Returns (row, raw_token).

    The raw token is the only place the unhashed value ever exists —
    the caller MUST include it in the API response (and only this
    response) because it cannot be recovered later.

    Does NOT commit. Caller owns the transaction so the mint can be
    bundled with any audit-trail writes upstream.
    """
    raw_token = secrets.token_urlsafe(SHARE_TOKEN_BYTES)
    row = ReportShare(
        report_id=report.id,
        version_id=version.id,
        token_hash=_hash_token(raw_token),
        audience=audience,
        watermark=watermark,
        password_hash=hash_password(password) if password else None,
        expires_at=expires_at,
        created_by_user_id=requested_by.id,
    )
    db.add(row)
    db.flush()
    return row, raw_token


# ---------------------------------------------------------------------------
# Consume
# ---------------------------------------------------------------------------


def consume_share(
    db: Session,
    *,
    token: str,
    password: str | None = None,
    now: datetime | None = None,
) -> ReportShare:
    """Resolve a presented token to a ``ReportShare`` row.

    Raises typed errors the API layer maps to HTTP status codes (see
    each subclass for the mapping). On success, increments
    ``access_count`` and touches ``last_accessed_at`` — both writes
    flush but don't commit (caller owns the transaction).

    No-enumeration contract: unknown / revoked / expired tokens all
    raise distinct exception types, but the API layer can choose to
    collapse them into one response shape if it wants to be paranoid.
    Currently the router does distinguish (404 / 410 / 410) because
    expired is a fundamentally different recovery path for the
    sender than revoked.
    """
    if not token:
        raise ShareNotFoundError("Empty token.")
    row = db.scalar(
        select(ReportShare).where(ReportShare.token_hash == _hash_token(token))
    )
    if row is None:
        raise ShareNotFoundError("Token not recognised.")
    if row.revoked_at is not None:
        raise ShareRevokedError("Share has been revoked.")
    current = now or utc_now()
    # SQLite (and any other DB that strips tzinfo from
    # ``DateTime(timezone=True)``) returns a tz-naive datetime even
    # when we stored a tz-aware one. Coerce to UTC for the
    # comparison so the test/dev SQLite path and the prod Postgres
    # path behave identically.
    expires = row.expires_at
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if expires is not None and expires <= current:
        raise ShareExpiredError("Share has expired.")
    if row.password_hash:
        if not password:
            raise SharePasswordRequiredError("Password required.")
        if not verify_password(password, row.password_hash):
            raise SharePasswordMismatchError("Password does not match.")

    # Successful consume — bump audit counters. Both writes flush but
    # don't commit; the consume endpoint commits at the end so a
    # failed render upstream doesn't leave a phantom access tick.
    row.access_count = (row.access_count or 0) + 1
    row.last_accessed_at = current
    db.flush()
    return row


# ---------------------------------------------------------------------------
# Revoke
# ---------------------------------------------------------------------------


def revoke_share(db: Session, *, share: ReportShare, now: datetime | None = None) -> None:
    """Mark the share revoked. Idempotent — re-revoking is a no-op.

    Doesn't commit. The row stays on the table as an audit record of
    "this token existed and was explicitly turned off"; we never
    hard-delete shares.
    """
    if share.revoked_at is not None:
        return
    share.revoked_at = now or utc_now()
    db.flush()


__all__ = [
    "SHARE_TOKEN_BYTES",
    "ShareError",
    "ShareExpiredError",
    "ShareNotFoundError",
    "SharePasswordMismatchError",
    "SharePasswordRequiredError",
    "ShareRevokedError",
    "consume_share",
    "mint_share",
    "revoke_share",
]
