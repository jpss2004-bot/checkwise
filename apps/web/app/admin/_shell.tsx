"use client";

import { Suspense } from "react";
import {
  Books,
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
  { href: "/admin/contact-requests", label: "Solicitudes", icon: EnvelopeSimple, roles: STAFF_ROLES },
  { href: "/admin/correction-requests", label: "Correcciones", icon: PencilSimple, roles: STAFF_ROLES },
  { href: "/admin/audit-log", label: "Audit log", icon: ListMagnifyingGlass, roles: STAFF_ROLES },
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
}) {
  return (
    <ConsoleShell
      gate={{
        // Operaciones is the staff console; anyone else is bounced to
        // /admin, which re-routes them to their own surface.
        roles: STAFF_ROLES,
        onDenied: () => "/admin",
      }}
      surfaceLabel="Operaciones internas"
      homeHref="/admin"
      pageEyebrow="Admin · CheckWise"
      footerLabel="Operaciones internas · Legal Shelf · CheckWise"
      navAriaLabel="Operaciones admin"
      nav={{ primary: PRIMARY_NAV, secondary: SECONDARY_NAV, settings: SETTINGS_NAV }}
      searchResultsHref="/admin/buscar"
      profileHref="/admin/configuracion/cuenta"
      profileLabel="Mi cuenta"
      // The superadmin also has the Plataforma console; the review team
      // (platform_admin) is not a superadmin, so don't dangle a switch
      // into a console the API would 403.
      shellSwitch={(session) =>
        session.roles.includes("operations_admin")
          ? { href: "/platform/dashboard", label: "Cambiar a Plataforma" }
          : null
      }
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
