"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Bell,
  Buildings,
  CalendarBlank,
  CheckCircle,
  Files,
  HourglassHigh,
  IdentificationCard,
  Storefront,
  Warning,
  WarningOctagon,
} from "@phosphor-icons/react";

import {
  Donut,
  RadialGauge,
  StackedBars,
  type ChartSegment,
} from "@/components/checkwise/charts";
import {
  EmptyState,
  Surface,
} from "@/components/checkwise/dashboard/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

import { ClientShell } from "../_shell";
import { VendorRef } from "@/components/checkwise/vendor-ref";
import {
  getClientMe,
  getClientOverview,
  getClientProfile,
  listClientNotifications,
  listClientActivity,
  listClientSubmissions,
  type ClientActivityItem,
  type ClientMe,
  type ClientNotificationItem,
  type ClientOverview,
  type ClientProfile,
  type ClientSubmissionItem,
} from "@/lib/api/client";
import { useUrlClientId } from "@/lib/workspace/use-url-client-id";
import { statusLabel, statusVariant } from "@/lib/constants/statuses";

/**
 * Client dashboard — redesigned.
 *
 * Hero: a radial compliance gauge + headline status next to a
 * three-segment semaphore donut. KPI strip below with sparkline-ish
 * accents. Two-column body holds (left) the recent submission feed
 * and risk attention list; (right) due-soon, recent activity, and
 * quick links into the operational surfaces.
 */
export default function ClientDashboardPage() {
  const urlClientId = useUrlClientId();
  const [me, setMe] = useState<ClientMe | null>(null);
  const [overview, setOverview] = useState<ClientOverview | null>(null);
  const [submissions, setSubmissions] = useState<ClientSubmissionItem[]>([]);
  const [activity, setActivity] = useState<ClientActivityItem[]>([]);
  const [notifications, setNotifications] = useState<ClientNotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [clientId, setClientId] = useState<string | null>(urlClientId);
  const [error, setError] = useState<string | null>(null);
  const [profile, setProfile] = useState<ClientProfile | null>(null);

  // Profile fetch is independent from overview so a late return on
  // the heavier overview query doesn't block the "termina tu alta"
  // banner from rendering. Failures are silent — the banner just
  // stays hidden.
  useEffect(() => {
    let cancelled = false;
    getClientProfile(urlClientId ? { client_id: urlClientId } : undefined)
      .then((p) => {
        if (cancelled) return;
        setProfile(p);
      })
      .catch(() => {
        // Silent — the dashboard still works without the banner.
      });
    return () => {
      cancelled = true;
    };
  }, [urlClientId]);

  useEffect(() => {
    let cancelled = false;
    getClientMe()
      .then((meData) => {
        if (cancelled) return;
        setMe(meData);
        // URL ``?client_id=`` wins over the user's default — that's
        // how internal-admin inspection of any tenant works. For
        // regular client_admin users the URL param normally matches
        // ``default_client_id`` (or is absent), so this collapses to
        // the previous behavior.
        setClientId(urlClientId ?? meData.default_client_id);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Error al cargar identidad.");
      });
    return () => {
      cancelled = true;
    };
  }, [urlClientId]);

  useEffect(() => {
    if (!me && !clientId) return;
    let cancelled = false;
    setError(null);
    const params = clientId ? { client_id: clientId } : undefined;
    Promise.all([
      getClientOverview(params),
      listClientSubmissions({ ...(params ?? {}), limit: 6 }),
      listClientActivity({ ...(params ?? {}), limit: 8 }),
      listClientNotifications({ ...(params ?? {}), limit: 5 }),
    ])
      .then(([ov, subs, act, notes]) => {
        if (cancelled) return;
        setOverview(ov);
        setSubmissions(subs.items);
        setActivity(act.items);
        setNotifications(notes.items);
        setUnreadCount(notes.unread_count);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Error al cargar resumen.");
      });
    return () => {
      cancelled = true;
    };
  }, [clientId, me]);

  return (
    <ClientShell
      title="Resumen del cliente"
      description="Cumplimiento de tus proveedores REPSE — riesgo, faltantes, entregas recientes y próximos vencimientos en una sola vista."
      actions={
        me && me.visible_client_ids.length > 1 ? (
          <ClientSwitcher
            value={clientId ?? ""}
            options={me.visible_client_ids}
            onChange={setClientId}
          />
        ) : null
      }
    >
      {error ? (
        <div className="rounded-lg border border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-bg)] p-4 text-sm text-[color:var(--status-warning-text)]">
          {error}
        </div>
      ) : !overview ? (
        <DashboardSkeleton />
      ) : (
        <div className="space-y-7">
          {profile && profile.onboarding_completed_at === null ? (
            <OnboardingPromptBanner clientName={profile.name} />
          ) : null}
          <ClientHero overview={overview} />
          <ClientKpiStrip overview={overview} />
          <div className="cw-stagger grid gap-5 lg:grid-cols-3">
            <div className="space-y-5 lg:col-span-2">
              <SemaphoreDistribution overview={overview} />
              <RecentSubmissionsCard rows={submissions} />
            </div>
            <div className="space-y-5">
              <NotificationCard rows={notifications} unreadCount={unreadCount} />
              <QuickLinks />
              <RecentActivityCard rows={activity} />
            </div>
          </div>
        </div>
      )}
    </ClientShell>
  );
}

