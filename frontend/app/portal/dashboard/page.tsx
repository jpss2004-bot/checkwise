"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  CalendarBlank,
  ClipboardText,
  HourglassHigh,
  LockKey,
  PencilSimple,
} from "@phosphor-icons/react";

import { DocStateBadge } from "@/components/checkwise/doc-state-badge";
import { EvidenceSlotGrid } from "@/components/checkwise/portal/evidence-slot-grid";
import {
  NextActionRail,
  type NextActionItem,
  type NextActionPriority,
} from "@/components/checkwise/portal/next-action-rail";
import { ProviderContextBar } from "@/components/checkwise/portal/provider-context-bar";
import { SemaphoreCard } from "@/components/checkwise/portal/semaphore-card";
import { WorkspaceIdentityCard } from "@/components/checkwise/workspace/workspace-identity-card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import type { EvidenceSlotCardProps } from "@/components/checkwise/portal/evidence-slot-card";
import {
  getDashboard,
  type DashboardAttentionItem,
  type DashboardOnboardingSummary,
  type DashboardPayload,
  type DashboardSemaphore,
  type DashboardSuggestedAction,
  type DashboardUpcomingDeadline,
  type DashboardDocumentStateCounts,
  type DashboardSemaphoreLevel,
} from "@/lib/api/portal";
import { verifyToken } from "@/lib/mock/invitations";
import { withOnboardingGate } from "@/lib/session/with-onboarding-gate";
import type { PortalSession } from "@/lib/session/portal";
import type { DocumentStateCode } from "@/lib/types";
import { buildWorkspaceContext } from "@/lib/workspace/resolver";
import type {
  DashboardSemaphore as ComponentSemaphore,
  SemaphoreTone,
} from "@/lib/mock/dashboard";

/**
 * Provider dashboard (Phase 4 — backend-owned read model).
 *
 * Locked state shows a hero pointing back to /portal/onboarding when
 * the expediente gate isn't satisfied. Otherwise the full dashboard
 * renders with semaphore + suggested actions + attention rows +
 * calendar entry + document-state overview.
 *
 * Data source: GET /api/v1/portal/workspaces/{id}/dashboard. The
 * backend composes onboarding + calendar slot views (replacement-
 * lineage aware) into the semaphore + counts + computed suggested
 * actions. Mocks are no longer consumed at runtime.
 */
