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


def send_welcome_with_temp_password_email(
    *,
    to_email: str,
    full_name: str,
    login_url: str,
    temp_password: str,
    role: str,
    organization_name: str | None = None,
) -> EmailDeliveryResult:
    """Welcome email shipped by the unified ``POST /admin/users`` flow.

    Carries the freshly-minted temporary credentials in plaintext.
    Recipient logs in with them, the backend's ``must_change_password``
    flag forces them through ``/activate``, and the temp password is
    discarded on first password rotation.

    Role drives the closing copy (client_admin → finish company
    profile + add providers; provider → upload first batch of
    documents). Everything else is shared.
    """
    if role == "client":
        next_step = (
            "3. Completa los datos fiscales de tu empresa y agrega a "
            "tus proveedores desde tu perfil."
        )
        subject = (
            f"Bienvenido a CheckWise — tus credenciales para {full_name}"
        )
    else:
        next_step = (
            "3. Sube los documentos REPSE pendientes desde tu espacio "
            "de proveedor."
        )
        subject = "Bienvenido a CheckWise — tus credenciales de proveedor"
    org_line = (
        f"Tu empresa {organization_name} ya está registrada en CheckWise."
        if organization_name
        else "Tu cuenta de CheckWise ya está activa."
    )
    body = "\n".join(
        [
            f"Hola {full_name},",
            "",
            org_line,
            "",
            "Para iniciar sesión por primera vez:",
            "",
            f"  1. Abre: {login_url}",
            f"  2. Inicia sesión con tu correo ({to_email}) y la "
            f"contraseña temporal: {temp_password}",
            next_step,
            "",
            (
                "Apenas inicies sesión te pediremos cambiar la "
                "contraseña temporal por una propia."
            ),
            "",
            "Si necesitas ayuda, responde este correo y te apoyamos.",
            "",
            "Equipo LegalShelf · CheckWise",
        ]
    )
    return send_transactional_email(
        to_email=to_email,
        subject=subject,
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
