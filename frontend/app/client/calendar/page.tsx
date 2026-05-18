"use client";

import { useEffect, useMemo, useState } from "react";
import { CalendarBlank } from "@phosphor-icons/react";

import {
  MiniBars,
  StackedBars,
  type ChartSegment,
} from "@/components/checkwise/charts";
import { Surface } from "@/components/checkwise/dashboard/stat-card";
import { Input } from "@/components/ui/input";
import { MetadataStrip } from "@/components/ui/metadata-strip";
import {
  ErrorState,
  Skeleton,
} from "@/components/checkwise/portal/state-surfaces";

import { ClientShell } from "../_shell";
import { getClientCalendar, type ClientCalendar } from "@/lib/api/client";

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

export default function ClientCalendarPage() {
  const [year, setYear] = useState(new Date().getFullYear() || 2026);
  const [data, setData] = useState<ClientCalendar | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    getClientCalendar({ year })
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
  }, [year]);

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
            min={2024}
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
            bodyClassName="p-0 overflow-x-auto"
          >
            <table className="w-full text-sm">
              <thead className="border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] text-left font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                <tr>
                  <th className="px-4 py-2.5">Mes</th>
                  <th className="px-3 py-2.5 text-right">Proveedores</th>
                  <th className="px-3 py-2.5 text-right">Total</th>
                  <th className="px-3 py-2.5">Distribución</th>
                  <th className="px-3 py-2.5 text-right">Vencen ≤14d</th>
                </tr>
              </thead>
              <tbody>
                {data.months.map((m) => {
                  const segments: ChartSegment[] = [
                    { label: "Aprobados", value: m.approved_total, tone: "success" },
                    { label: "Pendientes", value: m.pending_total, tone: "info" },
                    {
                      label: "Rechazos",
                      value: m.rejected_or_correction_total,
                      tone: "error",
                    },
                    { label: "Faltantes", value: m.missing_total, tone: "warning" },
                  ];
                  return (
                    <tr
                      key={m.month}
                      className="border-b border-[color:var(--border-subtle)] last:border-0 hover:bg-[color:var(--surface-hover)]"
                    >
                      <td className="px-4 py-3 font-medium text-[color:var(--text-primary)]">
                        {m.month_label}
                      </td>
                      <td className="px-3 py-3 text-right font-mono tabular-nums text-[color:var(--text-primary)]">
                        {m.vendors_total}
                      </td>
                      <td className="px-3 py-3 text-right font-mono tabular-nums text-[color:var(--text-primary)]">
                        {m.due_total}
                      </td>
                      <td className="min-w-[260px] px-3 py-3">
                        <StackedBars segments={segments} height={10} />
                      </td>
                      <td className="px-3 py-3 text-right font-mono tabular-nums text-[color:var(--text-primary)]">
                        {m.due_soon_total}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Surface>
        </div>
      )}
    </ClientShell>
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
