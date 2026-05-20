"""Service layer for internal feedback (tester bug / improvement reports).

Two-step Slack flow when a PNG screenshot is attached:

1. ``chat.postMessage`` with a Block Kit body → returns the message ts.
2. ``files.upload_v2`` (``files.getUploadURLExternal`` → POST bytes →
   ``files.completeUploadExternal``) posted as a *thread reply* on that
   ts, so the channel timeline stays tidy.

When no screenshot is attached, only step 1 runs.

Like ``contact_service.deliver_to_slack``, this function is best-effort:
it never raises. Slack failures are logged at WARNING and discarded so
the caller's HTTP response is independent of Slack health. It is meant
to be called from a FastAPI ``BackgroundTask``.

Rate limits.
  * ``record_and_check_rate`` — authenticated submitters. Keyed by user
    id, 10 reports per minute per user. Generous because logged-in
    testers are trusted.
  * ``record_and_check_public_rate`` — anonymous landing-page
    submitters. Keyed by peppered IP hash, 5 reports per hour per IP.
    Tighter because the landing page is publicly indexable and the
    only signal we have to cluster abuse is the source IP.

Both limiters reset on process restart; that's acceptable for V1 of a
public form. Redis-backed limiting is the V2 follow-up if/when the
backend scales beyond one Render instance.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from threading import Lock

from app.core.config import settings
from app.services.contact_service import hash_ip  # peppered SHA-256 IP hash

logger = logging.getLogger(__name__)


PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

_SLACK_TIMEOUT_SECONDS = 10


# ─── Rate limit (in-memory sliding window) ──────────────────────


_RATE_WINDOW_SECONDS = 60
_RATE_MAX_PER_WINDOW = 10

_rate_buckets: dict[str, deque[float]] = {}
_rate_lock = Lock()


def record_and_check_rate(user_id: str) -> bool:
    """Record a feedback submission and report whether it is within quota.

    Returns ``True`` when the submission is allowed (and recorded),
    ``False`` when the user has exceeded the per-minute cap.
    """
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


# Public landing-page submissions get a separate, tighter bucket — they
# come from anonymous traffic and the only ID we have is the source IP.
_PUBLIC_RATE_WINDOW_SECONDS = 60 * 60  # 1 hour
_PUBLIC_RATE_MAX_PER_WINDOW = 5

_public_rate_buckets: dict[str, deque[float]] = {}
_public_rate_lock = Lock()


def record_and_check_public_rate(ip_hash: str | None) -> bool:
    """Record an anonymous submission and report whether it is within quota.

    ``ip_hash`` is the peppered SHA-256 fingerprint from
    ``contact_service.hash_ip``. ``None`` (unknown IP — should be rare,
    means the proxy headers are misconfigured) bypasses the limiter so
    a single broken header doesn't lock everyone out; we'd rather get
    the report and triage by hand.

    Returns ``True`` when the submission is allowed (and recorded),
    ``False`` when the caller has exceeded the per-hour cap.
    """
    if ip_hash is None:
        return True
    now = time.monotonic()
    cutoff = now - _PUBLIC_RATE_WINDOW_SECONDS
    with _public_rate_lock:
        bucket = _public_rate_buckets.setdefault(ip_hash, deque())
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= _PUBLIC_RATE_MAX_PER_WINDOW:
            return False
        bucket.append(now)
        return True


def _reset_rate_limiter_for_tests() -> None:
    """Test-only hook to clear both in-process rate-limit stores."""
    with _rate_lock:
        _rate_buckets.clear()
    with _public_rate_lock:
        _public_rate_buckets.clear()


# ─── Slack delivery (background) ────────────────────────────────


def deliver_to_slack(snapshot: dict, screenshot_bytes: bytes | None) -> None:
    """Best-effort delivery of a feedback report to the Slack channel.

    Never raises. ``snapshot`` is a small plain dict captured at request
    time (see ``app.api.v1.feedback``); the background task closes over
    it instead of re-reading the request.
    """
    token = (settings.SLACK_BOT_TOKEN or "").strip()
    channel = (settings.SLACK_FEEDBACK_CHANNEL_ID or "").strip()
    if not token or not channel:
        logger.debug("feedback: slack not configured; skip")
        return

    try:
        thread_ts = _post_main_message(token=token, channel=channel, snapshot=snapshot)
    except Exception as exc:  # noqa: BLE001 — defensive; never propagate
        logger.warning("feedback: chat.postMessage failed err=%s", exc)
        return

    if not screenshot_bytes:
        return

    try:
        _upload_screenshot(
            token=token,
            channel=channel,
            thread_ts=thread_ts,
            png=screenshot_bytes,
            filename=f"feedback-{int(time.time())}.png",
            title=f"Screenshot — {snapshot.get('path') or '/'}",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("feedback: screenshot upload failed err=%s", exc)


# ─── Slack helpers ──────────────────────────────────────────────


def _post_main_message(*, token: str, channel: str, snapshot: dict) -> str | None:
    body = json.dumps(
        {
            "channel": channel,
            "blocks": _format_blocks(snapshot),
            "text": _fallback_text(snapshot),
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=_SLACK_TIMEOUT_SECONDS) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if not payload.get("ok"):
        raise RuntimeError(f"chat.postMessage error: {payload.get('error')}")
    return payload.get("ts")


def _upload_screenshot(
    *,
    token: str,
    channel: str,
    thread_ts: str | None,
    png: bytes,
    filename: str,
    title: str,
) -> None:
    # 1. Reserve an upload URL.
    qs = urllib.parse.urlencode({"filename": filename, "length": len(png)})
    req1 = urllib.request.Request(
        f"https://slack.com/api/files.getUploadURLExternal?{qs}",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    with urllib.request.urlopen(req1, timeout=_SLACK_TIMEOUT_SECONDS) as resp:
        payload1 = json.loads(resp.read().decode("utf-8"))
    if not payload1.get("ok"):
        raise RuntimeError(f"getUploadURLExternal error: {payload1.get('error')}")
    upload_url = payload1["upload_url"]
    file_id = payload1["file_id"]

    # 2. POST the PNG bytes to the reserved URL.
    req2 = urllib.request.Request(
        upload_url,
        data=png,
        headers={"Content-Type": "application/octet-stream"},
        method="POST",
    )
    with urllib.request.urlopen(req2, timeout=_SLACK_TIMEOUT_SECONDS) as resp:
        if resp.status >= 400:
            raise RuntimeError(f"upload POST failed status={resp.status}")

    # 3. Finalize the upload into the channel (as a thread reply when ts known).
    complete_body: dict = {
        "files": [{"id": file_id, "title": title}],
        "channel_id": channel,
    }
    if thread_ts:
        complete_body["thread_ts"] = thread_ts
    req3 = urllib.request.Request(
        "https://slack.com/api/files.completeUploadExternal",
        data=json.dumps(complete_body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    with urllib.request.urlopen(req3, timeout=_SLACK_TIMEOUT_SECONDS) as resp:
        payload3 = json.loads(resp.read().decode("utf-8"))
    if not payload3.get("ok"):
        raise RuntimeError(f"completeUploadExternal error: {payload3.get('error')}")


# ─── Block Kit formatters ───────────────────────────────────────


def _fallback_text(s: dict) -> str:
    label = "🐛 Bug" if s.get("type") == "bug" else "💡 Improvement"
    if s.get("is_public"):
        who = s.get("contact_email") or f"anon:{s.get('ip_hash') or '—'}"
        return f"CheckWise · {label} (público) · {who} · {s.get('path') or ''}"
    return f"CheckWise · {label} · {s.get('user_email') or ''} · {s.get('path') or ''}"


def _format_blocks(s: dict) -> list[dict]:
    kind = s.get("type", "bug")
    header = "🐛 Bug report" if kind == "bug" else "💡 Improvement"
    is_public = bool(s.get("is_public"))
    if is_public:
        header = f"{header} (público)"

    description = (s.get("description") or "").strip()
    if len(description) > 2800:
        description = description[:2800].rstrip() + "…"

    url = s.get("url") or "#"
    user_agent = (s.get("user_agent") or "")[:120]

    # Authenticated submissions show user identity + roles. Public
    # submissions instead show contact email (optional) and the
    # peppered IP-hash fingerprint so the same anonymous reporter can
    # be clustered across multiple reports without leaking PII.
    if is_public:
        contact_email = s.get("contact_email") or "—"
        ip_hash = s.get("ip_hash") or "—"
        identity_fields = [
            {"type": "mrkdwn", "text": f"*Email (opcional)*\n{contact_email}"},
            {"type": "mrkdwn", "text": f"*IP hash*\n`{ip_hash}`"},
        ]
    else:
        roles = s.get("user_roles") or []
        roles_text = ", ".join(roles) if roles else "—"
        identity_fields = [
            {"type": "mrkdwn", "text": f"*From*\n{s.get('user_email') or '—'}"},
            {"type": "mrkdwn", "text": f"*Roles*\n{roles_text}"},
        ]

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"CheckWise · {header}"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Description*\n{description}"},
        },
        {
            "type": "section",
            "fields": identity_fields
            + [
                {"type": "mrkdwn", "text": f"*Page*\n`{s.get('path') or '—'}`"},
                {"type": "mrkdwn", "text": f"*Viewport*\n{s.get('viewport') or '—'}"},
            ],
        },
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"<{url}|Open page> · {user_agent or '—'}"},
            ],
        },
    ]

    console_logs = (s.get("console_logs") or "").strip()
    if console_logs:
        if len(console_logs) > 2800:
            console_logs = console_logs[:2800].rstrip() + "\n…"
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Console (last entries)*\n```{console_logs}```",
                },
            }
        )

    return blocks


def feedback_snapshot(
    *,
    kind: str,
    description: str,
    url: str,
    path: str,
    viewport: str,
    user_agent: str,
    console_logs: str,
    user_email: str,
    user_full_name: str,
    user_roles: list[str],
) -> dict:
    """Build the snapshot for an *authenticated* feedback submission."""
    return {
        "type": kind,
        "description": description,
        "url": url,
        "path": path,
        "viewport": viewport,
        "user_agent": user_agent,
        "console_logs": console_logs,
        "user_email": user_email,
        "user_full_name": user_full_name,
        "user_roles": user_roles,
        "is_public": False,
    }


def public_feedback_snapshot(
    *,
    kind: str,
    description: str,
    url: str,
    path: str,
    viewport: str,
    user_agent: str,
    console_logs: str,
    contact_email: str | None,
    ip_hash: str | None,
) -> dict:
    """Build the snapshot for an *anonymous* landing-page submission.

    Same shape as ``feedback_snapshot`` but with ``is_public=True``,
    no user identity, and a peppered IP hash so the receiving channel
    can cluster repeat reporters without storing the raw IP.
    """
    return {
        "type": kind,
        "description": description,
        "url": url,
        "path": path,
        "viewport": viewport,
        "user_agent": user_agent,
        "console_logs": console_logs,
        "contact_email": contact_email,
        "ip_hash": ip_hash,
        "is_public": True,
    }


__all__ = [
    "PNG_MAGIC",
    "deliver_to_slack",
    "feedback_snapshot",
    "hash_ip",
    "public_feedback_snapshot",
    "record_and_check_public_rate",
    "record_and_check_rate",
]
