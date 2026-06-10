import {
  CheckCircle,
  CircleDashed,
  Clock,
  FileMagnifyingGlass,
  HourglassHigh,
  Tray,
  Warning,
  XCircle,
  type Icon,
} from "@phosphor-icons/react";

import { Badge } from "@/components/ui/badge";
import type { DocumentStateCode } from "@/lib/types";

/**
 * Plain-language Spanish labels for the 8 REPSE document states.
 * Drives badges, status pills, and any inline state text. Single source
 * of truth — never spell these out inline.
 *
 * Spec: docs/DESIGN_SYSTEM.md §3.1 (Document States) + §6.1 (Onboarding).
 */
export const DOC_STATE_LABELS: Record<DocumentStateCode, string> = {
  // Canonical wording unification (2026-06-10) — mirrors slotStateLabel()
  // in @/lib/constants/statuses so providers read the same words as
  // clients. `uploaded` collapses into "En revisión" alongside in_review.
  empty: "Por entregar",
  pending: "Por entregar",
  uploaded: "En revisión",
  in_review: "En revisión",
  approved: "Aprobado",
  rejected: "Requiere corrección",
  expired: "Vencido",
  needs_review: "Necesita aclaración",
};

const DOC_STATE_ICON: Record<DocumentStateCode, Icon> = {
  empty: CircleDashed,
  pending: Clock,
  uploaded: Tray,
  in_review: HourglassHigh,
  approved: CheckCircle,
  rejected: XCircle,
  expired: Warning,
  needs_review: FileMagnifyingGlass,
};

const DOC_STATE_VARIANT: Record<
  DocumentStateCode,
  | "doc-pending"
  | "doc-uploaded"
  | "doc-in-review"
  | "doc-approved"
  | "doc-rejected"
  | "doc-expired"
  | "doc-needs-review"
  | "doc-empty"
> = {
  empty: "doc-empty",
  pending: "doc-pending",
  uploaded: "doc-uploaded",
  in_review: "doc-in-review",
  approved: "doc-approved",
  rejected: "doc-rejected",
  expired: "doc-expired",
  needs_review: "doc-needs-review",
};

interface DocStateBadgeProps {
  state: DocumentStateCode;
  /** Override the default Spanish label. */
  label?: string;
  /** Hide the icon for very compact contexts (default: show). */
  withIcon?: boolean;
  className?: string;
}

export function DocStateBadge({
  state,
  label,
  withIcon = true,
  className,
}: DocStateBadgeProps) {
  const IconComponent = DOC_STATE_ICON[state];
  return (
    <Badge variant={DOC_STATE_VARIANT[state]} className={className}>
      {withIcon && <IconComponent className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />}
      <span>{label ?? DOC_STATE_LABELS[state]}</span>
    </Badge>
  );
}
