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
import {
  StatCard,
  Surface,
} from "@/components/checkwise/dashboard/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

import { AdminShell } from "../_shell";
import { getAdminOverview, type AdminOverview } from "@/lib/api/admin";

export default function AdminDashboardPage() {
  const [data, setData] = useState<AdminOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
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
  }, []);

  return (
    <AdminShell
      title="Resumen operativo"
      description="Vista panorámica del control plane: clientes, proveedores, workspaces activos y bandeja de revisión humana."
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
        <p className="rounded-md border border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-bg)] p-3 text-sm text-[color:var(--status-warning-text)]">
          {error}
        </p>
      ) : !data ? (
        <DashboardSkeleton />
      ) : (
        <div className="space-y-6">
          <AdminHero data={data} />

          <div className="cw-stagger grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label="Clientes"
              value={data.clients_total}
              tone="brand"
              icon={IdentificationCard}
              caption="Empresas dadas de alta en CheckWise."
              href="/admin/clients"
            />
            <StatCard
              label="Proveedores"
              value={data.vendors_total}
              tone="brand"
              icon={Storefront}
              caption="Total de proveedores REPSE registrados."
              href="/admin/vendors"
            />
            <StatCard
              label="Workspaces activos"
              value={data.active_workspaces_total}
              tone="teal"
              icon={Users}
              caption="Proveedores con expediente vivo."
            />
            <StatCard
              label="En revisión"
              value={data.pending_reviews_total}
              tone="info"
              icon={HourglassHigh}
              caption="Documentos en cola humana."
              href="/admin/reviewer"
            />
          </div>

          <div className="cw-stagger grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <StatCard
              label="Rechazos / aclaración"
              value={data.rejected_or_correction_total}
              tone={data.rejected_or_correction_total > 0 ? "warning" : "success"}
              icon={WarningCircle}
              caption="Documentos que requieren acción del proveedor."
            />
            <StatCard
              label="Entregas recientes"
              value={data.recent_submissions_total}
              tone="brand"
              icon={Files}
              caption="Cargas en los últimos días."
            />
            <StatCard
              label="Eventos audit log"
              value={data.recent_audit_events_total}
              tone="neutral"
              icon={ListMagnifyingGlass}
              caption="Trazabilidad reciente del sistema."
              href="/admin/audit-log"
            />
          </div>

          <OperationsLauncher />
        </div>
      )}
    </AdminShell>
  );
}

// ─── Hero ────────────────────────────────────────────────────────

function AdminHero({ data }: { data: AdminOverview }) {
  const utilisation =
    data.vendors_total === 0
      ? 0
      : Math.round((data.active_workspaces_total / Math.max(1, data.vendors_total)) * 100);
  const reviewBacklog = data.pending_reviews_total + data.rejected_or_correction_total;
  return (
    <section className="cw-fade-up overflow-hidden rounded-xl border border-[color:var(--border-default)] bg-gradient-to-br from-[color:var(--surface-brand-muted)] via-[color:var(--surface-raised)] to-[color:var(--surface-raised)] p-6 md:p-8">
      <div className="grid gap-6 md:grid-cols-[auto,1fr] md:items-center">
        <RadialGauge
          value={utilisation}
          tone="brand"
          size={148}
          thickness={12}
          label={`${utilisation}%`}
          caption="workspaces activos"
        />
        <div className="min-w-0 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="brand">Control plane</Badge>
            <span className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
              {data.clients_total} clientes · {data.vendors_total} proveedores
            </span>
          </div>
          <p className="text-lg font-semibold tracking-tight text-[color:var(--text-primary)] md:text-xl">
            {heroHeadline(data, reviewBacklog)}
          </p>
          <p className="max-w-2xl text-[13px] leading-relaxed text-[color:var(--text-secondary)]">
            {heroDescription(data, reviewBacklog)}
          </p>
        </div>
      </div>
    </section>
  );
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
    parts.push(`${data.recent_audit_events_total} eventos audit log recientes`);
  if (parts.length === 0)
    return backlog === 0
      ? "No hay actividad operativa pendiente — todo está al día."
      : "Todo bajo control. Revisa la sección inferior para entrar a cada superficie.";
  return parts.join(" · ") + ".";
}

// ─── Operations launcher ─────────────────────────────────────────

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
      href: "/admin/audit-log",
      icon: ListMagnifyingGlass,
      label: "Audit log",
      helper: "Eventos del sistema.",
    },
  ];
  return (
    <Surface
      title="Superficies operativas"
      description="Cada cambio queda firmado en el audit log."
    >
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((item) => (
          <li key={item.href}>
            <Link
              href={item.href}
              className="cw-hover-lift block rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-page)] p-3 transition-colors hover:bg-[color:var(--surface-hover)]"
            >
              <div className="flex items-center gap-2.5">
                <span className="flex h-9 w-9 items-center justify-center rounded-md bg-[color:var(--surface-brand-muted)] text-[color:var(--text-brand)]">
                  <item.icon className="h-4 w-4" weight="duotone" aria-hidden="true" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="flex items-center justify-between gap-1 text-[13px] font-semibold text-[color:var(--text-primary)]">
                    {item.label}
                    <ArrowRight
                      className="h-3 w-3 text-[color:var(--text-tertiary)]"
                      weight="bold"
                      aria-hidden="true"
                    />
                  </p>
                  <p className="text-[11px] text-[color:var(--text-secondary)]">
                    {item.helper}
                  </p>
                </div>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </Surface>
  );
}

function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      <div className="h-40 animate-pulse rounded-xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]" />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div
            key={i}
            className="h-28 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]"
          />
        ))}
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="h-28 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]"
          />
        ))}
      </div>
    </div>
  );
}
