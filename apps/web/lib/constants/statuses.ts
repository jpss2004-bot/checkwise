/**
 * Frontend mirror of apps/api/app/constants/statuses.py.
 *
 * Keep the two in sync when adding or renaming a status. The backend is
 * the source of truth for the enum values; this file is the source of
 * truth for the user-facing Spanish labels rendered everywhere a status
 * appears (portal badges, calendar dots, admin reviewer queue, client
 * dashboard, generated reports).
 *
 * Vocabulary pass (2026-06-02):
 *   - ``Prevalidado`` is the most jargony status in the catalog — it
 *     reads as engineer dialect to providers who don't know what was
 *     "pre"-validated. Renamed to ``Recibido — esperando revisión`` so
 *     the label matches what's actually true: we accepted the file, a
 *     human will look at it.
 *   - ``Excepción legal`` reads as a legal sanction rather than the
 *     positive outcome it actually is (approval under a documented
 *     legal exception). Renamed to ``Aprobado con nota legal``.
 *   - Every other label stayed: ``Posible inconsistencia``,
 *     ``Necesita aclaración``, ``Vencido``, ``No aplica`` are already
 *     in plain Spanish and tested through the provider feedback loop.
 */

export const DocumentStatus = {
  PENDIENTE: "pendiente",
  RECIBIDO: "recibido",
  PENDIENTE_REVISION: "pendiente_revision",
  PREVALIDADO: "prevalidado",
  POSIBLE_MISMATCH: "posible_mismatch",
  APROBADO: "aprobado",
  RECHAZADO: "rechazado",
  VENCIDO: "vencido",
  NO_APLICA: "no_aplica",
  REQUIERE_ACLARACION: "requiere_aclaracion",
  EXCEPCION_LEGAL: "excepcion_legal",
} as const;

export type DocumentStatusCode = (typeof DocumentStatus)[keyof typeof DocumentStatus];

export const ReviewerAction = {
  APPROVE: "approve",
  REJECT: "reject",
  REQUEST_CLARIFICATION: "request_clarification",
  MARK_EXCEPTION: "mark_exception",
} as const;

export type ReviewerActionCode = (typeof ReviewerAction)[keyof typeof ReviewerAction];

/** Statuses that mean "the provider must take action now." */
export const ACTIONABLE_STATUSES: readonly DocumentStatusCode[] = [
  DocumentStatus.RECHAZADO,
  DocumentStatus.VENCIDO,
  DocumentStatus.POSIBLE_MISMATCH,
  DocumentStatus.REQUIERE_ACLARACION,
];

/** Statuses that resolve a slot (terminal until a new submission arrives). */
export const RESOLVED_STATUSES: readonly DocumentStatusCode[] = [
  DocumentStatus.APROBADO,
  DocumentStatus.EXCEPCION_LEGAL,
  DocumentStatus.NO_APLICA,
];

/**
 * Plain-language Spanish labels shown in the user UI.
 *
 * Note on ``rechazado``: the backend status code is literally
 * "rechazado" but the user-facing label is the softer
 * "Requiere corrección" so the badge invites the provider to act
 * rather than feel rejected (Audit P1-02, 2026-05-25). The backend
 * code never changes; only the display string is softened.
 */
export const STATUS_LABELS_ES: Record<DocumentStatusCode, string> = {
  [DocumentStatus.PENDIENTE]: "Pendiente",
  // Collapsed (2026-06-10): a just-received document and one actively in
  // the reviewer queue read the same to a client — both "En revisión".
  [DocumentStatus.RECIBIDO]: "En revisión",
  [DocumentStatus.PENDIENTE_REVISION]: "En revisión",
  [DocumentStatus.PREVALIDADO]: "En revisión",
  [DocumentStatus.POSIBLE_MISMATCH]: "Posible inconsistencia",
  [DocumentStatus.APROBADO]: "Aprobado",
  [DocumentStatus.RECHAZADO]: "Requiere corrección",
  [DocumentStatus.VENCIDO]: "Vencido",
  [DocumentStatus.NO_APLICA]: "No aplica",
  [DocumentStatus.REQUIERE_ACLARACION]: "Necesita aclaración",
  [DocumentStatus.EXCEPCION_LEGAL]: "Aprobado con nota legal",
};

/** Badge color tones used for status surfaces across the client portal. */
export type StatusVariant =
  | "success"
  | "warning"
  | "info"
  | "destructive"
  | "secondary";

