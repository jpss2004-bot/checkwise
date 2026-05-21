"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  CalendarBlank,
  CheckCircle,
  CloudArrowUp,
  FileMagnifyingGlass,
  HourglassHigh,
  LockKey,
  Tray,
  Warning,
  WarningOctagon,
  type Icon,
} from "@phosphor-icons/react";

import { DocStateBadge } from "@/components/checkwise/doc-state-badge";
import { NextActionRail } from "@/components/checkwise/portal/next-action-rail";
import { PortalAppShell } from "@/components/checkwise/portal/portal-app-shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { MetadataStrip, type MetadataItem } from "@/components/ui/metadata-strip";
import { PageHeader } from "@/components/ui/page-header";
import { cn } from "@/lib/utils";
import {
  getDashboard,
  statusToDocumentStateCode,
  type DashboardAttentionItem,
  type DashboardOnboardingSummary,
  type DashboardPayload,
  type DashboardRecentUpload,
  type DashboardSemaphore,
  type DashboardSemaphoreLevel,
  type DashboardSuggestedAction,
  type DashboardUpcomingDeadline,
  type RequirementStatus,
} from "@/lib/api/portal";
import { withOnboardingGate } from "@/lib/session/with-onboarding-gate";
import type { PortalSession } from "@/lib/session/portal";
import type { DocumentStateCode } from "@/lib/types";

