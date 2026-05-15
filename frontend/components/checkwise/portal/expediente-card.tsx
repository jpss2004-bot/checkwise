"use client";

import {
  ArrowRight,
  Buildings,
  CheckCircle,
  CloudArrowUp,
  FilePdf,
  Files,
  Scales,
  ShieldCheck,
  Stamp,
  type Icon,
} from "@phosphor-icons/react";

import { DocStateBadge } from "@/components/checkwise/doc-state-badge";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { statusToDocumentStateCode, type OnboardingItem } from "@/lib/api/portal";
import type { DocumentStateCode } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * The shape the card renders against. Phase 5 — fed directly by the
 * backend's enriched ``OnboardingItem`` (no adapter, no frontend mock).
 * Kept as an intermediate type so the page can plug in either a real
 * backend item or, in the future, a reviewer-side variant without
 * forking the component.
 */
export interface ExpedienteCardItem {
  /** Stable id for React keys + upload routing. Derived from the
   *  canonical requirement_code (lowercased) by the page. */
  id: string;
  requirement_code: string;
  name: string;
  institution: string;
  why: string;
  format: string;
  state: DocumentStateCode;
  next_action: string;
  reviewer_note: string | null;
  required: boolean;
  filename: string | null;
}

const INSTITUTION_ICON: Record<string, Icon> = {
  sat: Scales,
  stps_repse: ShieldCheck,
  imss: Buildings,
  infonavit: Buildings,
  interno_cliente: Stamp,
};

const INSTITUTION_LABEL: Record<string, string> = {
  sat: "SAT",
  stps_repse: "STPS / REPSE",
  imss: "IMSS",
  infonavit: "INFONAVIT",
  interno_cliente: "Interno / Cliente",
};

/**
 * Build a card-ready view of a backend ``OnboardingItem``. Pure
 * mapping — drives no fetches, no fallbacks. Page-level state lives
 * in the page; this just normalises the field shape and id.
 */
export function expedienteCardItemFromOnboarding(
  item: OnboardingItem,
): ExpedienteCardItem {
  return {
    id: item.code.toLowerCase(),
    requirement_code: item.code,
    name: item.name,
    institution: item.institution,
    why: item.why,
    format: item.format,
    state: statusToDocumentStateCode(item.status),
    next_action: item.next_action,
    reviewer_note: item.reviewer_note,
    required: item.required,
    filename: item.filename,
  };
}

interface ExpedienteCardProps {
  requirement: ExpedienteCardItem;
  /** Called when the user clicks the primary CTA. Receives the card item. */
  onAction?: (req: ExpedienteCardItem) => void;
}

/**
 * Single requirement card for the expediente inicial gate.
 *
 * Each card explains: what + why + format + status + next action.
 * Status uses the design system's DocStateBadge with REPSE-state
 * tokens. The CTA label adapts to the current state.
 *
 * Spec: docs/DESIGN_SYSTEM.md §6.1 (Onboarding patterns)
 */
