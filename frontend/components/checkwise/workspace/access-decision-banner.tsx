import Link from "next/link";
import {
  ArrowRight,
  CheckCircle,
  HourglassHigh,
  Lock,
  ShieldWarning,
  WarningOctagon,
  type Icon,
} from "@phosphor-icons/react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import type { WorkspaceAccessOutcome } from "@/lib/workspace/types";

type AlertVariant = "info" | "success" | "warning" | "error";

interface BannerCopy {
  variant: AlertVariant;
  icon: Icon;
  title: string;
  body: string;
  cta?: { label: string; href: string };
}

function copyFor(outcome: WorkspaceAccessOutcome): BannerCopy | null {
  switch (outcome.decision) {
    case "allow":
      return null;

    case "allow_provisional":
      return {
        variant: "info",
        icon: HourglassHigh,
        title: "Tienes acceso provisional",
        body:
          "Tu expediente obligatorio está completo y CheckWise está revisando los documentos. Te avisaremos por correo cuando todo quede aprobado.",
        cta: { label: "Ver expediente", href: "/portal/onboarding" },
      };

    case "redirect_onboarding":
      return {
        variant: "warning",
        icon: ShieldWarning,
        title: "Te falta completar tu expediente inicial",
        body:
          "Tienes documentos obligatorios pendientes, rechazados o por revisión. Mientras tanto, no podemos darte acceso al dashboard.",
        cta: { label: "Ir al expediente", href: "/portal/onboarding" },
      };

    case "needs_confirmation":
      return {
        variant: "info",
        icon: ShieldWarning,
        title: "Confirma tu espacio antes de continuar",
        body:
          "Verifica que entras al workspace correcto. Es una salvaguarda contra accesos cruzados entre proveedores y clientes.",
        cta: { label: "Confirmar", href: "/portal/entra-a-tu-espacio" },
      };

    case "blocked": {
      const map: Record<typeof outcome.reason, { title: string; body: string }> = {
        invitation_expired: {
          title: "Tu invitación expiró",
          body:
            "Pide a quien te invitó que genere una nueva invitación. El acceso anterior ya no es válido.",
        },
        invitation_revoked: {
          title: "La invitación fue revocada",
          body:
            "El administrador retiró este acceso. Contacta a tu cliente o a soporte para más información.",
        },
        invitation_used: {
          title: "Este enlace ya fue usado",
          body:
            "Cada invitación se puede usar una sola vez. Si no recuerdas tu contraseña, contacta a soporte.",
        },
        company_mismatch: {
          title: "Detectamos un cruce de empresa",
          body:
            "El correo o RFC no coincide con la empresa de la invitación. Por seguridad bloqueamos el acceso hasta revisión humana.",
        },
        domain_mismatch: {
          title: "Tu correo no coincide con la empresa",
          body:
            "El dominio del correo no coincide con la empresa de la invitación. Verifica tus datos o contacta a quien te invitó.",
        },
        role_dispute: {
          title: "Conflicto de rol",
          body:
            "El rol propuesto no coincide con la invitación registrada. Esto requiere revisión humana antes de continuar.",
        },
        unknown_workspace: {
          title: "No reconocemos tu workspace",
          body:
            "No encontramos un workspace activo para tu sesión. Es posible que la invitación haya sido eliminada.",
        },
      };
      const entry = map[outcome.reason];
      return {
        variant: "error",
        icon: Lock,
        title: entry.title,
        body: entry.body,
        cta: { label: "Contactar soporte", href: "mailto:soporte@legalshelf.mx" },
      };
    }
  }
}

interface Props {
  outcome: WorkspaceAccessOutcome;
}

export function AccessDecisionBanner({ outcome }: Props) {
  const copy = copyFor(outcome);
  if (!copy) {
    return (
      <Alert variant="success">
        <AlertTitle className="flex items-center gap-2">
          <CheckCircle className="h-4 w-4" weight="fill" aria-hidden="true" />
          Acceso completo al portal
        </AlertTitle>
        <AlertDescription>
          Tu expediente está en regla. Sigue tu calendario REPSE y recibe alertas
          de cada vencimiento.
        </AlertDescription>
      </Alert>
    );
  }

  const IconComponent = copy.icon;
  return (
    <Alert variant={copy.variant}>
      <AlertTitle className="flex items-center gap-2">
        <IconComponent className="h-4 w-4" weight="bold" aria-hidden="true" />
        {copy.title}
      </AlertTitle>
      <AlertDescription className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <span>{copy.body}</span>
        {copy.cta && (
          <Button asChild size="sm" variant={copy.variant === "error" ? "outline" : "default"} className="shrink-0">
            <Link href={copy.cta.href}>
              <span>{copy.cta.label}</span>
              <ArrowRight className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
            </Link>
          </Button>
        )}
      </AlertDescription>
    </Alert>
  );
}

// Keep WarningOctagon import alive for future variant additions
void WarningOctagon;
