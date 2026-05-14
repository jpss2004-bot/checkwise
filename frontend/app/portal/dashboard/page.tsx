"use client";

import { useMemo } from "react";
import Link from "next/link";
import {
  ArrowRight,
  CalendarBlank,
  ClipboardText,
  ClockCounterClockwise,
  HourglassHigh,
  LockKey,
  PencilSimple,
} from "@phosphor-icons/react";

import { DocStateBadge } from "@/components/checkwise/doc-state-badge";
import { ProviderContextBar } from "@/components/checkwise/portal/provider-context-bar";
import { SemaphoreCard } from "@/components/checkwise/portal/semaphore-card";
import { SuggestedActions } from "@/components/checkwise/portal/suggested-actions";
import { WorkspaceIdentityCard } from "@/components/checkwise/workspace/workspace-identity-card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
  MOCK_ATTENTION_TODAY,
  MOCK_DOC_STATE_COUNTS,
  MOCK_SEMAPHORE,
  MOCK_SUGGESTED_ACTIONS,
  type AttentionRow,
} from "@/lib/mock/dashboard";
import { MOCK_EXPEDIENTE, countExpediente } from "@/lib/mock/expediente";
import { verifyToken } from "@/lib/mock/invitations";
import { decidePostLoginRoute } from "@/lib/routing/post-login";
import { withPortalSession } from "@/lib/session/with-portal-session";
import type { PortalSession } from "@/lib/session/portal";
import type { DocumentStateCode } from "@/lib/types";
import { buildWorkspaceContext } from "@/lib/workspace/resolver";

/**
 * Provider dashboard.
 *
 * Locked state shows a hero pointing back to /portal/onboarding when
 * the expediente gate isn't satisfied. Otherwise the full dashboard
 * renders with semaphore + suggested actions + attention rows +
 * calendar entry + document-state overview.
 *
 * TODO[backend-integration]: replace MOCK_SEMAPHORE,
 * MOCK_SUGGESTED_ACTIONS, MOCK_ATTENTION_TODAY, MOCK_DOC_STATE_COUNTS
 * with /api/v1/portal/dashboard once it exposes the equivalents.
 */
function DashboardInner({ session }: { session: PortalSession }) {
  // Reuse the same mock expediente to compute the gate.
  const expedienteCounts = useMemo(
    () => countExpediente(MOCK_EXPEDIENTE),
    [],
  );
  const decision = useMemo(
    () => decidePostLoginRoute(MOCK_EXPEDIENTE),
    [],
  );
  const gateBlocked = decision.banner === "expediente_blocked";
  const provisional = decision.banner === "provisional_access";

  // Build the workspace identity snapshot — same source as
  // /portal/entra-a-tu-espacio so users see consistent values.
  const workspace = useMemo(() => {
    const inv = verifyToken("demo").ok ? verifyToken("demo").invitation ?? null : null;
    return buildWorkspaceContext(session, inv);
  }, [session]);

  return (
    <>
      <ProviderContextBar
        session={session}
        onboardingPct={expedienteCounts.completion_pct}
      />
      <main className="mx-auto max-w-7xl space-y-8 px-5 py-8">
        {gateBlocked ? <LockedDashboardHero counts={expedienteCounts} /> : null}
        {provisional ? <ProvisionalAccessBanner /> : null}

        <WorkspaceIdentityCard workspace={workspace} />

        <SemaphoreCard data={MOCK_SEMAPHORE} />

        <ExpedienteSummaryCard counts={expedienteCounts} />

        <div className="grid gap-6 lg:grid-cols-3">
          <div className="space-y-6 lg:col-span-2">
            <SuggestedActions actions={MOCK_SUGGESTED_ACTIONS} />
            <AttentionToday rows={MOCK_ATTENTION_TODAY} />
            <DocumentStateOverview counts={MOCK_DOC_STATE_COUNTS} />
          </div>
          <div className="space-y-6">
            <CalendarTeaser />
            <UpcomingCard rows={MOCK_ATTENTION_TODAY.slice(0, 3)} />
          </div>
        </div>
      </main>
    </>
  );
}

export default withPortalSession(DashboardInner);

// ─── Provisional access banner ───────────────────────────────────

function ProvisionalAccessBanner() {
  return (
    <Alert variant="info">
      <AlertTitle className="flex items-center gap-2">
        <HourglassHigh className="h-4 w-4" weight="bold" aria-hidden="true" />
        Tu expediente está en revisión
      </AlertTitle>
      <AlertDescription className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <span>
          Subiste todos los documentos obligatorios — tienes acceso provisional
          al dashboard mientras nuestro equipo legal los revisa. Te avisaremos
          por correo cuando todo quede aprobado.
        </span>
        <Button asChild size="sm" variant="outline" className="shrink-0">
          <Link href="/portal/onboarding">
            <span>Ver expediente</span>
            <ArrowRight className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
          </Link>
        </Button>
      </AlertDescription>
    </Alert>
  );
}

