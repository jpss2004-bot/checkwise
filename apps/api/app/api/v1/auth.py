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

import hashlib
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import quote

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Request,
    Response,
    status,
)
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.common_passwords import is_common_password
from app.core.config import settings
from app.core.rate_limit import (
    client_ip_from_request,
    forgot_password_limiter,
    hash_identifier,
    login_limiter,
)
from app.db.session import get_db
from app.models import Membership, PasswordHistory, PasswordResetToken, User
from app.models.entities import utc_now
from app.services.audit_log import add_audit_event
from app.services.auth import (
    PASSWORD_HISTORY_DEPTH,
    TokenClaims,
    TokenError,
    bump_session_epoch,
    decode_access_token,
    generate_password_reset_token,
    hash_password,
    hash_password_reset_token,
    issue_access_token,
    password_matches_history,
    verify_password,
)
from app.services.email_delivery import send_password_reset_email
from app.services.notifications.background import emit_password_reset_in_background

router = APIRouter(prefix="/auth", tags=["auth"])
DbSession = Annotated[Session, Depends(get_db)]
log = logging.getLogger("checkwise.auth")


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
    must_change_password: bool = False
    last_login_at: datetime | None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_at: datetime
    user: UserOut
    roles: list[str]
    organization_ids: list[str]
    must_change_password: bool = False


def _apply_password_change(
    db: Session,
    user: User,
    new_plaintext: str,
) -> None:
    """Update ``user.password_hash`` to a fresh bcrypt of
    ``new_plaintext`` AFTER checking that it doesn't bcrypt-verify
    against any of the user's last ``PASSWORD_HISTORY_DEPTH`` hashes.

    Audit-finding #10 — the reuse check + history rotation are
    centralised here so set-password and reset-password share the
    same enforcement. The old hash is pushed to ``password_history``
    BEFORE rotation so the next change sees the value we just
    replaced. The oldest entries past the depth are deleted to keep
    the table compact.

    Raises ``HTTPException`` 422 when the new password is found in
    the user's history. Callers are expected to commit the session;
    this helper only stages the changes via ``db.flush()``.
    """
    prior_hashes = list(
        db.scalars(
            select(PasswordHistory.password_hash)
            .where(PasswordHistory.user_id == user.id)
            .order_by(PasswordHistory.created_at.desc())
            .limit(PASSWORD_HISTORY_DEPTH)
        )
    )
    # ``user.password_hash`` is the most-recent hash that has not yet
    # been pushed to the history table (we push lazily on change).
    # Include it in the check so the user can't immediately re-set
    # the password they currently have.
    if user.password_hash:
        prior_hashes.append(user.password_hash)
    if password_matches_history(new_plaintext, prior_hashes):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "No puedes reutilizar una contraseña reciente. "
                "Elige una distinta."
            ),
        )

    old_hash = user.password_hash
    user.password_hash = hash_password(new_plaintext)
    user.must_change_password = False
    # A password change clears any account lockout — otherwise a user who
    # self-service-resets while locked still couldn't log in until the
    # cooldown elapsed (login checks the lock before the password).
    user.failed_login_count = 0
    user.locked_until = None
    # CW-AUTH-002 — a password reset / set-password must terminate every
    # existing session (the common compromise-containment action). Bumping
    # the epoch here invalidates all outstanding tokens; the reset flow
    # forces a fresh /login, and set-password re-mints the current session's
    # token below so the active caller is not bounced mid-flow.
    bump_session_epoch(user)

    if old_hash:
        db.add(PasswordHistory(user_id=user.id, password_hash=old_hash))
        # Flush so the row we just added is visible to the
        # subsequent SELECT — without this, the count would be
        # one short and the trim would leave a stale row behind.
        db.flush()
        existing = list(
            db.scalars(
                select(PasswordHistory)
                .where(PasswordHistory.user_id == user.id)
                .order_by(PasswordHistory.created_at.desc())
            )
        )
        for stale in existing[PASSWORD_HISTORY_DEPTH:]:
            db.delete(stale)

    db.flush()


