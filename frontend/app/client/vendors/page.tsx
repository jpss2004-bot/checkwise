"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  CheckCircle,
  MagnifyingGlass,
  Storefront,
  Warning,
  WarningOctagon,
  type Icon,
} from "@phosphor-icons/react";

import { StackedBars, type ChartSegment } from "@/components/checkwise/charts";
import {
  EmptyState,
  StatCard,
  Surface,
} from "@/components/checkwise/dashboard/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";

import { ClientShell } from "../_shell";
import {
  listClientVendors,
  type ClientVendorRow,
} from "@/lib/api/client";

const LEVELS = [
  { value: "", label: "Todos" },
  { value: "green", label: "Verde" },
  { value: "yellow", label: "Amarillo" },
  { value: "red", label: "Rojo" },
] as const;

type SemaphoreLevel = "green" | "yellow" | "red";

export default function ClientVendorsPage() {
  const [rows, setRows] = useState<ClientVendorRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [level, setLevel] = useState<SemaphoreLevel | "">("");

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const data = await listClientVendors({
        search: search || undefined,
        semaphore_level: level || undefined,
      });
      setRows(data.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar proveedores.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const counts = useMemo(() => {
    const c = { green: 0, yellow: 0, red: 0 };
    for (const r of rows) c[r.semaphore_level] += 1;
    return c;
  }, [rows]);

  const sums = useMemo(() => {
    return rows.reduce(
      (acc, r) => {
        acc.missing += r.missing_required_count;
        acc.rejected += r.rejected_or_correction_count;
        acc.pending += r.pending_reviews_count;
        acc.dueSoon += r.due_soon_count;
        return acc;
      },
      { missing: 0, rejected: 0, pending: 0, dueSoon: 0 },
    );
  }, [rows]);

  const segments: ChartSegment[] = [
    { label: "Verde", value: counts.green, tone: "success" },
    { label: "Amarillo", value: counts.yellow, tone: "warning" },
    { label: "Rojo", value: counts.red, tone: "error" },
  ];

  return (
    <ClientShell
      title="Proveedores"
      description="Lista de proveedores que tienes bajo administración con su semáforo, % de cumplimiento y faltantes."
    >
      <div className="space-y-6">
        {/* KPI strip */}
        <div className="cw-stagger grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            label="Proveedores"
            value={rows.length}
            tone="brand"
            icon={Storefront}
            caption={`${counts.green} en verde · ${counts.yellow} en amarillo · ${counts.red} en rojo`}
          />
          <StatCard
            label="Faltantes obligatorios"
            value={sums.missing}
            tone={sums.missing > 0 ? "warning" : "success"}
            caption="Documentos REPSE pendientes."
          />
          <StatCard
            label="En revisión"
            value={sums.pending}
            tone="info"
            caption="Pendientes de validación humana."
          />
          <StatCard
            label="Vencen ≤14 días"
            value={sums.dueSoon}
            tone={sums.dueSoon > 0 ? "warning" : "success"}
            caption="Obligaciones próximas a vencer."
          />
        </div>

        {/* Distribution bar */}
        <Surface
          title="Distribución de riesgo"
          description="Composición visual del portafolio en el filtro actual."
        >
          <StackedBars segments={segments} height={14} />
        </Surface>

        {/* Filters */}
        <Surface title="Buscar y filtrar">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              refresh();
            }}
            className="flex flex-wrap items-end gap-3"
          >
            <div className="min-w-[220px] flex-1">
              <label className="block font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                Buscar
              </label>
              <div className="relative mt-1">
                <MagnifyingGlass
                  className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[color:var(--text-tertiary)]"
                  weight="bold"
                  aria-hidden="true"
                />
                <Input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Nombre o RFC"
                  className="pl-8"
                />
              </div>
            </div>
            <div>
              <label className="block font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                Semáforo
              </label>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {LEVELS.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => {
                      setLevel(opt.value as SemaphoreLevel | "");
                    }}
                    className={
                      "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors " +
                      (level === opt.value
                        ? "border-[color:var(--border-brand)] bg-[color:var(--surface-brand)] text-[color:var(--text-inverse)]"
                        : "border-[color:var(--border-default)] bg-[color:var(--surface-raised)] text-[color:var(--text-secondary)] hover:bg-[color:var(--surface-hover)]")
                    }
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
            <Button type="submit" size="sm" loading={loading}>
              Aplicar
            </Button>
          </form>
        </Surface>

        {error ? (
          <p className="rounded-md border border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-bg)] p-3 text-sm text-[color:var(--status-warning-text)]">
            {error}
          </p>
        ) : null}

        {/* Table */}
        <Surface bodyClassName="p-0">
          {rows.length === 0 && !loading ? (
            <div className="p-8">
              <EmptyState
                icon={Storefront}
                title="Sin proveedores con esos filtros"
                description="Modifica la búsqueda o limpia los filtros para ver más resultados."
              />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] text-left">
                  <tr className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                    <th className="px-4 py-2.5">Proveedor</th>
                    <th className="px-3 py-2.5">Semáforo</th>
                    <th className="px-3 py-2.5">% cumplimiento</th>
                    <th className="px-3 py-2.5 text-right">Revisión</th>
                    <th className="px-3 py-2.5 text-right">Faltantes</th>
                    <th className="px-3 py-2.5 text-right">Rechazos</th>
                    <th className="px-3 py-2.5 text-right">Vencen</th>
                    <th className="px-3 py-2.5"></th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr
                      key={row.vendor_id}
                      className="group border-b border-[color:var(--border-subtle)] transition-colors last:border-0 hover:bg-[color:var(--surface-hover)]"
                    >
                      <td className="px-4 py-3 align-top">
                        <p className="font-medium text-[color:var(--text-primary)]">
                          {row.vendor_name}
                        </p>
                        <p className="font-mono text-[11px] text-[color:var(--text-tertiary)]">
                          {row.vendor_rfc ?? "—"}
                          {row.persona_type
                            ? ` · ${row.persona_type}`
                            : ""}
                        </p>
                      </td>
                      <td className="px-3 py-3 align-top">
                        <SemaphorePill level={row.semaphore_level} />
                      </td>
                      <td className="px-3 py-3 align-top">
                        <div className="w-32">
                          <Progress
                            value={row.compliance_pct}
                            showValue
                            tone={
                              row.compliance_pct >= 80
                                ? "success"
                                : row.compliance_pct >= 60
                                  ? "warning"
                                  : "error"
                            }
                          />
                        </div>
                      </td>
                      <Cell value={row.pending_reviews_count} />
                      <Cell
                        value={row.missing_required_count}
                        warn={row.missing_required_count > 0}
                      />
                      <Cell
                        value={row.rejected_or_correction_count}
                        warn={row.rejected_or_correction_count > 0}
                      />
                      <Cell
                        value={row.due_soon_count}
                        warn={row.due_soon_count > 0}
                      />
                      <td className="px-3 py-3 text-right align-top">
                        <Button asChild size="sm" variant="outline">
                          <Link
                            href={`/client/vendors/${row.vendor_id}`}
                            className="inline-flex items-center gap-1"
                          >
                            Ver
                            <ArrowRight
                              className="h-3 w-3 transition-transform group-hover:translate-x-0.5"
                              weight="bold"
                              aria-hidden="true"
                            />
                          </Link>
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Surface>
      </div>
    </ClientShell>
  );
}