// ─── Expediente summary card ────────────────────────────────────

function ExpedienteSummaryCard({
  counts,
}: {
  counts: ReturnType<typeof countExpediente>;
}) {
  return (
    <section className="cw-fade-up rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-5 shadow-xs">
      <header className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <ClipboardText
            className="h-5 w-5 text-[color:var(--text-brand)]"
            weight="duotone"
            aria-hidden="true"
          />
          <h2 className="text-[15px] font-semibold text-[color:var(--text-primary)]">
            Tu expediente inicial
          </h2>
          <Badge variant="brand">{counts.completion_pct}%</Badge>
        </div>
        <Button asChild variant="outline" size="sm">
          <Link href="/portal/onboarding">
            <PencilSimple className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
            <span>Revisar o actualizar</span>
            <ArrowRight className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
          </Link>
        </Button>
      </header>

      <Progress
        value={counts.completion_pct}
        label={`${counts.completed + counts.in_review} de ${counts.total_required} documentos obligatorios avanzados`}
        showValue
        tone={counts.needs_action === 0 ? "success" : "brand"}
        className="max-w-3xl"
      />

      <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <SummaryStat label="Aprobados" value={counts.completed} tone="success" />
        <SummaryStat label="En revisión" value={counts.in_review} tone="info" />
        <SummaryStat label="Por atender" value={counts.needs_action} tone="warning" />
        <SummaryStat label="Opcionales pendientes" value={counts.optional_pending} tone="neutral" />
      </dl>
    </section>
  );
}

function SummaryStat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "success" | "info" | "warning" | "neutral";
}) {
  const accent =
    tone === "success"
      ? "text-[color:var(--status-success-text)]"
      : tone === "info"
        ? "text-[color:var(--status-info-text)]"
        : tone === "warning"
          ? "text-[color:var(--status-warning-text)]"
          : "text-[color:var(--text-primary)]";
  return (
    <div className="rounded-sm border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] px-3 py-2.5">
      <dt className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
        {label}
      </dt>
      <dd className={`font-mono text-xl font-semibold tabular-nums ${accent}`}>
        {value}
      </dd>
    </div>
  );
}

// ─── Locked-state hero ───────────────────────────────────────────

function LockedDashboardHero({
  counts,
}: {
  counts: ReturnType<typeof countExpediente>;
}) {
  return (
    <Alert variant="warning">
      <AlertTitle className="flex items-center gap-2">
        <LockKey className="h-4 w-4" weight="bold" aria-hidden="true" />
        Tu dashboard está limitado
      </AlertTitle>
      <AlertDescription className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <span>
          Tienes {counts.needs_action} documento{counts.needs_action === 1 ? "" : "s"}{" "}
          del expediente inicial por atender. Mientras tanto, puedes ver el
          dashboard pero no recibirás recordatorios mensuales.
        </span>
        <Button asChild size="sm" variant="default" className="shrink-0">
          <Link href="/portal/onboarding">
            <span>Ir al expediente</span>
            <ArrowRight className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
          </Link>
        </Button>
      </AlertDescription>
    </Alert>
  );
}

// ─── Attention today ─────────────────────────────────────────────

