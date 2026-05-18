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
import { Surface } from "@/components/checkwise/dashboard/stat-card";
import { Button } from "@/components/ui/button";
import { DataTable, type DataTableColumn } from "@/components/ui/data-table";
import { Input } from "@/components/ui/input";
import { MetadataStrip } from "@/components/ui/metadata-strip";
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
  const [rows, setRows] = useState<ClientVendorRow[] | null>(null);
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
      setRows(null);
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
    for (const r of rows ?? []) c[r.semaphore_level] += 1;
    return c;
  }, [rows]);

  const sums = useMemo(() => {
    return (rows ?? []).reduce(
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
        <MetadataStrip
          items={[
            { label: "Proveedores", value: (rows?.length ?? 0).toString(), mono: true },
            { label: "Verde", value: counts.green.toString(), mono: true, tone: "default" },
            { label: "Amarillo", value: counts.yellow.toString(), mono: true, tone: counts.yellow > 0 ? "warning" : "default" },
            { label: "Rojo", value: counts.red.toString(), mono: true, tone: counts.red > 0 ? "warning" : "default" },
            { label: "Faltantes", value: sums.missing.toString(), mono: true, tone: sums.missing > 0 ? "warning" : "default" },
            { label: "Vencen ≤14d", value: sums.dueSoon.toString(), mono: true, tone: sums.dueSoon > 0 ? "warning" : "default" },
          ]}
        />

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

        <DataTable<ClientVendorRow>
          items={rows}
          loading={loading}
          error={error}
          onRetry={refresh}
          columns={vendorColumns}
          rowKey={(row) => row.vendor_id}
          ariaLabel="Proveedores del portafolio"
          emptyTitle="Sin proveedores con esos filtros"
          emptyDescription="Modifica la búsqueda o limpia los filtros para ver más resultados."
          metaBadge={`${rows?.length ?? 0} proveedor${(rows?.length ?? 0) === 1 ? "" : "es"}`}
        />
      </div>
    </ClientShell>
  );
}

function MetricCell({ value, warn }: { value: number; warn?: boolean }) {
  return (
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
      {value === 0 ? "—" : value}
    </span>
  );
}

const vendorColumns: DataTableColumn<ClientVendorRow>[] = [
  {
    id: "vendor",
    header: "Proveedor",
    cell: (row) => (
      <div className="min-w-0">
        <p className="font-medium text-[color:var(--text-primary)]">
          {row.vendor_name}
        </p>
        <p className="font-mono text-[11px] tabular-nums text-[color:var(--text-tertiary)]">
          {row.vendor_rfc ?? "—"}
          {row.persona_type ? ` · ${row.persona_type}` : ""}
        </p>
      </div>
    ),
  },
  {
    id: "semaphore",
    header: "Semáforo",
    width: "120px",
    cell: (row) => <SemaphorePill level={row.semaphore_level} />,
  },
  {
    id: "compliance",
    header: "% cumplimiento",
    width: "160px",
    cell: (row) => (
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
    ),
  },
  {
    id: "pending",
    header: "Revisión",
    width: "90px",
    align: "right",
    cell: (row) => <MetricCell value={row.pending_reviews_count} />,
  },
  {
    id: "missing",
    header: "Faltantes",
    width: "100px",
    align: "right",
    cell: (row) => (
      <MetricCell
        value={row.missing_required_count}
        warn={row.missing_required_count > 0}
      />
    ),
  },
  {
    id: "rejected",
    header: "Rechazos",
    width: "100px",
    align: "right",
    cell: (row) => (
      <MetricCell
        value={row.rejected_or_correction_count}
        warn={row.rejected_or_correction_count > 0}
      />
    ),
  },
  {
    id: "due_soon",
    header: "Vencen",
    width: "90px",
    align: "right",
    cell: (row) => (
      <MetricCell value={row.due_soon_count} warn={row.due_soon_count > 0} />
    ),
  },
  {
    id: "action",
    header: "",
    width: "80px",
    align: "right",
    cell: (row) => (
      <Button asChild size="sm" variant="outline">
        <Link
          href={`/client/vendors/${row.vendor_id}`}
          className="inline-flex items-center gap-1"
        >
          Ver
          <ArrowRight className="h-3 w-3" weight="bold" aria-hidden="true" />
        </Link>
      </Button>
    ),
  },
];

const SEMAPHORE_META: Record<
  SemaphoreLevel,
  { label: string; tone: string; icon: Icon }
> = {
  green: {
    label: "Verde",
    tone:
      "bg-[color:var(--status-success-bg)] text-[color:var(--status-success-text)]",
    icon: CheckCircle,
  },
  yellow: {
    label: "Amarillo",
    tone:
      "bg-[color:var(--status-warning-bg)] text-[color:var(--status-warning-text)]",
    icon: Warning,
  },
  red: {
    label: "Rojo",
    tone:
      "bg-[color:var(--status-error-bg)] text-[color:var(--status-error-text)]",
    icon: WarningOctagon,
  },
};

function SemaphorePill({ level }: { level: SemaphoreLevel }) {
  const meta = SEMAPHORE_META[level];
  const IconComponent = meta.icon;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[12px] font-medium ${meta.tone}`}
    >
      <IconComponent className="h-3 w-3" weight="bold" aria-hidden="true" />
      {meta.label}
    </span>
  );
}