/**
 * Provider dashboard — operational REPSE compliance control panel.
 *
 * Session 4 redesign (2026-05-21): the dashboard was rebuilt around
 * the four questions an active vendor actually asks when they open
 * the surface:
 *
 *   1. "What is my current compliance status?" — thin status banner
 *      at the top of the page, semaphore tone + one-line reason.
 *   2. "What should I do next?" — single primary action in the
 *      left column, with a compact secondary list under it.
 *   3. "What is missing / in review / what did I upload?" — three
 *      side-by-side compact lists, each grouped by lifecycle stage
 *      and rendered as scannable rows instead of decorative cards.
 *   4. "What is coming up?" — right-rail "Próximos vencimientos"
 *      list, sorted by urgency.
 *
 * All four are backed by ``GET /api/v1/portal/workspaces/{id}/dashboard``;
 * no frontend-only mock suggestions remain. The donut + radial gauge
 * + 12-month calendar teaser from the previous iteration were removed
 * because they duplicated data the metadata strip + status banner +
 * /portal/calendar already surface — they made the dashboard read as
 * a marketing page rather than an operations console.
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

  const onboardingPct = dashboard?.onboarding_summary.completion_pct ?? null;

  if (loadError && !dashboard) {
    return (
      <PortalAppShell session={session}>
        <main className="mx-auto max-w-7xl space-y-6 px-5 py-8">
          <Alert variant="warning">
            <AlertTitle>No pudimos cargar tu dashboard</AlertTitle>
            <AlertDescription>
              Algo falló al consultar el resumen de tus obligaciones. Tu sesión
              sigue activa; vuelve a intentarlo en unos segundos.
            </AlertDescription>
          </Alert>
        </main>
      </PortalAppShell>
    );
  }

  if (!dashboard) {
    return (
      <PortalAppShell session={session}>
        <main className="mx-auto max-w-7xl space-y-5 px-5 py-6 md:px-7">
          <DashboardSkeleton />
        </main>
      </PortalAppShell>
    );
  }

  const onboarding = dashboard.onboarding_summary;
  // Only treat the dashboard as "initial-expediente locked" when the
  // provider has not yet completed onboarding. Once onboarding_completed_at
  // is set, any remaining ``needs_action`` documents are recurring
  // monthly obligations, not blockers on the initial expediente.
  const initialOnboardingDone = session.onboarding_completed_at !== null;
  const gateBlocked = !initialOnboardingDone && onboarding.needs_action > 0;
  const provisional = !gateBlocked && onboarding.in_review > 0 && !initialOnboardingDone;

  const counts = dashboard.document_state_counts;
  const recent = dashboard.recent_uploads ?? [];

  const attentionRows = splitAttentionItems(dashboard.attention_today);
  const inReviewRows = recent
    .filter((row) => {
      const code = statusToDocumentStateCode(row.status as RequirementStatus);
      return code === "in_review" || code === "uploaded";
    })
    .slice(0, 5);

  const primaryAction = dashboard.suggested_actions[0] ?? null;
  const secondaryActions = dashboard.suggested_actions.slice(1, 4);

  return (
    <PortalAppShell session={session} onboardingPct={onboardingPct}>
      <main className="mx-auto max-w-7xl space-y-5 px-5 py-6 md:px-7">
        <PageHeader
          eyebrow="Centro de cumplimiento"
          title={session.vendor_name}
          description="Lo que falta, lo que está en revisión y la próxima acción concreta para mantener tu cumplimiento al día."
          actions={
            <Button asChild size="sm" variant="outline">
              <Link href="/portal/upload">
                <CloudArrowUp className="h-4 w-4" weight="bold" aria-hidden="true" />
                Subir documento
              </Link>
            </Button>
          }
        />

        <MetadataStrip
          items={buildMetadataItems({
            rfc: session.vendor_rfc,
            personaType: session.persona_type,
            summary: onboarding,
            counts,
            semaphore: dashboard.semaphore,
            nextDeadline: dashboard.upcoming_deadlines[0] ?? null,
          })}
        />

        <StatusBanner semaphore={dashboard.semaphore} />

        {gateBlocked ? <LockedDashboardBanner summary={onboarding} /> : null}
        {provisional ? <ProvisionalAccessBanner /> : null}

        <div className="cw-stagger grid gap-5 lg:grid-cols-3">
          <div className="space-y-5 lg:col-span-2">
            <PrimaryActionPanel
              primary={primaryAction}
              secondary={secondaryActions}
              totalActions={dashboard.suggested_actions.length}
            />

            <OperationalQueues
              attention={attentionRows.actionable}
              dueSoon={attentionRows.dueSoon}
              inReview={inReviewRows}
              recent={recent}
            />
          </div>

          <div className="space-y-5">
            <UpcomingDeadlinesPanel rows={dashboard.upcoming_deadlines} />
            <ComplianceLedger counts={counts} />
          </div>
        </div>
      </main>
    </PortalAppShell>
  );
}

export default withOnboardingGate(DashboardInner);

// ─── Skeleton ─────────────────────────────────────────────────────

function DashboardSkeleton() {
  return (
    <div className="space-y-5">
      <div className="h-24 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]" />
      <div className="h-14 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]" />
      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <div className="h-40 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]" />
          <div className="h-72 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]" />
        </div>
        <div className="space-y-5">
          <div className="h-48 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]" />
          <div className="h-48 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]" />
        </div>
      </div>
    </div>
  );
}

// ─── Metadata strip ───────────────────────────────────────────────

const INSTITUTION_LABEL: Record<string, string> = {
  sat: "SAT",
  imss: "IMSS",
  infonavit: "INFONAVIT",
  stps_repse: "STPS / REPSE",
  interno_cliente: "Interno",
};

function buildMetadataItems(args: {
  rfc: string;
  personaType: PortalSession["persona_type"];
  summary: DashboardOnboardingSummary;
  counts: DashboardPayload["document_state_counts"];
  semaphore: DashboardSemaphore;
  nextDeadline: DashboardUpcomingDeadline | null;
}): MetadataItem[] {
  const { rfc, personaType, summary, counts, semaphore, nextDeadline } = args;
  const deadlineLabel = nextDeadline
    ? `${INSTITUTION_LABEL[nextDeadline.institution] ?? nextDeadline.institution} · ${
        nextDeadline.due_in_days != null
          ? nextDeadline.due_in_days === 0
            ? "hoy"
            : `${nextDeadline.due_in_days}d`
          : (nextDeadline.period_key ?? "")
      }`
    : "Sin vencimientos próximos";
  return [
    { label: "RFC", value: rfc, mono: true },
    { label: "Persona", value: personaType === "moral" ? "Moral" : "Física" },
    {
      label: "Cumplimiento",
      value: `${semaphore.compliance_pct}%`,
      mono: true,
      tone:
        semaphore.level === "green"
          ? "default"
          : semaphore.level === "yellow"
            ? "warning"
            : "warning",
    },
    {
      label: "Por atender",
      value: summary.needs_action,
      mono: true,
      tone: summary.needs_action > 0 ? "warning" : "default",
    },
    { label: "En revisión", value: summary.in_review, mono: true },
    { label: "Aprobados", value: counts.approved, mono: true },
    { label: "Próximo", value: deadlineLabel },
  ];
}

// ─── Status banner (replaces giant semaphore hero) ────────────────

const TONE_TO_ICON: Record<DashboardSemaphoreLevel, Icon> = {
  green: CheckCircle,
  yellow: Warning,
  red: WarningOctagon,
};

const TONE_TO_BAR: Record<DashboardSemaphoreLevel, string> = {
  green: "bg-[color:var(--status-success-text)]",
  yellow: "bg-[color:var(--status-warning-text)]",
  red: "bg-[color:var(--status-error-text)]",
};

const TONE_TO_BORDER: Record<DashboardSemaphoreLevel, string> = {
  green: "border-[color:var(--status-success-border)]",
  yellow: "border-[color:var(--status-warning-border)]",
  red: "border-[color:var(--status-error-border)]",
};

const TONE_TO_TEXT: Record<DashboardSemaphoreLevel, string> = {
  green: "text-[color:var(--status-success-text)]",
  yellow: "text-[color:var(--status-warning-text)]",
  red: "text-[color:var(--status-error-text)]",
};

function StatusBanner({ semaphore }: { semaphore: DashboardSemaphore }) {
  const IconComponent = TONE_TO_ICON[semaphore.level];
  return (
    <section
      aria-label="Estado de cumplimiento"
      className={cn(
        "cw-fade-up flex items-stretch overflow-hidden rounded-lg border bg-[color:var(--surface-raised)] shadow-xs",
        TONE_TO_BORDER[semaphore.level],
      )}
    >
      <span
        aria-hidden="true"
        className={cn("w-1.5 shrink-0", TONE_TO_BAR[semaphore.level])}
      />
      <div className="flex flex-1 flex-wrap items-center justify-between gap-3 px-4 py-3 sm:gap-5">
        <div className="flex min-w-0 items-center gap-3">
          <IconComponent
            className={cn("h-5 w-5 shrink-0", TONE_TO_TEXT[semaphore.level])}
            weight="fill"
            aria-hidden="true"
          />
          <div className="min-w-0">
            <p className="text-[13px] font-semibold leading-tight text-[color:var(--text-primary)]">
              {semaphore.label}
            </p>
            <p className="mt-0.5 line-clamp-2 text-xs leading-[1.45] text-[color:var(--text-secondary)]">
              {semaphore.reason}
            </p>
          </div>
        </div>
        <div className="flex shrink-0 items-baseline gap-2">
          <span
            className={cn(
              "font-mono text-xl font-semibold tabular-nums leading-none",
              TONE_TO_TEXT[semaphore.level],
            )}
          >
            {semaphore.compliance_pct}%
          </span>
          <span className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
            {semaphore.on_track}/{semaphore.total_tracked}
          </span>
        </div>
      </div>
    </section>
  );
}

// ─── Primary + secondary actions ──────────────────────────────────

const ACTION_CTA_LABEL: Record<DashboardSuggestedAction["type"], string> = {
  reupload: "Corregir carga",
  clarify: "Responder observación",
  verify_mismatch: "Verificar documento",
  complete_onboarding: "Subir documento",
  upcoming: "Subir documento",
  regularize: "Regularizar",
};

function PrimaryActionPanel({
  primary,
  secondary,
  totalActions,
}: {
  primary: DashboardSuggestedAction | null;
  secondary: DashboardSuggestedAction[];
  totalActions: number;
}) {
  if (!primary) {
    return (
      <NextActionRail
        actions={[]}
        emptyState={{
          title: "Estás al día",
          description:
            "No hay acciones urgentes para tu expediente en este momento.",
        }}
      />
    );
  }

  const priorityDot =
    primary.priority === "high"
      ? "bg-[color:var(--status-error-text)]"
      : primary.priority === "medium"
        ? "bg-[color:var(--status-warning-text)]"
        : "bg-[color:var(--status-info-text)]";

  const priorityLabel =
    primary.priority === "high"
      ? "Prioridad alta"
      : primary.priority === "medium"
        ? "Prioridad media"
        : "Prioridad baja";

  return (
    <section
      aria-label="Próxima acción"
      className="cw-fade-up rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-xs"
    >
      <header className="flex items-center justify-between gap-3 border-b border-[color:var(--border-subtle)] px-5 py-3">
        <h2 className="text-[13px] font-semibold uppercase tracking-wide text-[color:var(--text-primary)]">
          Tu siguiente acción
        </h2>
        <span className="font-mono text-[10px] tabular-nums text-[color:var(--text-tertiary)]">
          {totalActions} {totalActions === 1 ? "tarea" : "tareas"}
        </span>
      </header>

      <div className="space-y-3 p-5">
        <article className="flex flex-col gap-3 rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-page)] p-4 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
          <div className="min-w-0 flex-1 space-y-1.5">
            <div className="flex items-center gap-2">
              <span aria-hidden="true" className={cn("h-2 w-2 rounded-full", priorityDot)} />
              <span className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                {primary.requirement_code ?? primary.period_key ?? priorityLabel}
              </span>
            </div>
            <h3 className="text-[14px] font-semibold leading-snug text-[color:var(--text-primary)]">
              {primary.title}
            </h3>
            <p className="text-xs leading-[1.55] text-[color:var(--text-secondary)]">
              {primary.body}
            </p>
          </div>
          <Button asChild size="sm" className="shrink-0 self-start sm:self-center">
            <Link href={primary.href}>
              <span>{ACTION_CTA_LABEL[primary.type] ?? "Abrir"}</span>
              <ArrowRight className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
            </Link>
          </Button>
        </article>

        {secondary.length > 0 ? (
          <ul className="divide-y divide-[color:var(--border-subtle)] rounded-md border border-[color:var(--border-subtle)]">
            {secondary.map((action) => (
              <li
                key={action.id}
                className="flex flex-wrap items-center justify-between gap-3 px-3.5 py-2.5"
              >
                <div className="min-w-0 flex-1 space-y-0.5">
                  <p className="line-clamp-1 text-[13px] font-medium text-[color:var(--text-primary)]">
                    {action.title}
                  </p>
                  <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                    {action.requirement_code ?? action.period_key ?? "—"}
                  </p>
                </div>
                <Button asChild size="sm" variant="outline">
                  <Link href={action.href}>
                    <span>{ACTION_CTA_LABEL[action.type] ?? "Abrir"}</span>
                    <ArrowRight className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
                  </Link>
                </Button>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </section>
  );
}

// ─── Operational queues (Por atender / Vence pronto / Recibidos / Recientes) ──

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

function splitAttentionItems(items: DashboardAttentionItem[]): {
  actionable: DashboardAttentionItem[];
  dueSoon: DashboardAttentionItem[];
} {
  const actionable: DashboardAttentionItem[] = [];
  const dueSoon: DashboardAttentionItem[] = [];
  for (const row of items) {
    if (
      row.state === "rejected" ||
      row.state === "needs_correction" ||
      row.state === "possible_mismatch" ||
      row.state === "expired"
    ) {
      actionable.push(row);
    } else if (row.state === "missing") {
      dueSoon.push(row);
    }
  }
  return { actionable, dueSoon };
}

function OperationalQueues({
  attention,
  dueSoon,
  inReview,
  recent,
}: {
  attention: DashboardAttentionItem[];
  dueSoon: DashboardAttentionItem[];
  inReview: DashboardRecentUpload[];
  recent: DashboardRecentUpload[];
}) {
  return (
    <section
      aria-label="Estado operativo de tus documentos"
      className="grid gap-4 md:grid-cols-2"
    >
      <QueuePanel
        title="Por atender"
        icon={Warning}
        emptyTitle="Sin pendientes críticos"
        emptyDescription="No tienes documentos rechazados, vencidos o con observaciones."
        href={attention.length > 0 ? "/portal/onboarding" : undefined}
        rows={attention.slice(0, 5).map((row) => ({
          key: row.id,
          title: row.title,
          institution: INSTITUTION_LABEL[row.institution] ?? row.institution.toUpperCase(),
          state: SLOT_STATE_TO_DOC_CODE[row.state] ?? "pending",
          metaLine: formatDueLine(row.due_in_days),
          href: row.href,
        }))}
        totalCount={attention.length}
      />

      <QueuePanel
        title="Vence pronto"
        icon={CalendarBlank}
        emptyTitle="Sin vencimientos en 14 días"
        emptyDescription="Ningún documento obligatorio vence en las próximas dos semanas."
        href={dueSoon.length > 0 ? "/portal/calendar" : undefined}
        rows={dueSoon.slice(0, 5).map((row) => ({
          key: row.id,
          title: row.title,
          institution: INSTITUTION_LABEL[row.institution] ?? row.institution.toUpperCase(),
          state: "pending",
          metaLine: formatDueLine(row.due_in_days),
          href: row.href,
        }))}
        totalCount={dueSoon.length}
      />

      <QueuePanel
        title="En revisión"
        icon={HourglassHigh}
        emptyTitle="Sin documentos en cola"
        emptyDescription="No hay cargas esperando revisión legal en este momento."
        rows={inReview.map((row) => ({
          key: row.submission_id,
          title: row.requirement_name,
          institution:
            INSTITUTION_LABEL[row.institution] ??
            (row.institution ? row.institution.toUpperCase() : "—"),
          state: statusToDocumentStateCode(row.status as RequirementStatus),
          metaLine: formatSubmittedAt(row.submitted_at),
          href: row.href,
        }))}
        totalCount={inReview.length}
      />

      <QueuePanel
        title="Cargas recientes"
        icon={Tray}
        emptyTitle="Aún no has cargado documentos"
        emptyDescription="Cuando subas tu primer documento, aparecerá aquí con su estado."
        href={recent.length > 0 ? "/portal/submissions" : undefined}
        rows={recent.slice(0, 5).map((row) => ({
          key: row.submission_id,
          title: row.filename ?? row.requirement_name,
          institution:
            INSTITUTION_LABEL[row.institution] ??
            (row.institution ? row.institution.toUpperCase() : "—"),
          state: statusToDocumentStateCode(row.status as RequirementStatus),
          metaLine: formatSubmittedAt(row.submitted_at),
          href: row.href,
        }))}
        totalCount={recent.length}
      />
    </section>
  );
}

type QueueRow = {
  key: string;
  title: string;
  institution: string;
  state: DocumentStateCode;
  metaLine: string | null;
  href: string;
};

function QueuePanel({
  title,
  icon: IconComponent,
  rows,
  emptyTitle,
  emptyDescription,
  href,
  totalCount,
}: {
  title: string;
  icon: Icon;
  rows: QueueRow[];
  emptyTitle: string;
  emptyDescription: string;
  href?: string;
  totalCount: number;
}) {
  return (
    <article className="flex flex-col rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-xs">
      <header className="flex items-center justify-between gap-2 border-b border-[color:var(--border-subtle)] px-4 py-2.5">
        <div className="flex items-center gap-2">
          <IconComponent
            className="h-4 w-4 text-[color:var(--text-brand)]"
            weight="duotone"
            aria-hidden="true"
          />
          <h3 className="text-[12px] font-semibold uppercase tracking-wide text-[color:var(--text-primary)]">
            {title}
          </h3>
          <span className="font-mono text-[10px] tabular-nums text-[color:var(--text-tertiary)]">
            {totalCount}
          </span>
        </div>
        {href && totalCount > rows.length ? (
          <Link
            href={href}
            className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-link)] hover:underline"
          >
            Ver todo
          </Link>
        ) : null}
      </header>
      {rows.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-1 px-4 py-6 text-center">
          <p className="text-[13px] font-medium text-[color:var(--text-primary)]">
            {emptyTitle}
          </p>
          <p className="max-w-xs text-xs text-[color:var(--text-secondary)]">
            {emptyDescription}
          </p>
        </div>
      ) : (
        <ul className="divide-y divide-[color:var(--border-subtle)]">
          {rows.map((row) => (
            <li key={row.key}>
              <Link
                href={row.href}
                className="flex items-start justify-between gap-3 px-4 py-2.5 transition-colors hover:bg-[color:var(--surface-page)] focus-visible:bg-[color:var(--surface-page)] focus-visible:outline-none"
              >
                <div className="min-w-0 flex-1 space-y-0.5">
                  <p className="line-clamp-1 text-[13px] font-medium leading-tight text-[color:var(--text-primary)]">
                    {row.title}
                  </p>
                  <p className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                    <span>{row.institution}</span>
                    {row.metaLine ? (
                      <>
                        <span aria-hidden="true">·</span>
                        <span className="normal-case tracking-normal">
                          {row.metaLine}
                        </span>
                      </>
                    ) : null}
                  </p>
                </div>
                <DocStateBadge state={row.state} withIcon={false} className="shrink-0" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}

function formatDueLine(days: number | null | undefined): string | null {
  if (days === null || days === undefined) return null;
  if (days < 0) return `Vencido ${Math.abs(days)}d`;
  if (days === 0) return "Vence hoy";
  return `En ${days}d`;
}

function formatSubmittedAt(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const today = new Date();
  const diffMs = today.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  if (diffDays <= 0) return "Hoy";
  if (diffDays === 1) return "Ayer";
  if (diffDays < 7) return `Hace ${diffDays}d`;
  if (diffDays < 30) return `Hace ${Math.floor(diffDays / 7)} sem`;
  return date.toLocaleDateString("es-MX", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

// ─── Upcoming deadlines sidebar panel ─────────────────────────────

function UpcomingDeadlinesPanel({ rows }: { rows: DashboardUpcomingDeadline[] }) {
  return (
    <section
      aria-label="Próximos vencimientos"
      className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-xs"
    >
      <header className="flex items-center justify-between gap-2 border-b border-[color:var(--border-subtle)] px-4 py-2.5">
        <div className="flex items-center gap-2">
          <CalendarBlank
            className="h-4 w-4 text-[color:var(--text-brand)]"
            weight="duotone"
            aria-hidden="true"
          />
          <h3 className="text-[12px] font-semibold uppercase tracking-wide text-[color:var(--text-primary)]">
            Próximos vencimientos
          </h3>
        </div>
        <Link
          href="/portal/calendar"
          className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-link)] hover:underline"
        >
          Calendario
        </Link>
      </header>
      {rows.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-1 px-4 py-6 text-center">
          <CheckCircle
            className="h-5 w-5 text-[color:var(--status-success-text)]"
            weight="fill"
            aria-hidden="true"
          />
          <p className="text-[13px] font-medium text-[color:var(--text-primary)]">
            Sin vencimientos próximos
          </p>
          <p className="max-w-xs text-xs text-[color:var(--text-secondary)]">
            No tienes obligaciones próximas a vencer en los siguientes 30 días.
          </p>
        </div>
      ) : (
        <ul className="divide-y divide-[color:var(--border-subtle)]">
          {rows.map((row) => {
            const institutionLabel =
              INSTITUTION_LABEL[row.institution] ?? row.institution.toUpperCase();
            const due = row.due_in_days;
            const dueTone =
              due == null
                ? "neutral"
                : due <= 3
                  ? "error"
                  : due <= 7
                    ? "warning"
                    : "neutral";
            return (
              <li key={row.id}>
                <Link
                  href={row.href}
                  className="flex items-start justify-between gap-3 px-4 py-2.5 transition-colors hover:bg-[color:var(--surface-page)]"
                >
                  <div className="min-w-0 flex-1 space-y-0.5">
                    <p className="line-clamp-1 text-[13px] font-medium leading-tight text-[color:var(--text-primary)]">
                      {row.title}
                    </p>
                    <p className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                      <span>{institutionLabel}</span>
                      {row.period_key ? (
                        <>
                          <span aria-hidden="true">·</span>
                          <span>{row.period_key}</span>
                        </>
                      ) : null}
                    </p>
                  </div>
                  <span
                    className={cn(
                      "shrink-0 rounded-full px-2 py-0.5 font-mono text-[10px] tabular-nums",
                      dueTone === "error" &&
                        "bg-[color:var(--status-error-bg)] text-[color:var(--status-error-text)]",
                      dueTone === "warning" &&
                        "bg-[color:var(--status-warning-bg)] text-[color:var(--status-warning-text)]",
                      dueTone === "neutral" &&
                        "bg-[color:var(--surface-sunken)] text-[color:var(--text-secondary)]",
                    )}
                  >
                    {due == null
                      ? "—"
                      : due === 0
                        ? "Hoy"
                        : `${due}d`}
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

// ─── Compliance ledger (compact state counts, replaces donut) ─────

function ComplianceLedger({
  counts,
}: {
  counts: DashboardPayload["document_state_counts"];
}) {
  const entries: { state: DocumentStateCode; label: string; count: number }[] = useMemo(
    () => [
      { state: "approved", label: "Aprobados", count: counts.approved },
      { state: "in_review", label: "En revisión", count: counts.in_review },
      { state: "uploaded", label: "Recibidos", count: counts.uploaded },
      { state: "needs_review", label: "Necesitan acción", count: counts.needs_review },
      { state: "rejected", label: "Rechazados", count: counts.rejected },
      { state: "expired", label: "Vencidos", count: counts.expired },
      { state: "pending", label: "Pendientes", count: counts.pending },
    ],
    [counts],
  );
  const total = entries.reduce((sum, row) => sum + row.count, 0);

  return (
    <section
      aria-label="Resumen por estado"
      className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-xs"
    >
      <header className="flex items-center justify-between gap-2 border-b border-[color:var(--border-subtle)] px-4 py-2.5">
        <div className="flex items-center gap-2">
          <FileMagnifyingGlass
            className="h-4 w-4 text-[color:var(--text-brand)]"
            weight="duotone"
            aria-hidden="true"
          />
          <h3 className="text-[12px] font-semibold uppercase tracking-wide text-[color:var(--text-primary)]">
            Resumen por estado
          </h3>
        </div>
        <span className="font-mono text-[10px] tabular-nums text-[color:var(--text-tertiary)]">
          {total} {total === 1 ? "doc" : "docs"}
        </span>
      </header>
      <ul className="divide-y divide-[color:var(--border-subtle)]">
        {entries.map((row) => (
          <li
            key={row.state}
            className="flex items-center justify-between gap-3 px-4 py-2"
          >
            <DocStateBadge state={row.state} label={row.label} withIcon={false} />
            <span className="font-mono text-[13px] font-semibold tabular-nums text-[color:var(--text-primary)]">
              {row.count}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

// ─── Locked / provisional banners ────────────────────────────────

function LockedDashboardBanner({
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

