"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowRight,
  ChartBar,
  CheckCircle,
  CircleNotch,
  Package,
  Warning,
  WarningOctagon,
  type Icon,
} from "@phosphor-icons/react";

import { Surface } from "@/components/checkwise/dashboard/stat-card";
import { Button } from "@/components/ui/button";
import { DataTable, type DataTableColumn } from "@/components/ui/data-table";
import { MetadataStrip } from "@/components/ui/metadata-strip";
import { Progress } from "@/components/ui/progress";
import { SearchInput } from "@/components/ui/search-input";
import { Tooltip } from "@/components/ui/tooltip";
import { useDebouncedValue } from "@/lib/hooks/use-debounced-value";

import { ClientShell } from "../_shell";
import { VendorRef } from "@/components/checkwise/vendor-ref";
import {
  listClientNotifications,
  listClientVendors,
  type ClientVendorNextRenewal,
  type ClientVendorRow,
  type ClientVendorSort,
} from "@/lib/api/client";
import { Select } from "@/components/ui/select";
import {
  createReportFromPreset,
  ReportsApiError,
} from "@/lib/api/reports";
import { useUrlClientId } from "@/lib/workspace/use-url-client-id";
import { BUCKET_LABELS_ES, semaphoreLabel } from "@/lib/constants/statuses";
import { withReturnTo } from "@/lib/navigation/return-to";

const LEVELS = [
  { value: "", label: "Todos" },
  { value: "green", label: semaphoreLabel("green") },
  { value: "yellow", label: semaphoreLabel("yellow") },
  { value: "red", label: semaphoreLabel("red") },
] as const;

type SemaphoreLevel = "green" | "yellow" | "red";

function parseSemaphoreLevel(raw: string | null): SemaphoreLevel | "" {
  return raw === "green" || raw === "yellow" || raw === "red" ? raw : "";
}

const SORT_OPTIONS: ReadonlyArray<{ value: ClientVendorSort; label: string }> = [
  { value: "risk", label: "Riesgo (peor primero)" },
  { value: "compliance_asc", label: "Cumplimiento ↑" },
  { value: "compliance_desc", label: "Cumplimiento ↓" },
  { value: "missing_desc", label: "Más pendientes" },
  { value: "name", label: "Nombre (A–Z)" },
  { value: "recent", label: "Actividad reciente" },
];

const SORT_VALUES = new Set<ClientVendorSort>(SORT_OPTIONS.map((o) => o.value));

function parseSort(raw: string | null): ClientVendorSort {
  return raw && SORT_VALUES.has(raw as ClientVendorSort)
    ? (raw as ClientVendorSort)
    : "risk";
}

