import { Badge, type BadgeProps } from "@/components/ui/badge";
import type { RequirementStatus } from "@/lib/api/portal";
import {
  STATUS_EXPLAINER_ES,
  STATUS_LABELS_ES,
  type DocumentStatusCode,
} from "@/lib/constants/statuses";

// Maps each canonical workflow status to a Badge doc-state variant so the
// rendered color comes from --doc-* / --status-* tokens (one source of truth)
// rather than collapsing 11 statuses into 5 generic buckets. Mapping mirrors
// the SlotState taxonomy in docs/EVIDENCE_SLOTS.md so all status surfaces
// (calendar, checklist, queue, detail) read consistently.
const STATUS_VARIANT: Record<RequirementStatus, NonNullable<BadgeProps["variant"]>> = {
  pendiente: "doc-empty",
  recibido: "doc-uploaded",
  pendiente_revision: "doc-in-review",
  prevalidado: "doc-in-review",
  posible_mismatch: "doc-needs-review",
  aprobado: "doc-approved",
  rechazado: "doc-rejected",
  vencido: "doc-expired",
  no_aplica: "outline",
  requiere_aclaracion: "doc-needs-review",
  excepcion_legal: "info",
};

export function RequirementStatusBadge({ status }: { status: RequirementStatus }) {
  // Labels + explainers come from the central statuses dictionary so a
  // vocabulary change in one place propagates across every surface
  // (badge, calendar, dashboard, queue, timeline, reports).
  const label = STATUS_LABELS_ES[status as DocumentStatusCode] ?? status;
  const explainer = STATUS_EXPLAINER_ES[status as DocumentStatusCode] ?? "";
  return (
    <Badge
      variant={STATUS_VARIANT[status]}
      data-status={status}
      title={explainer}
      aria-label={explainer ? `${label}: ${explainer}` : label}
    >
      {label}
    </Badge>
  );
}
