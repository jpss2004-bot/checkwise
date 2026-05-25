from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr

from app.core.config import settings


@dataclass(frozen=True)
class EmailDeliveryResult:
    delivered: bool
    status: str
    error: str | None = None


def _sender() -> str:
    email = _from_email()
    return formataddr((settings.SMTP_FROM_NAME, email)) if settings.SMTP_FROM_NAME else email


def _host() -> str:
    return settings.SMTP_HOST or settings.EMAIL_SMTP_HOST


def _port() -> int:
    return settings.SMTP_PORT or settings.EMAIL_SMTP_PORT


def _username() -> str:
    return settings.SMTP_USERNAME or settings.EMAIL_SMTP_USER


def _password() -> str:
    return settings.SMTP_PASSWORD or settings.EMAIL_SMTP_PASSWORD


def _from_email() -> str:
    return settings.SMTP_FROM_EMAIL or settings.EMAIL_FROM or _username()


def smtp_configured() -> bool:
    return bool(_host() and _username() and _password() and _from_email())


def send_password_reset_email(*, to_email: str, reset_url: str) -> EmailDeliveryResult:
    """Send a password-reset email through the configured SMTP account."""
    body = "\n".join(
        [
            "Hola,",
            "",
            "Recibimos una solicitud para restablecer tu contraseña de CheckWise.",
            "Abre este enlace para definir una nueva contraseña:",
            "",
            reset_url,
            "",
            f"El enlace vence en {settings.PASSWORD_RESET_EXPIRES_MINUTES} minutos.",
            "Si no solicitaste este cambio, puedes ignorar este correo.",
            "",
            "CheckWise",
        ]
    )
    return send_transactional_email(
        to_email=to_email,
        subject="Restablece tu contraseña de CheckWise",
        body=body,
    )


def send_transactional_email(
    *,
    to_email: str,
    subject: str,
    body: str,
) -> EmailDeliveryResult:
    """Send a transactional plain-text email via the configured SMTP.

    Junta 2026-05-25 — generalised from ``send_password_reset_email``
    so reviewer-decision and renewal-reminder emails can use the
    same delivery plumbing without reimplementing the SMTP dance.
    Returns ``EmailDeliveryResult`` with one of three statuses:

    - ``"skipped"`` — SMTP credentials not configured. The caller
      typically treats this as a no-op (the in-app notification is
      the canonical delivery; email is a redundant courtesy).
    - ``"sent"`` — message accepted by the SMTP relay.
    - ``"failed"`` — SMTP raised. The error string is preserved on
      the result so the caller can log + retry later.

    Plain-text only by design (Junta 2026-05-25 lock). HTML support
    can land in a follow-up once we have a real template designer.
    """
    if not smtp_configured():
        return EmailDeliveryResult(
            delivered=False, status="skipped", error="smtp_not_configured"
        )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = _sender()
    message["To"] = to_email
    message.set_content(body)

    try:
        if settings.SMTP_USE_SSL:
            with smtplib.SMTP_SSL(_host(), _port(), timeout=15) as smtp:
                smtp.login(_username(), _password())
                smtp.send_message(message)
        else:
            with smtplib.SMTP(_host(), _port(), timeout=15) as smtp:
                if settings.SMTP_USE_TLS:
                    smtp.starttls()
                smtp.login(_username(), _password())
                smtp.send_message(message)
    except Exception as exc:  # pragma: no cover - network/provider dependent
        return EmailDeliveryResult(delivered=False, status="failed", error=str(exc))

    return EmailDeliveryResult(delivered=True, status="sent")
