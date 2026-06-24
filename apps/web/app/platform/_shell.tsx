"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import {
  Bug,
  Gauge,
  List,
  ListMagnifyingGlass,
  UserPlus,
  UsersThree,
  X,
  type Icon,
} from "@phosphor-icons/react";

import { BackBar } from "@/components/checkwise/back-bar";
import { BrandLogo } from "@/components/checkwise/brand-logo";
import { FeedbackLauncher } from "@/components/feedback/feedback-launcher";
import { SearchBar } from "@/components/checkwise/search-bar";
import { UserMenu } from "@/components/checkwise/user-menu";
import { MetadataStrip } from "@/components/ui/metadata-strip";
import { roleLabels } from "@/lib/constants/labels";
import { cn } from "@/lib/utils";
import {
  type AdminSession,
  clearAdminSession,
  readAdminSession,
} from "@/lib/session/admin";

/**
 * PlatformShell — IT/platform-admin surface (V2.6).
 *
 * Sibling of ``AdminShell`` introduced when the unified admin
 * console got muddled past ~10 nav items. This shell carries the
 * surfaces a platform admin uses occasionally: user provisioning,
 * audit log, feedback reports, system status. AdminShell keeps the
 * compliance / day-to-day operations work.
 *
 * Auth: same ``internal_admin`` role gates both shells for now —
 * the split is UX-only. A future ``platform_admin`` role can layer
 * on top without changing the route structure (see the sprint
 * memory note 2026-05-26).
 */

const NAV: { href: string; label: string; icon: Icon }[] = [
  { href: "/platform/dashboard", label: "Resumen", icon: Gauge },
  { href: "/platform/users", label: "Usuarios", icon: UsersThree },
  { href: "/platform/users/new", label: "Nuevo usuario", icon: UserPlus },
  { href: "/platform/audit-log", label: "Audit log", icon: ListMagnifyingGlass },
  { href: "/platform/feedback-reports", label: "Feedback", icon: Bug },
];

export function PlatformShell({
  title,
  description,
  actions,
  children,
  unframed = false,
}: {
  title?: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  unframed?: boolean;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [session, setSession] = useState<AdminSession | null>(null);
  const [ready, setReady] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    const current = readAdminSession();
    if (!current) {
      router.replace("/login");
      return;
    }
    // Platform/IT surfaces are superadmin-only (backend ``PlatformUser``
    // = ``require_role(operations_admin)``), so the UI never shows a page
    // the API would 403. The review team (``platform_admin``) is sent to
    // its own Operaciones landing instead of a dead login bounce.
    if (!current.roles.includes("operations_admin")) {
      const isStaff =
        current.roles.includes("platform_admin");
      router.replace(isStaff ? "/admin/dashboard" : "/login");
      return;
    }
    setSession(current);
    setReady(true);
  }, [router]);

  useEffect(() => {
    setDrawerOpen(false);
  }, [pathname]);

  // Single active nav item: the LONGEST matching href wins, so
  // ``/platform/users/new`` lights up "Nuevo usuario" without also
  // lighting up its "/platform/users" prefix sibling.
  const activeHref = NAV.filter(
    (item) =>
      pathname === item.href || pathname?.startsWith(item.href + "/"),
  ).sort((a, b) => b.href.length - a.href.length)[0]?.href;

  function onLogout() {
    clearAdminSession();
    router.replace("/login");
  }

  if (!ready || !session) return null;

  // The superadmin always also has the Operaciones console (staff
  // superset), so offer the jump back there.
  const hasOperations =
    session.roles.includes("operations_admin") ||
    session.roles.includes("platform_admin");

  return (
    <div
      data-density="dense"
      className="min-h-screen bg-[color:var(--surface-page)]"
    >
      <header className="sticky top-0 z-30 border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)]/95 backdrop-blur supports-[backdrop-filter]:bg-[color:var(--surface-raised)]/85">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-5 py-2.5">
          <Link href="/platform/dashboard" aria-label="CheckWise plataforma">
            <BrandLogo size="md" />
          </Link>
          <span className="hidden h-6 w-px bg-[color:var(--border-subtle)] lg:block" />
          <p className="hidden font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-teal)] lg:block">
            Plataforma · TI
          </p>
          <div className="ml-auto flex items-center gap-2">
            <SearchBar resultsHref="/admin/buscar" />
            <UserMenu
              name={session.user.full_name || session.user.email}
              email={session.user.email}
              roles={session.roles}
              profileHref={null}
              shellSwitch={
                hasOperations
                  ? {
                      href: "/admin/dashboard",
                      label: "Cambiar a Operaciones",
                    }
                  : null
              }
              onSignOut={onLogout}
            />
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
          aria-label="Plataforma"
          className="mx-auto hidden max-w-7xl gap-1 overflow-x-auto px-3 pb-2 lg:flex"
        >
          {NAV.map((item) => {
            const isActive = item.href === activeHref;
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
          aria-label="Menú plataforma"
          className="fixed inset-0 z-40 flex lg:hidden"
        >
          <button
            type="button"
            aria-label="Cerrar"
            onClick={() => setDrawerOpen(false)}
            className="absolute inset-0 bg-[color:var(--text-primary)]/40 backdrop-blur-sm"
          />
          <nav
            aria-label="Plataforma"
            className="relative ml-auto flex h-full w-72 max-w-[85vw] flex-col gap-1 border-l border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)] p-4 shadow-lg"
          >
            <p className="cw-eyebrow mb-2">Navegación</p>
            {NAV.map((item) => {
              const isActive = item.href === activeHref;
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

      <BackBar homeHref="/platform/dashboard" />

      <main
        className={cn(
          "mx-auto",
          unframed ? "w-full" : "max-w-7xl space-y-5 px-5 py-5",
        )}
      >
        {!unframed && (
          <header className="cw-fade-up space-y-3">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div className="min-w-0 space-y-1">
                <p className="cw-eyebrow">Plataforma · CheckWise</p>
                {title ? (
                  <h1 className="text-[26px] font-semibold leading-tight tracking-tight text-[color:var(--text-primary)]">
                    {title}
                  </h1>
                ) : null}
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
                  label: "Roles",
                  value: roleLabels(session.roles),
                  tone: "teal",
                },
              ]}
            />
          </header>
        )}
        <section className={unframed ? undefined : ""}>{children}</section>
      </main>

      <footer className="mx-auto max-w-7xl px-5 py-6 text-center font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
        Plataforma interna · Legal Shelf · CheckWise
      </footer>
      <FeedbackLauncher />
    </div>
  );
}
