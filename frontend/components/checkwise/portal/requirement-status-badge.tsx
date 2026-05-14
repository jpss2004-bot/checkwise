import { Badge } from "@/components/ui/badge";
import type { RequirementStatus } from "@/lib/portal-client";

const STATUS_LABELS: Record<RequirementStatus, string> = {
  pendiente: "Pendiente",
  recibido: "Recibido",
  pendiente_revision: "Esperando revisión",
  prevalidado: "Prevalidado",
  posible_mismatch: "Posible inconsistencia",
  aprobado: "Aprobado",
  rechazado: "Rechazado",
  vencido: "Vencido",
  no_aplica: "No aplica",
  requiere_aclaracion: "Necesita aclaración",
  excepcion_legal: "Excepción legal",
};

const STATUS_VARIANT: Record<
  RequirementStatus,
  "default" | "secondary" | "outline" | "warning" | "destructive"
> = {
  pendiente: "outline",
  recibido: "secondary",
  pendiente_revision: "default",
  prevalidado: "default",
  posible_mismatch: "warning",
  aprobado: "default",
  rechazado: "destructive",
  vencido: "destructive",
  no_aplica: "outline",
  requiere_aclaracion: "warning",
  excepcion_legal: "warning",
};

const STATUS_DESCRIPTIONS: Record<RequirementStatus, string> = {
  pendiente: "Aún no hemos recibido este documento. Cárgalo para que entre a revisión.",
  recibido: "Recibimos tu archivo. Pasará a revisión humana en breve.",
  pendiente_revision: "Tu archivo está en la fila de revisión. No necesitas hacer nada por ahora.",
  prevalidado: "Pasó las prevalidaciones automáticas. Falta la revisión humana final.",
  posible_mismatch:
    "El archivo parece no coincidir con el requisito, periodo o RFC esperado. Verifica antes de continuar.",
  aprobado: "Aprobado por la revisión humana. No requiere más acción.",
  rechazado: "Rechazado en revisión. Revisa los comentarios y vuelve a cargar el documento correcto.",
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
