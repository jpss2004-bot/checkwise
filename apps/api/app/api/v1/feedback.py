"""Internal feedback endpoints — bug reports and improvement suggestions.

Two surfaces:

* ``POST /api/v1/feedback`` — authenticated. Used by signed-in
  CheckWise testers via the floating "Report" button on the post-login
  layouts. Identifies the submitter by JWT and includes their roles in
  the Slack message.

* ``POST /api/v1/feedback/public`` — anonymous. Used by the same
  launcher when mounted on the public landing page. No JWT required;
  the submitter is identified only by a peppered IP-hash fingerprint
  and an *optional* reply-back email field they can fill in.

Both endpoints post a structured Block Kit message to the configured
Slack channel with the description, the page the submitter was on,
and (optionally) a PNG screenshot attached as a thread reply.

Defense in depth (both surfaces):
- PNG magic-byte check on the screenshot (browser Content-Type is
  trivially spoofed).
- ``MAX_SCREENSHOT_BYTES`` cap, returned as 413 if exceeded.
- In-memory rate limit. Authenticated: 10 reports per user per
  minute. Public: 5 reports per IP-hash per hour — tighter because
  the landing page is publicly indexable.
- Slack delivery runs in a ``BackgroundTask`` so the user's response
  is not gated on Slack latency or downtime.

If ``SLACK_BOT_TOKEN`` / ``SLACK_FEEDBACK_CHANNEL_ID`` are unset
(the local-dev default), the endpoint still validates and returns 202
with ``delivered: false`` — useful for wiring the frontend up first.
"""

from __future__ import annotations

import logging
from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.v1.auth import CurrentUser, get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.services.feedback_service import (
    PNG_MAGIC,
    create_feedback_report,
    deliver_to_slack,
    feedback_snapshot,
    hash_ip,
    public_feedback_snapshot,
    record_and_check_public_rate,
    record_and_check_rate,
    save_screenshot_to_storage,
)

router = APIRouter(prefix="/feedback", tags=["feedback"])

logger = logging.getLogger(__name__)


MAX_SCREENSHOT_BYTES = 5 * 1024 * 1024  # 5 MB
MIN_DESCRIPTION_CHARS = 10
MAX_DESCRIPTION_CHARS = 4000
MAX_CONSOLE_LOGS_CHARS = 16 * 1024  # 16 KB


class FeedbackResponse(BaseModel):
    ok: bool
    delivered: bool
    """``True`` when a Slack BackgroundTask was scheduled (token + channel
    configured), ``False`` when stub-mode skipped delivery. Persistence
    happens unconditionally; check ``report_id`` for the row."""
    report_id: str
    """ID of the persisted ``FeedbackReport`` row. Always present."""


@router.post(
    "",
    response_model=FeedbackResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit an internal bug report or improvement suggestion",
)
async def post_feedback(
    background: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
    current: Annotated[CurrentUser, Depends(get_current_user)],
    kind: Annotated[Literal["bug", "improvement"], Form(alias="type")],
    description: Annotated[
        str,
        Form(min_length=MIN_DESCRIPTION_CHARS, max_length=MAX_DESCRIPTION_CHARS),
    ],
    url: Annotated[str, Form(max_length=2048)],
    path: Annotated[str, Form(max_length=512)],
    viewport: Annotated[str, Form(max_length=32)] = "",
    user_agent: Annotated[str, Form(max_length=512)] = "",
    console_logs: Annotated[str, Form(max_length=MAX_CONSOLE_LOGS_CHARS)] = "",
    screenshot: Annotated[UploadFile | None, File()] = None,
) -> FeedbackResponse:
    description_clean = description.strip()
    if len(description_clean) < MIN_DESCRIPTION_CHARS:
        # Literal 422 to avoid the HTTP_422_UNPROCESSABLE_ENTITY → _CONTENT
        # rename deprecation in newer Starlette.
        raise HTTPException(
            status_code=422,
            detail=(
                f"La descripción debe tener al menos {MIN_DESCRIPTION_CHARS} "
                "caracteres (excluyendo espacios)."
            ),
        )

    if not record_and_check_rate(current.user.id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Demasiados reportes de este usuario. "
                "Espera un minuto e inténtalo de nuevo."
            ),
        )

    screenshot_bytes: bytes | None = None
    if screenshot is not None:
        screenshot_bytes = await _read_and_validate_screenshot(screenshot)

    snapshot = feedback_snapshot(
        kind=kind,
        description=description_clean,
        url=url,
        path=path,
        viewport=viewport,
        user_agent=user_agent,
        console_logs=console_logs,
        user_id=current.user.id,
        user_email=current.user.email,
        user_full_name=current.user.full_name,
        user_roles=list(current.roles),
    )

    # Persist FIRST. The HTTP response means "row exists, Slack
    # delivery scheduled (or stubbed)" — never "Slack delivered".
    row = create_feedback_report(
        db,
        snapshot=snapshot,
        storage_key=None,  # filled in below once we have a row id
        screenshot_size_bytes=len(screenshot_bytes) if screenshot_bytes else None,
    )
    if screenshot_bytes is not None:
        try:
            key = save_screenshot_to_storage(row.id, screenshot_bytes)
            row.screenshot_storage_key = key
            db.commit()
        except Exception as exc:  # noqa: BLE001 — defensive
            # Storage backend is misconfigured / unreachable. Row stays
            # without a key; Slack still gets the screenshot inline.
            logger.warning(
                "feedback: screenshot storage failed report_id=%s err=%s",
                row.id,
                exc,
            )

    configured = bool(
        (settings.SLACK_BOT_TOKEN or "").strip()
        and (settings.SLACK_FEEDBACK_CHANNEL_ID or "").strip()
    )
    if configured:
        background.add_task(deliver_to_slack, snapshot, screenshot_bytes, row.id)
    else:
        logger.info(
            "feedback: slack not configured; skipping delivery user=%s path=%s",
            current.user.email,
            path,
        )
        # Mark the row's delivery status as skipped so the triage UI
        # doesn't show it stuck on 'pending' forever.
        row.slack_delivery_status = "skipped"
        db.commit()

    return FeedbackResponse(ok=True, delivered=configured, report_id=row.id)


