"""Provider-neutral SMS / WhatsApp delivery.

Phase 7 cutover — the dispatcher always calls
:func:`send_message`; this module picks the right backend at
call time. The selection order is:

  1. **WhatsApp Cloud API (Meta)** — when ``WHATSAPP_ENABLED`` is
     true, the caller supplied a ``whatsapp_template_name`` +
     components, and Meta credentials are present. This is the
     long-term target; today's blocker is template approval.

  2. **Twilio SMS** — when ``TWILIO_ENABLED`` is true and the
     Twilio env vars are present. This is the interim transport
     so the platform can launch before Meta approval lands. The
     plaintext ``body`` is what goes on the wire — no template
     constraints, no 24-hour rule.

  3. **Dry-run** — neither backend configured. Logs what would
     have gone out and returns ``status="sent"`` so the audit
     trail records the attempt without lying about delivery.

Why one entry point: emitters don't care whether a given recipient
is receiving SMS or WhatsApp this week — they care whether the
message went out. Centralizing the selection here means the
moment Meta approves ``cw_renewal_threshold`` for the live
account, we flip ``WHATSAPP_ENABLED=true`` and **the same call
sites** automatically prefer WhatsApp. No emitter changes, no
dispatcher changes, no UI changes.

Why this module never raises: same discipline as
:mod:`app.services.whatsapp_delivery` and
:mod:`app.services.email_delivery`. Outbound is best-effort; a
Twilio outage cannot break the renewal cron. Every failure path
returns a :class:`MessageDeliveryResult` and the caller decides
what to do with it.

Why stdlib instead of the Twilio SDK: Twilio's send-SMS endpoint
is one POST with HTTP Basic auth. Pulling in the official SDK
adds ~10 transitive deps for an authenticated form-urlencoded
request. ``urllib.request`` + ``base64`` is enough.
"""

from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from app.core.config import settings
from app.services.whatsapp_delivery import (
    send_whatsapp_template,
    whatsapp_configured,
)

log = logging.getLogger("checkwise.messaging_delivery")


def _mask_phone(phone: str | None) -> str:
    """Last-4 only, for logs. ``'****1234'`` (or ``'****'`` if <4 digits).

    CW-LOG-001 — delivery logs must not retain full recipient phone
    numbers (the notification audit path already minimizes to last-4).
    Filtering to digits also strips any ``+``/spaces and prevents CR/LF in
    a crafted value from surviving into the log line (log-injection guard).
    """
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    return f"****{digits[-4:]}" if len(digits) >= 4 else "****"


@dataclass(frozen=True)
class MessageDeliveryResult:
    delivered: bool
    status: str
    backend: str  # "whatsapp" | "twilio" | "dry_run" | "none"
    error: str | None = None
    message_id: str | None = None
    recipient: str | None = None


def twilio_configured() -> bool:
    """True when every env var Twilio's REST API needs is present."""
    return bool(
        settings.TWILIO_ACCOUNT_SID
        and settings.TWILIO_AUTH_TOKEN
        and settings.TWILIO_FROM_NUMBER
    )


def messaging_configured() -> bool:
    """True when at least one backend is reachable.

    Used by the dispatcher / preferences UI to decide whether the
    WhatsApp channel is a viable preference at all. Returns False
    when both backends are unconfigured AND ``MESSAGING_ENABLED``
    is off — in that state every call short-circuits to dry-run.
    """
    if not settings.MESSAGING_ENABLED:
        return False
    return whatsapp_configured() or twilio_configured()


