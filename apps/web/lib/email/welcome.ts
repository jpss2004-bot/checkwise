/**
 * Welcome / activation email scaffold.
 *
 * This module owns the **template** the admin will eventually send
 * when inviting a new provider or client to CheckWise. It is
 * deliberately tiny and dependency-free so a future backend (Resend,
 * Postmark, SendGrid, AWS SES, etc.) can render it without a
 * client-side toolchain.
 *
 * Both `renderWelcomeEmailHtml` and `renderWelcomeEmailText` produce
 * a complete message body — they do NOT add transport-layer headers
 * (From, To, Subject). The transport adapter is responsible for that.
 *
 * TODO[backend-integration]:
 *   1. Pick an email provider and wire it into a backend route, e.g.
 *      POST /api/v1/invitations { email, role, company_hint }.
 *   2. Have that route generate an `Invitation` row + a signed
 *      activation token (JWT or stateful token, decide on auth side).
 *   3. Call this renderer with the resulting context, then ship the
 *      message via the provider's SDK.
 *   4. Set the activation URL host to the production domain via env
 *      (NEXT_PUBLIC_APP_URL or backend equivalent).
 */

export type InvitationRole = "provider" | "client";

export interface WelcomeEmailContext {
  /** Receiver display name (may be empty — template falls back to "tu"). */
  recipient_name: string;
  /** Plain-text role label shown in the email body. */
  role: InvitationRole;
  /** Receiver's company / vendor name. Optional — falls back to a generic line. */
  company_hint?: string | null;
  /** Issuing inviter (the CheckWise admin's display name or company). */
  inviter: string;
  /** Absolute activation URL. Should include `?token=…`. */
  activation_url: string;
  /** Plain-text token expiry, already formatted in es-MX. */
  expires_at_human: string;
  /** Support contact, included in the footer. */
  support_email: string;
}

const ROLE_LABEL: Record<InvitationRole, string> = {
  provider: "proveedor",
  client: "cliente",
};

const SUBJECT_BY_ROLE: Record<InvitationRole, string> = {
  provider:
    "Te invitaron a CheckWise · Activa tu cuenta de proveedor",
  client: "Te invitaron a CheckWise · Activa tu cuenta de cliente",
};

/** Returns the subject line for the welcome email. */
export function welcomeEmailSubject(role: InvitationRole): string {
  return SUBJECT_BY_ROLE[role];
}

/** Plain-text body. Use this as the multipart/alternative text/plain. */
export function renderWelcomeEmailText(ctx: WelcomeEmailContext): string {
  const greeting = ctx.recipient_name
    ? `Hola ${ctx.recipient_name},`
    : "Hola,";
  const companyLine = ctx.company_hint
    ? ` (${ctx.company_hint})`
    : "";

  return [
    greeting,
    "",
    `${ctx.inviter} te invitó a unirte a CheckWise como ${ROLE_LABEL[ctx.role]}${companyLine}.`,
    "",
    "CheckWise es la plataforma de cumplimiento documental REPSE de Legal Shelf.",
    "Desde tu portal podrás:",
    "",
    "  1. Crear tu contraseña.",
    "  2. Confirmar tu información de perfil.",
    "  3. Completar tu expediente inicial.",
    "  4. Acceder a tu dashboard de cumplimiento y reportes.",
    "",
    "Activa tu cuenta aquí:",
    ctx.activation_url,
    "",
    `Este enlace vence el ${ctx.expires_at_human}.`,
    "",
    `¿Necesitas ayuda? Escríbenos a ${ctx.support_email}.`,
    "",
    "— Equipo CheckWise · Powered by Legal Shelf",
  ].join("\n");
}

/**
 * HTML body. Inline styles only — avoids `<style>` blocks because
 * Gmail / Outlook strip them in many contexts.
 *
 * Brand colors are hard-coded here (not from CSS tokens) since the
 * recipient's email client won't have access to our design-system
 * variables.
 */
