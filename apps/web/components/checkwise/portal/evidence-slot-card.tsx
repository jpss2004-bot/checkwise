import * as React from "react";
import Link from "next/link";
import { ArrowRight, ArrowsClockwise } from "@phosphor-icons/react";

import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { DocumentStateCode } from "@/lib/types";

/**
 * EvidenceSlotCard — atomic unit of the evidence-slot lattice.
 *
 * Renders one obligation (workspace × requirement × period) as a
 * compact, scannable card. State is communicated via the state badge
 * in the bottom row plus the deadline chip; the card surface stays
 * neutral so a wall of cards reads as calm operational space rather
 * than as a chromatic strip-stack.
 *
 * Backed by canonical reads — never renders invented status. Lineage
 * indicator surfaces the supersession relationship when present.
 *
 * Spec: docs/design-system/VISUAL_REDESIGN_DOCTRINE.md §"Evidence Slot Grid".
 */

export interface EvidenceSlotCardProps {
  /** Stable id; used as React key by the grid. */
  id: string;
  /** Human-readable obligation title (Spanish, sentence case). */
  title: string;
  /** Institution chip text (already humanised, e.g. "SAT"). */
  institution: string;
  /** Period label, e.g. "2026-B1", or null for onboarding-only slots. */
  periodLabel?: string | null;
  /** Slot state — drives the colored bar + state badge. */
  state: DocumentStateCode;
  /** Spanish state label, e.g. "Aprobado". Falls back to a default. */
  stateLabel?: string;
  /** Days until / since deadline. null = no deadline. negative = overdue. */
  dueInDays?: number | null;
  /** Where clicking the card sends the user. */
  href: string;
  /** Lineage indicator: this slot's current submission replaces a prior one. */
  isReplacement?: boolean;
  /** Index for staggered entrance animation (passed by the grid). */
  index?: number;
  className?: string;
}

const STATE_LABEL_FALLBACK: Record<DocumentStateCode, string> = {
  // Canonical wording unification (2026-06-10) — mirrors slotStateLabel()
  // in @/lib/constants/statuses so provider slot cards read the same words
  // as client surfaces. `uploaded` collapses into "En revisión".
  empty: "Por entregar",
  pending: "Por entregar",
  uploaded: "En revisión",
  in_review: "En revisión",
  approved: "Aprobado",
  // Audit P1-02 — softer copy on provider-facing slot cards.
  rejected: "Requiere corrección",
  expired: "Vencido",
  needs_review: "Necesita aclaración",
};

const STATE_TEXT_CLASS: Record<DocumentStateCode, string> = {
  empty: "text-[color:var(--doc-empty-text)]",
  pending: "text-[color:var(--doc-pending-text)]",
  uploaded: "text-[color:var(--doc-uploaded-text)]",
  in_review: "text-[color:var(--doc-in-review-text)]",
  approved: "text-[color:var(--doc-approved-text)]",
  rejected: "text-[color:var(--doc-rejected-text)]",
  expired: "text-[color:var(--doc-expired-text)]",
  needs_review: "text-[color:var(--doc-needs-review-text)]",
};

const STATE_BG_CLASS: Record<DocumentStateCode, string> = {
  empty: "bg-[color:var(--doc-empty-bg)]",
  pending: "bg-[color:var(--doc-pending-bg)]",
  uploaded: "bg-[color:var(--doc-uploaded-bg)]",
  in_review: "bg-[color:var(--doc-in-review-bg)]",
  approved: "bg-[color:var(--doc-approved-bg)]",
  rejected: "bg-[color:var(--doc-rejected-bg)]",
  expired: "bg-[color:var(--doc-expired-bg)]",
  needs_review: "bg-[color:var(--doc-needs-review-bg)]",
};

export function EvidenceSlotCard({
  title,
  institution,
  periodLabel,
  state,
  stateLabel,
  dueInDays,
  href,
  isReplacement,
  index,
  className,
}: EvidenceSlotCardProps) {
  const resolvedStateLabel = stateLabel ?? STATE_LABEL_FALLBACK[state];
  const dueChip = renderDueChip(dueInDays);
  return (
    <Link
      href={href}
      className={cn(
        "cw-fade-up cw-hover-lift group flex h-full min-w-0 flex-col gap-2 overflow-hidden rounded-md p-4",
        "border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]",
        "shadow-xs focus:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]/40 focus-visible:ring-offset-2 focus-visible:ring-offset-[color:var(--surface-page)]",
        className,
      )}
      style={index != null ? ({ "--cw-index": index } as React.CSSProperties) : undefined}
      aria-label={`${title} · ${institution} · ${resolvedStateLabel}`}
    >
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
            {institution}
          </span>
          {periodLabel ? (
            <>
              <span aria-hidden="true" className="text-[color:var(--text-tertiary)]">
                ·
              </span>
              <span className="font-mono text-[10px] tracking-wide text-[color:var(--text-secondary)]">
                {periodLabel}
              </span>
            </>
          ) : null}
          {isReplacement ? (
            <Tooltip content="Reemplaza un intento previo" side="top">
              <span
                className="ml-auto inline-flex items-center gap-1 rounded-full border border-[color:var(--border-subtle)] px-1.5 py-0.5 text-[10px] text-[color:var(--text-tertiary)]"
                aria-label="Reemplaza intento previo"
              >
                <ArrowsClockwise className="h-2.5 w-2.5" weight="bold" aria-hidden="true" />
                Reemplazo
              </span>
            </Tooltip>
          ) : null}
        </div>

        <p className="line-clamp-2 text-[13px] font-medium leading-[1.35] text-[color:var(--text-primary)]">
          {title}
        </p>

        <div className="mt-auto flex items-center justify-between gap-2">
          <span
            className={cn(
              "inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium",
              STATE_BG_CLASS[state],
              STATE_TEXT_CLASS[state],
            )}
          >
            {resolvedStateLabel}
          </span>
          {dueChip}
          <ArrowRight
            className="h-3.5 w-3.5 shrink-0 text-[color:var(--text-tertiary)] transition-transform duration-fast group-hover:translate-x-0.5 group-hover:text-[color:var(--text-brand)]"
            weight="bold"
            aria-hidden="true"
          />
        </div>
      </div>
    </Link>
  );
}


function renderDueChip(days: number | null | undefined) {
  if (days === null || days === undefined) return null;
  const overdue = days < 0;
  const urgent = !overdue && days <= 5;
  const className = overdue
    ? "border-[color:var(--status-error-border)] bg-[color:var(--status-error-bg)] text-[color:var(--status-error-text)]"
    : urgent
      ? "border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-bg)] text-[color:var(--status-warning-text)]"
      : "border-[color:var(--border-subtle)] bg-[color:var(--surface-sunken)] text-[color:var(--text-secondary)]";
  const label = overdue
    ? `Vencido ${Math.abs(days)}d`
    : days === 0
      ? "Vence hoy"
      : `En ${days}d`;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 font-mono text-[10px] tabular-nums",
        className,
      )}
    >
      {label}
    </span>
  );
}
