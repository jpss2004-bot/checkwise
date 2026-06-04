"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Books,
  CalendarBlank,
  ClipboardText,
  Files,
  HourglassHigh,
  IdentificationCard,
  ListChecks,
  ListMagnifyingGlass,
  Storefront,
  Users,
  WarningCircle,
} from "@phosphor-icons/react";

import { RadialGauge } from "@/components/checkwise/charts";
import { Button } from "@/components/ui/button";
import { MetadataStrip } from "@/components/ui/metadata-strip";
import {
  ErrorState,
  Skeleton,
} from "@/components/checkwise/portal/state-surfaces";

import { AdminShell } from "../_shell";
import { getAdminOverview, type AdminOverview } from "@/lib/api/admin";

export default function AdminDashboardPage() {
  const [data, setData] = useState<AdminOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(null);
    getAdminOverview()
      .then((overview) => {
        if (!cancelled) setData(overview);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Error al cargar el resumen.");
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  return (
    <AdminShell
      title="Resumen operativo"
      description="Vista panorámica de la operación: clientes, proveedores, espacios activos y la bandeja de revisión humana."
      actions={
        <Button asChild size="sm" variant="outline">
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
      ) : !data ? (
        <DashboardSkeleton />
      ) : (
        <div className="space-y-6">
          <AdminHero data={data} />
          <AdminSignals data={data} />
          <OperationsLauncher />
        </div>
      )}
    </AdminShell>
  );
}

// ─── Hero (asymmetric, no gradient) ─────────────────────────────

function AdminHero({ data }: { data: AdminOverview }) {
  const reviewBacklog =
    data.pending_reviews_total + data.rejected_or_correction_total;
  // The gauge headline is a REAL count (active workspaces), not a
  // synthetic percentage. The ring is a coverage proportion of active
  // workspaces against vendors, clamped by RadialGauge so it never reads
  // a misleading ">100%" when a vendor holds more than one workspace.
  return (
    <section className="cw-fade-up grid gap-5 rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-5 shadow-xs md:grid-cols-[auto,1fr] md:items-center md:gap-8 md:p-6">
      <RadialGauge
        value={data.active_workspaces_total}
        max={Math.max(1, data.vendors_total)}
        tone="brand"
        size={140}
        thickness={12}
        label={data.active_workspaces_total.toString()}
        caption={`espacios activos · ${data.vendors_total} proveedores`}
      />
      <div className="min-w-0 space-y-3">
        <p className="cw-eyebrow">Panorama · {data.clients_total} clientes · {data.vendors_total} proveedores</p>
        <p className="text-xl font-semibold leading-tight tracking-tight text-[color:var(--text-primary)]">
          {heroHeadline(data, reviewBacklog)}
        </p>
        <p className="max-w-2xl text-[13px] leading-relaxed text-[color:var(--text-secondary)]">
          {heroDescription(data, reviewBacklog)}
        </p>
        <MetadataStrip
          bordered={false}
          className="!py-0"
          items={[
            {
              label: "Revisar",
              value: formatCount(data.pending_reviews_total),
              mono: true,
            },
            {
              label: "Correcciones",
              value: formatCount(data.rejected_or_correction_total),
              mono: true,
              tone: data.rejected_or_correction_total > 0 ? "warning" : "default",
            },
            {
              label: "Audit recientes",
              value: formatCount(data.recent_audit_events_total),
              mono: true,
            },
          ]}
        />
      </div>
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
    parts.push(`${data.recent_audit_events_total} eventos recientes en la bitácora de auditoría`);
  if (parts.length === 0)
    return backlog === 0
      ? "No hay actividad operativa pendiente. Todo está al día."
      : "Todo bajo control. Revisa la sección inferior para entrar a cada superficie.";
  return parts.join(" · ") + ".";
}

// ─── Vertical signals list (replaces 4-up + 3-up StatCard grids) ──

type SignalRow = {
  href?: string;
  icon: typeof IdentificationCard;
  label: string;
  caption: string;
  value: number;
  tone?: "default" | "warning" | "teal";
};

function AdminSignals({ data }: { data: AdminOverview }) {
  const rows: SignalRow[] = [
    {
      href: "/admin/clients",
      icon: IdentificationCard,
      label: "Clientes",
      caption: "Empresas dadas de alta en CheckWise.",
      value: data.clients_total,
    },
    {
      href: "/admin/vendors",
      icon: Storefront,
      label: "Proveedores",
      caption: "Proveedores REPSE registrados.",
      value: data.vendors_total,
    },
    {
      icon: Users,
      label: "Espacios activos",
      caption: "Proveedores con expediente vivo.",
      value: data.active_workspaces_total,
      tone: "teal",
    },
    {
      href: "/admin/reviewer",
      icon: HourglassHigh,
      label: "En revisión",
      caption: "Documentos en cola humana.",
      value: data.pending_reviews_total,
    },
    {
      icon: WarningCircle,
      label: "Rechazos / aclaración",
      caption: "Documentos que requieren acción del proveedor.",
      value: data.rejected_or_correction_total,
      tone: data.rejected_or_correction_total > 0 ? "warning" : "default",
    },
    {
      icon: Files,
      label: "Entregas recientes",
      caption: "Cargas en los últimos días.",
      value: data.recent_submissions_total,
    },
    {
      href: "/platform/audit-log",
      icon: ListMagnifyingGlass,
      label: "Eventos de auditoría",
      caption: "Trazabilidad reciente del sistema.",
      value: data.recent_audit_events_total,
    },
  ];

  return (
    <section
      aria-label="Estado operativo"
      className="cw-fade-up rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-xs"
    >
      <header className="border-b border-[color:var(--border-subtle)] px-5 py-3">
        <p className="cw-eyebrow">Estado operativo</p>
        <p className="text-sm font-semibold text-[color:var(--text-primary)]">
          Señales agrupadas
        </p>
      </header>
      <ul className="divide-y divide-[color:var(--border-subtle)]">
        {rows.map((row) => (
          <li key={row.label}>
            <SignalRow row={row} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function SignalRow({ row }: { row: SignalRow }) {
  const Icon = row.icon;
  const valueTone =
    row.tone === "warning"
      ? "text-[color:var(--status-warning-text)]"
      : row.tone === "teal"
      ? "text-[color:var(--text-teal)]"
      : "text-[color:var(--text-primary)]";
  const content = (
    <div className="flex items-center gap-3 px-5 py-3 transition-colors hover:bg-[color:var(--surface-hover)]">
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-[color:var(--surface-sunken)] text-[color:var(--text-secondary)]">
        <Icon className="h-4 w-4" weight="bold" aria-hidden="true" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[13px] font-semibold text-[color:var(--text-primary)]">
          {row.label}
        </p>
        <p className="text-[11px] text-[color:var(--text-tertiary)]">
          {row.caption}
        </p>
      </div>
      <span
        className={`font-mono text-lg font-semibold tabular-nums ${valueTone}`}
      >
        {row.value}
      </span>
      {row.href ? (
        <ArrowRight
          className="h-4 w-4 shrink-0 text-[color:var(--text-tertiary)]"
          weight="bold"
          aria-hidden="true"
        />
      ) : (
        <span className="h-4 w-4 shrink-0" aria-hidden />
      )}
    </div>
  );
  if (row.href) {
    return (
      <Link
        href={row.href}
        className="block focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[color:var(--border-focus)]/40"
      >
        {content}
      </Link>
    );
  }
  return content;
}

// ─── Operations launcher (vertical bordered list) ────────────────

function OperationsLauncher() {
  const items: {
    href: string;
    icon: typeof IdentificationCard;
    label: string;
    helper: string;
  }[] = [
    {
      href: "/admin/clients",
      icon: IdentificationCard,
      label: "Clientes",
      helper: "Alta, edición y estatus.",
    },
    {
      href: "/admin/vendors",
      icon: Storefront,
      label: "Proveedores",
      helper: "Registro, contacto y persona.",
    },
    {
      href: "/admin/requirements",
      icon: Books,
      label: "Requisitos",
      helper: "Catálogo regulatorio REPSE.",
    },
    {
      href: "/admin/calendar",
      icon: CalendarBlank,
      label: "Calendario",
      helper: "Periodos y obligaciones.",
    },
    {
      href: "/admin/reviewer",
      icon: ListChecks,
      label: "Bandeja",
      helper: "Cola de revisión humana.",
    },
    {
      href: "/platform/audit-log",
      icon: ListMagnifyingGlass,
      label: "Bitácora de auditoría",
      helper: "Eventos del sistema.",
    },
  ];
  return (
    <section
      aria-label="Superficies operativas"
      className="cw-fade-up rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-xs"
    >
      <header className="border-b border-[color:var(--border-subtle)] px-5 py-3">
        <p className="cw-eyebrow">Superficies operativas</p>
        <p className="text-sm font-semibold text-[color:var(--text-primary)]">
          Cada cambio queda firmado en la bitácora de auditoría
        </p>
      </header>
      <ul className="divide-y divide-[color:var(--border-subtle)]">
        {items.map((item) => (
          <li key={item.href}>
            <Link
              href={item.href}
              className="flex items-center gap-3 px-5 py-3 transition-colors hover:bg-[color:var(--surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[color:var(--border-focus)]/40"
            >
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-[color:var(--surface-brand-muted)] text-[color:var(--text-brand)]">
                <item.icon className="h-4 w-4" weight="bold" aria-hidden="true" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-[13px] font-semibold text-[color:var(--text-primary)]">
                  {item.label}
                </p>
                <p className="text-[11px] text-[color:var(--text-tertiary)]">
                  {item.helper}
                </p>
              </div>
              <ArrowRight
                className="h-4 w-4 shrink-0 text-[color:var(--text-tertiary)]"
                weight="bold"
                aria-hidden="true"
              />
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

function DashboardSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-live="polite">
      <span className="sr-only">Cargando resumen operativo…</span>
      <div className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-5 shadow-xs">
        <div className="grid gap-5 md:grid-cols-[auto,1fr] md:items-center">
          <Skeleton className="h-[140px] w-[140px] rounded-full" />
          <div className="space-y-2">
            <Skeleton className="h-3 w-3/12" />
            <Skeleton className="h-6 w-9/12" />
            <Skeleton className="h-3 w-8/12" />
          </div>
        </div>
      </div>
      {[0, 1].map((g) => (
        <div
          key={g}
          className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-xs"
        >
          <div className="border-b border-[color:var(--border-subtle)] px-5 py-3">
            <Skeleton className="h-3 w-2/12" />
          </div>
          <div className="divide-y divide-[color:var(--border-subtle)]">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="flex items-center gap-3 px-5 py-3">
                <Skeleton className="h-8 w-8 rounded-md" />
                <div className="flex-1 space-y-1">
                  <Skeleton className="h-3 w-4/12" />
                  <Skeleton className="h-3 w-6/12" />
                </div>
                <Skeleton className="h-5 w-10" />
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
