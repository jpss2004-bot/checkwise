"use client";

/**
 * Phase 7 / Slice N8b — client_admin notification preferences page.
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

import { ClientShell } from "../../_shell";

export default function ClientNotificationSettingsPage() {
  return (
    <ClientShell
      title="Preferencias de notificaciones"
      description="Decide cómo quieres recibir tus avisos (correo, WhatsApp, o ambos) y silencia categorías que no te interesen."
    >
      <NotificationPreferencesPanel />
    </ClientShell>
  );
}
