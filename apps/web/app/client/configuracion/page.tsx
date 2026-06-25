"use client";

/**
 * /client/configuracion — client "Mi cuenta" + the hub index (audit
 * Move 2 / F7). The tabbed home for what used to be three scattered,
 * avatar-menu-only pages (company profile, seats, notification prefs),
 * now with a real nav entry and a new self-service account screen.
 */

import { useEffect, useState } from "react";

import { AccountIdentityCard } from "@/components/checkwise/settings/account-identity-card";
import { ChangePasswordCard } from "@/components/checkwise/settings/change-password-card";
import { SettingsNav } from "@/components/checkwise/settings/settings-nav";
import { clientSettingsTabs } from "@/components/checkwise/settings/tabs";
import { useUrlClientId } from "@/lib/workspace/use-url-client-id";
import { readAdminSession, type AdminSession } from "@/lib/session/admin";

import { ClientShell } from "../_shell";

export default function ClientAccountSettingsPage() {
  const urlClientId = useUrlClientId();
  const [session, setSession] = useState<AdminSession | null>(null);
  useEffect(() => {
    setSession(readAdminSession());
  }, []);

  return (
    <ClientShell
      title="Configuración"
      description="Tu cuenta, tu equipo y las preferencias de tu empresa, en un solo lugar."
    >
      <div className="space-y-5">
        <SettingsNav tabs={clientSettingsTabs(urlClientId)} />
        {session ? (
          <AccountIdentityCard
            fullName={session.user.full_name}
            email={session.user.email}
            roles={session.roles}
            lastLoginAt={session.user.last_login_at}
          />
        ) : null}
        <ChangePasswordCard />
      </div>
    </ClientShell>
  );
}