export function ExpedienteCard({ requirement, onAction }: ExpedienteCardProps) {
  const IconComponent = INSTITUTION_ICON[requirement.institution];
  const cardTone = toneForState(requirement.state);

  return (
    <article
      className={cn(
        "group relative flex flex-col gap-4 rounded-lg border bg-[color:var(--surface-raised)] p-5 shadow-xs transition-shadow duration-fast hover:shadow-sm cw-hover-lift",
        cardTone === "attention"
          ? "border-[color:var(--status-warning-border)]"
          : cardTone === "rejected"
            ? "border-[color:var(--status-error-border)]"
            : cardTone === "approved"
              ? "border-[color:var(--status-success-border)]"
              : "border-[color:var(--border-default)]",
      )}
      aria-labelledby={`req-${requirement.id}-title`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[color:var(--surface-brand-muted)]">
            <IconComponent
              className="h-5 w-5 text-[color:var(--text-brand)]"
              weight="duotone"
              aria-hidden="true"
            />
          </span>
          <div className="min-w-0">
            <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
              {INSTITUTION_LABEL[requirement.institution]}
              {requirement.requirement_code && (
                <>
                  {" · "}
                  <span className="text-[color:var(--text-secondary)]">
                    {requirement.requirement_code}
                  </span>
                </>
              )}
            </p>
            <h3
              id={`req-${requirement.id}-title`}
              className="mt-1 text-[15px] font-semibold leading-5 text-[color:var(--text-primary)]"
            >
              {requirement.name}
            </h3>
            <p className="mt-1.5 inline-flex">
              <span
                className={cn(
                  "rounded-full border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide font-semibold",
                  requirement.required
                    ? "border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-bg)] text-[color:var(--status-warning-text)]"
                    : "border-[color:var(--border-subtle)] bg-[color:var(--surface-sunken)] text-[color:var(--text-tertiary)]",
                )}
                title={
                  requirement.required
                    ? "Obligatorio para activar el dashboard"
                    : "Opcional — puedes subirlo después"
                }
              >
                {requirement.required
                  ? "Obligatorio · activa dashboard"
                  : "Opcional"}
              </span>
            </p>
          </div>
        </div>
        <DocStateBadge state={requirement.state} />
      </div>

      <p className="text-[13px] leading-5 text-[color:var(--text-secondary)]">
        {requirement.why}
      </p>

      {requirement.filename ? (
        <div className="flex items-center gap-2 rounded-sm border border-[color:var(--doc-uploaded-border)] bg-[color:var(--doc-uploaded-bg)] p-3">
          <FilePdf
            className="h-4 w-4 shrink-0 text-[color:var(--doc-uploaded-text)]"
            weight="duotone"
            aria-hidden="true"
          />
          <span
            className="min-w-0 flex-1 truncate font-mono text-xs text-[color:var(--doc-uploaded-text)]"
            title={requirement.filename}
          >
            {requirement.filename}
          </span>
          <CheckCircle
            className="h-4 w-4 shrink-0 text-[color:var(--doc-uploaded-text)]"
            weight="fill"
            aria-hidden="true"
          />
        </div>
      ) : (
        <div className="flex items-start gap-2 rounded-sm bg-[color:var(--surface-sunken)] p-3">
          <Files
            className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[color:var(--text-tertiary)]"
            weight="bold"
            aria-hidden="true"
          />
          <p className="text-xs leading-5 text-[color:var(--text-secondary)]">
            {requirement.format}
          </p>
        </div>
      )}

      {requirement.reviewer_note && (
        <div className="rounded-sm border border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-bg)] p-3 text-xs text-[color:var(--status-warning-text)]">
          <p className="font-semibold">Nota del revisor</p>
          <p className="mt-0.5 leading-5">{requirement.reviewer_note}</p>
        </div>
      )}

      <div className="mt-auto flex flex-col gap-3 border-t border-[color:var(--border-subtle)] pt-3 sm:flex-row sm:items-end sm:justify-between">
        <p className="text-xs leading-5 text-[color:var(--text-primary)]">
          <span className="font-semibold text-[color:var(--text-brand)]">
            Siguiente paso:
          </span>{" "}
          {requirement.next_action}
        </p>
        {requirement.state !== "approved" && requirement.state !== "in_review" && (
          <Button
            type="button"
            size="sm"
            variant={
              requirement.state === "rejected" || requirement.state === "expired"
                ? "default"
                : "outline"
            }
            onClick={() => onAction?.(requirement)}
            className="shrink-0"
          >
            <CloudArrowUp className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
            {ctaLabelForState(requirement.state)}
            <ArrowRight className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
          </Button>
        )}
      </div>

      {(requirement.state === "rejected" ||
        requirement.state === "needs_review" ||
        requirement.state === "expired") && (
        <p className="text-[11px] text-[color:var(--text-tertiary)]">
          ¿Crees que hay un cruce de empresa o una asignación incorrecta?{" "}
          <a
            href="/portal/entra-a-tu-espacio#correccion"
            className="text-[color:var(--text-link)] hover:underline"
          >
            Reportar inconsistencia
          </a>
          .
        </p>
      )}
    </article>
  );
}

function toneForState(
  state: DocumentStateCode,
): "attention" | "rejected" | "approved" | "neutral" {
  if (state === "approved") return "approved";
  if (state === "rejected" || state === "expired") return "rejected";
  if (state === "needs_review" || state === "pending") return "attention";
  return "neutral";
}

function ctaLabelForState(state: DocumentStateCode): string {
  if (state === "rejected") return "Corregir y volver a subir";
  if (state === "expired") return "Subir versión vigente";
  if (state === "needs_review") return "Revisar y confirmar";
  if (state === "uploaded") return "Ver lo que enviaste";
  return "Subir documento";
}

interface InlineUploadingStateProps {
  filename: string;
  pct: number;
}

/** Inline upload-in-progress block, drops into the bottom of a card. */
export function InlineUploadingState({ filename, pct }: InlineUploadingStateProps) {
  return (
    <div className="rounded-sm border border-[color:var(--doc-uploaded-border)] bg-[color:var(--doc-uploaded-bg)] p-3 text-xs text-[color:var(--doc-uploaded-text)]">
      <div className="mb-2 flex items-center justify-between gap-3">
        <span className="flex min-w-0 items-center gap-1.5">
          <Spinner className="text-current" label={null} />
          <span className="truncate font-medium">{filename}</span>
        </span>
        <span className="font-mono tabular-nums">{pct}%</span>
      </div>
      <div className="h-1 w-full overflow-hidden rounded-full bg-[color:var(--surface-raised)]">
        <div
          className="h-full rounded-full bg-[color:var(--doc-uploaded-text)] transition-[width] duration-fast"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
