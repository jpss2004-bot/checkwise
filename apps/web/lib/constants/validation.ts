/**
 * Plain-Spanish labels for the prevalidation rule codes emitted by
 * ``apps/api/app/services/prevalidation.py``.
 *
 * Vocabulary pass (2026-06-02):
 *   - The provider portal no longer renders one row per rule_code. It
 *     uses ``groupValidations`` below to fold every signal into three
 *     grouped outcomes a non-technical provider can act on. The map
 *     of per-rule labels (VALIDATION_RULE_LABELS_ES) stays around for
 *     reviewer/admin diagnostic surfaces and for the "Datos técnicos"
 *     expandables in the admin UI.
 *   - Reworded entries for less jargon: ``sha256_hash`` no longer
 *     reads as "Huella de integridad" (cryptography dialect);
 *     ``document_intelligence`` no longer reads as "Verificación
 *     automática del documento" (mechanism-not-outcome). Both stay
 *     in the dictionary for admin diagnostic use only.
 */

import type { ValidationSignal } from "@/components/checkwise/validation-summary";

export type ValidationRuleCode =
  | "file_exists"
  | "allowed_file_type"
  | "pdf_magic_header"
  | "pdf_encrypted"
  | "pdf_readable_text"
  | "max_file_size"
  | "sha256_hash"
  | "duplicate_hash"
  | "vendor_match"
  | "period_match"
  | "requirement_match"
  | "document_intelligence"
  | "human_review_required";

/**
 * Per-rule labels. Kept for reviewer surfaces + the QA tooltip on the
 * grouped summary rows. NOT shown to providers as headline labels
 * anymore — use ``groupValidations`` for the provider view.
 */
export const VALIDATION_RULE_LABELS_ES: Record<ValidationRuleCode, string> = {
  file_exists: "Archivo recibido",
  allowed_file_type: "Tipo de archivo permitido",
  pdf_magic_header: "Estructura PDF válida",
  pdf_encrypted: "PDF sin contraseña",
  pdf_readable_text: "Texto legible",
  max_file_size: "Tamaño dentro del límite",
  sha256_hash: "Verificación de integridad",
  duplicate_hash: "Sin duplicados",
  vendor_match: "RFC del proveedor coincide",
  period_match: "Periodo coincide",
  requirement_match: "Coincide con el requisito",
  document_intelligence: "Lectura del documento",
  human_review_required: "Requiere revisión humana",
};

export function validationLabel(ruleCode: string): string {
  return (
    VALIDATION_RULE_LABELS_ES[ruleCode as ValidationRuleCode] ?? ruleCode
  );
}

// ─────────────────────────────────────────────────────────────────────
// Grouped provider-facing summary
// ─────────────────────────────────────────────────────────────────────
//
// Providers don't think in terms of N validation rules. They think:
//   1. "Did my file go through?"
//   2. "Is it the document they actually want?"
//   3. "What happens next?"
//
// The grouper below maps every backend rule_code into one of three
// grouped outcomes that answer those questions. Each group has a
// status (ok / warning / failure / pending) derived from the worst
// signal in the group, plus an optional explanation sentence sourced
// from the actual ``message`` on the failing signal.

export type GroupedValidationState = "ok" | "warning" | "failure" | "pending";

export type GroupedValidationOutcome = {
  /** Stable id used by tests and analytics events. */
  id: "file_received" | "matches_requirement" | "next_step";
  /** Headline shown to the provider. */
  title: string;
  /** State pill / icon driver. */
  state: GroupedValidationState;
  /** Optional sub-line shown on warning/failure with the specific issue. */
  detail: string | null;
  /** Underlying rule_codes folded into this group (for QA tooltips). */
  ruleCodes: string[];
};

/**
 * Rules that report on "did the file come through cleanly". Provider
 * cares about the outcome (yes / no with a reason), not which of the
 * 8 individual file-format checks fired.
 */
const FILE_RULES = new Set<string>([
  "file_exists",
  "allowed_file_type",
  "max_file_size",
  "pdf_magic_header",
  "pdf_encrypted",
  "pdf_readable_text",
  "sha256_hash",
  "duplicate_hash",
]);

/**
 * Rules that report on "does the document match what was asked for".
 * This is where the AI / classifier signals land.
 */
