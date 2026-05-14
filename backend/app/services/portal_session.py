"""Portal session token service.

CheckWise 1.7 replaces the V1.2 "client stores opaque token in
localStorage" model with an httpOnly cookie carrying a signed JWT.

Threat model the cookie addresses:
    * Workspace ID and access token are no longer reachable from JS,
      so an XSS in any portal page can't lift the session.
    * Token tampering is caught by signature verification.
    * Token reuse across browsers is bounded by expiry.

Backend remains the source of truth for tenant ownership. The cookie
payload below is *display + routing*; every protected endpoint still
validates the workspace_id against the path and the access_token
against the ProviderWorkspace row in DB.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import jwt

from app.core.config import settings


@dataclass(frozen=True)
class PortalSessionClaims:
    """Decoded payload of a portal session cookie."""

    workspace_id: str
    access_token: str
    issued_at: datetime
    expires_at: datetime


class PortalSessionError(Exception):
    """Raised when a cookie can't be decoded or has expired."""


def issue_portal_session_token(
    *, workspace_id: str, access_token: str, now: datetime | None = None
) -> tuple[str, datetime]:
    """Sign a session cookie. Returns (jwt_string, expires_at)."""
    issued_at = (now or datetime.now(UTC)).replace(microsecond=0)
    expires_at = issued_at.fromtimestamp(
        issued_at.timestamp() + settings.PORTAL_SESSION_EXPIRES_MINUTES * 60,
        tz=UTC,
    )
    payload = {
        "sub": workspace_id,
        "tok": access_token,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
        "typ": "portal_session",
    }
    token = jwt.encode(
        payload,
        settings.AUTH_JWT_SECRET,
        algorithm=settings.AUTH_JWT_ALGORITHM,
    )
    return token, expires_at


def verify_portal_session_token(token: str) -> PortalSessionClaims:
    """Decode + validate a portal session cookie.

    Raises PortalSessionError on any failure (expired, bad signature,
    wrong type, missing claims). Callers should map this to a 401.
    """
    if not token:
        raise PortalSessionError("Empty session token.")
    try:
        decoded = jwt.decode(
            token,
            settings.AUTH_JWT_SECRET,
            algorithms=[settings.AUTH_JWT_ALGORITHM],
            options={"require": ["sub", "tok", "iat", "exp", "typ"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise PortalSessionError("Session expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise PortalSessionError(f"Invalid session token: {exc}") from exc

    if decoded.get("typ") != "portal_session":
        raise PortalSessionError("Wrong token type.")

    workspace_id = decoded.get("sub")
    access_token = decoded.get("tok")
    if not isinstance(workspace_id, str) or not isinstance(access_token, str):
        raise PortalSessionError("Malformed session claims.")

    return PortalSessionClaims(
        workspace_id=workspace_id,
        access_token=access_token,
        issued_at=datetime.fromtimestamp(int(decoded["iat"]), tz=UTC),
        expires_at=datetime.fromtimestamp(int(decoded["exp"]), tz=UTC),
    )
