"use client";

/**
 * /admin/configuracion/notificaciones — staff notification preferences
 * (audit Move 2). Mounts the shared, role-agnostic
 * :class:`NotificationPreferencesPanel` (GET/PUT /me/notification-
 * preferences works for staff too) inside the Operaciones settings hub.
 */

import { NotificationPreferencesPanel } from "@/components/checkwise/notifications/notification-preferences-panel";
import { SettingsNav } from "@/components/checkwise/settings/settings-nav";
import { STAFF_SETTINGS_TABS } from "@/components/checkwise/settings/tabs";

import { AdminShell } from "../../_shell";

export default function AdminNotificationSettingsPage() {
  return (
    <AdminShell
      title="Configuración"
      description="Decide cómo quieres recibir tus avisos (correo, WhatsApp, o ambos) y silencia categorías que no te interesen."
    >
      <div className="space-y-5">
        <SettingsNav tabs={STAFF_SETTINGS_TABS} />
        <NotificationPreferencesPanel />
      </div>
    </AdminShell>
  );
}
