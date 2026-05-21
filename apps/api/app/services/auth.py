"""Auth primitives — password hashing + JWT issue/verify.

Patch 6 (Auth + RBAC) introduces real LegalShelf-staff accounts. This
module hides the cryptographic moving parts behind a small surface so
the rest of the app does not need to know which library implements
hashing or token signing.

Decisions:
- Passwords are hashed with bcrypt (Modular Crypt Format), salt
  generated per call. Rounds come from ``settings.AUTH_BCRYPT_ROUNDS``.
- Tokens are JWT, HS256 by default. Payload carries ``sub`` (user id),
  ``email``, ``roles`` (sorted unique list, e.g. ``["internal_admin"]``),
  ``orgs`` (sorted unique list of organization ids the user belongs to),
  ``iat`` and ``exp``. No refresh token in V1 — re-issue on /login.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass

import bcrypt
import jwt

from app.core.config import settings

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


def hash_password(plaintext: str) -> str:
    """Hash a plaintext password with bcrypt + per-call random salt."""
    if not plaintext:
        raise ValueError("password is empty")
    salt = bcrypt.gensalt(rounds=settings.AUTH_BCRYPT_ROUNDS)
    return bcrypt.hashpw(plaintext.encode("utf-8"), salt).decode("utf-8")


def verify_password(plaintext: str, hashed: str | None) -> bool:
    """Constant-time check. Returns False for empty / missing hashes."""
    if not plaintext or not hashed:
        return False
    try:
        return bcrypt.checkpw(plaintext.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        # Malformed hash. Treat as a mismatch; the caller will return a
        # generic 401 so we don't leak hash corruption to the client.
        return False


# ---------------------------------------------------------------------------
# Password-reset tokens
# ---------------------------------------------------------------------------


def generate_password_reset_token() -> str:
    """Create a high-entropy URL-safe token for one password reset."""
    return secrets.token_urlsafe(32)


def hash_password_reset_token(token: str) -> str:
    """Hash reset tokens before persistence.

    The raw token only lives in the emailed link. A database leak should
    not give an attacker usable reset URLs.
    """
    if not token:
        raise ValueError("reset token is empty")
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TokenClaims:
    user_id: str
    email: str
    roles: tuple[str, ...]
    orgs: tuple[str, ...]
    issued_at: int
    expires_at: int


class TokenError(Exception):
    """Raised when a token cannot be decoded or has expired."""


def issue_access_token(
    *,
    user_id: str,
    email: str,
    roles: list[str],
    orgs: list[str],
    now: int | None = None,
) -> str:
    """Build a signed JWT for ``user_id``. ``now`` lets tests pin time."""
    issued_at = int(time.time()) if now is None else now
    expires_at = issued_at + settings.AUTH_JWT_EXPIRES_MINUTES * 60
    payload = {
        "sub": user_id,
        "email": email,
        "roles": sorted(set(roles)),
        "orgs": sorted(set(orgs)),
        "iat": issued_at,
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.AUTH_JWT_SECRET, algorithm=settings.AUTH_JWT_ALGORITHM)


def decode_access_token(token: str) -> TokenClaims:
    """Verify signature + expiry and return structured claims.

    Raises ``TokenError`` on any failure (bad signature, expired, missing
    required fields). Callers translate that into a 401.
    """
    if not token:
        raise TokenError("missing token")
    try:
        payload = jwt.decode(
            token,
            settings.AUTH_JWT_SECRET,
            algorithms=[settings.AUTH_JWT_ALGORITHM],
        )
    except jwt.ExpiredSignatureError as exc:  # pragma: no cover - thin wrap
        raise TokenError("token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError(f"invalid token: {exc}") from exc

    try:
        return TokenClaims(
            user_id=str(payload["sub"]),
            email=str(payload["email"]),
            roles=tuple(payload.get("roles") or ()),
            orgs=tuple(payload.get("orgs") or ()),
            issued_at=int(payload["iat"]),
            expires_at=int(payload["exp"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise TokenError("token payload malformed") from exc
