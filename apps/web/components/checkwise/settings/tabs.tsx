import {
  Bell,
  Buildings,
  IdentificationCard,
  Users,
} from "@phosphor-icons/react";

import { withClientId } from "@/lib/navigation/with-client-id";

import type { SettingsTab } from "./settings-nav";

/**
 * Single source of truth for the per-surface "Configuración" hub IA
 * (audit Move 2). Keeping the tab lists here means the staff and client
 * settings pages — and any future tab — stay in sync instead of each
 * page hand-rolling its own nav array.
 */

// Staff (AdminShell) hub. "Mi cuenta" (identity + password) is the new
// screen the audit called for; "Notificaciones" reuses the role-agnostic
// preferences panel. The superadmin reaches user provisioning, feedback,
// etc. via the Plataforma switcher — those are not personal settings.
export const STAFF_SETTINGS_TABS: readonly SettingsTab[] = [
  {
    href: "/admin/configuracion",
    label: "Mi cuenta",
    icon: IdentificationCard,
  },
  {
    href: "/admin/configuracion/notificaciones",
    label: "Notificaciones",
    icon: Bell,
  },
];

/**
 * Client (ClientShell) hub. Folds the three previously-scattered client
 * settings homes (onboarding company profile, seats, notification prefs)
 * into one tabbed surface plus the new "Mi cuenta" (audit F7). Hrefs
 * carry the active ``?client_id=`` so staff break-glass sessions stay
 * scoped. ``client_viewer`` sees every tab; the management controls
 * inside are server-enforced and hidden client-side.
 */
export function clientSettingsTabs(
  clientId: string | null,
): SettingsTab[] {
  return [
    {
      href: withClientId("/client/configuracion", clientId),
      label: "Mi cuenta",
      icon: IdentificationCard,
    },
    {
      href: withClientId("/client/configuracion/usuarios", clientId),
      label: "Usuarios y accesos",
      icon: Users,
    },
    {
      href: withClientId("/client/configuracion/notificaciones", clientId),
      label: "Notificaciones",
      icon: Bell,
    },
    {
      href: withClientId("/client/onboarding", clientId),
      label: "Datos de la empresa",
      icon: Buildings,
    },
  ];
}