async def _read_and_validate_screenshot(file: UploadFile) -> bytes:
    # Read one byte past the cap so we can detect overflow without
    # streaming the whole oversized payload into memory.
    raw = await file.read(MAX_SCREENSHOT_BYTES + 1)
    if len(raw) > MAX_SCREENSHOT_BYTES:
        # 413 lives under two names in Starlette — the old REQUEST_ENTITY_TOO_LARGE
        # is deprecated in favor of CONTENT_TOO_LARGE. Use the literal so we
        # don't pick up the deprecation warning either way.
        raise HTTPException(
            status_code=413,
            detail=(
                f"La captura no puede pesar más de "
                f"{MAX_SCREENSHOT_BYTES // (1024 * 1024)} MB."
            ),
        )
    if not raw.startswith(PNG_MAGIC):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="La captura debe ser una imagen PNG válida.",
        )
    return raw


# ─── Public (unauthenticated) endpoint ──────────────────────────


MAX_CONTACT_EMAIL_CHARS = 256


def _client_ip(request: Request) -> str | None:
    """Resolve the client IP, preferring proxy headers where present.

    Render places its load balancer in front of the uvicorn process,
    so ``request.client.host`` is the LB. Mirrors the same helper in
    ``contact.py``.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    if request.client and request.client.host:
        return request.client.host
    return None


@router.post(
    "/public",
    response_model=FeedbackResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a bug report or improvement suggestion from the public landing",
)
async def post_public_feedback(
    request: Request,
    background: BackgroundTasks,
    db: Annotated[Session, Depends(get_db)],
    kind: Annotated[Literal["bug", "improvement"], Form(alias="type")],
    description: Annotated[
        str,
        Form(min_length=MIN_DESCRIPTION_CHARS, max_length=MAX_DESCRIPTION_CHARS),
    ],
    url: Annotated[str, Form(max_length=2048)],
    path: Annotated[str, Form(max_length=512)],
    viewport: Annotated[str, Form(max_length=32)] = "",
    user_agent: Annotated[str, Form(max_length=512)] = "",
    console_logs: Annotated[str, Form(max_length=MAX_CONSOLE_LOGS_CHARS)] = "",
    contact_email: Annotated[str, Form(max_length=MAX_CONTACT_EMAIL_CHARS)] = "",
    screenshot: Annotated[UploadFile | None, File()] = None,
) -> FeedbackResponse:
    description_clean = description.strip()
    if len(description_clean) < MIN_DESCRIPTION_CHARS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"La descripción debe tener al menos {MIN_DESCRIPTION_CHARS} "
                "caracteres (excluyendo espacios)."
            ),
        )

    # The browser-supplied user_agent field is best-effort; fall back to
    # the request header when missing so the Slack message always has
    # something useful.
    ua = user_agent or (request.headers.get("user-agent") or "")[:512]

    ip = _client_ip(request)
    ip_h = hash_ip(ip)

    if not record_and_check_public_rate(ip_h):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Demasiados reportes desde esta dirección. "
                "Inténtalo de nuevo en una hora."
            ),
        )

    screenshot_bytes: bytes | None = None
    if screenshot is not None:
        screenshot_bytes = await _read_and_validate_screenshot(screenshot)

    email_clean = contact_email.strip() or None

    snapshot = public_feedback_snapshot(
        kind=kind,
        description=description_clean,
        url=url,
        path=path,
        viewport=viewport,
        user_agent=ua,
        console_logs=console_logs,
        contact_email=email_clean,
        ip_hash=ip_h,
    )

    row = create_feedback_report(
        db,
        snapshot=snapshot,
        storage_key=None,
        screenshot_size_bytes=len(screenshot_bytes) if screenshot_bytes else None,
    )
    if screenshot_bytes is not None:
        try:
            key = save_screenshot_to_storage(row.id, screenshot_bytes)
            row.screenshot_storage_key = key
            db.commit()
        except Exception as exc:  # noqa: BLE001 — defensive
            logger.warning(
                "feedback(public): screenshot storage failed report_id=%s err=%s",
                row.id,
                exc,
            )

    configured = bool(
        (settings.SLACK_BOT_TOKEN or "").strip()
        and (settings.SLACK_FEEDBACK_CHANNEL_ID or "").strip()
    )
    if configured:
        background.add_task(deliver_to_slack, snapshot, screenshot_bytes, row.id)
    else:
        logger.info(
            "feedback(public): slack not configured; skipping delivery ip_hash=%s path=%s",
            ip_h or "—",
            path,
        )
        row.slack_delivery_status = "skipped"
        db.commit()

    return FeedbackResponse(ok=True, delivered=configured, report_id=row.id)
