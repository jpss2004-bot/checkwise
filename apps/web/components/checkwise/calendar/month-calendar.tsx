"use client";

import { CaretLeft, CaretRight } from "@phosphor-icons/react";

import { Button } from "@/components/ui/button";
import type { ClientCalendarItem } from "@/lib/api/client";
import { MONTH_LABELS_ES } from "@/lib/api/portal";

import {
  BUCKET_CELL,
  RISK_ICON,
  RISK_LABEL,
  riskBucket,
  worstRisk,
} from "./client-calendar-shared";

const WEEKDAYS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];

/**
 * Month-grid calendar — the page's main component. Each day that carries
 * deadlines is tinted by its worst obligation state and shows a count;
 * tapping it selects the day so its obligations render in detail below.
 * REPSE deadlines cluster on the 17th (SAT annual on the 30th), so the
 * grid honestly shows mid-month as the hot day.
 */
export function MonthCalendar({
  year,
  month,
  itemsByDay,
  today,
  selectedDay,
  onSelectDay,
  onPrevMonth,
  onNextMonth,
  onToday,
}: {
  year: number;
  /** 1-12 */
  month: number;
  /** day (1-31) → obligations due that day, for THIS month. */
  itemsByDay: Map<number, ClientCalendarItem[]>;
  today: Date;
  selectedDay: number | null;
  onSelectDay: (day: number) => void;
  onPrevMonth: () => void;
  onNextMonth: () => void;
  onToday: () => void;
}) {
  const daysInMonth = new Date(year, month, 0).getDate();
  // Monday-first offset for the 1st of the month.
  const leadingBlanks = (new Date(year, month - 1, 1).getDay() + 6) % 7;
  const isCurrentMonth =
    today.getFullYear() === year && today.getMonth() + 1 === month;
  const todayDay = today.getDate();

  const cells: (number | null)[] = [
    ...Array.from({ length: leadingBlanks }, () => null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-[color:var(--text-primary)]">
          {MONTH_LABELS_ES[month]}{" "}
          <span className="font-mono tabular-nums text-[color:var(--text-tertiary)]">
            {year}
          </span>
        </h2>
        <div className="flex items-center gap-1.5">
          <Button variant="ghost" size="sm" onClick={onToday}>
            Hoy
          </Button>
          <Button
            variant="outline"
            size="icon"
            onClick={onPrevMonth}
            aria-label="Mes anterior"
          >
            <CaretLeft className="h-4 w-4" weight="bold" aria-hidden="true" />
          </Button>
          <Button
            variant="outline"
            size="icon"
            onClick={onNextMonth}
            aria-label="Mes siguiente"
          >
            <CaretRight className="h-4 w-4" weight="bold" aria-hidden="true" />
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-7 gap-1 sm:gap-1.5">
        {WEEKDAYS.map((w) => (
          <div
            key={w}
            className="pb-1 text-center font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]"
          >
            {w}
          </div>
        ))}
        {cells.map((day, idx) => {
          if (day === null) {
            return <div key={`blank-${idx}`} aria-hidden="true" />;
          }
          const items = itemsByDay.get(day) ?? [];
          const isToday = isCurrentMonth && day === todayDay;
          const isSelected = selectedDay === day;
          return (
            <DayCell
              key={day}
              day={day}
              items={items}
              isToday={isToday}
              isSelected={isSelected}
              onSelect={() => onSelectDay(day)}
            />
          );
        })}
      </div>
    </div>
  );
}

function DayCell({
  day,
  items,
  isToday,
  isSelected,
  onSelect,
}: {
  day: number;
  items: ClientCalendarItem[];
  isToday: boolean;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const empty = items.length === 0;
  const worst = empty ? null : (worstRisk(items) ?? "on_track");
  const bucket = worst ? riskBucket(worst) : null;
  const Icon = worst ? RISK_ICON[worst] : null;

  const base =
    "relative flex min-h-[60px] flex-col rounded-lg border p-1.5 text-left sm:min-h-[76px] ";
  const ring = isSelected
    ? "ring-2 ring-[color:var(--border-focus)] "
    : isToday
      ? "ring-1 ring-[color:var(--border-focus)] "
      : "";

  if (empty) {
    return (
      <div
        className={
          base +
          ring +
          "border-[color:var(--border-subtle)]/50 bg-[color:var(--surface-page)]/30"
        }
      >
        <span
          className={
            "text-xs tabular-nums " +
            (isToday
              ? "font-semibold text-[color:var(--text-brand)]"
              : "text-[color:var(--text-tertiary)]")
          }
        >
          {day}
        </span>
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={isSelected}
      aria-label={`${day} · ${items.length} ${items.length === 1 ? "obligación" : "obligaciones"} · ${worst ? RISK_LABEL[worst] : ""}`}
      className={
        base +
        ring +
        (bucket ? BUCKET_CELL[bucket] : "") +
        " transition-[transform,box-shadow] duration-150 ease-out hover:-translate-y-px hover:shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]"
      }
    >
      <span
        className={
          "text-xs font-semibold tabular-nums " +
          (isToday ? "text-[color:var(--text-brand)]" : "")
        }
      >
        {day}
      </span>
      <span className="mt-auto flex items-center gap-1 self-end">
        {Icon ? (
          <Icon
            className="h-3.5 w-3.5 shrink-0"
            weight="bold"
            aria-hidden="true"
          />
        ) : null}
        <span className="font-mono text-sm font-semibold leading-none tabular-nums">
          {items.length}
        </span>
      </span>
    </button>
  );
}
