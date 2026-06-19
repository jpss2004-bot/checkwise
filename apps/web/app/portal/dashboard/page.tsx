"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Bank,
  CalendarBlank,
  CheckCircle,
  CloudArrowUp,
  DownloadSimple,
  FileMagnifyingGlass,
  HourglassHigh,
  Lightning,
  LockKey,
  Tray,
  TrendUp,
  Warning,
  WarningOctagon,
  type Icon,
} from "@phosphor-icons/react";

import {
  Donut,
  MiniBars,
  RadialGauge,
  Sparkline,
  StackedBars,
  type ChartSegment,
  type ChartTone,
} from "@/components/checkwise/charts";
import { DocStateBadge } from "@/components/checkwise/doc-state-badge";
import { EmptyExpedienteHero } from "@/components/checkwise/portal/empty-expediente-hero";
import { PortalAppShell } from "@/components/checkwise/portal/portal-app-shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { MetadataStrip, type MetadataItem } from "@/components/ui/metadata-strip";
import { PageHeader } from "@/components/ui/page-header";
import { Select } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import {
  expedienteZipUrl,
  getDashboard,
  getOnboarding,
  statusToDocumentStateCode,
  type DashboardInstitutionBreakdown,
  type DashboardOnboardingSummary,
  type DashboardPayload,
  type DashboardRecentUpload,
  type DashboardSemaphore,
  type DashboardSemaphoreLevel,
  type DashboardSuggestedAction,
  type DashboardUpcomingDeadline,
  type OnboardingSummary,
  type RequirementStatus,
} from "@/lib/api/portal";
import { bucketLabel, statusLabel } from "@/lib/constants/statuses";
import { withOnboardingGate } from "@/lib/session/with-onboarding-gate";
import type { PortalSession } from "@/lib/session/portal";
import type { DocumentStateCode } from "@/lib/types";

/**
 * Provider dashboard — visual REPSE compliance command center.
 *
 * Session 5 (2026-05-21) doubled-down on at-a-glance visuals after
 * Session 4's compact rewrite read as "operational but joyless." The
 * surface now layers:
 *
 *   1. A hero block — large radial gauge on the left (compliance %
 *      with stacked-distribution bar underneath), single dominant
 *      next-action card on the right. The two answer "where am I"
 *      and "what do I do" before the user scrolls.
 *   2. A 4-up KPI strip with mini sparklines derived from the
 *      14-day upload window — "Por atender", "En revisión",
 *      "Aprobados", "Próximo vencimiento".
 *   3. A graph row — 14-day upload-activity MiniBars chart on the
 *      left, per-institution stacked-bar breakdown on the right.
 *   4. The operational queues from Session 4 (Por atender / Vence
 *      pronto / En revisión / Cargas recientes) plus the right-rail
 *      upcoming-deadlines + state donut.
 *
 * Every chart is bound to the existing backend payload (semaphore,
 * document_state_counts, recent_uploads, institution_breakdown,
 * upcoming_deadlines) plus the new derived 14-day per-day series
 * computed from recent_uploads. No invented metrics.
 */
