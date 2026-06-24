"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import {
  Books,
  CalendarBlank,
  ChartLineUp,
  ClipboardText,
  EnvelopeSimple,
  Gauge,
  IdentificationCard,
  List,
  PencilSimple,
  Storefront,
  X,
  type Icon,
} from "@phosphor-icons/react";

import { BackBar } from "@/components/checkwise/back-bar";
import { BrandLogo } from "@/components/checkwise/brand-logo";
import { FeedbackLauncher } from "@/components/feedback/feedback-launcher";
import { AdminWiseMount } from "@/components/checkwise/wise/admin-wise-mount";
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
 * AdminShell — premium-dense operations console shell (V2.1).
 *
 * Density: dense (per VISUAL_DIRECTION_2_X tier lock).
 * Header: brand mark + horizontal nav + user chip on desktop, drawer
 * on mobile (<1024px). Page header carries title + MetadataStrip
 * (workspace identity demoted from greeting block to mono metadata).
 */

// Operaciones nav. The IT-side actions (user provisioning, audit
// log, feedback reports) live in the sibling /platform/* shell —
// see ``apps/web/app/platform/_shell.tsx``. ``UserMenu`` carries a
// switcher so the same internal_admin can flip between the two
// surfaces without leaving the page.
//
// ``roles`` lists who may actually load each page (mirrors the
// backend dependency gate). A reviewer-only user lands in this shell
// because /admin/reviewer is their surface, but every other page is
// internal_admin-only (AdminUser) and would 403 them — so the nav is
// filtered by role and never dangles a link the API rejects.
const NAV: { href: string; label: string; icon: Icon; roles: string[] }[] = [
  { href: "/admin/dashboard", label: "Resumen", icon: Gauge, roles: ["platform_admin", "operations_admin"] },
  { href: "/admin/clients", label: "Clientes", icon: IdentificationCard, roles: ["platform_admin", "operations_admin"] },
  { href: "/admin/vendors", label: "Proveedores", icon: Storefront, roles: ["platform_admin", "operations_admin"] },
  { href: "/admin/requirements", label: "Requisitos", icon: Books, roles: ["platform_admin", "operations_admin"] },
  { href: "/admin/calendar", label: "Calendario", icon: CalendarBlank, roles: ["platform_admin", "operations_admin"] },
  { href: "/admin/reviewer", label: "Bandeja", icon: ClipboardText, roles: ["platform_admin", "operations_admin"] },
  { href: "/admin/reports", label: "Reportes", icon: ChartLineUp, roles: ["platform_admin", "operations_admin"] },
  { href: "/admin/contact-requests", label: "Solicitudes", icon: EnvelopeSimple, roles: ["platform_admin", "operations_admin"] },
  {
    href: "/admin/correction-requests",
    label: "Correcciones",
    icon: PencilSimple,
    roles: ["internal_admin"],
  },
];

export function AdminShell({
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
  /**
   * When true, skip the shell's internal page header (eyebrow,
   * title, description, actions, MetadataStrip). Use this when the
   * page renders its own complete header — e.g. the shared
   * <ReportEditor>. Defaults to false so existing pages keep their
   * current chrome.
   */
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
    // Accept either internal_admin or reviewer. Earlier this gated
    // strictly on internal_admin and locked out reviewer-only users,
    // even though /admin/reviewer is the reviewer role's primary
    // landing surface per decideDestination() in /login.
    if (
      !current.roles.includes("platform_admin") &&
      !current.roles.includes("operations_admin")
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
    router.replace("/login");
  }

  if (!ready || !session) return null;

  // Show each nav link only to a role that can actually load the page,
  // so a reviewer-only user sees Bandeja instead of a row of links the
  // API would 403.
  const visibleNav = NAV.filter((item) =>
    item.roles.some((role) => session.roles.includes(role)),
  );

  // The Plataforma console is superadmin-only (backend ``PlatformUser``
  // = ``operations_admin``). The review team reaches this Operaciones
  // shell but is not a superadmin, so don't dangle a switch into a
  // console the API would 403.
  const hasPlatform = session.roles.includes("operations_admin");

  return (
    <div
      data-density="dense"
      className="min-h-screen bg-[color:var(--surface-page)]"
    >
      <header className="sticky top-0 z-30 border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)]/95 backdrop-blur supports-[backdrop-filter]:bg-[color:var(--surface-raised)]/85">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-5 py-2.5">
          <Link href="/admin" aria-label="CheckWise admin">
            <BrandLogo size="md" />
          </Link>
          <span className="hidden h-6 w-px bg-[color:var(--border-subtle)] lg:block" />
          <p className="hidden font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-teal)] lg:block">
            Operaciones internas
          </p>
          <div className="ml-auto flex items-center gap-2">
            <SearchBar resultsHref="/admin/buscar" />
            <UserMenu
              name={session.user.full_name || session.user.email}
              email={session.user.email}
              roles={session.roles}
              profileHref={null}
              shellSwitch={
                hasPlatform
                  ? {
                      href: "/platform/dashboard",
                      label: "Cambiar a Plataforma",
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
          aria-label="Operaciones admin"
          className="mx-auto hidden max-w-7xl gap-1 overflow-x-auto px-3 pb-2 lg:flex"
        >
          {visibleNav.map((item) => {
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
          aria-label="Menú admin"
          className="fixed inset-0 z-40 flex lg:hidden"
        >
          <button
            type="button"
            aria-label="Cerrar"
            onClick={() => setDrawerOpen(false)}
            className="absolute inset-0 bg-[color:var(--text-primary)]/40 backdrop-blur-sm"
          />
          <nav
            aria-label="Operaciones admin"
            className="relative ml-auto flex h-full w-72 max-w-[85vw] flex-col gap-1 border-l border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)] p-4 shadow-lg"
          >
            <p className="cw-eyebrow mb-2">Navegación</p>
            {visibleNav.map((item) => {
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

      <BackBar homeHref="/admin" />

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
                <p className="cw-eyebrow">Admin · CheckWise</p>
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
        Operaciones internas · Legal Shelf · CheckWise
      </footer>
      <FeedbackLauncher />
      {/* M1-follow-up: Wise mounts only when the URL carries a
          ``?client_id=`` so the backend's _resolve_client_id can
          scope answers. Hidden on cross-tenant pages like the admin
          dashboard. */}
      <Suspense fallback={null}>
        <AdminWiseMount />
      </Suspense>
    </div>
  );
}
