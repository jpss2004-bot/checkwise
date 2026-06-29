"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Bell,
  Buildings,
  CalendarBlank,
  CheckCircle,
  FileText,
  Files,
  HourglassHigh,
  IdentificationCard,
  Sparkle,
  Warning,
  WarningOctagon,
} from "@phosphor-icons/react";

import {
  EmptyState,
  Surface,
} from "@/components/checkwise/dashboard/stat-card";
import { ErrorState } from "@/components/checkwise/portal/state-surfaces";
import { Button } from "@/components/ui/button";

import { ClientShell } from "../_shell";
import { VendorRef } from "@/components/checkwise/vendor-ref";
import {
  getClientMe,
  getClientOverview,
  getClientOverviewTrajectory,
  getClientProfile,
  listClientNotifications,
  type ClientExposure,
  type ClientMe,
  type ClientNotificationItem,
  type ClientOverview,
  type ClientProfile,
  type ClientRiskVendor,
  type ClientTrajectory,
} from "@/lib/api/client";
import { bucketLabel } from "@/lib/constants/statuses";
import { useUrlClientId } from "@/lib/workspace/use-url-client-id";

/**
 * Client dashboard — decision-grade redesign (2026-06-19).
 *
 * Leads with ONE canonical, reconciled compliance number ("X de Y al día,
 * de las ya vencidas"), a period-anchored coverage trajectory against the
 * 85% target, and the single biggest legal/tax exposure right now. Below:
 * date-correct risk tiles (Vencidos / Por vencer / Próximas / Rechazos / En
 * revisión), a named worklist with momentum, and a de-cluttered novedades
 * rail. A whisper-quiet AI advisory line appears only when there's something
 * (and never overrides the human verdict).
 */
