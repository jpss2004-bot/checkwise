import Link from "next/link";
import {
  ArrowRight,
  Buildings,
  IdentificationCard,
  PaperPlaneTilt,
  Stamp,
  Truck,
  type Icon,
} from "@phosphor-icons/react";

import { ProtectedFieldNotice } from "@/components/checkwise/workspace/protected-field-notice";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { WorkspaceContext } from "@/lib/workspace/types";

interface Props {
  workspace: WorkspaceContext;
  /** Show a "Reportar información incorrecta" link. Defaults true. */
  showCorrectionLink?: boolean;
  /** Hide the "Revisar mi expediente" link (e.g. when already on the gate). */
  hideExpedienteLink?: boolean;
}

const ROLE_ICON: Record<WorkspaceContext["protected"]["role"], Icon> = {
  provider: Truck,
  client: Buildings,
};

const ROLE_LABEL: Record<WorkspaceContext["protected"]["role"], string> = {
  provider: "Proveedor",
  client: "Cliente",
};

/**
 * Tenant-identity summary used on /portal/dashboard and embedded by
 * /portal/entra-a-tu-espacio. Mixes "free to display" headlines with
 * `ProtectedFieldNotice` for fields that need an explicit lock.
 *
 * Spec: docs/CHECKWISE_1_6.md §9 (Dashboard workspace context).
 */
export function WorkspaceIdentityCard({
  workspace,
  showCorrectionLink = true,
  hideExpedienteLink = false,
}: Props) {
  const RoleIcon = ROLE_ICON[workspace.protected.role];
  return (
    <section className="cw-fade-up rounded-xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-5 shadow-xs sm:p-6">
      <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <span
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[color:var(--surface-brand-muted)]"
            aria-hidden="true"
          >
            <RoleIcon
              className="h-5 w-5 text-[color:var(--text-brand)]"
              weight="duotone"
            />
          </span>
          <div className="min-w-0">
            <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-teal)]">
              Tu espacio en CheckWise
            </p>
            <h2 className="text-base font-semibold text-[color:var(--text-primary)]">
              {workspace.protected.company_legal_name}
            </h2>
            <p className="mt-0.5 text-xs text-[color:var(--text-secondary)]">
              {workspace.invitation_hints.inviter
                ? `Invitado por ${workspace.invitation_hints.inviter}`
                : "Workspace creado por tu cliente"}
            </p>
          </div>
        </div>
        <Badge variant="brand">{ROLE_LABEL[workspace.protected.role]}</Badge>
      </header>

      <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <ProtectedFieldNotice
          label="Rol asignado"
          value={ROLE_LABEL[workspace.protected.role]}
          helper="Definido por la invitación."
        />
        <ProtectedFieldNotice
          label="RFC"
          value={workspace.protected.rfc ?? ""}
          mono
          helper={workspace.protected.rfc ? "Locked al alta." : "Aún no registrado."}
        />
        <ProtectedFieldNotice
          label="Razón social"
          value={workspace.protected.company_legal_name}
          helper="Locked al alta. Solicita corrección si difiere."
        />
        <ProtectedFieldNotice
          label="Workspace"
          value={workspace.protected.workspace_id}
          mono
          helper="Identificador interno."
        />
      </dl>

      <footer className="mt-5 flex flex-wrap items-center gap-2 border-t border-[color:var(--border-subtle)] pt-4">
        {!hideExpedienteLink && (
          <Button asChild variant="outline" size="sm">
            <Link href="/portal/onboarding">
              <Stamp className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
              <span>Revisar mi expediente</span>
              <ArrowRight className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
            </Link>
          </Button>
        )}
        {showCorrectionLink && (
          <Button asChild variant="ghost" size="sm">
            <Link href="/portal/entra-a-tu-espacio#correccion">
              <IdentificationCard className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
              <span>Reportar información incorrecta</span>
            </Link>
          </Button>
        )}
        <p className="ml-auto inline-flex items-center gap-1.5 text-[11px] text-[color:var(--text-tertiary)]">
          <PaperPlaneTilt className="h-3 w-3" weight="bold" aria-hidden="true" />
          Cambios sensibles pasan por revisión.
        </p>
      </footer>
    </section>
  );
}
