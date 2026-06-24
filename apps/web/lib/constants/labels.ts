/**
 * Shared Spanish display labels for the catalog enums that surface in
 * the admin and client UIs (roles, persona type, risk level, cadence /
 * frequency / period type, and generic entity status).
 *
 * Why this file exists: before this, each admin page hand-rolled its
 * own status/persona/risk rendering, so raw backend codes leaked into
 * the Spanish operator UI ("internal_admin", "moral", "alto", "mensual",
 * "active"). The fix is one canonical source of user-facing labels so
 * every surface reads the same plain-Spanish string.
 *
 * Document status labels live in ``statuses.ts`` (the compliance state
 * machine). Institution labels live in ``lib/api/portal.ts``
 * (``INSTITUTION_LABELS``) and report audience labels in
 * ``lib/reports/constants.ts`` — both re-exported here so callers have a
 * single import for "give me the Spanish label for this code".
 *
 * Each accessor is forgiving: an unmapped code is humanised
 * (underscores → spaces, first letter capitalised) rather than rendered
 * raw or crashing. The maps cover the values the backend actually emits;
 * the humaniser is only a safety net for codes added server-side but not
 * yet mirrored here.
 */

export { INSTITUTION_LABELS } from "@/lib/api/portal";
export { REPORT_AUDIENCE_LABEL, REPORT_STATUS_LABEL } from "@/lib/reports/constants";

/**
 * Humanise an unmapped enum code as a last resort: ``alta_inicial`` →
 * "Alta inicial". Never returns an empty string for a non-empty input.
 */
function humanizeCode(code: string): string {
  const cleaned = code.replace(/[_-]+/g, " ").trim();
  if (!cleaned) return code;
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
}

// ---------------------------------------------------------------------------
// Membership roles (apps/api/app/constants/roles.py :: MembershipRole)
// ---------------------------------------------------------------------------

export const ROLE_LABELS_ES: Record<string, string> = {
  // Role-model redesign (2026-06-23).
  operations_admin: "Administrador de operaciones",
  platform_admin: "Equipo CheckWise",
  client_admin: "Administrador del cliente",
  client_viewer: "Solo lectura",
  provider: "Proveedor",
  // Deprecated (legacy audit rows may still carry these).
  internal_admin: "Equipo CheckWise",
  reviewer: "Equipo CheckWise",
};

export function roleLabel(code: string): string {
  return ROLE_LABELS_ES[code] ?? humanizeCode(code);
}

/** Join a list of role codes into a readable Spanish string. */
export function roleLabels(codes: readonly string[]): string {
  return codes.map(roleLabel).join(", ");
}

// ---------------------------------------------------------------------------
// Persona type (vendor / workspace)
// ---------------------------------------------------------------------------

export const PERSONA_LABELS_ES: Record<string, string> = {
  moral: "Persona moral",
  fisica: "Persona física",
};

export function personaLabel(code: string | null | undefined): string {
  if (!code) return "—";
  return PERSONA_LABELS_ES[code] ?? humanizeCode(code);
}

// ---------------------------------------------------------------------------
// Requirement risk level
//
// The backend is inconsistent here: the seed writes Spanish ("alto"),
// the admin create endpoint defaults to English ("medium"). Map both
// so a requirement renders the same Spanish label and badge tone no
// matter which path created it.
// ---------------------------------------------------------------------------

type RiskBadgeVariant = "success" | "warning" | "destructive" | "outline";

const RISK_CANONICAL: Record<string, "bajo" | "medio" | "alto" | "critico"> = {
  low: "bajo",
  bajo: "bajo",
  medium: "medio",
  medio: "medio",
  med: "medio",
  high: "alto",
  alto: "alto",
  critical: "critico",
  critico: "critico",
  "crítico": "critico",
};

const RISK_LABELS_ES: Record<"bajo" | "medio" | "alto" | "critico", string> = {
  bajo: "Bajo",
  medio: "Medio",
  alto: "Alto",
  critico: "Crítico",
};

const RISK_VARIANTS: Record<
  "bajo" | "medio" | "alto" | "critico",
  RiskBadgeVariant
> = {
  bajo: "success",
  medio: "warning",
  alto: "destructive",
  critico: "destructive",
};

export function riskLabel(code: string | null | undefined): string {
  if (!code) return "—";
  const canonical = RISK_CANONICAL[code.toLowerCase()];
  return canonical ? RISK_LABELS_ES[canonical] : humanizeCode(code);
}

