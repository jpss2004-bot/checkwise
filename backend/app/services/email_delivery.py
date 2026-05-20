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
    email = settings.SMTP_FROM_EMAIL or settings.SMTP_USERNAME
    return formataddr((settings.SMTP_FROM_NAME, email)) if settings.SMTP_FROM_NAME else email


def smtp_configured() -> bool:
    return bool(
        settings.SMTP_HOST
        and settings.SMTP_USERNAME
        and settings.SMTP_PASSWORD
        and (settings.SMTP_FROM_EMAIL or settings.SMTP_USERNAME)
    )


def send_password_reset_email(*, to_email: str, reset_url: str) -> EmailDeliveryResult:
    """Send a password-reset email through the configured SMTP account."""
    if not smtp_configured():
        return EmailDeliveryResult(delivered=False, status="skipped", error="smtp_not_configured")

    message = EmailMessage()
    message["Subject"] = "Restablece tu contraseña de CheckWise"
    message["From"] = _sender()
    message["To"] = to_email
    message.set_content(
        "\n".join(
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
    )

    try:
        if settings.SMTP_USE_SSL:
            with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
                smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
                if settings.SMTP_USE_TLS:
                    smtp.starttls()
                smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                smtp.send_message(message)
    except Exception as exc:  # pragma: no cover - network/provider dependent
        return EmailDeliveryResult(delivered=False, status="failed", error=str(exc))

    return EmailDeliveryResult(delivered=True, status="sent")
