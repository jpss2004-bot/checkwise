from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from typing import Final

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


def send_owner_reset_temp_password_email(
    *,
    to_email: str,
    full_name: str,
    login_url: str,
    temp_password: str,
    organization_name: str | None = None,
) -> EmailDeliveryResult:
    """Temp credentials issued by the account owner (multi-user step 2).

    Sent when the Primary Account Owner resets a secondary user's
    password from ``POST /client/users/{id}/reset-password``. Same
    plaintext-once discipline as the welcome email: the recipient
    logs in with the temp password and ``must_change_password``
    forces a rotation. Plain text (like the self-service reset) —
    the welcome HTML's "Bienvenido" framing would be wrong here.
    """
    origin = (
        f"El titular de la cuenta de {organization_name}"
        if organization_name
        else "El titular de su cuenta"
    )
    body = "\n".join(
        [
            f"Hola {full_name}:",
            "",
            f"{origin} restableció su contraseña de CheckWise.",
            "",
            "Sus nuevos datos de acceso:",
            f"  Usuario:               {to_email}",
            f"  Contraseña temporal:   {temp_password}",
            "",
            f"Ingrese en {login_url} con la contraseña temporal; por "
            "seguridad, le pediremos definir una nueva en cuanto "
            "inicie sesión.",
            "",
            "Si usted no esperaba este cambio, contacte al titular de "
            "su cuenta o responda a este correo.",
            "",
            "Equipo LegalShelf · CheckWise",
        ]
    )
    return send_transactional_email(
        to_email=to_email,
        subject="CheckWise — su contraseña fue restablecida",
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

    Voice is formal ``usted`` throughout (B2B REPSE compliance tone).
    Role drives subject + intro + closing step:
      * ``client``   → finish company profile + register providers.
      * ``provider`` → upload first batch of REPSE documents.
      * ``admin``    → internal LegalShelf admin; generic intro.
    Ships a branded HTML body with a plain-text fallback (the text
    part still renders cleanly in text-only clients).
    """
    if role == "client":
        subject = (
            f"Bienvenido a CheckWise — acceso para {organization_name}"
            if organization_name
            else "Bienvenido a CheckWise — sus credenciales de acceso"
        )
        intro_line = (
            f"Su empresa {organization_name} ya está registrada en "
            "CheckWise y su cuenta de administrador está lista."
            if organization_name
            else "Su cuenta de CheckWise ya está activa."
        )
        next_step = (
            "Complete los datos fiscales de su empresa y registre a sus "
            "proveedores desde su perfil."
        )
    elif role == "admin":
        subject = "Bienvenido a CheckWise — su acceso de administrador"
        intro_line = "Su cuenta de administrador de CheckWise ya está activa."
        next_step = (
            "Revise el panel de administración y configure a su equipo."
        )
    else:  # provider
        subject = "Bienvenido a CheckWise — su acceso de proveedor"
        intro_line = (
            f"Su espacio de proveedor para {organization_name} ya está "
            "activo en CheckWise."
            if organization_name
            else "Su cuenta de CheckWise ya está activa."
        )
        next_step = (
            "Cargue los documentos REPSE pendientes desde su espacio de "
            "proveedor."
        )

    body = "\n".join(
        [
            f"Hola {full_name}:",
            "",
            intro_line,
            "",
            "Sus datos de acceso:",
            f"  Usuario:               {to_email}",
            f"  Contraseña temporal:   {temp_password}",
            "",
            "Para ingresar por primera vez:",
            f"  1. Abra {login_url}",
            "  2. Inicie sesión con el usuario y la contraseña temporal "
            "de arriba.",
            f"  3. {next_step}",
            "",
            (
                "Por seguridad, le pediremos cambiar la contraseña "
                "temporal en cuanto inicie sesión."
            ),
            "",
            "Si necesita ayuda, responda a este correo y con gusto le "
            "apoyamos.",
            "",
            "Equipo LegalShelf · CheckWise",
        ]
    )
    html_body = _render_welcome_html(
        full_name=full_name,
        to_email=to_email,
        login_url=login_url,
        temp_password=temp_password,
        intro_line=intro_line,
        next_step=next_step,
    )
    return send_transactional_email(
        to_email=to_email,
        subject=subject,
        body=body,
        html_body=html_body,
    )


# --- Brand tokens (from the CheckWise brand sheet). Kept inline so the
# email service stays dependency-free; mirror brand_assets/Logos CW. ----
_BRAND_NAVY: Final = "#013557"
_BRAND_TEAL: Final = "#09c1b0"
_BRAND_INK: Final = "#1f2933"
_BRAND_MUTED: Final = "#52606d"


def _logo_url() -> str:
    """Absolute URL to the trademark lockup PNG served by the frontend.

    Email clients can't resolve relative paths, so we anchor on
    ``FRONTEND_BASE_URL`` (the same base every transactional link uses).
    Asset lives at ``apps/web/public/brand/checkwise-lockup.png``.
    """
    return f"{settings.FRONTEND_BASE_URL.rstrip('/')}/brand/checkwise-lockup.png"


def _esc(value: str) -> str:
    """Minimal HTML escaping for interpolated user/data strings."""
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _render_welcome_html(
    *,
    full_name: str,
    to_email: str,
    login_url: str,
    temp_password: str,
    intro_line: str,
    next_step: str,
) -> str:
    """Branded, email-safe HTML for the welcome message.

    Table-based, inline-styled, no external CSS — the lowest common
    denominator that survives Gmail/Outlook/Apple Mail. The plain-text
    body passed alongside is the fallback for text-only clients.
    """
    name = _esc(full_name)
    email = _esc(to_email)
    pwd = _esc(temp_password)
    intro = _esc(intro_line)
    step = _esc(next_step)
    login = _esc(login_url)
    return f"""\
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Bienvenido a CheckWise</title>
</head>
<body style="margin:0;padding:0;background-color:#f0f2f5;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" \
style="background-color:#f0f2f5;padding:24px 0;">
<tr><td align="center">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" \
style="max-width:560px;width:100%;background-color:#ffffff;border-radius:12px;\
overflow:hidden;border:1px solid #e4e7eb;">
<tr><td align="center" style="padding:32px 32px 8px 32px;">
<img src="{_logo_url()}" alt="CheckWise" width="180" \
style="display:block;width:180px;max-width:60%;height:auto;">
</td></tr>
<tr><td style="padding:16px 40px 0 40px;font-family:'Open Sans',Arial,\
sans-serif;color:{_BRAND_INK};font-size:16px;line-height:1.5;">
<p style="margin:0 0 16px 0;">Hola {name}:</p>
<p style="margin:0 0 24px 0;color:{_BRAND_MUTED};">{intro}</p>
</td></tr>
<tr><td style="padding:0 40px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" \
style="background-color:#f7f9fa;border:1px solid #e4e7eb;border-radius:8px;">
<tr><td style="padding:18px 20px;font-family:'Open Sans',Arial,sans-serif;">
<p style="margin:0 0 4px 0;font-size:11px;text-transform:uppercase;\
letter-spacing:.06em;color:{_BRAND_MUTED};">Usuario</p>
<p style="margin:0 0 16px 0;font-family:'Courier New',monospace;\
font-size:15px;color:{_BRAND_INK};">{email}</p>
<p style="margin:0 0 4px 0;font-size:11px;text-transform:uppercase;\
letter-spacing:.06em;color:{_BRAND_MUTED};">Contraseña temporal</p>
<p style="margin:0;font-family:'Courier New',monospace;font-size:18px;\
font-weight:bold;color:{_BRAND_NAVY};">{pwd}</p>
</td></tr>
</table>
</td></tr>
<tr><td align="center" style="padding:28px 40px 8px 40px;">
<a href="{login}" style="display:inline-block;background-color:{_BRAND_TEAL};\
color:#ffffff;text-decoration:none;font-family:'Open Sans',Arial,sans-serif;\
font-size:16px;font-weight:bold;padding:13px 32px;border-radius:8px;">\
Ingresar a CheckWise</a>
</td></tr>
<tr><td style="padding:16px 40px 0 40px;font-family:'Open Sans',Arial,\
sans-serif;color:{_BRAND_INK};font-size:15px;line-height:1.6;">
<p style="margin:0 0 8px 0;font-weight:bold;color:{_BRAND_NAVY};">\
Para ingresar por primera vez:</p>
<p style="margin:0 0 6px 0;">1. Abra el enlace de arriba.</p>
<p style="margin:0 0 6px 0;">2. Inicie sesión con el usuario y la \
contraseña temporal.</p>
<p style="margin:0 0 20px 0;">3. {step}</p>
<p style="margin:0 0 20px 0;color:{_BRAND_MUTED};font-size:14px;">\
Por seguridad, le pediremos cambiar la contraseña temporal en cuanto \
inicie sesión.</p>
</td></tr>
<tr><td style="padding:0 40px 32px 40px;border-top:1px solid #e4e7eb;\
font-family:'Open Sans',Arial,sans-serif;color:{_BRAND_MUTED};\
font-size:13px;line-height:1.6;">
<p style="margin:20px 0 4px 0;">Si necesita ayuda, responda a este correo \
y con gusto le apoyamos.</p>
<p style="margin:0;color:{_BRAND_NAVY};font-weight:bold;">\
Equipo LegalShelf · CheckWise</p>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""


def send_transactional_email(
    *,
    to_email: str,
    subject: str,
    body: str,
    html_body: str | None = None,
) -> EmailDeliveryResult:
    """Send a transactional email via the configured SMTP.

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

    ``body`` is the plain-text part (always set). When ``html_body``
    is provided it is attached as a ``multipart/alternative`` HTML
    part — capable clients render the HTML, text-only clients fall
    back to ``body``. Callers that omit ``html_body`` stay plain-text
    (password reset, reviewer decision, renewal reminders).
    """
    if not smtp_configured():
        return EmailDeliveryResult(
            delivered=False, status="skipped", error="smtp_not_configured"
        )

    # Strip CR/LF from header values: EmailMessage's default policy raises
    # ValueError on an embedded linefeed, which would escape this function and
    # break the documented "never raises" contract. Stripping also closes the
    # header-injection vector for values built from vendor/requirement names.
    safe_subject = (subject or "").replace("\r", " ").replace("\n", " ")
    safe_to = (to_email or "").replace("\r", "").replace("\n", "")

    message = EmailMessage()
    message["Subject"] = safe_subject
    message["From"] = _sender()
    message["To"] = safe_to
    message.set_content(body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

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
