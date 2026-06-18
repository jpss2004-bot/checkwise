// Client-portal calendar helpers. The portal-agnostic vocabulary (severity
// order, heatmap tones, date math) now lives in ./calendar-shared and is
// re-exported here so existing client imports keep working unchanged — there
// is exactly ONE definition of the calendar's colors and urgency math. Only
// the client-specific bits (status badges, the client's upload/chase next
// step, deep-link focus) are defined below.

import type { ClientCalendarItem, ClientCalendarRisk } from "@/lib/api/client";
import {
  DocumentStatus,
  SlotState,
  slotStateLabel,
  slotStateVariant,
  statusLabel,
  statusVariant,
} from "@/lib/constants/statuses";

import { RISK_ORDER } from "./calendar-shared";

export * from "./calendar-shared";

// Backwards-compatible alias — the client surfaces index by this name.
export const CLIENT_RISK_ORDER = RISK_ORDER;

/** Canonical status badge (label + tone) for one obligation. A still-empty
 *  required slot reads as "Por entregar" (MISSING) rather than the raw
 *  "pendiente" so the vocabulary matches the rest of the client portal. */
export function itemStatusDisplay(item: ClientCalendarItem) {
  if (item.status === DocumentStatus.PENDIENTE && !item.submission_id) {
    return {
      label: slotStateLabel(SlotState.MISSING),
      variant: slotStateVariant(SlotState.MISSING),
    };
  }
  return { label: statusLabel(item.status), variant: statusVariant(item.status) };
}

/** Worst (lowest-ordinal) risk among a set of obligations, or null when
 *  the set is empty / unclassified. Drives a matrix cell's tint. */
export function worstRisk(items: ClientCalendarItem[]): ClientCalendarRisk | null {
  let worst: ClientCalendarRisk | null = null;
  for (const item of items) {
    const r = item.risk_level;
    if (!r) continue;
    if (worst === null || RISK_ORDER[r] < RISK_ORDER[worst]) worst = r;
  }
  return worst;
}

/** Deep-link focus bucket on the vendor detail page
 *  (?focus=…#documentos) — the shipped convention the vendors list uses. */
export function focusForItem(
  item: ClientCalendarItem,
): "missing" | "rejected" | "due_soon" {
  if (item.risk_level === "action_required") return "rejected";
  if (!item.submission_id) return "missing";
  return "due_soon";
}

/** The obligation's deadline month (1-12), from its ISO deadline. */
export function monthOf(item: ClientCalendarItem): number {
  return Number(item.deadline_iso.slice(5, 7));
}

/** The concrete next step for the CLIENT on one obligation. The client does
 *  not upload, so every action is framed as chasing the provider or waiting
 *  on the reviewer — never a fabricated capability. */
export function nextActionFor(item: ClientCalendarItem): string {
  switch (item.risk_level) {
    case "action_required":
      return "Pídele al proveedor que corrija y reemplace el documento.";
    case "in_review":
      return "En revisión por el equipo. No requiere acción de tu parte.";
    case "on_track":
      return "Al día. Sin acción pendiente.";
    default:
      // overdue / due_soon / upcoming
      return item.submission_id
        ? "Da seguimiento con el proveedor."
        : "Pídele al proveedor que suba el documento.";
  }
}