function AttentionToday({ rows }: { rows: AttentionRow[] }) {
  if (rows.length === 0) return null;
  return (
    <section className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-xs">
      <header className="flex items-center gap-2 border-b border-[color:var(--border-subtle)] px-5 py-3">
        <ClockCounterClockwise
          className="h-4 w-4 text-[color:var(--text-brand)]"
          weight="duotone"
          aria-hidden="true"
        />
        <h2 className="text-[13px] font-semibold uppercase tracking-wide text-[color:var(--text-primary)]">
          Necesita tu atención hoy
        </h2>
      </header>
      <ul className="divide-y divide-[color:var(--border-subtle)]">
        {rows.map((row) => (
          <li
            key={row.id}
            className="flex flex-wrap items-center justify-between gap-3 px-5 py-3 transition-colors hover:bg-[color:var(--surface-hover)]"
          >
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-[color:var(--text-primary)]">
                {row.title}
              </p>
              <p className="mt-0.5 font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                {row.institution}
              </p>
            </div>
            <div className="flex items-center gap-3">
              <DueChip days={row.due_in_days} />
              <DocStateBadge state={row.state} withIcon={false} />
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function DueChip({ days }: { days: number }) {
  const overdue = days < 0;
  const urgent = days >= 0 && days <= 5;
  const className = overdue
    ? "bg-[color:var(--status-error-bg)] text-[color:var(--status-error-text)] border-[color:var(--status-error-border)]"
    : urgent
      ? "bg-[color:var(--status-warning-bg)] text-[color:var(--status-warning-text)] border-[color:var(--status-warning-border)]"
      : "bg-[color:var(--surface-sunken)] text-[color:var(--text-secondary)] border-[color:var(--border-default)]";
  const label = overdue
    ? `Vencido hace ${Math.abs(days)}d`
    : days === 0
      ? "Vence hoy"
      : `En ${days}d`;
  return (
    <span
      className={`rounded-full border px-2.5 py-0.5 font-mono text-[10px] font-medium ${className}`}
    >
      {label}
    </span>
  );
}

// ─── Document state overview ─────────────────────────────────────

function DocumentStateOverview({
  counts,
}: {
  counts: typeof MOCK_DOC_STATE_COUNTS;
}) {
  const entries: { state: DocumentStateCode; count: number }[] = [
    { state: "approved", count: counts.approved },
    { state: "in_review", count: counts.in_review },
    { state: "uploaded", count: counts.uploaded },
    { state: "pending", count: counts.pending },
    { state: "needs_review", count: counts.needs_review },
    { state: "rejected", count: counts.rejected },
    { state: "expired", count: counts.expired },
  ];
  return (
    <section className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-5 shadow-xs">
      <h2 className="mb-3 text-[13px] font-semibold uppercase tracking-wide text-[color:var(--text-primary)]">
        Resumen por estado
      </h2>
      <ul className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {entries.map(({ state, count }) => (
          <li
            key={state}
            className="flex items-center justify-between gap-2 rounded-sm border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] px-3 py-2.5"
          >
            <DocStateBadge state={state} />
            <span className="font-mono text-sm font-semibold tabular-nums text-[color:var(--text-primary)]">
              {count}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

// ─── Calendar teaser ─────────────────────────────────────────────

function CalendarTeaser() {
  // 12 month dots — colored by mock status; clicking goes to the
  // calendar route. Real palette comes from the dashboard aggregate.
  const MONTHS = [
    "Ene",
    "Feb",
    "Mar",
    "Abr",
    "May",
    "Jun",
    "Jul",
    "Ago",
    "Sep",
    "Oct",
    "Nov",
    "Dic",
  ];
  // 0..4 → past, 5 → current month (May), 6..11 → upcoming
  const CURRENT = 4;
  return (
    <section className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-5 shadow-xs">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wide text-[color:var(--text-primary)]">
          <CalendarBlank
            className="h-4 w-4 text-[color:var(--text-brand)]"
            weight="duotone"
            aria-hidden="true"
          />
          Calendario REPSE
        </h2>
        <Badge variant="brand">2026</Badge>
      </div>
      <div className="grid grid-cols-6 gap-2">
        {MONTHS.map((month, idx) => {
          const isCurrent = idx === CURRENT;
          const isPast = idx < CURRENT;
          const tone = isPast
            ? idx === 2
              ? "bg-[color:var(--status-warning-bg)] text-[color:var(--status-warning-text)] border-[color:var(--status-warning-border)]"
              : "bg-[color:var(--status-success-bg)] text-[color:var(--status-success-text)] border-[color:var(--status-success-border)]"
            : isCurrent
              ? "border-[color:var(--border-focus)] bg-[color:var(--surface-brand-muted)] text-[color:var(--text-brand)] ring-2 ring-[color:var(--border-focus)]/40"
              : "border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] text-[color:var(--text-tertiary)]";
          return (
            <div
              key={month}
              className={`flex flex-col items-center justify-center rounded-sm border px-1 py-2 ${tone}`}
            >
              <p className="font-mono text-[10px] uppercase">{month}</p>
            </div>
          );
        })}
      </div>
      <p className="mt-3 text-xs text-[color:var(--text-secondary)]">
        Mayo es el periodo en curso. Tienes 2 obligaciones por completar.
      </p>
      <Button asChild variant="outline" size="sm" className="mt-3 w-full">
        <Link href="/portal/calendar">
          <span>Abrir calendario completo</span>
          <ArrowRight className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
        </Link>
      </Button>
    </section>
  );
}

// ─── Upcoming side card ──────────────────────────────────────────

function UpcomingCard({ rows }: { rows: AttentionRow[] }) {
  if (rows.length === 0) return null;
  return (
    <section className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-5 shadow-xs">
      <h2 className="mb-3 flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wide text-[color:var(--text-primary)]">
        Próximos vencimientos
      </h2>
      <ul className="space-y-3">
        {rows.map((row) => (
          <li
            key={row.id}
            className="flex items-start justify-between gap-3 border-b border-[color:var(--border-subtle)] pb-3 last:border-0 last:pb-0"
          >
            <div className="min-w-0">
              <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                {row.institution}
              </p>
              <p className="mt-0.5 text-[13px] font-medium leading-5 text-[color:var(--text-primary)]">
                {row.title}
              </p>
            </div>
            <DueChip days={row.due_in_days} />
          </li>
        ))}
      </ul>
    </section>
  );
}
