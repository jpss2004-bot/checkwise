"""Service layer for the public contact form (P0-3).

Responsibilities:

1. Hash the submitter's IP for storage. We use SHA-256 with
   ``AUTH_JWT_SECRET`` as a pepper and truncate to 16 hex chars.
   Enough entropy to cluster suspicious patterns; not reversible
   from a DB dump without the pepper.
2. Insert the row and return the persisted entity.
3. Best-effort Slack notification. Fires as a FastAPI BackgroundTask
   so the response is not delayed by Slack latency. Failures are
   logged and never propagated.

The Slack channel URL comes from ``settings.SLACK_CONTACT_WEBHOOK_URL``.
If empty (the default), delivery is a no-op — persistence is still
guaranteed.

In-memory IP rate limit. ``record_and_check_rate`` returns ``True``
when the request is within the allowance, ``False`` when the caller
has exceeded the per-hour cap. The store is a module-level dict
that resets on process restart — acceptable for V1 of a public form;
Redis-backed limiting is the V2 follow-up.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime
from threading import Lock

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import ContactRequest, new_id, utc_now

logger = logging.getLogger(__name__)


# ─── IP hashing ─────────────────────────────────────────────────


def hash_ip(ip: str | None) -> str | None:
    """Return a peppered 16-hex SHA-256 prefix for the client IP.

    Empty / missing IP → ``None`` (we store NULL rather than the hash
    of an empty string so analytics queries don't conflate
    "unknown source" with a real cluster).
    """
    if not ip:
        return None
    pepper = settings.AUTH_JWT_SECRET or "checkwise-fallback-pepper"
    digest = hashlib.sha256(f"{ip}:{pepper}".encode()).hexdigest()
    return digest[:16]


# ─── Rate limit (in-memory sliding window) ──────────────────────


_RATE_WINDOW_SECONDS = 60 * 60  # 1 hour
_RATE_MAX_PER_WINDOW = 5  # 5 submissions per hour per IP-hash

_rate_buckets: dict[str, deque[float]] = {}
_rate_lock = Lock()


def record_and_check_rate(key: str | None) -> bool:
    """Record a submission and report whether it is within quota.

    ``key`` is the hashed-IP. ``None`` (unknown IP) bypasses the
    limiter so a misconfigured proxy header doesn't lock out
    everyone behind it — operationally we'd rather log the row and
    triage in the DB.

    Returns ``True`` when the submission is allowed (and recorded),
    ``False`` when the caller has exceeded the cap.
    """
    if key is None:
        return True
    now = time.monotonic()
    cutoff = now - _RATE_WINDOW_SECONDS
    with _rate_lock:
        bucket = _rate_buckets.setdefault(key, deque())
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


# ─── Persistence ────────────────────────────────────────────────


def create_contact_request(
    db: Session,
    *,
    name: str,
    email: str,
    message: str,
    company: str | None,
    role: str | None,
    source: str,
    ip_hash: str | None,
    user_agent: str | None,
) -> ContactRequest:
    """Insert and return the persisted ContactRequest."""
    now = utc_now()
    row = ContactRequest(
        id=new_id(),
        name=name,
        email=email,
        company=company,
        role=role,
        message=message,
        source=source,
        status="new",
        ip_hash=ip_hash,
        user_agent=user_agent,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ─── Slack delivery (background) ─────────────────────────────────


def deliver_to_slack(row_id: str, payload_snapshot: dict) -> None:
    """Best-effort POST to the configured Slack webhook.

    Never raises. Logs at WARNING on failure. Called as a FastAPI
    BackgroundTask so the user's response is not delayed by Slack.

    ``payload_snapshot`` is a small dict (name, email, company, role,
    message snippet, source) captured at request time. We avoid
    re-querying the DB from the background task.
    """
    url = (settings.SLACK_CONTACT_WEBHOOK_URL or "").strip()
    if not url:
        logger.debug("contact: slack webhook not configured; skip")
        return

    blocks = _format_slack_blocks(row_id=row_id, payload=payload_snapshot)
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
                    "contact: slack delivery returned status=%s for row=%s",
                    resp.status,
                    row_id,
                )
    except urllib.error.URLError as exc:
        logger.warning(
            "contact: slack delivery failed for row=%s err=%s",
            row_id,
            exc,
        )
    except Exception as exc:  # noqa: BLE001 — defensive; never propagate
        logger.warning(
            "contact: slack delivery unexpected error for row=%s err=%s",
            row_id,
            exc,
        )


def _format_slack_fallback_text(p: dict) -> str:
    name = p.get("name", "")
    company = p.get("company") or "—"
    return f"CheckWise · nuevo contacto · {name} ({company})"


def _format_slack_blocks(*, row_id: str, payload: dict) -> list[dict]:
    name = payload.get("name", "")
    email = payload.get("email", "")
    company = payload.get("company") or "—"
    role = payload.get("role") or "—"
    source = payload.get("source") or "landing"
    message = (payload.get("message") or "").strip()
    if len(message) > 800:
        message = message[:800].rstrip() + "…"
    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "Nueva solicitud de contacto · CheckWise"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Nombre*\n{name}"},
                {"type": "mrkdwn", "text": f"*Email*\n{email}"},
                {"type": "mrkdwn", "text": f"*Empresa*\n{company}"},
                {"type": "mrkdwn", "text": f"*Rol*\n{role}"},
                {"type": "mrkdwn", "text": f"*Origen*\n{source}"},
                {"type": "mrkdwn", "text": f"*ID*\n`{row_id}`"},
            ],
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Mensaje*\n{message or '_(vacío)_'}"},
        },
    ]


# ─── Helper for endpoint composition ────────────────────────────


def slack_payload_snapshot(
    *,
    name: str,
    email: str,
    company: str | None,
    role: str | None,
    message: str,
    source: str,
) -> dict:
    """Build the small dict the background task closes over."""
    return {
        "name": name,
        "email": email,
        "company": company,
        "role": role,
        "message": message,
        "source": source,
    }


def now_iso() -> datetime:
    """Compat wrapper so tests can monkeypatch a deterministic clock."""
    return utc_now()