def _enforce_password_rules(value: str) -> str:
    """Mirror of the frontend ``PASSWORD_RULES`` in
    ``apps/web/lib/email-inference.ts``: ≥12 chars + at least one
    uppercase + one lowercase + one digit.

    Audit-finding #2 — without this, the backend accepted weak
    passwords (e.g., ``aaaaaaaaaaaa``) when callers bypassed the
    UI. The frontend gate alone is not a security control; bake the
    same rules into the request schema so a curl call cannot land a
    password the official UI would have rejected.
    """
    if len(value) < 12:
        raise ValueError("La contraseña debe tener al menos 12 caracteres.")
    if not any(c.isupper() for c in value):
        raise ValueError("La contraseña debe incluir al menos una letra mayúscula.")
    if not any(c.islower() for c in value):
        raise ValueError("La contraseña debe incluir al menos una letra minúscula.")
    if not any(c.isdigit() for c in value):
        raise ValueError("La contraseña debe incluir al menos un número.")
    # AUTH G-4 — reject high-frequency / breached passwords that pass the
    # composition rules (e.g. "Password1234", "Bienvenido2026"). Offline
    # denylist, no network call.
    if is_common_password(value):
        raise ValueError(
            "Esta contraseña es demasiado común o aparece en listas de "
            "contraseñas filtradas. Elige una contraseña única."
        )
    return value


class SetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _validate_password(cls, v: str) -> str:
        return _enforce_password_rules(v)


class SetPasswordResponse(BaseModel):
    user: UserOut
    must_change_password: bool
    # CW-AUTH-002 — set-password bumps the session epoch (invalidating all
    # other sessions), so it re-mints the CURRENT session's token and
    # returns it here (and as an httpOnly cookie). The caller must adopt
    # this token; the one it authenticated with is now stale.
    access_token: str
    expires_at: datetime


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)

    @field_validator("email")
    @classmethod
    def _norm_email(cls, value: str) -> str:
        return _normalize_email(value)


class ForgotPasswordResponse(BaseModel):
    message: str


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=20, max_length=256)
    new_password: str = Field(..., min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _validate_password(cls, v: str) -> str:
        return _enforce_password_rules(v)


class ResetPasswordResponse(BaseModel):
    message: str


class ResetPasswordPreviewResponse(BaseModel):
    """Audit-finding #5 — lightweight preview lets ``/reset-password``
    show the user *which* account they are about to reset.

    Returning the full email is acceptable: the recipient already
    possesses the secret token, so they already have authorization
    over the account. The endpoint cannot be used to enumerate
    accounts without first holding a valid (unexpired, unused)
    token issued by ``/auth/forgot-password``.
    """

    email: str


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
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Falta el encabezado de autorización.",
        )
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Encabezado de autorización inválido.",
        )
    token = parts[1].strip()
    if not token:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="El token de autorización está vacío.",
        )
    return token


def _claims_from_header(authorization: str | None) -> TokenClaims:
    token = _bearer_token(authorization)
    try:
        return decode_access_token(token)
    except TokenError as exc:
        # INFRA-6 — return a stable, generic message rather than echoing
        # the JWT library's reason ("Signature verification failed",
        # "Not enough segments", …). The frontend treats every 401 the
        # same (clear session → /login), so nothing is lost and decoder
        # internals stop crossing the trust boundary.
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticación inválido o expirado.",
        ) from exc


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _is_account_locked(user: User) -> bool:
    return user.locked_until is not None and _as_utc(user.locked_until) > utc_now()


# NOTE: the lockout state is enforced (a locked account is rejected
# pre-password) but never surfaced to the caller with a distinct message
# or status — login returns the same generic 401 for locked, unknown, and
# bad-password cases so the response can't be used to enumerate which
# emails exist (a 401-vs-429 oracle). The retry-minutes / lockout-detail
# formatters were therefore removed.


def _register_failed_login(db: Session, user: User) -> None:
    """Increment the consecutive-failure counter; lock the account once it
    reaches the threshold (then reset the counter so the post-cooldown
    window is fresh). No-op when lockout is disabled (THRESHOLD <= 0)."""
    threshold = settings.AUTH_LOCKOUT_THRESHOLD
    if threshold <= 0:
        return
    user.failed_login_count = (user.failed_login_count or 0) + 1
    if user.failed_login_count >= threshold:
        user.locked_until = utc_now() + timedelta(
            minutes=settings.AUTH_LOCKOUT_MINUTES
        )
        user.failed_login_count = 0
    db.commit()


