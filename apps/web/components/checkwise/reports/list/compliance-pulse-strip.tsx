"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  ArrowUpRight,
  CalendarBlank,
  CheckCircle,
  CircleNotch,
  CloudArrowUp,
  Info,
  Shield,
  Sparkle,
  Warning,
  WarningOctagon,
  type Icon,
} from "@phosphor-icons/react";

import { RadialGauge } from "@/components/checkwise/charts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";
import {
  getDashboard,
  type DashboardAttentionItem,
  type DashboardPayload,
  type DashboardSemaphoreLevel,
  type DashboardSuggestedAction,
  type DashboardUpcomingDeadline,
} from "@/lib/api/portal";
import {
  ReportsApiError,
  createReportFromPreset,
} from "@/lib/api/reports";
import type { PortalSession } from "@/lib/session/portal";

/**
 * Provider-portal Compliance Pulse strip (P1.6).
 *
 * Sits above the report list on /portal/reports and gives the
 * vendor an at-a-glance compliance read before they ever open a
 * generated report. Data source is the canonical dashboard endpoint
 * (`GET /api/v1/portal/workspaces/{id}/dashboard`) so the semaphore,
 * counts, attention items, deadlines and prioritized actions all
 * resolve through the same `dashboard_compute` logic that the
 * provider report blocks read.
 *
 * The strip is intentionally read-only — every action either deep-
 * links into the canonical upload flow or kicks off the provider
 * "Mi estado de cumplimiento" preset (`provider-current-state`) so
 * the user lands on a freshly-generated report.
 */

const PROVIDER_CURRENT_STATE_PRESET = "provider-current-state";

const INSTITUTION_LABEL: Record<string, string> = {
  sat: "SAT",
  imss: "IMSS",
  infonavit: "INFONAVIT",
  stps_repse: "STPS / REPSE",
  interno_cliente: "Interno / Cliente",
};

const SEMAPHORE_TONE: Record<
  DashboardSemaphoreLevel,
  "success" | "warning" | "error"
> = {
  green: "success",
  yellow: "warning",
  red: "error",
};

const SEMAPHORE_ICON: Record<DashboardSemaphoreLevel, Icon> = {
  green: CheckCircle,
  yellow: Warning,
  red: WarningOctagon,
};

const SEMAPHORE_BORDER: Record<DashboardSemaphoreLevel, string> = {
  green: "border-[color:var(--status-success-border)]",
  yellow: "border-[color:var(--status-warning-border)]",
  red: "border-[color:var(--status-error-border)]",
};

const PRIORITY_BADGE: Record<
  DashboardSuggestedAction["priority"],
  { label: string; variant: "destructive" | "warning" | "outline" }
> = {
  high: { label: "Alta", variant: "destructive" },
  medium: { label: "Media", variant: "warning" },
  low: { label: "Baja", variant: "outline" },
};

interface UrgencyBucket {
  key: "week" | "fortnight" | "month" | "later";
  label: string;
  max_days: number | null;
  count: number;
  tone: string;
}

function bucketDeadlines(rows: DashboardUpcomingDeadline[]): UrgencyBucket[] {
  const buckets: UrgencyBucket[] = [
    {
      key: "week",
      label: "≤ 7 días",
      max_days: 7,
      count: 0,
      tone: "var(--status-error-text)",
    },
    {
      key: "fortnight",
      label: "≤ 14 días",
      max_days: 14,
      count: 0,
      tone: "var(--status-warning-text)",
    },
    {
      key: "month",
      label: "≤ 30 días",
      max_days: 30,
      count: 0,
      tone: "var(--status-info-text)",
    },
    {
      key: "later",
      label: "Más adelante",
      max_days: null,
      count: 0,
      tone: "var(--text-tertiary)",
    },
  ];
  for (const row of rows) {
    const due = row.due_in_days;
    let placed = false;
    if (due === null || due === undefined) {
      buckets[buckets.length - 1].count += 1;
      continue;
    }
    for (const b of buckets) {
      if (b.max_days === null || due <= b.max_days) {
        b.count += 1;
        placed = true;
        break;
      }
    }
    if (!placed) buckets[buckets.length - 1].count += 1;
  }
  return buckets;
}