function DashboardInner({ session }: { session: PortalSession }) {
  const [dashboard, setDashboard] = useState<DashboardPayload | null>(null);
  const [onboardingPayload, setOnboardingPayload] = useState<OnboardingSummary | null>(
    null,
  );
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    // Fetch dashboard + onboarding independently so the dashboard renders the
    // instant its own payload lands — it must not wait on the secondary
    // onboarding fetch. The onboarding payload only powers the empty-state
    // hero's "first 5 documents" checklist and the Wise dock's net-new welcome
    // line, and failing it is non-fatal (the dashboard renders without the
    // checklist), so it streams in on its own.
    getDashboard(session)
      .then((dash) => {
        if (cancelled) return;
        setDashboard(dash);
        setLoadError(false);
      })
      .catch(() => {
        if (cancelled) return;
        setLoadError(true);
      });
    getOnboarding(session)
      .then((onboarding) => {
        if (!cancelled) setOnboardingPayload(onboarding);
      })
      .catch((err) => {
        // Non-fatal, but don't swallow it silently — a recurring failure here
        // means the empty-state checklist degrades with no signal (audit
        // 2026-06-09). Dev-only so the prod console stays clean (2026-06-12).
        if (process.env.NODE_ENV !== "production") {
          console.warn("[portal/dashboard] onboarding fetch failed:", err);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [session]);

  const onboardingPct = dashboard?.onboarding_summary.completion_pct ?? null;
  // ``useMemo14DayActivity`` is a hook — it must run unconditionally on
  // every render. We compute it from the (possibly null) payload's
  // ``recent_uploads`` so the early returns below can stay simple
  // without violating the rules of hooks.
  const uploadActivity = useMemo14DayActivity(dashboard?.recent_uploads ?? []);

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
  const initialOnboardingDone = session.onboarding_completed_at !== null;
  const gateBlocked = !initialOnboardingDone && onboarding.needs_action > 0;
  const provisional =
    !gateBlocked && onboarding.in_review > 0 && !initialOnboardingDone;

  const counts = dashboard.document_state_counts;
  const recent = dashboard.recent_uploads ?? [];
  const institutionBreakdown = dashboard.institution_breakdown ?? [];

  const attentionRows = splitAttentionItems(dashboard.attention_today);
  const inReviewRows = recent
    .filter((row) => {
      const code = statusToDocumentStateCode(row.status as RequirementStatus);
      return code === "in_review" || code === "uploaded";
    })
    .slice(0, 5);

  const primaryAction = dashboard.suggested_actions[0] ?? null;
  const secondaryActions = dashboard.suggested_actions.slice(1, 4);

  // Wise Phase 1 (2026-05-21) — until the provider has completed the
  // initial expediente, replace the chart-rich layout with the
  // guided checklist hero. Charts of mostly-zero data read as broken
  // to a brand-new vendor; the checklist gives them a concrete
  // first move. The Wise dock lives at the PortalAppShell level
  // (Phase 4) so it follows the user across every portal page —
  // we no longer mount it from inside the dashboard.

  const header = (
    <PageHeader
      eyebrow="Centro de cumplimiento"
      title={session.vendor_name}
      description="Lo que falta, lo que está en revisión y la próxima acción concreta para mantener tu cumplimiento al día."
      actions={
        <>
          {/* Phase 5 / Slice 5C — Descargar expediente with filter
              modal. The button opens an in-dialog filter set
              (institución / periodo / estado); all three default to
              "Todo". Submit opens the filtered ZIP URL in a new
              tab so cookie auth carries on the top-level
              navigation. Slice 5B's plain anchor was replaced
              because the dashboard is the natural surface for
              "give me everything OR a scoped slice". */}
          <ExpedienteDownloadDialog session={session} />
          <Button asChild size="sm">
            <Link href="/portal/upload">
              <CloudArrowUp
                className="h-4 w-4"
                weight="bold"
                aria-hidden="true"
              />
              Subir documento
            </Link>
          </Button>
        </>
      }
    />
  );

  const metadata = (
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
  );

  if (!initialOnboardingDone) {
    return (
      <PortalAppShell session={session} onboardingPct={onboardingPct}>
        <main className="mx-auto max-w-5xl space-y-5 px-5 py-6 md:px-7">
          {header}
          {metadata}
          {gateBlocked ? <LockedDashboardBanner summary={onboarding} /> : null}
          {provisional ? <ProvisionalAccessBanner /> : null}
          <EmptyExpedienteHero
            vendorName={session.vendor_name}
            summary={onboarding}
            semaphore={dashboard.semaphore}
            onboarding={onboardingPayload}
          />
        </main>
      </PortalAppShell>
    );
  }

  return (
    <PortalAppShell session={session} onboardingPct={onboardingPct}>
      <main className="mx-auto max-w-7xl space-y-5 px-5 py-6 md:px-7">
        {header}
        {metadata}

        {gateBlocked ? <LockedDashboardBanner summary={onboarding} /> : null}
        {provisional ? <ProvisionalAccessBanner /> : null}

        {/* ── Hero block: gauge + primary action ── */}
        <section className="cw-stagger grid gap-5 lg:grid-cols-12">
          <ComplianceHeroCard
            semaphore={dashboard.semaphore}
            counts={counts}
            summary={onboarding}
            className="lg:col-span-8"
          />
          <NextActionHero
            primary={primaryAction}
            secondary={secondaryActions}
            totalActions={dashboard.suggested_actions.length}
            className="lg:col-span-4"
          />
        </section>

        {/* ── KPI strip: 4 cards with sparklines ── */}
        <section
          aria-label="Indicadores clave"
          className="cw-stagger grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
        >
          {/* "Por atender" is a backlog COUNT (needs_action + expired),
              not a 14-day upload pulse, so it intentionally omits a
              sparkline — pairing the backlog headline with the
              upload-activity trend measured two different populations
              and read as a contradiction (audit 2026-06-18). */}
          <KpiCard
            label="Por atender"
            value={onboarding.needs_action + counts.expired}
            tone={onboarding.needs_action + counts.expired > 0 ? "warning" : "success"}
            icon={Warning}
            sparkData={[]}
            caption={
              onboarding.needs_action + counts.expired > 0
                ? "Documentos que necesitan tu acción"
                : "Sin pendientes críticos"
            }
          />
          <KpiCard
            label={bucketLabel("pending_reviews")}
            value={onboarding.in_review}
            tone="info"
            icon={HourglassHigh}
            sparkData={uploadActivity.byBucketReview}
            caption="Esperando revisión legal"
          />
          <KpiCard
            label="Aprobados"
            value={counts.approved}
            tone="success"
            icon={CheckCircle}
            sparkData={uploadActivity.byBucketApproved}
            caption="Obligaciones al día"
          />
          <KpiDeadlineCard deadline={dashboard.upcoming_deadlines[0] ?? null} />
        </section>

        {/* ── Graph row: activity + institution ── */}
        <section className="cw-stagger grid gap-5 lg:grid-cols-12">
          <UploadActivityCard activity={uploadActivity} className="lg:col-span-8" />
          <InstitutionBreakdownCard
            rows={institutionBreakdown}
            className="lg:col-span-4"
          />
        </section>

        {/* ── Operational queues + right rail ── */}
        <section className="cw-stagger grid gap-5 lg:grid-cols-12">
          <div className="space-y-5 lg:col-span-8">
            <OperationalQueues
              attention={attentionRows.actionable}
              dueSoon={attentionRows.dueSoon}
              inReview={inReviewRows}
              recent={recent}
            />
          </div>
          <div className="space-y-5 lg:col-span-4">
            <UpcomingDeadlinesPanel rows={dashboard.upcoming_deadlines} />
            <ComplianceDonut counts={counts} />
          </div>
        </section>
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
      <div className="grid gap-5 lg:grid-cols-12">
        <div className="h-64 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] lg:col-span-8" />
        <div className="h-64 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] lg:col-span-4" />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div
            key={i}
            className="h-28 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]"
          />
        ))}
      </div>
      <div className="grid gap-5 lg:grid-cols-12">
        <div className="h-64 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] lg:col-span-8" />
        <div className="h-64 animate-pulse rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] lg:col-span-4" />
      </div>
    </div>
  );
}

