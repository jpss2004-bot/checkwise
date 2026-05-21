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

  return (
    <div className="flex items-center gap-3">
      <span className="flex items-center gap-2 text-[13px] font-semibold text-[color:var(--text-primary)]">
        <IconComponent
          className="h-4 w-4 text-[color:var(--text-brand)]"
          weight="duotone"
          aria-hidden="true"
        />
        {label}
      </span>

      {total > 0 && (
        <span
          className="ml-auto flex shrink-0 items-center gap-1.5"
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
            className="relative h-1 w-10 overflow-hidden rounded-full bg-[color:var(--surface-sunken)]"
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