export default function ClientDashboardPage() {
  const urlClientId = useUrlClientId();
  const [me, setMe] = useState<ClientMe | null>(null);
  const [overview, setOverview] = useState<ClientOverview | null>(null);
  const [trajectory, setTrajectory] = useState<ClientTrajectory | null>(null);
  const [notifications, setNotifications] = useState<ClientNotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [clientId, setClientId] = useState<string | null>(urlClientId);
  const [error, setError] = useState<string | null>(null);
  const [profile, setProfile] = useState<ClientProfile | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    getClientProfile(urlClientId ? { client_id: urlClientId } : undefined)
      .then((p) => {
        if (!cancelled) setProfile(p);
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
      listClientNotifications({ ...(params ?? {}), limit: 6 }),
    ])
      .then(([ov, notes]) => {
        if (cancelled) return;
        setOverview(ov);
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
  }, [clientId, me, reloadKey]);

  // Trajectory is lazy + independent: a slow or empty history never blocks or
  // breaks the headline. Failures just hide the sparkline.
  useEffect(() => {
    if (!me && !clientId) return;
    let cancelled = false;
    const params = clientId ? { client_id: clientId } : undefined;
    getClientOverviewTrajectory(params)
      .then((t) => {
        if (!cancelled) setTrajectory(t);
      })
      .catch(() => {
        if (!cancelled) setTrajectory(null);
      });
    return () => {
      cancelled = true;
    };
  }, [clientId, me, reloadKey]);

  return (
    <ClientShell
      title="Resumen del cliente"
      description="Cumplimiento de tus proveedores REPSE — tu mayor riesgo, tendencia y faltantes en una sola vista."
      actions={
        me && me.visible_client_ids.length > 1 ? (
          <ClientSwitcher
            value={clientId ?? ""}
            options={
              me.visible_clients && me.visible_clients.length > 0
                ? me.visible_clients
                : me.visible_client_ids.map((id) => ({ id, name: id }))
            }
            onChange={setClientId}
          />
        ) : overview ? (
          // Single-tenant users never see the switcher, so the client org
          // name was otherwise unlabeled on a page full of *provider* names.
          // A labeled "Cliente" chip makes "this is YOUR organization"
          // unambiguous (2nd-review note 1.4).
          <ClientBadge name={overview.client_name} />
        ) : null
      }
    >
      {error ? (
        <ErrorState
          tone="error"
          title="No pudimos cargar tu resumen"
          description={error}
          onRetry={() => setReloadKey((k) => k + 1)}
        />
      ) : !overview ? (
        <DashboardSkeleton />
      ) : (
        <div className="space-y-6">
          {profile && profile.onboarding_completed_at === null ? (
            <OnboardingPromptBanner clientName={profile.name} />
          ) : null}
          <div className="cw-fade-up grid gap-5 lg:grid-cols-[1.05fr,1fr]">
            <DecisionHero overview={overview} trajectory={trajectory} />
            <BiggestExposureCard
              exposure={overview.biggest_exposure}
              overview={overview}
            />
          </div>
          <InsightLine overview={overview} />
          <SignalsStrip overview={overview} />
          <div className="cw-stagger grid gap-5 lg:grid-cols-3">
            <div className="space-y-5 lg:col-span-2">
              <RiskWorklistCard
                vendors={overview.top_risk_vendors}
                pattern={overview.top_failure_pattern}
              />
            </div>
            <div className="space-y-5">
              <NovedadesCard rows={notifications} unreadCount={unreadCount} />
              <ActionsCard />
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
  options: { id: string; name: string }[];
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
        {options.map((opt) => (
          <option key={opt.id} value={opt.id}>
            {opt.name}
          </option>
        ))}
      </select>
    </label>
  );
}

// Read-only counterpart to ClientSwitcher for single-tenant users: same
// chrome, but it states the client organization instead of switching it.
function ClientBadge({ name }: { name: string }) {
  return (
    <span className="flex items-center gap-2 rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-3 py-1.5 text-xs text-[color:var(--text-secondary)]">
      <Buildings className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
      <span className="font-mono text-[10px] uppercase tracking-wide">Cliente</span>
      <span className="font-medium text-[color:var(--text-primary)]">{name}</span>
    </span>
  );
}

// ─── Hero: canonical number + distribution + trajectory ──────────

function heroDrillHref(o: ClientOverview): string | null {
  if (o.red_count > 0) return "/client/vendors?level=red";
  if (o.yellow_count > 0) return "/client/vendors?level=yellow";
  return null;
}

function gapToTarget(o: ClientOverview, target: number): number {
  if (o.obligations_due_total === 0) return 0;
  const needed = Math.ceil((target / 100) * o.obligations_due_total);
  return Math.max(0, needed - o.obligations_on_track_total);
}

function DecisionHero({
  overview,
  trajectory,
}: {
  overview: ClientOverview;
  trajectory: ClientTrajectory | null;
}) {
  const tone =
    overview.compliance_pct >= 85
      ? "var(--status-success-text)"
      : overview.compliance_pct >= 60
        ? "var(--status-warning-text)"
        : "var(--status-error-text)";
  const target = trajectory?.target_pct ?? 85;
  const gap = gapToTarget(overview, target);
  const drillHref = heroDrillHref(overview);

  return (
    <section className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-5 shadow-xs md:p-6">
      <p className="cw-eyebrow">
        Obligaciones al día{" "}
        <span className="normal-case tracking-normal text-[color:var(--text-tertiary)]">
          (de las ya vencidas)
        </span>
      </p>
      <div className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span
          className="font-mono text-[40px] font-semibold leading-none tabular-nums"
          style={{ color: tone }}
        >
          {Math.round(overview.compliance_pct)}
          <span className="text-2xl">%</span>
        </span>
        <span className="text-[13px] text-[color:var(--text-secondary)]">
          {overview.obligations_on_track_total} de {overview.obligations_due_total}
        </span>
        <ComplianceTrendChip delta={overview.compliance_trend_delta} />
      </div>

      {/* Names what the number measures and over whom — the reviewer
          couldn't tell the scope from "Obligaciones al día" alone
          (2nd-review note 1.3). */}
      <p className="mt-1.5 text-[11px] leading-4 text-[color:var(--text-tertiary)]">
        De las obligaciones de tus {overview.vendors_total} proveedores con
        fecha límite ya vencida este año.
      </p>

      <DistributionBar overview={overview} />

      {trajectory && trajectory.has_history && trajectory.points.length > 1 ? (
        <TrajectorySparkline trajectory={trajectory} />
      ) : null}

      <p className="mt-3 text-[12px] text-[color:var(--text-secondary)]">
        {gap > 0 ? (
          <>
            Te {gap === 1 ? "falta" : "faltan"}{" "}
            <span className="font-semibold text-[color:var(--text-primary)]">
              {gap} obligación{gap === 1 ? "" : "es"}
            </span>{" "}
            para la meta del {target}%
            {drillHref ? (
              <>
                {" · "}
                <Link
                  href={drillHref}
                  className="font-medium text-[color:var(--text-link)] hover:underline"
                >
                  ver proveedores en riesgo
                </Link>
              </>
            ) : null}
          </>
        ) : (
          <>Estás en la meta del {target}% · {overview.client_name}</>
        )}
      </p>
    </section>
  );
}

// Month-over-month approval-rate momentum (clearly labelled — not the
// cumplimiento %). Up = improving (teal), down = error, flat/none = muted.
function ComplianceTrendChip({ delta }: { delta: number | null }) {
  if (delta === null) {
    return (
      <span className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
        Sin tendencia aún
      </span>
    );
  }
  const up = delta > 0;
  const flat = delta === 0;
  const cls = flat
    ? "text-[color:var(--text-tertiary)]"
    : up
      ? "text-[color:var(--status-success-text)]"
      : "text-[color:var(--status-error-text)]";
  const sign = up ? "▲" : flat ? "→" : "▼";
  return (
    <span
      className={`inline-flex items-center gap-1 font-mono text-[11px] font-semibold tabular-nums ${cls}`}
      title="Cambio en la tasa de aprobación respecto al mes anterior"
    >
      {sign} {Math.abs(delta)} pts
      <span className="font-normal text-[color:var(--text-tertiary)]">
        aprobación vs mes anterior
      </span>
    </span>
  );
}

// Thin three-segment distribution — al día / en proceso / en riesgo. Replaces
// the old redundant donut with something that costs no vertical space.
function DistributionBar({ overview }: { overview: ClientOverview }) {
  const total =
    overview.green_count + overview.yellow_count + overview.red_count;
  if (total === 0) return null;
  const seg = [
    { v: overview.green_count, c: "var(--status-success-text)", label: "al día" },
    { v: overview.yellow_count, c: "var(--status-warning-text)", label: "en proceso" },
    { v: overview.red_count, c: "var(--status-error-text)", label: "en riesgo" },
  ];
  return (
    <div className="mt-3">
      <div className="flex h-2 overflow-hidden rounded-full bg-[color:var(--surface-sunken)]">
        {seg.map((s) =>
          s.v > 0 ? (
            <div
              key={s.label}
              style={{ width: `${(s.v / total) * 100}%`, backgroundColor: s.c }}
              aria-hidden="true"
            />
          ) : null,
        )}
      </div>
      <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-0.5 text-[11px] text-[color:var(--text-secondary)]">
        {seg.map((s) => (
          <span key={s.label} className="inline-flex items-center gap-1.5">
            <span
              className="h-2 w-2 rounded-full"
              style={{ backgroundColor: s.c }}
              aria-hidden="true"
            />
            <span className="font-mono font-semibold tabular-nums text-[color:var(--text-primary)]">
              {s.v}
            </span>
            {s.label}
          </span>
        ))}
      </div>
    </div>
  );
}

// Period-anchored coverage line + fixed 85% reference. Honest history, never a
// forecast curve. Inline SVG so it costs no chart bundle.
function TrajectorySparkline({ trajectory }: { trajectory: ClientTrajectory }) {
  const pts = trajectory.points;
  const W = 320;
  const H = 64;
  const pad = 8;
  const values = pts.map((p) => p.compliance_pct);
  const lo = Math.max(0, Math.min(...values, trajectory.target_pct) - 6);
  const hi = 100;
  const x = (i: number) =>
    pts.length === 1 ? W / 2 : pad + (i * (W - 2 * pad)) / (pts.length - 1);
  const y = (v: number) => H - pad - ((v - lo) / (hi - lo)) * (H - 2 * pad);
  const line = pts
    .map((p, i) => `${x(i).toFixed(1)},${y(p.compliance_pct).toFixed(1)}`)
    .join(" ");
  const targetY = y(trajectory.target_pct);
  const last = pts[pts.length - 1];
  return (
    <div className="mt-3">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="h-16 w-full"
        role="img"
        aria-label={`Cobertura de obligaciones por período: de ${pts[0].compliance_pct}% a ${last.compliance_pct}%, meta ${trajectory.target_pct}%`}
      >
        <line
          x1={pad}
          y1={targetY}
          x2={W - pad}
          y2={targetY}
          stroke="var(--text-tertiary)"
          strokeWidth={1}
          strokeDasharray="3 3"
          opacity={0.6}
        />
        <polyline
          points={line}
          fill="none"
          stroke="var(--text-teal)"
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        <circle
          cx={x(pts.length - 1)}
          cy={y(last.compliance_pct)}
          r={3.5}
          fill="var(--text-teal)"
        />
      </svg>
      <div className="flex justify-between font-mono text-[10px] text-[color:var(--text-tertiary)]">
        <span>{pts[0].label}</span>
        <span>cobertura por período · meta {trajectory.target_pct}%</span>
        <span>{last.label}</span>
      </div>
    </div>
  );
}

// ─── Biggest exposure ────────────────────────────────────────────

function BiggestExposureCard({
  exposure,
  overview,
}: {
  exposure: ClientExposure | null;
  overview: ClientOverview;
}) {
  if (!exposure) {
    return (
      <section className="flex flex-col justify-center rounded-lg border border-[color:var(--status-success-border)] bg-[color:var(--status-success-bg)] p-5 md:p-6">
        <p className="cw-eyebrow text-[color:var(--status-success-text)]">
          Sin exposición crítica
        </p>
        <div className="mt-2 flex items-start gap-3">
          <CheckCircle
            className="mt-0.5 h-6 w-6 shrink-0 text-[color:var(--status-success-text)]"
            weight="fill"
            aria-hidden="true"
          />
          <p className="text-[13px] leading-relaxed text-[color:var(--text-secondary)]">
            Ningún proveedor tiene obligaciones vencidas ni rechazos pendientes
            ahora. Te avisaremos en cuanto algo necesite tu atención.
          </p>
        </div>
        {overview.due_soon_total > 0 ? (
          <p className="mt-3 text-[11px] text-[color:var(--text-tertiary)]">
            {overview.due_soon_total} obligación
            {overview.due_soon_total === 1 ? "" : "es"} por vencer en los
            próximos 14 días.
          </p>
        ) : null}
      </section>
    );
  }
  return (
    <Link
      href={exposure.href}
      className="group flex flex-col rounded-lg border border-[color:var(--status-error-border)] bg-[color:var(--status-error-bg)] p-5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)] focus-visible:ring-offset-2 md:p-6"
    >
      <p className="cw-eyebrow inline-flex items-center gap-1.5 text-[color:var(--status-error-text)]">
        <WarningOctagon className="h-3.5 w-3.5" weight="fill" aria-hidden="true" />
        Tu mayor exposición ahora
      </p>
      <p className="mt-2 truncate text-[15px] font-semibold text-[color:var(--text-primary)]">
        {exposure.vendor_name}
      </p>
      <p className="mt-0.5 text-[13px] text-[color:var(--status-error-text)]">
        {exposure.headline}
      </p>
      <p className="mt-2 text-[11px] leading-relaxed text-[color:var(--status-error-text)]">
        {exposure.reason}
        {exposure.detail ? (
          <span className="text-[color:var(--text-secondary)]"> · {exposure.detail}</span>
        ) : null}
      </p>
      <span className="mt-auto inline-flex items-center gap-1 pt-4 text-[12px] font-semibold text-[color:var(--status-error-text)]">
        Ver proveedor
        <ArrowRight
          className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5"
          weight="bold"
          aria-hidden="true"
        />
      </span>
    </Link>
  );
}

// ─── Insight line (AI advisory + root-cause pattern) ─────────────

function InsightLine({ overview }: { overview: ClientOverview }) {
  const showAi = overview.ia_revisar_total > 0;
  const pattern = overview.top_failure_pattern;
  if (!showAi && !pattern) return null;
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2 px-1">
      {showAi ? (
        <span className="inline-flex items-center gap-2 text-[12px] text-[color:var(--status-warning-text)]">
          <Sparkle className="h-4 w-4 shrink-0" weight="fill" aria-hidden="true" />
          <span>
            La IA marcó {overview.ia_revisar_total} documento
            {overview.ia_revisar_total === 1 ? "" : "s"} en revisión para tu
            atención
          </span>
          <span className="text-[11px] text-[color:var(--text-tertiary)]">
            — sugerencia, la revisión humana decide
          </span>
        </span>
      ) : null}
      {pattern ? (
        <span className="inline-flex items-center gap-2 text-[12px] text-[color:var(--text-secondary)]">
          <Warning
            className="h-4 w-4 shrink-0 text-[color:var(--status-warning-text)]"
            weight="fill"
            aria-hidden="true"
          />
          <span>
            Patrón recurrente:{" "}
            <span className="font-semibold text-[color:var(--text-primary)]">
              {pattern.requirement_name}
            </span>{" "}
            pendiente en {pattern.vendor_count} proveedores
          </span>
        </span>
      ) : null}
    </div>
  );
}

// ─── Signals strip (date-correct risk tiles) ─────────────────────

function SignalsStrip({ overview }: { overview: ClientOverview }) {
  const tiles: {
    href: string;
    icon: typeof WarningOctagon;
    label: string;
    value: number;
    tone: "error" | "warning" | "muted";
  }[] = [
    {
      href: "/client/calendar",
      icon: WarningOctagon,
      label: "Vencidos",
      value: overview.overdue_total,
      tone: overview.overdue_total > 0 ? "error" : "muted",
    },
    {
      href: "/client/calendar",
      icon: CalendarBlank,
      label: "Por vencer ≤14d",
      value: overview.due_soon_total,
      tone: overview.due_soon_total > 0 ? "warning" : "muted",
    },
    {
      href: "/client/calendar",
      icon: Files,
      label: "Próximas",
      value: overview.proxima_total,
      tone: "muted",
    },
    {
      href: "/client/submissions?status=rechazado",
      icon: Warning,
      label: "Rechazos",
      value: overview.rejected_or_correction_total,
      tone: overview.rejected_or_correction_total > 0 ? "error" : "muted",
    },
    {
      href: "/client/submissions",
      icon: HourglassHigh,
      label: bucketLabel("pending_reviews"),
      value: overview.pending_reviews_total,
      tone: "muted",
    },
  ];
  return (
    <section
      aria-label="Señales del portafolio"
      className="cw-fade-up grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5"
    >
      {tiles.map((t) => {
        const Icon = t.icon;
        const valueTone =
          t.tone === "error"
            ? "text-[color:var(--status-error-text)]"
            : t.tone === "warning"
              ? "text-[color:var(--status-warning-text)]"
              : "text-[color:var(--text-secondary)]";
        return (
          <Link
            key={t.label}
            href={t.href}
            className="group rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-3.5 shadow-xs transition-colors hover:bg-[color:var(--surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]/40"
          >
            <div className="flex items-center justify-between">
              <Icon
                className="h-4 w-4 text-[color:var(--text-tertiary)]"
                weight="bold"
                aria-hidden="true"
              />
              <ArrowRight
                className="h-3.5 w-3.5 text-[color:var(--text-tertiary)] opacity-0 transition-opacity group-hover:opacity-100"
                weight="bold"
                aria-hidden="true"
              />
            </div>
            <p className={`mt-2 font-mono text-2xl font-semibold tabular-nums ${valueTone}`}>
              {t.value}
            </p>
            <p className="text-[11px] text-[color:var(--text-secondary)]">{t.label}</p>
          </Link>
        );
      })}
    </section>
  );
}

// ─── Risk worklist + root-cause pattern ──────────────────────────

const RISK_DOT_TONE: Record<ClientRiskVendor["semaphore_level"], string> = {
  red: "var(--status-error-text)",
  yellow: "var(--status-warning-text)",
  green: "var(--status-success-text)",
};

function MomentumChip({ delta }: { delta: number | null }) {
  if (delta === null || delta === 0) return null;
  const up = delta > 0;
  return (
    <span
      className="font-mono text-[11px] tabular-nums"
      style={{
        color: up ? "var(--status-success-text)" : "var(--status-error-text)",
      }}
      title="Tendencia de aprobación vs mes anterior"
    >
      {up ? "▲" : "▼"} {Math.abs(delta)}
    </span>
  );
}

function RiskWorklistCard({
  vendors,
  pattern,
}: {
  vendors: ClientRiskVendor[];
  pattern: ClientOverview["top_failure_pattern"];
}) {
  if (vendors.length === 0) {
    return (
      <Surface title="Requieren tu atención" icon={CheckCircle}>
        <div className="flex items-center gap-3 py-2 text-[13px] text-[color:var(--text-secondary)]">
          <CheckCircle
            className="h-5 w-5 shrink-0 text-[color:var(--status-success-text)]"
            weight="fill"
            aria-hidden="true"
          />
          Ningún proveedor necesita acción ahora. Te avisaremos cuando algo
          cambie.
        </div>
      </Surface>
    );
  }
  return (
    <Surface
      title="Requieren tu atención"
      icon={WarningOctagon}
      actions={
        <Link
          href="/client/vendors?level=red"
          className="inline-flex items-center gap-1 rounded-sm text-[12px] font-medium text-[color:var(--text-link)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)] focus-visible:ring-offset-2"
        >
          Ver todos
          <ArrowRight className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
        </Link>
      }
      bodyClassName="p-0"
    >
      <ul className="divide-y divide-[color:var(--border-subtle)]">
        {vendors.map((v) => (
          <li key={v.vendor_id}>
            <Link
              href={`/client/vendors/${v.vendor_id}`}
              className="group flex items-center gap-3 px-5 py-3 transition-colors hover:bg-[color:var(--surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[color:var(--border-focus)]/50"
            >
              <span
                className="h-2.5 w-2.5 shrink-0 rounded-full"
                style={{ backgroundColor: RISK_DOT_TONE[v.semaphore_level] }}
                aria-hidden="true"
              />
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13px] font-semibold text-[color:var(--text-primary)] group-hover:underline">
                  {v.vendor_name}
                </p>
                <p
                  className="truncate text-[12px]"
                  style={{ color: RISK_DOT_TONE[v.semaphore_level] }}
                >
                  {v.top_reason}
                </p>
              </div>
              <MomentumChip delta={v.momentum_delta} />
              <span className="font-mono text-[13px] font-semibold tabular-nums text-[color:var(--text-secondary)]">
                {v.compliance_pct}%
              </span>
              <ArrowRight
                className="h-4 w-4 shrink-0 text-[color:var(--text-tertiary)] transition-transform group-hover:translate-x-0.5 group-hover:text-[color:var(--text-primary)]"
                weight="bold"
                aria-hidden="true"
              />
            </Link>
          </li>
        ))}
      </ul>
      {pattern ? (
        <div className="flex items-start gap-2 border-t border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] px-5 py-2.5 text-[12px] text-[color:var(--text-secondary)]">
          <Warning
            className="mt-0.5 h-4 w-4 shrink-0 text-[color:var(--status-warning-text)]"
            weight="fill"
            aria-hidden="true"
          />
          <span>
            Tu falla #1:{" "}
            <span className="font-semibold text-[color:var(--text-primary)]">
              {pattern.requirement_name}
            </span>{" "}
            ({pattern.institution}) — pendiente en {pattern.vendor_count}{" "}
            proveedores. Atácala una vez en lugar de proveedor por proveedor.
          </span>
        </div>
      ) : null}
    </Surface>
  );
}

