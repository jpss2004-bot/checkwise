"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Buildings,
  CalendarBlank,
  CaretDown,
  CaretRight,
  House,
  Package,
  Scales,
  ShieldCheck,
  type Icon,
} from "@phosphor-icons/react";

import {
  MiniBars,
  StackedBars,
  type ChartSegment,
} from "@/components/checkwise/charts";
import { Surface } from "@/components/checkwise/dashboard/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { MetadataStrip } from "@/components/ui/metadata-strip";
import {
  ErrorState,
  Skeleton,
} from "@/components/checkwise/portal/state-surfaces";

import { ClientShell } from "../_shell";
import { VendorRef } from "@/components/checkwise/vendor-ref";
import {
  getClientCalendar,
  listClientVendors,
  type ClientCalendar,
  type ClientCalendarItem,
  type ClientCalendarMonth,
  type ClientVendorListResponse,
} from "@/lib/api/client";
import { INSTITUTION_LABELS } from "@/lib/api/portal";

const MONTH_SHORT = [
  "Ene",
  "Feb",
  "Mar",
  "Abr",
  "May",
  "Jun",
  "Jul",
  "Ago",
  "Sep",
  "Oct",
  "Nov",
  "Dic",
];

// Junta 2026-05-23 — institution icons mirror the portal calendar
// so the client view reads with the same visual vocabulary the
// provider already uses. House (vivienda) for INFONAVIT is the
// disambiguator from IMSS (Buildings) per the audit follow-up.
const INSTITUTION_ICON: Record<string, Icon> = {
  sat: Scales,
  imss: Buildings,
  infonavit: House,
  stps_repse: ShieldCheck,
};

const INSTITUTION_ORDER = ["sat", "imss", "infonavit", "stps_repse"] as const;

// Spanish labels for the status enum used inside the expanded row.
// Centralised here so any future status surface on this page stays
// in lockstep with the rest of the product.
const STATUS_LABEL: Record<string, string> = {
  aprobado: "Aprobado",
  rechazado: "Requiere corrección",
  requiere_aclaracion: "Necesita aclaración",
  pendiente_revision: "En revisión",
  posible_mismatch: "Posible inconsistencia",
  prevalidado: "Prevalidado",
  recibido: "Recibido",
  vencido: "Vencido",
  no_aplica: "No aplica",
  pendiente: "Pendiente",
  excepcion_legal: "Excepción legal",
};

function statusVariant(
  status: string,
): "success" | "warning" | "destructive" | "info" | "secondary" {
  if (status === "aprobado" || status === "excepcion_legal") return "success";
  if (status === "rechazado" || status === "vencido") return "destructive";
  if (
    status === "requiere_aclaracion" ||
    status === "posible_mismatch" ||
    status === "pendiente_revision" ||
    status === "prevalidado" ||
    status === "recibido"
  ) {
    return "warning";
  }
  return "secondary";
}

