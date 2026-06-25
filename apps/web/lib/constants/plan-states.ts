/**
 * Phase C — shared copy + labels for the tiered-access / demo UX.
 * Central dicts so the plan UI reads consistently (the backend supplies the
 * human ``plan_label``; these cover the FE-only strings).
 */

/** Where a "Contactar a CheckWise" CTA points (upgrade / sales). */
export const PLAN_CONTACT_HREF = "/contacto";

/** Upsell shown when a capability the plan lacks is attempted. */
export const PLAN_UPSELL_COPY =
  "Esta función requiere un plan superior. Contacta a tu ejecutivo de CheckWise.";

/** Spanish labels for the capability keys returned by GET /client/plan. */
export const PLAN_CAPABILITY_LABELS: Record<string, string> = {
  export_audit_package: "Exportar paquete de auditoría",
  bulk_export: "Exportación masiva",
  download_documents: "Descargar documentos",
};
