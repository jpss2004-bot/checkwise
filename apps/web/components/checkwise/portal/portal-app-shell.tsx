"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  Bell,
  Bug,
  CalendarBlank,
  CaretLeft,
  CaretRight,
  ChartLineUp,
  ClipboardText,
  CloudArrowUp,
  Files,
  House,
  IdentificationCard,
  List,
  Question,
  SignOut,
  UserCircle,
  X,
  type Icon,
} from "@phosphor-icons/react";

import { BackBar } from "@/components/checkwise/back-bar";
import { BrandLogo } from "@/components/checkwise/brand-logo";
import { WiseDock } from "@/components/checkwise/portal/wise-dock";
import { SearchBar } from "@/components/checkwise/search-bar";
import { UserMenu } from "@/components/checkwise/user-menu";
import { FeedbackLauncher } from "@/components/feedback/feedback-launcher";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { getProviderNotificationSummary } from "@/lib/api/portal";
import { clearPortalSession, type PortalSession } from "@/lib/session/portal";

/**
 * PortalAppShell — sidebar-driven shell for the vendor portal.
 *
 * Replaces the top-only ``ProviderContextBar``. The sidebar holds the
 * brand mark, primary nav, and session footer; a slim top bar carries
 * workspace context and an expediente progress indicator. On mobile
 * the sidebar collapses into a hamburger-triggered drawer.
 *
 * Existing pages render their content as children; the shell adds:
 *   • role-aware nav with active states
 *   • workspace context bar at the top
 *   • mobile-responsive collapsing drawer
 *   • brand-consistent surface chrome
 */

type NavItem = {
  href: string;
  label: string;
  icon: Icon;
  /** Optional badge counter rendered next to the label. */
  badge?: number;
  /** Tooltip / sublabel — shown beneath the label in expanded mode. */
  hint?: string;
};

const PRIMARY_NAV: NavItem[] = [
  { href: "/portal/dashboard", label: "Dashboard", icon: House, hint: "Resumen del workspace" },
  {
    href: "/portal/onboarding",
    label: "Expediente",
    icon: ClipboardText,
    hint: "Documentos iniciales",
  },
  {
    href: "/portal/calendar",
    label: "Calendario",
    icon: CalendarBlank,
    hint: "Vista anual REPSE",
  },
  {
    href: "/portal/upload",
    label: "Subir documento",
    icon: CloudArrowUp,
    hint: "Carga guiada",
  },
  {
    href: "/portal/submissions",
    label: "Documentos",
    icon: Files,
    hint: "Historial por institución",
  },
  {
    href: "/portal/reports",
    label: "Reportes",
    icon: ChartLineUp,
    hint: "Resúmenes ejecutivos",
  },
  {
    href: "/portal/notifications",
    label: "Notificaciones",
    icon: Bell,
    hint: "Decisiones del revisor",
  },
];

const SECONDARY_NAV: NavItem[] = [
  {
    href: "/portal/entra-a-tu-espacio",
    label: "Mi espacio",
    icon: IdentificationCard,
    hint: "Identidad del workspace",
  },
  {
    href: "/portal/perfil",
    label: "Mi perfil",
    icon: UserCircle,
    hint: "Tus datos de contacto",
  },
];

type PortalAppShellProps = {
  session: PortalSession;
  onboardingPct?: number | null;
  children: React.ReactNode;
};

