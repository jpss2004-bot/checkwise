"use client";

import {
  CheckCircle,
  CircleDashed,
  Clock,
  FileMagnifyingGlass,
  HourglassHigh,
  Tray,
  Warning,
  WarningDiamond,
  XCircle,
  type Icon,
} from "@phosphor-icons/react";

import { DOC_STATE_LABELS } from "@/components/checkwise/doc-state-badge";
import { INSTITUTION_LABELS, MONTH_LABELS_ES } from "@/lib/api/portal";
import type { DocumentStateCode } from "@/lib/types";

import { riskRank } from "./calendar-shared";
import type { CalendarEntry, CalendarInstitutionCode } from "./types";

/**
 * Phase 7 / Slice 7A — provider calendar, mobile layout.
 *
 * The desktop grid (12-month columns × institution rows) is hard to
 * read on a phone: ``min-w-[860px]`` + ``overflow-x-auto`` works but
 * forces a horizontal-scroll-then-tap interaction that no provider
 * wants on a small screen. This component renders the same data as
 * a vertical, month-by-month list — each month is a card, each
 * obligation is a tappable row. Tapping a row calls the same
 * ``onSelect`` the desktop grid uses, so the existing EventDrawer
 * stays the single source of truth for action.
 *
 * Visible only below the ``lg`` (1024px) breakpoint; the page wraps
 * the grid in ``hidden lg:block`` and this component in
 * ``lg:hidden`` so each viewport gets exactly one layout.
 *
 * Sorted from current month outward: the current month + future
 * months render first (most actionable), past months drop below.
 * Empty months are skipped entirely so the list collapses to what
 * the provider actually has in front of them.
 */

const STATE_ICON: Record<DocumentStateCode, Icon> = {
  approved: CheckCircle,
  in_review: HourglassHigh,
  uploaded: Tray,
  rejected: XCircle,
  expired: Warning,
  possible_mismatch: WarningDiamond,
  needs_review: FileMagnifyingGlass,
  pending: Clock,
  empty: CircleDashed,
};

const STATE_TONE: Record<DocumentStateCode, string> = {
  approved:
    "border-[color:var(--doc-approved-border)] bg-[color:var(--doc-approved-bg)] text-[color:var(--doc-approved-text)]",
  in_review:
    "border-[color:var(--doc-in-review-border)] bg-[color:var(--doc-in-review-bg)] text-[color:var(--doc-in-review-text)]",
  uploaded:
    "border-[color:var(--doc-uploaded-border)] bg-[color:var(--doc-uploaded-bg)] text-[color:var(--doc-uploaded-text)]",
  rejected:
    "border-[color:var(--doc-rejected-border)] bg-[color:var(--doc-rejected-bg)] text-[color:var(--doc-rejected-text)]",
  expired:
    "border-[color:var(--doc-expired-border)] bg-[color:var(--doc-expired-bg)] text-[color:var(--doc-expired-text)]",
  possible_mismatch:
    "border-[color:var(--doc-needs-review-border)] bg-[color:var(--doc-needs-review-bg)] text-[color:var(--doc-needs-review-text)]",
  needs_review:
    "border-[color:var(--doc-needs-review-border)] bg-[color:var(--doc-needs-review-bg)] text-[color:var(--doc-needs-review-text)]",
  pending:
    "border-[color:var(--doc-pending-border)] bg-[color:var(--doc-pending-bg)] text-[color:var(--doc-pending-text)]",
  empty:
    "border-[color:var(--doc-empty-border)] bg-[color:var(--doc-empty-bg)] text-[color:var(--doc-empty-text)]",
};

const INSTITUTION_LABEL_SHORT: Record<CalendarInstitutionCode, string> = {
  sat: "SAT",
  imss: "IMSS",
  infonavit: "INFONAVIT",
  stps_repse: "STPS/REPSE",
};

