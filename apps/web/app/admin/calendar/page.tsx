"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowRight, CalendarBlank, Clock, Tray } from "@phosphor-icons/react";

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
  type CalendarRadar,
  getAdminCalendar,
  getAdminCalendarRadar,
  listPeriods,
} from "@/lib/api/admin";
import {
  cadenceLabel,
  INSTITUTION_LABELS,
  personaLabel,
} from "@/lib/constants/labels";

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

/** Urgency tone for a "due in N days" value — drives the badge color so the
 *  eye lands on what's most imminent first. */
function dueTone(days: number): {
  variant: "destructive" | "warning" | "outline";
  text: string;
} {
  if (days <= 7) return { variant: "destructive", text: "var(--status-error-text)" };
  if (days <= 14) return { variant: "warning", text: "var(--status-warning-text)" };
  return { variant: "outline", text: "var(--text-secondary)" };
}

function dueLabel(days: number): string {
  if (days <= 0) return "vence hoy";
  if (days === 1) return "vence mañana";
  return `vence en ${days} días`;
}

export default function AdminCalendarPage() {
  const [year, setYear] = useState<number>(new Date().getFullYear() || 2026);
  const [calendar, setCalendar] = useState<AdminCalendar | null>(null);
  const [periods, setPeriods] = useState<AdminPeriod[]>([]);
  const [radar, setRadar] = useState<CalendarRadar | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  // "Periodos en BD" is a raw dump of the period rows — useful only
  // when cross-referencing codes/period_keys against the backend, so
  // it stays collapsed by default (same idiom as the reviewer's
  // TraceabilityCard).
  const [showPeriods, setShowPeriods] = useState(false);
  // The static month catalog is now secondary to the operational radar
  // (P2-07): kept for "is the year seeded correctly?" but collapsed so the
  // forward view leads.
  const [showCatalog, setShowCatalog] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    // The radar is portfolio-wide (year-independent); the catalog is per-year.
    Promise.all([
      getAdminCalendar({ year }),
      listPeriods({ year }),
      getAdminCalendarRadar({ top: 40 }),
    ])
      .then(([cal, per, rad]) => {
        if (cancelled) return;
        setCalendar(cal);
        setPeriods(per.items);
        setRadar(rad);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Error al cargar calendario.");
      });
    return () => {
      cancelled = true;
    };
  }, [year, reloadKey]);

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
      description="Radar de lo que vence pronto y lo que requiere intervención en todo el portafolio. El catálogo regulatorio del año queda como referencia secundaria."
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
          onRetry={() => setReloadKey((k) => k + 1)}
        />
      ) : !calendar || !radar ? (
        <CalendarSkeleton />
      ) : (
        <div className="space-y-6">
          {/* ─── Operational radar (primary) ─────────────────────── */}
          {/* Urgency strip + awaiting-review, computed across every active
              provider from the same deadline engine the portal uses. */}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {radar.urgency_bands.map((band) => {
              const count = radar.urgency_buckets[band.key] ?? 0;
              const tone =
                band.key === "week"
                  ? "var(--status-error-text)"
                  : band.key === "fortnight"
                    ? "var(--status-warning-text)"
                    : "var(--text-primary)";
              return (
                <div
                  key={band.key}
                  className="rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-4 py-3 shadow-[var(--shadow-sm)]"
                >
                  <p
                    className="text-[20px] font-semibold tabular-nums leading-none"
                    style={{ color: count ? tone : "var(--text-tertiary)" }}
                  >
                    {count}
                  </p>
                  <p className="mt-1 text-[11px] text-[color:var(--text-secondary)]">
                    {band.label}
                  </p>
                </div>
              );
            })}
            <Link
              href="/admin/reviewer"
              className="group flex flex-col justify-between rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-4 py-3 shadow-[var(--shadow-sm)] transition-colors hover:bg-[color:var(--surface-hover)]"
            >
              <span className="flex items-center gap-1.5">
                <Tray className="h-4 w-4 text-[color:var(--text-ai)]" weight="bold" aria-hidden="true" />
                <span
                  className="text-[20px] font-semibold tabular-nums leading-none"
                  style={{
                    color: radar.awaiting_review_total
                      ? "var(--text-primary)"
                      : "var(--text-tertiary)",
                  }}
                >
                  {radar.awaiting_review_total}
                </span>
              </span>
              <span className="mt-1 inline-flex items-center gap-1 text-[11px] text-[color:var(--text-secondary)]">
                En revisión
                <ArrowRight className="h-3 w-3 opacity-0 transition-opacity group-hover:opacity-100" weight="bold" aria-hidden="true" />
              </span>
            </Link>
          </div>

          <Surface
            title="Próximos vencimientos"
            description="Obligaciones obligatorias más cercanas a vencer en todo el portafolio. Selecciona un proveedor para atender el pendiente."
            bodyClassName="p-0"
          >
            {radar.upcoming.length === 0 ? (
              <div className="flex flex-col items-center gap-2 px-4 py-10 text-center">
                <Clock className="h-6 w-6 text-[color:var(--text-tertiary)]" weight="regular" aria-hidden="true" />
                <p className="text-[13px] font-medium text-[color:var(--text-primary)]">
                  Sin vencimientos próximos
                </p>
                <p className="max-w-md text-[12px] text-[color:var(--text-secondary)]">
                  Ningún proveedor activo tiene obligaciones obligatorias por
                  vencer. Aparecerán aquí conforme se acerquen sus fechas.
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] text-left font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                    <tr>
                      <th className="px-4 py-2.5">Vence</th>
                      <th className="px-3 py-2.5">Obligación</th>
                      <th className="px-3 py-2.5">Proveedor</th>
                      <th className="px-3 py-2.5">Institución</th>
                      <th className="px-3 py-2.5 text-right">Abrir</th>
                    </tr>
                  </thead>
                  <tbody>
                    {radar.upcoming.map((item, i) => {
                      const tone = dueTone(item.due_in_days);
                      return (
                        <tr
                          key={`${item.vendor_id}-${item.period_key}-${item.title}-${i}`}
                          className="border-b border-[color:var(--border-subtle)] last:border-0 hover:bg-[color:var(--surface-hover)]"
                        >
                          <td className="px-4 py-2.5">
                            <Badge variant={tone.variant} className="whitespace-nowrap">
                              {dueLabel(item.due_in_days)}
                            </Badge>
                          </td>
                          <td className="px-3 py-2.5 text-[color:var(--text-primary)]">
                            {item.title}
                          </td>
                          <td className="px-3 py-2.5">
                            <Link
                              href={`/admin/vendors/${item.vendor_id}`}
                              className="text-[color:var(--text-link)] hover:underline"
                            >
                              {item.vendor_name}
                            </Link>
                          </td>
                          <td className="px-3 py-2.5">
                            <Badge variant="outline">
                              {INSTITUTION_LABELS[item.institution] ?? item.institution}
                            </Badge>
                          </td>
                          <td className="px-3 py-2.5 text-right">
                            <Link
                              href={`/admin/vendors/${item.vendor_id}`}
                              aria-label={`Abrir ${item.vendor_name}`}
                              className="inline-flex items-center justify-center rounded-sm p-1 text-[color:var(--text-tertiary)] hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--text-primary)]"
                            >
                              <ArrowRight className="h-4 w-4" weight="bold" aria-hidden="true" />
                            </Link>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Surface>

          {radar.truncated ? (
            <p className="text-[11px] text-[color:var(--text-tertiary)]">
              Mostrando los proveedores más relevantes; el portafolio excede el
              límite de escaneo del radar.
            </p>
          ) : null}

          {/* ─── Year catalog (secondary reference) ──────────────── */}
          <section className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-xs">
            <button
              type="button"
              onClick={() => setShowCatalog((v) => !v)}
              aria-expanded={showCatalog}
              className="flex w-full items-center justify-between px-5 py-3.5 text-left"
            >
              <div>
                <h3 className="text-[13px] font-semibold uppercase tracking-wide text-[color:var(--text-primary)]">
                  Catálogo regulatorio {calendar.year} (referencia)
                </h3>
                <p className="mt-0.5 text-[11px] text-[color:var(--text-tertiary)]">
                  Distribución mensual esperada del catálogo — útil para
                  confirmar que el año está bien sembrado.
                </p>
              </div>
              <span className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                {showCatalog ? "Ocultar" : "Mostrar"}
              </span>
            </button>
            {showCatalog ? (
              <div className="space-y-5 border-t border-[color:var(--border-subtle)] p-5">
                <MetadataStrip
                  items={[
                    {
                      label: "Esperadas",
                      value: totalExpected.toString(),
                      mono: true,
                    },
                    {
                      label: "Periodos cargados",
                      value: periods.length.toString(),
                      mono: true,
                      tone: "teal",
                    },
                    {
                      label: "Meses con datos",
                      value: `${calendar.months.length}/12`,
                      mono: true,
                    },
                    {
                      label: "Año",
                      value: `${calendar.year} · ${personaLabel(calendar.persona_type)}`,
                    },
                  ]}
                />

                <Surface
                  title="Distribución mensual"
                  description="Cuántas obligaciones esperan los proveedores por mes."
                >
                  <MiniBars data={expectedBars} height={120} showValues />
                </Surface>

                <Surface title="Detalle por mes" bodyClassName="p-0">
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
                                      {INSTITUTION_LABELS[i.institution] ?? i.institution}: {i.expected}
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

                <div className="rounded-md border border-[color:var(--border-subtle)]">
                  <button
                    type="button"
                    onClick={() => setShowPeriods((v) => !v)}
                    aria-expanded={showPeriods}
                    className="flex w-full items-center justify-between px-4 py-3 text-left"
                  >
                    <h4 className="text-[12px] font-semibold uppercase tracking-wide text-[color:var(--text-secondary)]">
                      Periodos en BD (referencia técnica)
                    </h4>
                    <span className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                      {showPeriods ? "Ocultar" : `Mostrar (${periods.length})`}
                    </span>
                  </button>
                  {showPeriods ? (
                    <div className="overflow-x-auto border-t border-[color:var(--border-subtle)]">
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
                                <Badge variant="outline">{cadenceLabel(p.period_type)}</Badge>
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
                  ) : null}
                </div>
              </div>
            ) : null}
          </section>
        </div>
      )}
    </AdminShell>
  );
}

function CalendarSkeleton() {
  return (
    <div className="space-y-5" aria-busy="true" aria-live="polite">
      <span className="sr-only">Cargando calendario operativo…</span>
      <Skeleton className="h-20 w-full rounded-md" />
      <Skeleton className="h-64 w-full rounded-lg" />
      <Skeleton className="h-12 w-full rounded-lg" />
    </div>
  );
}
