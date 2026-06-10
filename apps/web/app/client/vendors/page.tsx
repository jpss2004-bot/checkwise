"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  ChartBar,
  CheckCircle,
  CircleNotch,
  MagnifyingGlass,
  Package,
  Warning,
  WarningOctagon,
  type Icon,
} from "@phosphor-icons/react";

import { Surface } from "@/components/checkwise/dashboard/stat-card";
import { Button } from "@/components/ui/button";
import { DataTable, type DataTableColumn } from "@/components/ui/data-table";
import { Input } from "@/components/ui/input";
import { MetadataStrip } from "@/components/ui/metadata-strip";
import { Progress } from "@/components/ui/progress";

import { ClientShell } from "../_shell";
import { VendorRef } from "@/components/checkwise/vendor-ref";
import {
  listClientNotifications,
  listClientVendors,
  type ClientVendorNextRenewal,
  type ClientVendorRow,
} from "@/lib/api/client";
import {
  createReportFromPreset,
  ReportsApiError,
} from "@/lib/api/reports";
import { useUrlClientId } from "@/lib/workspace/use-url-client-id";
import { BUCKET_LABELS_ES, semaphoreLabel } from "@/lib/constants/statuses";

const LEVELS = [
  { value: "", label: "Todos" },
  { value: "green", label: semaphoreLabel("green") },
  { value: "yellow", label: semaphoreLabel("yellow") },
  { value: "red", label: semaphoreLabel("red") },
] as const;

type SemaphoreLevel = "green" | "yellow" | "red";

export default function ClientVendorsPage() {
  const urlClientId = useUrlClientId();
  const [rows, setRows] = useState<ClientVendorRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [level, setLevel] = useState<SemaphoreLevel | "">("");
  const [unreadByVendor, setUnreadByVendor] = useState<Record<string, number>>({});

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const scope = urlClientId ? { client_id: urlClientId } : {};
      const [data, notifications] = await Promise.all([
        listClientVendors({
          ...scope,
          search: search || undefined,
          semaphore_level: level || undefined,
        }),
        listClientNotifications({ ...scope, unread_only: true, limit: 200 }),
      ]);
      const counts: Record<string, number> = {};
      for (const item of notifications.items) {
        if (!item.vendor_id) continue;
        counts[item.vendor_id] = (counts[item.vendor_id] ?? 0) + 1;
      }
      setRows(data.items);
      setUnreadByVendor(counts);
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
  }, [urlClientId]);

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

  const router = useRouter();
  const [generatingVendorId, setGeneratingVendorId] = useState<string | null>(null);

  const onGenerateReport = useCallback(
    async (vendorId: string) => {
      if (generatingVendorId) return;
      setGeneratingVendorId(vendorId);
      try {
        // Per-provider report: server generates the visual deliverable inline
        // (hybrid AI + deterministic fallback) scoped to this one vendor, then
        // we land on the finished read-only report.
        const r = await createReportFromPreset("client-vendor-detail", true, {
          vendorId,
        });
        router.push(`/client/reports/${r.id}`);
      } catch (e) {
        setGeneratingVendorId(null);
        setError(
          e instanceof ReportsApiError ? e.message : "Error generando el reporte.",
        );
      }
    },
    [generatingVendorId, router],
  );

  const columns = useMemo(
    () => buildVendorColumns(unreadByVendor, onGenerateReport, generatingVendorId),
    [unreadByVendor, onGenerateReport, generatingVendorId],
  );

  return (
    <ClientShell
      title="Proveedores"
      description="Lista de proveedores que tienes bajo administración con su semáforo, % de cumplimiento y faltantes."
    >
      {generatingVendorId ? (
        <div
          className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-4 bg-[color:var(--surface-base)]/80 backdrop-blur-sm"
          role="status"
          aria-live="polite"
        >
          <CircleNotch
            className="h-8 w-8 animate-spin text-[color:var(--text-ai)]"
            weight="bold"
            aria-hidden="true"
          />
          <p className="text-[14px] font-semibold text-[color:var(--text-primary)]">
            Generando el reporte del proveedor…
          </p>
        </div>
      ) : null}
      <div className="space-y-6">
        {/* Junta 2026-05-23 — discovery entry point to the audit
            package builder. Sits at the top of the vendors page so a
            client_admin under audit-time pressure finds it before
            they start scrolling. */}
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-brand-muted)] p-4">
          <div className="flex items-start gap-3">
            <Package
              className="mt-0.5 h-5 w-5 text-[color:var(--text-brand)]"
              weight="bold"
              aria-hidden="true"
            />
            <div className="min-w-0">
              <p className="text-sm font-semibold text-[color:var(--text-primary)]">
                ¿Llega un auditor?
              </p>
              <p className="mt-0.5 text-xs text-[color:var(--text-secondary)]">
                Arma un ZIP con los documentos exactos que te está
                pidiendo: filtra por periodo, institución y proveedor.
              </p>
            </div>
          </div>
          <Button asChild size="sm">
            <Link href="/client/auditoria">
              Preparar paquete para auditoría
              <ArrowRight className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
            </Link>
          </Button>
        </div>

        <MetadataStrip
          items={[
            { label: "Proveedores", value: (rows?.length ?? 0).toString(), mono: true },
            { label: semaphoreLabel("green"), value: counts.green.toString(), mono: true, tone: "default" },
            { label: semaphoreLabel("yellow"), value: counts.yellow.toString(), mono: true, tone: counts.yellow > 0 ? "warning" : "default" },
            { label: semaphoreLabel("red"), value: counts.red.toString(), mono: true, tone: counts.red > 0 ? "warning" : "default" },
            { label: BUCKET_LABELS_ES.missing_required, value: sums.missing.toString(), mono: true, tone: sums.missing > 0 ? "warning" : "default" },
            { label: BUCKET_LABELS_ES.due_soon, value: sums.dueSoon.toString(), mono: true, tone: sums.dueSoon > 0 ? "warning" : "default" },
          ]}
        />

        {/* D4 — "Distribución de riesgo" StackedBars removed; the
            Dashboard donut + the MetadataStrip above already convey
            this distribution. The page kept the bar and the strip
            side-by-side which was visually redundant. */}

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
          columns={columns}
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

