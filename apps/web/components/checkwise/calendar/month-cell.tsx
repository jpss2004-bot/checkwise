"use client";

import { useEffect, useRef, useState } from "react";

import { MONTH_LABELS_ES } from "@/lib/api/portal";

import { RISK_LABEL, riskSegments } from "./calendar-shared";
import { CellPopover } from "./cell-popover";
import { RiskCompositionContent } from "./risk-composition-cell";
import type { CalendarEntry } from "./types";

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

  // Risk-composition cell, identical to the client matrix: a neutral surface
  // with the obligation count over a proportional bar split by the six
  // severities (overdue / awaiting-correction / due-soon / in-review / upcoming
  // / on-track) — the look the provider asked to match. Urgency is read from
  // the bar's red/orange slice, not a separate ring or a flat worst-case fill.
  const monthLabel = MONTH_LABELS_ES[month];
  const segments = riskSegments(events.map((e) => e.risk_level));
  const firstEvent = events[0];
  const breakdown = segments
    .map((s) => `${s.n} ${RISK_LABEL[s.risk].toLowerCase()}`)
    .join(", ");
  const ariaLabel =
    events.length === 1
      ? `${firstEvent.obligation} en ${monthLabel}: ${RISK_LABEL[firstEvent.risk_level ?? "on_track"]}. Toca para ver detalle.`
      : `${events.length} obligaciones en ${monthLabel} — ${breakdown}. Toca para ver detalle.`;

  return (
    <div
      className="relative"
      onMouseEnter={handleEnter}
      onMouseLeave={scheduleClose}
    >
      <button
        ref={buttonRef}
        type="button"
        // A single-obligation cell opens its drawer directly. A
        // multi-obligation cell is a disclosure: tap/click toggles the
        // popover that lists each obligation. The click previously always
        // opened events[0], so obligations 2..N were reachable only by
        // hovering — a dead end on touch and easy to miss with a mouse
        // (Portal Proveedor, 2ª revisión, Calendario #2).
        onClick={() =>
          events.length > 1 ? setOpen((o) => !o) : onSelect(events[0].id)
        }
        onFocus={handleEnter}
        onBlur={scheduleClose}
        aria-label={ariaLabel}
        aria-haspopup={events.length > 1 ? "menu" : undefined}
        aria-expanded={events.length > 1 ? open : undefined}
        className={
          "flex h-12 lg:h-14 2xl:h-16 w-full flex-col items-center justify-center gap-1 rounded-[6px] border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-1.5 transition-[transform,box-shadow] duration-150 ease-out hover:-translate-y-px hover:shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)] " +
          (isCurrent ? "ring-1 ring-[color:var(--border-focus)] " : "")
        }
      >
        <RiskCompositionContent count={events.length} segments={segments} />
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