/**
 * Status → Badge color "variant". Centralized (Audit F2, 2026-06-09) so
 * the client-portal surfaces (dashboard pill, submissions table, calendar
 * dots) can't drift apart when a status is added or its tone changes.
 *
 * The tone reconciles the three pre-existing per-page maps toward the
 * dashboard's mapping: the in-review-ish states (recibido /
 * pendiente_revision / prevalidado) read as ``info``; ``excepcion_legal``
 * is a positive outcome so it shares ``aprobado``'s ``success``;
 * ``no_aplica`` is a neutral non-event (``secondary``).
 */
export const STATUS_VARIANT: Record<DocumentStatusCode, StatusVariant> = {
  [DocumentStatus.PENDIENTE]: "secondary",
  [DocumentStatus.RECIBIDO]: "info",
  [DocumentStatus.PENDIENTE_REVISION]: "info",
  [DocumentStatus.PREVALIDADO]: "info",
  [DocumentStatus.POSIBLE_MISMATCH]: "warning",
  [DocumentStatus.APROBADO]: "success",
  [DocumentStatus.RECHAZADO]: "destructive",
  [DocumentStatus.VENCIDO]: "destructive",
  [DocumentStatus.NO_APLICA]: "secondary",
  [DocumentStatus.REQUIERE_ACLARACION]: "warning",
  [DocumentStatus.EXCEPCION_LEGAL]: "success",
};

/**
 * Convenience accessor that always returns a variant. Falls back to
 * ``secondary`` for a status code that's been added to the backend but
 * not yet mirrored here — matching the per-page fallbacks this replaced.
 */
export function statusVariant(status: string): StatusVariant {
  return STATUS_VARIANT[status as DocumentStatusCode] ?? "secondary";
}

/**
 * One-line plain-Spanish explainer per status, rendered beneath the
 * status badge on the submission detail hero so the provider never has
 * to guess what a label means. Kept short (under ~80 chars) so it fits
 * on a single line at mobile widths.
 *
 * These are intentionally written from the provider's perspective —
 * what does this status mean for ME and what should I do next.
 */
export const STATUS_EXPLAINER_ES: Record<DocumentStatusCode, string> = {
  [DocumentStatus.PENDIENTE]: "Aún no has subido este documento.",
  [DocumentStatus.RECIBIDO]: "Recibimos tu archivo. Lo vamos a revisar.",
  [DocumentStatus.PENDIENTE_REVISION]: "Está en cola para revisión humana.",
  [DocumentStatus.PREVALIDADO]: "Pasó las primeras revisiones. Un humano lo revisará pronto.",
  [DocumentStatus.POSIBLE_MISMATCH]: "Detectamos algo que podría no coincidir. Lo revisará el equipo legal.",
  [DocumentStatus.APROBADO]: "El equipo legal lo aprobó. No tienes nada más que hacer.",
  [DocumentStatus.RECHAZADO]: "El equipo legal lo rechazó. Necesitas subir uno nuevo.",
  [DocumentStatus.VENCIDO]: "Ya no cubre el periodo vigente. Sube la versión actualizada.",
  [DocumentStatus.NO_APLICA]: "Este requisito no aplica para tu caso.",
  [DocumentStatus.REQUIERE_ACLARACION]: "El equipo legal necesita más información. Lee la nota y responde.",
  [DocumentStatus.EXCEPCION_LEGAL]: "Aprobado bajo nota legal. Conserva el sustento en tu expediente.",
};

/**
 * Convenience accessor that always returns a string. Use this when the
 * caller may receive a status code that's been added to the backend
 * but not yet mirrored here — falling back to the raw code keeps the
 * UI rendering instead of crashing, while making the gap obvious.
 */
export function statusLabel(status: string): string {
  return STATUS_LABELS_ES[status as DocumentStatusCode] ?? status;
}

export function statusExplainer(status: string): string | null {
  return STATUS_EXPLAINER_ES[status as DocumentStatusCode] ?? null;
}

// ===========================================================================
// Canonical vocabulary unification (2026-06-10).
//
// Before this, the client portal carried FIVE parallel status vocabularies
// (DocumentStatus, SlotState, the doc-state badge, the semáforo, and the
// requirement-count "buckets"), and each screen re-labeled the same concept
// with different Spanish words — "Prevalidado"/"En revisión"/"Esperando
// revisión" for one document, "Verde"/"En regla"/"al día" for one semáforo
// level, etc. The maps below are the single source of truth for the three
// axes that previously lived as inline per-page maps. Shared concepts are
// worded IDENTICALLY to STATUS_LABELS_ES above (e.g. rejected →
// "Requiere corrección", in-review → "En revisión") so a status reads the
// same on the calendar, Entregas, Reportes, dashboard and vendor surfaces.
// ===========================================================================