export function MobileMonthList({
  events,
  currentMonth,
  onSelect,
}: {
  events: CalendarEntry[];
  /** 1-12. Used to reorder months from "current first" rather than
   *  always starting from January. */
  currentMonth: number;
  onSelect: (id: string) => void;
}) {
  // Bucket by month, drop empty months, then reorder so current
  // month and the months after it come first.
  const byMonth = new Map<number, CalendarEntry[]>();
  for (const e of events) {
    const list = byMonth.get(e.month) ?? [];
    list.push(e);
    byMonth.set(e.month, list);
  }
  const populatedMonths = Array.from(byMonth.keys()).sort((a, b) => a - b);
  if (populatedMonths.length === 0) {
    return (
      <section
        className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-6 text-center text-sm text-[color:var(--text-secondary)]"
        aria-label="Calendario vacío"
      >
        Sin obligaciones que mostrar con los filtros actuales.
      </section>
    );
  }
  const reordered = [
    ...populatedMonths.filter((m) => m >= currentMonth),
    ...populatedMonths.filter((m) => m < currentMonth),
  ];

  return (
    <section
      aria-label="Calendario por mes"
      className="space-y-4"
    >
      {reordered.map((month) => {
        const monthEvents = byMonth.get(month) ?? [];
        // A6 — most-urgent-first by the server risk tier (so an overdue but
        // still-"pending" obligation leads over an upcoming one — the time
        // dimension the state RANK alone misses), with the document-state RANK
        // as the tiebreak within a tier.
        const sorted = [...monthEvents].sort(
          (a, b) =>
            riskRank(a.risk_level) - riskRank(b.risk_level) ||
            RANK[a.state] - RANK[b.state],
        );
        const isCurrent = month === currentMonth;
        return (
          <article
            key={month}
            className={
              "rounded-lg border bg-[color:var(--surface-raised)] shadow-xs " +
              (isCurrent
                ? "border-[color:var(--border-focus)] ring-1 ring-[color:var(--border-focus)]/30"
                : "border-[color:var(--border-default)]")
            }
            aria-current={isCurrent ? "true" : undefined}
          >
            <header className="flex items-center justify-between border-b border-[color:var(--border-subtle)] px-4 py-2.5">
              <h3 className="text-[13px] font-semibold text-[color:var(--text-primary)]">
                {MONTH_LABELS_ES[month]}
              </h3>
              <span className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                {monthEvents.length}{" "}
                {monthEvents.length === 1 ? "obligación" : "obligaciones"}
              </span>
            </header>
            <ul className="divide-y divide-[color:var(--border-subtle)]">
              {sorted.map((event) => (
                <li key={event.id}>
                  <button
                    type="button"
                    onClick={() => onSelect(event.id)}
                    className="flex w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-[color:var(--surface-hover)] focus:outline-none focus-visible:bg-[color:var(--surface-hover)]"
                  >
                    <StateBadge state={event.state} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13px] font-medium text-[color:var(--text-primary)]">
                        {event.obligation}
                      </span>
                      <span className="mt-0.5 block truncate text-[11px] text-[color:var(--text-tertiary)]">
                        {INSTITUTION_LABEL_SHORT[
                          event.institution as CalendarInstitutionCode
                        ] ??
                          INSTITUTION_LABELS[event.institution] ??
                          event.institution}
                        {event.period_label ? ` · ${event.period_label}` : ""}
                        {event.filename ? ` · ${event.filename}` : ""}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </article>
        );
      })}
    </section>
  );
}

function StateBadge({ state }: { state: DocumentStateCode }) {
  const Icon = STATE_ICON[state];
  return (
    <span
      className={
        "mt-0.5 inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium " +
        STATE_TONE[state]
      }
      title={DOC_STATE_LABELS[state]}
    >
      <Icon className="h-3 w-3" weight="bold" aria-hidden="true" />
      <span>{DOC_STATE_LABELS[state]}</span>
    </span>
  );
}

const RANK: Record<DocumentStateCode, number> = {
  rejected: 0,
  expired: 1,
  possible_mismatch: 2,
  needs_review: 3,
  pending: 4,
  uploaded: 5,
  in_review: 6,
  approved: 7,
  empty: 8,
};
