// Portal-agnostic calendar vocabulary — the severity ordering, heatmap
// tones, and "in N days" date math shared by EVERY calendar surface (the
// client calendar, the admin cross-portfolio grid, and the obligation
// detail panels). Kept in one place so the colors and urgency math can
// never drift between portals. Client-only helpers (status badges, upload
// hrefs) live in ./client-calendar-shared, which re-exports everything here.

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

import { SEMAPHORE_DOT_CLASS } from "@/lib/constants/statuses";

// Institution → icon, app-wide. House (vivienda) for INFONAVIT disambiguates
// it from IMSS (Buildings); Scales for SAT, ShieldCheck for STPS/REPSE.
export const INSTITUTION_ICON: Record<string, Icon> = {
  sat: Scales,
  imss: Buildings,
  infonavit: House,
  stps_repse: ShieldCheck,
};

// The six ordered severities the backend emits (``_calendar_item_risk`` /
// the admin grid's ``worst_risk``). Structurally identical to
// ``ClientCalendarRisk`` in lib/api/client, so the two interoperate.
export type CalendarRisk =
  | "overdue"
  | "action_required"
  | "due_soon"
  | "in_review"
  | "upcoming"
  | "on_track";

// Most-severe-first. Mirrors the backend ``_CALENDAR_RISK_ORDER``.
export const RISK_ORDER: Record<CalendarRisk, number> = {
  overdue: 0,
  action_required: 1,
  due_soon: 2,
  in_review: 3,
  upcoming: 4,
  on_track: 5,
};

/** Sort key for "most urgent first" ordering. Lower = more urgent; an unknown
 *  or missing risk (e.g. a stale backend that hasn't shipped ``risk_level``)
 *  sorts last so it never jumps ahead of a classified obligation. */
export function riskRank(risk: CalendarRisk | string | null | undefined): number {
  const ord = risk ? RISK_ORDER[risk as CalendarRisk] : undefined;
  return ord ?? 99;
}

/** Worst (lowest-ordinal) risk among a set, or ``on_track`` when empty. */
export function worstRiskOf(
  risks: ReadonlyArray<CalendarRisk | string | null | undefined>,
): CalendarRisk {
  let worst: CalendarRisk = "on_track";
  for (const r of risks) {
    if (!r) continue;
    const ord = RISK_ORDER[r as CalendarRisk];
    if (ord !== undefined && ord < RISK_ORDER[worst]) worst = r as CalendarRisk;
  }
  return worst;
}

export const RISK_LABEL: Record<CalendarRisk, string> = {
  overdue: "Vencida",
  action_required: "Requiere corrección",
  due_soon: "Vence pronto",
  in_review: "En revisión",
  upcoming: "Próxima",
  on_track: "Al día",
};

export const RISK_ICON: Record<CalendarRisk, Icon> = {
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

export function riskBucket(risk: CalendarRisk): RiskBucket {
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

// The semáforo dot fill is defined ONCE in lib/constants/statuses.ts; re-export
// it here so calendar surfaces share the exact same red/yellow/green tone.
export const SEMAPHORE_DOT = SEMAPHORE_DOT_CLASS;

// Per-risk solid fill for the in-cell composition bar + legend, pinned to the
// ONE portal-wide tone scale (state-vocabulary unification 2026-06-19): a
// color always means the same severity everywhere. The two blocking severities
// (overdue + action_required) share RED — the label/icon distinguishes them —
// instead of the old orange-for-correction, which collided with the orange
// "Vencido" badge. in_review is the info BLUE used everywhere else (was navy).
export const RISK_BAR_COLOR: Record<CalendarRisk, string> = {
  overdue: "hsl(var(--red-500))",
  action_required: "hsl(var(--red-500))",
  due_soon: "hsl(var(--amber-500))",
  in_review: "hsl(var(--blue-500))",
  upcoming: "hsl(var(--gray-400))",
  on_track: "hsl(var(--green-500))",
};

// Worst-first ordering for stacked bars + legends, so the most urgent slice
// always leads. Mirrors RISK_ORDER.
export const RISK_LEVELS_WORST_FIRST: CalendarRisk[] = [
  "overdue",
  "action_required",
  "due_soon",
  "in_review",
  "upcoming",
  "on_track",
];

export type RiskSegment = { risk: CalendarRisk; n: number };

/** Group a set of obligation risks into worst-first, non-empty segments — the
 *  composition a calendar heat cell's bar renders (how a month's count splits
 *  across the six severities). Shared by the client matrix and the provider
 *  grid so a cell reads identically on both. A null/unknown risk counts as
 *  ``on_track`` (the least-urgent bucket). */
export function riskSegments(
  risks: ReadonlyArray<CalendarRisk | string | null | undefined>,
): RiskSegment[] {
  const counts = new Map<CalendarRisk, number>();
  for (const r of risks) {
    const key = (r && r in RISK_ORDER ? r : "on_track") as CalendarRisk;
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  const out: RiskSegment[] = [];
  for (const risk of RISK_LEVELS_WORST_FIRST) {
    const n = counts.get(risk) ?? 0;
    if (n > 0) out.push({ risk, n });
  }
  return out;
}

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