def send_message(
    *,
    to_phone: str,
    body: str,
    whatsapp_template_name: str | None = None,
    whatsapp_components: list[dict] | None = None,
    timeout: float = 12.0,
) -> MessageDeliveryResult:
    """Send a message to ``to_phone`` (E.164, no leading ``+``).

    Always returns a result; never raises. ``status`` values:

      * ``"sent"`` — backend accepted the message (or dry-run).
      * ``"skipped_disabled"`` — ``MESSAGING_ENABLED=false``.
      * ``"skipped_no_recipient"`` — ``to_phone`` is empty.
      * ``"skipped_no_backend"`` — kill switches off / configured
        backends are missing credentials.
      * ``"failed"`` — backend returned an error body. The
        ``error`` field carries Twilio / Meta's response.
    """
    if not settings.MESSAGING_ENABLED:
        return MessageDeliveryResult(
            delivered=False,
            status="skipped_disabled",
            backend="none",
            recipient=to_phone or None,
        )
    if not to_phone:
        return MessageDeliveryResult(
            delivered=False,
            status="skipped_no_recipient",
            backend="none",
        )

    # ---- 1. WhatsApp template path (when eligible) -------------
    # Both the kill switch AND a template name are required to
    # route through WhatsApp. The kill switch alone isn't enough
    # because WhatsApp only accepts pre-approved template sends;
    # there's no plaintext fallback inside Meta's API.
    if (
        settings.WHATSAPP_ENABLED
        and whatsapp_template_name
        and whatsapp_components is not None
        and whatsapp_configured()
    ):
        wa_result = send_whatsapp_template(
            to_phone=to_phone,
            template_name=whatsapp_template_name,
            components=whatsapp_components,
            timeout=timeout,
        )
        return MessageDeliveryResult(
            delivered=wa_result.delivered,
            status=wa_result.status,
            backend="whatsapp",
            error=wa_result.error,
            message_id=wa_result.message_id,
            recipient=wa_result.recipient or to_phone,
        )

    # ---- 2. Twilio SMS path (the interim default) --------------
    if settings.TWILIO_ENABLED and twilio_configured():
        return _send_via_twilio(
            to_phone=to_phone, body=body, timeout=timeout
        )

    # ---- 3. Dry-run / no backend -------------------------------
    if settings.TWILIO_DRY_RUN or settings.WHATSAPP_DRY_RUN:
        log.info(
            "[messaging_delivery] dry-run sent to=%s body_len=%d",
            _mask_phone(to_phone),
            len(body or ""),
        )
        return MessageDeliveryResult(
            delivered=True,
            status="sent",
            backend="dry_run",
            recipient=to_phone,
        )

    return MessageDeliveryResult(
        delivered=False,
        status="skipped_no_backend",
        backend="none",
        recipient=to_phone,
    )


# ---------------------------------------------------------------------------
# Twilio path
# ---------------------------------------------------------------------------


_TWILIO_BASE = "https://api.twilio.com/2010-04-01"


def _send_via_twilio(
    *, to_phone: str, body: str, timeout: float
) -> MessageDeliveryResult:
    """POST to Twilio's Messages.json endpoint with HTTP Basic auth.

    The recipient must be E.164 with the leading ``+`` — Twilio is
    stricter than Meta here. We canonicalize at the wire so the
    function is safe to call with either form.
    """
    if settings.TWILIO_DRY_RUN:
        log.info(
            "[messaging_delivery] twilio dry-run to=%s body_len=%d",
            _mask_phone(to_phone),
            len(body or ""),
        )
        return MessageDeliveryResult(
            delivered=True,
            status="sent",
            backend="twilio",
            recipient=to_phone,
        )

    e164 = to_phone if to_phone.startswith("+") else f"+{to_phone}"
    url = (
        f"{_TWILIO_BASE}/Accounts/"
        f"{settings.TWILIO_ACCOUNT_SID}/Messages.json"
    )
    form = urllib.parse.urlencode(
        {
            "From": settings.TWILIO_FROM_NUMBER,
            "To": e164,
            "Body": body[:1600],  # Twilio caps body at 1600 chars
        }
    ).encode("utf-8")
    auth = base64.b64encode(
        f"{settings.TWILIO_ACCOUNT_SID}:{settings.TWILIO_AUTH_TOKEN}".encode()
    ).decode("ascii")
    req = urllib.request.Request(
        url,
        data=form,
        method="POST",
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            payload = json.loads(raw) if raw else {}
            sid = payload.get("sid")
            return MessageDeliveryResult(
                delivered=True,
                status="sent",
                backend="twilio",
                message_id=sid,
                recipient=e164,
            )
    except urllib.error.HTTPError as exc:
        # CW-LOG-001 — never log or return the raw provider response body
        # (it can carry recipient/message detail and reaches the persisted
        # ``*_reason``/audit fields). The HTTP status code is the sanitized
        # triage signal; mask the recipient in the log.
        log.warning(
            "[messaging_delivery] twilio HTTP %s to=%s",
            exc.code,
            _mask_phone(e164),
        )
        return MessageDeliveryResult(
            delivered=False,
            status="failed",
            backend="twilio",
            error=f"http_{exc.code}",
            recipient=e164,
        )
    except urllib.error.URLError as exc:
        log.warning(
            "[messaging_delivery] twilio network error to=%s reason=%s",
            _mask_phone(e164),
            exc.reason,
        )
        return MessageDeliveryResult(
            delivered=False,
            status="failed",
            backend="twilio",
            error=f"network: {exc.reason}",
            recipient=e164,
        )
    except Exception as exc:  # pragma: no cover — defensive catch-all
        log.exception(
            "[messaging_delivery] twilio unexpected error to=%s",
            _mask_phone(e164),
        )
        return MessageDeliveryResult(
            delivered=False,
            status="failed",
            backend="twilio",
            error=f"unexpected: {exc!r}",
            recipient=e164,
        )
