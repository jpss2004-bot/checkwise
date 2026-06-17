"use client";

import { useState } from "react";
import { CaretDown, CaretRight } from "@phosphor-icons/react";

import type {
  ClientCalendarItem,
  ClientCalendarProvider,
} from "@/lib/api/client";
import { MONTH_LABELS_ES, MONTH_LABELS_SHORT_ES } from "@/lib/api/portal";

import {
  BUCKET_CELL,
  RISK_ICON,
  RISK_LABEL,
  SEMAPHORE_DOT,
  riskBucket,
  worstRisk,
  type RiskBucket,
} from "./client-calendar-shared";

/**
 * The client calendar itself: providers (rows, worst-first) × 12 months.
 * The meaningful unit of REPSE time is the month (≈every deadline lands on
 * the 17th), so the grid IS the calendar. Tap a cell for one provider's
 * month, or a month header for the whole portfolio that month; either
 * selection renders in detail below, grouped by provider.
 *
 * Desktop shows the grid; below lg each provider becomes a collapsible row
 * of its active months, since a 13-column grid can't breathe on a phone.
 */

const LEGEND: { bucket: RiskBucket; label: string }[] = [
  { bucket: "critical", label: "Vencido / por corregir" },
  { bucket: "soon", label: "Vence pronto" },
  { bucket: "review", label: "En revisión" },
  { bucket: "upcoming", label: "Próximo" },
  { bucket: "ok", label: "Al día" },
];

type Selected = { month: number; vendorId: string | null } | null;

