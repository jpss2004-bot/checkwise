"""Public contact-form endpoint (P0-3).

Replaces the V1.x mock helper at
``apps/web/lib/mock/contact-requests.ts``. Unauthenticated by design
— the landing page is public. The persistence layer is the canonical
audit trail; optional Slack delivery happens out-of-band via a
BackgroundTask so the response is never gated on Slack health.

Defense in depth:
- Pydantic validators cap every field length.
- Module-level in-memory rate limit caps 5 submissions per
  hashed-IP per hour. Hash uses ``AUTH_JWT_SECRET`` as pepper; only
  16 hex chars persisted.
- 429 is returned when the cap is hit. Clients can retry after
  the window expires.

Why not POST behind ``api/v1/auth/*``? Contact requests come from
anonymous prospects who have no account yet. Authenticated correction
flows have their own surface (workspace cookie + RBAC).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.contact import ContactRequestCreate, ContactRequestPublicResponse
from app.services.contact_service import (
    create_contact_request,
    deliver_to_slack,
    hash_ip,
    record_and_check_rate,
    slack_payload_snapshot,
)

router = APIRouter(prefix="/contact", tags=["contact"])


DbSession = Annotated[Session, Depends(get_db)]


def _client_ip(request: Request) -> str | None:
    """Resolve the client IP, preferring proxy headers where present.

    Render places its load balancer in front of the uvicorn process,
    so ``request.client.host`` is the LB. We look at ``x-forwarded-for``
    first (Render injects it), fall back to direct.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        # XFF is a comma-separated chain; the leftmost entry is the
        # original client.
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
    "",
    response_model=ContactRequestPublicResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a public contact request from the landing page",
)
def post_contact_request(
    payload: ContactRequestCreate,
    request: Request,
    background: BackgroundTasks,
    db: DbSession,
) -> ContactRequestPublicResponse:
    ip = _client_ip(request)
    ip_h = hash_ip(ip)
    user_agent_raw = request.headers.get("user-agent")
    user_agent = (user_agent_raw or "")[:512] or None

    if not record_and_check_rate(ip_h):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Demasiadas solicitudes desde esta dirección. "
                "Inténtalo de nuevo en una hora."
            ),
        )

    row = create_contact_request(
        db,
        name=payload.name,
        email=str(payload.email),
        company=payload.company,
        role=payload.role,
        message=payload.message,
        source=payload.source,
        ip_hash=ip_h,
        user_agent=user_agent,
    )

    snapshot = slack_payload_snapshot(
        name=payload.name,
        email=str(payload.email),
        company=payload.company,
        role=payload.role,
        message=payload.message,
        source=payload.source,
    )
    background.add_task(deliver_to_slack, row.id, snapshot)

    return ContactRequestPublicResponse(
        ok=True,
        request_id=row.id,
        created_at=row.created_at,
    )