export default function ClientVendorsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const urlClientId = useUrlClientId();
  const [rows, setRows] = useState<ClientVendorRow[] | null>(null);
  // True portfolio size from the API (not rows.length), so the count never
  // under-reports when the response is capped (audit P2.10).
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState(() => searchParams?.get("q") ?? "");
  // Search runs against the API; debounce so it fires as typing settles
  // instead of needing a manual "Aplicar" click.
  const debouncedSearch = useDebouncedValue(search.trim(), 300);
  const [level, setLevel] = useState<SemaphoreLevel | "">(() =>
    parseSemaphoreLevel(searchParams?.get("level") ?? null),
  );
  const [sort, setSort] = useState<ClientVendorSort>(() =>
    parseSort(searchParams?.get("sort") ?? null),
  );
  const [unreadByVendor, setUnreadByVendor] = useState<Record<string, number>>({});
  const vendorsHref = useMemo(() => {
    const params = new URLSearchParams();
    if (urlClientId) params.set("client_id", urlClientId);
    if (search.trim()) params.set("q", search.trim());
    if (level) params.set("level", level);
    if (sort !== "risk") params.set("sort", sort);
    const qs = params.toString();
    return `/client/vendors${qs ? `?${qs}` : ""}`;
  }, [level, search, sort, urlClientId]);

  useEffect(() => {
    router.replace(vendorsHref, { scroll: false });
  }, [router, vendorsHref]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const scope = urlClientId ? { client_id: urlClientId } : {};
      const [data, notifications] = await Promise.all([
        listClientVendors({
          ...scope,
          search: debouncedSearch || undefined,
          semaphore_level: level || undefined,
          sort,
        }),
        listClientNotifications({ ...scope, unread_only: true, limit: 200 }),
      ]);
      const counts: Record<string, number> = {};
      for (const item of notifications.items) {
        if (!item.vendor_id) continue;
        counts[item.vendor_id] = (counts[item.vendor_id] ?? 0) + 1;
      }
      setRows(data.items);
      setTotal(data.total ?? data.items.length);
      setUnreadByVendor(counts);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al cargar proveedores.");
      setRows(null);
    } finally {
      setLoading(false);
    }
  }, [urlClientId, debouncedSearch, level, sort]);

  // Auto-search: re-fetch when the client scope, the debounced query, or the
  // semáforo filter changes — no manual "Aplicar" click needed.
  useEffect(() => {
    refresh();
  }, [refresh]);

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
    () =>
      buildVendorColumns(
        unreadByVendor,
        onGenerateReport,
        generatingVendorId,
        vendorsHref,
      ),
    [unreadByVendor, onGenerateReport, generatingVendorId, vendorsHref],
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
            { label: `${BUCKET_LABELS_ES.due_soon} ≤14 d`, value: sums.dueSoon.toString(), mono: true, tone: sums.dueSoon > 0 ? "warning" : "default" },
          ]}
        />

        {/* D4 — "Distribución de riesgo" StackedBars removed; the
            Dashboard donut + the MetadataStrip above already convey
            this distribution. The page kept the bar and the strip
            side-by-side which was visually redundant. */}

        {/* Filters */}
        <Surface title="Buscar y filtrar">
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-[220px] flex-1">
              <label className="block font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                Buscar
              </label>
              <SearchInput
                value={search}
                onValueChange={setSearch}
                placeholder="Nombre o RFC"
                ariaLabel="Buscar proveedor por nombre o RFC"
                className="mt-1"
              />
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
            <div>
              <label
                htmlFor="vendor-sort"
                className="block font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]"
              >
                Ordenar por
              </label>
              <Select
                id="vendor-sort"
                value={sort}
                onChange={(e) => setSort(parseSort(e.target.value))}
                className="mt-1 w-[200px]"
              >
                {SORT_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </Select>
            </div>
          </div>
        </Surface>

        <DataTable<ClientVendorRow>
          items={rows}
          loading={loading}
          error={error}
          onRetry={refresh}
          columns={columns}
          rowKey={(row) => row.vendor_id}
          mobileCards
          ariaLabel="Proveedores del portafolio"
          emptyTitle="Sin proveedores con esos filtros"
          emptyDescription="Modifica la búsqueda o limpia los filtros para ver más resultados."
          metaBadge={
            total > (rows?.length ?? 0)
              ? `Mostrando ${rows?.length ?? 0} de ${total} proveedores`
              : `${rows?.length ?? 0} proveedor${(rows?.length ?? 0) === 1 ? "" : "es"}`
          }
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

// A non-zero bucket count is a drill-down: clicking it deep-links into the
// provider detail focused on that bucket (?focus=…#documentos), so the client
// goes from the aggregate straight to the specific documents (CW-06).
function DrillMetricCell({
  vendorId,
  focus,
  value,
}: {
  vendorId: string;
  focus: "missing" | "rejected" | "due_soon";
  value: number;
}) {
  if (value <= 0) return <MetricCell value={value} />;
  return (
    <Link
      href={`/client/vendors/${vendorId}?focus=${focus}#documentos`}
      title="Ver estos documentos del proveedor"
      className="rounded-sm underline decoration-dotted decoration-1 underline-offset-2 hover:opacity-80 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[color:var(--ring)]"
    >
      <MetricCell value={value} warn />
    </Link>
  );
}

function buildVendorColumns(
  unreadByVendor: Record<string, number>,
  onGenerateReport: (vendorId: string) => void,
  generatingVendorId: string | null,
  returnToHref: string,
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
      <DrillMetricCell
        vendorId={row.vendor_id}
        focus="missing"
        value={row.missing_required_count}
      />
    ),
  },
  {
    id: "rejected",
    header: BUCKET_LABELS_ES.rejected_or_correction,
    width: "100px",
    align: "right",
    cell: (row) => (
      <DrillMetricCell
        vendorId={row.vendor_id}
        focus="rejected"
        value={row.rejected_or_correction_count}
      />
    ),
  },
  {
    id: "due_soon",
    header: `${BUCKET_LABELS_ES.due_soon} ≤14d`,
    width: "90px",
    align: "right",
    cell: (row) => (
      <DrillMetricCell
        vendorId={row.vendor_id}
        focus="due_soon"
        value={row.due_soon_count}
      />
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
            href={withReturnTo(`/client/vendors/${row.vendor_id}`, returnToHref)}
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

// CW-16 — plain-language reason behind each semáforo color, so the pill
// explains *why* a provider is red/yellow/green instead of just showing it.
// Mirrors the backend rule in _compute_semaphore (portal.py).
const SEMAPHORE_EXPLANATION: Record<SemaphoreLevel, string> = {
  green: "Al día: todos los documentos obligatorios están aprobados.",
  yellow:
    "En proceso: hay documentos faltantes, en revisión o por vencer — ninguno rechazado.",
  red: "En riesgo: hay documentos rechazados o por corregir, o el proveedor aún no tiene ningún documento aprobado.",
};

function SemaphorePill({ level }: { level: SemaphoreLevel }) {
  const meta = SEMAPHORE_META[level];
  const IconComponent = meta.icon;
  return (
    <Tooltip content={SEMAPHORE_EXPLANATION[level]}>
      {/* Focusable (tabIndex) + aria-label so the "why is this red" reason is
          reachable by keyboard and announced to screen readers — a bare
          <span> trigger was neither (WCAG 2.1.1/4.1.2, audit P3.16). */}
      <span
        tabIndex={0}
        aria-label={`${meta.label}: ${SEMAPHORE_EXPLANATION[level]}`}
        className={`inline-flex cursor-help items-center gap-1.5 rounded-full px-2 py-0.5 text-[12px] font-medium ${meta.tone} focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)] focus-visible:ring-offset-1`}
      >
        <IconComponent className="h-3 w-3" weight="bold" aria-hidden="true" />
        {meta.label}
      </span>
    </Tooltip>
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