def _email_log_hash(email: str) -> str:
    return hashlib.sha256(email.encode("utf-8")).hexdigest()[:12]


def _client_ip(request: Request) -> str:
    """Best-effort IP for rate-limit bucketing only — never authoritative
    for authorization. Thin wrapper over the canonical
    :func:`client_ip_from_request` resolver (rightmost ``X-Forwarded-For``
    hop behind Render's single trusted proxy → X-Real-IP → socket peer),
    so the spoofable leftmost-XFF parsing lives in exactly one place."""
    return client_ip_from_request(request)


_RATE_LIMITED_DETAIL = (
    "Demasiados intentos. Espera unos minutos antes de volver a intentar."
)


# Paths that a user with ``must_change_password=True`` is allowed to reach
# before clearing the flag. Anything else returns 403 from
# ``get_current_user``. Kept narrow on purpose: the user must be able to
# (a) read their own identity to render the forced-password screen and
# (b) submit the new password. Cross-referenced with
# ``must_change_password_allowed`` in
# ``app/security/route_policy_manifest.json``; the manifest test fails
# CI if a new route deviates from this list silently.
_PASSWORD_GATE_ALLOWED_PATHS = frozenset(
    {
        "/api/v1/auth/me",
        "/api/v1/auth/set-password",
    }
)


_PASSWORD_RESET_REQUIRED_DETAIL = (
    "Debes establecer una nueva contraseña antes de continuar."
)


def _enforce_login_rate_limit(request: Request, email: str) -> None:
    """Sliding-window cap on /auth/login. Buckets are (ip, email) so a
    legitimate user typing a typo at a busy IP cannot lock another user
    out, but a credential-stuffing run from one IP across many emails
    still trips the IP-only bucket below."""
    limit = settings.AUTH_LOGIN_RATE_LIMIT_PER_MINUTE
    if limit <= 0:
        return
    ip = _client_ip(request)
    ip_bucket = f"login:ip:{hash_identifier(ip)}"
    email_bucket = f"login:email:{hash_identifier(email)}"
    # Per-IP limit is more permissive (corporate NATs share IPs); the
    # per-(ip,email) pair gets the tighter cap.
    ok_ip = login_limiter.check(ip_bucket, limit=limit * 3, window_seconds=60)
    ok_pair = login_limiter.check(
        f"login:ip-email:{hash_identifier(ip)}:{hash_identifier(email)}",
        limit=limit,
        window_seconds=60,
    )
    # Cross-IP per-email cap: without it, an attacker who rotates the
    # (now rightmost-pinned, but defense-in-depth) source IP could spray a
    # single account past the per-(ip,email) bucket. A small multiple of
    # the pair limit leaves headroom for one user legitimately hitting the
    # form from a couple of devices/networks while still capping a spray.
    ok_email = login_limiter.check(
        email_bucket, limit=limit * 5, window_seconds=60
    )
    if not ok_ip or not ok_pair or not ok_email:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, detail=_RATE_LIMITED_DETAIL
        )


def _enforce_forgot_password_rate_limit(request: Request, email: str) -> None:
    """Tight cap on /auth/forgot-password to avoid reset-link enumeration
    + mail-bombing. Lower volume than login because resets are rarer.

    forgot-password has NO account lockout (unlike login), so rate
    limiting is its only brute-force / abuse guard. Two buckets:

    * ``ip_bucket`` (per-IP) bounds enumeration sweeps from one source.
    * ``email_bucket`` (per-EMAIL, **cross-IP** — the key carries no IP
      component) is the mailbomb guard: it caps how many reset emails a
      single address can be sent per hour *regardless* of how many source
      IPs the requests come from, so XFF rotation can't be used to flood a
      known mailbox past the per-IP cap.
    """
    limit = settings.AUTH_FORGOT_PASSWORD_RATE_LIMIT_PER_HOUR
    if limit <= 0:
        return
    ip = _client_ip(request)
    ip_bucket = f"forgot:ip:{hash_identifier(ip)}"
    email_bucket = f"forgot:email:{hash_identifier(email)}"
    ok_ip = forgot_password_limiter.check(
        ip_bucket, limit=limit * 2, window_seconds=3600
    )
    ok_email = forgot_password_limiter.check(
        email_bucket, limit=limit, window_seconds=3600
    )
    if not ok_ip or not ok_email:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, detail=_RATE_LIMITED_DETAIL
        )


