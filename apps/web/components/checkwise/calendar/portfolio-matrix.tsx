"use client";

import { useState } from "react";
import Link from "next/link";
import { CaretDown, CaretRight } from "@phosphor-icons/react";

import type {
  ClientCalendarItem,
  ClientCalendarProvider,
} from "@/lib/api/client";
import {
  MONTH_LABELS_ES,
  MONTH_LABELS_SHORT_ES,
} from "@/lib/api/portal";
import { withReturnTo } from "@/lib/navigation/return-to";

import {
  BUCKET_CELL,
  RISK_ICON,
  RISK_LABEL,
  SEMAPHORE_DOT,
  riskBucket,
  worstRisk,
} from "./client-calendar-shared";

/**
 * Portfolio risk matrix — providers (rows, worst-first) × 12 months.
 * Each cell is tinted by the worst obligation state for that provider in
 * that month, so a client can spot the danger provider / danger month at
 * a glance. The agenda above answers "what do I do now"; this answers
 * "where is my year's risk". Clicking a populated cell opens the item
 * drawer for that cell's obligations.
 *
 * Desktop renders the grid (horizontally scrollable, sticky provider
 * column). Below lg the grid is impractical, so each provider becomes a
 * collapsible card listing the months that need attention.
 */
export function PortfolioMatrix({
  providers,
  itemsByCell,
  currentMonth,
  onOpenCell,
  returnToHref,
}: {
  providers: ClientCalendarProvider[];
  /** key = `${vendor_id}-${month}` (month 1-12). */
  itemsByCell: Map<string, ClientCalendarItem[]>;
  /** 1-12 when viewing the current year, else null. */
  currentMonth: number | null;
  onOpenCell: (items: ClientCalendarItem[]) => void;
  returnToHref: string;
}) {
  if (providers.length === 0) return null;
  return (
    <>
      {/* Desktop grid */}
      <div className="hidden overflow-x-auto lg:block">
        <table className="w-full table-fixed border-collapse text-sm">
          <colgroup>
            <col style={{ width: "200px" }} />
            {Array.from({ length: 12 }, (_, i) => (
              <col key={`mcol-${i}`} />
            ))}
          </colgroup>
          <thead>
            <tr className="border-b border-[color:var(--border-subtle)]">
              <th
                scope="col"
                className="sticky left-0 z-10 border-r border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)] px-3 py-2 text-left font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]"
              >
                Proveedor
              </th>
              {MONTH_LABELS_SHORT_ES.map((m, idx) => {
                const isCurrent = currentMonth === idx + 1;
                return (
                  <th
                    key={m}
                    scope="col"
                    aria-current={isCurrent ? "true" : undefined}
                    className={
                      "px-1 py-2 text-center font-mono text-[10px] uppercase tracking-wide " +
                      (isCurrent
                        ? "text-[color:var(--text-brand)]"
                        : "text-[color:var(--text-tertiary)]")
                    }
                  >
                    {m}
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
                  className="sticky left-0 z-10 border-r border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)] px-3 py-2 text-left align-middle"
                >
                  <ProviderLabel provider={p} returnToHref={returnToHref} />
                </th>
                {Array.from({ length: 12 }, (_, monthIdx) => {
                  const month = monthIdx + 1;
                  const cellItems =
                    itemsByCell.get(`${p.vendor_id}-${month}`) ?? [];
                  return (
                    <td key={month} className="p-1 align-middle">
                      <MatrixCell
                        items={cellItems}
                        month={month}
                        vendorName={p.vendor_name}
                        isCurrent={currentMonth === month}
                        onOpen={() => onOpenCell(cellItems)}
                      />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile: per-provider accordion of months needing attention */}
      <div className="space-y-2 lg:hidden">
        {providers.map((p) => (
          <ProviderAccordion
            key={p.vendor_id}
            provider={p}
            itemsByCell={itemsByCell}
            onOpenCell={onOpenCell}
            returnToHref={returnToHref}
          />
        ))}
      </div>
    </>
  );
}

function ProviderLabel({
  provider,
  returnToHref,
}: {
  provider: ClientCalendarProvider;
  returnToHref: string;
}) {
  return (
    <Link
      href={withReturnTo(`/client/vendors/${provider.vendor_id}`, returnToHref)}
      className="group block"
      title={`Abrir expediente · ${provider.compliance_pct}% al día`}
    >
      <span className="flex items-center gap-1.5">
        <span
          aria-hidden="true"
          className={
            "h-2 w-2 shrink-0 rounded-full " +
            SEMAPHORE_DOT[provider.semaphore_level]
          }
        />
        <span className="truncate text-[12px] font-medium text-[color:var(--text-primary)] group-hover:text-[color:var(--text-brand)] group-hover:underline">
          {provider.vendor_name}
        </span>
      </span>
      <span className="mt-0.5 block pl-3.5 font-mono text-[10px] tabular-nums text-[color:var(--text-tertiary)]">
        {provider.compliance_pct}% al día
      </span>
    </Link>
  );
}

function MatrixCell({
  items,
  month,
  vendorName,
  isCurrent,
  onOpen,
}: {
  items: ClientCalendarItem[];
  month: number;
  vendorName: string;
  isCurrent: boolean;
  onOpen: () => void;
}) {
  if (items.length === 0) {
    return (
      <div
        aria-hidden="true"
        className={
          "h-10 w-full rounded-[6px] border " +
          (isCurrent
            ? "border-[color:var(--border-focus)] bg-[color:var(--surface-brand-muted)]/20"
            : "border-[color:var(--border-subtle)]/50 bg-[color:var(--surface-page)]/40")
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
      onClick={onOpen}
      aria-label={`${vendorName}: ${items.length} ${items.length === 1 ? "obligación" : "obligaciones"} en ${MONTH_LABELS_ES[month]}, estado ${RISK_LABEL[worst]}`}
      title={`${MONTH_LABELS_ES[month]} · ${RISK_LABEL[worst]} · ${items.length}`}
      className={
        "flex h-10 w-full items-center justify-center gap-1 rounded-[6px] border transition-[transform,box-shadow] duration-150 ease-out hover:-translate-y-px hover:shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)] " +
        BUCKET_CELL[bucket] +
        (isCurrent ? " ring-1 ring-[color:var(--border-focus)]" : "")
      }
    >
      <Icon className="h-3.5 w-3.5 shrink-0" weight="bold" aria-hidden="true" />
      <span className="font-mono text-[11px] font-semibold tabular-nums">
        {items.length}
      </span>
    </button>
  );
}

function ProviderAccordion({
  provider,
  itemsByCell,
  onOpenCell,
  returnToHref,
}: {
  provider: ClientCalendarProvider;
  itemsByCell: Map<string, ClientCalendarItem[]>;
  onOpenCell: (items: ClientCalendarItem[]) => void;
  returnToHref: string;
}) {
  const [open, setOpen] = useState(provider.semaphore_level === "red");
  // Months that need attention (worst risk is not "al día" / "próxima").
  const attentionMonths: { month: number; items: ClientCalendarItem[] }[] = [];
  for (let month = 1; month <= 12; month += 1) {
    const items = itemsByCell.get(`${provider.vendor_id}-${month}`) ?? [];
    if (items.length === 0) continue;
    const worst = worstRisk(items) ?? "on_track";
    const bucket = riskBucket(worst);
    if (bucket === "ok" || bucket === "upcoming") continue;
    attentionMonths.push({ month, items });
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
            {provider.compliance_pct}% al día · {attentionMonths.length}{" "}
            {attentionMonths.length === 1 ? "mes por atender" : "meses por atender"}
          </span>
        </span>
      </button>
      {open ? (
        attentionMonths.length === 0 ? (
          <div className="border-t border-[color:var(--border-subtle)] px-4 py-3">
            <p className="text-xs text-[color:var(--text-secondary)]">
              Sin pendientes este año.{" "}
              <Link
                href={withReturnTo(
                  `/client/vendors/${provider.vendor_id}`,
                  returnToHref,
                )}
                className="font-medium text-[color:var(--text-brand)] hover:underline"
              >
                Ver expediente
              </Link>
            </p>
          </div>
        ) : (
          <ul className="divide-y divide-[color:var(--border-subtle)] border-t border-[color:var(--border-subtle)]">
            {attentionMonths.map(({ month, items }) => {
              const worst = worstRisk(items) ?? "on_track";
              const Icon = RISK_ICON[worst];
              return (
                <li key={month}>
                  <button
                    type="button"
                    onClick={() => onOpenCell(items)}
                    className="flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-[color:var(--surface-hover)]"
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
        )
      ) : null}
    </article>
  );
}