function DashboardInner({ session }: { session: PortalSession }) {
  const [dashboard, setDashboard] = useState<DashboardPayload | null>(null);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getDashboard(session)
      .then((payload) => {
        if (cancelled) return;
        setDashboard(payload);
        setLoadError(false);
      })
      .catch(() => {
        if (cancelled) return;
        setLoadError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [session]);

  // Build the workspace identity snapshot — same source as
  // /portal/entra-a-tu-espacio so users see consistent values.
  const workspace = useMemo(() => {
    const inv = verifyToken("demo").ok ? verifyToken("demo").invitation ?? null : null;
    return buildWorkspaceContext(session, inv);
  }, [session]);

  if (loadError && !dashboard) {
    return (
      <>
        <ProviderContextBar session={session} />
        <main className="mx-auto max-w-7xl space-y-6 px-5 py-8">
          <Alert variant="warning">
            <AlertTitle>No pudimos cargar tu dashboard</AlertTitle>
            <AlertDescription>
              Algo falló al consultar el resumen de tus obligaciones. Tu sesión
              sigue activa; vuelve a intentarlo en unos segundos.
            </AlertDescription>
          </Alert>
        </main>
      </>
    );
  }

  if (!dashboard) {
    return (
      <>
        <ProviderContextBar session={session} />
        <main className="mx-auto max-w-7xl space-y-6 px-5 py-8">
          <DashboardSkeleton />
        </main>
      </>
    );
  }

  const onboarding = dashboard.onboarding_summary;
  const gateBlocked = onboarding.needs_action > 0;
  const provisional = !gateBlocked && onboarding.in_review > 0;

  return (
    <>
      <ProviderContextBar
        session={session}
        onboardingPct={onboarding.completion_pct}
      />
      <main className="mx-auto max-w-7xl space-y-8 px-5 py-8">
        {gateBlocked ? <LockedDashboardHero summary={onboarding} /> : null}
        {provisional ? <ProvisionalAccessBanner /> : null}

        <WorkspaceIdentityCard workspace={workspace} />

        <SemaphoreCard data={adaptSemaphore(dashboard.semaphore)} />

        <ExpedienteSummaryCard summary={onboarding} />

        <div className="grid gap-6 lg:grid-cols-3">
          <div className="space-y-6 lg:col-span-2">
            <NextActionRail
              actions={toNextActionItems(dashboard.suggested_actions)}
              emptyState={{
                title: "Estás al día",
                description: "No hay acciones urgentes para tu workspace en este momento.",
              }}
            />
            <EvidenceSlotGrid
              title="Necesita tu atención"
              items={toSlotItems(dashboard.attention_today)}
              emptyState={{
                title: "Nada por atender hoy",
                description:
                  "Todas tus obligaciones activas están en revisión o aprobadas.",
              }}
            />
            <DocumentStateOverview counts={dashboard.document_state_counts} />
          </div>
          <div className="space-y-6">
            <CalendarTeaser />
            <UpcomingCard rows={dashboard.upcoming_deadlines} />
          </div>
        </div>
      </main>
    </>
  );
}

export default withOnboardingGate(DashboardInner);

// ─── Skeleton ─────────────────────────────────────────────────────

function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      <div className="h-24 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]" />
      <div className="h-40 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]" />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <div className="h-48 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]" />
          <div className="h-48 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]" />
        </div>
        <div className="space-y-6">
          <div className="h-40 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]" />
          <div className="h-40 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]" />
        </div>
      </div>
    </div>
  );
}

// ─── Adapters: backend payload → component prop shape ─────────────

const LEVEL_TO_TONE: Record<DashboardSemaphoreLevel, SemaphoreTone> = {
  green: "green",
  yellow: "yellow",
  red: "red",
};

function adaptSemaphore(s: DashboardSemaphore): ComponentSemaphore {
  return {
    tone: LEVEL_TO_TONE[s.level],
    headline: s.label,
    description: s.reason,
    compliance_pct: s.compliance_pct,
    total_tracked: s.total_tracked,
    on_track: s.on_track,
  };
}

// Backend slot states (10) → frontend DocumentStateCode (8).
const SLOT_STATE_TO_DOC_CODE: Record<string, DocumentStateCode> = {
  missing: "pending",
  uploaded: "uploaded",
  in_review: "in_review",
  approved: "approved",
  rejected: "rejected",
  needs_correction: "needs_review",
  possible_mismatch: "needs_review",
  exception: "approved",
  expired: "expired",
  not_applicable: "approved",
};

const ACTION_CTA_LABEL: Record<DashboardSuggestedAction["type"], string> = {
  reupload: "Corregir",
  clarify: "Responder",
  verify_mismatch: "Verificar",
  complete_onboarding: "Subir documento",
  upcoming: "Subir documento",
};

const ACTION_PRIORITY_MAP: Record<DashboardSuggestedAction["priority"], NextActionPriority> = {
  low: "low",
  medium: "medium",
  high: "high",
};

function toNextActionItems(actions: DashboardSuggestedAction[]): NextActionItem[] {
  return actions.map((action) => ({
    id: action.id,
    title: action.title,
    body: action.body,
    priority: ACTION_PRIORITY_MAP[action.priority],
    ctaLabel: ACTION_CTA_LABEL[action.type] ?? "Abrir",
    ctaHref: action.href,
    meta: action.requirement_code ?? action.period_key ?? undefined,
  }));
}

