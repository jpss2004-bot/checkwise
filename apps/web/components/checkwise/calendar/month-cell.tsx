"use client";

import { useEffect, useRef, useState } from "react";
import {
  CheckCircle,
  CircleDashed,
  Clock,
  FileMagnifyingGlass,
  HourglassHigh,
  Tray,
  Warning,
  XCircle,
  type Icon,
} from "@phosphor-icons/react";

import { DOC_STATE_LABELS } from "@/components/checkwise/doc-state-badge";
import { MONTH_LABELS_ES } from "@/lib/api/portal";
import type { DocumentStateCode } from "@/lib/types";

import { CellPopover } from "./cell-popover";
import { URGENT_STATES, type CalendarEntry } from "./types";

const SEGMENT_BG: Record<DocumentStateCode, string> = {
  approved:     "bg-[color:var(--doc-approved-bg)]",
  in_review:    "bg-[color:var(--doc-in-review-bg)]",
  uploaded:     "bg-[color:var(--doc-uploaded-bg)]",
  rejected:     "bg-[color:var(--doc-rejected-bg)]",
  expired:      "bg-[color:var(--doc-expired-bg)]",
  needs_review: "bg-[color:var(--doc-needs-review-bg)]",
  pending:      "bg-[color:var(--doc-pending-bg)]",
  empty:        "bg-[color:var(--doc-empty-bg)]",
};

const STATE_ICON: Record<DocumentStateCode, Icon> = {
  approved:     CheckCircle,
  in_review:    HourglassHigh,
  uploaded:     Tray,
  rejected:     XCircle,
  expired:      Warning,
  needs_review: FileMagnifyingGlass,
  pending:      Clock,
  empty:        CircleDashed,
};

const STATE_ICON_COLOR: Record<DocumentStateCode, string> = {
  approved:     "text-[color:var(--doc-approved-text)]",
  in_review:    "text-[color:var(--doc-in-review-text)]",
  uploaded:     "text-[color:var(--doc-uploaded-text)]",
  rejected:     "text-[color:var(--doc-rejected-text)]",
  expired:      "text-[color:var(--doc-expired-text)]",
  needs_review: "text-[color:var(--doc-needs-review-text)]",
  pending:      "text-[color:var(--doc-pending-text)]",
  empty:        "text-[color:var(--doc-empty-text)]",
};

const DOMINANT_RANK: Record<DocumentStateCode, number> = {
  rejected:     0,
  expired:      1,
  needs_review: 2,
  pending:      3,
  uploaded:     4,
  in_review:    5,
  approved:     6,
  empty:        7,
};

function dominantState(events: CalendarEntry[]): DocumentStateCode {
  return [...events].sort(
    (a, b) => DOMINANT_RANK[a.state] - DOMINANT_RANK[b.state],
  )[0].state;
}

function hasUrgent(events: CalendarEntry[]): boolean {
  return events.some((e) => URGENT_STATES.has(e.state));
}

function uniqueStates(events: CalendarEntry[]): DocumentStateCode[] {
  const seen = new Set<DocumentStateCode>();
  for (const e of events) seen.add(e.state);
  return Array.from(seen);
}

