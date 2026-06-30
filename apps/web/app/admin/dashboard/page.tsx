"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  CheckCircle,
  ClipboardText,
  EnvelopeSimple,
  HourglassHigh,
  Megaphone,
  PencilSimpleLine,
  Percent,
  WarningOctagon,
  XCircle,
} from "@phosphor-icons/react";

import { StackedBars, type ChartTone } from "@/components/checkwise/charts";
import {
  EmptyState,
  StatCard,
  Surface,
} from "@/components/checkwise/dashboard/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/ui/data-table";
import { MetadataStrip } from "@/components/ui/metadata-strip";
import {
  ErrorState,
  Skeleton,
} from "@/components/checkwise/portal/state-surfaces";

import { AdminShell } from "../_shell";
import {
  getAdminOverview,
  getRollup,
  type AdminOverview,
  type AdminRollup,
  type RollupClientRow,
  type RollupQueueHealth,
  type RollupVendorAtRisk,
} from "@/lib/api/admin";
import {
  bucketLabel,
  SEMAPHORE_LABELS_ES,
  semaphoreLabel,
  semaphoreVariant,
  type SemaphoreLevel,
} from "@/lib/constants/statuses";

/**
 * Admin dashboard — operations console (P2 audit, 2026-06-10).
 *
 * Replaces the vanity workspace-ratio gauge + bare count rows with the
 * aggregates the ops team actually drives from: queue health with aging
 * buckets, 7-day throughput, per-client semáforo rollup, the named
 * vendors at risk, and the three operational inboxes. The launcher
 * section that duplicated the nav is gone.
 */
