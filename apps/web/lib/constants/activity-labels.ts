/**
 * Spanish labels for the client Activity (audit-trail) feed.
 *
 * The /client/activity endpoint emits machine tokens for the actor
 * (``supplier`` / ``reviewer`` / ``system`` / ``client_admin`` / …) and
 * the action (``submission.uploaded`` / ``reviewer.decision`` / …). Those
 * are internal field values, not product copy — surfacing them verbatim
 * read as a leaked database column on the evidence surface a Legal
 * Director / Compliance Manager relies on (audit P2.13).
 *
 * These maps are the single source of truth for turning those tokens into
 * the calm Spanish the rest of the portal speaks. Locked by
 * ``activity-labels.test.ts`` so the vocabulary can't silently drift.
 */

export const ACTIVITY_ACTOR_LABELS_ES: Record<string, string> = {
  supplier: "Proveedor",
  reviewer: "Revisor",
  system: "Sistema",
  client_admin: "Cliente",
  internal_admin: "Equipo CheckWise",
};

export const ACTIVITY_ACTION_LABELS_ES: Record<string, string> = {
  "submission.uploaded": "Carga de documento",
  "reviewer.decision": "Decisión de revisión",
  "submission.replacement_linked": "Reemplazo vinculado",
  "submission.replaced": "Entrega reemplazada",
  "metadata.ready": "Metadata lista",
  "metadata.pending": "Metadata en proceso",
};

/** Title-case a raw dotted/underscored token as a last-resort fallback. */
function humanizeToken(raw: string): string {
  const cleaned = raw.replace(/[._]+/g, " ").trim();
  if (!cleaned) return raw;
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
}

export function activityActorLabel(raw: string): string {
  return ACTIVITY_ACTOR_LABELS_ES[raw] ?? humanizeToken(raw);
}

export function activityActionLabel(raw: string): string {
  return ACTIVITY_ACTION_LABELS_ES[raw] ?? humanizeToken(raw);
}
