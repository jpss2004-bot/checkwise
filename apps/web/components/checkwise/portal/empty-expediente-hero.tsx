"use client";

import Link from "next/link";
import {
  ArrowRight,
  CheckCircle,
  CloudArrowUp,
  HourglassHigh,
  Sparkle,
} from "@phosphor-icons/react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  type DashboardOnboardingSummary,
  type DashboardSemaphore,
  type OnboardingItem,
  type OnboardingSummary,
  type RequirementStatus,
  statusToDocumentStateCode,
} from "@/lib/api/portal";
import type { DocumentStateCode } from "@/lib/types";

/**
 * EmptyExpedienteHero — guided start surface for vendors who have
 * not yet completed their initial expediente (``onboarding_completed_at``
 * is still null).
 *
 * Replaces the chart-rich dashboard layout in that state because:
 *   • Charts of mostly-zero data read as broken to a brand-new user.
 *   • The provider's only meaningful next step is upload-the-first-doc,
 *     and the dashboard payload alone doesn't tell them which one to
 *     start with — the onboarding payload does.
 *
 * Shape: a hero header with progress copy + the existing semaphore
 * reason, followed by a numbered list of the next 3-5 required
 * onboarding documents in canonical order. Each row deep-links to
 * /portal/upload with the requirement_code pre-set, and surfaces a
 * completion checkmark for steps the provider has already touched.
 *
 * Driven by the canonical onboarding read model — never invents
 * steps, never drifts from the catalog.
 */

interface EmptyExpedienteHeroProps {
  vendorName: string;
  summary: DashboardOnboardingSummary;
  semaphore: DashboardSemaphore;
  onboarding: OnboardingSummary | null;
  /** How many steps to surface. Defaults to 5. */
  limit?: number;
  className?: string;
}

