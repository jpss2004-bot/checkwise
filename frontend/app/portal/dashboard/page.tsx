"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  CalendarBlank,
  CheckCircle,
  ClipboardText,
  CloudArrowUp,
  HourglassHigh,
  LockKey,
  Sparkle,
  Warning,
  WarningOctagon,
  type Icon,
} from "@phosphor-icons/react";

import { Donut, RadialGauge, StackedBars, type ChartSegment } from "@/components/checkwise/charts";
import {
  EmptyState,
  Surface,
} from "@/components/checkwise/dashboard/stat-card";
import { DocStateBadge } from "@/components/checkwise/doc-state-badge";
import { EvidenceSlotGrid } from "@/components/checkwise/portal/evidence-slot-grid";
import {
  NextActionRail,
  type NextActionItem,
  type NextActionPriority,
} from "@/components/checkwise/portal/next-action-rail";
import { PortalAppShell } from "@/components/checkwise/portal/portal-app-shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import type { EvidenceSlotCardProps } from "@/components/checkwise/portal/evidence-slot-card";
import {
  getDashboard,
  type DashboardAttentionItem,
  type DashboardOnboardingSummary,
  type DashboardPayload,
  type DashboardSemaphore,
  type DashboardSemaphoreLevel,
  type DashboardSuggestedAction,
  type DashboardUpcomingDeadline,
} from "@/lib/api/portal";
import { withOnboardingGate } from "@/lib/session/with-onboarding-gate";
import type { PortalSession } from "@/lib/session/portal";
import type { DocumentStateCode } from "@/lib/types";

