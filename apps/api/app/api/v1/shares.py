"""Phase 10D — public consume endpoints for shared reports.

Lives at ``/r/`` (under the v1 prefix → ``/api/v1/r/<token>``). NO
auth dependency — these endpoints are deliberately reachable
without a bearer token. The token itself is the authorization.

Three endpoints:

* ``GET  /r/{token}``          — render the report as HTML.
* ``POST /r/{token}/unlock``   — submit a password and receive a
                                 short-lived cookie that the GET
                                 trusts for subsequent reads.
* ``GET  /r/{token}/info``     — lightweight probe used by the
                                 Next.js wrapper / a future preview
                                 image: returns audience + title +
                                 has_password without rendering the
                                 full body. Same 404/410 contract
                                 as the GET above so an attacker
                                 can't probe via this endpoint
                                 either.

Cookie signing: HMAC-SHA256 over ``share_id|expires_at`` using the
existing ``AUTH_JWT_SECRET``. Short-lived (1 hour); same-site=lax;
HttpOnly. The cookie name scopes to the share id so a token swap
doesn't accidentally inherit a password unlock from another link.

All responses set ``Cache-Control: no-store`` so a shared link
behind a corporate proxy doesn't get cached and replayed by
another user on the same network.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rate_limit import enforce_share_unlock_rate_limit
from app.db.session import get_db
from app.models import Report, ReportVersion
from app.models.entities import utc_now
from app.services.reports.print_render import render_report_document_html
from app.services.reports.sharing import (
    ShareExpiredError,
    ShareNotFoundError,
    SharePasswordMismatchError,
    SharePasswordRequiredError,
    ShareRevokedError,
    consume_share,
)

logger = logging.getLogger(__name__)


# Public router. Prefix ``/r`` keeps the URLs short — the v1 mount
# prepends ``/api/v1``, so the final shape is ``/api/v1/r/<token>``.
router = APIRouter(prefix="/r", tags=["shares"])
DbSession = Annotated[Session, Depends(get_db)]


# Cookie config. Name is per-share so unlocking link A doesn't
# auto-unlock link B if they happen to share a password.
COOKIE_PREFIX = "cw_share_unlock_"
COOKIE_TTL_SECONDS = 60 * 60  # 1 hour — re-prompt on long sessions

NO_STORE = {"Cache-Control": "no-store"}


def _throttle_share_consume(request: Request, token: str) -> None:
    """Apply the M3 share-unlock brute-force cap.

    Same limiter for all three /r/{token}* paths so a probe campaign
    that mixes info + consume + unlock can't escape budget by
    bouncing between endpoints.
    """
    enforce_share_unlock_rate_limit(
        request,
        token,
        per_minute=settings.SHARE_UNLOCK_RATE_LIMIT_PER_MINUTE,
        per_hour=settings.SHARE_UNLOCK_RATE_LIMIT_PER_HOUR,
    )


# ---------------------------------------------------------------------------
# Unlock-cookie signing
# ---------------------------------------------------------------------------


def _sign_unlock(share_id: str, *, now: datetime | None = None) -> str:
    """Sign a per-share unlock token. ``share_id|expires_iso|sig``.

    HMAC-SHA256 over (share_id + "|" + expires_iso) using
    ``AUTH_JWT_SECRET`` as the key. Same secret the JWT layer uses
    so we don't introduce a second one to manage.
    """
    when = now or utc_now()
    expires = when + timedelta(seconds=COOKIE_TTL_SECONDS)
    payload = f"{share_id}|{expires.isoformat()}"
    sig = hmac.new(
        settings.AUTH_JWT_SECRET.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}|{sig}"


def _verify_unlock(share_id: str, raw: str | None) -> bool:
    """Verify an unlock cookie. Returns True iff sig matches AND
    expires_at hasn't passed.

    Constant-time comparison via ``hmac.compare_digest``. Bad
    formatting / missing parts return False without raising — a
    tampered cookie should look like "no cookie at all" to the
    caller.
    """
    if not raw:
        return False
    parts = raw.split("|")
    if len(parts) != 3:
        return False
    candidate_share_id, expires_iso, sig = parts
    if candidate_share_id != share_id:
        return False
    try:
        expires = datetime.fromisoformat(expires_iso)
    except ValueError:
        return False
    if expires <= utc_now():
        return False
    expected = hmac.new(
        settings.AUTH_JWT_SECRET.encode("utf-8"),
        f"{candidate_share_id}|{expires_iso}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, sig)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class UnlockPayload(BaseModel):
    password: str = Field(..., min_length=1)


class UnlockResponse(BaseModel):
    ok: bool = True


class ShareInfo(BaseModel):
    """Probe response — no rendered body, just enough metadata so the
    consumer can decide whether to prompt for a password."""

    audience: str
    has_password: bool
    expires_at: datetime | None
    title: str | None


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


def _raise_for_share_error(exc: Exception) -> None:
    """Translate sharing.* exceptions into the HTTP shape the public
    router commits to.

    * NotFound + Revoked + Expired → distinct status codes (404/410/410)
      so the recipient knows which recovery path to take (ask the
      sender for a new link vs. the sender revoked it intentionally
      vs. it lapsed). The body never reveals which one — the only
      signal is the status code.
    * Password errors → 401 with a clear body so the frontend can
      render the password form.
    """
    if isinstance(exc, ShareNotFoundError):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Enlace no disponible."
        )
    if isinstance(exc, ShareRevokedError):
        raise HTTPException(
            status.HTTP_410_GONE, detail="Enlace no disponible."
        )
    if isinstance(exc, ShareExpiredError):
        raise HTTPException(
            status.HTTP_410_GONE, detail="Enlace no disponible."
        )
    if isinstance(exc, SharePasswordRequiredError):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="password_required",
        )
    if isinstance(exc, SharePasswordMismatchError):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="password_invalid",
        )
    raise exc  # pragma: no cover — unmapped error type


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def _cookie_name_for(token: str) -> str:
    """Per-token cookie name — short hash so we don't echo the raw
    token in the cookie name (browsers log cookie names in dev tools).
    """
    return COOKIE_PREFIX + hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]


def _try_consume_with_unlock_cookie(
    db: Session,
    *,
    token: str,
    presented_password: str | None,
    unlock_cookie: str | None,
):
    """Attempt to consume the share.

    First pass: try with the presented password (or None). If the
    share requires a password and there's a valid unlock cookie for
    THIS token, we skip the password check by calling consume with
    a marker that disables it — simpler: peek at the row first to
    know whether the cookie is valid, then call consume with the
    matching password.

    We do it in two steps because consume_share is the only place
    that knows the password-hash semantics; we don't want to
    duplicate that.
    """
    from sqlalchemy import select

    from app.models import ReportShare
    from app.services.reports.sharing import _hash_token  # type: ignore[attr-defined]

    # Peek to find the share id (so we can verify the cookie tied
    # to it). Same lookup consume_share does — slight redundancy is
    # fine; the hot path is short.
    peek = db.scalar(
        select(ReportShare).where(ReportShare.token_hash == _hash_token(token))
    )
    if peek is None:
        # Unknown token — let consume raise the standard error.
        return consume_share(db, token=token, password=presented_password)

    if peek.password_hash and _verify_unlock(peek.id, unlock_cookie):
        # Valid unlock cookie present — bypass the password check
        # by calling consume with no password requirement. We do
        # this by temporarily blanking the row's hash for the
        # consume call... actually cleaner: re-implement the
        # consume logic inline for this branch. Tiny duplication
        # for clarity.
        return _consume_bypassing_password(db, share=peek)

    return consume_share(db, token=token, password=presented_password)


def _consume_bypassing_password(db: Session, *, share):
    """Inline equivalent of consume_share for the "unlock-cookie
    valid" branch. Same revoke / expired checks, same access-counter
    bump.
    """
    if share.revoked_at is not None:
        raise ShareRevokedError("Share has been revoked.")
    expires = share.expires_at
    if expires is not None and expires.tzinfo is None:
        from datetime import UTC as _UTC

        expires = expires.replace(tzinfo=_UTC)
    if expires is not None and expires <= utc_now():
        raise ShareExpiredError("Share has expired.")
    share.access_count = (share.access_count or 0) + 1
    share.last_accessed_at = utc_now()
    db.flush()
    return share


@router.get("/{token}/info", response_model=ShareInfo, summary="Share metadata probe")
def get_share_info(
    token: str, request: Request, db: DbSession
) -> ShareInfo:
    """Return audience + title + has_password without rendering the body.

    Same 404/410 contract as the GET render — so probing this
    endpoint doesn't reveal more state than rendering would.
    Password-protected shares return 200 with ``has_password=True``
    so the frontend knows to show the password form.
    """
    _throttle_share_consume(request, token)
    from sqlalchemy import select

    from app.models import ReportShare
    from app.services.reports.sharing import _hash_token  # type: ignore[attr-defined]

    row = db.scalar(
        select(ReportShare).where(ReportShare.token_hash == _hash_token(token))
    )
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Enlace no disponible."
        )
    # Same tz-naive coercion the sharing service uses — see
    # ``consume_share`` for the SQLite/Postgres parity rationale.
    expires = row.expires_at
    if expires is not None and expires.tzinfo is None:
        from datetime import UTC as _UTC

        expires = expires.replace(tzinfo=_UTC)
    if row.revoked_at is not None or (expires is not None and expires <= utc_now()):
        raise HTTPException(
            status.HTTP_410_GONE, detail="Enlace no disponible."
        )
    report = db.get(Report, row.report_id)
    # Don't leak the real report title before the password is supplied.
    # A password-protected share withholds its title until the caller
    # presents a valid unlock cookie for THIS token (the same cookie the
    # render path trusts). The probe still reports has_password +
    # expires_at so the frontend can render the password form.
    has_password = row.password_hash is not None
    unlocked = not has_password or _verify_unlock(
        row.id, request.cookies.get(_cookie_name_for(token))
    )
    return ShareInfo(
        audience=row.audience,
        has_password=has_password,
        expires_at=row.expires_at,
        title=(report.title if report else None) if unlocked else None,
    )


@router.post(
    "/{token}/unlock",
    response_model=UnlockResponse,
    summary="Submit a password and set a short-lived unlock cookie",
)
def post_share_unlock(
    token: str,
    payload: UnlockPayload,
    request: Request,
    response: Response,
    db: DbSession,
) -> UnlockResponse:
    """Verify the password; on success, set the unlock cookie.

    The cookie is HttpOnly + SameSite=Lax + Secure (in production —
    settings-driven). It's scoped to a per-share name so different
    shared links don't share unlock state.
    """
    _throttle_share_consume(request, token)
    try:
        share = consume_share(db, token=token, password=payload.password)
    except Exception as exc:
        # Roll back the consume side-effects on auth failure so a
        # brute-force attempt doesn't pump access_count.
        db.rollback()
        _raise_for_share_error(exc)
        raise  # unreachable; _raise_for_share_error always raises
    db.commit()
    cookie_value = _sign_unlock(share.id)
    response.set_cookie(
        key=_cookie_name_for(token),
        value=cookie_value,
        max_age=COOKIE_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        # ``cookie_secure`` is the real property (same one auth.py's login
        # cookie uses — True for non-local env). The previous
        # getattr(settings, "COOKIE_SECURE", False) referenced a name that
        # doesn't exist, so the unlock cookie was minted WITHOUT Secure
        # even in production.
        secure=settings.cookie_secure,
        path="/api/v1/r/",
    )
    for k, v in NO_STORE.items():
        response.headers[k] = v
    return UnlockResponse()


@router.get(
    "/{token}",
    summary="Render a shared report as HTML (public, token-gated)",
)
def get_share(token: str, request: Request, db: DbSession) -> Response:
    """Render the shared report version.

    Cookie lookup is per-token (the unlock cookie name embeds a
    digest of the token). FastAPI's ``Cookie`` dep requires a
    static alias, so we read the cookie out of ``request.cookies``
    directly using the per-token name we computed.
    """
    _throttle_share_consume(request, token)
    unlock_cookie = request.cookies.get(_cookie_name_for(token))
    try:
        share = _try_consume_with_unlock_cookie(
            db,
            token=token,
            presented_password=None,
            unlock_cookie=unlock_cookie,
        )
    except Exception as exc:
        db.rollback()
        _raise_for_share_error(exc)
        raise  # unreachable
    report = db.get(Report, share.report_id)
    version = db.get(ReportVersion, share.version_id)
    if report is None or version is None:
        db.rollback()
        raise HTTPException(
            status.HTTP_410_GONE, detail="Enlace no disponible."
        )
    # Serve the DESIGNED document (verdict → findings → bars → matrix),
    # the same self-contained HTML the PDF renders — not the generic
    # key/value structural dump. A shared link should show the real
    # report, not a debug view.
    #
    # Defense-in-depth: this endpoint is UNAUTHENTICATED, so pass the
    # share's audience. For vendor_facing / external_signed shares the
    # renderer strips named-provider identity from each block — even if
    # the stored version was somehow persisted with names.
    html_bytes = render_report_document_html(
        report, version, audience=share.audience
    )
    db.commit()
    return Response(
        content=html_bytes,
        media_type="text/html; charset=utf-8",
        headers=NO_STORE,
    )
