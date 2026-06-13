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
  internal_admin: "Administrador interno",
  platform_admin: "Administrador de plataforma",
  reviewer: "Revisor",
  client_admin: "Administrador de cliente",
  provider: "Proveedor",
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