// ─── Client switcher (header actions) ────────────────────────────

function ClientSwitcher({
  value,
  options,
  onChange,
}: {
  value: string;
  options: string[];
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex items-center gap-2 rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-3 py-1.5 text-xs text-[color:var(--text-secondary)]">
      <Buildings className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
      <span className="font-mono text-[10px] uppercase tracking-wide">Cliente</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="bg-transparent font-medium text-[color:var(--text-primary)] focus:outline-none"
      >
        {options.map((cid) => (
          <option key={cid} value={cid}>
            {cid}
          </option>
        ))}
      </select>
    </label>
  );
}

// ─── Hero (compliance + headline) ────────────────────────────────

function ClientHero({ overview }: { overview: ClientOverview }) {
  const tone =
    overview.compliance_pct >= 85
      ? "success"
      : overview.compliance_pct >= 60
        ? "warning"
        : "error";
  return (
    <section className="cw-fade-up rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-5 shadow-xs md:p-6">
      <div className="grid gap-5 md:grid-cols-[auto,1fr] md:items-center md:gap-8">
        <RadialGauge
          value={overview.compliance_pct}
          tone={tone}
          size={140}
          thickness={12}
          label={`${Math.round(overview.compliance_pct)}%`}
          caption="cumplimiento"
        />
        <div className="min-w-0 space-y-3">
          <p className="cw-eyebrow">
            {overview.client_name} · {overview.active_workspaces_total} workspace
            {overview.active_workspaces_total === 1 ? "" : "s"} activo
            {overview.active_workspaces_total === 1 ? "" : "s"}
          </p>
          <p className="text-xl font-semibold leading-tight tracking-tight text-[color:var(--text-primary)]">
            {summaryHeadline(overview)}
          </p>
          <p className="max-w-2xl text-[13px] leading-relaxed text-[color:var(--text-secondary)]">
            {summaryDescription(overview)}
          </p>
          {overview.last_activity_at ? (
            <p className="font-mono text-[11px] tabular-nums text-[color:var(--text-tertiary)]">
              Última actividad ·{" "}
              {new Date(overview.last_activity_at).toLocaleString("es-MX")}
            </p>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function summaryHeadline(o: ClientOverview): string {
  if (o.red_count > 0)
    return `Tienes ${o.red_count} proveedor${o.red_count === 1 ? "" : "es"} en rojo`;
  if (o.yellow_count > 0)
    return `Tienes ${o.yellow_count} proveedor${o.yellow_count === 1 ? "" : "es"} en amarillo`;
  if (o.green_count > 0)
    return "Todos tus proveedores están en verde";
  return "No hay proveedores activos para mostrar";
}

function summaryDescription(o: ClientOverview): string {
  const parts: string[] = [];
  if (o.missing_required_total > 0) parts.push(`${o.missing_required_total} faltantes obligatorios`);
  if (o.rejected_or_correction_total > 0)
    parts.push(`${o.rejected_or_correction_total} rechazos o aclaraciones pendientes`);
  if (o.pending_reviews_total > 0)
    parts.push(`${o.pending_reviews_total} en revisión por nuestro equipo`);
  if (o.due_soon_total > 0)
    parts.push(`${o.due_soon_total} obligaciones vencen en los próximos 14 días`);
  if (parts.length === 0) return "Tu portafolio está al día. Te avisaremos cuando algo necesite tu atención.";
  return parts.join(" · ") + ".";
}

// ─── KPI strip ────────────────────────────────────────────────────

// Junta 2026-05-23 — soft banner that prompts the client_admin to
// finish their self-service alta on /client/onboarding. Hidden once
// ``onboarding_completed_at`` is set on the row.
function OnboardingPromptBanner({ clientName }: { clientName: string }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-bg)] p-4">
      <div className="flex items-start gap-3">
        <IdentificationCard
          className="mt-0.5 h-5 w-5 text-[color:var(--status-warning-text)]"
          weight="bold"
          aria-hidden="true"
        />
        <div className="min-w-0">
          <p className="text-sm font-semibold text-[color:var(--text-primary)]">
            Termina tu alta, {clientName}
          </p>
          <p className="mt-0.5 text-xs text-[color:var(--text-secondary)]">
            Nuestro equipo precargó tus datos básicos. Completa el
            sector, domicilio fiscal y teléfono para activar tu
            portafolio. No te pediremos archivos.
          </p>
        </div>
      </div>
      <Button asChild size="sm">
        <Link href="/client/onboarding">
          Completar mi alta
          <ArrowRight className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
        </Link>
      </Button>
    </div>
  );
}

function ClientKpiStrip({ overview }: { overview: ClientOverview }) {
  const rows: {
    href?: string;
    icon: typeof Storefront;
    label: string;
    caption: string;
    value: number;
    tone?: "default" | "warning" | "teal";
  }[] = [
    {
      href: "/client/vendors",
      icon: Storefront,
      label: "Proveedores",
      caption: `${overview.active_workspaces_total} workspaces activos.`,
      value: overview.vendors_total,
    },
    {
      icon: Files,
      label: "Faltantes obligatorios",
      caption: "Documentos REPSE pendientes de carga.",
      value: overview.missing_required_total,
      tone:
        overview.missing_required_total > 0 ? "warning" : "default",
    },
    {
      icon: HourglassHigh,
      label: "En revisión",
      caption: "Nuestro equipo legal está validando.",
      value: overview.pending_reviews_total,
    },
    {
      href: "/client/calendar",
      icon: CalendarBlank,
      label: "Vencen ≤14 días",
      caption: "Próximas obligaciones críticas.",
      value: overview.due_soon_total,
      tone:
        overview.due_soon_total > 0 ? "warning" : "default",
    },
  ];

  return (
    <section
      aria-label="Señales del portafolio"
      className="cw-fade-up rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-xs"
    >
      <header className="border-b border-[color:var(--border-subtle)] px-5 py-3">
        <p className="cw-eyebrow">Señales del portafolio</p>
      </header>
      <ul className="divide-y divide-[color:var(--border-subtle)]">
        {rows.map((row) => {
          const Icon = row.icon;
          const tone =
            row.tone === "warning"
              ? "text-[color:var(--status-warning-text)]"
              : row.tone === "teal"
              ? "text-[color:var(--text-teal)]"
              : "text-[color:var(--text-primary)]";
          const content = (
            <div className="flex items-center gap-3 px-5 py-3 transition-colors hover:bg-[color:var(--surface-hover)]">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-[color:var(--surface-sunken)] text-[color:var(--text-secondary)]">
                <Icon className="h-4 w-4" weight="bold" aria-hidden />
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
                className={`font-mono text-lg font-semibold tabular-nums ${tone}`}
              >
                {row.value === 0 ? "—" : row.value}
              </span>
              {row.href ? (
                <ArrowRight
                  className="h-4 w-4 shrink-0 text-[color:var(--text-tertiary)]"
                  weight="bold"
                  aria-hidden
                />
              ) : (
                <span className="h-4 w-4 shrink-0" aria-hidden />
              )}
            </div>
          );
          return (
            <li key={row.label}>
              {row.href ? (
                <Link
                  href={row.href}
                  className="block focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[color:var(--border-focus)]/40"
                >
                  {content}
                </Link>
              ) : (
                content
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

// ─── Semaphore distribution ──────────────────────────────────────

function SemaphoreDistribution({ overview }: { overview: ClientOverview }) {
  const segments: ChartSegment[] = [
    { label: "Verde · al día", value: overview.green_count, tone: "success" },
    { label: "Amarillo · pendiente", value: overview.yellow_count, tone: "warning" },
    { label: "Rojo · crítico", value: overview.red_count, tone: "error" },
  ];
  const total = segments.reduce((sum, s) => sum + s.value, 0);
  return (
    <Surface
      title="Distribución de tu portafolio"
      description="Cómo se reparten tus proveedores según su nivel de cumplimiento."
      actions={
        <Button asChild variant="outline" size="sm">
          <Link href="/client/vendors">
            <span>Ver proveedores</span>
            <ArrowRight className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
          </Link>
        </Button>
      }
    >
      {total === 0 ? (
        <EmptyState
          icon={Storefront}
          title="Sin proveedores activos"
          description="Cuando registres proveedores, aquí verás cómo se distribuye su riesgo."
        />
      ) : (
        <div className="grid gap-5 md:grid-cols-[auto,1fr] md:items-center">
          <Donut
            segments={segments}
            size={132}
            thickness={14}
            centerLabel={total}
            centerCaption="proveedores"
            showLegend={false}
          />
          <div className="space-y-2.5">
            {segments.map((seg) => (
              <SemaphoreRow
                key={seg.label}
                segment={seg}
                total={total}
              />
            ))}
            <div className="mt-3 border-t border-[color:var(--border-subtle)] pt-3">
              <StackedBars
                segments={segments}
                height={10}
                showLegend={false}
              />
            </div>
          </div>
        </div>
      )}
    </Surface>
  );
}

function SemaphoreRow({
  segment,
  total,
}: {
  segment: ChartSegment;
  total: number;
}) {
  const pct = total === 0 ? 0 : Math.round((segment.value / total) * 100);
  const toneIcon =
    segment.tone === "success"
      ? CheckCircle
      : segment.tone === "warning"
        ? Warning
        : WarningOctagon;
  const Icon = toneIcon;
  const toneText =
    segment.tone === "success"
      ? "text-[color:var(--status-success-text)]"
      : segment.tone === "warning"
        ? "text-[color:var(--status-warning-text)]"
        : "text-[color:var(--status-error-text)]";
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] px-3 py-2">
      <span className={`flex items-center gap-2 text-[13px] font-medium ${toneText}`}>
        <Icon className="h-4 w-4" weight="fill" aria-hidden="true" />
        {segment.label}
      </span>
      <span className="flex items-center gap-2">
        <span className="font-mono text-[11px] tabular-nums text-[color:var(--text-tertiary)]">
          {pct}%
        </span>
        <span className="font-mono text-lg font-semibold tabular-nums text-[color:var(--text-primary)]">
          {segment.value}
        </span>
      </span>
    </div>
  );
}

// ─── Recent submissions ──────────────────────────────────────────

function RecentSubmissionsCard({ rows }: { rows: ClientSubmissionItem[] }) {
  return (
    <Surface
      title="Entregas recientes"
      icon={Files}
      actions={
        <Button asChild variant="outline" size="sm">
          <Link href="/client/submissions">
            <span>Ver todas</span>
            <ArrowRight className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
          </Link>
        </Button>
      }
    >
      {rows.length === 0 ? (
        <EmptyState
          icon={Files}
          title="Sin entregas recientes"
          description="Cuando tus proveedores suban documentos, aparecerán aquí."
        />
      ) : (
        <ul className="divide-y divide-[color:var(--border-subtle)]">
          {rows.slice(0, 6).map((row) => (
            <li
              key={row.submission_id}
              className="flex items-start justify-between gap-3 py-3 first:pt-0 last:pb-0"
            >
              <div className="min-w-0">
                <p className="truncate text-[13px] font-medium text-[color:var(--text-primary)]">
                  <VendorRef vendorId={row.vendor_id} vendorName={row.vendor_name} />
                </p>
                <p className="truncate text-[12px] text-[color:var(--text-secondary)]">
                  {row.requirement_name ?? row.requirement_code ?? "—"}
                  {row.period_key ? (
                    <span className="ml-2 font-mono text-[11px] text-[color:var(--text-tertiary)]">
                      {row.period_key}
                    </span>
                  ) : null}
                </p>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1">
                <StatusPill status={row.status} />
                <span className="font-mono text-[10px] text-[color:var(--text-tertiary)]">
                  {timeAgo(row.submitted_at)}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Surface>
  );
}

// Both the label and the color tone are pulled from the central statuses
// dictionary so a vocabulary or color change anywhere propagates here
// without a hunt (Audit F2).
function StatusPill({ status }: { status: string }) {
  return (
    <Badge variant={statusVariant(status)}>
      {statusLabel(status)}
    </Badge>
  );
}

// ─── Quick links ─────────────────────────────────────────────────

function NotificationCard({
  rows,
  unreadCount,
}: {
  rows: ClientNotificationItem[];
  unreadCount: number;
}) {
  return (
    <Surface
      title="Novedades"
      icon={Bell}
      actions={
        <Link
          href="/client/notifications"
          className="text-[11px] font-medium text-[color:var(--text-link)] hover:underline"
        >
          Ver todas
        </Link>
      }
    >
      {rows.length === 0 ? (
        <EmptyState
          icon={Bell}
          title="Sin novedades"
          description="Cuando un proveedor suba documentos o haya avances, apareceran aqui."
        />
      ) : (
        <ul className="space-y-3">
          {rows.slice(0, 5).map((row) => (
            <li key={row.id} className="flex items-start gap-3">
              <span
                aria-hidden="true"
                className={
                  "mt-1.5 h-2 w-2 shrink-0 rounded-full " +
                  (row.read_at ? "bg-[color:var(--border-subtle)]" : "bg-[color:var(--text-teal)]")
                }
              />
              <div className="min-w-0 flex-1">
                <p className="truncate text-[12px] font-medium text-[color:var(--text-primary)]">
                  {row.title}
                </p>
                <p className="mt-0.5 line-clamp-2 text-[11px] text-[color:var(--text-secondary)]">
                  {row.body}
                </p>
                <p className="mt-1 font-mono text-[10px] text-[color:var(--text-tertiary)]">
                  {row.vendor_id && row.vendor_name ? (
                    <VendorRef
                      vendorId={row.vendor_id}
                      vendorName={row.vendor_name}
                      muted
                    />
                  ) : (
                    row.vendor_name ?? "Cliente"
                  )}{" "}
                  · {timeAgo(row.created_at)}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
      {unreadCount > 0 ? (
        <p className="mt-3 rounded-md bg-[color:var(--surface-teal-muted)] px-2 py-1.5 text-[11px] font-medium text-[color:var(--text-teal)]">
          {unreadCount} sin leer
        </p>
      ) : null}
    </Surface>
  );
}

function QuickLinks() {
  const items: { href: string; label: string; helper: string }[] = [
    {
      href: "/client/vendors",
      label: "Proveedores",
      helper: "Lista filtrable con su semáforo.",
    },
    {
      href: "/client/calendar",
      label: "Calendario",
      helper: "Vista anual de obligaciones.",
    },
    {
      href: "/client/submissions",
      label: "Entregas",
      helper: "Búsqueda + filtros de cargas.",
    },
    {
      href: "/client/metadata",
      label: "Metadata",
      helper: "Excel maestro documental.",
    },
    {
      href: "/client/activity",
      label: "Actividad",
      helper: "Bitácora reciente del cliente.",
    },
  ];
  return (
    <Surface title="Accesos rápidos" bodyClassName="p-0">
      <ul className="divide-y divide-[color:var(--border-subtle)]">
        {items.map((item) => (
          <li key={item.href}>
            <Link
              href={item.href}
              className="flex items-center justify-between gap-3 px-4 py-2.5 text-[12px] transition-colors hover:bg-[color:var(--surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[color:var(--border-focus)]/40"
            >
              <div className="min-w-0">
                <p className="font-semibold text-[color:var(--text-primary)]">
                  {item.label}
                </p>
                <p className="mt-0.5 text-[11px] text-[color:var(--text-secondary)]">
                  {item.helper}
                </p>
              </div>
              <ArrowRight
                className="h-3.5 w-3.5 shrink-0 text-[color:var(--text-tertiary)]"
                weight="bold"
                aria-hidden
              />
            </Link>
          </li>
        ))}
      </ul>
    </Surface>
  );
}

// ─── Recent activity timeline ────────────────────────────────────

function RecentActivityCard({ rows }: { rows: ClientActivityItem[] }) {
  return (
    <Surface
      title="Actividad reciente"
      actions={
        <Link
          href="/client/activity"
          className="text-[11px] font-medium text-[color:var(--text-link)] hover:underline"
        >
          Ver más
        </Link>
      }
    >
      {rows.length === 0 ? (
        <EmptyState
          title="Sin actividad reciente"
          description="Aún no hay eventos registrados para este cliente."
        />
      ) : (
        <ol className="space-y-3">
          {rows.slice(0, 6).map((row) => (
            <li key={row.id} className="flex items-start gap-3">
              <span
                aria-hidden="true"
                className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-[color:var(--text-teal)]"
              />
              <div className="min-w-0 flex-1">
                <p className="truncate text-[12px] text-[color:var(--text-primary)]">
                  {row.summary}
                </p>
                <p className="mt-0.5 truncate font-mono text-[10px] text-[color:var(--text-tertiary)]">
                  {row.vendor_id && row.vendor_name ? (
                    <VendorRef
                      vendorId={row.vendor_id}
                      vendorName={row.vendor_name}
                      muted
                    />
                  ) : (
                    row.vendor_name ?? "—"
                  )}{" "}
                  · {row.action} · {timeAgo(row.occurred_at)}
                </p>
              </div>
            </li>
          ))}
        </ol>
      )}
    </Surface>
  );
}

// ─── Helpers ──────────────────────────────────────────────────────

function timeAgo(iso: string): string {
  try {
    const now = Date.now();
    const then = new Date(iso).getTime();
    const diff = Math.max(0, Math.round((now - then) / 1000));
    if (diff < 60) return "hace segs";
    const mins = Math.floor(diff / 60);
    if (mins < 60) return `${mins} min`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h`;
    const days = Math.floor(hours / 24);
    if (days < 30) return `${days}d`;
    return new Date(iso).toLocaleDateString("es-MX", {
      day: "2-digit",
      month: "short",
    });
  } catch {
    return iso;
  }
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
      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <div className="h-56 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]" />
          <div className="h-56 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]" />
        </div>
        <div className="space-y-5">
          <div className="h-40 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]" />
          <div className="h-40 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]" />
        </div>
      </div>
    </div>
  );
}