def _enforce_reset_preview_rate_limit(request: Request) -> None:
    """Modest per-IP cap on /auth/reset-password/preview.

    The preview is a token-validity oracle (valid vs invalid/expired/used
    tokens are deliberately indistinguishable in copy, but a 200-vs-400
    response still leaks validity). Without a rate limit an attacker can
    brute-probe reset tokens from one source. Reuse the forgot-password
    limiter, keyed by IP only (the token is in the query, not the bucket).
    """
    limit = settings.AUTH_FORGOT_PASSWORD_RATE_LIMIT_PER_HOUR
    if limit <= 0:
        return
    ip = _client_ip(request)
    ip_bucket = f"reset-preview:ip:{hash_identifier(ip)}"
    # Allow a generous multiple of the forgot-password cap: a legit user
    # may reload the reset page a few times, but this still bounds sweeps.
    if not forgot_password_limiter.check(
        ip_bucket, limit=limit * 6, window_seconds=3600
    ):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, detail=_RATE_LIMITED_DETAIL
        )


_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _enforce_cookie_csrf(request: Request) -> None:
    """Origin/Referer allowlist check for cookie-authenticated mutating
    requests (FE-SEC-1). Mirrors ``portal.enforce_portal_csrf``.

    Only reached when a request authenticated via the session COOKIE (no
    bearer header) on an unsafe method. The cookie is issued
    ``SameSite=None; Secure`` in prod (cross-site Vercel↔Render), so the
    browser would otherwise attach it to cross-site form POSTs; this
    rejects any whose Origin/Referer is not in the allowlist. Bearer
    (header) auth never reaches here, so the existing flow is unaffected.
    Fail-closed in non-local; lenient in local for curl/test ergonomics.
    """
    allowed = settings.allowed_csrf_origins
    origin = request.headers.get("origin")
    if origin:
        if origin.rstrip("/") in allowed:
            return
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="Origin no permitido para esta sesión."
        )
    referer = request.headers.get("referer")
    if referer:
        from urllib.parse import urlparse

        parsed = urlparse(referer)
        if parsed.scheme and parsed.netloc:
            referer_origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
            if referer_origin in allowed:
                return
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="Referer no permitido para esta sesión."
        )
    if settings.is_local_env:
        return
    raise HTTPException(
        status.HTTP_403_FORBIDDEN,
        detail="Falta cabecera Origin/Referer para esta sesión.",
    )


