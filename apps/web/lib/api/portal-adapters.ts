/**
 * Legacy adapters that map real backend payloads to older UI-friendly
 * mock shapes. `/portal/onboarding` now consumes the enriched backend
 * response directly; the onboarding adapter is retained only for older
 * callers/tests and prefers backend-owned copy when present.
 */

import { MOCK_EXPEDIENTE, type ExpedienteRequirement } from "@/lib/mock/expediente";
import {
  MONTH_LABELS,
  type CalendarEvent,
  type CalendarInstitution as MockCalendarInstitution,
} from "@/lib/mock/calendar";
import {
  statusToDocumentStateCode,
  type CalendarPayload,
  type OnboardingItem,
  type OnboardingSummary,
  type RequirementStatus,
} from "@/lib/api/portal";

// The backend-status → UI DocumentStateCode mapping lives in portal.ts
// (statusToDocumentStateCode). This module used to re-declare an
// identical copy (statusToCode); removed to keep one source of truth
// (Audit F2).

// ──────────────────────────────────────────────────────────────────
// Onboarding adapter
// ──────────────────────────────────────────────────────────────────

/**
 * Fallback enrichment keyed by requirement_code, derived from the
 * original mock. The backend owns these fields now; this dictionary is
 * only a backward-compatibility fallback.
 */
const ENRICHMENT_BY_CODE: Record<
  string,
  Pick<ExpedienteRequirement, "why" | "format" | "next_action" | "reviewer_note">
> = (() => {
  const dict: Record<
    string,
    Pick<ExpedienteRequirement, "why" | "format" | "next_action" | "reviewer_note">
  > = {};
  for (const r of MOCK_EXPEDIENTE) {
    if (!r.requirement_code) continue;
    dict[r.requirement_code] = {
      why: r.why,
      format: r.format,
      next_action: r.next_action,
      reviewer_note: r.reviewer_note,
    };
  }
  return dict;
})();

const DEFAULT_ENRICHMENT: Pick<
  ExpedienteRequirement,
  "why" | "format" | "next_action"
> = {
  why: "Este documento forma parte de tu expediente REPSE.",
  format: "PDF · documento oficial vigente",
  next_action: "Sube el documento desde el wizard.",
};

const INSTITUTION_FROM_BACKEND: Record<
  string,
  ExpedienteRequirement["institution"]
> = {
  sat: "sat",
  imss: "imss",
  infonavit: "infonavit",
  stps_repse: "stps_repse",
  interno_cliente: "interno_cliente",
};

/**
 * Flatten the backend OnboardingSummary into the mock shape the
 * existing /portal/onboarding UI consumes.
 */
export function adaptOnboardingToRequirements(
  summary: OnboardingSummary,
): ExpedienteRequirement[] {
  const out: ExpedienteRequirement[] = [];
  for (const section of summary.sections) {
    for (const item of section.items) {
      const enrichment = ENRICHMENT_BY_CODE[item.code] ?? DEFAULT_ENRICHMENT;
      out.push(adaptOnboardingItem(item, enrichment));
    }
  }
  return out;
}

function adaptOnboardingItem(
  item: OnboardingItem,
  enrichment: Pick<
    ExpedienteRequirement,
    "why" | "format" | "next_action" | "reviewer_note"
  >,
): ExpedienteRequirement {
  return {
    id: item.code.toLowerCase(),
    requirement_code: item.code,
    name: item.name,
    institution: INSTITUTION_FROM_BACKEND[item.institution] ?? "interno_cliente",
    why: item.why || enrichment.why,
    format: item.format || enrichment.format,
    state: statusToDocumentStateCode(item.status),
    next_action: item.next_action || item.note || enrichment.next_action,
    reviewer_note: item.reviewer_note ?? enrichment.reviewer_note,
    required: item.required,
    filename: item.filename ?? null,
  };
}

// ──────────────────────────────────────────────────────────────────
// Calendar adapter
// ──────────────────────────────────────────────────────────────────

const FREQ_MAP: Record<string, CalendarEvent["frequency"]> = {
  mensual: "monthly",
  bimestral: "bimonthly",
  cuatrimestral: "four_monthly",
  anual: "annual",
};

const CALENDAR_INSTITUTION_FROM_BACKEND: Record<string, MockCalendarInstitution> = {
  sat: "sat",
  imss: "imss",
  infonavit: "infonavit",
  stps_repse: "stps_repse",
};

/**
 * Flatten the backend CalendarPayload into the mock CalendarEvent[]
 * shape. Each backend per-month-per-institution-per-item becomes one
 * CalendarEvent with computed deadline.
 */
export function adaptCalendarToEvents(payload: CalendarPayload): CalendarEvent[] {
  const out: CalendarEvent[] = [];
  for (const month of payload.months) {
    for (const inst of month.institutions) {
      const institution = CALENDAR_INSTITUTION_FROM_BACKEND[inst.institution];
      if (!institution) continue;
      for (const item of inst.items) {
        out.push({
          id: `${institution}-${payload.year}-${month.month}-${item.code}`,
          year: payload.year,
          month: month.month,
          institution,
          obligation: item.name,
          required_document: item.name,
          deadline_iso: `${payload.year}-${String(month.month).padStart(2, "0")}-17`,
          state: statusToDocumentStateCode(item.status),
          suggested_action: defaultActionFor(item.status),
          frequency: FREQ_MAP[item.frequency] ?? "monthly",
        });
      }
    }
  }
  return out;
}

function defaultActionFor(status: RequirementStatus): string {
  switch (status) {
    case "aprobado":
    case "excepcion_legal":
    case "no_aplica":
      return "Aprobado. Sin acción inmediata.";
    case "pendiente_revision":
    case "prevalidado":
    case "recibido":
      return "Documento en revisión humana. Te avisaremos por correo.";
    case "rechazado":
      return "Sube una versión corregida desde el wizard.";
    case "vencido":
      return "Documento vencido. Sube la versión vigente.";
    case "posible_mismatch":
    case "requiere_aclaracion":
      return "Revisa la observación y resube si es necesario.";
    default:
      return "Sube este documento desde el wizard.";
  }
}

// ──────────────────────────────────────────────────────────────────
// Counts (compatible with mock countExpediente shape)
// ──────────────────────────────────────────────────────────────────

export interface ExpedienteCounts {
  total_required: number;
  completed: number;
  in_review: number;
  needs_action: number;
  optional_pending: number;
  completion_pct: number;
  is_gate_satisfied: boolean;
}

/**
 * Count requirements by state. Matches the shape of
 * `lib/mock/expediente.countExpediente` exactly.
 */
export function countRealExpediente(reqs: ExpedienteRequirement[]): ExpedienteCounts {
  const required = reqs.filter((r) => r.required);
  const total_required = required.length;
  const completed = required.filter((r) => r.state === "approved").length;
  const in_review = required.filter((r) =>
    ["uploaded", "in_review"].includes(r.state),
  ).length;
  const needs_action = required.filter((r) =>
    ["pending", "empty", "rejected", "expired", "needs_review"].includes(r.state),
  ).length;
  const optional_pending = reqs.filter(
    (r) => !r.required && r.state !== "approved",
  ).length;
  const completion_pct =
    total_required === 0
      ? 100
      : Math.round(((completed + in_review) / total_required) * 100);
  const is_gate_satisfied = needs_action === 0;
  return {
    total_required,
    completed,
    in_review,
    needs_action,
    optional_pending,
    completion_pct,
    is_gate_satisfied,
  };
}

// keep MONTH_LABELS in scope (so future adapter additions can use it)
void MONTH_LABELS;
