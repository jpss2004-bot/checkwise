import { Badge } from "@/components/ui/badge";
import type { RequirementStatus } from "@/lib/portal-client";

const STATUS_LABELS: Record<RequirementStatus, string> = {
  pendiente: "Pendiente",
  recibido: "Recibido",
  pendiente_revision: "Pendiente de revisión",
  prevalidado: "Prevalidado",
  posible_mismatch: "Posible mismatch",
  aprobado: "Aprobado",
  rechazado: "Rechazado",
  vencido: "Vencido",
  no_aplica: "No aplica",
  requiere_aclaracion: "Requiere aclaración",
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

export function RequirementStatusBadge({ status }: { status: RequirementStatus }) {
  return (
    <Badge variant={STATUS_VARIANT[status]} data-status={status}>
      {STATUS_LABELS[status]}
    </Badge>
  );
}
