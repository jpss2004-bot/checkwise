"use client";

import { IdentificationCard } from "@phosphor-icons/react";

import { Surface } from "@/components/checkwise/dashboard/stat-card";
import { Badge } from "@/components/ui/badge";
import { roleLabel } from "@/lib/constants/labels";

/**
 * AccountIdentityCard — read-only display of the signed-in user's own
 * identity (audit Move 2, "Mi cuenta"). Shell-agnostic: rendered inside
 * both the staff (AdminShell) and client (ClientShell) settings hubs.
 *
 * Read-only by design for this pass — there is no self-service
 * ``PUT /me`` for name/email yet, so we show the values rather than
 * imply they're editable. Roles are de-duped on their display label via
 * ``roleLabel`` (audit F4).
 */
export function AccountIdentityCard({
  fullName,
  email,
  roles,
  lastLoginAt,
}: {
  fullName: string;
  email: string;
  roles: readonly string[];
  lastLoginAt?: string | null;
}) {
  const roleBadges = Array.from(new Set(roles.map(roleLabel)));

  return (
    <Surface
      title="Mi cuenta"
      icon={IdentificationCard}
      description="Los datos de tu cuenta. Para cambiar tu nombre o correo, escribe a soporte."
    >
      <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
        <Row label="Nombre">
          <span className="text-sm text-[color:var(--text-primary)]">
            {fullName || "—"}
          </span>
        </Row>
        <Row label="Correo">
          <span className="font-mono text-[13px] text-[color:var(--text-primary)]">
            {email}
          </span>
        </Row>
        <Row label="Acceso">
          {roleBadges.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {roleBadges.map((label) => (
                <Badge key={label} variant="outline">
                  {label}
                </Badge>
              ))}
            </div>
          ) : (
            <span className="text-sm text-[color:var(--text-tertiary)]">—</span>
          )}
        </Row>
        <Row label="Último ingreso">
          <span className="text-[13px] text-[color:var(--text-secondary)]">
            {lastLoginAt
              ? new Date(lastLoginAt).toLocaleString("es-MX")
              : "—"}
          </span>
        </Row>
      </dl>
    </Surface>
  );
}

function Row({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <dt className="cw-eyebrow">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}
