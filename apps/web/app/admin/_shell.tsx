"use client";

import { Suspense } from "react";
import {
  Books,
  Bug,
  CalendarBlank,
  ChartLineUp,
  ClipboardText,
  EnvelopeSimple,
  Gauge,
  Gear,
  IdentificationCard,
  ListMagnifyingGlass,
  PencilSimple,
  Storefront,
  Table,
  UsersThree,
} from "@phosphor-icons/react";

import { AdminWiseMount } from "@/components/checkwise/wise/admin-wise-mount";
import {
  ConsoleShell,
  type ConsoleNavItem,
} from "@/components/checkwise/shell/console-shell";

/**
 * AdminShell — the Operaciones console (staff: review team + superadmin).
 *
 * A thin config over the shared ``<ConsoleShell>`` (audit Move 4 / F13):
 * the header, drawer, footer, MetadataStrip, search, user menu, and the
 * primary/overflow/settings nav all live in that component now. This
 * file just declares the Operaciones nav + the staff entry gate.
 */

// CheckWise staff = review team (platform_admin) + superadmin
// (operations_admin). Mirror of the backend ``STAFF_ROLES`` set
// (``apps/api/app/constants/roles.py``).
const STAFF_ROLES = ["platform_admin", "operations_admin"] as const;

// Superadmin-only surfaces (account provisioning + the user directory,
// product-feedback triage). The backend gates these on operations_admin
// (the ``PlatformUser`` dependency); the matching nav entries + a tighter
// page gate (``requireRoles`` below) keep the review team (platform_admin)
// out of a UI the API would only 403. These moved here from the retired
// /platform console (2026-06-30 consolidation into one Operaciones console).
const SUPERADMIN_ROLES = ["operations_admin"] as const;

// Day-to-day decision loop — the ≤7 surfaces a staffer touches every
// shift. ``GET /admin/*`` authorizes both staff roles, so every item is
// gated to STAFF_ROLES and the nav never dangles a link the API 403s.
const PRIMARY_NAV: ConsoleNavItem[] = [
  { href: "/admin/dashboard", label: "Resumen", icon: Gauge, roles: STAFF_ROLES },
  { href: "/admin/clients", label: "Clientes", icon: IdentificationCard, roles: STAFF_ROLES },
  { href: "/admin/vendors", label: "Proveedores", icon: Storefront, roles: STAFF_ROLES },
  { href: "/admin/requirements", label: "Requisitos", icon: Books, roles: STAFF_ROLES },
  { href: "/admin/calendar", label: "Calendario", icon: CalendarBlank, roles: STAFF_ROLES },
  { href: "/admin/reviewer", label: "Bandeja", icon: ClipboardText, roles: STAFF_ROLES },
  { href: "/admin/reports", label: "Reportes", icon: ChartLineUp, roles: STAFF_ROLES },
];

// Occasional / administrative surfaces — collapsed into the "Más"
// overflow so the primary row doesn't sprawl back to 11 chips (audit
// F10). The audit log lives here because ``roles.py`` grants
// ``platform_admin`` a documented read permission it otherwise had no UI
// path to (audit F2).
const SECONDARY_NAV: ConsoleNavItem[] = [
  // Account provisioning + the user directory — superadmin-only. Moved
  // here from the retired /platform console (2026-06-30 consolidation).
  { href: "/admin/cuentas", label: "Cuentas", icon: UsersThree, roles: SUPERADMIN_ROLES },
  { href: "/admin/contact-requests", label: "Solicitudes", icon: EnvelopeSimple, roles: STAFF_ROLES },
  { href: "/admin/correction-requests", label: "Correcciones", icon: PencilSimple, roles: STAFF_ROLES },
  // Audit metadata-rules — a fully-built rulebook page that previously had
  // no nav entry (audit routing-nav "Orphan route /admin/metadata").
  { href: "/admin/metadata", label: "Metadata", icon: Table, roles: STAFF_ROLES },
  { href: "/admin/audit-log", label: "Audit log", icon: ListMagnifyingGlass, roles: STAFF_ROLES },
  // Product-feedback triage — superadmin-only, also moved from /platform.
  { href: "/admin/feedback-reports", label: "Feedback", icon: Bug, roles: SUPERADMIN_ROLES },
];

// Settings keeps a dedicated gear anchor in the primary row (audit F11).
const SETTINGS_NAV: ConsoleNavItem = {
  href: "/admin/configuracion",
  label: "Configuración",
  icon: Gear,
  roles: STAFF_ROLES,
};

export function AdminShell({
  title,
  description,
  actions,
  children,
  unframed = false,
  requireRoles = STAFF_ROLES,
}: {
  title?: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  /**
   * When true, skip the shell's internal page header (eyebrow, title,
   * description, actions, MetadataStrip). Use this when the page renders
   * its own complete header — e.g. the shared <ReportEditor>.
   */
  unframed?: boolean;
  /**
   * Tighten the entry gate for superadmin-only sub-sections that live in
   * the Operaciones chrome (account provisioning, feedback triage). Defaults
   * to both staff roles; pass ``["operations_admin"]`` to fence the review
   * team out of a page whose API is operations_admin-only. A denied staffer
   * lands on the Operaciones home rather than a dead /login bounce.
   */
  requireRoles?: readonly string[];
}) {
  return (
    <ConsoleShell
      gate={{
        // Operaciones is the staff console. A staffer who lacks the tighter
        // (superadmin) role lands on the Operaciones home; anyone non-staff
        // is bounced to /admin, which re-routes them to their own surface.
        roles: requireRoles,
        onDenied: (session) =>
          STAFF_ROLES.some((role) => session.roles.includes(role))
            ? "/admin/dashboard"
            : "/admin",
      }}
      surfaceLabel="Operaciones internas"
      homeHref="/admin"
      pageEyebrow="Admin · CheckWise"
      footerLabel="Operaciones internas · Legal Shelf · CheckWise"
      navAriaLabel="Operaciones admin"
      nav={{ primary: PRIMARY_NAV, secondary: SECONDARY_NAV, settings: SETTINGS_NAV }}
      searchResultsHref="/admin/buscar"
      profileHref="/admin/configuracion"
      profileLabel="Mi cuenta"
      // Wise mounts only when the URL carries a ``?client_id=`` so the
      // backend's _resolve_client_id can scope answers; hidden on
      // cross-tenant pages like the admin dashboard.
      footerSlot={
        <Suspense fallback={null}>
          <AdminWiseMount />
        </Suspense>
      }
      title={title}
      description={description}
      actions={actions}
      unframed={unframed}
    >
      {children}
    </ConsoleShell>
  );
}