export default function ClientCalendarPage() {
  const [year, setYear] = useState(new Date().getFullYear() || 2026);
  const [data, setData] = useState<ClientCalendar | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandedMonth, setExpandedMonth] = useState<number | null>(null);
  // Item 3 — vendor multi-select. Empty list = portfolio-wide view.
  const [vendorFilter, setVendorFilter] = useState<string[]>([]);
  const [vendorsList, setVendorsList] =
    useState<ClientVendorListResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    listClientVendors()
      .then((res) => {
        if (!cancelled) setVendorsList(res);
      })
      .catch(() => {
        if (!cancelled) setVendorsList({ items: [], total: 0 } as never);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    getClientCalendar({ year, vendor_ids: vendorFilter })
      .then((cal) => {
        if (!cancelled) setData(cal);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Error al cargar calendario.");
      });
    return () => {
      cancelled = true;
    };
  }, [year, vendorFilter]);

  function toggleVendor(id: string) {
    setVendorFilter((prev) =>
      prev.includes(id) ? prev.filter((v) => v !== id) : [...prev, id],
    );
  }

  const totals = useMemo(() => {
    if (!data) return { due: 0, approved: 0, pending: 0, missing: 0, rejected: 0, dueSoon: 0 };
    return data.months.reduce(
      (acc, m) => {
        acc.due += m.due_total;
        acc.approved += m.approved_total;
        acc.pending += m.pending_total;
        acc.missing += m.missing_total;
        acc.rejected += m.rejected_or_correction_total;
        acc.dueSoon += m.due_soon_total;
        return acc;
      },
      { due: 0, approved: 0, pending: 0, missing: 0, rejected: 0, dueSoon: 0 },
    );
  }, [data]);

  const barsApproved = useMemo(() => {
    if (!data) return [];
    return data.months.map((m) => ({
      label: MONTH_SHORT[m.month - 1] ?? `${m.month}`,
      value: m.approved_total,
      tone: "success" as const,
    }));
  }, [data]);

  const barsMissing = useMemo(() => {
    if (!data) return [];
    return data.months.map((m) => ({
      label: MONTH_SHORT[m.month - 1] ?? `${m.month}`,
      value: m.missing_total + m.rejected_or_correction_total,
      tone: "warning" as const,
    }));
  }, [data]);

  return (
    <ClientShell
      title="Calendario del cliente"
      description="Cumplimiento mensual agregado de todos los proveedores bajo este cliente."
      actions={
        <label className="flex items-center gap-2 rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-3 py-1 text-xs">
          <CalendarBlank
            className="h-3.5 w-3.5 text-[color:var(--text-secondary)]"
            weight="bold"
            aria-hidden="true"
          />
          <span className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
            Año
          </span>
          <Input
            type="number"
            // REPSE compliance starts in 2021. Match backend MIN_YEAR=2021
            // (apps/api/app/core/period_validation.py) instead of the prior
            // 2024 floor which silently blocked 2021-2023 historical
            // periods that the API otherwise serves.
            min={2021}
            max={2030}
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
            className="h-7 w-20 border-0 bg-transparent p-0 font-mono text-sm font-semibold focus-visible:ring-0"
          />
        </label>
      }
    >
      {error ? (
        <ErrorState
          title="No pudimos cargar el calendario"
          description={error}
          onRetry={() => setYear((y) => y)}
        />
      ) : !data ? (
        <CalendarSkeleton />
      ) : (
        <div className="space-y-6">
          <MetadataStrip
            items={[
              { label: "Año", value: data.year.toString(), mono: true },
              { label: "Obligaciones", value: totals.due.toString(), mono: true },
              { label: "Aprobadas", value: totals.approved.toString(), mono: true, tone: "teal" },
              { label: "Pendientes", value: totals.pending.toString(), mono: true },
              {
                label: "Faltantes+Rechazos",
                value: (totals.missing + totals.rejected).toString(),
                mono: true,
                tone: totals.missing + totals.rejected > 0 ? "warning" : "default",
              },
              { label: "Vencen ≤14d", value: totals.dueSoon.toString(), mono: true, tone: totals.dueSoon > 0 ? "warning" : "default" },
            ]}
          />

          <Surface
            title="Filtrar por proveedor"
            description={
              vendorFilter.length === 0
                ? "Mostrando todos los proveedores del portafolio. Toca un proveedor para acotar el calendario a sus obligaciones."
                : `Filtrando por ${vendorFilter.length} proveedor${vendorFilter.length === 1 ? "" : "es"}.`
            }
            actions={
              vendorFilter.length > 0 ? (
                <button
                  type="button"
                  className="text-xs font-medium text-[color:var(--text-brand)] hover:underline"
                  onClick={() => setVendorFilter([])}
                >
                  Limpiar filtro
                </button>
              ) : null
            }
          >
            <div className="flex flex-wrap gap-2">
              {(vendorsList?.items ?? []).map((v) => {
                const active = vendorFilter.includes(v.vendor_id);
                return (
                  <button
                    type="button"
                    key={v.vendor_id}
                    onClick={() => toggleVendor(v.vendor_id)}
                    aria-pressed={active}
                    className={
                      "rounded-full border px-3 py-1.5 text-xs font-medium transition " +
                      (active
                        ? "border-[color:var(--interactive-primary)] bg-[color:var(--surface-brand-muted)] text-[color:var(--text-brand)]"
                        : "border-[color:var(--border-default)] bg-[color:var(--surface-raised)] text-[color:var(--text-secondary)] hover:border-[color:var(--border-strong)]")
                    }
                  >
                    {v.vendor_name}
                  </button>
                );
              })}
              {vendorsList && vendorsList.items.length === 0 ? (
                <p className="text-xs text-[color:var(--text-tertiary)]">
                  Aún no tienes proveedores registrados.
                </p>
              ) : null}
            </div>
          </Surface>

          <Surface
            title="Ritmo anual"
            description="Distribución mensual de obligaciones aprobadas vs. faltantes."
          >
            <div className="grid gap-6 md:grid-cols-2">
              <div>
                <p className="cw-eyebrow mb-2">Aprobadas por mes</p>
                <MiniBars data={barsApproved} height={100} showValues />
              </div>
              <div>
                <p className="cw-eyebrow mb-2">Faltantes + rechazos por mes</p>
                <MiniBars data={barsMissing} height={100} showValues />
              </div>
            </div>
          </Surface>

          <Surface
            title="Detalle por mes"
            description="Toca una fila para ver el detalle por proveedor y empaquetarlo para auditoría."
            bodyClassName="p-0 overflow-x-auto"
          >
            <table className="w-full text-sm">
              <thead className="border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] text-left font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                <tr>
                  <th className="px-4 py-2.5">Mes</th>
                  <th className="px-3 py-2.5">Instituciones</th>
                  <th className="px-3 py-2.5 text-right">Proveedores</th>
                  <th className="px-3 py-2.5 text-right">Total</th>
                  <th className="px-3 py-2.5">Distribución</th>
                  <th className="px-3 py-2.5 text-right">Vencen ≤14d</th>
                  <th className="px-3 py-2.5 text-right" aria-label="Acciones" />
                </tr>
              </thead>
              <tbody>
                {data.months.map((m) => (
                  <MonthRow
                    key={m.month}
                    month={m}
                    year={data.year}
                    expanded={expandedMonth === m.month}
                    onToggle={() =>
                      setExpandedMonth((prev) =>
                        prev === m.month ? null : m.month,
                      )
                    }
                  />
                ))}
              </tbody>
            </table>
          </Surface>
        </div>
      )}
    </ClientShell>
  );
}