function toSlotItems(rows: DashboardAttentionItem[]): EvidenceSlotCardProps[] {
  return rows.map((row) => ({
    id: row.id,
    title: row.title,
    institution: INSTITUTION_LABEL[row.institution] ?? row.institution.toUpperCase(),
    state: SLOT_STATE_TO_DOC_CODE[row.state] ?? "pending",
    dueInDays: row.due_in_days,
    href: row.href,
  }));
}

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
  summary,
}: {
  summary: DashboardOnboardingSummary;
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
          <Badge variant="brand">{summary.completion_pct}%</Badge>
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
        value={summary.completion_pct}
        label={`${summary.completed + summary.in_review} de ${summary.total_required} documentos obligatorios avanzados`}
        showValue
        tone={summary.needs_action === 0 ? "success" : "brand"}
        className="max-w-3xl"
      />

      <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <SummaryStat label="Aprobados" value={summary.completed} tone="success" />
        <SummaryStat label="En revisión" value={summary.in_review} tone="info" />
        <SummaryStat label="Por atender" value={summary.needs_action} tone="warning" />
        <SummaryStat
          label="Opcionales pendientes"
          value={summary.optional_pending}
          tone="neutral"
        />
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
  summary,
}: {
  summary: DashboardOnboardingSummary;
}) {
  return (
    <Alert variant="warning">
      <AlertTitle className="flex items-center gap-2">
        <LockKey className="h-4 w-4" weight="bold" aria-hidden="true" />
        Tu dashboard está limitado
      </AlertTitle>
      <AlertDescription className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <span>
          Tienes {summary.needs_action} documento
          {summary.needs_action === 1 ? "" : "s"} del expediente inicial por
          atender. Mientras tanto, puedes ver el dashboard pero no recibirás
          recordatorios mensuales.
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

// ─── Institution labels (used by UpcomingCard side rail) ────────

const INSTITUTION_LABEL: Record<string, string> = {
  sat: "SAT",
  imss: "IMSS",
  infonavit: "INFONAVIT",
  stps_repse: "STPS / REPSE",
  interno_cliente: "Interno / Cliente",
};

// ─── Document state overview ─────────────────────────────────────

function DocumentStateOverview({
  counts,
}: {
  counts: DashboardDocumentStateCounts;
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
  // 12 month dots — colored statically. Real coloring is provided by
  // /portal/calendar which the user can open from this teaser.
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
  const CURRENT = new Date().getMonth();
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
        <Badge variant="brand">{new Date().getFullYear()}</Badge>
      </div>
      <div className="grid grid-cols-6 gap-2">
        {MONTHS.map((month, idx) => {
          const isCurrent = idx === CURRENT;
          const isPast = idx < CURRENT;
          const tone = isPast
            ? "bg-[color:var(--surface-sunken)] text-[color:var(--text-tertiary)] border-[color:var(--border-subtle)]"
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
        Abre el calendario para ver cada obligación con su estado real.
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

function UpcomingCard({ rows }: { rows: DashboardUpcomingDeadline[] }) {
  if (rows.length === 0) return null;
  return (
    <section className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-5 shadow-xs">
      <h2 className="mb-3 flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wide text-[color:var(--text-primary)]">
        Próximos vencimientos
      </h2>
      <ul className="space-y-3">
        {rows.map((row) => {
          const institutionLabel =
            INSTITUTION_LABEL[row.institution] ?? row.institution;
          return (
            <li
              key={row.id}
              className="flex items-start justify-between gap-3 border-b border-[color:var(--border-subtle)] pb-3 last:border-0 last:pb-0"
            >
              <div className="min-w-0">
                <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                  {institutionLabel}
                </p>
                <Link
                  href={row.href}
                  className="mt-0.5 block text-[13px] font-medium leading-5 text-[color:var(--text-primary)] hover:underline"
                >
                  {row.title}
                </Link>
                {row.period_key ? (
                  <p className="mt-0.5 font-mono text-[10px] text-[color:var(--text-tertiary)]">
                    {row.period_key}
                  </p>
                ) : null}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
