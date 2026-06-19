"use client";

import type { Icon } from "@phosphor-icons/react";

import type { CalendarEntry } from "./types";

const APPROVED_STATES = new Set(["approved"]);

function approvedRatio(events: CalendarEntry[]): {
  done: number;
  total: number;
  pct: number;
} {
  if (events.length === 0) return { done: 0, total: 0, pct: 0 };
  const done = events.filter((e) => APPROVED_STATES.has(e.state)).length;
  const pct = Math.round((done / events.length) * 100);
  return { done, total: events.length, pct };
}

export function InstitutionRowHeader({
  icon: IconComponent,
  label,
  events,
}: {
  icon: Icon;
  label: string;
  events: CalendarEntry[];
}) {
  const { done, total, pct } = approvedRatio(events);
  const wise = pct >= 90 && total > 0;
  const barTone = wise
    ? "bg-[color:var(--interactive-secondary)]"
    : "bg-[color:var(--interactive-primary)]";
  const chipText = wise
    ? "text-[color:var(--interactive-secondary)]"
    : "text-[color:var(--text-secondary)]";

  // The institution column is a fixed 160px (table-fixed + <colgroup>). A long
  // single-word label like "INFONAVIT" can't wrap and, laid out inline with an
  // ``ml-auto`` progress chip, pushed the compliance bar PAST the column edge
  // and over the first month cell ("la barra … se overlapea con el calendario").
  // Stacking the chip+bar *below* the label removes the horizontal competition
  // entirely, so neither can overflow regardless of label length; the label
  // still truncates as a final safety net.
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <span className="flex min-w-0 items-center gap-2 text-[13px] font-semibold text-[color:var(--text-primary)]">
        <IconComponent
          className="h-4 w-4 shrink-0 text-[color:var(--text-brand)]"
          weight="duotone"
          aria-hidden="true"
        />
        <span className="truncate">{label}</span>
      </span>

      {total > 0 && (
        <span
          className="flex items-center gap-1.5"
          aria-label={`${done} de ${total} aprobadas (${pct}%)`}
        >
          <span
            className={
              "font-mono text-[10px] font-medium tabular-nums " + chipText
            }
          >
            {done}/{total}
          </span>
          <span
            aria-hidden="true"
            className="relative h-1 w-10 max-w-full shrink-0 overflow-hidden rounded-full bg-[color:var(--surface-sunken)]"
          >
            <span
              className={"absolute inset-y-0 left-0 rounded-full " + barTone}
              style={{ width: `${pct}%` }}
            />
          </span>
        </span>
      )}
    </div>
  );
}
