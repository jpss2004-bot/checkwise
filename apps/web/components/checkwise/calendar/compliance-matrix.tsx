"use client";

import { useEffect, useRef, useState } from "react";
import { CaretDown, CaretRight } from "@phosphor-icons/react";

import { MONTH_LABELS_ES, MONTH_LABELS_SHORT_ES } from "@/lib/api/portal";

import {
  BUCKET_CELL,
  RISK_ICON,
  RISK_LABEL,
  SEMAPHORE_DOT,
  riskBucket,
  type CalendarRisk,
  type RiskBucket,
} from "./calendar-shared";
import {
  MatrixCellPopover,
  type CellPreviewItem,
} from "./matrix-cell-popover";

/**
 * A rows×12-months compliance heatmap — the shared calendar grid. Rows are
 * an abstract entity (providers for the client calendar, clients for the
 * admin cross-portfolio grid); each cell carries a precomputed count + worst
 * risk, so the matrix is portal-agnostic. The month is the meaningful unit of
 * REPSE time (≈every deadline lands on the 17th), so the grid IS the calendar.
 *
 * Tap a cell to select one row's month, a month header for that month across
 * every row, or — when ``onSelectRow`` is given — a row label to drill into
 * it. Desktop shows the grid; below lg each row becomes a collapsible list of
 * its active months, since a 13-column grid can't breathe on a phone.
 */

export type ComplianceMatrixRow = {
  id: string;
  name: string;
  semaphore_level: string;
  /** Optional muted second line, e.g. "82% al día" or a vendor count. */
  subtitle?: string;
};

export type ComplianceMatrixCell = { count: number; worstRisk: CalendarRisk };

export type ComplianceMatrixSelection = {
  rowId: string | null;
  month: number;
} | null;

const LEGEND: { bucket: RiskBucket; label: string }[] = [
  { bucket: "critical", label: "Vencido / por corregir" },
  { bucket: "soon", label: "Vence pronto" },
  { bucket: "review", label: "En revisión" },
  { bucket: "upcoming", label: "Próximo" },
  { bucket: "ok", label: "Al día" },
];

const SEMAPHORE_DOT_FALLBACK = SEMAPHORE_DOT.yellow;

function dotClass(level: string): string {
  return SEMAPHORE_DOT[level as "red" | "yellow" | "green"] ?? SEMAPHORE_DOT_FALLBACK;
}