const MATCH_RULES = new Set<string>([
  "vendor_match",
  "period_match",
  "requirement_match",
  "document_intelligence",
]);

/**
 * Rules that report on "what happens next" — human review required.
 */
const NEXT_STEP_RULES = new Set<string>([
  "human_review_required",
]);

function worstState(
  current: GroupedValidationState,
  incoming: GroupedValidationState,
): GroupedValidationState {
  const order: GroupedValidationState[] = ["ok", "pending", "warning", "failure"];
  return order.indexOf(incoming) > order.indexOf(current) ? incoming : current;
}

function stateFromSignal(signal: { result: string; severity: string }): GroupedValidationState {
  if (signal.severity === "error" || signal.result === "fail") return "failure";
  if (signal.severity === "warning" || signal.result === "warning") return "warning";
  if (signal.result === "pending") return "pending";
  return "ok";
}

function firstActionableMessage(
  signals: ValidationSignal[],
): string | null {
  // Prefer error/warning messages over OK ones — the detail line is
  // there to explain a problem, not to congratulate the user.
  const escalated = signals.filter(
    (s) => s.severity === "error" || s.severity === "warning" || s.result === "fail" || s.result === "warning",
  );
  if (escalated.length === 0) return null;
  return escalated[0].message ?? null;
}

/**
 * Fold N raw validation signals into three grouped outcomes for the
 * provider summary.
 *
 * The returned array always has exactly three entries in this order:
 *   1. file_received       — Did we receive the file correctly?
 *   2. matches_requirement — Does it look like the right document?
 *   3. next_step           — What happens now?
 *
 * Each group's ``state`` is the worst state of any signal in it
 * (failure > warning > pending > ok). Each group's ``detail`` is the
 * first error/warning message in that group, or null when everything
 * passed.
 */
export function groupValidations(
  signals: ValidationSignal[],
): GroupedValidationOutcome[] {
  const fileSignals = signals.filter((s) => FILE_RULES.has(s.rule_code));
  const matchSignals = signals.filter((s) => MATCH_RULES.has(s.rule_code));
  const nextSignals = signals.filter((s) => NEXT_STEP_RULES.has(s.rule_code));

  const fileState = fileSignals.reduce<GroupedValidationState>(
    (acc, s) => worstState(acc, stateFromSignal(s)),
    "ok",
  );
  const matchState = matchSignals.reduce<GroupedValidationState>(
    (acc, s) => worstState(acc, stateFromSignal(s)),
    "ok",
  );

  // The "next step" group is informational only. It's always rendered
  // as ``ok`` (a positive checkmark on "a human will review") unless
  // the backend explicitly told us human review is REQUIRED — in which
  // case the headline shifts to "Un humano lo revisará y te avisamos"
  // with the same OK state (it's not a failure; it's the expected flow).
  const humanReviewRequired = nextSignals.some(
    (s) => s.requires_human_review || s.result === "required",
  );

  const fileTitleByState: Record<GroupedValidationState, string> = {
    ok: "Recibimos el archivo correctamente",
    pending: "Procesando el archivo",
    warning: "Recibimos el archivo, pero detectamos algo",
    failure: "No pudimos procesar el archivo",
  };

  const matchTitleByState: Record<GroupedValidationState, string> = {
    ok: "Parece coincidir con lo que pediste",
    pending: "Revisando si coincide con el requisito",
    warning: "Podría no coincidir con el requisito",
    failure: "No coincide con el requisito esperado",
  };

  return [
    {
      id: "file_received",
      title: fileTitleByState[fileState],
      state: fileState,
      detail: fileState === "ok" ? null : firstActionableMessage(fileSignals),
      ruleCodes: fileSignals.map((s) => s.rule_code),
    },
    {
      id: "matches_requirement",
      title: matchTitleByState[matchState],
      state: matchState,
      detail: matchState === "ok" ? null : firstActionableMessage(matchSignals),
      ruleCodes: matchSignals.map((s) => s.rule_code),
    },
    {
      id: "next_step",
      title: humanReviewRequired
        ? "Un humano lo revisará y te avisamos"
        : "Un humano lo revisará si hace falta",
      state: "ok",
      detail: null,
      ruleCodes: nextSignals.map((s) => s.rule_code),
    },
  ];
}