// ─── Novedades (single de-cluttered feed) ────────────────────────

function NovedadesCard({
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
          description="Cuando un proveedor suba documentos o haya avances, aparecerán aquí."
        />
      ) : (
        <ul className="space-y-3">
          {rows.slice(0, 6).map((row) => (
            <li key={row.id} className="flex items-start gap-3">
              <span
                aria-hidden="true"
                className={
                  "mt-1.5 h-2 w-2 shrink-0 rounded-full " +
                  (row.read_at
                    ? "bg-[color:var(--border-subtle)]"
                    : "bg-[color:var(--text-teal)]")
                }
              />
              <div className="min-w-0 flex-1">
                {/* Honor the notification's deep-link here too, so the card
                    behaves like the inbox instead of being inert
                    (2nd-review note 5.x). */}
                {row.action_url ? (
                  <Link
                    href={row.action_url}
                    className="block truncate text-[12px] font-medium text-[color:var(--text-primary)] hover:text-[color:var(--text-link)] hover:underline"
                  >
                    {row.title}
                  </Link>
                ) : (
                  <p className="truncate text-[12px] font-medium text-[color:var(--text-primary)]">
                    {row.title}
                  </p>
                )}
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

// ─── Action outcomes (not nav duplicates) ────────────────────────

function ActionsCard() {
  const items: {
    href: string;
    label: string;
    helper: string;
    icon: typeof FileText;
  }[] = [
    {
      href: "/client/reports",
      label: "Reporte ejecutivo",
      helper: "Genera un PDF para tu dirección.",
      icon: FileText,
    },
    {
      href: "/client/auditoria",
      label: "Paquete de auditoría",
      helper: "Arma el ZIP con evidencia para un inspector.",
      icon: Files,
    },
    {
      href: "/client/activity",
      label: "Bitácora de actividad",
      helper: "Historial completo del cliente.",
      icon: HourglassHigh,
    },
  ];
  return (
    <Surface title="Acciones" bodyClassName="p-0">
      <ul className="divide-y divide-[color:var(--border-subtle)]">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                className="flex items-center gap-3 px-4 py-2.5 text-[12px] transition-colors hover:bg-[color:var(--surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[color:var(--border-focus)]/40"
              >
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-[color:var(--surface-sunken)] text-[color:var(--text-secondary)]">
                  <Icon className="h-4 w-4" weight="bold" aria-hidden="true" />
                </span>
                <div className="min-w-0 flex-1">
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

// ─── Onboarding banner ───────────────────────────────────────────

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
            Nuestro equipo precargó tus datos básicos. Completa el sector,
            domicilio fiscal y teléfono para activar tu portafolio. No te
            pediremos archivos.
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
      <div className="grid gap-5 lg:grid-cols-[1.05fr,1fr]">
        <div className="h-48 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]" />
        <div className="h-48 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]" />
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {[0, 1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className="h-24 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]"
          />
        ))}
      </div>
      <div className="grid gap-5 lg:grid-cols-3">
        <div className="h-64 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] lg:col-span-2" />
        <div className="h-64 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]" />
      </div>
    </div>
  );
}
