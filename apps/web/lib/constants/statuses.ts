/**
 * Frontend mirror of apps/api/app/constants/statuses.py.
 *
 * Keep the two in sync when adding or renaming a status. The backend is
 * the source of truth; this file exists so components and pages can
 * compare against a named constant instead of typing the raw string in
 * every conditional.
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

/** Plain-language Spanish labels shown in the provider UI. */
export const STATUS_LABELS_ES: Record<DocumentStatusCode, string> = {
  [DocumentStatus.PENDIENTE]: "Pendiente",
  [DocumentStatus.RECIBIDO]: "Recibido",
  [DocumentStatus.PENDIENTE_REVISION]: "Esperando revisión",
  [DocumentStatus.PREVALIDADO]: "Prevalidado",
  [DocumentStatus.POSIBLE_MISMATCH]: "Posible inconsistencia",
  [DocumentStatus.APROBADO]: "Aprobado",
  [DocumentStatus.RECHAZADO]: "Rechazado",
  [DocumentStatus.VENCIDO]: "Vencido",
  [DocumentStatus.NO_APLICA]: "No aplica",
  [DocumentStatus.REQUIERE_ACLARACION]: "Necesita aclaración",
  [DocumentStatus.EXCEPCION_LEGAL]: "Excepción legal",
};