// ─── Constants / helpers ──────────────────────────────────────────

const INSTITUTION_LABEL: Record<string, string> = {
  sat: "SAT",
  imss: "IMSS",
  infonavit: "INFONAVIT",
  stps_repse: "STPS / REPSE",
  interno_cliente: "Interno",
};

const TONE_TO_ICON: Record<DashboardSemaphoreLevel, Icon> = {
  green: CheckCircle,
  yellow: Warning,
  red: WarningOctagon,
};

const TONE_TO_HERO_GRADIENT: Record<DashboardSemaphoreLevel, string> = {
  green:
    "from-[color:var(--status-success-bg)] via-transparent to-[color:var(--surface-teal-muted)]",
  yellow:
    "from-[color:var(--status-warning-bg)] via-transparent to-[color:var(--surface-brand-muted)]",
  red:
    "from-[color:var(--status-error-bg)] via-transparent to-[color:var(--surface-brand-muted)]",
};

const TONE_TO_BORDER: Record<DashboardSemaphoreLevel, string> = {
  green: "border-[color:var(--status-success-border)]",
  yellow: "border-[color:var(--status-warning-border)]",
  red: "border-[color:var(--status-error-border)]",
};

const TONE_TO_GAUGE: Record<DashboardSemaphoreLevel, ChartTone> = {
  green: "success",
  yellow: "warning",
  red: "error",
};

const TONE_TO_BADGE: Record<DashboardSemaphoreLevel, "success" | "warning" | "destructive"> = {
  green: "success",
  yellow: "warning",
  red: "destructive",
};

// ─── Metadata strip items ─────────────────────────────────────────

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
      tone: semaphore.level === "green" ? "default" : "warning",
    },
    {
      label: "Por atender",
      value: summary.needs_action,
      mono: true,
      tone: summary.needs_action > 0 ? "warning" : "default",
    },
    { label: bucketLabel("pending_reviews"), value: summary.in_review, mono: true },
    { label: "Aprobados", value: counts.approved, mono: true },
    { label: "Próximo", value: deadlineLabel },
  ];
}

// ─── Hero: compliance gauge + distribution ────────────────────────

