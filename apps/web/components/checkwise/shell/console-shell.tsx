"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import { List, X, type Icon } from "@phosphor-icons/react";

import { BackBar } from "@/components/checkwise/back-bar";
import { BrandLogo } from "@/components/checkwise/brand-logo";
import { FeedbackLauncher } from "@/components/feedback/feedback-launcher";
import { SearchBar } from "@/components/checkwise/search-bar";
import { ShellNavMore } from "@/components/checkwise/shell/shell-nav-more";
import { UserMenu } from "@/components/checkwise/user-menu";
import { MetadataStrip } from "@/components/ui/metadata-strip";
import { roleLabels } from "@/lib/constants/labels";
import { cn } from "@/lib/utils";
import {
  type AdminSession,
  clearAdminSession,
  readAdminSession,
} from "@/lib/session/admin";
import { logoutAdmin } from "@/lib/api/auth";

/**
 * ConsoleShell — the one staff "operations console" shell (audit Move 4).
 *
 * ``AdminShell`` (Operaciones) and ``PlatformShell`` (Plataforma) were
 * ~300 near-identical lines each — same header, drawer, footer,
 * MetadataStrip, search and user menu, differing only in their nav
 * config and entry gate (audit F13). They now both reduce to a thin
 * ``<ConsoleShell {...config}>`` so any chrome/a11y fix lands once.
 *
 * a11y (audit F14): this shell carries the modal-drawer treatment that
 * previously lived only in ``ClientShell`` — ``aria-modal``, focus trap,
 * Escape-to-close, focus restore on close, and a skip-to-content link —
 * so the staff surfaces get the same keyboard/SR experience as clients.
 *
 * ``ClientShell`` is intentionally NOT folded in here: it carries a lot
 * of bespoke behaviour (legal-consent gate, break-glass banner,
 * notification bell, Wise dock, per-tenant ``withClientId`` routing) and
 * already has the a11y this shell adds, so merging it would add risk for
 * little gain.
 */

export type ConsoleNavItem = {
  href: string;
  label: string;
  icon: Icon;
  /** When set, the item only renders for a session holding one of these
   *  roles (mirrors the backend gate). Omit to always show. */
  roles?: readonly string[];
};

export type ConsoleNavConfig = {
  /** Day-to-day chips, left-aligned in the primary row. */
  primary: ConsoleNavItem[];
  /** Occasional surfaces, collapsed into the "Más" overflow. */
  secondary?: ConsoleNavItem[];
  /** A settings gear anchor pinned to the right of the primary row. */
  settings?: ConsoleNavItem;
};

export type ConsoleShellSwitch = { href: string; label: string };

export type ConsoleShellProps = {
  /** Who may load the shell, and where to send a session that fails the
   *  gate (the no-session case always routes to /login). */
  gate: {
    roles: readonly string[];
    onDenied: (session: AdminSession) => string;
  };
  /** Mono eyebrow next to the brand mark, e.g. "Operaciones internas". */
  surfaceLabel: string;
  /** Logo link + BackBar home target, e.g. "/admin". */
  homeHref: string;
  /** Page-header eyebrow, e.g. "Admin · CheckWise". */
  pageEyebrow: string;
  /** Footer line, e.g. "Operaciones internas · Legal Shelf · CheckWise". */
  footerLabel: string;
  /** aria-label for the nav landmarks, e.g. "Operaciones admin". */
  navAriaLabel: string;
  nav: ConsoleNavConfig;
  searchResultsHref: string;
  profileHref: string | null;
  profileLabel?: string;
  /** Computed per-session so the switcher only shows when reachable. */
  shellSwitch?: (session: AdminSession) => ConsoleShellSwitch | null;
  /** Extra mount rendered after the footer (e.g. the admin Wise dock). */
  footerSlot?: React.ReactNode;
  title?: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  /** Skip the built-in page header (eyebrow/title/MetadataStrip) when the
   *  page renders its own complete header — e.g. <ReportEditor>. */
  unframed?: boolean;
  children: React.ReactNode;
};

