"""WhatsApp Cloud API (Meta direct) — low-level outbound transport.

Mirrors the shape of :mod:`app.services.email_delivery`. One function,
one purpose: ship a *template* message to a phone number using Meta's
Graph API and report back what happened. Caller orchestrates which
template, the parameters, the recipient — this module owns only the
wire.

Why templates only:
    Meta requires pre-approved templates for outbound utility / business
    messages. There is no "send a freeform message" path for the first
    contact a user has had with you in 24 hr. The catalog of approved
    templates lives in :mod:`app.services.whatsapp_templates`.

Why this module never raises:
    Outbound notifications are best-effort. A WhatsApp API hiccup must
    not break the renewal cron or the reviewer-decision request. The
    function returns ``WhatsAppDeliveryResult(delivered=False, …)`` on
    every failure mode and the caller decides what to do with it.

Why we don't pull in the official Facebook SDK:
    The Meta Cloud API for utility templates is one POST. Pulling in
    the official SDK adds ~6 transitive dependencies for what is
    effectively ``urllib.request.urlopen`` with a JSON body. Using the
    stdlib keeps the wheel tight and the surface area small. If we
    later need media uploads, webhooks, or interactive components, that
    decision can be reversed.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

from app.core.config import settings
from app.services.whatsapp_templates import PHONE_OTP_TEMPLATE

log = logging.getLogger("checkwise.whatsapp_delivery")

# Meta phone numbers must be E.164 without the leading "+". For
# Mexico (country code 52) a clean ``5512345678`` becomes
# ``525512345678``. The normalizer is permissive on input — it accepts
# ``+52 55 1234 5678``, ``(55) 1234-5678``, ``5215512345678``, or just
# the 10-digit local number — and tries to converge on one E.164 form.
_DIGITS_RE = re.compile(r"\D+")


@dataclass(frozen=True)
class WhatsAppDeliveryResult:
    delivered: bool
    status: str
    error: str | None = None
    message_id: str | None = None
    recipient: str | None = None


def whatsapp_configured() -> bool:
    """True when every env var needed to call Meta is present.

    Used by callers (and by ``send_whatsapp_template``) to short-circuit
    to ``status="skipped"`` instead of attempting a call that will
    obviously 401. Independent of WHATSAPP_ENABLED — config can be
    valid even when the kill switch is off, and vice versa.
    """

    return bool(
        settings.WHATSAPP_ACCESS_TOKEN
        and settings.WHATSAPP_PHONE_NUMBER_ID
        and settings.WHATSAPP_API_VERSION
    )


def normalize_phone_e164(
    raw: str | None,
    *,
    default_country_code: str | None = None,
) -> str | None:
    """Strip a Mexican-style phone into E.164 without the ``+``.

    Returns ``None`` when the input is empty or doesn't have enough
    digits to be a plausible phone number. Meta is strict: spaces,
    dashes, parentheses, and a leading ``+`` all need to come off
    before the POST body.

    Edge cases:
        * If the input already starts with the country code (e.g. ``52
          55 1234 5678``) we keep the country code.
        * If the input is exactly 10 digits we prepend the configured
          default country code (52 for MX).
        * If the input is 11 digits starting with ``1`` (US-style) we
          treat it as US/Canada and keep as-is. Mexico migrated off the
          ``1`` prefix in 2022 so this is unambiguous.
    """

    if not raw:
        return None
    digits = _DIGITS_RE.sub("", raw)
    if not digits:
        return None
    cc = default_country_code or settings.WHATSAPP_DEFAULT_COUNTRY_CODE or "52"
    # Already includes a country code (12-15 digits is the E.164 range)
    if len(digits) >= 11:
        return digits
    # Local 10-digit number → prepend default country code
    if len(digits) == 10:
        return f"{cc}{digits}"
    # Too short to be a real phone — caller can decide to skip.
    return None


def send_whatsapp_template(
    *,
    to_phone: str,
    template_name: str,
    components: list[dict],
    language_code: str | None = None,
    timeout: float = 12.0,
) -> WhatsAppDeliveryResult:
    """Send a single approved WhatsApp template message.

    ``components`` is the structured payload Meta expects — typically a
    list with one ``"type": "body"`` entry whose ``"parameters"`` array
    fills the template's ``{{1}}``, ``{{2}}``, … placeholders in order.
    See :mod:`app.services.whatsapp_templates` for builders that
    produce this shape for the templates we actually ship.

    Returns a :class:`WhatsAppDeliveryResult` with one of these
    statuses:

    * ``"sent"`` — Meta accepted the message and returned a message id.
    * ``"skipped_disabled"`` — WHATSAPP_ENABLED is False (kill switch).
    * ``"skipped_no_recipient"`` — phone normalized to None.
    * ``"skipped_not_configured"`` — required env vars missing.
    * ``"skipped_dry_run"`` — DRY_RUN is on; the payload was logged
      but no HTTP request fired.
    * ``"failed"`` — Meta returned a non-2xx, or the request errored.
    """

    if not settings.WHATSAPP_ENABLED:
        return WhatsAppDeliveryResult(
            delivered=False, status="skipped_disabled"
        )

    if not whatsapp_configured():
        return WhatsAppDeliveryResult(
            delivered=False,
            status="skipped_not_configured",
            error="whatsapp_credentials_missing",
        )

    recipient = normalize_phone_e164(to_phone)
    if not recipient:
        return WhatsAppDeliveryResult(
            delivered=False,
            status="skipped_no_recipient",
            error="phone_unparsable",
            recipient=to_phone,
        )

    payload = {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {
                "code": language_code or settings.WHATSAPP_DEFAULT_LANGUAGE_CODE
            },
            "components": components,
        },
    }

    if settings.WHATSAPP_DRY_RUN:
        # DRY_RUN is a dev/staging aid. If it's ever set on a non-local
        # deploy, real outbound is silently disabled — log loudly so the
        # misconfiguration is visible instead of users mysteriously never
        # receiving messages (e.g. their phone-verification OTP).
        if not settings.is_local_env:
            log.warning(
                "whatsapp.dry_run_in_non_local CHECKWISE_ENV=%s template=%s — "
                "outbound WhatsApp is DISABLED (WHATSAPP_DRY_RUN=true). Unset "
                "WHATSAPP_DRY_RUN to send real messages.",
                settings.CHECKWISE_ENV,
                template_name,
            )
        # Logged at INFO so a dev tail can confirm what would have shipped
        # without the call ever reaching Meta. Useful while templates are
        # in review. NEVER log the OTP template's components — that array
        # carries the plaintext 6-digit verification code, which must not
        # land in logs regardless of environment. Log a redacted summary
        # for OTP; the full payload is fine for non-secret templates.
        # Scrub CR/LF from the recipient before logging so a crafted value
        # can't forge log lines (CodeQL log-injection).
        safe_to = str(recipient).replace("\r", " ").replace("\n", " ")
        if template_name == PHONE_OTP_TEMPLATE:
            log.info(
                "whatsapp.dry_run template=%s to=%s components=<redacted "
                "OTP, %d component(s)>",
                template_name,
                safe_to,
                len(components),
            )
        else:
            log.info(
                "whatsapp.dry_run template=%s to=%s components=%s",
                template_name,
                safe_to,
                json.dumps(components, ensure_ascii=False),
            )
        return WhatsAppDeliveryResult(
            delivered=False,
            status="skipped_dry_run",
            recipient=recipient,
        )

    url = (
        f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}"
        f"/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    )
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw) if raw else {}
        message_id = None
        if isinstance(data, dict):
            messages = data.get("messages") or []
            if messages and isinstance(messages, list):
                message_id = messages[0].get("id")
        return WhatsAppDeliveryResult(
            delivered=True,
            status="sent",
            message_id=message_id,
            recipient=recipient,
        )
    except urllib.error.HTTPError as exc:
        # Meta returns useful JSON in the body — surface it to the
        # caller so the audit log can record *why* the send failed
        # (template not approved, recipient not opted-in, etc.).
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:  # pragma: no cover — defensive
            detail = ""
        log.warning(
            "whatsapp.http_error status=%s template=%s detail=%s",
            exc.code,
            template_name,
            detail[:500],
        )
        return WhatsAppDeliveryResult(
            delivered=False,
            status="failed",
            error=f"http_{exc.code}: {detail[:300]}",
            recipient=recipient,
        )
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        log.warning("whatsapp.transport_error template=%s err=%s", template_name, exc)
        return WhatsAppDeliveryResult(
            delivered=False,
            status="failed",
            error=str(exc),
            recipient=recipient,
        )
