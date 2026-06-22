"""WhatsApp template payload builders.

Each function in this module produces the ``components`` array that
:func:`app.services.whatsapp_delivery.send_whatsapp_template` posts to
Meta. The functions exist so the event sites stay short and the
template variables can be unit-tested without hitting the network.

Meta requires templates to be **submitted and approved** before they
can be used in production. The canonical submission payload for each
template here lives at ``docs/runbooks/whatsapp_templates.json``; the
runbook walks the operator through pasting it into the Meta WhatsApp
Manager UI. Until a template is approved, ``send_whatsapp_template``
will return a ``failed`` status with Meta's "template not found" body
— that's expected and audited.

Template names:
    * ``cw_renewal_threshold``
    * ``cw_reviewer_decision``

Both templates target ``es_MX`` and live in the ``UTILITY`` category
(Meta's cheapest tier — appropriate for compliance notifications).
"""

from __future__ import annotations

from datetime import date
from typing import Literal

# Public template names. Kept as module constants so callers don't
# scatter string literals across the codebase. If Meta ever requires
# a renamed template we update once here.
RENEWAL_TEMPLATE = "cw_renewal_threshold"
DECISION_TEMPLATE = "cw_reviewer_decision"
# Phase 7 / Slice N8 — phone-verification OTP. Approval pending at
# Meta; until live, ``send_whatsapp_template`` returns ``failed``
# with Meta's "template not found" body and the OTP flow falls
# back to logging the code for dev/staging.
PHONE_OTP_TEMPLATE = "cw_phone_otp"

# Severity → display label used in the renewal template body. The body
# text on Meta's side reads "{{1}} de {{2}} vence en {{3}} ({{4}})";
# this is the value substituted for {{4}}.
_RENEWAL_SEVERITY_LABEL: dict[str, str] = {
    "yellow": "Próximo a vencer",
    "red": "Vencido",
    "info": "Recordatorio",
}

# Reviewer action → display label for {{3}} in the decision template.
#
# This builder is fed by TWO callers with DIFFERENT key styles for the
# same decision, so we map both:
#   * submission_workflow → ``ReviewerAction.value``
#     ('approve' / 'reject' / 'request_clarification' / 'mark_exception')
#   * notifications.fanout → verification event-action values
#     ('approved' / 'rejected' / 'needs_clarification')
# Spanish wording matches email_templates._DECISION_HEADLINE/_DECISION_VERB.
_DECISION_LABEL: dict[str, str] = {
    # ReviewerAction values (submission_workflow path)
    "approve": "Aprobado",
    "reject": "Rechazado",
    "request_clarification": "Requiere aclaración",
    "mark_exception": "Excepción legal",
    # Verification event-action values (fanout path)
    "approved": "Aprobado",
    "rejected": "Rechazado",
    "needs_clarification": "Requiere aclaración",
}


def _text(value: str) -> dict:
    """Wrap a string parameter for Meta's template components shape."""

    return {"type": "text", "text": value}


def _body_components(parameters: list[dict]) -> list[dict]:
    return [{"type": "body", "parameters": parameters}]


def build_renewal_threshold_components(
    *,
    vendor_name: str,
    requirement_name: str,
    due_date: date,
    days_remaining: int,
    severity: Literal["yellow", "red", "info"] = "yellow",
) -> list[dict]:
    """Return the ``components`` array for ``cw_renewal_threshold``.

    Maps to a body text like:
        "*{{1}}* — {{2}} vence el {{3}} ({{4}}). Sube la versión vigente
         antes de la fecha para mantener tu expediente en regla."

    Parameter order:
        {{1}} vendor_name
        {{2}} requirement_name
        {{3}} due_date (formatted DD/MM/YYYY)
        {{4}} severity_label + days_remaining hint
    """

    severity_label = _RENEWAL_SEVERITY_LABEL.get(severity, severity)
    if days_remaining > 0:
        hint = f"{severity_label} · faltan {days_remaining} d"
    elif days_remaining == 0:
        hint = f"{severity_label} · vence hoy"
    else:
        hint = f"{severity_label} · {abs(days_remaining)} d vencido"
    return _body_components(
        [
            _text(vendor_name),
            _text(requirement_name),
            _text(due_date.strftime("%d/%m/%Y")),
            _text(hint),
        ]
    )


def build_reviewer_decision_components(
    *,
    vendor_name: str,
    requirement_name: str,
    decision_action: str,
    reviewer_name: str | None = None,
) -> list[dict]:
    """Return the ``components`` array for ``cw_reviewer_decision``.

    Maps to a body text like:
        "*{{1}}* — Documento «{{2}}» {{3}} por {{4}}. Abre tu expediente
         en CheckWise para ver el detalle."

    Parameter order:
        {{1}} vendor_name
        {{2}} requirement_name
        {{3}} decision label (Aprobado / Rechazado / Requiere aclaración)
        {{4}} reviewer display name (or "Legal Shelf" if unknown)
    """

    decision_label = _DECISION_LABEL.get(decision_action, decision_action)
    reviewer = reviewer_name.strip() if reviewer_name else "Legal Shelf"
    return _body_components(
        [
            _text(vendor_name),
            _text(requirement_name),
            _text(decision_label),
            _text(reviewer),
        ]
    )


def build_phone_otp_components(*, code: str) -> list[dict]:
    """Return the ``components`` array for ``cw_phone_otp``.

    The Meta template body reads:
        "Tu código de verificación de CheckWise es *{{1}}*. Expira en
         10 minutos. Si no lo solicitaste, ignora este mensaje."

    Parameter order:
        {{1}} 6-digit numeric code (plaintext — sent out-of-band only).
    """
    return _body_components([_text(code)])