export function renderWelcomeEmailHtml(ctx: WelcomeEmailContext): string {
  const greeting = ctx.recipient_name
    ? `Hola ${escapeHtml(ctx.recipient_name)},`
    : "Hola,";
  const companyLine = ctx.company_hint
    ? ` <em>(${escapeHtml(ctx.company_hint)})</em>`
    : "";

  return `<!doctype html>
<html lang="es">
  <head>
    <meta charset="utf-8" />
    <title>${escapeHtml(welcomeEmailSubject(ctx.role))}</title>
  </head>
  <body style="margin:0;padding:0;background:#F7F9FB;font-family:'Geist','Helvetica Neue',Arial,sans-serif;color:#1B2638;">
    <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="background:#F7F9FB;padding:32px 16px;">
      <tr>
        <td align="center">
          <table role="presentation" cellpadding="0" cellspacing="0" width="560" style="max-width:560px;background:#ffffff;border:1px solid #DDE2EC;border-radius:12px;overflow:hidden;">
            <tr>
              <td style="background:#013557;padding:24px 32px;color:#ffffff;">
                <p style="margin:0;font-size:12px;letter-spacing:0.18em;text-transform:uppercase;color:#09c1b0;">Te invitaron a CheckWise</p>
                <h1 style="margin:8px 0 0 0;font-size:22px;line-height:28px;color:#ffffff;">Activa tu cuenta</h1>
              </td>
            </tr>
            <tr>
              <td style="padding:28px 32px;font-size:14px;line-height:22px;">
                <p style="margin:0 0 14px 0;">${greeting}</p>
                <p style="margin:0 0 14px 0;">
                  <strong>${escapeHtml(ctx.inviter)}</strong> te invitó a unirte a CheckWise como
                  <strong>${ROLE_LABEL[ctx.role]}</strong>${companyLine}.
                </p>
                <p style="margin:0 0 18px 0;color:#5F6E87;">
                  CheckWise es la plataforma de cumplimiento documental REPSE de Legal Shelf.
                  En menos de 5 minutos quedas listo.
                </p>

                <ol style="margin:0 0 20px 0;padding:0 0 0 20px;color:#1B2638;">
                  <li style="margin-bottom:6px;">Crea tu contraseña.</li>
                  <li style="margin-bottom:6px;">Confirma tu información.</li>
                  <li style="margin-bottom:6px;">Completa tu expediente inicial.</li>
                  <li>Accede a tu dashboard y reportes.</li>
                </ol>

                <p style="margin:24px 0;">
                  <a href="${escapeAttr(ctx.activation_url)}"
                     style="display:inline-block;background:#013557;color:#ffffff;padding:12px 22px;border-radius:8px;text-decoration:none;font-weight:600;font-size:14px;">
                    Activar mi cuenta
                  </a>
                </p>

                <p style="margin:0 0 6px 0;font-size:12px;color:#8D98AE;">
                  Si el botón no funciona, copia y pega este enlace en tu navegador:
                </p>
                <p style="margin:0 0 18px 0;word-break:break-all;font-family:'Geist Mono',monospace;font-size:12px;color:#5F6E87;">
                  ${escapeHtml(ctx.activation_url)}
                </p>

                <p style="margin:0 0 14px 0;font-size:12px;color:#8D98AE;">
                  Este enlace vence el <strong>${escapeHtml(ctx.expires_at_human)}</strong>.
                  Si crees que recibiste este correo por error, ignóralo.
                </p>
              </td>
            </tr>
            <tr>
              <td style="border-top:1px solid #EEF1F6;padding:18px 32px;background:#F7F9FB;font-size:12px;color:#5F6E87;">
                ¿Necesitas ayuda? Escríbenos a
                <a href="mailto:${escapeAttr(ctx.support_email)}" style="color:#024069;text-decoration:none;">${escapeHtml(ctx.support_email)}</a>.
                <br />
                — Equipo CheckWise · Powered by Legal Shelf
              </td>
            </tr>
          </table>
          <p style="margin:14px 0 0 0;font-size:11px;color:#8D98AE;">
            Recibiste este correo porque ${escapeHtml(ctx.inviter)} solicitó tu acceso a CheckWise.
          </p>
        </td>
      </tr>
    </table>
  </body>
</html>`;
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function escapeAttr(value: string): string {
  return escapeHtml(value);
}