export function PortfolioMatrix({
  providers,
  itemsByCell,
  currentMonth,
  selected,
  onSelectCell,
  onSelectMonth,
}: {
  providers: ClientCalendarProvider[];
  /** key = `${vendor_id}-${month}` (month 1-12). */
  itemsByCell: Map<string, ClientCalendarItem[]>;
  currentMonth: number | null;
  selected: Selected;
  onSelectCell: (vendorId: string, month: number) => void;
  onSelectMonth: (month: number) => void;
}) {
  if (providers.length === 0) return null;

  const monthTotals = Array.from({ length: 12 }, (_, i) => {
    const month = i + 1;
    let count = 0;
    for (const p of providers) {
      count += itemsByCell.get(`${p.vendor_id}-${month}`)?.length ?? 0;
    }
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
                Proveedor
              </th>
              {MONTH_LABELS_SHORT_ES.map((m, idx) => {
                const month = idx + 1;
                const isCurrent = currentMonth === month;
                const isSelMonth =
                  selected?.vendorId === null && selected?.month === month;
                const total = monthTotals[idx];
                return (
                  <th key={m} scope="col" className="px-1 pb-1.5 pt-1">
                    <button
                      type="button"
                      onClick={() => onSelectMonth(month)}
                      aria-pressed={isSelMonth}
                      title={`Ver ${MONTH_LABELS_ES[month]} en todo el portafolio`}
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
            {providers.map((p) => (
              <tr
                key={p.vendor_id}
                className="border-b border-[color:var(--border-subtle)] last:border-0"
              >
                <th
                  scope="row"
                  className="sticky left-0 z-10 bg-[color:var(--surface-raised)] px-3 py-2 text-left align-middle"
                >
                  <span className="flex items-center gap-2">
                    <span
                      aria-hidden="true"
                      className={
                        "h-2.5 w-2.5 shrink-0 rounded-full " +
                        SEMAPHORE_DOT[p.semaphore_level]
                      }
                    />
                    <span className="min-w-0">
                      <span className="block truncate text-[13px] font-medium text-[color:var(--text-primary)]">
                        {p.vendor_name}
                      </span>
                      <span className="font-mono text-[11px] tabular-nums text-[color:var(--text-tertiary)]">
                        {p.compliance_pct}% al día
                      </span>
                    </span>
                  </span>
                </th>
                {Array.from({ length: 12 }, (_, monthIdx) => {
                  const month = monthIdx + 1;
                  const cellItems =
                    itemsByCell.get(`${p.vendor_id}-${month}`) ?? [];
                  const isSel =
                    selected?.vendorId === p.vendor_id &&
                    selected?.month === month;
                  return (
                    <td key={month} className="p-1 align-middle">
                      <MatrixCell
                        items={cellItems}
                        month={month}
                        vendorName={p.vendor_name}
                        isCurrent={currentMonth === month}
                        isSelected={isSel}
                        onClick={() => onSelectCell(p.vendor_id, month)}
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

      {/* Mobile: per-provider accordion of active months */}
      <div className="space-y-2 lg:hidden">
        {providers.map((p) => (
          <ProviderMonthsAccordion
            key={p.vendor_id}
            provider={p}
            itemsByCell={itemsByCell}
            selected={selected}
            onSelectCell={onSelectCell}
          />
        ))}
      </div>
    </div>
  );
}

function MatrixCell({
  items,
  month,
  vendorName,
  isCurrent,
  isSelected,
  onClick,
}: {
  items: ClientCalendarItem[];
  month: number;
  vendorName: string;
  isCurrent: boolean;
  isSelected: boolean;
  onClick: () => void;
}) {
  if (items.length === 0) {
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
  const worst = worstRisk(items) ?? "on_track";
  const bucket = riskBucket(worst);
  const Icon = RISK_ICON[worst];
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={isSelected}
      aria-label={`${vendorName}: ${items.length} ${items.length === 1 ? "obligación" : "obligaciones"} en ${MONTH_LABELS_ES[month]}, estado ${RISK_LABEL[worst]}. Ver detalle.`}
      title={`${MONTH_LABELS_ES[month]} · ${RISK_LABEL[worst]} · ${items.length}`}
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
        {items.length}
      </span>
    </button>
  );
}

function ProviderMonthsAccordion({
  provider,
  itemsByCell,
  selected,
  onSelectCell,
}: {
  provider: ClientCalendarProvider;
  itemsByCell: Map<string, ClientCalendarItem[]>;
  selected: Selected;
  onSelectCell: (vendorId: string, month: number) => void;
}) {
  const [open, setOpen] = useState(provider.semaphore_level === "red");
  const months: { month: number; items: ClientCalendarItem[] }[] = [];
  for (let month = 1; month <= 12; month += 1) {
    const items = itemsByCell.get(`${provider.vendor_id}-${month}`) ?? [];
    if (items.length > 0) months.push({ month, items });
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
          className={
            "h-2.5 w-2.5 shrink-0 rounded-full " +
            SEMAPHORE_DOT[provider.semaphore_level]
          }
        />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13px] font-medium text-[color:var(--text-primary)]">
            {provider.vendor_name}
          </span>
          <span className="font-mono text-[10px] tabular-nums text-[color:var(--text-tertiary)]">
            {provider.compliance_pct}% al día · {months.length}{" "}
            {months.length === 1 ? "mes con vencimientos" : "meses con vencimientos"}
          </span>
        </span>
      </button>
      {open ? (
        <ul className="divide-y divide-[color:var(--border-subtle)] border-t border-[color:var(--border-subtle)]">
          {months.map(({ month, items }) => {
            const worst = worstRisk(items) ?? "on_track";
            const Icon = RISK_ICON[worst];
            const isSel =
              selected?.vendorId === provider.vendor_id &&
              selected?.month === month;
            return (
              <li key={month}>
                <button
                  type="button"
                  onClick={() => onSelectCell(provider.vendor_id, month)}
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
                      BUCKET_CELL[riskBucket(worst)]
                    }
                  >
                    <Icon className="h-3 w-3" weight="bold" aria-hidden="true" />
                    {RISK_LABEL[worst]}
                  </span>
                  <span className="ml-auto font-mono text-[11px] tabular-nums text-[color:var(--text-secondary)]">
                    {items.length}
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