export function PortalAppShell({
  session,
  onboardingPct,
  children,
}: PortalAppShellProps) {
  const [mobileOpen, setMobileOpen] = useState(false);
  // Junta 2026-05-23 — desktop sidebar can collapse to an icon-only
  // rail so the operator gets more canvas. Persisted to localStorage
  // so the choice survives reloads. Mobile stays drawer-based; this
  // toggle is hidden under lg.
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const raw = window.localStorage.getItem("checkwise.portal.sidebar.collapsed");
      if (raw === "1") setSidebarCollapsed(true);
    } catch {
      // Storage blocked → stay expanded, no-op.
    }
  }, []);
  function toggleSidebar() {
    // A manual toggle cancels any pending Wise auto-restore — the user
    // has taken control of the rail.
    wiseRestoreRef.current = null;
    setSidebarCollapsed((prev) => {
      const next = !prev;
      try {
        window.localStorage.setItem(
          "checkwise.portal.sidebar.collapsed",
          next ? "1" : "0",
        );
      } catch {
        // Best-effort only.
      }
      return next;
    });
  }

  // Junta 2026-06-12 — opening Wise on a tight screen collapses the
  // left rail to its icon-only width so the drawer's 380px gutter
  // doesn't crowd the content. We remember the rail's prior state and
  // restore it when Wise closes. Only fires below 1440px (wide screens
  // have room for both); never writes localStorage (it's a temporary
  // courtesy, not the user's saved preference). ``wiseRestoreRef`` is
  // null when there's nothing to restore.
  const wiseRestoreRef = useRef<boolean | null>(null);
  function handleWiseOpenChange(open: boolean) {
    if (open) {
      const tight =
        typeof window !== "undefined" &&
        window.matchMedia("(max-width: 1439px)").matches;
      if (!tight) return;
      setSidebarCollapsed((prev) => {
        if (prev) {
          // Already collapsed — nothing to restore later.
          wiseRestoreRef.current = null;
          return prev;
        }
        wiseRestoreRef.current = false;
        return true;
      });
    } else {
      setSidebarCollapsed((prev) => {
        if (wiseRestoreRef.current === null) return prev;
        const restored = wiseRestoreRef.current;
        wiseRestoreRef.current = null;
        return restored;
      });
    }
  }
  // Phase 4 / Slice 4B — unread-count for the Notificaciones nav
  // badge. Best-effort: a fetch failure leaves the badge hidden
  // rather than blocking the shell. Auto-refreshes every 60 s so the
  // badge tracks reviewer decisions that land while the tab is open.
  const [notifUnread, setNotifUnread] = useState<number>(0);
  useEffect(() => {
    let cancelled = false;
    function refresh() {
      getProviderNotificationSummary(session)
        .then((s) => {
          if (!cancelled) setNotifUnread(s.unread_count);
        })
        .catch(() => undefined);
    }
    refresh();
    const handle = window.setInterval(refresh, 60_000);
    return () => {
      cancelled = true;
      window.clearInterval(handle);
    };
  }, [session]);
  const primaryNav = PRIMARY_NAV.map((item) =>
    item.href === "/portal/notifications"
      ? { ...item, badge: notifUnread > 0 ? notifUnread : undefined }
      : item,
  );

  const router = useRouter();
  const pathname = usePathname();

  const pct =
    typeof onboardingPct === "number" && Number.isFinite(onboardingPct)
      ? Math.min(100, Math.max(0, Math.round(onboardingPct)))
      : null;
  const isComplete = pct !== null && pct >= 100;

  async function onLogout() {
    await clearPortalSession();
    router.push("/");
  }

  return (
    <div className="min-h-screen lg:flex">
      {/* ── Sidebar (lg+) ─────────────────────────────────────── */}
      <aside
        className={cn(
          // Sticky, viewport-height column: nav stays at the top and the
          // collapse control + account footer stay pinned to the bottom of
          // the VIEWPORT, so neither is buried at the bottom of a tall page.
          "hidden lg:sticky lg:top-0 lg:flex lg:h-screen lg:shrink-0 lg:flex-col lg:self-start lg:border-r lg:border-[color:var(--border-subtle)] lg:bg-[color:var(--surface-raised)] lg:transition-[width] lg:duration-200",
          sidebarCollapsed ? "lg:w-20" : "lg:w-64",
        )}
        aria-label={sidebarCollapsed ? "Barra lateral colapsada" : "Barra lateral"}
      >
        {/* Brand — pinned top */}
        <div
          className={cn(
            "flex shrink-0 items-center",
            sidebarCollapsed ? "h-20 justify-center px-2" : "h-20 px-5",
          )}
        >
          <Link
            href="/portal/dashboard"
            aria-label="CheckWise"
            className="inline-flex items-center"
          >
            <BrandLogo size="lg" variant={sidebarCollapsed ? "compact" : undefined} />
          </Link>
        </div>

        {/* Workspace + nav — the only part that scrolls, so the brand and
            footer never leave the viewport. */}
        <div className="flex-1 overflow-y-auto">
          {sidebarCollapsed ? null : (
            <div className="px-3 pt-1 pb-3">
              <WorkspaceCard session={session} />
            </div>
          )}

          <SidebarNav
            pathname={pathname ?? ""}
            items={primaryNav}
            title="Operación"
            collapsed={sidebarCollapsed}
          />
          <SidebarNav
            pathname={pathname ?? ""}
            items={SECONDARY_NAV}
            title="Cuenta"
            collapsed={sidebarCollapsed}
          />
        </div>

        {/* Account + collapse — pinned bottom of the viewport */}
        <div
          className={cn(
            "shrink-0 border-t border-[color:var(--border-subtle)]",
            sidebarCollapsed ? "p-2" : "p-3",
          )}
        >
          {pct !== null && !sidebarCollapsed ? (
            <SidebarProgress pct={pct} complete={isComplete} />
          ) : null}
          {sidebarCollapsed ? (
            <SidebarCompactActions onLogout={onLogout} />
          ) : (
            <SupportFooter onLogout={onLogout} />
          )}
          <button
            type="button"
            onClick={toggleSidebar}
            aria-label={sidebarCollapsed ? "Expandir barra lateral" : "Colapsar barra lateral"}
            aria-pressed={sidebarCollapsed}
            className={cn(
              "mt-2 inline-flex w-full items-center justify-center gap-1.5 rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)] py-1.5 text-[11px] font-medium text-[color:var(--text-secondary)] transition-colors hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--text-primary)]",
              sidebarCollapsed ? "px-1" : "px-2",
            )}
          >
            {sidebarCollapsed ? (
              <CaretRight className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
            ) : (
              <>
                <CaretLeft className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
                <span>Colapsar</span>
              </>
            )}
          </button>
        </div>
      </aside>

      {/* ── Mobile drawer (lg-) ───────────────────────────────── */}
      {mobileOpen ? (
        <div
          className="fixed inset-0 z-40 flex lg:hidden"
          role="dialog"
          aria-modal="true"
        >
          <button
            type="button"
            className="absolute inset-0 bg-[color:var(--gray-950)]/40 backdrop-blur-sm"
            onClick={() => setMobileOpen(false)}
            aria-label="Cerrar menú"
          />
          <aside className="relative z-10 flex h-full w-72 flex-col border-r border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)] cw-fade-up">
            <div className="flex items-center justify-between px-5 py-4">
              <BrandLogo size="lg" />
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setMobileOpen(false)}
                aria-label="Cerrar"
              >
                <X className="h-5 w-5" weight="bold" />
              </Button>
            </div>
            <div className="px-3 pb-3">
              <WorkspaceCard session={session} />
            </div>
            <SidebarNav
              pathname={pathname ?? ""}
              items={primaryNav}
              title="Operación"
              onNavigate={() => setMobileOpen(false)}
            />
            <SidebarNav
              pathname={pathname ?? ""}
              items={SECONDARY_NAV}
              title="Cuenta"
              onNavigate={() => setMobileOpen(false)}
            />
            <div className="mt-auto p-3">
              {pct !== null ? (
                <SidebarProgress pct={pct} complete={isComplete} />
              ) : null}
              <SupportFooter onLogout={onLogout} />
            </div>
          </aside>
        </div>
      ) : null}

      {/* ── Main column ───────────────────────────────────────── */}
      {/* ``wise-push-target``: at ≥1024px the open Wise drawer reserves
          380px on the right so it never covers the workspace top bar;
          below that Wise is a bottom sheet (no push). See globals.css. */}
      <div className="wise-push-target flex min-w-0 flex-1 flex-col">
        <TopBar
          session={session}
          pct={pct}
          isComplete={isComplete}
          onToggleMobile={() => setMobileOpen((v) => !v)}
          onLogout={onLogout}
        />
        <BackBar
          homeHref="/portal/dashboard"
          hiddenOn={["/portal/entra-a-tu-espacio", "/portal/onboarding"]}
        />
        <div className="flex-1">{children}</div>
      </div>
      {/* Phase 4 (2026-05-21): Wise lives at the shell level so the
          copilot is available on every portal page. The dock self-
          fetches the dashboard + onboarding payloads on first open
          and derives its page context from the current URL, so
          individual pages don't need to wire it up. The dashboard
          page still passes ``dashboard`` + ``onboarding`` as props
          to avoid a redundant refetch — every other page lets the
          dock manage its own data. */}
      <WiseDock session={session} onOpenChange={handleWiseOpenChange} />
      <FeedbackLauncher />
    </div>
  );
}