function Cell({ value, warn }: { value: number; warn?: boolean }) {
  return (
    <td className="px-3 py-3 text-right align-top">
      <span
        className={
          "font-mono tabular-nums " +
          (warn
            ? "font-semibold text-[color:var(--status-warning-text)]"
            : value === 0
              ? "text-[color:var(--text-tertiary)]"
              : "text-[color:var(--text-primary)]")
        }
      >
        {value}
      </span>
    </td>
  );
}

const SEMAPHORE_META: Record<
  SemaphoreLevel,
  { label: string; tone: string; icon: Icon }
> = {
  green: {
    label: "Verde",
    tone:
      "border-[color:var(--status-success-border)] bg-[color:var(--status-success-bg)] text-[color:var(--status-success-text)]",
    icon: CheckCircle,
  },
  yellow: {
    label: "Amarillo",
    tone:
      "border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-bg)] text-[color:var(--status-warning-text)]",
    icon: Warning,
  },
  red: {
    label: "Rojo",
    tone:
      "border-[color:var(--status-error-border)] bg-[color:var(--status-error-bg)] text-[color:var(--status-error-text)]",
    icon: WarningOctagon,
  },
};

function SemaphorePill({ level }: { level: SemaphoreLevel }) {
  const meta = SEMAPHORE_META[level];
  const IconComponent = meta.icon;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${meta.tone}`}
    >
      <IconComponent className="h-3 w-3" weight="fill" aria-hidden="true" />
      {meta.label}
    </span>
  );
}
