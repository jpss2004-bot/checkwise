import { Badge, type BadgeProps } from "@/components/ui/badge";
import type { RequirementStatus } from "@/lib/api/portal";

const STATUS_LABELS: Record<RequirementStatus, string> = {
  pendiente: "Pendiente",
  recibido: "Recibido",
  pendiente_revision: "Esperando revisión",
  prevalidado: "Prevalidado",
  posible_mismatch: "Posible inconsistencia",
  aprobado: "Aprobado",
  // Audit P1-02 (2026-05-25) — softened from "Rechazado" so the
  // badge invites the provider to act rather than feel rejected.
  // Backend status code stays ``rechazado``; this is a UX-copy-only
  // change. The longer status detail (STATUS_DESCRIPTIONS) keeps
  // the verb form "fue rechazado" which is correct in narrative
  // context but reads harsh as a noun on a pill.
  rechazado: "Requiere corrección",
  vencido: "Vencido",
  no_aplica: "No aplica",
  requiere_aclaracion: "Necesita aclaración",
  excepcion_legal: "Excepción legal",
};

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

const STATUS_DESCRIPTIONS: Record<RequirementStatus, string> = {
  pendiente: "Aún no hemos recibido este documento. Cárgalo para que entre a revisión.",
  recibido: "Recibimos tu archivo. Pasará a revisión humana en breve.",
  pendiente_revision: "Tu archivo está en la fila de revisión. No necesitas hacer nada por ahora.",
  prevalidado: "Pasó las prevalidaciones automáticas. Falta la revisión humana final.",
  posible_mismatch:
    "El archivo parece no coincidir con el requisito, periodo o RFC esperado. Verifica antes de continuar.",
  aprobado: "Aprobado por la revisión humana. No requiere más acción.",
  rechazado:
    "Necesita corrección. Revisa los comentarios del revisor y vuelve a cargar el documento correcto.",
  vencido: "El documento ya no cubre el periodo vigente. Sube la versión actualizada.",
  no_aplica: "Este requisito no aplica para tu caso.",
  requiere_aclaracion:
    "Necesitamos una aclaración antes de aprobar. Revisa los comentarios del revisor.",
  excepcion_legal:
    "Aprobado bajo excepción legal documentada. Conserva el sustento en tu expediente.",
};

export function RequirementStatusBadge({ status }: { status: RequirementStatus }) {
  return (
    <Badge
      variant={STATUS_VARIANT[status]}
      data-status={status}
      title={STATUS_DESCRIPTIONS[status]}
      aria-label={`${STATUS_LABELS[status]}: ${STATUS_DESCRIPTIONS[status]}`}
    >
      {STATUS_LABELS[status]}
    </Badge>
  );
}