/** Badge variant for a risk level; ``outline`` for unknown codes. */
export function riskVariant(code: string | null | undefined): RiskBadgeVariant {
  if (!code) return "outline";
  const canonical = RISK_CANONICAL[code.toLowerCase()];
  return canonical ? RISK_VARIANTS[canonical] : "outline";
}

// ---------------------------------------------------------------------------
// Cadence — shared by requirement frequency, load_type, and period_type.
// Values the backend emits are already Spanish-ish but snake_cased /
// lowercase ("alta_inicial", "unica_vez"); these prettify them.
// ---------------------------------------------------------------------------

export const CADENCE_LABELS_ES: Record<string, string> = {
  mensual: "Mensual",
  bimestral: "Bimestral",
  trimestral: "Trimestral",
  cuatrimestral: "Cuatrimestral",
  semestral: "Semestral",
  anual: "Anual",
  unica_vez: "Única vez",
  alta_inicial: "Alta inicial",
  evento: "Por evento",
  reporte_interno: "Reporte interno",
  no_frequency: "Sin periodicidad",
};

export function cadenceLabel(code: string | null | undefined): string {
  if (!code) return "—";
  return CADENCE_LABELS_ES[code.toLowerCase()] ?? humanizeCode(code);
}

// ---------------------------------------------------------------------------
// Generic entity status (client / vendor / workspace)
// ---------------------------------------------------------------------------

type StatusBadgeVariant = "success" | "warning" | "secondary" | "outline";

const ENTITY_STATUS_LABELS_ES: Record<string, string> = {
  active: "Activo",
  inactive: "Inactivo",
  suspended: "Suspendido",
  pending: "Pendiente",
  archived: "Archivado",
};

const ENTITY_STATUS_VARIANTS: Record<string, StatusBadgeVariant> = {
  active: "success",
  inactive: "secondary",
  suspended: "warning",
  pending: "warning",
  archived: "outline",
};

export function entityStatusLabel(code: string | null | undefined): string {
  if (!code) return "—";
  return ENTITY_STATUS_LABELS_ES[code.toLowerCase()] ?? humanizeCode(code);
}

export function entityStatusVariant(
  code: string | null | undefined,
): StatusBadgeVariant {
  if (!code) return "outline";
  return ENTITY_STATUS_VARIANTS[code.toLowerCase()] ?? "outline";
}

// ---------------------------------------------------------------------------
// Audit log — actor type, entity type, and action codes.
//
// The backend writes raw ``domain.entity.verb`` action strings (English,
// snake_case) plus actor/entity-type codes. The platform audit-log explorer
// used to render these verbatim against Spanish chrome (P1-06a). These maps
// give each a plain-Spanish label; the raw code is kept as a tooltip for
// power users. The action humaniser splits on ``.`` and ``_`` so an
// unmapped/future code reads "Domain · entity verb" instead of raw.
// ---------------------------------------------------------------------------

export const AUDIT_ACTOR_TYPE_LABELS_ES: Record<string, string> = {
  // Role-model redesign (2026-06-23).
  operations_admin: "Administrador de operaciones",
  platform_admin: "Equipo CheckWise",
  client_admin: "Administrador del cliente",
  client_viewer: "Solo lectura",
  provider: "Proveedor",
  system: "Sistema",
  // Deprecated (legacy audit rows).
  internal_admin: "Equipo CheckWise",
  reviewer: "Equipo CheckWise",
};

export function auditActorTypeLabel(code: string | null | undefined): string {
  if (!code) return "—";
  return AUDIT_ACTOR_TYPE_LABELS_ES[code] ?? humanizeCode(code);
}

export const AUDIT_ENTITY_TYPE_LABELS_ES: Record<string, string> = {
  user: "Usuario",
  client: "Cliente",
  vendor: "Proveedor",
  submission: "Entrega",
  workspace: "Espacio de proveedor",
  provider_workspace: "Espacio de proveedor",
  requirement: "Requisito",
  report: "Reporte",
  system: "Sistema",
  notification_template: "Plantilla de notificación",
  contact_request: "Solicitud de contacto",
  feedback_report: "Reporte de feedback",
};

export function auditEntityTypeLabel(code: string | null | undefined): string {
  if (!code) return "—";
  return AUDIT_ENTITY_TYPE_LABELS_ES[code] ?? humanizeCode(code);
}