export interface CompliancePulseStripProps {
  session: PortalSession;
}

export function CompliancePulseStrip({ session }: CompliancePulseStripProps) {
  const router = useRouter();
  const [dashboard, setDashboard] = useState<DashboardPayload | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setDashboard(null);
    setLoadError(null);
    getDashboard(session)
      .then((payload) => {
        if (cancelled) return;
        setDashboard(payload);
      })
      .catch(() => {
        if (cancelled) return;
        setLoadError(
          "No pudimos cargar el pulso de cumplimiento. Vuelve a intentarlo en unos segundos.",
        );
      });
    return () => {
      cancelled = true;
    };
  }, [session]);

  const onGenerate = useCallback(async () => {
    if (generating) return;
    setGenerating(true);
    try {
      // No-customization flow: server generates inline (hybrid AI +
      // deterministic fallback); we land on the finished read-only report.
      const r = await createReportFromPreset(PROVIDER_CURRENT_STATE_PRESET, true);
      router.push(`/portal/reports/${r.id}`);
    } catch (e) {
      setGenerating(false);
      setLoadError(
        e instanceof ReportsApiError
          ? `No pudimos generar el reporte: ${e.message}`
          : "No pudimos generar el reporte.",
      );
    }
  }, [generating, router]);

  if (loadError && !dashboard) {
    return (
      <section
        aria-label="Pulso de cumplimiento"
        className="rounded-lg border border-[color:var(--status-warning-border)] bg-[color:var(--surface-raised)] px-4 py-3 text-[12px] text-[color:var(--text-secondary)]"
      >
        <span className="cw-eyebrow text-[color:var(--status-warning-text)]">
          Pulso de cumplimiento
        </span>
        <p className="mt-1">{loadError}</p>
      </section>
    );
  }

  if (!dashboard) {
    return <PulseSkeleton />;
  }

  return (
    <PulseContent
      dashboard={dashboard}
      onGenerate={onGenerate}
      generating={generating}
    />
  );
}

// ─── Skeleton ────────────────────────────────────────────────────

function PulseSkeleton() {
  return (
    <section
      aria-label="Pulso de cumplimiento"
      aria-busy="true"
      className="space-y-3"
    >
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <div
          className="h-[148px] animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] xl:col-span-2"
        />
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="h-[148px] animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]"
          />
        ))}
      </div>
      <div className="h-16 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]" />
    </section>
  );
}

// ─── Strip body ──────────────────────────────────────────────────

function PulseContent({
  dashboard,
  onGenerate,
  generating,
}: {
  dashboard: DashboardPayload;
  onGenerate: () => void;
  generating: boolean;
}) {
  const {
    semaphore,
    attention_today,
    upcoming_deadlines,
    suggested_actions,
    document_state_counts,
  } = dashboard;
  // P1-b (2026-05-20): excepcion_legal slots are NOT actionable for
  // the provider, but they're also not missing — they're legally
  // closed by LegalShelf. Surface the count so providers don't
  // misread them as gaps in their expediente.
  const exceptionCount = document_state_counts?.exception ?? 0;

  const blockingCount = useMemo(
    () =>
      attention_today.filter(
        (a) =>
          a.state === "rejected" ||
          a.state === "needs_correction" ||
          a.state === "possible_mismatch",
      ).length,
    [attention_today],
  );

  const urgency = useMemo(
    () => bucketDeadlines(upcoming_deadlines),
    [upcoming_deadlines],
  );
  const urgencyTotal = urgency.reduce((s, b) => s + b.count, 0);
  const topActions = suggested_actions.slice(0, 3);

  return (
    <section
      aria-label="Pulso de cumplimiento"
      className="cw-fade-up space-y-3"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[14px] font-semibold tracking-tight text-[color:var(--text-primary)]">
          Pulso de cumplimiento
        </h2>
        <span className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
          Actualizado {new Date().toLocaleString("es-MX", {
            dateStyle: "medium",
            timeStyle: "short",
          })}
        </span>
      </header>

      {/* F7 (2026-05-19 visual audit): break the 4-up equal grid that
          gave every card identical weight. SemaphoreCard owns the
          headline metric (cumplimiento %), so it takes 2 columns at
          xl+ while the three secondaries share the remaining 3. The
          eye anchors on the score first; everything else trails. */}
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <div className="xl:col-span-2">
          <SemaphoreCard
            level={semaphore.level}
            compliancePct={semaphore.compliance_pct}
            onTrack={semaphore.on_track}
            totalTracked={semaphore.total_tracked}
            label={semaphore.label}
            exceptionCount={exceptionCount}
          />
        </div>
        <AttentionCard
          totalAttention={attention_today.length}
          blockingCount={blockingCount}
          items={attention_today}
        />
        <DeadlinesCard
          totalUpcoming={urgencyTotal}
          buckets={urgency}
          rows={upcoming_deadlines}
        />
        <ActionsCard actions={topActions} totalActions={suggested_actions.length} />
      </div>

      <CtaPanel
        onGenerate={onGenerate}
        generating={generating}
        topActionHref={topActions[0]?.href ?? null}
      />
    </section>
  );
}

