"use client";

import type {
  ClientCalendarItem,
  ClientCalendarProvider,
} from "@/lib/api/client";
import {
  MONTH_LABELS_ES,
  MONTH_LABELS_SHORT_ES,
} from "@/lib/api/portal";

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
 * Portfolio risk overview — providers (rows, worst-first) × 12 months.
 * Each cell is tinted by the worst obligation state for that provider in
 * that month, so the client can scan where the year's risk concentrates.
 * Clicking a cell or a provider jumps to that provider's detailed review
 * card below. Desktop-only: below lg the provider cards (with their own
 * summaries) carry the overview, so there's no cramped grid on a phone.
 */

const LEGEND: { bucket: RiskBucket; label: string }[] = [
  { bucket: "critical", label: "Vencido / por corregir" },
  { bucket: "soon", label: "Vence pronto" },
  { bucket: "review", label: "En revisión" },
  { bucket: "upcoming", label: "Próximo" },
  { bucket: "ok", label: "Al día" },
];

export function PortfolioMatrix({
  providers,
  itemsByCell,
  currentMonth,
  onSelectProvider,
}: {
  providers: ClientCalendarProvider[];
  /** key = `${vendor_id}-${month}` (month 1-12). */
  itemsByCell: Map<string, ClientCalendarItem[]>;
  /** 1-12 when viewing the current year, else null. */
  currentMonth: number | null;
  onSelectProvider: (vendorId: string) => void;
}) {
  if (providers.length === 0) return null;
  return (
    <div className="hidden lg:block">
      <div className="overflow-x-auto">
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
                className="sticky left-0 z-10 bg-[color:var(--surface-raised)] px-3 py-2.5 text-left text-xs font-semibold text-[color:var(--text-secondary)]"
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
                      "px-1 py-2.5 text-center text-[11px] font-medium uppercase tracking-wide " +
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
                  className="sticky left-0 z-10 bg-[color:var(--surface-raised)] px-3 py-2 text-left align-middle"
                >
                  <button
                    type="button"
                    onClick={() => onSelectProvider(p.vendor_id)}
                    className="group flex w-full items-center gap-2 text-left"
                    title={`Ver el detalle de ${p.vendor_name}`}
                  >
                    <span
                      aria-hidden="true"
                      className={
                        "h-2.5 w-2.5 shrink-0 rounded-full " +
                        SEMAPHORE_DOT[p.semaphore_level]
                      }
                    />
                    <span className="min-w-0">
                      <span className="block truncate text-[13px] font-medium text-[color:var(--text-primary)] group-hover:text-[color:var(--text-brand)] group-hover:underline">
                        {p.vendor_name}
                      </span>
                      <span className="font-mono text-[11px] tabular-nums text-[color:var(--text-tertiary)]">
                        {p.compliance_pct}% al día
                      </span>
                    </span>
                  </button>
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
                        onClick={() => onSelectProvider(p.vendor_id)}
                      />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

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
  );
}

function MatrixCell({
  items,
  month,
  vendorName,
  isCurrent,
  onClick,
}: {
  items: ClientCalendarItem[];
  month: number;
  vendorName: string;
  isCurrent: boolean;
  onClick: () => void;
}) {
  if (items.length === 0) {
    return (
      <div
        aria-hidden="true"
        className={
          "h-12 w-full rounded-md border " +
          (isCurrent
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
      aria-label={`${vendorName}: ${items.length} ${items.length === 1 ? "obligación" : "obligaciones"} en ${MONTH_LABELS_ES[month]}, estado ${RISK_LABEL[worst]}. Ver detalle.`}
      title={`${MONTH_LABELS_ES[month]} · ${RISK_LABEL[worst]} · ${items.length}`}
      className={
        "flex h-12 w-full flex-col items-center justify-center gap-0.5 rounded-md border transition-[transform,box-shadow] duration-150 ease-out hover:-translate-y-px hover:shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)] " +
        BUCKET_CELL[bucket] +
        (isCurrent ? " ring-1 ring-[color:var(--border-focus)]" : "")
      }
    >
      <Icon className="h-4 w-4 shrink-0" weight="bold" aria-hidden="true" />
      <span className="font-mono text-[11px] font-semibold leading-none tabular-nums">
        {items.length}
      </span>
    </button>
  );
}