function ComplianceHeroCard({
  semaphore,
  counts,
  summary,
  className,
}: {
  semaphore: DashboardSemaphore;
  counts: DashboardPayload["document_state_counts"];
  summary: DashboardOnboardingSummary;
  className?: string;
}) {
  const IconComponent = TONE_TO_ICON[semaphore.level];
  const segments: ChartSegment[] = [
    { label: "Aprobados", value: counts.approved, tone: "success" },
    { label: bucketLabel("pending_reviews"), value: counts.in_review + counts.uploaded, tone: "info" },
    {
      label: "Necesitan acción",
      value: counts.needs_review + counts.rejected + counts.expired,
      tone: "warning",
    },
    { label: "Pendientes", value: counts.pending, tone: "neutral" },
  ];
  return (
    <section
      className={cn(
        "cw-fade-up relative overflow-hidden rounded-lg border bg-[color:var(--surface-raised)] shadow-sm",
        TONE_TO_BORDER[semaphore.level],
        className,
      )}
      aria-label="Estado de cumplimiento"
    >
      {/* Decorative gradient + grid ornament. Visual only — keeps the
          hero from reading as a flat card without introducing data
          the user has to parse. */}
      <div
        aria-hidden="true"
        className={cn(
          "pointer-events-none absolute inset-0 bg-gradient-to-br opacity-60",
          TONE_TO_HERO_GRADIENT[semaphore.level],
        )}
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -right-16 -top-16 h-56 w-56 rounded-full bg-[color:var(--surface-teal-muted)] opacity-40 blur-3xl"
      />
      <div className="pointer-events-none absolute inset-0 cw-grid-pattern opacity-30" aria-hidden="true" />

      <div className="relative grid gap-6 p-6 md:grid-cols-[auto,1fr] md:items-center md:p-8">
        <div className="flex flex-col items-center gap-3 md:items-start">
          <RadialGauge
            value={semaphore.compliance_pct}
            tone={TONE_TO_GAUGE[semaphore.level]}
            size={172}
            thickness={14}
            label={`${Math.round(semaphore.compliance_pct)}%`}
            caption="cumplimiento"
          />
          <div className="flex items-center gap-2 font-mono text-[11px] text-[color:var(--text-tertiary)]">
            <span className="tabular-nums text-[color:var(--text-primary)]">
              {semaphore.on_track}
            </span>
            <span>/</span>
            <span className="tabular-nums">{semaphore.total_tracked}</span>
            <span className="uppercase tracking-wide">obligaciones al día</span>
          </div>
        </div>

        <div className="min-w-0 space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={TONE_TO_BADGE[semaphore.level]} className="inline-flex items-center gap-1">
              <IconComponent className="h-3 w-3" weight="fill" aria-hidden="true" />
              {semaphore.label}
            </Badge>
            <span className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
              Periodo {new Date().getFullYear()}
            </span>
          </div>
          <p className={cn("text-[15px] leading-relaxed text-[color:var(--text-primary)]")}>
            {semaphore.reason}
          </p>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <MiniStat
              label="Obligatorios"
              value={summary.total_required}
              tone="neutral"
            />
            <MiniStat
              label="Completados"
              value={summary.completed}
              tone="success"
            />
            <MiniStat
              label={bucketLabel("pending_reviews")}
              value={summary.in_review}
              tone="info"
            />
            <MiniStat
              label="Por atender"
              value={summary.needs_action}
              tone={summary.needs_action > 0 ? "warning" : "neutral"}
            />
          </div>

          <div>
            <StackedBars segments={segments} height={10} showLegend={false} />
            <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
              {segments.map((seg) => (
                <li key={seg.label} className="flex items-center gap-1.5">
                  <span
                    aria-hidden="true"
                    className="h-2 w-2 rounded-full"
                    style={{ background: toneToCssVar(seg.tone) }}
                  />
                  <span>{seg.label}</span>
                  <span className="text-[color:var(--text-primary)]">{seg.value}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}

function MiniStat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "neutral" | "success" | "info" | "warning";
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
    <div className="rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)]/70 px-3 py-2 backdrop-blur-sm">
      <p className="font-mono text-[9px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
        {label}
      </p>
      <p className={cn("mt-0.5 font-mono text-xl font-semibold tabular-nums leading-none", accent)}>
        {value}
      </p>
    </div>
  );
}

function toneToCssVar(tone: ChartSegment["tone"]): string {
  switch (tone) {
    case "success":
      return "var(--status-success-text)";
    case "warning":
      return "var(--status-warning-text)";
    case "error":
      return "var(--status-error-text)";
    case "info":
      return "var(--status-info-text)";
    case "teal":
      return "var(--text-teal)";
    case "brand":
      return "var(--text-brand)";
    default:
      return "var(--text-tertiary)";
  }
}

// ─── Hero: next action ────────────────────────────────────────────

const ACTION_CTA_LABEL: Record<DashboardSuggestedAction["type"], string> = {
  reupload: "Corregir carga",
  clarify: "Responder observación",
  verify_mismatch: "Verificar documento",
  complete_onboarding: "Subir documento",
  upcoming: "Subir documento",
  regularize: "Regularizar",
};

function NextActionHero({
  primary,
  secondary,
  totalActions,
  className,
}: {
  primary: DashboardSuggestedAction | null;
  secondary: DashboardSuggestedAction[];
  totalActions: number;
  className?: string;
}) {
  if (!primary) {
    return (
      <section
        aria-label="Sin acciones pendientes"
        className={cn(
          "cw-fade-up relative flex flex-col items-center justify-center overflow-hidden rounded-lg border border-[color:var(--status-success-border)] bg-[color:var(--surface-raised)] p-6 text-center shadow-sm",
          className,
        )}
      >
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 bg-gradient-to-br from-[color:var(--status-success-bg)] to-transparent opacity-50"
        />
        <span
          className="relative inline-flex h-12 w-12 items-center justify-center rounded-full bg-[color:var(--status-success-bg)] text-[color:var(--status-success-text)]"
          aria-hidden="true"
        >
          <Lightning className="h-6 w-6" weight="fill" />
        </span>
        <h2 className="relative mt-3 text-[15px] font-semibold text-[color:var(--text-primary)]">
          Estás al día
        </h2>
        <p className="relative mt-1 max-w-xs text-xs text-[color:var(--text-secondary)]">
          No hay acciones urgentes para tu expediente en este momento.
        </p>
      </section>
    );
  }

  const priorityDot =
    primary.priority === "high"
      ? "bg-[color:var(--status-error-text)]"
      : primary.priority === "medium"
        ? "bg-[color:var(--status-warning-text)]"
        : "bg-[color:var(--status-info-text)]";

  return (
    <section
      aria-label="Próxima acción"
      className={cn(
        "cw-fade-up relative flex flex-col overflow-hidden rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-brand)] text-[color:var(--surface-raised)] shadow-md",
        className,
      )}
    >
      {/* Decorative blur disc + teal accent so the hero CTA reads as
          the brand "Wise" moment rather than a generic dark card. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -right-12 -top-12 h-48 w-48 rounded-full bg-[color:var(--brand-teal-light,#5eead4)] opacity-20 blur-3xl"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -bottom-16 -left-12 h-40 w-40 rounded-full bg-[color:var(--text-teal)] opacity-10 blur-3xl"
      />

      <header className="relative flex items-center justify-between gap-2 border-b border-white/10 px-5 py-3">
        <div className="flex items-center gap-2">
          <Lightning className="h-4 w-4 text-[color:var(--text-teal)]" weight="fill" aria-hidden="true" />
          <h2 className="text-[12px] font-semibold uppercase tracking-wide text-white/90">
            Tu siguiente acción
          </h2>
        </div>
        <span className="font-mono text-[10px] tabular-nums text-white/60">
          {totalActions} {totalActions === 1 ? "tarea" : "tareas"}
        </span>
      </header>

      <div className="relative flex flex-1 flex-col gap-3 p-5">
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <span aria-hidden="true" className={cn("h-2 w-2 rounded-full", priorityDot)} />
            <span className="font-mono text-[10px] uppercase tracking-wide text-white/60">
              {primary.requirement_code ?? primary.period_key ?? "Prioridad"}
            </span>
          </div>
          <h3 className="text-[15px] font-semibold leading-snug text-white">
            {primary.title}
          </h3>
          <p className="line-clamp-3 text-xs leading-[1.55] text-white/75">
            {primary.body}
          </p>
        </div>

        <Button
          asChild
          size="sm"
          className="self-start bg-[color:var(--text-teal)] text-[color:var(--surface-brand)] hover:bg-[color:var(--text-teal)]/90"
        >
          <Link href={primary.href}>
            <span>{ACTION_CTA_LABEL[primary.type] ?? "Abrir"}</span>
            <ArrowRight className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
          </Link>
        </Button>

        {secondary.length > 0 ? (
          <ul className="mt-2 space-y-1.5 border-t border-white/10 pt-3">
            {secondary.map((action) => (
              <li key={action.id}>
                <Link
                  href={action.href}
                  className="group flex items-start justify-between gap-3 rounded-md px-2 py-1.5 transition-colors hover:bg-white/5"
                >
                  <div className="min-w-0 flex-1 space-y-0.5">
                    <p className="line-clamp-1 text-[12px] font-medium text-white/90">
                      {action.title}
                    </p>
                    <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-inverse-muted)]">
                      {action.requirement_code ?? action.period_key ?? "—"}
                    </p>
                  </div>
                  <ArrowRight
                    className="mt-1 h-3.5 w-3.5 shrink-0 text-white/50 transition-transform group-hover:translate-x-0.5 group-hover:text-[color:var(--text-teal)]"
                    weight="bold"
                    aria-hidden="true"
                  />
                </Link>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </section>
  );
}

// ─── KPI strip ────────────────────────────────────────────────────

const KPI_TONE_TEXT: Record<"success" | "info" | "warning" | "neutral", string> = {
  success: "text-[color:var(--status-success-text)]",
  info: "text-[color:var(--status-info-text)]",
  warning: "text-[color:var(--status-warning-text)]",
  neutral: "text-[color:var(--text-primary)]",
};

const KPI_TONE_BORDER: Record<"success" | "info" | "warning" | "neutral", string> = {
  success: "border-[color:var(--status-success-border)]",
  info: "border-[color:var(--status-info-border)]",
  warning: "border-[color:var(--status-warning-border)]",
  neutral: "border-[color:var(--border-default)]",
};

const KPI_TONE_ICON_BG: Record<"success" | "info" | "warning" | "neutral", string> = {
  success: "bg-[color:var(--status-success-bg)] text-[color:var(--status-success-text)]",
  info: "bg-[color:var(--status-info-bg)] text-[color:var(--status-info-text)]",
  warning: "bg-[color:var(--status-warning-bg)] text-[color:var(--status-warning-text)]",
  neutral: "bg-[color:var(--surface-sunken)] text-[color:var(--text-secondary)]",
};

const KPI_TONE_SPARK: Record<"success" | "info" | "warning" | "neutral", ChartTone> = {
  success: "success",
  info: "info",
  warning: "warning",
  neutral: "neutral",
};

function KpiCard({
  label,
  value,
  tone,
  icon: IconComponent,
  sparkData,
  caption,
}: {
  label: string;
  value: number;
  tone: "success" | "info" | "warning" | "neutral";
  icon: Icon;
  sparkData: number[];
  caption?: string;
}) {
  return (
    <article
      className={cn(
        "cw-hover-lift relative overflow-hidden rounded-lg border bg-[color:var(--surface-raised)] p-4 shadow-xs",
        KPI_TONE_BORDER[tone],
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span
            aria-hidden="true"
            className={cn(
              "flex h-9 w-9 shrink-0 items-center justify-center rounded-md",
              KPI_TONE_ICON_BG[tone],
            )}
          >
            <IconComponent className="h-4 w-4" weight="duotone" />
          </span>
          <p className="font-mono text-[11px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
            {label}
          </p>
        </div>
      </div>
      <div className="mt-3 flex items-end justify-between gap-3">
        <p
          className={cn(
            "font-mono text-3xl font-semibold tabular-nums leading-none",
            KPI_TONE_TEXT[tone],
          )}
        >
          {value}
        </p>
        {sparkData.length >= 2 ? (
          <Sparkline
            data={sparkData}
            width={88}
            height={28}
            tone={KPI_TONE_SPARK[tone]}
            filled
          />
        ) : null}
      </div>
      {caption ? (
        <p className="mt-2 text-[12px] leading-snug text-[color:var(--text-secondary)]">
          {caption}
        </p>
      ) : null}
    </article>
  );
}

function KpiDeadlineCard({ deadline }: { deadline: DashboardUpcomingDeadline | null }) {
  const days = deadline?.due_in_days ?? null;
  const tone: "success" | "info" | "warning" | "neutral" = !deadline
    ? "success"
    : days != null && days <= 3
      ? "warning"
      : days != null && days <= 7
        ? "info"
        : "neutral";
  return (
    <article
      className={cn(
        "cw-hover-lift relative overflow-hidden rounded-lg border bg-[color:var(--surface-raised)] p-4 shadow-xs",
        KPI_TONE_BORDER[tone],
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span
            aria-hidden="true"
            className={cn(
              "flex h-9 w-9 shrink-0 items-center justify-center rounded-md",
              KPI_TONE_ICON_BG[tone],
            )}
          >
            <CalendarBlank className="h-4 w-4" weight="duotone" />
          </span>
          <p className="font-mono text-[11px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
            Próximo vencimiento
          </p>
        </div>
      </div>
      {deadline ? (
        <div className="mt-3 space-y-2">
          <p className="flex items-baseline gap-2">
            <span
              className={cn(
                "font-mono text-3xl font-semibold tabular-nums leading-none",
                KPI_TONE_TEXT[tone],
              )}
            >
              {days == null ? "—" : days === 0 ? "Hoy" : `${days}d`}
            </span>
            <span className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
              {INSTITUTION_LABEL[deadline.institution] ?? deadline.institution}
            </span>
          </p>
          <Link
            href={deadline.href}
            className="line-clamp-2 text-[12px] leading-snug text-[color:var(--text-secondary)] hover:text-[color:var(--text-link)] hover:underline"
          >
            {deadline.title}
          </Link>
        </div>
      ) : (
        <div className="mt-3 space-y-1.5">
          <p
            className={cn(
              "font-mono text-3xl font-semibold tabular-nums leading-none",
              KPI_TONE_TEXT[tone],
            )}
          >
            —
          </p>
          <p className="text-[12px] leading-snug text-[color:var(--text-secondary)]">
            Sin vencimientos próximos
          </p>
        </div>
      )}
    </article>
  );
}

// ─── 14-day upload activity (derived) ─────────────────────────────

type ActivityWindow = {
  /** Per-day total upload count for the last 14 days, oldest first. */
  perDay: number[];
  /** Date label (e.g. ``"03/05"``) per slot in `perDay`. */
  dayLabels: string[];
  /** Per-day count of uploads whose CURRENT status maps to attention. */
  byBucketAttention: number[];
  /** Per-day count of uploads whose CURRENT status maps to in_review/uploaded. */
  byBucketReview: number[];
  /** Per-day count of uploads whose CURRENT status maps to approved. */
  byBucketApproved: number[];
  /** Total uploads in the 14-day window. */
  total: number;
};

function useMemo14DayActivity(rows: DashboardRecentUpload[]): ActivityWindow {
  return useMemo(() => derive14DayActivity(rows), [rows]);
}

function derive14DayActivity(rows: DashboardRecentUpload[]): ActivityWindow {
  const days = 14;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const start = new Date(today);
  start.setDate(start.getDate() - (days - 1));

  const perDay = new Array<number>(days).fill(0);
  const byBucketAttention = new Array<number>(days).fill(0);
  const byBucketReview = new Array<number>(days).fill(0);
  const byBucketApproved = new Array<number>(days).fill(0);
  const dayLabels: string[] = [];
  for (let i = 0; i < days; i += 1) {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    dayLabels.push(
      `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}`,
    );
  }

  for (const row of rows) {
    const submitted = new Date(row.submitted_at);
    if (Number.isNaN(submitted.getTime())) continue;
    submitted.setHours(0, 0, 0, 0);
    const diffDays = Math.floor(
      (submitted.getTime() - start.getTime()) / (1000 * 60 * 60 * 24),
    );
    if (diffDays < 0 || diffDays >= days) continue;
    perDay[diffDays] += 1;
    const code = statusToDocumentStateCode(row.status as RequirementStatus);
    if (code === "approved") {
      byBucketApproved[diffDays] += 1;
    } else if (code === "in_review" || code === "uploaded") {
      byBucketReview[diffDays] += 1;
    } else if (
      code === "rejected" ||
      code === "needs_review" ||
      code === "expired"
    ) {
      byBucketAttention[diffDays] += 1;
    }
  }

  const total = perDay.reduce((sum, n) => sum + n, 0);
  return {
    perDay,
    dayLabels,
    byBucketAttention,
    byBucketReview,
    byBucketApproved,
    total,
  };
}

function UploadActivityCard({
  activity,
  className,
}: {
  activity: ActivityWindow;
  className?: string;
}) {
  const max = Math.max(0, ...activity.perDay);
  // Highlight today's column with brand tone, others with teal tint.
  const data = activity.perDay.map((value, idx) => ({
    label: activity.dayLabels[idx] ?? "",
    value,
    tone: (idx === activity.perDay.length - 1 ? "brand" : "teal") as ChartTone,
  }));
  return (
    <section
      aria-label="Actividad de cargas (14 días)"
      className={cn(
        "cw-fade-up rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-xs",
        className,
      )}
    >
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-[color:var(--border-subtle)] px-5 py-3">
        <div className="flex items-center gap-2">
          <TrendUp className="h-4 w-4 text-[color:var(--text-brand)]" weight="duotone" aria-hidden="true" />
          <h3 className="text-[12px] font-semibold uppercase tracking-wide text-[color:var(--text-primary)]">
            Actividad de cargas
          </h3>
          <span className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
            últimos 14 días
          </span>
        </div>
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-2xl font-semibold tabular-nums leading-none text-[color:var(--text-primary)]">
            {activity.total}
          </span>
          <span className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
            {activity.total === 1 ? "carga" : "cargas"}
          </span>
        </div>
      </header>
      <div className="p-5">
        {activity.total === 0 ? (
          <div className="flex flex-col items-center justify-center gap-1 py-10 text-center">
            <Tray
              className="h-8 w-8 text-[color:var(--text-tertiary)]"
              weight="duotone"
              aria-hidden="true"
            />
            <p className="text-[13px] font-medium text-[color:var(--text-primary)]">
              Sin actividad reciente
            </p>
            <p className="max-w-xs text-xs text-[color:var(--text-secondary)]">
              Cuando subas un documento, aquí verás un pulso diario de tu
              expediente durante las últimas dos semanas.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            <MiniBars data={data} height={140} />
            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-[color:var(--border-subtle)] pt-3 font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
              <span>
                Pico:{" "}
                <span className="text-[color:var(--text-primary)]">
                  {max} {max === 1 ? "carga" : "cargas"}/día
                </span>
              </span>
              <span>
                Promedio:{" "}
                <span className="text-[color:var(--text-primary)]">
                  {(activity.total / 14).toFixed(1)}/día
                </span>
              </span>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

// ─── Institution breakdown ────────────────────────────────────────

function InstitutionBreakdownCard({
  rows,
  className,
}: {
  rows: DashboardInstitutionBreakdown[];
  className?: string;
}) {
  return (
    <section
      aria-label="Distribución por institución"
      className={cn(
        "cw-fade-up rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-xs",
        className,
      )}
    >
      <header className="flex items-center justify-between gap-2 border-b border-[color:var(--border-subtle)] px-5 py-3">
        <div className="flex items-center gap-2">
          <Bank className="h-4 w-4 text-[color:var(--text-brand)]" weight="duotone" aria-hidden="true" />
          <h3 className="text-[12px] font-semibold uppercase tracking-wide text-[color:var(--text-primary)]">
            Por institución
          </h3>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
          obligatorios
        </span>
      </header>
      <div className="p-5">
        {rows.length === 0 ? (
          <p className="py-6 text-center text-xs text-[color:var(--text-secondary)]">
            Sin obligaciones registradas.
          </p>
        ) : (
          <ul className="space-y-3">
            {rows.map((row) => {
              const segments: ChartSegment[] = [
                { label: "Aprobados", value: row.approved, tone: "success" },
                { label: bucketLabel("pending_reviews"), value: row.in_review, tone: "info" },
                { label: "Por atender", value: row.needs_action, tone: "warning" },
                { label: "Pendientes", value: row.pending, tone: "neutral" },
              ];
              return (
                <li key={row.institution} className="space-y-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-[11px] font-semibold uppercase tracking-wide text-[color:var(--text-primary)]">
                      {INSTITUTION_LABEL[row.institution] ?? row.institution.toUpperCase()}
                    </span>
                    <span className="font-mono text-[10px] tabular-nums text-[color:var(--text-tertiary)]">
                      {row.approved}/{row.total}
                    </span>
                  </div>
                  <StackedBars segments={segments} height={8} showLegend={false} />
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}

// ─── Operational queues ───────────────────────────────────────────

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

function splitAttentionItems(
  items: { id: string; title: string; institution: string; state: string; due_in_days: number | null; href: string }[],
): {
  actionable: typeof items;
  dueSoon: typeof items;
} {
  const actionable: typeof items = [];
  const dueSoon: typeof items = [];
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
  attention: ReturnType<typeof splitAttentionItems>["actionable"];
  dueSoon: ReturnType<typeof splitAttentionItems>["dueSoon"];
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
        href={attention.length > 0 ? "/portal/calendar" : undefined}
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
        title="Documentos faltantes"
        icon={CalendarBlank}
        emptyTitle="Sin documentos faltantes"
        emptyDescription="No tienes documentos obligatorios por cargar en este momento."
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
        title={bucketLabel("pending_reviews")}
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

// ─── Right rail: upcoming deadlines ───────────────────────────────

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
                    {due == null ? "—" : due === 0 ? "Hoy" : `${due}d`}
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

// ─── Right rail: compliance donut ─────────────────────────────────

function ComplianceDonut({
  counts,
}: {
  counts: DashboardPayload["document_state_counts"];
}) {
  const segments: ChartSegment[] = [
    { label: "Aprobados", value: counts.approved, tone: "success" },
    { label: bucketLabel("pending_reviews"), value: counts.in_review + counts.uploaded, tone: "info" },
    {
      label: "Necesitan acción",
      value: counts.needs_review + counts.rejected + counts.expired,
      tone: "warning",
    },
    { label: "Pendientes", value: counts.pending, tone: "neutral" },
  ];
  const total = segments.reduce((sum, s) => sum + s.value, 0);
  return (
    <section
      aria-label="Distribución por estado"
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
            Distribución
          </h3>
        </div>
        <span className="font-mono text-[10px] tabular-nums text-[color:var(--text-tertiary)]">
          {total} {total === 1 ? "doc" : "docs"}
        </span>
      </header>
      <div className="p-5">
        {total === 0 ? (
          <p className="py-4 text-center text-xs text-[color:var(--text-secondary)]">
            Aún no hay documentos cargados.
          </p>
        ) : (
          <Donut
            segments={segments}
            size={132}
            thickness={14}
            centerLabel={total}
            centerCaption="docs"
            showLegend
          />
        )}
      </div>
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

// ---------------------------------------------------------------------------
// Phase 5 / Slice 5C — Expediente download dialog
// ---------------------------------------------------------------------------
//
// Replaces the plain "Descargar expediente" anchor from Slice 5B with
// a modal that picks institución / periodo / estado before opening
// the filtered ZIP URL. All three default to "Todo" — submitting
// without changes preserves the original full-pull behavior.
//
// Submission opens the URL in a new tab (cookie-auth navigation,
// same pattern as Slice 5A/5B). Dialog closes on submit so the user
// returns to the dashboard with the download fired.

const _ZIP_INSTITUTION_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: "", label: "Todas las instituciones" },
  { value: "sat", label: "SAT" },
  { value: "imss", label: "IMSS" },
  { value: "infonavit", label: "INFONAVIT" },
  { value: "stps_repse", label: "STPS / REPSE" },
  { value: "interno_cliente", label: "Interno / Cliente" },
];

const _ZIP_STATUS_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: "", label: "Todos los estados" },
  { value: "aprobado", label: statusLabel("aprobado") },
  { value: "pendiente_revision", label: statusLabel("pendiente_revision") },
  { value: "requiere_aclaracion", label: statusLabel("requiere_aclaracion") },
  { value: "rechazado", label: statusLabel("rechazado") },
  { value: "excepcion_legal", label: statusLabel("excepcion_legal") },
];

// Canonical period_key shapes accepted by the backend (see
// apps/api/app/models/entities.py:155): ``YYYY-Mxx`` (mensual, 01-12),
// ``YYYY-Bn`` (bimestral, 1-6), ``YYYY-Qn`` (cuatrimestral, 1-3),
// ``YYYY-A`` (anual). An unrecognized key is silently treated as "no
// filter" by the ZIP endpoint, so we validate before firing the
// download to avoid a misleading full pull.
const _PERIOD_KEY_RE = /^\d{4}-(M(0[1-9]|1[0-2])|B[1-6]|Q[1-3]|A)$/;

function ExpedienteDownloadDialog({ session }: { session: PortalSession }) {
  const [open, setOpen] = useState(false);
  const [institution, setInstitution] = useState("");
  const [periodKey, setPeriodKey] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const trimmedPeriod = periodKey.trim();
  const periodError =
    trimmedPeriod !== "" && !_PERIOD_KEY_RE.test(trimmedPeriod)
      ? "Formato no reconocido. Usa YYYY-Mnn, YYYY-Bn, YYYY-Qn o YYYY-A."
      : null;

  function handleSubmit() {
    if (periodError) return;
    const url = expedienteZipUrl(session, {
      institution: institution || null,
      period_key: trimmedPeriod || null,
      status: statusFilter || null,
    });
    window.open(url, "_blank", "noopener,noreferrer");
    setOpen(false);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline">
          <DownloadSimple
            className="h-4 w-4"
            weight="bold"
            aria-hidden="true"
          />
          Descargar expediente
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Descargar expediente</DialogTitle>
          <DialogDescription>
            Te enviamos un ZIP con tus documentos agrupados por
            institución y periodo. Deja los filtros en &quot;Todo&quot; para
            una descarga completa o selecciona para acotar.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3 py-2">
          <Field label="Institución" htmlFor="zip-filter-institution">
            <Select
              id="zip-filter-institution"
              value={institution}
              onChange={(e) => setInstitution(e.target.value)}
            >
              {_ZIP_INSTITUTION_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field
            label="Periodo (opcional)"
            htmlFor="zip-filter-period"
            helper="Formato YYYY-Mnn (ej. 2026-M05), o YYYY-Bn / YYYY-Qn / YYYY-A."
            error={periodError}
          >
            <input
              id="zip-filter-period"
              value={periodKey}
              onChange={(e) => setPeriodKey(e.target.value)}
              placeholder="2026-M05"
              className="block w-full rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-2 py-1.5 text-sm text-[color:var(--text-primary)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]/40"
            />
          </Field>
          <Field label="Estado" htmlFor="zip-filter-status">
            <Select
              id="zip-filter-status"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              {_ZIP_STATUS_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => setOpen(false)}
          >
            Cancelar
          </Button>
          <Button type="button" onClick={handleSubmit} disabled={!!periodError}>
            <DownloadSimple
              className="h-4 w-4"
              weight="bold"
              aria-hidden="true"
            />
            Descargar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