def get_current_user(
    request: Request,
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    # Bearer header takes precedence (existing flow, byte-for-byte
    # unchanged). When absent, fall back to the httpOnly session cookie
    # (FE-SEC-1) — and CSRF-guard it on mutating methods, since the cookie
    # is ambient/cross-site. The cookie is INERT in prod until the
    # frontend opts in with credentials:'include'; the header path here is
    # untouched, so this fallback cannot regress current sessions.
    if authorization:
        claims = _claims_from_header(authorization)
    else:
        cookie_token = request.cookies.get(settings.AUTH_SESSION_COOKIE_NAME)
        if not cookie_token:
            # Preserve the existing "missing credentials" 401 contract.
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                detail="Falta el encabezado de autorización.",
            )
        if request.method.upper() not in _SAFE_METHODS:
            _enforce_cookie_csrf(request)
        try:
            claims = decode_access_token(cookie_token)
        except TokenError as exc:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                detail="Token de autenticación inválido o expirado.",
            ) from exc
    user = db.get(User, claims.user_id)
    if user is None or user.status != "active":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Tu sesión ya no está activa.")

    # CW-AUTHZ-001 / CW-AUTH-001 / CW-AUTH-002 — session-epoch revocation.
    # Reject any token minted before the user's current epoch (a password
    # reset / set-password, a staff role revocation, or a client demotion
    # all bump it). ``<`` (strictly older), never ``!=``, so a future-dated
    # epoch from a clock/replication race can never brick a valid token. No
    # extra query — ``user`` is already loaded above.
    if claims.session_epoch < (user.session_epoch or 0):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail="Tu sesión ya no está activa."
        )

    # P0 gate: a user flagged ``must_change_password=True`` may only
    # touch the narrow surface needed to clear the flag. Without this,
    # a freshly-activated provider whose token was issued before they
    # set a personal password can read or mutate any route their role
    # permits. The allow-list is enforced here (one place) rather than
    # threaded through every router so a missed Depends cannot
    # accidentally open a hole.
    if user.must_change_password and request.url.path not in _PASSWORD_GATE_ALLOWED_PATHS:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=_PASSWORD_RESET_REQUIRED_DETAIL,
        )

    return CurrentUser(
        user=UserOut(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            status=user.status,
            must_change_password=user.must_change_password,
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
                status.HTTP_403_FORBIDDEN,
                detail=f"Necesitas el rol '{role}' para esta acción.",
            )
        return current

    return _dep


def require_any_role(*roles: str) -> Callable[..., CurrentUser]:
    """Dependency factory: 403 unless the user carries **any** of ``roles``.

    Used when an endpoint should accept several roles (e.g. the
    reviewer queue is fine with either ``reviewer`` or ``internal_admin``
    — both should be able to read it).
    """

    accepted = tuple(roles)

    def _dep(
        current: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> CurrentUser:
        if not any(role in current.roles for role in accepted):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=(
                    "Necesitas alguno de estos roles para esta acción: "
                    f"{list(accepted)}."
                ),
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
                status.HTTP_403_FORBIDDEN,
                detail="No perteneces a esta organización.",
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
                detail=f"Necesitas el rol '{role}' en esta organización.",
            )
        return current

    return _dep


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def _audit_provenance(request: Request) -> tuple[str, str | None]:
    """(ip, user_agent) for an audit row. UA truncated to the column width."""
    ua = request.headers.get("user-agent")
    return _client_ip(request), (ua[:512] if ua else None)


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest, request: Request, response: Response, db: DbSession
) -> LoginResponse:
    # Throttle before doing any DB work so a brute-force flood can't
    # ramp bcrypt CPU into the ground.
    _enforce_login_rate_limit(request, payload.email)
    user = db.execute(
        select(User).where(User.email == payload.email)
    ).scalar_one_or_none()

    # Account lockout — refuse a locked, active account before the
    # password check (so even the correct password is rejected during the
    # cooldown). The DB lockout bookkeeping (locked_until / failed_login_count)
    # is untouched; we just return the SAME generic 401 as the unknown-user
    # / bad-password path instead of a distinct 429 lockout message. A
    # 401-vs-429 split was an account-enumeration oracle: only existing
    # active accounts could be locked, so the 429 confirmed the email
    # exists. Run the dummy bcrypt first to keep timing comparable.
    if user is not None and user.status == "active" and _is_account_locked(user):
        verify_password(payload.password, _DUMMY_HASH)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas."
        )

    # Generic 401 for both unknown-user and bad-password so the response
    # does not leak whether an email exists. Bcrypt's constant-time check
    # still runs to keep timing roughly comparable.
    if user is None or user.status != "active":
        verify_password(payload.password, _DUMMY_HASH)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas.")
    if not verify_password(payload.password, user.password_hash):
        # INFRA-3 — record the failed attempt against the (known, active)
        # account so the audit log carries an authentication trail. Commit
        # it explicitly: _register_failed_login is a no-op (no commit) when
        # lockout is disabled, so without this the row would roll back.
        ip, ua = _audit_provenance(request)
        add_audit_event(
            db,
            action="auth.login.failed",
            entity_type="user",
            entity_id=user.id,
            actor_type="anonymous",
            after={"email": user.email, "reason": "bad_password"},
            ip_address=ip,
            user_agent=ua,
        )
        db.commit()
        # Count the failure; this may trip the lockout threshold and set
        # ``locked_until`` in the DB. We deliberately do NOT surface the
        # lock with a distinct 429 message — that would re-open the
        # 401-vs-429 enumeration oracle (only an existing active account
        # can be locked). The lockout bookkeeping still happens here and is
        # enforced pre-password on the next attempt; the response stays the
        # same generic 401 the unknown-user / bad-password path returns.
        _register_failed_login(db, user)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas.")

    # Successful auth — clear any accumulated failure / lock state.
    if user.failed_login_count or user.locked_until is not None:
        user.failed_login_count = 0
        user.locked_until = None

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
        user_id=user.id,
        email=user.email,
        roles=roles,
        orgs=org_ids,
        session_epoch=user.session_epoch or 0,
    )
    # FE-SEC-1 — also deposit the JWT in an httpOnly cookie so the
    # frontend can move off localStorage (XSS-exfiltratable). The token is
    # still returned in the body, so the current header-based flow keeps
    # working; the browser only stores this cross-site cookie once the
    # login fetch opts into credentials:'include', so it stays inert in
    # prod until that frontend cutover lands.
    response.set_cookie(
        key=settings.AUTH_SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.AUTH_JWT_EXPIRES_MINUTES * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )
    user.last_login_at = utc_now()
    # INFRA-3 — authentication trail: who logged in, from where, when.
    ip, ua = _audit_provenance(request)
    add_audit_event(
        db,
        action="auth.login.succeeded",
        entity_type="user",
        entity_id=user.id,
        actor_type="user",
        actor_id=user.id,
        after={"email": user.email},
        ip_address=ip,
        user_agent=ua,
    )
    # Audit-finding #1 — ``db.flush()`` pushes pending changes to the
    # connection but does NOT persist them. ``get_db`` closes the
    # session without an implicit commit, so without this explicit
    # commit ``last_login_at`` would roll back and the column would
    # forever stay NULL despite this code clearly intending to set it.
    db.commit()

    claims = decode_access_token(token)
    return LoginResponse(
        access_token=token,
        expires_at=datetime.fromtimestamp(claims.expires_at, tz=UTC),
        user=UserOut(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            status=user.status,
            must_change_password=user.must_change_password,
            last_login_at=user.last_login_at,
        ),
        roles=roles,
        organization_ids=org_ids,
        must_change_password=user.must_change_password,
    )


