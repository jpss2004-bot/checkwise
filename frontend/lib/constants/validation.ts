/**
 * Plain-Spanish labels for the prevalidation rule codes emitted by
 * ``backend/app/services/prevalidation.py``.
 *
 * Backend rationale: every ``ValidationSignal`` carries both a
 * machine-readable ``rule_code`` (engineer dialect — ``file_exists``,
 * ``allowed_file_type``, etc.) and a user-facing ``message`` already
 * written in Spanish. Until BL-003 (2026-05-20) the frontend rendered
 * the ``rule_code`` as the primary label of each row in the validation
 * summary, exposing non-technical providers to identifiers they were
 * never meant to see ("file_exists", "pdf_magic_header"). That is the
 * exact pain the tester (jluna@legalshelf.mx) called out on the
 * /portal/upload surface in the 11:28 AM Slack feedback.
 *
 * This map produces the human title. The backend ``message`` stays as
 * the supporting sentence under the title. The raw ``rule_code``
 * still travels with the signal so QA tooling and reviewers can match
 * a UI row to a backend assertion via the tooltip / aria-label, but
 * it is no longer the primary label.
 *
 * Keep this map in sync with ``prevalidation.py``: every code emitted
 * there must have an entry here. The default fallback (``label`` =
 * the code itself) is a safety net for codes added in the future
 * before this map is updated — it is intentionally ugly so a missing
 * entry stands out in QA.
 */

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

export const VALIDATION_RULE_LABELS_ES: Record<ValidationRuleCode, string> = {
  file_exists: "Archivo recibido",
  allowed_file_type: "Tipo de archivo permitido",
  pdf_magic_header: "Estructura PDF válida",
  pdf_encrypted: "PDF sin contraseña",
  pdf_readable_text: "Texto legible",
  max_file_size: "Tamaño dentro del límite",
  sha256_hash: "Huella de integridad",
  duplicate_hash: "Sin duplicados",
  vendor_match: "RFC del proveedor coincide",
  period_match: "Periodo coincide",
  requirement_match: "Cumple con el requisito",
  document_intelligence: "Señales de calidad del documento",
  human_review_required: "Requiere revisión humana",
};

/**
 * Look up the friendly label, falling back to the raw code so a
 * forgotten entry is immediately visible in QA instead of silently
 * vanishing.
 */
export function validationLabel(ruleCode: string): string {
  return (
    VALIDATION_RULE_LABELS_ES[ruleCode as ValidationRuleCode] ?? ruleCode
  );
}
