"use client";

/**
 * /admin/configuracion — staff "Mi cuenta" (audit Move 2 / F6).
 *
 * Fills the gap where staff had no settings or account surface at all
 * (``profileHref`` was hard-wired to ``null``). Read-only identity plus
 * self-service password change; notification preferences live on the
 * sibling tab. Reachable from the Operaciones nav "Configuración" entry
 * and the user-menu "Mi cuenta" link, both gated to STAFF_ROLES by the
 * shell.
 */

import { useEffect, useState } from "react";

import { AccountIdentityCard } from "@/components/checkwise/settings/account-identity-card";
import { ChangePasswordCard } from "@/components/checkwise/settings/change-password-card";
import { SettingsNav } from "@/components/checkwise/settings/settings-nav";
import { STAFF_SETTINGS_TABS } from "@/components/checkwise/settings/tabs";
import { readAdminSession, type AdminSession } from "@/lib/session/admin";

import { AdminShell } from "../_shell";

export default function AdminAccountSettingsPage() {
  const [session, setSession] = useState<AdminSession | null>(null);
  useEffect(() => {
    setSession(readAdminSession());
  }, []);

  return (
    <AdminShell
      title="Configuración"
      description="Administra tu cuenta y tus preferencias en CheckWise."
    >
      <div className="space-y-5">
        <SettingsNav tabs={STAFF_SETTINGS_TABS} />
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
    </AdminShell>
  );
}