// ─── Subcomponents ───────────────────────────────────────────────

function WorkspaceCard({ session }: { session: PortalSession }) {
  return (
    <div className="rounded-lg border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] px-3 py-2.5">
      <p className="font-mono text-[9px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
        Workspace activo
      </p>
      <p className="mt-0.5 truncate text-[13px] font-semibold text-[color:var(--text-primary)]">
        {session.vendor_name}
      </p>
      <p className="truncate font-mono text-[11px] text-[color:var(--text-secondary)]">
        {session.vendor_rfc}
      </p>
      <div className="mt-1.5 flex flex-wrap items-center gap-1">
        <Badge variant="outline" className="px-1.5 py-0">
          {session.persona_type === "moral" ? "Persona Moral" : "Persona Física"}
        </Badge>
        <span className="truncate text-[10px] text-[color:var(--text-tertiary)]">
          {session.client_name}
        </span>
      </div>
    </div>
  );
}

function SidebarNav({
  items,
  pathname,
  title,
  onNavigate,
  collapsed = false,
}: {
  items: NavItem[];
  pathname: string;
  title?: string;
  onNavigate?: () => void;
  /** Junta 2026-05-23 — when true, the nav renders as an icon-only
   *  rail. Label + badge are hidden visually but kept on
   *  ``title`` / ``aria-label`` so the row stays accessible. */
  collapsed?: boolean;
}) {
  return (
    <nav
      className={collapsed ? "px-2 py-2" : "px-3 py-2"}
      aria-label={title}
    >
      {title && !collapsed ? (
        <p className="px-2 pb-1.5 font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
          {title}
        </p>
      ) : null}
      <ul className="space-y-0.5">
        {items.map((item) => {
          const isActive =
            pathname === item.href || pathname.startsWith(item.href + "/");
          const IconComponent = item.icon;
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                onClick={onNavigate}
                title={collapsed ? item.label : undefined}
                aria-label={collapsed ? item.label : undefined}
                className={cn(
                  "group relative flex items-center rounded-md text-[13px] transition-colors duration-fast",
                  collapsed
                    ? "justify-center px-2 py-2"
                    : "gap-2.5 px-2.5 py-2",
                  isActive
                    ? "bg-[color:var(--surface-brand-muted)] font-semibold text-[color:var(--text-brand)]"
                    : "text-[color:var(--text-secondary)] hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--text-primary)]",
                )}
              >
                {isActive ? (
                  <span
                    aria-hidden="true"
                    className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full bg-[color:var(--text-brand)]"
                  />
                ) : null}
                <IconComponent
                  className={cn(
                    "h-4 w-4 shrink-0",
                    isActive
                      ? "text-[color:var(--text-brand)]"
                      : "text-[color:var(--text-tertiary)] group-hover:text-[color:var(--text-secondary)]",
                  )}
                  weight={isActive ? "fill" : "duotone"}
                />
                {collapsed ? null : (
                  <>
                    <span className="min-w-0 flex-1 truncate">{item.label}</span>
                    {item.badge ? (
                      <span className="rounded-full bg-[color:var(--surface-brand)] px-1.5 font-mono text-[10px] tabular-nums text-[color:var(--text-inverse)]">
                        {item.badge}
                      </span>
                    ) : null}
                  </>
                )}
                {collapsed && item.badge ? (
                  <span
                    aria-hidden="true"
                    className="absolute right-1 top-1 h-2 w-2 rounded-full bg-[color:var(--surface-brand)]"
                  />
                ) : null}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

function SidebarProgress({
  pct,
  complete,
}: {
  pct: number;
  complete: boolean;
}) {
  return (
    <div
      className={cn(
        "mb-2 rounded-lg border px-3 py-2.5",
        complete
          ? "border-[color:var(--status-success-border)] bg-[color:var(--status-success-bg)]"
          : "border-[color:var(--border-subtle)] bg-[color:var(--surface-page)]",
      )}
    >
      <div className="flex items-center justify-between text-[10px]">
        <p
          className={cn(
            "font-mono uppercase tracking-wide",
            complete
              ? "text-[color:var(--status-success-text)]"
              : "text-[color:var(--text-tertiary)]",
          )}
        >
          Expediente
        </p>
        <p
          className={cn(
            "font-mono font-semibold tabular-nums",
            complete
              ? "text-[color:var(--status-success-text)]"
              : "text-[color:var(--text-primary)]",
          )}
        >
          {pct}%
        </p>
      </div>
      <div
        className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-[color:var(--surface-sunken)]"
        aria-hidden="true"
      >
        <div
          className={cn(
            "h-full rounded-full transition-[width] duration-700 ease-out",
            complete
              ? "bg-[color:var(--status-success-text)]"
              : "bg-[color:var(--text-brand)]",
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function dispatchOpenFeedback() {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent("checkwise:open-feedback"));
}

function SupportFooter({ onLogout }: { onLogout: () => void }) {
  return (
    <div className="rounded-lg border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] px-3 py-2.5">
      <div className="flex items-center gap-2 text-[11px] text-[color:var(--text-secondary)]">
        <Question
          className="h-3.5 w-3.5 text-[color:var(--text-tertiary)]"
          weight="bold"
          aria-hidden="true"
        />
        <span className="truncate">¿Necesitas ayuda? Soporte CheckWise</span>
      </div>
      <button
        type="button"
        onClick={dispatchOpenFeedback}
        className="mt-2 inline-flex w-full items-center justify-center gap-1.5 rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)] px-2 py-1.5 text-[11px] font-medium text-[color:var(--text-secondary)] transition-colors hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--text-primary)]"
      >
        <Bug className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
        Reportar problema
      </button>
      <button
        type="button"
        onClick={onLogout}
        className="mt-2 inline-flex w-full items-center justify-center gap-1.5 rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)] px-2 py-1.5 text-[11px] font-medium text-[color:var(--text-secondary)] transition-colors hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--text-primary)]"
      >
        <SignOut className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
        Cerrar sesión
      </button>
    </div>
  );
}

function SidebarCompactActions({ onLogout }: { onLogout: () => void }) {
  /** Icon-only stack shown in the collapsed sidebar so the report-bug
   *  and logout affordances stay reachable without forcing the user to
   *  expand the rail. Tooltips on hover via ``title`` / aria-label.
   *  Matches the floating launcher's behavior by dispatching a window
   *  event the launcher listens for. */
  return (
    <div className="flex flex-col items-center gap-1">
      <button
        type="button"
        onClick={dispatchOpenFeedback}
        title="Reportar problema"
        aria-label="Reportar problema"
        className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)] text-[color:var(--text-secondary)] transition-colors hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--text-primary)]"
      >
        <Bug className="h-4 w-4" weight="bold" aria-hidden="true" />
      </button>
      <button
        type="button"
        onClick={onLogout}
        title="Cerrar sesión"
        aria-label="Cerrar sesión"
        className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)] text-[color:var(--text-secondary)] transition-colors hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--text-primary)]"
      >
        <SignOut className="h-4 w-4" weight="bold" aria-hidden="true" />
      </button>
    </div>
  );
}