function MonthRow({
  month,
  year,
  expanded,
  onToggle,
}: {
  month: ClientCalendarMonth;
  year: number;
  expanded: boolean;
  onToggle: () => void;
}) {
  const segments: ChartSegment[] = [
    { label: "Aprobados", value: month.approved_total, tone: "success" },
    { label: "Pendientes", value: month.pending_total, tone: "info" },
    { label: "Rechazos", value: month.rejected_or_correction_total, tone: "error" },
    { label: "Faltantes", value: month.missing_total, tone: "warning" },
  ];

  // Per-institution count for the month. Built off ``items[]`` so it
  // stays in sync with the same data driving the expanded panel.
  const institutionCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const item of month.items) {
      counts[item.institution] = (counts[item.institution] ?? 0) + 1;
    }
    return counts;
  }, [month.items]);

  const periodKey = `${year}-M${String(month.month).padStart(2, "0")}`;
  const auditUrl = `/client/auditoria?period_from=${periodKey}&period_to=${periodKey}`;
  const Caret = expanded ? CaretDown : CaretRight;

  return (
    <>
      <tr
        className="cursor-pointer border-b border-[color:var(--border-subtle)] last:border-0 hover:bg-[color:var(--surface-hover)]"
        onClick={onToggle}
        aria-expanded={expanded}
        role="button"
      >
        <td className="px-4 py-3 font-medium text-[color:var(--text-primary)]">
          <span className="inline-flex items-center gap-2">
            <Caret
              className="h-3.5 w-3.5 text-[color:var(--text-tertiary)]"
              weight="bold"
              aria-hidden="true"
            />
            {month.month_label}
          </span>
        </td>
        <td className="px-3 py-3">
          <div className="flex flex-wrap items-center gap-1.5">
            {INSTITUTION_ORDER.map((code) => {
              const count = institutionCounts[code] ?? 0;
              if (count === 0) return null;
              const IconComponent = INSTITUTION_ICON[code];
              return (
                <span
                  key={code}
                  className="inline-flex items-center gap-1 rounded-full border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] px-2 py-0.5 text-[11px] font-medium text-[color:var(--text-secondary)]"
                  title={`${INSTITUTION_LABELS[code] ?? code} · ${count}`}
                >
                  {IconComponent ? (
                    <IconComponent
                      className="h-3 w-3 text-[color:var(--text-brand)]"
                      weight="bold"
                      aria-hidden="true"
                    />
                  ) : null}
                  <span>{INSTITUTION_LABELS[code] ?? code}</span>
                  <span className="font-mono tabular-nums text-[10px] text-[color:var(--text-tertiary)]">
                    {count}
                  </span>
                </span>
              );
            })}
            {Object.keys(institutionCounts).length === 0 ? (
              <span className="text-[11px] text-[color:var(--text-tertiary)]">
                Sin obligaciones este mes
              </span>
            ) : null}
          </div>
        </td>
        <td className="px-3 py-3 text-right font-mono tabular-nums text-[color:var(--text-primary)]">
          {month.vendors_total}
        </td>
        <td className="px-3 py-3 text-right font-mono tabular-nums text-[color:var(--text-primary)]">
          {month.due_total}
        </td>
        <td className="min-w-[260px] px-3 py-3">
          <StackedBars segments={segments} height={10} />
        </td>
        <td className="px-3 py-3 text-right font-mono tabular-nums text-[color:var(--text-primary)]">
          {month.due_soon_total}
        </td>
        <td className="px-3 py-3 text-right">
          <Button
            asChild
            size="sm"
            variant="outline"
            onClick={(e) => e.stopPropagation()}
            disabled={month.due_total === 0}
          >
            <Link
              href={auditUrl}
              title="Pre-llena la página de paquete para auditoría con este mes"
            >
              <Package className="h-3 w-3" weight="bold" aria-hidden="true" />
              Paquete
            </Link>
          </Button>
        </td>
      </tr>
      {expanded ? (
        <tr className="border-b border-[color:var(--border-subtle)] last:border-0 bg-[color:var(--surface-sunken)]">
          <td colSpan={7} className="px-4 py-3">
            <ExpandedDetail items={month.items} />
          </td>
        </tr>
      ) : null}
    </>
  );
}

