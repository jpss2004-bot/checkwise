"use client";

import {
  Bug,
  Gauge,
  ListMagnifyingGlass,
  UserPlus,
  UsersThree,
} from "@phosphor-icons/react";

import {
  ConsoleShell,
  type ConsoleNavItem,
} from "@/components/checkwise/shell/console-shell";

/**
 * PlatformShell — the Plataforma console (superadmin-only IT surface).
 *
 * A thin config over the shared ``<ConsoleShell>`` (audit Move 4 / F13),
 * sibling of ``AdminShell``. Carries the surfaces a superadmin uses
 * occasionally: user provisioning, audit log, feedback reports.
 *
 * Auth (2026-06-23 role redesign): superadmin-only — the backend
 * ``PlatformUser`` dependency requires ``operations_admin``, so the gate
 * matches it. The review team (``platform_admin``) is NOT admitted here
 * (user provisioning is a superadmin power); they work in the Operaciones
 * console and reach the audit log at ``/admin/audit-log``.
 */

const PLATFORM_NAV: ConsoleNavItem[] = [
  { href: "/platform/dashboard", label: "Resumen", icon: Gauge },
  { href: "/platform/users", label: "Usuarios", icon: UsersThree },
  { href: "/platform/users/new", label: "Nuevo usuario", icon: UserPlus },
  { href: "/platform/audit-log", label: "Audit log", icon: ListMagnifyingGlass },
  { href: "/platform/feedback-reports", label: "Feedback", icon: Bug },
];

export function PlatformShell({
  title,
  description,
  actions,
  children,
  unframed = false,
}: {
  title?: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  unframed?: boolean;
}) {
  return (
    <ConsoleShell
      gate={{
        // Superadmin-only. A review-team member (platform_admin) who
        // lands here is sent to their own Operaciones landing instead of
        // a dead /login bounce; anyone else re-authenticates.
        roles: ["operations_admin"],
        onDenied: (session) =>
          session.roles.includes("platform_admin")
            ? "/admin/dashboard"
            : "/login",
      }}
      surfaceLabel="Plataforma · TI"
      homeHref="/platform/dashboard"
      pageEyebrow="Plataforma · CheckWise"
      footerLabel="Plataforma interna · Legal Shelf · CheckWise"
      navAriaLabel="Plataforma"
      nav={{ primary: PLATFORM_NAV }}
      searchResultsHref="/admin/buscar"
      profileHref="/admin/configuracion/cuenta"
      profileLabel="Mi cuenta"
      // The superadmin always also has the Operaciones console (staff
      // superset), so offer the jump back there.
      shellSwitch={() => ({
        href: "/admin/dashboard",
        label: "Cambiar a Operaciones",
      })}
      title={title}
      description={description}
      actions={actions}
      unframed={unframed}
    >
      {children}
    </ConsoleShell>
  );
}
