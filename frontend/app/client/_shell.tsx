"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import {
  CalendarBlank,
  ClockClockwise,
  Files,
  Gauge,
  SignOut,
  Storefront,
  Buildings,
  type Icon,
} from "@phosphor-icons/react";

import { BrandLogo } from "@/components/checkwise/brand-logo";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  type AdminSession,
  clearAdminSession,
  readAdminSession,
} from "@/lib/session/admin";

/**
 * ClientShell — polished cliente corporativo console shell.
 *
 * Same architectural choice as AdminShell: brand mark + role context,
 * polished horizontal nav with icon affordance, right-side user chip
 * with role badges + sign-out. Keeps the top-nav layout (user picked
 * the hybrid sidebar-on-portal, top-nav-on-admin/client option).
 */

const NAV: { href: string; label: string; icon: Icon }[] = [
  { href: "/client/dashboard", label: "Resumen", icon: Gauge },
  { href: "/client/vendors", label: "Proveedores", icon: Storefront },
  { href: "/client/calendar", label: "Calendario", icon: CalendarBlank },
  { href: "/client/submissions", label: "Entregas", icon: Files },
  { href: "/client/activity", label: "Actividad", icon: ClockClockwise },
];

export function ClientShell({
  title,
  description,
  actions,
  children,
}: {
  title: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
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
    <div className="min-h-screen bg-[color:var(--surface-page)]">
      <header className="sticky top-0 z-30 border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)]/95 backdrop-blur supports-[backdrop-filter]:bg-[color:var(--surface-raised)]/85">
        <div className="mx-auto flex max-w-7xl items-center gap-4 px-5 py-3">
          <Link href="/client/dashboard" aria-label="CheckWise · vista cliente">
            <BrandLogo size="md" />
          </Link>
          <div className="hidden h-7 w-px bg-[color:var(--border-subtle)] sm:block" />
          <div className="hidden min-w-0 flex-1 sm:block">
            <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-teal)]">
              Vista cliente · cumplimiento de tus proveedores
            </p>
            <p className="truncate text-[13px] font-medium text-[color:var(--text-primary)]">
              <span className="font-mono">{session.user.email}</span>
              <span className="ml-2 text-[color:var(--text-tertiary)]">
                ·{" "}
                {session.roles
                  .map((r) => r.replace(/_/g, " "))
                  .join(", ")}
              </span>
            </p>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <Badge variant="teal" className="hidden md:inline-flex">
              <Buildings className="h-3 w-3" weight="bold" aria-hidden="true" />
              {session.user.full_name}
            </Badge>
            <Button type="button" variant="outline" size="sm" onClick={onLogout}>
              <SignOut className="h-4 w-4" weight="bold" aria-hidden="true" />
              <span className="hidden sm:inline">Cerrar sesión</span>
            </Button>
          </div>
        </div>
        <nav
          aria-label="Portal cliente"
          className="mx-auto flex max-w-7xl gap-1 overflow-x-auto px-3 pb-2"
        >
          {NAV.map((item) => {
            const isActive =
              pathname === item.href || pathname?.startsWith(item.href + "/");
            const IconComponent = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "inline-flex shrink-0 items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-[12px] font-medium transition-colors duration-fast",
                  isActive
                    ? "border-[color:var(--border-brand)] bg-[color:var(--surface-brand)] text-[color:var(--text-inverse)] shadow-xs"
                    : "border-transparent bg-transparent text-[color:var(--text-secondary)] hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--text-primary)]",
                )}
              >
                <IconComponent
                  className="h-3.5 w-3.5"
                  weight={isActive ? "fill" : "bold"}
                  aria-hidden="true"
                />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </header>

      <main className="mx-auto max-w-7xl space-y-6 px-5 py-6">
        <header className="cw-fade-up flex flex-wrap items-end justify-between gap-3 border-b border-[color:var(--border-subtle)] pb-4">
          <div className="min-w-0 space-y-1">
            <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-teal)]">
              Cliente · CheckWise
            </p>
            <h1 className="text-2xl font-semibold tracking-tight text-[color:var(--text-primary)]">
              {title}
            </h1>
            {description ? (
              <p className="max-w-prose text-[13px] text-[color:var(--text-secondary)]">
                {description}
              </p>
            ) : null}
          </div>
          {actions ? (
            <div className="flex flex-wrap gap-2">{actions}</div>
          ) : null}
        </header>
        <section>{children}</section>
      </main>

      <footer className="mx-auto max-w-7xl px-5 py-6 text-center font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
        Powered by Legal Shelf · CheckWise
      </footer>
    </div>
  );
}