export function ConsoleShell({
  gate,
  surfaceLabel,
  homeHref,
  pageEyebrow,
  footerLabel,
  navAriaLabel,
  nav,
  searchResultsHref,
  profileHref,
  profileLabel,
  shellSwitch,
  footerSlot,
  title,
  description,
  actions,
  unframed = false,
  children,
}: ConsoleShellProps) {
  const router = useRouter();
  const pathname = usePathname();
  const [session, setSession] = useState<AdminSession | null>(null);
  const [ready, setReady] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const drawerPanelRef = useRef<HTMLElement | null>(null);
  const drawerReturnFocusRef = useRef<HTMLElement | null>(null);

  // Keep the latest gate in a ref so the entry effect runs once (on
  // mount) without re-firing when the inline ``gate`` prop changes
  // identity every render.
  const gateRef = useRef(gate);
  gateRef.current = gate;

  useEffect(() => {
    const current = readAdminSession();
    if (!current) {
      router.replace("/login");
      return;
    }
    if (!gateRef.current.roles.some((role) => current.roles.includes(role))) {
      router.replace(gateRef.current.onDenied(current));
      return;
    }
    setSession(current);
    setReady(true);
  }, [router]);

  useEffect(() => {
    setDrawerOpen(false);
  }, [pathname]);

  // Mobile drawer a11y (audit F14, ported from ClientShell): the panel is
  // the only nav < 1024px, so it must behave like a real dialog — trap
  // Tab, close on Escape, focus the panel on open, restore focus on close.
  useEffect(() => {
    if (!drawerOpen) return;
    drawerReturnFocusRef.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const panel = drawerPanelRef.current;
    const focusables = () =>
      panel
        ? Array.from(
            panel.querySelectorAll<HTMLElement>(
              'a[href],button:not([disabled]),[tabindex]:not([tabindex="-1"])',
            ),
          )
        : [];
    focusables()[0]?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        setDrawerOpen(false);
        return;
      }
      if (e.key !== "Tab") return;
      const items = focusables();
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      drawerReturnFocusRef.current?.focus();
    };
  }, [drawerOpen]);

  async function onLogout() {
    // FE-SEC-1 — clear the server-side session cookie too, then drop the
    // local identity + in-memory bearer and route to /login.
    await logoutAdmin();
    clearAdminSession();
    router.replace("/login");
  }

  if (!ready || !session) return null;

  // An item with no ``roles`` always shows; one with ``roles`` shows only
  // to a matching session, so the nav never dangles a link the API 403s.
  const roleMatch = (item: ConsoleNavItem) =>
    !item.roles || item.roles.some((role) => session.roles.includes(role));
  const visiblePrimary = nav.primary.filter(roleMatch);
  const visibleSecondary = (nav.secondary ?? []).filter(roleMatch);
  const settingsItem =
    nav.settings && roleMatch(nav.settings) ? nav.settings : null;

  // Longest matching href wins, so a child route (e.g. /platform/users/new)
  // lights its own chip without also lighting its /platform/users prefix
  // sibling. Secondary items self-detect inside <ShellNavMore>.
  const activeHref = [...visiblePrimary, ...(settingsItem ? [settingsItem] : [])]
    .filter(
      (item) =>
        pathname === item.href || pathname?.startsWith(item.href + "/"),
    )
    .sort((a, b) => b.href.length - a.href.length)[0]?.href;

  const switchConfig = shellSwitch?.(session) ?? null;

  const desktopChip = (item: ConsoleNavItem) => {
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
  };

  const drawerLink = (item: ConsoleNavItem) => {
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
  };

  return (
    <div
      data-density="dense"
      className="min-h-screen bg-[color:var(--surface-page)]"
    >
      {/* Skip-to-content: first focusable element, visually hidden until
          focused, so keyboard/SR users bypass the chrome on every route
          (WCAG 2.4.1, audit F14). */}
      <a
        href="#console-main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-3 focus:z-50 focus:rounded-md focus:border focus:border-[color:var(--border-focus)] focus:bg-[color:var(--surface-raised)] focus:px-3 focus:py-1.5 focus:text-sm focus:font-medium focus:text-[color:var(--text-primary)] focus:shadow-md"
      >
        Saltar al contenido
      </a>
      <header className="sticky top-0 z-30 border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)]/95 backdrop-blur supports-[backdrop-filter]:bg-[color:var(--surface-raised)]/85">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-5 py-2.5">
          <Link href={homeHref} aria-label={`CheckWise · ${surfaceLabel}`}>
            <BrandLogo size="md" />
          </Link>
          <span className="hidden h-6 w-px bg-[color:var(--border-subtle)] lg:block" />
          <p className="hidden font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-teal)] lg:block">
            {surfaceLabel}
          </p>
          <div className="ml-auto flex items-center gap-2">
            <SearchBar resultsHref={searchResultsHref} />
            <UserMenu
              name={session.user.full_name || session.user.email}
              email={session.user.email}
              roles={session.roles}
              profileHref={profileHref}
              profileLabel={profileLabel}
              shellSwitch={switchConfig}
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
          aria-label={navAriaLabel}
          className="mx-auto hidden max-w-7xl items-center gap-1 px-3 pb-2 lg:flex"
        >
          {/* Day-to-day chips scroll within their own container if they
              don't fit. The utility cluster (settings + "Más") is pinned
              to the right OUTSIDE that container — otherwise the scroll
              container's overflow clips the "Más" dropdown panel. */}
          <div className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto">
            {visiblePrimary.map(desktopChip)}
          </div>
          {settingsItem || visibleSecondary.length > 0 ? (
            <span
              className="mx-1 h-6 w-px shrink-0 self-center bg-[color:var(--border-subtle)]"
              aria-hidden="true"
            />
          ) : null}
          {settingsItem ? desktopChip(settingsItem) : null}
          <ShellNavMore items={visibleSecondary} />
        </nav>
      </header>

      {drawerOpen ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={navAriaLabel}
          className="fixed inset-0 z-40 flex lg:hidden"
        >
          <button
            type="button"
            aria-label="Cerrar"
            onClick={() => setDrawerOpen(false)}
            className="absolute inset-0 bg-[color:var(--text-primary)]/40 backdrop-blur-sm"
          />
          <nav
            ref={drawerPanelRef}
            aria-label="Menú de navegación"
            className="relative ml-auto flex h-full w-72 max-w-[85vw] flex-col gap-1 border-l border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)] p-4 shadow-lg"
          >
            <p className="cw-eyebrow mb-2">Navegación</p>
            {visiblePrimary.map(drawerLink)}
            {/* The overflow has no room to hide on mobile, so the drawer
                lists everything — grouped under "Más" to mirror desktop. */}
            {visibleSecondary.length > 0 ? (
              <>
                <p className="cw-eyebrow mb-1 mt-3">Más</p>
                {visibleSecondary.map(drawerLink)}
              </>
            ) : null}
            {settingsItem ? (
              <>
                <span
                  className="my-2 h-px bg-[color:var(--border-subtle)]"
                  aria-hidden="true"
                />
                {drawerLink(settingsItem)}
              </>
            ) : null}
          </nav>
        </div>
      ) : null}

      <BackBar homeHref={homeHref} />

      <main
        id="console-main"
        tabIndex={-1}
        className={cn(
          "mx-auto scroll-mt-20 focus:outline-none",
          unframed ? "w-full" : "max-w-7xl space-y-5 px-5 py-5",
        )}
      >
        {!unframed && (
          <header className="cw-fade-up space-y-3">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div className="min-w-0 space-y-1">
                <p className="cw-eyebrow">{pageEyebrow}</p>
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
        <section>{children}</section>
      </main>

      <footer className="mx-auto max-w-7xl px-5 py-6 text-center font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
        {footerLabel}
      </footer>
      <FeedbackLauncher />
      {footerSlot}
    </div>
  );
}
