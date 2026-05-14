"""Auth + RBAC endpoints (Patch 6).

Real LegalShelf-staff authentication: email + password -> JWT.

Public surface:
- ``POST /api/v1/auth/login`` — verify credentials, return a signed JWT
  along with the user identity and the roles + organization ids the
  token carries.
- ``GET /api/v1/auth/me`` — return the current user resolved from the
  Authorization header.

Reusable dependencies + helpers exported for the rest of the codebase:
- ``get_current_user`` — FastAPI dependency. Reads
  ``Authorization: Bearer <token>``, verifies the JWT, hydrates the
  ``User`` row, and returns ``CurrentUser``. 401 on any failure.
- ``require_role(role)`` — dependency factory enforcing the role is
  present in the user's active memberships (regardless of org). 403
  if missing.
- ``require_org_role(role)`` — dependency factory enforcing the role
  is held *within the path's ``organization_id``*. 403 if missing.

The provider portal (``X-Workspace-Token``) is intentionally untouched
— it lives in ``portal.py`` and authenticates a workspace, not a user.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Membership, User
from app.models.entities import utc_now
from app.services.auth import (
    TokenClaims,
    TokenError,
    decode_access_token,
    issue_access_token,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])
DbSession = Annotated[Session, Depends(get_db)]


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


def _normalize_email(value: str) -> str:
    """Trim + lowercase. Reject anything without an ``@``."""
    cleaned = (value or "").strip().lower()
    if "@" not in cleaned or len(cleaned) < 3:
        raise ValueError("invalid email")
    return cleaned


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=1, max_length=255)

    @field_validator("email")
    @classmethod
    def _norm_email(cls, value: str) -> str:
        return _normalize_email(value)


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    status: str
    last_login_at: datetime | None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_at: datetime
    user: UserOut
    roles: list[str]
    organization_ids: list[str]


class CurrentUser(BaseModel):
    """Hydrated request principal — what every protected endpoint sees."""

    user: UserOut
    roles: list[str]
    organization_ids: list[str]
    token_expires_at: datetime


# ---------------------------------------------------------------------------
# Helpers + dependencies (declared before routes so /me can reference them)
# ---------------------------------------------------------------------------


# Pre-computed bcrypt hash of an arbitrary value, used to keep the
# unknown-user branch in /login spending roughly the same amount of
# CPU as the known-user-bad-password branch. Not a security boundary
# — the value never matches a real password.
_DUMMY_HASH = "$2b$12$C6UzMDM.H6dfI/f/IKxGhuJ5xQk/Q0qfgY7r5y4Qx0K3qj1l6Q0aS"


def _bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header")
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid Authorization header")
    token = parts[1].strip()
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Empty bearer token")
    return token


def _claims_from_header(authorization: str | None) -> TokenClaims:
    token = _bearer_token(authorization)
    try:
        return decode_access_token(token)
    except TokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


def get_current_user(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    claims = _claims_from_header(authorization)
    user = db.get(User, claims.user_id)
    if user is None or user.status != "active":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="User not active")

    return CurrentUser(
        user=UserOut(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            status=user.status,
            last_login_at=user.last_login_at,
        ),
        roles=list(claims.roles),
        organization_ids=list(claims.orgs),
        token_expires_at=datetime.fromtimestamp(claims.expires_at, tz=UTC),
    )


def require_role(role: str) -> Callable[..., CurrentUser]:
    """Dependency factory: 403 unless the user carries ``role``."""

    def _dep(
        current: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> CurrentUser:
        if role not in current.roles:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, detail=f"Role '{role}' required"
            )
        return current

    return _dep


def require_org_role(role: str) -> Callable[..., CurrentUser]:
    """The role must be held within the path's ``organization_id``.

    Re-checks the role inside the org against the DB (not just the
    token), so a stale-but-valid token cannot use a role it lost since
    issue time.
    """

    def _dep(
        organization_id: str,
        current: Annotated[CurrentUser, Depends(get_current_user)],
        db: DbSession,
    ) -> CurrentUser:
        if organization_id not in current.organization_ids:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, detail="Not a member of this organization"
            )
        membership = db.execute(
            select(Membership).where(
                Membership.user_id == current.user.id,
                Membership.organization_id == organization_id,
                Membership.role == role,
                Membership.status == "active",
            )
        ).scalar_one_or_none()
        if membership is None:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role}' required in this organization",
            )
        return current

    return _dep


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: DbSession) -> LoginResponse:
    user = db.execute(
        select(User).where(User.email == payload.email)
    ).scalar_one_or_none()

    # Generic 401 for both unknown-user and bad-password so the response
    # does not leak whether an email exists. Bcrypt's constant-time check
    # still runs to keep timing roughly comparable.
    if user is None or user.status != "active":
        verify_password(payload.password, _DUMMY_HASH)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    memberships = (
        db.execute(
            select(Membership).where(
                Membership.user_id == user.id,
                Membership.status == "active",
            )
        )
        .scalars()
        .all()
    )
    roles = sorted({m.role for m in memberships})
    org_ids = sorted({m.organization_id for m in memberships})

    token = issue_access_token(
        user_id=user.id, email=user.email, roles=roles, orgs=org_ids
    )
    user.last_login_at = utc_now()
    db.flush()

    claims = decode_access_token(token)
    return LoginResponse(
        access_token=token,
        expires_at=datetime.fromtimestamp(claims.expires_at, tz=UTC),
        user=UserOut(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            status=user.status,
            last_login_at=user.last_login_at,
        ),
        roles=roles,
        organization_ids=org_ids,
    )


@router.get("/me", response_model=CurrentUser)
def me(current: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
    return current
