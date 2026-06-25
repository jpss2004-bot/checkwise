"use client";

/**
 * Phase 7 / Slice N8b — client_admin notification preferences page,
 * folded into the Configuración hub (audit Move 2 / F7).
 *
 * Mounts the shared :class:`NotificationPreferencesPanel` inside the
 * `ClientShell`. The panel handles all of: channel preference, phone
 * verification (OTP), and per-category mute matrix.
 *
 * Auth: gated by ClientShell — which redirects to /login when the
 * staff JWT is missing or expired. The panel itself calls
 * GET/PUT /api/v1/me/notification-preferences with the same JWT.
 */

import { NotificationPreferencesPanel } from "@/components/checkwise/notifications/notification-preferences-panel";
import { SettingsNav } from "@/components/checkwise/settings/settings-nav";
import { clientSettingsTabs } from "@/components/checkwise/settings/tabs";
import { useUrlClientId } from "@/lib/workspace/use-url-client-id";

import { ClientShell } from "../../_shell";

export default function ClientNotificationSettingsPage() {
  const urlClientId = useUrlClientId();
  return (
    <ClientShell
      title="Configuración"
      description="Decide cómo quieres recibir tus avisos (correo, WhatsApp, o ambos) y silencia categorías que no te interesen."
    >
      <div className="space-y-5">
        <SettingsNav tabs={clientSettingsTabs(urlClientId)} />
        <NotificationPreferencesPanel />
      </div>
    </ClientShell>
  );
}
