"""Service layer for provider workspace correction requests (Stage 2.7-a).

A provider can ask CheckWise support to correct a Tier B field
(``contact_email`` / ``contact_phone`` / ``contact_name``) on their
workspace via the ``CorrectionRequestForm`` mounted on the workspace
context bar. RFC, razón social, contract reference and any other
tenant-locked field stay support-only — those requests must be routed
through email/Slack, not through this endpoint. The Tier B restriction
is the locked decision from §18 of the experience plan.

Responsibilities:

1. In-memory rate limit keyed by the authenticated user_id. 5 requests
   per hour per user — generous because the form is gated behind the
   provider portal session, but tight enough to prevent abuse if a
   token leaks. Resets on process restart.
2. Persist the request as an ``AuditLog`` row with action
   ``correction_request.submitted`` and ``actor_type=provider``. The
   row carries the workspace_id, the field, the proposed value, the
   provider's reason, and the IP/UA fingerprint so admin triage has
   the full context.
3. Best-effort Slack delivery to ``SLACK_CORRECTION_WEBHOOK_URL`` as a
   FastAPI ``BackgroundTask``. Mirrors the contact-service pattern
   exactly: stdlib ``urllib`` (no SDK), Block Kit payload, never raise.
   Failures log at WARNING and are dropped so the user response is
   never gated on Slack health.

The Tier B field list is the single source of truth. Any field outside
it returns HTTP 422 from the router; the service does not silently
re-route the request.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from collections import deque
from threading import Lock
from typing import Final

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import AuditLog, new_id, utc_now

logger = logging.getLogger(__name__)


# ─── Tier B contract ───────────────────────────────────────────

# Locked decision from PROVIDER_EXPERIENCE_IMPROVEMENT_PLAN.md §18.
# The provider can self-submit a correction request only for these
# fields. Anything else returns 422 from the router with a "contact
# support" message.
TIER_B_FIELDS: Final[frozenset[str]] = frozenset(
    {"contact_email", "contact_phone", "contact_name"}
)

TIER_B_FIELD_LABEL_ES: Final[dict[str, str]] = {
    "contact_email": "Correo de contacto",
    "contact_phone": "Teléfono de contacto",
    "contact_name": "Nombre de la persona de contacto",
}


# ─── Rate limit (in-memory sliding window) ─────────────────────


_RATE_WINDOW_SECONDS = 60 * 60  # 1 hour
_RATE_MAX_PER_WINDOW = 5  # 5 corrections per hour per authenticated user

_rate_buckets: dict[str, deque[float]] = {}
_rate_lock = Lock()


def record_and_check_rate(user_id: str | None) -> bool:
    """Record a correction-request submission and report whether it's allowed.

    Returns ``True`` when the submission is within quota, ``False``
    when the caller has exceeded the per-hour cap. ``None`` (anonymous
    — should not happen on this endpoint) bypasses the limiter; the
    router still rejects with 401 before reaching the service.
    """
    if user_id is None:
        return True
    now = time.monotonic()
    cutoff = now - _RATE_WINDOW_SECONDS
    with _rate_lock:
        bucket = _rate_buckets.setdefault(user_id, deque())
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= _RATE_MAX_PER_WINDOW:
            return False
        bucket.append(now)
        return True


def _reset_rate_limiter_for_tests() -> None:
    """Test-only hook to clear the in-process rate-limit store."""
    with _rate_lock:
        _rate_buckets.clear()


# ─── Persistence ───────────────────────────────────────────────


def create_correction_request(
    db: Session,
    *,
    workspace_id: str,
    user_id: str,
    user_email: str | None,
    field: str,
    current_value: str,
    proposed_value: str,
    reason: str,
    message: str | None,
    ip_hash: str | None,
    user_agent: str | None,
) -> AuditLog:
    """Persist a correction request as an ``audit_log`` row.

    ``before`` captures the current value, ``after`` captures the
    proposed change. ``metadata`` carries provider-facing identifiers
    (correction id, ip hash, ua) so the admin triage UI / Slack ack can
    surface the request without re-reading the row.

    Returns the persisted row. The row id IS the correction-request id
    surfaced to the provider.
    """
    correction_id = new_id()
    now = utc_now()
    row = AuditLog(
        id=correction_id,
        actor_id=user_id,
        actor_type="provider",
        action="correction_request.submitted",
        entity_type="provider_workspace",
        entity_id=workspace_id,
        before={"field": field, "value": current_value},
        after={"field": field, "value": proposed_value},
        event_metadata={
            "correction_request_id": correction_id,
            "reason": reason,
            "message": message,
            "user_email": user_email,
            "ip_hash": ip_hash,
            "user_agent": user_agent,
            "status": "pending",
        },
        created_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ─── Slack delivery (background) ───────────────────────────────


def deliver_to_slack(correction_id: str, payload_snapshot: dict) -> None:
    """Best-effort POST to the configured Slack webhook.

    Never raises. Logs at WARNING on failure. Called as a FastAPI
    ``BackgroundTask`` so the provider's response is not delayed by
    Slack latency.
    """
    url = (settings.SLACK_CORRECTION_WEBHOOK_URL or "").strip()
    if not url:
        logger.debug("correction_request: slack webhook not configured; skip")
        return

    blocks = _format_slack_blocks(
        correction_id=correction_id, payload=payload_snapshot
    )
    fallback = _format_slack_fallback_text(payload_snapshot)
    body = json.dumps({"blocks": blocks, "text": fallback}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status >= 400:
                logger.warning(
                    "correction_request: slack delivery returned status=%s for id=%s",
                    resp.status,
                    correction_id,
                )
    except urllib.error.URLError as exc:
        logger.warning(
            "correction_request: slack delivery failed for id=%s err=%s",
            correction_id,
            exc,
        )
    except Exception as exc:  # noqa: BLE001 — defensive; never propagate
        logger.warning(
            "correction_request: slack delivery unexpected error for id=%s err=%s",
            correction_id,
            exc,
        )


def _format_slack_fallback_text(p: dict) -> str:
    label = TIER_B_FIELD_LABEL_ES.get(p.get("field", ""), p.get("field", ""))
    provider = p.get("user_email") or p.get("user_id") or "—"
    return f"CheckWise · solicitud de corrección · {label} · {provider}"


def _format_slack_blocks(*, correction_id: str, payload: dict) -> list[dict]:
    field = payload.get("field", "")
    field_label = TIER_B_FIELD_LABEL_ES.get(field, field)
    current_value = (payload.get("current_value") or "").strip() or "—"
    proposed_value = (payload.get("proposed_value") or "").strip() or "—"
    reason = (payload.get("reason") or "").strip() or "—"
    message = (payload.get("message") or "").strip()
    if len(message) > 800:
        message = message[:800].rstrip() + "…"
    workspace_id = payload.get("workspace_id") or "—"
    user_email = payload.get("user_email") or "—"

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "Nueva solicitud de corrección · CheckWise",
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Proveedor*\n{user_email}"},
                {"type": "mrkdwn", "text": f"*Workspace*\n`{workspace_id}`"},
                {"type": "mrkdwn", "text": f"*Campo*\n{field_label}"},
                {"type": "mrkdwn", "text": f"*Folio*\n`{correction_id}`"},
            ],
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Valor actual*\n{current_value}"},
                {"type": "mrkdwn", "text": f"*Valor propuesto*\n{proposed_value}"},
            ],
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Razón*\n{reason}"},
        },
    ]
    if message:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Mensaje adicional del proveedor*\n{message}",
                },
            }
        )
    return blocks


def slack_payload_snapshot(
    *,
    workspace_id: str,
    user_id: str,
    user_email: str | None,
    field: str,
    current_value: str,
    proposed_value: str,
    reason: str,
    message: str | None,
) -> dict:
    """Build the small dict the BackgroundTask closes over."""
    return {
        "workspace_id": workspace_id,
        "user_id": user_id,
        "user_email": user_email,
        "field": field,
        "current_value": current_value,
        "proposed_value": proposed_value,
        "reason": reason,
        "message": message,
    }


__all__ = [
    "TIER_B_FIELDS",
    "TIER_B_FIELD_LABEL_ES",
    "create_correction_request",
    "deliver_to_slack",
    "record_and_check_rate",
    "slack_payload_snapshot",
]