function buildVendorColumns(
  unreadByVendor: Record<string, number>,
  onGenerateReport: (vendorId: string) => void,
  generatingVendorId: string | null,
): DataTableColumn<ClientVendorRow>[] {
  return [
  {
    id: "vendor",
    header: "Proveedor",
    cell: (row) => (
      <div className="min-w-0">
        <p className="font-medium text-[color:var(--text-primary)]">
          <VendorRef vendorId={row.vendor_id} vendorName={row.vendor_name} />
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
    header: BUCKET_LABELS_ES.pending_reviews,
    width: "90px",
    align: "right",
    cell: (row) => <MetricCell value={row.pending_reviews_count} />,
  },
  {
    id: "missing",
    header: BUCKET_LABELS_ES.missing_required,
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
    header: BUCKET_LABELS_ES.rejected_or_correction,
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
    header: BUCKET_LABELS_ES.due_soon,
    width: "90px",
    align: "right",
    cell: (row) => (
      <MetricCell value={row.due_soon_count} warn={row.due_soon_count > 0} />
    ),
  },
  {
    id: "renewal",
    header: "Renovación",
    width: "180px",
    cell: (row) =>
      row.next_renewal ? <RenewalPill renewal={row.next_renewal} /> : (
        <span className="text-[12px] text-[color:var(--text-tertiary)]">—</span>
      ),
  },
  {
    id: "notifications",
    header: "Novedades",
    width: "100px",
    align: "right",
    cell: (row) => {
      const count = unreadByVendor?.[row.vendor_id] ?? 0;
      return count > 0 ? (
        <span className="inline-flex min-w-6 justify-center rounded-full bg-[color:var(--surface-teal-muted)] px-2 py-0.5 font-mono text-[11px] font-semibold text-[color:var(--text-teal)]">
          {count}
        </span>
      ) : (
        <span className="text-[color:var(--text-tertiary)]">—</span>
      );
    },
  },
  {
    id: "action",
    header: "",
    width: "210px",
    align: "right",
    cell: (row) => (
      <div className="inline-flex items-center gap-2">
        <Button
          size="sm"
          variant="default"
          onClick={() => onGenerateReport(row.vendor_id)}
          disabled={generatingVendorId !== null}
          title="Generar un reporte visual de este proveedor"
          className="inline-flex items-center gap-1"
        >
          {generatingVendorId === row.vendor_id ? (
            <CircleNotch className="h-3 w-3 animate-spin" weight="bold" aria-hidden="true" />
          ) : (
            <ChartBar className="h-3 w-3" weight="bold" aria-hidden="true" />
          )}
          Reporte
        </Button>
        <Button asChild size="sm" variant="outline">
          <Link
            href={`/client/vendors/${row.vendor_id}`}
            className="inline-flex items-center gap-1"
          >
            Ver
            <ArrowRight className="h-3 w-3" weight="bold" aria-hidden="true" />
          </Link>
        </Button>
      </div>
    ),
  },
  ];
}

const SEMAPHORE_META: Record<
  SemaphoreLevel,
  { label: string; tone: string; icon: Icon }
> = {
  green: {
    label: semaphoreLabel("green"),
    tone:
      "bg-[color:var(--status-success-bg)] text-[color:var(--status-success-text)]",
    icon: CheckCircle,
  },
  yellow: {
    label: semaphoreLabel("yellow"),
    tone:
      "bg-[color:var(--status-warning-bg)] text-[color:var(--status-warning-text)]",
    icon: Warning,
  },
  red: {
    label: semaphoreLabel("red"),
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

// Phase 6D — renewal urgency pill. Yellow for due_soon (within 30
// days), red for overdue (past the due date). Shows the requirement
// short label + the day count so the client_admin can scan the
// column without clicking through.
function RenewalPill({ renewal }: { renewal: ClientVendorNextRenewal }) {
  const overdue = renewal.status === "overdue";
  const tone = overdue
    ? "bg-[color:var(--status-error-bg)] text-[color:var(--status-error-text)]"
    : "bg-[color:var(--status-warning-bg)] text-[color:var(--status-warning-text)]";
  const short = renewal.requirement_name
    .replace("Constancia de Situación Fiscal (CSF)", "CSF")
    .replace("Constancia de Situación Fiscal (CSF) y actualizaciones", "CSF")
    .replace("Registro REPSE original", "REPSE")
    .replace("Registro patronal original", "Patronal");
  const tail = overdue
    ? `vencido hace ${-renewal.days_remaining}d`
    : renewal.days_remaining === 0
      ? "vence hoy"
      : `en ${renewal.days_remaining}d`;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[12px] font-medium ${tone}`}
      title={`${renewal.requirement_name} · vence ${renewal.due_date}`}
    >
      {short} · {tail}
    </span>
  );
}