export function EmptyExpedienteHero({
  vendorName,
  summary,
  semaphore,
  onboarding,
  limit = 5,
  className,
}: EmptyExpedienteHeroProps) {
  const steps = pickSteps(onboarding, limit);
  const greetingName = friendlyVendorName(vendorName).trim();

  return (
    <section
      aria-label="Empieza tu expediente"
      className={cn(
        "cw-fade-up relative overflow-hidden rounded-xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-sm",
        className,
      )}
    >
      {/* Decorative gradient + grid ornament. Visual only. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-gradient-to-br from-[color:var(--surface-brand-muted)] via-transparent to-[color:var(--surface-teal-muted)] opacity-70"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-[color:var(--text-teal)] opacity-10 blur-3xl"
      />
      <div className="pointer-events-none absolute inset-0 cw-grid-pattern opacity-30" aria-hidden="true" />

      <div className="relative grid gap-6 p-6 md:grid-cols-[1fr,auto] md:items-start md:p-8">
        <div className="min-w-0 space-y-3">
          <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-teal)]">
            Empieza tu expediente
          </p>
          <h2 className="text-2xl font-semibold leading-tight tracking-[-0.01em] text-[color:var(--text-primary)] sm:text-3xl">
            Hola{greetingName ? ` ${greetingName}` : ""}.
            <br className="hidden sm:block" /> Vamos a armar tu cumplimiento, paso a paso.
          </h2>
          <p className="max-w-prose text-[13px] leading-relaxed text-[color:var(--text-secondary)]">
            {semaphore.reason.trim() ? <>{semaphore.reason.trim()} </> : null}
            El checklist de abajo tiene los documentos obligatorios para que tu
            expediente quede listo.
          </p>
        </div>
        <ProgressBadge summary={summary} />
      </div>

      <div className="relative border-t border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)]/85 backdrop-blur-sm">
        <div className="px-6 py-5 md:px-8">
          <div className="mb-4 flex items-center justify-between gap-2">
            <h3 className="text-[12px] font-semibold uppercase tracking-wide text-[color:var(--text-primary)]">
              Primeros pasos
            </h3>
            <span className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
              {summary.completed} / {summary.total_required} obligatorios
            </span>
          </div>
          {onboarding === null ? (
            <StepsSkeleton />
          ) : steps.length === 0 ? (
            <EmptyStepsState summary={summary} />
          ) : (
            <ol className="space-y-2.5">
              {steps.map((step, idx) => (
                <li key={step.code}>
                  <StepRow step={step} index={idx + 1} />
                </li>
              ))}
            </ol>
          )}
        </div>
      </div>
    </section>
  );
}

// ─── Pieces ─────────────────────────────────────────────────────────

function ProgressBadge({ summary }: { summary: DashboardOnboardingSummary }) {
  const pct = Math.max(0, Math.min(100, summary.completion_pct));
  const tone =
    pct >= 100
      ? "text-[color:var(--status-success-text)]"
      : pct >= 50
        ? "text-[color:var(--status-info-text)]"
        : "text-[color:var(--text-brand)]";
  return (
    <div className="flex items-center gap-3 self-start rounded-lg border border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)]/80 px-4 py-3 backdrop-blur-sm">
      <div className="text-right">
        <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
          Avance
        </p>
        <p className={cn("font-mono text-2xl font-semibold tabular-nums leading-none", tone)}>
          {pct}%
        </p>
      </div>
      <div className="h-12 w-[3px] rounded-full bg-[color:var(--border-subtle)]">
        <div
          aria-hidden="true"
          className="h-12 w-full origin-bottom rounded-full bg-gradient-to-t from-[color:var(--text-teal)] to-[color:var(--text-brand)]"
          style={{ transform: `scaleY(${pct / 100})` }}
        />
      </div>
    </div>
  );
}

function StepRow({ step, index }: { step: OnboardingItem; index: number }) {
  const code = statusToDocumentStateCode(step.status as RequirementStatus);
  const status = stepStatus(code);
  // Always pass both the canonical ``requirement_code`` AND the
  // human ``requirement`` name so the intake wizard renders the
  // document the provider actually clicked on. Without the name, the
  // wizard would fall back to an arbitrary catalog default (see the
  // intake-wizard 2026-05-21 fix).
  // Provider-portal UX pass (2026-05-25) — include ``institution`` so
  // the upload wizard's Step 1 locks the institution field instead of
  // falling back to its hardcoded "sat" default. ``OnboardingItem``
  // exposes the field; the calendar/onboarding href builders on the
  // backend received the matching fix.
  const href =
    `/portal/upload?requirement_code=${encodeURIComponent(step.code)}` +
    `&requirement=${encodeURIComponent(step.name)}` +
    `&institution=${encodeURIComponent(step.institution)}` +
    `&from=onboarding`;

  return (
    <Link
      href={href}
      className={cn(
        "group flex items-start justify-between gap-3 rounded-lg border px-4 py-3 transition-all",
        status === "done"
          ? "border-[color:var(--status-success-border)] bg-[color:var(--status-success-bg)]/50"
          : status === "in_progress"
            ? "border-[color:var(--status-info-border)] bg-[color:var(--status-info-bg)]/50 hover:border-[color:var(--border-strong)]"
            : "border-[color:var(--border-default)] bg-[color:var(--surface-raised)] hover:border-[color:var(--border-strong)] hover:bg-[color:var(--surface-page)]",
      )}
    >
      <div className="flex min-w-0 items-start gap-3">
        <StepBadge status={status} index={index} />
        <div className="min-w-0 space-y-0.5">
          <p className="text-[13.5px] font-medium leading-snug text-[color:var(--text-primary)]">
            {step.name}
          </p>
          <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
            {step.institution.toUpperCase()}
          </p>
          {step.why ? (
            <p className="text-[12px] leading-relaxed text-[color:var(--text-secondary)]">
              {step.why}
            </p>
          ) : null}
        </div>
      </div>
      <StepCta status={status} />
    </Link>
  );
}

type StepStatus = "todo" | "in_progress" | "done";

function stepStatus(code: DocumentStateCode): StepStatus {
  if (code === "approved") return "done";
  if (
    code === "in_review" ||
    code === "uploaded" ||
    code === "needs_review" ||
    code === "rejected" ||
    code === "expired"
  ) {
    return "in_progress";
  }
  return "todo";
}

function StepBadge({ status, index }: { status: StepStatus; index: number }) {
  if (status === "done") {
    return (
      <span
        aria-hidden="true"
        className="mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[color:var(--status-success-text)] text-white"
      >
        <CheckCircle className="h-4 w-4" weight="fill" />
      </span>
    );
  }
  if (status === "in_progress") {
    return (
      <span
        aria-hidden="true"
        className="mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[color:var(--status-info-bg)] text-[color:var(--status-info-text)]"
      >
        <HourglassHigh className="h-3.5 w-3.5" weight="bold" />
      </span>
    );
  }
  return (
    <span
      aria-hidden="true"
      className="mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-[color:var(--border-default)] bg-[color:var(--surface-page)] font-mono text-[12px] font-semibold text-[color:var(--text-secondary)]"
    >
      {index}
    </span>
  );
}

function StepCta({ status }: { status: StepStatus }) {
  if (status === "done") {
    return (
      <span className="shrink-0 self-center font-mono text-[10px] uppercase tracking-wide text-[color:var(--status-success-text)]">
        Listo
      </span>
    );
  }
  if (status === "in_progress") {
    return (
      <span className="shrink-0 self-center font-mono text-[10px] uppercase tracking-wide text-[color:var(--status-info-text)]">
        En curso →
      </span>
    );
  }
  return (
    <Button
      asChild={false}
      size="sm"
      variant="outline"
      className="pointer-events-none shrink-0 self-center"
      tabIndex={-1}
    >
      <span className="inline-flex items-center gap-1">
        <CloudArrowUp className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
        Subir
      </span>
    </Button>
  );
}

function StepsSkeleton() {
  // Mirrors StepRow's height/spacing so the list reserves space and reads
  // as loading rather than swapping content once the onboarding payload
  // resolves. Distinct from EmptyStepsState — only shown while the payload
  // is unavailable (``onboarding === null``), never as a completion state.
  return (
    <div role="status" aria-busy="true" className="space-y-2.5">
      <span className="sr-only">Cargando tus primeros pasos…</span>
      {Array.from({ length: 4 }).map((_, idx) => (
        <div
          key={idx}
          aria-hidden="true"
          className="flex items-start gap-3 rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-4 py-3"
        >
          <div className="mt-0.5 h-7 w-7 shrink-0 animate-pulse rounded-full bg-[color:var(--surface-page)]" />
          <div className="min-w-0 flex-1 space-y-2">
            <div className="h-3.5 w-7/12 animate-pulse rounded bg-[color:var(--surface-page)]" />
            <div className="h-2.5 w-3/12 animate-pulse rounded bg-[color:var(--surface-page)]" />
          </div>
        </div>
      ))}
    </div>
  );
}

function EmptyStepsState({ summary }: { summary: DashboardOnboardingSummary }) {
  if (summary.total_required === 0) {
    return (
      <div className="rounded-lg border border-dashed border-[color:var(--border-default)] bg-[color:var(--surface-page)] p-6 text-center">
        <Sparkle
          className="mx-auto h-6 w-6 text-[color:var(--text-teal)]"
          weight="fill"
          aria-hidden="true"
        />
        <p className="mt-2 text-[13px] font-medium text-[color:var(--text-primary)]">
          Tu expediente no requiere documentos obligatorios.
        </p>
        <p className="mx-auto mt-1 max-w-prose text-xs text-[color:var(--text-secondary)]">
          Si esto te parece raro, escríbele a tu cliente o a Legal Shelf.
        </p>
      </div>
    );
  }
  return (
    <div className="rounded-lg border border-dashed border-[color:var(--status-success-border)] bg-[color:var(--status-success-bg)]/40 p-6 text-center">
      <CheckCircle
        className="mx-auto h-6 w-6 text-[color:var(--status-success-text)]"
        weight="fill"
        aria-hidden="true"
      />
      <p className="mt-2 text-[13px] font-medium text-[color:var(--text-primary)]">
        Ya tocaste todos tus documentos obligatorios.
      </p>
      <p className="mx-auto mt-1 max-w-prose text-xs text-[color:var(--text-secondary)]">
        Solo falta que termine la revisión. Te avisaremos por correo cuando
        todo quede aprobado.
      </p>
      <Button asChild size="sm" variant="outline" className="mt-3">
        <Link href="/portal/onboarding">
          <span>Ver expediente</span>
          <ArrowRight className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
        </Link>
      </Button>
    </div>
  );
}

// ─── Helpers ────────────────────────────────────────────────────────

/**
 * Walk the onboarding payload sections in catalog order, picking
 * required items first (todo before in-progress before done) and
 * capping at ``limit``. Done items still surface so the checklist
 * shows the provider's progress instead of jumping straight to the
 * next blank step.
 */
function pickSteps(
  onboarding: OnboardingSummary | null,
  limit: number,
): OnboardingItem[] {
  if (!onboarding) return [];
  const required: OnboardingItem[] = [];
  for (const section of onboarding.sections) {
    for (const item of section.items) {
      if (!item.required) continue;
      required.push(item);
    }
  }
  // Stable sort: todo first, then in-progress, then done. Within
  // each bucket preserve catalog order.
  const buckets: Record<StepStatus, OnboardingItem[]> = {
    todo: [],
    in_progress: [],
    done: [],
  };
  for (const item of required) {
    const code = statusToDocumentStateCode(item.status as RequirementStatus);
    buckets[stepStatus(code)].push(item);
  }
  return [...buckets.todo, ...buckets.in_progress, ...buckets.done].slice(0, limit);
}

function friendlyVendorName(full: string): string {
  const suffixes = [
    " S.A. DE C.V.",
    " SA DE CV",
    " S DE RL DE CV",
    " S. DE R.L. DE C.V.",
    " S.A.S.",
    " SAS",
    " S.A.",
    " SA",
  ];
  const upper = full.toUpperCase();
  for (const suffix of suffixes) {
    if (upper.endsWith(suffix)) {
      return full.slice(0, full.length - suffix.length).trim();
    }
  }
  return full;
}
