"use client";

import { useEffect, useMemo, useState } from "react";
import { CalendarBlank } from "@phosphor-icons/react";

import { MiniBars } from "@/components/checkwise/charts";
import { Surface } from "@/components/checkwise/dashboard/stat-card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { MetadataStrip } from "@/components/ui/metadata-strip";
import {
  ErrorState,
  Skeleton,
} from "@/components/checkwise/portal/state-surfaces";

import { AdminShell } from "../_shell";
import {
  type AdminCalendar,
  type AdminPeriod,
  getAdminCalendar,
  listPeriods,
} from "@/lib/api/admin";

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

export default function AdminCalendarPage() {
  const [year, setYear] = useState<number>(new Date().getFullYear() || 2026);
  const [calendar, setCalendar] = useState<AdminCalendar | null>(null);
  const [periods, setPeriods] = useState<AdminPeriod[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    Promise.all([getAdminCalendar({ year }), listPeriods({ year })])
      .then(([cal, per]) => {
        if (cancelled) return;
        setCalendar(cal);
        setPeriods(per.items);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Error al cargar calendario.");
      });
    return () => {
      cancelled = true;
    };
  }, [year]);

  const expectedBars = useMemo(() => {
    if (!calendar) return [];
    return calendar.months.map((m) => ({
      label: MONTH_SHORT[m.month - 1] ?? `${m.month}`,
      value: m.expected_total,
      tone: "brand" as const,
    }));
  }, [calendar]);

  const totalExpected = useMemo(() => {
    if (!calendar) return 0;
    return calendar.months.reduce((sum, m) => sum + m.expected_total, 0);
  }, [calendar]);

  return (
    <AdminShell
      title="Calendario operativo"
      description="Vista del año regulatorio: obligaciones esperadas por mes y los periodos cargados en la base."
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
            // (backend/app/core/period_validation.py) instead of the prior
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
      ) : !calendar ? (
        <CalendarSkeleton />
      ) : (
        <div className="space-y-6">
          <MetadataStrip
            items={[
              {
                label: "Esperadas",
                value: totalExpected.toString(),
                mono: true,
              },
              {
                label: "Periodos BD",
                value: periods.length.toString(),
                mono: true,
                tone: "teal",
              },
              {
                label: "Cobertura",
                value: `${calendar.months.length}/12`,
                mono: true,
              },
              {
                label: "Año",
                value: `${calendar.year} · ${calendar.persona_type}`,
                mono: true,
              },
            ]}
          />

          <Surface
            title="Distribución mensual"
            description="Cuántas obligaciones esperan los proveedores por mes."
          >
            <MiniBars data={expectedBars} height={120} showValues />
          </Surface>

          <Surface
            title="Detalle por mes"
            bodyClassName="p-0"
          >
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] text-left font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                  <tr>
                    <th className="px-4 py-2.5">Mes</th>
                    <th className="px-3 py-2.5 text-right">Esperadas</th>
                    <th className="px-3 py-2.5">Por institución</th>
                  </tr>
                </thead>
                <tbody>
                  {calendar.months.map((m) => (
                    <tr
                      key={m.month}
                      className="border-b border-[color:var(--border-subtle)] last:border-0 hover:bg-[color:var(--surface-hover)]"
                    >
                      <td className="px-4 py-2.5 font-medium text-[color:var(--text-primary)]">
                        {MONTH_SHORT[m.month - 1]}
                      </td>
                      <td className="px-3 py-2.5 text-right font-mono tabular-nums">
                        {m.expected_total}
                      </td>
                      <td className="px-3 py-2.5">
                        {m.institutions.length === 0 ? (
                          <span className="text-[color:var(--text-tertiary)]">—</span>
                        ) : (
                          <div className="flex flex-wrap gap-1.5">
                            {m.institutions.map((i) => (
                              <Badge key={i.institution} variant="outline">
                                {i.institution}: {i.expected}
                              </Badge>
                            ))}
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Surface>

          <Surface
            title={`Periodos en BD (${periods.length})`}
            bodyClassName="p-0"
          >
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] text-left font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                  <tr>
                    <th className="px-4 py-2.5">Código</th>
                    <th className="px-3 py-2.5">Period key</th>
                    <th className="px-3 py-2.5">Tipo</th>
                    <th className="px-3 py-2.5">Año</th>
                    <th className="px-3 py-2.5">Mes</th>
                  </tr>
                </thead>
                <tbody>
                  {periods.map((p) => (
                    <tr
                      key={p.id}
                      className="border-b border-[color:var(--border-subtle)] last:border-0 hover:bg-[color:var(--surface-hover)]"
                    >
                      <td className="px-4 py-2.5 font-mono text-[11px] text-[color:var(--text-secondary)]">
                        {p.code}
                      </td>
                      <td className="px-3 py-2.5 font-mono text-[11px] text-[color:var(--text-secondary)]">
                        {p.period_key ?? "—"}
                      </td>
                      <td className="px-3 py-2.5">
                        <Badge variant="outline">{p.period_type}</Badge>
                      </td>
                      <td className="px-3 py-2.5 font-mono tabular-nums">
                        {p.year ?? "—"}
                      </td>
                      <td className="px-3 py-2.5 font-mono tabular-nums">
                        {p.month ?? "—"}
                      </td>
                    </tr>
                  ))}
                  {periods.length === 0 ? (
                    <tr>
                      <td
                        colSpan={5}
                        className="px-3 py-6 text-center text-xs text-[color:var(--text-tertiary)]"
                      >
                        Sin periodos para el año seleccionado.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </Surface>
        </div>
      )}
    </AdminShell>
  );
}

function CalendarSkeleton() {
  return (
    <div className="space-y-5" aria-busy="true" aria-live="polite">
      <span className="sr-only">Cargando calendario operativo…</span>
      <Skeleton className="h-12 w-full rounded-md" />
      <Skeleton className="h-32 w-full rounded-lg" />
      <Skeleton className="h-64 w-full rounded-lg" />
    </div>
  );
}