// ---------------------------------------------------------------------------
// Semáforo — portfolio / vendor health (backend ``semaphore_level``).
// Canonical labels ratified 2026-06-10: Al día / En proceso / En riesgo.
// ---------------------------------------------------------------------------

export type SemaphoreLevel = "green" | "yellow" | "red";

export const SEMAPHORE_LABELS_ES: Record<SemaphoreLevel, string> = {
  green: "Al día",
  yellow: "En proceso",
  red: "En riesgo",
};

export const SEMAPHORE_VARIANT: Record<SemaphoreLevel, StatusVariant> = {
  green: "success",
  yellow: "warning",
  red: "destructive",
};

export function semaphoreLabel(level: string): string {
  return SEMAPHORE_LABELS_ES[level as SemaphoreLevel] ?? level;
}

export function semaphoreVariant(level: string): StatusVariant {
  return SEMAPHORE_VARIANT[level as SemaphoreLevel] ?? "secondary";
}

// ---------------------------------------------------------------------------
// SlotState — the coarse UI projection of DocumentStatus the backend emits
// for report blocks and the provider expediente grid (apps/api
// /app/services/evidence_slots.py :: SlotState). Item-level badge labels.
// Words match STATUS_LABELS_ES for every shared concept.
// ---------------------------------------------------------------------------

export const SlotState = {
  MISSING: "missing",
  UPLOADED: "uploaded",
  IN_REVIEW: "in_review",
  POSSIBLE_MISMATCH: "possible_mismatch",
  APPROVED: "approved",
  REJECTED: "rejected",
  NEEDS_CORRECTION: "needs_correction",
  EXCEPTION: "exception",
  EXPIRED: "expired",
  NOT_APPLICABLE: "not_applicable",
} as const;

export type SlotStateCode = (typeof SlotState)[keyof typeof SlotState];

export const SLOT_STATE_LABELS_ES: Record<SlotStateCode, string> = {
  [SlotState.MISSING]: "Por entregar",
  // Collapsed with IN_REVIEW (2026-06-10): both read "En revisión".
  [SlotState.UPLOADED]: "En revisión",
  [SlotState.IN_REVIEW]: "En revisión",
  [SlotState.POSSIBLE_MISMATCH]: "Posible inconsistencia",
  [SlotState.APPROVED]: "Aprobado",
  [SlotState.REJECTED]: "Requiere corrección",
  [SlotState.NEEDS_CORRECTION]: "Necesita aclaración",
  [SlotState.EXCEPTION]: "Aprobado con nota legal",
  [SlotState.EXPIRED]: "Vencido",
  [SlotState.NOT_APPLICABLE]: "No aplica",
};

export const SLOT_STATE_VARIANT: Record<SlotStateCode, StatusVariant> = {
  [SlotState.MISSING]: "secondary",
  [SlotState.UPLOADED]: "info",
  [SlotState.IN_REVIEW]: "info",
  [SlotState.POSSIBLE_MISMATCH]: "warning",
  [SlotState.APPROVED]: "success",
  [SlotState.REJECTED]: "destructive",
  [SlotState.NEEDS_CORRECTION]: "warning",
  [SlotState.EXCEPTION]: "success",
  [SlotState.EXPIRED]: "destructive",
  [SlotState.NOT_APPLICABLE]: "secondary",
};

export function slotStateLabel(state: string): string {
  return SLOT_STATE_LABELS_ES[state as SlotStateCode] ?? state;
}

export function slotStateVariant(state: string): StatusVariant {
  return SLOT_STATE_VARIANT[state as SlotStateCode] ?? "secondary";
}

// ---------------------------------------------------------------------------
// Requirement "buckets" — the count KPIs the client API returns
// (missing_required / rejected_or_correction / pending_reviews / due_soon).
// Count-level wording (a column header / KPI tile), distinct from the
// item-level badge above: a single missing document reads "Por entregar",
// but the portfolio count of them reads "Faltantes".
// ---------------------------------------------------------------------------

export type BucketKey =
  | "missing_required"
  | "rejected_or_correction"
  | "pending_reviews"
  | "due_soon";

export const BUCKET_LABELS_ES: Record<BucketKey, string> = {
  missing_required: "Faltantes",
  rejected_or_correction: "Por corregir",
  pending_reviews: "En revisión",
  due_soon: "Por vencer",
};

export const BUCKET_VARIANT: Record<BucketKey, StatusVariant> = {
  missing_required: "warning",
  rejected_or_correction: "destructive",
  pending_reviews: "info",
  due_soon: "warning",
};

export function bucketLabel(key: BucketKey): string {
  return BUCKET_LABELS_ES[key];
}