// ─── Card 1: Semaphore ───────────────────────────────────────────

function SemaphoreCard({
  level,
  compliancePct,
  onTrack,
  totalTracked,
  label,
  exceptionCount,
}: {
  level: DashboardSemaphoreLevel;
  compliancePct: number;
  onTrack: number;
  totalTracked: number;
  label: string;
  exceptionCount: number;
}) {
  const tone = SEMAPHORE_TONE[level];
  const IconComponent = SEMAPHORE_ICON[level];
  const isEmpty = totalTracked === 0;
  return (
    <article
      className={`flex h-full flex-col gap-3 rounded-lg border bg-[color:var(--surface-raised)] p-4 shadow-[var(--shadow-sm)] ${SEMAPHORE_BORDER[level]}`}
      aria-label="Estado general de cumplimiento"
    >
      <header className="flex items-center justify-between gap-2">
        <span className="cw-eyebrow inline-flex items-center gap-1">
          Estado general
          {/* P1-a (2026-05-20): the "X de N obligaciones" denominator
              reads against the full annual REPSE calendar, while the
              per-report KPI block counts only the report period.
              Tooltip explains the difference so providers don't read
              the two numbers as conflicting. */}
          <Tooltip
            side="top"
            content={
              <span className="block max-w-[260px] text-[11px] leading-snug">
                <strong className="block font-semibold">
                  ¿Cómo se calcula?
                </strong>
                Cumplimiento = obligaciones requeridas aprobadas ÷ total
                de obligaciones del calendario REPSE del año en curso.
                Incluye periodos futuros, por eso el porcentaje sube
                gradualmente a lo largo del año. Los KPIs dentro de un
                reporte cuentan solo el periodo del reporte.
              </span>
            }
          >
            <button
              type="button"
              aria-label="¿Cómo se calcula el cumplimiento?"
              className="inline-flex h-4 w-4 items-center justify-center rounded-full text-[color:var(--text-tertiary)] hover:text-[color:var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]"
            >
              <Info className="h-3.5 w-3.5" weight="regular" aria-hidden="true" />
            </button>
          </Tooltip>
        </span>
        <Badge
          variant={
            tone === "success"
              ? "success"
              : tone === "warning"
                ? "warning"
                : "destructive"
          }
          className="inline-flex items-center gap-1"
        >
          <IconComponent className="h-3 w-3" weight="fill" aria-hidden="true" />
          {isEmpty ? "Sin datos" : label.split(" · ")[0]}
        </Badge>
      </header>
      <div className="flex items-center gap-3">
        <RadialGauge
          value={compliancePct}
          tone={tone}
          size={92}
          thickness={9}
          label={`${compliancePct}%`}
          caption="cumplimiento"
        />
        <div className="min-w-0 flex-1 space-y-1.5">
          <p className="text-[12px] leading-snug text-[color:var(--text-secondary)]">
            {isEmpty
              ? "Todavía no hay obligaciones suficientes para calcular el pulso."
              : `${onTrack} de ${totalTracked} obligaciones al día`}
          </p>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-[color:var(--surface-sunken)]">
            <div
              className="h-full rounded-full transition-[width] duration-700"
              style={{
                width: `${compliancePct}%`,
                backgroundColor:
                  tone === "success"
                    ? "var(--status-success-text)"
                    : tone === "warning"
                      ? "var(--status-warning-text)"
                      : "var(--status-error-text)",
              }}
              aria-hidden="true"
            />
          </div>
          {exceptionCount > 0 ? (
            <Tooltip
              side="bottom"
              content={
                <span className="block max-w-[240px] text-[11px] leading-snug">
                  Documentos marcados como excepción legal por
                  LegalShelf (criterio normativo, no requeridos para
                  el periodo). No cuentan como pendientes ni como
                  faltantes.
                </span>
              }
            >
              <button
                type="button"
                aria-label={`${exceptionCount} documentos marcados como excepción legal`}
                className="inline-flex items-center gap-1 self-start rounded-full border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-secondary)] hover:border-[color:var(--border-default)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]"
              >
                <Shield className="h-3 w-3" weight="bold" aria-hidden="true" />
                <span className="font-semibold text-[color:var(--text-primary)]">
                  {exceptionCount}
                </span>
                <span className="normal-case tracking-normal">
                  excepción legal
                </span>
              </button>
            </Tooltip>
          ) : null}
        </div>
      </div>
    </article>
  );
}