@router.post(
    "/forgot-password",
    response_model=ForgotPasswordResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    background: BackgroundTasks,
    db: DbSession,
) -> ForgotPasswordResponse:
    """Create a one-time reset link and email it when the account exists.

    The response is intentionally generic for both known and unknown
    emails so the endpoint cannot be used to enumerate users.
    """
    # Cap reset-link generation per IP + per email to make mass
    # enumeration and inbox-bombing impractical without blocking
    # legitimate single-account recovery.
    _enforce_forgot_password_rate_limit(request, payload.email)
    generic = ForgotPasswordResponse(
        message=(
            "Si el correo existe en CheckWise, enviaremos instrucciones "
            "para restablecer la contraseña."
        )
    )

    user = db.execute(
        select(User).where(User.email == payload.email, User.status == "active")
    ).scalar_one_or_none()
    if user is None:
        log.warning(
            "password_reset_request_no_active_user email_hash=%s",
            _email_log_hash(payload.email),
        )
        return generic

    now = utc_now()
    existing_tokens = (
        db.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used_at.is_(None),
            )
        )
        .scalars()
        .all()
    )
    for token in existing_tokens:
        token.used_at = now

    raw_token = generate_password_reset_token()
    reset_token = PasswordResetToken(
        user_id=user.id,
        email=user.email,
        token_hash=hash_password_reset_token(raw_token),
        expires_at=now + timedelta(minutes=settings.PASSWORD_RESET_EXPIRES_MINUTES),
        delivery_status="pending",
    )
    db.add(reset_token)
    db.flush()

    reset_url = (
        f"{settings.FRONTEND_BASE_URL.rstrip('/')}/reset-password"
        f"?token={quote(raw_token, safe='')}"
    )
    delivery = send_password_reset_email(to_email=user.email, reset_url=reset_url)
    reset_token.delivery_status = delivery.status
    reset_token.delivery_error = delivery.error
    log_method = log.info if delivery.status == "sent" else log.warning
    log_method(
        "password_reset_delivery status=%s email_hash=%s reset_token_id=%s error=%s",
        delivery.status,
        _email_log_hash(user.email),
        reset_token.id,
        delivery.error,
    )
    add_audit_event(
        db,
        action="auth.password_reset_requested",
        entity_type="user",
        entity_id=user.id,
        actor_type="system",
        after={
            "email": user.email,
            "reset_token_id": reset_token.id,
            "expires_at": reset_token.expires_at.isoformat(),
            "delivery_status": delivery.status,
        },
    )
    db.commit()

    # Phase 7 cutover (Slice C) — also dispatch through the unified fabric in
    # parallel with the legacy email send above (the user-visible delivery).
    # CW-DOS-002 — the fabric emit performs blocking SMTP/SMS in active mode,
    # so it runs AFTER the response as a BackgroundTask on its own session
    # (the reset-token row is committed above; the task re-loads the user by
    # id). A failure there never affects this request.
    background.add_task(
        emit_password_reset_in_background,
        user_id=user.id,
        reset_token_id=reset_token.id,
        reset_url=reset_url,
    )

    return generic