export const AUDIT_ACTION_LABELS_ES: Record<string, string> = {
  "admin.client.updated": "Cliente actualizado",
  "admin.contact_request.status_changed":
    "Estado de solicitud de contacto cambiado",
  "admin.feedback_report.status_changed":
    "Estado de reporte de feedback cambiado",
  "admin.notification_template.activated": "Plantilla de notificación activada",
  "admin.notification_template.created": "Plantilla de notificación creada",
  "admin.requirement.created": "Requisito creado",
  "admin.requirement.updated": "Requisito actualizado",
  "admin.user.deleted": "Usuario eliminado",
  "admin.user.identity_updated": "Identidad de usuario actualizada",
  "admin.user.membership_granted": "Membresía otorgada",
  "admin.user.membership_promoted": "Membresía promovida",
  "admin.user.membership_revoked": "Membresía revocada",
  "admin.user.provisioned": "Usuario creado",
  "admin.user.restored": "Usuario restaurado",
  "admin.user_password_reset": "Contraseña de usuario restablecida",
  "admin.vendor.created": "Proveedor creado",
  "admin.vendor.updated": "Proveedor actualizado",
  "admin.vendor_expediente_downloaded": "Expediente de proveedor descargado",
  "admin.workspace.updated": "Espacio de proveedor actualizado",
  "auth.login.failed": "Inicio de sesión fallido",
  "auth.login.succeeded": "Inicio de sesión exitoso",
  "auth.logout": "Cierre de sesión",
  "auth.password_changed": "Contraseña cambiada",
  "auth.password_reset_completed": "Restablecimiento de contraseña completado",
  "auth.password_reset_requested": "Restablecimiento de contraseña solicitado",
  "client.audit_package_downloaded": "Paquete de auditoría descargado",
  "client.document_downloaded": "Documento descargado",
  "client.legal_consent_accepted": "Consentimiento legal aceptado",
  "client.notification_marked_read": "Notificación marcada como leída",
  "client.notifications_marked_all_read":
    "Todas las notificaciones marcadas como leídas",
  "client.profile_updated": "Perfil actualizado",
  "client.provider_invited": "Proveedor invitado",
  "client.user_created": "Usuario de cliente creado",
  "client.user_password_reset": "Contraseña de usuario de cliente restablecida",
  "client.user_removed": "Usuario de cliente eliminado",
  "client.vendor_expediente_downloaded": "Expediente de proveedor descargado",
  "client.vendor_metadata_downloaded": "Metadata de proveedor descargada",
  "correction_request.submitted": "Solicitud de corrección enviada",
  "email.transactional_sent": "Correo transaccional enviado",
  "notification.dispatch_attempted": "Intento de envío de notificación",
  "notification.whatsapp_dispatched": "Notificación de WhatsApp enviada",
  "provider.document_downloaded": "Documento descargado",
  "provider.expediente_downloaded": "Expediente descargado",
  "provider.legal_consent_accepted": "Consentimiento legal aceptado",
  "provider.notification_marked_read": "Notificación marcada como leída",
  "provider.notifications_marked_all_read":
    "Todas las notificaciones marcadas como leídas",
  "provider.submission_cancelled": "Entrega cancelada",
  "report.share_minted": "Enlace de reporte generado",
  "report.share_revoked": "Enlace de reporte revocado",
  "reviewer.document_downloaded": "Documento descargado",
  "submission.created": "Entrega creada",
  "submission.replacement_linked": "Reemplazo de entrega vinculado",
  "submission.reviewer_decision": "Decisión de revisor",
  "submission.uploaded": "Entrega cargada",
  "system.auto_approved": "Aprobado automáticamente",
  "user.notification_preferences_updated":
    "Preferencias de notificación actualizadas",
  "user.phone_verification_confirmed": "Verificación de teléfono confirmada",
  "user.phone_verification_requested": "Verificación de teléfono solicitada",
  "whatsapp.transactional_sent": "WhatsApp transaccional enviado",
};

/** Humanise an unmapped audit action: ``domain.entity_verb`` →
 *  "Domain · entity verb" so a new server-side code never renders raw. */
function humanizeAuditAction(code: string): string {
  const [domain, ...rest] = code.split(".");
  const tail = rest.join(" ").replace(/[_.]+/g, " ").trim();
  const head = humanizeCode(domain);
  return tail ? `${head} · ${tail}` : head;
}

export function auditActionLabel(code: string | null | undefined): string {
  if (!code) return "—";
  return AUDIT_ACTION_LABELS_ES[code] ?? humanizeAuditAction(code);
}