// ─── Card 2: Attention required ──────────────────────────────────

function AttentionCard({
  totalAttention,
  blockingCount,
  items,
}: {
  totalAttention: number;
  blockingCount: number;
  items: DashboardAttentionItem[];
}) {
  const isEmpty = totalAttention === 0;
  const tone = blockingCount > 0 ? "error" : isEmpty ? "success" : "warning";

  // F7 follow-on: align the skeleton with the new 5-col + col-span-2
  // layout so the initial paint doesn't reflow.
  // Bucket the top items by institution for a compact chip row.
  const institutions = useMemo(() => {
    const seen = new Map<string, number>();
    for (const i of items) {
      const key = i.institution || "—";
      seen.set(key, (seen.get(key) ?? 0) + 1);
    }
    return [...seen.entries()].sort((a, b) => b[1] - a[1]).slice(0, 4);
  }, [items]);

  return (
    <article
      className={`flex h-full flex-col gap-3 rounded-lg border bg-[color:var(--surface-raised)] p-4 shadow-[var(--shadow-sm)] ${
        tone === "error"
          ? "border-[color:var(--status-error-border)]"
          : tone === "warning"
            ? "border-[color:var(--status-warning-border)]"
            : "border-[color:var(--border-default)]"
      }`}
      aria-label="Documentos que requieren atención"
    >
      <header className="flex items-center justify-between gap-2">
        <span className="cw-eyebrow">Atención requerida</span>
        <Badge
          variant={
            tone === "error"
              ? "destructive"
              : tone === "warning"
                ? "warning"
                : "success"
          }
        >
          {isEmpty ? "Sin pendientes" : `${totalAttention} ítems`}
        </Badge>
      </header>
      <div className="flex items-baseline gap-2">
        <span className="font-mono text-3xl font-semibold tabular-nums text-[color:var(--text-primary)]">
          {totalAttention}
        </span>
        <span className="text-[12px] text-[color:var(--text-secondary)]">
          documento{totalAttention === 1 ? "" : "s"} por atender
        </span>
      </div>
      {blockingCount > 0 ? (
        <p className="text-[12px] text-[color:var(--status-error-text)]">
          <strong className="font-semibold">{blockingCount}</strong> con rechazo
          u observación
        </p>
      ) : isEmpty ? (
        <p className="text-[12px] text-[color:var(--text-tertiary)]">
          No hay documentos urgentes por atender.
        </p>
      ) : (
        <p className="text-[12px] text-[color:var(--text-tertiary)]">
          Subidos o en revisión — sin rechazos por ahora.
        </p>
      )}
      {institutions.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {institutions.map(([inst, count]) => (
            <span
              key={inst}
              className="inline-flex items-center gap-1 rounded-full border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-secondary)]"
            >
              {INSTITUTION_LABEL[inst] ?? inst.toUpperCase()}
              <span className="font-semibold text-[color:var(--text-primary)]">
                {count}
              </span>
            </span>
          ))}
        </div>
      ) : null}
      <Link
        href="/portal/dashboard"
        className="mt-auto inline-flex items-center gap-1 text-[12px] font-medium text-[color:var(--text-brand)] hover:underline"
      >
        Ver detalle
        <ArrowUpRight className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
      </Link>
    </article>
  );
}

