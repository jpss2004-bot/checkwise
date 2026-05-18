"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import {
  CalendarBlank,
  ClockClockwise,
  Files,
  Gauge,
  List,
  SignOut,
  Storefront,
  X,
  type Icon,
} from "@phosphor-icons/react";

import { BrandLogo } from "@/components/checkwise/brand-logo";
import { Button } from "@/components/ui/button";
import { MetadataStrip } from "@/components/ui/metadata-strip";
import { cn } from "@/lib/utils";
import {
  type AdminSession,
  clearAdminSession,
  readAdminSession,
} from "@/lib/session/admin";

/**
 * ClientShell — premium-dense cliente corporativo console (V2.1).
 *
 * Same architectural shape as AdminShell with the client palette.
 * Density: dense. Horizontal nav with drawer fallback <1024px.
 * Workspace identity rendered as MetadataStrip below the title.
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
  const [drawerOpen, setDrawerOpen] = useState(false);

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

  useEffect(() => {
    setDrawerOpen(false);
  }, [pathname]);

  function onLogout() {
    clearAdminSession();
    router.replace("/admin/login");
  }

  if (!ready || !session) return null;

  return (
    <div
      data-density="dense"
      className="min-h-screen bg-[color:var(--surface-page)]"
    >
      <header className="sticky top-0 z-30 border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)]/95 backdrop-blur supports-[backdrop-filter]:bg-[color:var(--surface-raised)]/85">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-5 py-2.5">
          <Link href="/client/dashboard" aria-label="CheckWise · vista cliente">
            <BrandLogo size="md" />
          </Link>
          <span className="hidden h-6 w-px bg-[color:var(--border-subtle)] lg:block" />
          <p className="hidden font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-teal)] lg:block">
            Vista cliente · cumplimiento del portafolio
          </p>
          <div className="ml-auto flex items-center gap-2">
            <span className="hidden font-mono text-[11px] text-[color:var(--text-tertiary)] md:inline">
              {session.user.email}
            </span>
            <Button type="button" variant="outline" size="sm" onClick={onLogout}>
              <SignOut className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
              <span className="hidden sm:inline">Cerrar sesión</span>
            </Button>
            <button
              type="button"
              aria-label={drawerOpen ? "Cerrar menú" : "Abrir menú"}
              aria-expanded={drawerOpen}
              onClick={() => setDrawerOpen((open) => !open)}
              className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-[color:var(--border-subtle)] text-[color:var(--text-secondary)] transition-colors hover:bg-[color:var(--surface-hover)] lg:hidden"
            >
              {drawerOpen ? (
                <X className="h-4 w-4" weight="bold" />
              ) : (
                <List className="h-4 w-4" weight="bold" />
              )}
            </button>
          </div>
        </div>
        <nav
          aria-label="Portal cliente"
          className="mx-auto hidden max-w-7xl gap-1 overflow-x-auto px-3 pb-2 lg:flex"
        >
          {NAV.map((item) => {
            const isActive =
              pathname === item.href || pathname?.startsWith(item.href + "/");
            const IconComponent = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={isActive ? "page" : undefined}
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

      {drawerOpen ? (
        <div
          role="dialog"
          aria-label="Menú cliente"
          className="fixed inset-0 z-40 flex lg:hidden"
        >
          <button
            type="button"
            aria-label="Cerrar"
            onClick={() => setDrawerOpen(false)}
            className="absolute inset-0 bg-[color:var(--text-primary)]/40 backdrop-blur-sm"
          />
          <nav
            aria-label="Portal cliente"
            className="relative ml-auto flex h-full w-72 max-w-[85vw] flex-col gap-1 border-l border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)] p-4 shadow-lg"
          >
            <p className="cw-eyebrow mb-2">Navegación</p>
            {NAV.map((item) => {
              const isActive =
                pathname === item.href || pathname?.startsWith(item.href + "/");
              const IconComponent = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={isActive ? "page" : undefined}
                  className={cn(
                    "flex items-center gap-2 rounded-md border px-3 py-2 text-sm font-medium transition-colors",
                    isActive
                      ? "border-[color:var(--border-brand)] bg-[color:var(--surface-brand)] text-[color:var(--text-inverse)]"
                      : "border-transparent text-[color:var(--text-secondary)] hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--text-primary)]",
                  )}
                >
                  <IconComponent
                    className="h-4 w-4"
                    weight={isActive ? "fill" : "bold"}
                    aria-hidden="true"
                  />
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>
      ) : null}

      <main className="mx-auto max-w-7xl space-y-5 px-5 py-5">
        <header className="cw-fade-up space-y-3">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div className="min-w-0 space-y-1">
              <p className="cw-eyebrow">Cliente · CheckWise</p>
              <h1 className="text-[26px] font-semibold leading-tight tracking-tight text-[color:var(--text-primary)]">
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
          </div>
          <MetadataStrip
            items={[
              { label: "Usuario", value: session.user.full_name },
              { label: "Correo", value: session.user.email, mono: true },
              {
                label: "Rol",
                value: session.roles
                  .map((r) => r.replace(/_/g, " "))
                  .join(", "),
                mono: true,
                tone: "teal",
              },
            ]}
          />
        </header>
        <section>{children}</section>
      </main>

      <footer className="mx-auto max-w-7xl px-5 py-6 text-center font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
        Powered by Legal Shelf · CheckWise
      </footer>
    </div>
  );
}
