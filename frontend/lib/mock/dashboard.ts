/**
 * MOCK dashboard data.
 *
 * Suggested actions, semaphore tone, and "what needs my attention
 * today" rows. Replaced when the backend exposes the equivalent
 * aggregates per provider.
 *
 * TODO[backend-integration]: Swap for /api/v1/portal/dashboard
 * once it exposes suggested actions + semaphore aggregates.
 */

import type { SuggestedAction, DocumentStateCode } from "@/lib/types";

/**
 * Semaphore tone — drives the big hero gauge on the dashboard.
 *
 * green  → no actionable items, everything is clean
 * yellow → some attention items but nothing blocking
 * red    → at least one overdue / rejected / expired blocker
 */
export type SemaphoreTone = "green" | "yellow" | "red";

export interface DashboardSemaphore {
  tone: SemaphoreTone;
  headline: string;
  /** Plain-language explanation of the tone. */
  description: string;
  /** 0–100. */
  compliance_pct: number;
  /** Total count of "currently being tracked" obligations. */
  total_tracked: number;
  /** Count of obligations completed in the current period. */
  on_track: number;
}

export const MOCK_SEMAPHORE: DashboardSemaphore = {
  tone: "yellow",
  headline: "Cumplimiento estable, con 2 puntos por atender",
  description:
    "Tu expediente está activo y la mayoría de tus obligaciones están al día. Atiende los pendientes esta semana para evitar que pasen a rojo.",
  compliance_pct: 78,
  total_tracked: 14,
  on_track: 11,
};

/**
 * Suggested actions — the dashboard's "what should I do next" panel.
 * Ordered by priority then by deadline.
 */
export const MOCK_SUGGESTED_ACTIONS: SuggestedAction[] = [
  {
    id: "sat-iva-mayo",
    title: "Sube tu Opinión de Cumplimiento SAT de mayo",
    description:
      "Vence en 5 días. Descárgala desde el portal del SAT y súbela en PDF.",
    priority: "high",
    cta_label: "Subir documento",
    cta_href: "/portal/upload?requirement_code=REQ-MON-001&period_key=2026-M05",
    status_badge: "pending",
    deadline_iso: "2026-05-19",
  },
  {
    id: "icsoe-vence",
    title: "Tu acuse ICSOE vence pronto",
    description:
      "El ICSOE del cuatrimestre Q2 vence en 12 días. Te recordamos antes para no llegar al filo.",
    priority: "medium",
    cta_label: "Ver detalle",
    cta_href: "/portal/dashboard",
    status_badge: "uploaded",
    deadline_iso: "2026-05-26",
  },
  {
    id: "rfc-rep-rechazado",
    title: "Corrige el documento rechazado: RFC del representante",
    description:
      "El revisor marcó que el archivo era del proveedor, no del representante legal.",
    priority: "high",
    cta_label: "Corregir",
    cta_href: "/portal/onboarding#rfc-rep",
    status_badge: "rejected",
  },
  {
    id: "patronal-needs-review",
    title: "Revisa el documento marcado como 'necesita revisión'",
    description:
      "Tu registro patronal podría no coincidir con tu razón social.",
    priority: "medium",
    cta_label: "Revisar",
    cta_href: "/portal/onboarding#patronal",
    status_badge: "needs_review",
  },
];

/**
 * "Necesita tu atención hoy" — short list of obligations due in the
 * next 7 days or already overdue.
 */
export interface AttentionRow {
  id: string;
  title: string;
  institution: string;
  due_in_days: number; // negative = overdue
  state: DocumentStateCode;
}

export const MOCK_ATTENTION_TODAY: AttentionRow[] = [
  {
    id: "sat-may",
    title: "Opinión de Cumplimiento SAT · mayo",
    institution: "SAT",
    due_in_days: 5,
    state: "pending",
  },
  {
    id: "imss-may",
    title: "Comp. de pago IMSS · mayo",
    institution: "IMSS",
    due_in_days: 3,
    state: "pending",
  },
  {
    id: "icsoe-q2",
    title: "Acuse ICSOE · cuatrimestre Q2",
    institution: "STPS",
    due_in_days: 12,
    state: "uploaded",
  },
];

/**
 * Document state counts shown in the dashboard summary chip row.
 * In production this comes from an aggregate query.
 */
export interface DocStateCounts {
  approved: number;
  in_review: number;
  uploaded: number;
  pending: number;
  rejected: number;
  expired: number;
  needs_review: number;
}

export const MOCK_DOC_STATE_COUNTS: DocStateCounts = {
  approved: 11,
  in_review: 1,
  uploaded: 1,
  pending: 2,
  rejected: 1,
  expired: 1,
  needs_review: 1,
};
