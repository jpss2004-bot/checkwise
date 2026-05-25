"""Plain-text email body templates for transactional outbound.

Junta 2026-05-25 — every outbound transactional email goes through
one of these builders. Pure functions, no IO, no DB access — easy
to test, easy to snapshot, easy to translate.

Conventions
-----------

* Spanish (es-MX) tone matches the rest of the product: ``tú``, not
  ``usted``; clear, short sentences; no exclamation marks.
* Each builder returns ``(subject, body)``. The subject is one line
  with no line breaks; the body is multi-paragraph plain text and
  always ends with a CTA URL and the ``CheckWise`` signature.
* All builders accept already-resolved primitives (names, RFCs,
  dates, URLs). Resolving DB rows into those primitives is the
  caller's responsibility so the templates stay testable without a
  database fixture.

Status labels mirror the canonical Spanish vocabulary used across
the rest of the product (see ``apps/web/lib/api/portal.ts`` and
``apps/web/components/checkwise/portal/requirement-status-badge.tsx``).
"""

from __future__ import annotations

from datetime import date

# Spanish label per reviewer action. Keys mirror
# :class:`app.constants.statuses.ReviewerAction`.
_DECISION_HEADLINE: dict[str, str] = {
    "approve": "Tu documento fue aprobado",
    "reject": "Tu documento necesita correcciones",
    "request_clarification": "El equipo te pide una aclaración",
    "mark_exception": "Tu documento quedó bajo excepción legal",
}

# Verb form used in the body — adapts the headline noun to the
# sentence around it.
_DECISION_VERB: dict[str, str] = {
    "approve": "fue aprobado",
    "reject": "necesita correcciones",
    "request_clarification": "necesita una aclaración",
    "mark_exception": "quedó aprobado bajo excepción legal",
}


def build_provider_decision_email(
    *,
    provider_name: str,
    vendor_name: str,
    requirement_name: str,
    period_label: str | None,
    action: str,
    reason: str | None,
    observations: str | None,
    submission_url: str,
) -> tuple[str, str]:
    """Build the email for the provider whose submission was decided.

    Subject reads as a status, body opens with the headline, lists the
    decision details and the reviewer's note (when present), and ends
    with a CTA to the submission detail page where the provider can
    see the full timeline and the original PDF.
    """
    headline = _DECISION_HEADLINE.get(action, "Tu documento tiene una decisión")
    verb = _DECISION_VERB.get(action, "tiene una decisión")
    subject = f"{headline}: {requirement_name}"

    lines = [
        f"Hola {provider_name},",
        "",
        f"Tu carga de '{requirement_name}'"
        + (f" del periodo {period_label}" if period_label else "")
        + f" {verb}.",
        "",
        f"Proveedor: {vendor_name}",
    ]
    if reason:
        lines.extend(["", f"Motivo: {reason}"])
    if observations:
        lines.extend(["", f"Observaciones del revisor: {observations}"])
    lines.extend(
        [
            "",
            "Abre el detalle en CheckWise para ver el documento "
            "y, si aplica, corregirlo:",
            submission_url,
            "",
            "CheckWise",
        ]
    )
    return subject, "\n".join(lines)


def build_provider_renewal_email(
    *,
    provider_name: str,
    vendor_name: str,
    requirement_name: str,
    due_date: date,
    days_remaining: int,
    severity: str,
    portal_url: str,
) -> tuple[str, str]:
    """Build the email for the provider whose renewal threshold crossed.

    ``severity`` mirrors ``ProviderNotification.severity`` ("yellow"
    for upcoming due dates, "red" for overdue). The headline + verb
    pivot accordingly.
    """
    is_overdue = days_remaining <= 0
    subject = (
        f"Documento vencido por renovar: {requirement_name}"
        if is_overdue
        else f"Próximo vencimiento: {requirement_name}"
    )
    deadline = _format_es_date(due_date)
    body_intro = (
        f"Hola {provider_name},",
        "",
        (
            f"Tu '{requirement_name}' venció el {deadline} y CheckWise lo "
            "sigue marcando como pendiente de renovación."
            if is_overdue
            else
            f"Tu '{requirement_name}' vence el {deadline}. "
            f"Te quedan {days_remaining} días para subir la versión "
            "actualizada antes de que caduque."
        ),
        "",
        f"Proveedor: {vendor_name}",
    )
    lines = list(body_intro)
    lines.extend(
        [
            "",
            (
                "Abre CheckWise para subir el documento actualizado:"
                if is_overdue
                else "Abre CheckWise cuando estés listo para subir la renovación:"
            ),
            portal_url,
            "",
            "CheckWise",
        ]
    )
    # ``severity`` is reserved for future tone tweaks (e.g. a red badge
    # in the subject); for v1 plain-text we keep the same shape.
    _ = severity
    return subject, "\n".join(lines)


def build_client_renewal_email(
    *,
    client_contact_name: str,
    vendor_name: str,
    requirement_name: str,
    due_date: date,
    days_remaining: int,
    severity: str,
    client_portal_url: str,
) -> tuple[str, str]:
    """Build the email for the client_admin whose vendor's renewal
    threshold crossed.

    Distinct from the provider email because the client_admin doesn't
    upload the document themselves — they want to know which provider
    is at risk and where to monitor it.
    """
    is_overdue = days_remaining <= 0
    subject = (
        f"Proveedor con documento vencido: {vendor_name}"
        if is_overdue
        else f"Próximo vencimiento de proveedor: {vendor_name}"
    )
    deadline = _format_es_date(due_date)
    if is_overdue:
        message = (
            f"Tu proveedor {vendor_name} no ha renovado "
            f"'{requirement_name}', vencido el {deadline}. Considera "
            "darle seguimiento antes de la próxima auditoría."
        )
    else:
        message = (
            f"Tu proveedor {vendor_name} debe renovar "
            f"'{requirement_name}' el {deadline}. Le quedan "
            f"{days_remaining} días."
        )
    lines = [
        f"Hola {client_contact_name},",
        "",
        message,
        "",
        "Revisa el estado del expediente del proveedor en CheckWise:",
        client_portal_url,
        "",
        "CheckWise",
    ]
    _ = severity
    return subject, "\n".join(lines)


def _format_es_date(value: date) -> str:
    """``date(2026, 5, 25)`` → ``25 de mayo de 2026``."""
    months_es = [
        "enero",
        "febrero",
        "marzo",
        "abril",
        "mayo",
        "junio",
        "julio",
        "agosto",
        "septiembre",
        "octubre",
        "noviembre",
        "diciembre",
    ]
    return f"{value.day} de {months_es[value.month - 1]} de {value.year}"


__all__ = (
    "build_provider_decision_email",
    "build_provider_renewal_email",
    "build_client_renewal_email",
)