@router.get(
    "/reset-password/preview",
    response_model=ResetPasswordPreviewResponse,
)
def reset_password_preview(
    token: str,
    db: DbSession,
    request: Request,
) -> ResetPasswordPreviewResponse:
    """Audit-finding #5 — return the recipient email tied to a reset
    token so ``/reset-password`` can show which account the form is
    about to update.

    Same validity rules as the POST handler: invalid / used / expired
    tokens are all 400. The endpoint deliberately uses the same
    Spanish error copy as ``reset_password`` to avoid an oracle that
    distinguishes "token never existed" from "token already used"
    from "token expired" — for an attacker probing tokens, all three
    look identical.
    """
    _enforce_reset_preview_rate_limit(request)
    token_hash = hash_password_reset_token(token)
    reset_token = db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    ).scalar_one_or_none()

    if reset_token is None or reset_token.used_at is not None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="El enlace para restablecer la contraseña no es válido.",
        )
    if _as_utc(reset_token.expires_at) <= utc_now():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="El enlace para restablecer la contraseña ya venció.",
        )

    user = db.get(User, reset_token.user_id)
    if user is None or user.status != "active":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="El enlace para restablecer la contraseña no es válido.",
        )

    return ResetPasswordPreviewResponse(email=user.email)


@router.post("/reset-password", response_model=ResetPasswordResponse)
def reset_password(
    payload: ResetPasswordRequest,
    db: DbSession,
) -> ResetPasswordResponse:
    token_hash = hash_password_reset_token(payload.token)
    reset_token = db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    ).scalar_one_or_none()

    if reset_token is None or reset_token.used_at is not None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="El enlace para restablecer la contraseña no es válido.",
        )
    if _as_utc(reset_token.expires_at) <= utc_now():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="El enlace para restablecer la contraseña ya venció.",
        )

    user = db.get(User, reset_token.user_id)
    if user is None or user.status != "active":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="El enlace para restablecer la contraseña no es válido.",
        )

    now = utc_now()
    # Audit-finding #10 — reject reuse against the user's last
    # PASSWORD_HISTORY_DEPTH hashes (and the current one) BEFORE
    # consuming the reset token. The token has already been validated
    # as unused + unexpired; if the password is a reuse we 422 and
    # leave the token alive so the user can try again from the same
    # link rather than having to request a fresh one.
    _apply_password_change(db, user, payload.new_password)
    reset_token.used_at = now

    sibling_tokens = (
        db.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.id != reset_token.id,
            )
        )
        .scalars()
        .all()
    )
    for sibling in sibling_tokens:
        sibling.used_at = now

    add_audit_event(
        db,
        action="auth.password_reset_completed",
        entity_type="user",
        entity_id=user.id,
        actor_type="user",
        actor_id=user.id,
        after={"email": user.email, "reset_token_id": reset_token.id},
    )
    db.commit()
    return ResetPasswordResponse(message="Contraseña restablecida correctamente.")