/**
 * Provider dashboard — sidebar-shelled command center.
 *
 * The dashboard reads ``GET /api/v1/portal/workspaces/{id}/dashboard``
 * and presents the four buckets a vendor cares about in priority
 * order:
 *
 *   1. Semaphore hero — a radial gauge on the compliance %, with a
 *      one-line plain-language status and an inline distribution
 *      breakdown.
 *   2. KPI strip — pending actions, in-review, approved this period,
 *      next deadline. Each card is hoverable / linkable.
 *   3. Suggested actions rail — unchanged.
 *   4. Attention list + side rail with mini calendar + upcoming
 *      deadlines and a document-state donut.
 *
 * Animations: cw-stagger on the KPI strip and section blocks so the
 * surface "lights up" gently on mount.
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
        <main className="mx-auto max-w-7xl space-y-6 px-5 py-8">
          <DashboardSkeleton />
        </main>
      </PortalAppShell>
    );
  }

  const onboarding = dashboard.onboarding_summary;
  const gateBlocked = onboarding.needs_action > 0;
  const provisional = !gateBlocked && onboarding.in_review > 0;

  return (
    <PortalAppShell session={session} onboardingPct={onboardingPct}>
      <main className="mx-auto max-w-7xl space-y-6 px-5 py-6 md:px-7">
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

        <WorkspaceMetadataStrip
          summary={onboarding}
          counts={dashboard.document_state_counts}
          nextDeadline={dashboard.upcoming_deadlines[0] ?? null}
          rfc={session.vendor_rfc}
          personaType={session.persona_type}
        />

        {gateBlocked ? <LockedDashboardHero summary={onboarding} /> : null}
        {provisional ? <ProvisionalAccessBanner /> : null}

        <SemaphoreHero
          semaphore={dashboard.semaphore}
          counts={dashboard.document_state_counts}
        />

        <NextActionRail
          actions={toNextActionItems(dashboard.suggested_actions)}
          emptyState={{
            title: "Estás al día",
            description: "No hay acciones urgentes para tu workspace en este momento.",
          }}
        />

        <ExpedienteSummaryCard summary={onboarding} />

        <div className="cw-stagger grid gap-5 lg:grid-cols-3">
          <div className="space-y-5 lg:col-span-2">
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
          <div className="space-y-5">
            <CalendarTeaser />
            <UpcomingCard rows={dashboard.upcoming_deadlines} />
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
    <div className="space-y-6">
      <div className="h-24 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]" />
      <div className="h-40 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]" />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div
            key={i}
            className="h-28 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]"
          />
        ))}
      </div>
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <div className="h-56 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]" />
          <div className="h-56 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]" />
        </div>
        <div className="space-y-6">
          <div className="h-40 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]" />
          <div className="h-40 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]" />
        </div>
      </div>
    </div>
  );
}

// ─── Semaphore hero (with radial gauge + distribution) ───────────

const TONE_TO_ICON: Record<DashboardSemaphoreLevel, Icon> = {
  green: CheckCircle,
  yellow: Warning,
  red: WarningOctagon,
};

const TONE_TO_HERO_BG: Record<DashboardSemaphoreLevel, string> = {
  green: "border-[color:var(--status-success-border)]",
  yellow: "border-[color:var(--status-warning-border)]",
  red: "border-[color:var(--status-error-border)]",
};

const TONE_TO_ACCENT: Record<
  DashboardSemaphoreLevel,
  "success" | "warning" | "error"
> = {
  green: "success",
  yellow: "warning",
  red: "error",
};

function SemaphoreHero({
  semaphore,
  counts,
}: {
  semaphore: DashboardSemaphore;
  counts: DashboardPayload["document_state_counts"];
}) {
  const IconComponent = TONE_TO_ICON[semaphore.level];
  const accent = TONE_TO_ACCENT[semaphore.level];
  const segments: ChartSegment[] = [
    { label: "Aprobados", value: counts.approved, tone: "success" },
    { label: "En revisión", value: counts.in_review + counts.uploaded, tone: "info" },
    { label: "Por atender", value: counts.needs_review + counts.rejected, tone: "warning" },
    { label: "Pendientes", value: counts.pending, tone: "neutral" },
    { label: "Vencidos", value: counts.expired, tone: "error" },
  ];
  return (
    <section
      className={`cw-fade-up rounded-lg border bg-[color:var(--surface-raised)] shadow-xs ${TONE_TO_HERO_BG[semaphore.level]}`}
      aria-label="Estado de cumplimiento"
    >
      <div className="grid gap-6 p-6 md:grid-cols-[auto,1fr] md:items-center md:p-8">
        <div className="flex items-center justify-center md:justify-start">
          <RadialGauge
            value={semaphore.compliance_pct}
            tone={accent}
            size={148}
            thickness={12}
            label={`${Math.round(semaphore.compliance_pct)}%`}
            caption="cumplimiento"
          />
        </div>
        <div className="min-w-0 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={accent === "success" ? "success" : accent === "warning" ? "warning" : "destructive"} className="inline-flex items-center gap-1">
              <IconComponent className="h-3 w-3" weight="fill" aria-hidden="true" />
              {semaphore.label}
            </Badge>
            <span className="font-mono text-[11px] text-[color:var(--text-tertiary)]">
              {semaphore.on_track} de {semaphore.total_tracked} obligaciones al día
            </span>
          </div>
          <p className="text-[15px] leading-relaxed text-[color:var(--text-primary)]">
            {semaphore.reason}
          </p>
          <StackedBars segments={segments} height={12} />
        </div>
      </div>
    </section>
  );
}

// ─── Workspace metadata strip ────────────────────────────────────
//
// 2.x direction: replaces the previous 4-up KPI card grid (AUDIT F2 —
// identical card grids). The same 4 signals — workspace identity,
// pending-action count, in-review count, next deadline — render as a
// single horizontal label/value strip below the page header. The
// dense composition matches the V2.0 hero's monospace metadata
// signature and removes one cliché SaaS pattern from the surface.

function WorkspaceMetadataStrip({
  summary,
  counts,
  nextDeadline,
  rfc,
  personaType,
}: {
  summary: DashboardOnboardingSummary;
  counts: DashboardPayload["document_state_counts"];
  nextDeadline: DashboardUpcomingDeadline | null;
  rfc: string;
  personaType: PortalSession["persona_type"];
}) {
  const deadlineLabel = nextDeadline
    ? `${INSTITUTION_LABEL[nextDeadline.institution] ?? nextDeadline.institution} · ${nextDeadline.period_key ?? ""}`
    : "Sin vencimientos próximos";

  return (
    <div className="cw-metadata-strip cw-fade-up border-t border-b border-[color:var(--border-subtle)] py-3">
      <div>
        <span className="cw-eyebrow">RFC</span>
        <span className="font-mono text-[13px] text-[color:var(--text-primary)]">{rfc}</span>
      </div>
      <div>
        <span className="cw-eyebrow">Persona</span>
        <span className="text-[13px] text-[color:var(--text-primary)]">
          {personaType === "moral" ? "Moral" : "Física"}
        </span>
      </div>
      <div>
        <span className="cw-eyebrow">Por atender</span>
        <span
          className={`font-mono text-[13px] font-semibold tabular-nums ${
            summary.needs_action > 0
              ? "text-[color:var(--status-warning-text)]"
              : "text-[color:var(--status-success-text)]"
          }`}
        >
          {summary.needs_action}
        </span>
      </div>
      <div>
        <span className="cw-eyebrow">En revisión</span>
        <span className="font-mono text-[13px] tabular-nums text-[color:var(--text-primary)]">
          {summary.in_review}
        </span>
      </div>
      <div>
        <span className="cw-eyebrow">Aprobados</span>
        <span className="font-mono text-[13px] tabular-nums text-[color:var(--status-success-text)]">
          {counts.approved}
        </span>
      </div>
      <div>
        <span className="cw-eyebrow">Próximo</span>
        {nextDeadline?.href ? (
          <Link
            href={nextDeadline.href}
            className="text-[13px] text-[color:var(--text-primary)] hover:underline"
          >
            {deadlineLabel}
          </Link>
        ) : (
          <span className="text-[13px] text-[color:var(--text-tertiary)]">{deadlineLabel}</span>
        )}
      </div>
    </div>
  );
}

// ─── Adapters ────────────────────────────────────────────────────

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

const ACTION_PRIORITY_MAP: Record<
  DashboardSuggestedAction["priority"],
  NextActionPriority
> = {
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

// ─── Expediente summary ──────────────────────────────────────────

function ExpedienteSummaryCard({
  summary,
}: {
  summary: DashboardOnboardingSummary;
}) {
  const segments: ChartSegment[] = [
    { label: "Aprobados", value: summary.completed, tone: "success" },
    { label: "En revisión", value: summary.in_review, tone: "info" },
    { label: "Por atender", value: summary.needs_action, tone: "warning" },
    {
      label: "Sin iniciar",
      value: Math.max(
        0,
        summary.total_required -
          summary.completed -
          summary.in_review -
          summary.needs_action,
      ),
      tone: "neutral",
    },
  ];
  return (
    <Surface
      title="Tu expediente inicial"
      icon={ClipboardText}
      actions={
        <>
          <Badge variant="brand">{summary.completion_pct}%</Badge>
          <Button asChild variant="outline" size="sm">
            <Link href="/portal/onboarding">
              <span>Revisar</span>
              <ArrowRight className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
            </Link>
          </Button>
        </>
      }
    >
      <p className="mb-3 text-[13px] text-[color:var(--text-secondary)]">
        {summary.completed + summary.in_review} de {summary.total_required}{" "}
        documentos obligatorios avanzados.
      </p>
      <StackedBars segments={segments} height={14} />
    </Surface>
  );
}

// ─── Locked hero ─────────────────────────────────────────────────

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

// ─── Institution labels ──────────────────────────────────────────

const INSTITUTION_LABEL: Record<string, string> = {
  sat: "SAT",
  imss: "IMSS",
  infonavit: "INFONAVIT",
  stps_repse: "STPS / REPSE",
  interno_cliente: "Interno / Cliente",
};

// ─── Document state overview (donut) ─────────────────────────────

function DocumentStateOverview({
  counts,
}: {
  counts: DashboardPayload["document_state_counts"];
}) {
  const all: ChartSegment[] = [
    { label: "Aprobados", value: counts.approved, tone: "success" },
    { label: "En revisión", value: counts.in_review, tone: "info" },
    { label: "Recibidos", value: counts.uploaded, tone: "info" },
    { label: "Necesitan acción", value: counts.needs_review, tone: "warning" },
    { label: "Rechazados", value: counts.rejected, tone: "error" },
    { label: "Pendientes", value: counts.pending, tone: "neutral" },
    { label: "Vencidos", value: counts.expired, tone: "error" },
  ];
  const segments: ChartSegment[] = all.filter((s) => s.value > 0);
  const total = segments.reduce((sum, s) => sum + s.value, 0);

  if (total === 0) {
    return (
      <Surface title="Resumen por estado">
        <EmptyState
          icon={Sparkle}
          title="Aún no hay documentos cargados"
          description="Cuando subas tu primer documento, aquí verás el desglose por estado."
        />
      </Surface>
    );
  }

  // Render a flat row of badges below the donut so the legend works
  // even when the user wants to click a specific state.
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
    <Surface
      title="Resumen por estado"
      description="Distribución de todos los documentos cargados hasta hoy."
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
        <Donut
          segments={segments}
          size={132}
          thickness={14}
          centerLabel={total}
          centerCaption="documentos"
          showLegend={false}
        />
        <ul className="grid flex-1 grid-cols-2 gap-2 sm:grid-cols-3">
          {entries.map(({ state, count }) => (
            <li
              key={state}
              className="flex items-center justify-between gap-2 rounded-sm border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] px-2.5 py-2"
            >
              <DocStateBadge state={state} withIcon={false} />
              <span className="font-mono text-sm font-semibold tabular-nums text-[color:var(--text-primary)]">
                {count}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </Surface>
  );
}

// ─── Calendar teaser ─────────────────────────────────────────────

function CalendarTeaser() {
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
    <Surface
      title="Calendario REPSE"
      icon={CalendarBlank}
      actions={
        <Badge variant="brand">{new Date().getFullYear()}</Badge>
      }
    >
      <div className="grid grid-cols-6 gap-1.5">
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
              className={`flex flex-col items-center justify-center rounded-sm border px-1 py-2 text-center ${tone}`}
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
    </Surface>
  );
}

// ─── Upcoming card ───────────────────────────────────────────────

function UpcomingCard({ rows }: { rows: DashboardUpcomingDeadline[] }) {
  if (rows.length === 0) {
    return (
      <Surface title="Próximos vencimientos">
        <EmptyState
          icon={CheckCircle}
          title="Sin vencimientos próximos"
          description="No tienes obligaciones próximas a vencer en los siguientes 30 días."
        />
      </Surface>
    );
  }
  return (
    <Surface title="Próximos vencimientos">
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
              <ArrowRight
                className="mt-1 h-3.5 w-3.5 text-[color:var(--text-tertiary)]"
                weight="bold"
                aria-hidden="true"
              />
            </li>
          );
        })}
      </ul>
    </Surface>
  );
}