export function MonthCell({
  events,
  month,
  isCurrent,
  isPast,
  onSelect,
}: {
  events: CalendarEntry[];
  month: number;
  isCurrent: boolean;
  isPast: boolean;
  onSelect: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTimer = () => {
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  };

  const scheduleClose = () => {
    clearTimer();
    closeTimerRef.current = setTimeout(() => setOpen(false), 120);
  };

  const handleEnter = () => {
    clearTimer();
    setOpen(true);
  };

  useEffect(() => clearTimer, []);

  if (events.length === 0) {
    return (
      <div
        className={
          "relative h-12 lg:h-14 2xl:h-16 w-full rounded-[6px] border " +
          (isCurrent
            ? "border-[color:var(--border-focus)] bg-[color:var(--surface-brand-muted)]/30"
            : isPast
              ? "border-[color:var(--border-subtle)]/50 bg-[color:var(--surface-page)]/40"
              : "border-[color:var(--border-subtle)] bg-[color:var(--surface-page)]")
        }
        aria-hidden="true"
      />
    );
  }

  const dominant = dominantState(events);
  const states = uniqueStates(events);
  const isSingleState = states.length === 1;
  const urgent = hasUrgent(events);
  // A6 — alert ring driven by the server risk tier: a month holding an overdue
  // or action-required obligation reads as critical at a glance, regardless of
  // whether it is in the past. Falls back to the legacy past-urgent signal when
  // ``risk_level`` is absent (stale backend).
  const hasCritical =
    events.some(
      (e) => e.risk_level === "overdue" || e.risk_level === "action_required",
    ) ||
    (urgent && isPast);
  // Bugfix (2026-05-21) — past months that contain real history
  // (approved uploads, in-review submissions, anything other than an
  // empty slot) must NOT be visually dimmed. A fully-compliant user
  // viewing the current year was seeing every past month rendered
  // at opacity-50 + grayscale-[25%], making their entire upload
  // history look washed out — they reported the calendar "seemed
  // empty" because the green approved markers and submission counts
  // were barely visible. Cells with events now render at full
  // opacity regardless of month position; the past-vs-current
  // distinction lives only on truly empty cells (handled in the
  // events.length === 0 branch above). ``urgent`` still drives the
  // rejected ring below so missed-and-overdue cells stay loud.
  const monthLabel = MONTH_LABELS_ES[month];
  const firstEvent = events[0];
  const ariaLabel =
    events.length === 1
      ? `${firstEvent.obligation} en ${monthLabel}: ${DOC_STATE_LABELS[firstEvent.state]}`
      : `${events.length} obligaciones en ${monthLabel}; ${states
          .map((s) => DOC_STATE_LABELS[s])
          .join(", ")}. Toca para ver detalle.`;

  const DominantIcon = STATE_ICON[dominant];

  return (
    <div
      className="relative"
      onMouseEnter={handleEnter}
      onMouseLeave={scheduleClose}
    >
      <button
        ref={buttonRef}
        type="button"
        onClick={() => onSelect(events[0].id)}
        onFocus={handleEnter}
        onBlur={scheduleClose}
        aria-label={ariaLabel}
        aria-haspopup={events.length > 1 ? "menu" : undefined}
        aria-expanded={events.length > 1 ? open : undefined}
        className={
          "group relative flex h-12 lg:h-14 2xl:h-16 w-full flex-col overflow-hidden rounded-[6px] border border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)] " +
          (isCurrent
            ? " ring-1 ring-[color:var(--border-focus)] "
            : " ") +
          "transition-[transform,box-shadow,border-color] duration-150 ease-out hover:-translate-y-px hover:border-[color:var(--border-default)] hover:shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)] focus-visible:ring-offset-1 " +
          (hasCritical ? "ring-1 ring-[color:var(--doc-rejected-border)] " : "")
        }
      >
        <SegmentBar events={events} />
        <span className="flex flex-1 items-center justify-center gap-1.5 px-1">
          <DominantIcon
            className={
              "h-3 w-3 lg:h-3.5 lg:w-3.5 shrink-0 " + STATE_ICON_COLOR[dominant]
            }
            weight="bold"
            aria-hidden="true"
          />
          <span
            className="font-mono text-[11px] lg:text-[12px] font-semibold tabular-nums text-[color:var(--text-primary)]"
          >
            {events.length}
          </span>
          {!isSingleState && events.length > 1 && (
            <span
              aria-hidden="true"
              className="text-[8px] font-mono text-[color:var(--text-tertiary)]"
            >
              {states.length}↕
            </span>
          )}
        </span>
      </button>

      <CellPopover
        triggerRef={buttonRef}
        events={events}
        month={month}
        open={open && events.length > 0}
        onSelect={(id) => {
          setOpen(false);
          onSelect(id);
        }}
        onEnter={handleEnter}
        onLeave={scheduleClose}
      />
    </div>
  );
}

function SegmentBar({ events }: { events: CalendarEntry[] }) {
  const segments = [...events].sort(
    (a, b) => DOMINANT_RANK[a.state] - DOMINANT_RANK[b.state],
  );
  return (
    <div className="flex h-2 lg:h-2.5 w-full">
      {segments.map((event, idx) => (
        <span
          key={event.id}
          className={
            SEGMENT_BG[event.state] +
            (idx > 0 ? " border-l border-[color:var(--surface-raised)]" : "")
          }
          style={{ width: `${100 / segments.length}%` }}
          aria-hidden="true"
        />
      ))}
    </div>
  );
}