@router.get("/me", response_model=CurrentUser)
def me(current: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
    return current


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    """Clear the httpOnly session cookie (FE-SEC-1) and audit the logout.

    Stateless JWTs can't be server-revoked, so logout is a cookie clear:
    the frontend also drops any in-memory token. Safe to call
    unauthenticated (idempotent). The cookie attributes must match the
    ones ``login`` set or the browser won't remove it.

    G-7 — best-effort resolve the principal from the bearer header or the
    session cookie and write an ``auth.logout`` row so session-end has a
    forensic trail (mirrors the login-success/failure audit). Resolution
    and auditing are wrapped so logout can never fail or leak — an
    anonymous/expired-token logout still returns 204.
    """
    token = ""
    if authorization:
        try:
            token = _bearer_token(authorization)
        except HTTPException:
            token = ""
    if not token:
        token = request.cookies.get(settings.AUTH_SESSION_COOKIE_NAME) or ""

    if token:
        try:
            claims = decode_access_token(token)
        except TokenError:
            claims = None
        if claims is not None:
            try:
                ip, ua = _audit_provenance(request)
                add_audit_event(
                    db,
                    action="auth.logout",
                    entity_type="user",
                    entity_id=claims.user_id,
                    actor_type="user",
                    actor_id=claims.user_id,
                    after={"email": claims.email},
                    ip_address=ip,
                    user_agent=ua,
                )
                db.commit()
            except Exception:  # noqa: BLE001 — logout must never fail
                db.rollback()

    resp = Response(status_code=status.HTTP_204_NO_CONTENT)
    resp.delete_cookie(
        key=settings.AUTH_SESSION_COOKIE_NAME,
        path="/",
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )
    return resp


@router.post("/set-password", response_model=SetPasswordResponse)
def set_password(
    payload: SetPasswordRequest,
    current: Annotated[CurrentUser, Depends(get_current_user)],
    response: Response,
    db: DbSession,
) -> SetPasswordResponse:
    """Update the authenticated user's password and clear the
    must-change-password flag.

    Used by:
    - The first-login flow at ``/activate`` after a user signs in with
      seed/temporary credentials. Backend issues a JWT, frontend posts
      the new password here, then redirects to the workspace entry.
    - Future "change my password" UI for any signed-in user.

    CW-AUTH-002 — the password change bumps the user's ``session_epoch``,
    which invalidates EVERY outstanding token (including the one this
    request authenticated with). To avoid bouncing the active caller
    mid-flow, we re-mint a fresh token carrying the new epoch, deposit it
    as the httpOnly session cookie, and return it in the body. All OTHER
    sessions (other devices / stale tokens) are now dead, which is the
    desired behavior.
    """
    user = db.get(User, current.user.id)
    if user is None or user.status != "active":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Tu sesión ya no está activa.")

    # Audit-finding #10 — same reuse guard as /reset-password. This also
    # bumps user.session_epoch (CW-AUTH-002) via ``_apply_password_change``.
    _apply_password_change(db, user, payload.new_password)
    # Hardening pass (2026-05-26) — write the same canonical audit
    # row the /reset-password endpoint writes. set-password is the
    # /activate forced-first-login surface; without this row the
    # forensic trail was missing the most material action on the
    # account (initial password set + must-change-password clear).
    add_audit_event(
        db,
        action="auth.password_changed",
        entity_type="user",
        entity_id=user.id,
        actor_type="user",
        actor_id=user.id,
        after={"email": user.email, "source": "set_password"},
    )
    db.commit()

    # Re-mint the current session's token at the NEW epoch. Roles/orgs are
    # unchanged by a password set, so reuse the just-validated claims rather
    # than re-querying memberships.
    fresh_token = issue_access_token(
        user_id=user.id,
        email=user.email,
        roles=list(current.roles),
        orgs=list(current.organization_ids),
        session_epoch=user.session_epoch or 0,
    )
    response.set_cookie(
        key=settings.AUTH_SESSION_COOKIE_NAME,
        value=fresh_token,
        max_age=settings.AUTH_JWT_EXPIRES_MINUTES * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )
    fresh_claims = decode_access_token(fresh_token)

    return SetPasswordResponse(
        user=UserOut(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            status=user.status,
            must_change_password=user.must_change_password,
            last_login_at=user.last_login_at,
        ),
        must_change_password=user.must_change_password,
        access_token=fresh_token,
        expires_at=datetime.fromtimestamp(fresh_claims.expires_at, tz=UTC),
    )