// ─── Card 3: Upcoming deadlines ──────────────────────────────────

function DeadlinesCard({
  totalUpcoming,
  buckets,
  rows,
}: {
  totalUpcoming: number;
  buckets: UrgencyBucket[];
  rows: DashboardUpcomingDeadline[];
}) {
  const isEmpty = totalUpcoming === 0;
  const nextDeadline = rows[0] ?? null;
  const total = Math.max(totalUpcoming, 1);

  return (
    <article
      className="flex h-full flex-col gap-3 rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-4 shadow-[var(--shadow-sm)]"
      aria-label="Próximos vencimientos"
    >
      <header className="flex items-center justify-between gap-2">
        <span className="cw-eyebrow">Próximos vencimientos</span>
        <Badge variant="outline" className="inline-flex items-center gap-1">
          <CalendarBlank className="h-3 w-3" weight="bold" aria-hidden="true" />
          {isEmpty ? "Ninguno" : `${totalUpcoming}`}
        </Badge>
      </header>
      {isEmpty ? (
        <p className="text-[12px] text-[color:var(--text-tertiary)]">
          Sin vencimientos próximos en los próximos 30 días.
        </p>
      ) : (
        <>
          <div
            className="flex h-2.5 w-full overflow-hidden rounded-full bg-[color:var(--surface-sunken)]"
            role="img"
            aria-label="Barra de urgencia"
          >
            {buckets.map((b) =>
              b.count > 0 ? (
                <div
                  key={b.key}
                  style={{
                    width: `${(b.count / total) * 100}%`,
                    backgroundColor: b.tone,
                  }}
                  title={`${b.label}: ${b.count}`}
                />
              ) : null,
            )}
          </div>
          <ul className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
            {buckets.map((b) => (
              <li
                key={b.key}
                className="flex items-center justify-between gap-1"
              >
                <span className="flex items-center gap-1.5 text-[color:var(--text-tertiary)]">
                  <span
                    className="h-1.5 w-1.5 rounded-full"
                    style={{ backgroundColor: b.tone }}
                    aria-hidden="true"
                  />
                  {b.label}
                </span>
                <span className="font-mono font-semibold tabular-nums text-[color:var(--text-primary)]">
                  {b.count}
                </span>
              </li>
            ))}
          </ul>
          {nextDeadline ? (
            <Link
              href={nextDeadline.href}
              className="mt-auto block rounded-sm border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] p-2 hover:bg-[color:var(--surface-hover)]"
            >
              <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                Próximo ·{" "}
                {INSTITUTION_LABEL[nextDeadline.institution] ??
                  nextDeadline.institution}
              </p>
              <p className="mt-0.5 truncate text-[12px] font-medium text-[color:var(--text-primary)]">
                {nextDeadline.title}
              </p>
              {typeof nextDeadline.due_in_days === "number" ? (
                <p className="mt-0.5 text-[11px] text-[color:var(--text-secondary)]">
                  {nextDeadline.due_in_days === 0
                    ? "Vence hoy"
                    : nextDeadline.due_in_days === 1
                      ? "Vence en 1 día"
                      : `Vence en ${nextDeadline.due_in_days} días`}
                </p>
              ) : null}
            </Link>
          ) : null}
        </>
      )}
    </article>
  );
}

// ─── Card 4: Prioritized actions ─────────────────────────────────