function TopBar({
  session,
  pct,
  isComplete,
  onToggleMobile,
  onLogout,
}: {
  session: PortalSession;
  pct: number | null;
  isComplete: boolean;
  onToggleMobile: () => void;
  onLogout: () => void;
}) {
  return (
    <header className="sticky top-0 z-30 border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)]/95 backdrop-blur supports-[backdrop-filter]:bg-[color:var(--surface-raised)]/80">
      <div className="flex h-14 items-center gap-3 px-4 md:px-6">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="lg:hidden"
          onClick={onToggleMobile}
          aria-label="Abrir menú"
        >
          <List className="h-5 w-5" weight="bold" />
        </Button>

        <div className="lg:hidden">
          <BrandLogo variant="compact" size="md" />
        </div>

        <div className="hidden min-w-0 flex-1 lg:flex lg:flex-col">
          <p className="text-[11px] text-[color:var(--text-tertiary)]">Sesión proveedor</p>
          <p className="truncate text-[13px] text-[color:var(--text-primary)]">
            <span className="font-semibold">{session.vendor_name}</span>
            <span className="ml-2 text-[color:var(--text-secondary)]">
              · Cliente: {session.client_name}
              {session.filial_name ? ` / ${session.filial_name}` : ""}
              {session.contract_reference ? ` · ${session.contract_reference}` : ""}
            </span>
          </p>
        </div>

        <div className="ml-auto flex items-center gap-2">
          <SearchBar resultsHref="/portal/buscar" />
          {pct !== null ? (
            <span
              className={cn(
                "hidden items-center gap-2 rounded-full border px-2.5 py-1 text-[11px] sm:inline-flex",
                isComplete
                  ? "border-[color:var(--status-success-border)] bg-[color:var(--status-success-bg)] text-[color:var(--status-success-text)]"
                  : "border-[color:var(--border-default)] bg-[color:var(--surface-brand-muted)] text-[color:var(--text-brand)]",
              )}
            >
              <ClipboardText className="h-3 w-3" aria-hidden="true" />
              <span>Expediente</span>
              <span className="font-mono font-semibold tabular-nums">{pct}%</span>
            </span>
          ) : null}
          <UserMenu
            name={session.full_name || session.vendor_name}
            email={session.contact_email || ""}
            profileHref="/portal/entra-a-tu-espacio"
            profileLabel="Mi espacio"
            onSignOut={onLogout}
          />
        </div>
      </div>
    </header>
  );
}