function ExpandedDetail({ items }: { items: ClientCalendarItem[] }) {
  if (items.length === 0) {
    return (
      <p className="text-xs text-[color:var(--text-tertiary)]">
        Este mes no tiene obligaciones registradas en el calendario.
      </p>
    );
  }
  // Group by vendor so the expanded section reads "proveedor X tiene
  // estos requisitos" — the mental model an auditor walks through.
  const byVendor = new Map<string, { vendor_name: string; rows: ClientCalendarItem[] }>();
  for (const item of items) {
    const key = item.vendor_id;
    if (!byVendor.has(key)) {
      byVendor.set(key, { vendor_name: item.vendor_name, rows: [] });
    }
    byVendor.get(key)!.rows.push(item);
  }
  const groups = Array.from(byVendor.values()).sort((a, b) =>
    a.vendor_name.localeCompare(b.vendor_name, "es"),
  );
  return (
    <div className="space-y-4">
      {groups.map((g) => (
        <div key={g.vendor_name}>
          <div className="mb-2 flex items-center justify-between">
            <p className="text-xs font-semibold uppercase tracking-wide text-[color:var(--text-secondary)]">
              <VendorRef
                vendorId={g.rows[0].vendor_id}
                vendorName={g.vendor_name}
              />
            </p>
            <Link
              href={`/client/vendors/${g.rows[0].vendor_id}`}
              className="text-[11px] font-medium text-[color:var(--text-brand)] hover:underline"
              title="Abrir el expediente del proveedor"
            >
              Ver expediente →
            </Link>
          </div>
          <ul className="divide-y divide-[color:var(--border-subtle)] rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)]">
            {g.rows.map((row) => {
              const inst = INSTITUTION_LABELS[row.institution] ?? row.institution;
              const IconComponent = INSTITUTION_ICON[row.institution];
              const statusText = STATUS_LABEL[row.status] ?? row.status;
              return (
                <li
                  key={`${row.vendor_id}-${row.requirement_code ?? row.requirement_name}-${row.period_key ?? ""}`}
                  className="flex flex-wrap items-center justify-between gap-3 px-3 py-2 text-xs"
                >
                  <div className="flex min-w-0 items-center gap-2">
                    {IconComponent ? (
                      <IconComponent
                        className="h-3.5 w-3.5 shrink-0 text-[color:var(--text-brand)]"
                        weight="bold"
                        aria-hidden="true"
                      />
                    ) : null}
                    <span className="font-medium text-[color:var(--text-primary)]">
                      {row.requirement_name}
                    </span>
                    <span className="text-[color:var(--text-tertiary)]">·</span>
                    <span className="text-[color:var(--text-secondary)]">{inst}</span>
                    <span className="text-[color:var(--text-tertiary)]">·</span>
                    <span className="font-mono text-[10px] text-[color:var(--text-tertiary)]">
                      {row.period_label}
                    </span>
                  </div>
                  <Badge variant={statusVariant(row.status)}>{statusText}</Badge>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
}

function CalendarSkeleton() {
  return (
    <div className="space-y-5" aria-busy="true" aria-live="polite">
      <span className="sr-only">Cargando calendario…</span>
      <Skeleton className="h-12 w-full rounded-md" />
      <Skeleton className="h-56 w-full rounded-lg" />
      <Skeleton className="h-80 w-full rounded-lg" />
    </div>
  );
}