export function ComplianceMatrix({
  rows,
  cells,
  cellItems,
  currentMonth,
  selected,
  onSelectCell,
  onSelectMonth,
  onSelectRow,
  rowHeader = "Proveedor",
}: {
  rows: ComplianceMatrixRow[];
  /** key = `${rowId}-${month}` (month 1-12). */
  cells: Map<string, ComplianceMatrixCell>;
  /** Optional per-cell obligation preview (same `${rowId}-${month}` key). When
   *  given, a populated cell shows a hover/focus popover listing its contents
   *  so a busy cell can be scanned without the click + scroll-to-detail trip.
   *  Omit it (e.g. the admin grid) to disable the preview entirely. */
  cellItems?: Map<string, CellPreviewItem[]>;
  currentMonth: number | null;
  selected: ComplianceMatrixSelection;
  onSelectCell: (rowId: string, month: number) => void;
  onSelectMonth: (month: number) => void;
  /** When set, the row label becomes a drill-in button. */
  onSelectRow?: (rowId: string) => void;
  rowHeader?: string;
}) {
  if (rows.length === 0) return null;

  const monthTotals = Array.from({ length: 12 }, (_, i) => {
    const month = i + 1;
    let count = 0;
    for (const r of rows) count += cells.get(`${r.id}-${month}`)?.count ?? 0;
    return count;
  });

  return (
    <div>
      {/* Desktop grid */}
      <div className="hidden overflow-x-auto lg:block">
        <table className="w-full table-fixed border-collapse">
          <colgroup>
            <col style={{ width: "240px" }} />
            {Array.from({ length: 12 }, (_, i) => (
              <col key={`mcol-${i}`} />
            ))}
          </colgroup>
          <thead>
            <tr className="border-b border-[color:var(--border-subtle)]">
              <th
                scope="col"
                className="sticky left-0 z-10 bg-[color:var(--surface-raised)] px-3 py-2 text-left text-xs font-semibold text-[color:var(--text-secondary)]"
              >
                {rowHeader}
              </th>
              {MONTH_LABELS_SHORT_ES.map((m, idx) => {
                const month = idx + 1;
                const isCurrent = currentMonth === month;
                const isSelMonth =
                  selected?.rowId === null && selected?.month === month;
                const total = monthTotals[idx];
                return (
                  <th key={m} scope="col" className="px-1 pb-1.5 pt-1">
                    <button
                      type="button"
                      onClick={() => onSelectMonth(month)}
                      aria-pressed={isSelMonth}
                      title={`Ver ${MONTH_LABELS_ES[month]} en todas las filas`}
                      className={
                        "flex w-full flex-col items-center rounded-md px-1 py-1 transition-colors hover:bg-[color:var(--surface-hover)] " +
                        (isSelMonth ? "bg-[color:var(--surface-selected)] " : "")
                      }
                    >
                      <span
                        className={
                          "text-[11px] font-medium uppercase tracking-wide " +
                          (isCurrent
                            ? "text-[color:var(--text-brand)]"
                            : "text-[color:var(--text-tertiary)]")
                        }
                      >
                        {m}
                      </span>
                      <span className="font-mono text-[10px] tabular-nums text-[color:var(--text-tertiary)]">
                        {total || ""}
                      </span>
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.id}
                className="border-b border-[color:var(--border-subtle)] last:border-0"
              >
                <th
                  scope="row"
                  className="sticky left-0 z-10 bg-[color:var(--surface-raised)] px-3 py-2 text-left align-middle"
                >
                  <RowLabel row={row} onSelectRow={onSelectRow} />
                </th>
                {Array.from({ length: 12 }, (_, monthIdx) => {
                  const month = monthIdx + 1;
                  const cell = cells.get(`${row.id}-${month}`);
                  const isSel =
                    selected?.rowId === row.id && selected?.month === month;
                  return (
                    <td key={month} className="p-1 align-middle">
                      <MatrixCell
                        cell={cell}
                        month={month}
                        rowName={row.name}
                        preview={cellItems?.get(`${row.id}-${month}`)}
                        isCurrent={currentMonth === month}
                        isSelected={isSel}
                        onClick={() => onSelectCell(row.id, month)}
                      />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>

        <ul className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-[color:var(--border-subtle)] pt-3">
          <li className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
            Leyenda
          </li>
          {LEGEND.map(({ bucket, label }) => (
            <li key={bucket} className="flex items-center gap-1.5">
              <span
                aria-hidden="true"
                className={"h-3.5 w-3.5 rounded border " + BUCKET_CELL[bucket]}
              />
              <span className="text-xs text-[color:var(--text-secondary)]">
                {label}
              </span>
            </li>
          ))}
        </ul>
      </div>

      {/* Mobile: per-row accordion of active months */}
      <div className="space-y-2 lg:hidden">
        {rows.map((row) => (
          <RowMonthsAccordion
            key={row.id}
            row={row}
            cells={cells}
            selected={selected}
            onSelectCell={onSelectCell}
            onSelectRow={onSelectRow}
          />
        ))}
      </div>
    </div>
  );
}

function RowLabel({
  row,
  onSelectRow,
}: {
  row: ComplianceMatrixRow;
  onSelectRow?: (rowId: string) => void;
}) {
  const inner = (
    <span className="flex items-center gap-2">
      <span
        aria-hidden="true"
        className={"h-2.5 w-2.5 shrink-0 rounded-full " + dotClass(row.semaphore_level)}
      />
      <span className="min-w-0">
        <span className="block truncate text-[13px] font-medium text-[color:var(--text-primary)]">
          {row.name}
        </span>
        {row.subtitle ? (
          <span className="font-mono text-[11px] tabular-nums text-[color:var(--text-tertiary)]">
            {row.subtitle}
          </span>
        ) : null}
      </span>
    </span>
  );
  if (!onSelectRow) return inner;
  return (
    <button
      type="button"
      onClick={() => onSelectRow(row.id)}
      title={`Ver el detalle de ${row.name}`}
      className="-mx-1 flex w-full items-center rounded-md px-1 py-0.5 text-left transition-colors hover:bg-[color:var(--surface-hover)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]"
    >
      {inner}
    </button>
  );
}

function MatrixCell({
  cell,
  month,
  rowName,
  preview,
  isCurrent,
  isSelected,
  onClick,
}: {
  cell: ComplianceMatrixCell | undefined;
  month: number;
  rowName: string;
  preview?: CellPreviewItem[];
  isCurrent: boolean;
  isSelected: boolean;
  onClick: () => void;
}) {
  // Hover/focus preview state. Hooks must run unconditionally (an empty cell
  // returns early below), so they're declared first. The 120ms close delay
  // lets the pointer travel from the cell onto the popover without it closing
  // — same pattern as the provider calendar's MonthCell.
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const clearTimer = () => {
    if (closeTimer.current) {
      clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  };
  const scheduleClose = () => {
    clearTimer();
    closeTimer.current = setTimeout(() => setOpen(false), 120);
  };
  const handleEnter = () => {
    clearTimer();
    setOpen(true);
  };
  useEffect(() => clearTimer, []);

  if (!cell || cell.count === 0) {
    return (
      <div
        aria-hidden="true"
        className={
          "h-14 w-full rounded-md border " +
          (isSelected
            ? "ring-2 ring-[color:var(--border-focus)] "
            : isCurrent
              ? "border-[color:var(--border-focus)] bg-[color:var(--surface-brand-muted)]/20"
              : "border-[color:var(--border-subtle)]/40 bg-[color:var(--surface-page)]/30")
        }
      />
    );
  }
  const bucket = riskBucket(cell.worstRisk);
  const Icon = RISK_ICON[cell.worstRisk];
  const hasPreview = (preview?.length ?? 0) > 0;
  const previewTitle = `${MONTH_LABELS_ES[month]} · ${cell.count} ${cell.count === 1 ? "obligación" : "obligaciones"}`;

  return (
    <div
      className="relative"
      onMouseEnter={hasPreview ? handleEnter : undefined}
      onMouseLeave={hasPreview ? scheduleClose : undefined}
    >
      <button
        ref={buttonRef}
        type="button"
        onClick={onClick}
        onFocus={hasPreview ? handleEnter : undefined}
        onBlur={hasPreview ? scheduleClose : undefined}
        aria-pressed={isSelected}
        aria-label={`${rowName}: ${cell.count} ${cell.count === 1 ? "obligación" : "obligaciones"} en ${MONTH_LABELS_ES[month]}, estado ${RISK_LABEL[cell.worstRisk]}. Ver detalle.`}
        // Native title only when there's no rich popover (avoid a double tooltip).
        title={
          hasPreview
            ? undefined
            : `${MONTH_LABELS_ES[month]} · ${RISK_LABEL[cell.worstRisk]} · ${cell.count}`
        }
        className={
          "flex h-14 w-full flex-col items-center justify-center gap-0.5 rounded-md border transition-[transform,box-shadow] duration-150 ease-out hover:-translate-y-px hover:shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)] " +
          BUCKET_CELL[bucket] +
          (isSelected
            ? " ring-2 ring-[color:var(--border-focus)]"
            : isCurrent
              ? " ring-1 ring-[color:var(--border-focus)]"
              : "")
        }
      >
        <Icon className="h-4 w-4 shrink-0" weight="bold" aria-hidden="true" />
        <span className="font-mono text-sm font-semibold leading-none tabular-nums">
          {cell.count}
        </span>
      </button>
      {hasPreview ? (
        <MatrixCellPopover
          triggerRef={buttonRef}
          items={preview ?? []}
          title={previewTitle}
          open={open}
          onEnter={handleEnter}
          onLeave={scheduleClose}
        />
      ) : null}
    </div>
  );
}

function RowMonthsAccordion({
  row,
  cells,
  selected,
  onSelectCell,
  onSelectRow,
}: {
  row: ComplianceMatrixRow;
  cells: Map<string, ComplianceMatrixCell>;
  selected: ComplianceMatrixSelection;
  onSelectCell: (rowId: string, month: number) => void;
  onSelectRow?: (rowId: string) => void;
}) {
  const [open, setOpen] = useState(row.semaphore_level === "red");
  const months: { month: number; cell: ComplianceMatrixCell }[] = [];
  for (let month = 1; month <= 12; month += 1) {
    const cell = cells.get(`${row.id}-${month}`);
    if (cell && cell.count > 0) months.push({ month, cell });
  }
  const Caret = open ? CaretDown : CaretRight;
  return (
    <article className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-4 py-3 text-left"
      >
        <Caret
          className="h-3.5 w-3.5 shrink-0 text-[color:var(--text-tertiary)]"
          weight="bold"
          aria-hidden="true"
        />
        <span
          aria-hidden="true"
          className={"h-2.5 w-2.5 shrink-0 rounded-full " + dotClass(row.semaphore_level)}
        />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13px] font-medium text-[color:var(--text-primary)]">
            {row.name}
          </span>
          <span className="font-mono text-[10px] tabular-nums text-[color:var(--text-tertiary)]">
            {row.subtitle ? `${row.subtitle} · ` : ""}
            {months.length}{" "}
            {months.length === 1 ? "mes con vencimientos" : "meses con vencimientos"}
          </span>
        </span>
      </button>
      {open ? (
        <ul className="divide-y divide-[color:var(--border-subtle)] border-t border-[color:var(--border-subtle)]">
          {onSelectRow ? (
            <li>
              <button
                type="button"
                onClick={() => onSelectRow(row.id)}
                className="flex w-full items-center gap-2 px-4 py-2 text-left text-[12px] font-medium text-[color:var(--text-link)] hover:bg-[color:var(--surface-hover)]"
              >
                Ver detalle completo
              </button>
            </li>
          ) : null}
          {months.map(({ month, cell }) => {
            const Icon = RISK_ICON[cell.worstRisk];
            const isSel =
              selected?.rowId === row.id && selected?.month === month;
            return (
              <li key={month}>
                <button
                  type="button"
                  onClick={() => onSelectCell(row.id, month)}
                  aria-pressed={isSel}
                  className={
                    "flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-[color:var(--surface-hover)] " +
                    (isSel ? "bg-[color:var(--surface-selected)]" : "")
                  }
                >
                  <span className="w-10 shrink-0 font-mono text-[11px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                    {MONTH_LABELS_SHORT_ES[month - 1]}
                  </span>
                  <span
                    className={
                      "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium " +
                      BUCKET_CELL[riskBucket(cell.worstRisk)]
                    }
                  >
                    <Icon className="h-3 w-3" weight="bold" aria-hidden="true" />
                    {RISK_LABEL[cell.worstRisk]}
                  </span>
                  <span className="ml-auto font-mono text-[11px] tabular-nums text-[color:var(--text-secondary)]">
                    {cell.count}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
    </article>
  );
}
