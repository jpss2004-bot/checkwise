"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";

import { Button } from "@/components/ui/button";
import {
  type AdminSession,
  clearAdminSession,
  readAdminSession,
} from "@/lib/session/admin";

/**
 * Phase 8 — shared shell for the client portal pages.
 *
 * Gates the session, ensures the user has either ``client_admin``
 * or ``internal_admin``, then renders a top nav + body slot. The
 * actual data scoping happens server-side; the shell only redirects
 * users who shouldn't be on these pages.
 */

const NAV = [
  { href: "/client/dashboard", label: "Resumen" },
  { href: "/client/vendors", label: "Proveedores" },
  { href: "/client/calendar", label: "Calendario" },
  { href: "/client/submissions", label: "Entregas" },
  { href: "/client/activity", label: "Actividad" },
];

export function ClientShell({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [session, setSession] = useState<AdminSession | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const current = readAdminSession();
    if (!current) {
      router.replace("/admin/login");
      return;
    }
    if (
      !current.roles.includes("client_admin") &&
      !current.roles.includes("internal_admin")
    ) {
      router.replace("/admin");
      return;
    }
    setSession(current);
    setReady(true);
  }, [router]);

  function onLogout() {
    clearAdminSession();
    router.replace("/admin/login");
  }

  if (!ready || !session) return null;

  return (
    <main className="mx-auto max-w-7xl space-y-6 px-5 py-6">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-4">
        <div className="space-y-1">
          <p className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
            Cliente · {session.user.email}
          </p>
          <h1 className="text-xl font-semibold">{title}</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link
            href="/admin"
            className="text-xs text-muted-foreground hover:underline"
          >
            Inicio staff
          </Link>
          <Button type="button" variant="outline" size="sm" onClick={onLogout}>
            Cerrar sesión
          </Button>
        </div>
      </header>

      <nav className="flex flex-wrap gap-2 text-xs">
        {NAV.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={
                "rounded-full border px-3 py-1.5 font-medium transition-colors " +
                (active
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border bg-white text-muted-foreground hover:bg-muted")
              }
            >
              {item.label}
            </Link>
          );
        })}
      </nav>

      <section>{children}</section>
    </main>
  );
}