function ActionsCard({
  actions,
  totalActions,
}: {
  actions: DashboardSuggestedAction[];
  totalActions: number;
}) {
  // ``actions`` is the sliced-to-3 list rendered in the card; the
  // header badge needs the unsliced count so a workspace with 4+
  // actions doesn't read as "3" while the sibling Atención card
  // shows the full total. Audit (2026-05-20) caught this when the
  // P1-c regularize action surfaced as a 4th item that disappeared
  // from the strip badge.
  const isEmpty = totalActions === 0;
  const overflow = Math.max(0, totalActions - actions.length);
  return (
    <article
      className="flex h-full flex-col gap-3 rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-4 shadow-[var(--shadow-sm)]"
      aria-label="Acciones prioritarias"
    >
      <header className="flex items-center justify-between gap-2">
        <span className="cw-eyebrow">Acciones prioritarias</span>
        <Badge variant="outline">{totalActions}</Badge>
      </header>
      {isEmpty ? (
        <p className="text-[12px] text-[color:var(--text-tertiary)]">
          No hay acciones urgentes para tu workspace en este momento.
        </p>
      ) : (
        <ul className="space-y-2">
          {actions.map((a) => {
            const badge = PRIORITY_BADGE[a.priority];
            return (
              <li key={a.id}>
                <Link
                  href={a.href}
                  className="group flex items-start gap-2 rounded-sm border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] p-2 hover:border-[color:var(--border-focus)] hover:bg-[color:var(--surface-hover)]"
                >
                  <div className="min-w-0 flex-1 space-y-0.5">
                    <p className="line-clamp-2 text-[12px] font-medium leading-snug text-[color:var(--text-primary)]">
                      {a.title}
                    </p>
                    <div className="flex items-center gap-1.5">
                      <Badge variant={badge.variant} className="text-[10px]">
                        {badge.label}
                      </Badge>
                      {a.requirement_code ? (
                        <span className="truncate font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                          {a.requirement_code}
                        </span>
                      ) : null}
                    </div>
                  </div>
                  <ArrowRight
                    className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[color:var(--text-tertiary)] transition group-hover:translate-x-0.5 group-hover:text-[color:var(--text-primary)]"
                    weight="bold"
                    aria-hidden="true"
                  />
                </Link>
              </li>
            );
          })}
        </ul>
      )}
      {overflow > 0 ? (
        <Link
          href="/portal/dashboard#acciones"
          className="mt-auto inline-flex items-center gap-1 text-[11px] font-medium text-[color:var(--text-brand)] hover:underline"
        >
          Ver {overflow} acción{overflow === 1 ? "" : "es"} más
          <ArrowUpRight className="h-3 w-3" weight="bold" aria-hidden="true" />
        </Link>
      ) : null}
    </article>
  );
}

// ─── CTA panel ───────────────────────────────────────────────────

function CtaPanel({
  onGenerate,
  generating,
  topActionHref,
}: {
  onGenerate: () => void;
  generating: boolean;
  topActionHref: string | null;
}) {
  return (
    <div className="flex flex-col items-start gap-3 rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-page)] px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <p className="text-[13px] font-semibold leading-tight text-[color:var(--text-primary)]">
          Genera un reporte actualizado de tu cumplimiento
        </p>
        <p className="text-[12px] text-[color:var(--text-secondary)]">
          Crea “Mi estado de cumplimiento” con los datos más recientes y
          compártelo con tu cliente.
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {topActionHref ? (
          <Button asChild variant="outline" size="sm">
            <Link href={topActionHref}>
              <CloudArrowUp
                className="h-3.5 w-3.5"
                weight="bold"
                aria-hidden="true"
              />
              Subir documento pendiente
            </Link>
          </Button>
        ) : null}
        <Button
          type="button"
          size="sm"
          onClick={onGenerate}
          disabled={generating}
          aria-busy={generating}
        >
          {generating ? (
            <CircleNotch
              className="h-3.5 w-3.5 animate-spin"
              weight="bold"
              aria-hidden="true"
            />
          ) : (
            <Sparkle className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
          )}
          {generating ? "Generando…" : "Generar reporte actualizado"}
        </Button>
      </div>
    </div>
  );
}