export default function AdminDashboardPage() {
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [rollup, setRollup] = useState<AdminRollup | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setOverview(null);
    setRollup(null);
    setError(null);
    Promise.all([getAdminOverview(), getRollup()])
      .then(([ov, ru]) => {
        if (cancelled) return;
        setOverview(ov);
        setRollup(ru);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Error al cargar el resumen.");
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  const loaded = overview && rollup;

  return (
    <AdminShell
      title="Resumen operativo"
      description="Consola de operaciones: salud de la cola de revisión, ritmo del equipo, semáforo por cliente y bandejas pendientes."
      actions={
        <Button asChild size="sm">
          <Link href="/admin/reviewer">
            <ClipboardText className="h-4 w-4" weight="bold" aria-hidden="true" />
            Bandeja de revisión
          </Link>
        </Button>
      }
    >
      {error ? (
        <ErrorState
          title="No pudimos cargar el resumen"
          description={error}
          onRetry={() => setReloadKey((k) => k + 1)}
        />
      ) : !loaded ? (
        <DashboardSkeleton />
      ) : (
        <div className="space-y-6">
          <OpsHero overview={overview} queue={rollup.queue} />
          <ThroughputStrip throughput={rollup.throughput} />
          <ClientsRollupSection clients={rollup.clients} />
          <div className="cw-stagger grid gap-5 lg:grid-cols-3">
            <VendorsAtRiskCard
              vendors={rollup.vendors_at_risk}
              className="lg:col-span-2"
            />
            <OperationalInbox inbox={rollup.inbox} />
          </div>
        </div>
      )}
    </AdminShell>
  );
}

// ─── Hero — backlog headline + queue health ──────────────────────

function OpsHero({
  overview,
  queue,
}: {
  overview: AdminOverview;
  queue: RollupQueueHealth;
}) {
  const reviewBacklog =
    overview.pending_reviews_total + overview.rejected_or_correction_total;
  return (
    <section className="cw-fade-up grid gap-5 rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-5 shadow-xs md:grid-cols-[1fr,auto] md:items-center md:gap-8 md:p-6">
      <div className="min-w-0 space-y-3">
        <p className="cw-eyebrow">
          Panorama · {overview.clients_total} clientes · {overview.vendors_total}{" "}
          proveedores
        </p>
        <p className="text-xl font-semibold leading-tight tracking-tight text-[color:var(--text-primary)]">
          {heroHeadline(overview, reviewBacklog)}
        </p>
        <p className="max-w-2xl text-[13px] leading-relaxed text-[color:var(--text-secondary)]">
          {heroDescription(overview, reviewBacklog)}
        </p>
        <MetadataStrip
          bordered={false}
          className="!py-0"
          items={[
            {
              label: "Revisar",
              value: formatCount(overview.pending_reviews_total),
              mono: true,
            },
            {
              label: "Correcciones",
              value: formatCount(overview.rejected_or_correction_total),
              mono: true,
              tone:
                overview.rejected_or_correction_total > 0 ? "warning" : "default",
            },
            {
              label: "Entregas recientes",
              value: formatCount(overview.recent_submissions_total),
              mono: true,
            },
          ]}
        />
      </div>
      <QueueHealthPanel queue={queue} />
    </section>
  );
}

function formatCount(n: number): string {
  // Show a real 0 on an operations dashboard: "0 por revisar" is
  // meaningful good news and must be distinguishable from missing data.
  return n.toString();
}

function heroHeadline(data: AdminOverview, backlog: number): string {
  if (backlog === 0) return "Cero pendientes en la bandeja";
  if (data.pending_reviews_total === 0)
    return `${data.rejected_or_correction_total} documentos esperan acción del proveedor`;
  if (data.rejected_or_correction_total === 0)
    return `${data.pending_reviews_total} documentos en cola humana`;
  return `${backlog} pendientes entre revisión y correcciones`;
}

function heroDescription(data: AdminOverview, backlog: number): string {
  const parts: string[] = [];
  if (data.pending_reviews_total > 0)
    parts.push(`${data.pending_reviews_total} a revisar`);
  if (data.rejected_or_correction_total > 0)
    parts.push(`${data.rejected_or_correction_total} con feedback al proveedor`);
  if (data.recent_submissions_total > 0)
    parts.push(`${data.recent_submissions_total} entregas en el último ciclo`);
  if (data.recent_audit_events_total > 0)
    parts.push(
      `${data.recent_audit_events_total} eventos recientes en la bitácora de auditoría`,
    );
  if (parts.length === 0)
    return backlog === 0
      ? "No hay actividad operativa pendiente. Todo está al día."
      : "Todo bajo control. Las secciones inferiores detallan cada cliente.";
  return parts.join(" · ") + ".";
}

// ─── Queue health (replaces the workspace-ratio gauge) ───────────

type AgeBucket = {
  key: string;
  label: string;
  value: number;
  tone: ChartTone;
};

function QueueHealthPanel({ queue }: { queue: RollupQueueHealth }) {
  const buckets: AgeBucket[] = [
    {
      key: "under_24h",
      label: "<24 h",
      value: queue.age_buckets.under_24h,
      tone: "success",
    },
    {
      key: "h24_to_72h",
      label: "1–3 días",
      value: queue.age_buckets.h24_to_72h,
      tone: "info",
    },
    {
      key: "over_72h",
      label: "3–7 días",
      value: queue.age_buckets.over_72h,
      tone: "warning",
    },
    {
      key: "over_7d",
      label: "+7 días",
      value: queue.age_buckets.over_7d,
      tone: "error",
    },
  ];
  return (
    <div className="w-full rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] p-4 md:w-[320px]">
      <div className="flex items-center justify-between gap-3">
        <p className="cw-eyebrow">Cola de revisión</p>
        <HourglassHigh
          className="h-4 w-4 text-[color:var(--text-tertiary)]"
          weight="duotone"
          aria-hidden="true"
        />
      </div>
      <div className="mt-2 flex items-baseline gap-2">
        <span className="font-mono text-4xl font-semibold tabular-nums leading-none text-[color:var(--text-primary)]">
          {queue.pending_total}
        </span>
        <span className="text-[11px] text-[color:var(--text-secondary)]">
          pendientes
        </span>
      </div>
      <p className="mt-1.5 text-[11px] text-[color:var(--text-tertiary)]">
        {queue.oldest_age_hours !== null
          ? `la más antigua lleva ${humanizeHours(queue.oldest_age_hours)} esperando`
          : "no hay documentos en espera"}
      </p>
      {queue.pending_total > 0 ? (
        <StackedBars
          segments={buckets}
          height={8}
          showLegend={false}
          className="mt-3"
        />
      ) : null}
      <div className="mt-3 grid grid-cols-2 gap-1.5">
        {buckets.map((bucket) => (
          <AgeChip key={bucket.key} bucket={bucket} />
        ))}
      </div>
    </div>
  );
}

function AgeChip({ bucket }: { bucket: AgeBucket }) {
  const active = bucket.value > 0;
  const toneClass =
    active && bucket.tone === "error"
      ? "border-[color:var(--status-error-border)] bg-[color:var(--status-error-bg)] text-[color:var(--status-error-text)]"
      : active && bucket.tone === "warning"
        ? "border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-bg)] text-[color:var(--status-warning-text)]"
        : active
          ? "border-[color:var(--border-default)] bg-[color:var(--surface-raised)] text-[color:var(--text-secondary)]"
          : "border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)] text-[color:var(--text-tertiary)]";
  return (
    <span
      className={`flex items-center justify-between gap-2 rounded-md border px-2 py-1 text-[10px] font-medium ${toneClass}`}
    >
      <span>{bucket.label}</span>
      <span className="font-mono text-[11px] tabular-nums">{bucket.value}</span>
    </span>
  );
}

/** <48h reads in hours ("31h"); anything older reads in days ("4d"). */
function humanizeHours(hours: number): string {
  if (hours < 48) return `${Math.max(1, Math.round(hours))}h`;
  return `${Math.round(hours / 24)}d`;
}

// ─── Throughput (últimos 7 días) ─────────────────────────────────

function ThroughputStrip({
  throughput,
}: {
  throughput: AdminRollup["throughput"];
}) {
  const approved = throughput.approved_last_7d;
  const rejected = throughput.rejected_last_7d;
  const resolved = approved + rejected;
  const rejectionRate =
    resolved === 0 ? null : Math.round((rejected / resolved) * 100);
  return (
    <section
      aria-label="Ritmo de revisión"
      className="cw-stagger grid gap-3 sm:grid-cols-3"
    >
      <StatCard
        compact
        label="Aprobados"
        value={approved}
        caption="últimos 7 días"
        icon={CheckCircle}
        tone={approved > 0 ? "success" : "neutral"}
      />
      <StatCard
        compact
        label="Rechazados"
        value={rejected}
        caption="últimos 7 días"
        icon={XCircle}
        tone={rejected > 0 ? "error" : "neutral"}
      />
      <StatCard
        compact
        label="Tasa de rechazo"
        value={rejectionRate === null ? "—" : `${rejectionRate}%`}
        caption="rechazados entre resueltos · últimos 7 días"
        icon={Percent}
        tone={rejectionRate !== null && rejectionRate >= 20 ? "warning" : "neutral"}
      />
    </section>
  );
}

// ─── Per-client rollup table ─────────────────────────────────────

function ClientsRollupSection({ clients }: { clients: RollupClientRow[] }) {
  return (
    <section className="space-y-3">
      <header className="space-y-0.5">
        <h2 className="text-[13px] font-semibold uppercase tracking-wide text-[color:var(--text-primary)]">
          Clientes por estado
        </h2>
        <p className="text-xs text-[color:var(--text-secondary)]">
          Semáforo y pendientes de cada cartera, ordenados de mayor a menor
          riesgo.
        </p>
      </header>
      <DataTable<RollupClientRow>
        items={clients}
        columns={[
          {
            id: "client",
            header: "Cliente",
            cell: (row) => (
              <Link
                href={`/admin/clients/${row.client_id}`}
                className="font-medium text-[color:var(--text-primary)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]/40"
              >
                {row.client_name}
              </Link>
            ),
          },
          {
            id: "vendors",
            header: "Proveedores",
            width: "100px",
            align: "right",
            cell: (row) => (
              <span className="font-mono text-[12px] tabular-nums text-[color:var(--text-secondary)]">
                {row.vendors_total}
              </span>
            ),
          },
          {
            id: "semaphore",
            header: "Semáforo",
            width: "150px",
            cell: (row) => <SemaphoreChips row={row} />,
          },
          {
            id: "compliance",
            header: "Cumplimiento",
            width: "150px",
            cell: (row) => <CompliancePct pct={row.compliance_pct} />,
          },
          {
            id: "missing",
            header: bucketLabel("missing_required"),
            width: "90px",
            align: "right",
            cell: (row) => (
              <CountCell value={row.missing_required_total} tone="warning" />
            ),
          },
          {
            id: "reviews",
            header: bucketLabel("pending_reviews"),
            width: "100px",
            align: "right",
            cell: (row) => (
              <CountCell value={row.pending_reviews_total} tone="info" />
            ),
          },
          {
            id: "due_soon",
            header: "Por vencer ≤14 d",
            width: "130px",
            align: "right",
            cell: (row) => (
              <CountCell value={row.due_soon_total} tone="warning" />
            ),
          },
        ]}
        rowKey={(row) => row.client_id}
        ariaLabel="Clientes por estado"
        caption="Rollup de cumplimiento por cliente, ordenado del de mayor riesgo al de menor."
        emptyTitle="Sin clientes activos"
        emptyDescription="Cuando haya clientes con proveedores, su semáforo aparecerá aquí."
        metaBadge={`${clients.length} cliente${clients.length === 1 ? "" : "s"}`}
      />
    </section>
  );
}

/**
 * Compact green/yellow/red distribution. Counts at zero render as
 * muted outline chips so the eye lands only on the buckets that exist.
 */
function SemaphoreChips({ row }: { row: RollupClientRow }) {
  const chips: { level: SemaphoreLevel; count: number }[] = [
    { level: "green", count: row.green_count },
    { level: "yellow", count: row.yellow_count },
    { level: "red", count: row.red_count },
  ];
  return (
    <div className="flex items-center gap-1.5">
      {chips.map((chip) => (
        <Badge
          key={chip.level}
          variant={chip.count > 0 ? semaphoreVariant(chip.level) : "outline"}
          title={SEMAPHORE_LABELS_ES[chip.level]}
          className="font-mono tabular-nums"
        >
          {chip.count}
          <span className="sr-only"> {SEMAPHORE_LABELS_ES[chip.level]}</span>
        </Badge>
      ))}
    </div>
  );
}

function CompliancePct({ pct }: { pct: number }) {
  const clamped = Math.max(0, Math.min(100, pct));
  const barColor =
    clamped >= 85
      ? "var(--status-success-text)"
      : clamped >= 60
        ? "var(--status-warning-text)"
        : "var(--status-error-text)";
  return (
    <div className="flex items-center gap-2">
      <span className="w-9 text-right font-mono text-[12px] tabular-nums text-[color:var(--text-primary)]">
        {Math.round(clamped)}%
      </span>
      <span
        className="h-1.5 w-16 overflow-hidden rounded-full bg-[color:var(--surface-sunken)]"
        aria-hidden="true"
      >
        <span
          className="block h-full rounded-full transition-[width] duration-700 ease-out"
          style={{ width: `${clamped}%`, background: barColor }}
        />
      </span>
    </div>
  );
}

function CountCell({
  value,
  tone = "default",
}: {
  value: number;
  tone?: "default" | "warning" | "info";
}) {
  if (value === 0) {
    return (
      <span className="font-mono text-[12px] tabular-nums text-[color:var(--text-tertiary)]">
        —
      </span>
    );
  }
  const toneClass =
    tone === "warning"
      ? "text-[color:var(--status-warning-text)]"
      : tone === "info"
        ? "text-[color:var(--status-info-text)]"
        : "text-[color:var(--text-primary)]";
  return (
    <span className={`font-mono text-[12px] font-semibold tabular-nums ${toneClass}`}>
      {value}
    </span>
  );
}

// ─── Vendors at risk ─────────────────────────────────────────────

function VendorsAtRiskCard({
  vendors,
  className,
}: {
  vendors: RollupVendorAtRisk[];
  className?: string;
}) {
  const rows = vendors.slice(0, 8);
  return (
    <Surface
      title="Proveedores en riesgo"
      description="Los expedientes con peor semáforo de toda la cartera."
      icon={WarningOctagon}
      className={className}
      bodyClassName={rows.length > 0 ? "p-0" : undefined}
    >
      {rows.length === 0 ? (
        <EmptyState
          icon={CheckCircle}
          title="Ningún proveedor en riesgo"
          description="Toda la cartera está en verde. Nada que perseguir hoy."
        />
      ) : (
        <ul className="divide-y divide-[color:var(--border-subtle)]">
          {rows.map((vendor) => (
            <li
              key={vendor.vendor_id}
              className="flex flex-wrap items-center justify-between gap-3 px-5 py-3"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13px] font-semibold text-[color:var(--text-primary)]">
                  <Link
                    href={`/admin/vendors/${vendor.vendor_id}`}
                    className="hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]/40"
                  >
                    {vendor.vendor_name}
                  </Link>
                </p>
                <p className="truncate text-[11px] text-[color:var(--text-tertiary)]">
                  {vendor.client_name} · última actividad{" "}
                  {lastActivityLabel(vendor.last_activity_at)}
                </p>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[12px] tabular-nums text-[color:var(--text-secondary)]">
                    {Math.round(vendor.compliance_pct)}%
                  </span>
                  <Badge variant={semaphoreVariant(vendor.semaphore_level)}>
                    {semaphoreLabel(vendor.semaphore_level)}
                  </Badge>
                </div>
                <p className="font-mono text-[10px] tabular-nums text-[color:var(--text-tertiary)]">
                  {vendor.missing_required_count} faltantes ·{" "}
                  {vendor.rejected_or_correction_count} por corregir
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Surface>
  );
}

/** "hace 3h" / "hace 2d" style humanizer; falls back to an es-MX date. */
function lastActivityLabel(iso: string | null): string {
  if (!iso) return "sin registro";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "sin registro";
  const mins = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (mins < 60) return `hace ${Math.max(1, mins)} min`;
  const hours = Math.floor(mins / 60);
  if (hours < 48) return `hace ${hours}h`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `hace ${days}d`;
  return `el ${new Date(iso).toLocaleDateString("es-MX", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  })}`;
}

// ─── Operational inbox ───────────────────────────────────────────

function OperationalInbox({ inbox }: { inbox: AdminRollup["inbox"] }) {
  const rows: {
    href: string;
    icon: typeof EnvelopeSimple;
    label: string;
    caption: string;
    value: number;
  }[] = [
    {
      href: "/admin/contact-requests",
      icon: EnvelopeSimple,
      label: "Solicitudes de contacto",
      caption: "Leads del formulario público sin atender.",
      value: inbox.contact_requests_pending,
    },
    {
      href: "/admin/correction-requests",
      icon: PencilSimpleLine,
      label: "Correcciones pendientes",
      caption: "Cambios de datos propuestos por proveedores.",
      value: inbox.correction_requests_pending,
    },
    {
      href: "/admin/feedback-reports",
      icon: Megaphone,
      label: "Feedback nuevo",
      caption: "Reportes de bugs y mejoras sin triage.",
      value: inbox.feedback_reports_new,
    },
  ];
  return (
    <Surface
      title="Bandeja operativa"
      description="Pendientes fuera de la cola documental."
      bodyClassName="p-0"
    >
      <ul className="divide-y divide-[color:var(--border-subtle)]">
        {rows.map((row) => {
          const Icon = row.icon;
          const muted = row.value === 0;
          return (
            <li key={row.href}>
              <Link
                href={row.href}
                className="flex items-center gap-3 px-5 py-3 transition-colors hover:bg-[color:var(--surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[color:var(--border-focus)]/40"
              >
                <span
                  className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-md ${
                    muted
                      ? "bg-[color:var(--surface-sunken)] text-[color:var(--text-tertiary)]"
                      : "bg-[color:var(--surface-brand-muted)] text-[color:var(--text-brand)]"
                  }`}
                >
                  <Icon className="h-4 w-4" weight="bold" aria-hidden="true" />
                </span>
                <div className="min-w-0 flex-1">
                  <p
                    className={`text-[13px] font-semibold ${
                      muted
                        ? "text-[color:var(--text-secondary)]"
                        : "text-[color:var(--text-primary)]"
                    }`}
                  >
                    {row.label}
                  </p>
                  <p className="text-[11px] text-[color:var(--text-tertiary)]">
                    {row.caption}
                  </p>
                </div>
                <span
                  className={`font-mono text-lg font-semibold tabular-nums ${
                    muted
                      ? "text-[color:var(--text-tertiary)]"
                      : "text-[color:var(--text-primary)]"
                  }`}
                >
                  {row.value}
                </span>
                <ArrowRight
                  className="h-4 w-4 shrink-0 text-[color:var(--text-tertiary)]"
                  weight="bold"
                  aria-hidden="true"
                />
              </Link>
            </li>
          );
        })}
      </ul>
    </Surface>
  );
}

// ─── Loading skeleton ────────────────────────────────────────────

function DashboardSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-live="polite">
      <span className="sr-only">Cargando la consola de operaciones…</span>
      <div className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-5 shadow-xs">
        <div className="grid gap-5 md:grid-cols-[1fr,320px] md:items-center">
          <div className="space-y-2">
            <Skeleton className="h-3 w-3/12" />
            <Skeleton className="h-6 w-9/12" />
            <Skeleton className="h-3 w-8/12" />
            <Skeleton className="h-3 w-5/12" />
          </div>
          <Skeleton className="h-[148px] w-full rounded-md" />
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-[88px] rounded-lg" />
        ))}
      </div>
      <div className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-xs">
        <div className="border-b border-[color:var(--border-subtle)] px-5 py-3">
          <Skeleton className="h-3 w-2/12" />
        </div>
        <div className="divide-y divide-[color:var(--border-subtle)]">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="flex items-center gap-3 px-5 py-3">
              <Skeleton className="h-4 w-4/12" />
              <Skeleton className="h-4 w-2/12" />
              <Skeleton className="h-4 w-2/12" />
              <Skeleton className="h-4 w-2/12" />
            </div>
          ))}
        </div>
      </div>
      <div className="grid gap-5 lg:grid-cols-3">
        <Skeleton className="h-56 rounded-lg lg:col-span-2" />
        <Skeleton className="h-56 rounded-lg" />
      </div>
    </div>
  );
}
