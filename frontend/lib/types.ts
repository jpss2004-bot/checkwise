/**
 * Shared frontend types. Centralized so components, pages, and API
 * clients all reference the same shape.
 *
 * Spec: docs/DESIGN_SYSTEM.md §5 (Type Centralization)
 */

/**
 * Canonical REPSE document state vocabulary. Mirrors the backend's
 * DocumentStatus StrEnum, with the additional product-level states
 * that exist only on the frontend (e.g. `empty` slot for a missing
 * required document).
 */
export type DocumentStateCode =
  | "empty"
  | "pending"
  | "uploaded"
  | "in_review"
  | "approved"
  | "rejected"
  | "expired"
  | "needs_review";

/**
 * AI/OCR confidence buckets for extracted metadata. Maps to the four
 * confidence levels documented in DESIGN_SYSTEM.md §6.5.
 */
export type ConfidenceLevel = "high" | "medium" | "low" | "none";

/**
 * Validation signal result. Used by ValidationSummary,
 * PrevalidationStep, and DocumentSubmissionForm.
 */
export type ValidationResult = "valid" | "warning" | "error" | "pending";

/**
 * Two top-level document groupings in the compliance workflow.
 * - expediente_inicial: one-time corporate file (constancia, REPSE, etc.)
 * - cumplimiento_repse: recurring compliance (SAT/IMSS/INFONAVIT/Acuses)
 */
export type DocumentGroup = "expediente_inicial" | "cumplimiento_repse";

/**
 * Priority for suggested actions in the dashboard's "Sugerencias" panel.
 */
export type ActionPriority = "high" | "medium" | "low";

/**
 * Suggested action shown in the dashboard.
 */
export interface SuggestedAction {
  id: string;
  title: string;
  description: string;
  priority: ActionPriority;
  cta_label: string;
  cta_href: string;
  status_badge?: DocumentStateCode;
  deadline_iso?: string;
}
