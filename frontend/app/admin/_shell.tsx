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
 * Phase 7 — shared shell for the new admin operations pages.
 *
 * Plain, operational, no redesign. Provides:
 *   * gate: redirects to /admin/login if no session, to /admin if the
 *     user lacks the ``internal_admin`` role
 *   * top nav with links to every admin operations page
 *   * a slot for the page body
 *
 * Keeping this self-contained means each page file stays ~one screen
 * of code. Reviewer pages already render through their own shells.
 */

const NAV = [
  { href: "/admin/dashboard", label: "Resumen" },
  { href: "/admin/clients", label: "Clientes" },
  { href: "/admin/vendors", label: "Proveedores" },
  { href: "/admin/requirements", label: "Requisitos" },
  { href: "/admin/calendar", label: "Calendario" },
  { href: "/admin/audit-log", label: "Audit log" },
];

export function AdminShell({
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
    if (!current.roles.includes("internal_admin")) {
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
            Admin · {session.user.email}
          </p>
          <h1 className="text-xl font-semibold">{title}</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link
            href="/admin"
            className="text-xs text-muted-foreground hover:underline"
          >
            Inicio admin
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
