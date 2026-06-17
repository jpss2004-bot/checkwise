// Shared vocabulary + date helpers for the client calendar surfaces
// (risk strip, agenda, portfolio matrix, item drawer). Kept in one place
// so the severity ordering, tones, and "in N days" math never drift
// between the three views that render the same obligations.

import {
  ArrowsClockwise,
  Buildings,
  CalendarBlank,
  CheckCircle,
  Clock,
  House,
  HourglassHigh,
  Scales,
  ShieldCheck,
  WarningOctagon,
  type Icon,
} from "@phosphor-icons/react";

// Institution icons mirror the portal calendar so the client view reads
// with the same visual vocabulary. House (vivienda) for INFONAVIT
// disambiguates it from IMSS (Buildings).
export const INSTITUTION_ICON: Record<string, Icon> = {
  sat: Scales,
  imss: Buildings,
  infonavit: House,
  stps_repse: ShieldCheck,
};

import type { ClientCalendarItem, ClientCalendarRisk } from "@/lib/api/client";
import {
  DocumentStatus,
  SlotState,
  slotStateLabel,
  slotStateVariant,
  statusLabel,
  statusVariant,
} from "@/lib/constants/statuses";

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

// Most-severe-first. Mirrors the backend ``_calendar_item_risk`` ordering.
export const CLIENT_RISK_ORDER: Record<ClientCalendarRisk, number> = {
  overdue: 0,
  action_required: 1,
  due_soon: 2,
  in_review: 3,
  upcoming: 4,
  on_track: 5,
};

/** Worst (lowest-ordinal) risk among a set of obligations, or null when
 *  the set is empty / unclassified. Drives a matrix cell's tint. */
export function worstRisk(items: ClientCalendarItem[]): ClientCalendarRisk | null {
  let worst: ClientCalendarRisk | null = null;
  for (const item of items) {
    const r = item.risk_level;
    if (!r) continue;
    if (worst === null || CLIENT_RISK_ORDER[r] < CLIENT_RISK_ORDER[worst]) {
      worst = r;
    }
  }
  return worst;
}

export const RISK_LABEL: Record<ClientCalendarRisk, string> = {
  overdue: "Vencida",
  action_required: "Requiere corrección",
  due_soon: "Vence pronto",
  in_review: "En revisión",
  upcoming: "Próxima",
  on_track: "Al día",
};

export const RISK_ICON: Record<ClientCalendarRisk, Icon> = {
  overdue: WarningOctagon,
  action_required: ArrowsClockwise,
  due_soon: Clock,
  in_review: HourglassHigh,
  upcoming: CalendarBlank,
  on_track: CheckCircle,
};

// Coarser heatmap bucket for the matrix: critical (overdue/rejected) →
// soon → review → upcoming → ok. Five tones read cleanly at a glance.
export type RiskBucket = "critical" | "soon" | "review" | "upcoming" | "ok";

export function riskBucket(risk: ClientCalendarRisk): RiskBucket {
  if (risk === "overdue" || risk === "action_required") return "critical";
  if (risk === "due_soon") return "soon";
  if (risk === "in_review") return "review";
  if (risk === "on_track") return "ok";
  return "upcoming";
}

export const BUCKET_CELL: Record<RiskBucket, string> = {
  critical:
    "border-[color:var(--doc-rejected-border)] bg-[color:var(--doc-rejected-bg)] text-[color:var(--doc-rejected-text)]",
  soon: "border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-bg)] text-[color:var(--status-warning-text)]",
  review:
    "border-[color:var(--doc-in-review-border)] bg-[color:var(--doc-in-review-bg)] text-[color:var(--doc-in-review-text)]",
  upcoming:
    "border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] text-[color:var(--text-tertiary)]",
  ok: "border-[color:var(--doc-approved-border)] bg-[color:var(--doc-approved-bg)] text-[color:var(--doc-approved-text)]",
};

export const SEMAPHORE_DOT: Record<"red" | "yellow" | "green", string> = {
  red: "bg-[color:var(--status-error-text)]",
  yellow: "bg-[color:var(--status-warning-text)]",
  green: "bg-[color:var(--status-success-text)]",
};

// ─── Date helpers ───────────────────────────────────────────────
// deadline_iso is "YYYY-MM-DD" with the conventional day-17 cutoff.
// Parsed as a *local* date so "in N days" never drifts at a UTC boundary.

export function parseLocalDate(iso: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return null;
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
}

export function daysUntil(iso: string, today: Date): number | null {
  const d = parseLocalDate(iso);
  if (!d) return null;
  const base = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  return Math.round((d.getTime() - base.getTime()) / 86_400_000);
}

export function formatShortDate(iso: string): string {
  const d = parseLocalDate(iso);
  if (!d) return iso;
  return d.toLocaleDateString("es-MX", { day: "2-digit", month: "short" });
}

export function formatLongDate(iso: string): string {
  const d = parseLocalDate(iso);
  if (!d) return iso;
  return d.toLocaleDateString("es-MX", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  });
}

export function relativeDeadline(iso: string, today: Date): string {
  const n = daysUntil(iso, today);
  const short = formatShortDate(iso);
  if (n === null) return short;
  if (n < 0) {
    const abs = Math.abs(n);
    return `Venció hace ${abs} día${abs === 1 ? "" : "s"} · ${short}`;
  }
  if (n === 0) return `Vence hoy · ${short}`;
  if (n === 1) return `Vence mañana · ${short}`;
  return `Vence en ${n} días · ${short}`;
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
