"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import {
  CalendarBlank,
  ChartLineUp,
  ClipboardText,
  CloudArrowUp,
  Files,
  House,
  IdentificationCard,
  List,
  Question,
  SignOut,
  X,
  type Icon,
} from "@phosphor-icons/react";

import { BrandLogo } from "@/components/checkwise/brand-logo";
import { WiseDock } from "@/components/checkwise/portal/wise-dock";
import { FeedbackLauncher } from "@/components/feedback/feedback-launcher";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
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
];

const SECONDARY_NAV: NavItem[] = [
  {
    href: "/portal/entra-a-tu-espacio",
    label: "Mi espacio",
    icon: IdentificationCard,
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
      <aside className="hidden lg:flex lg:w-64 lg:shrink-0 lg:flex-col lg:border-r lg:border-[color:var(--border-subtle)] lg:bg-[color:var(--surface-raised)]">
        <div className="flex h-16 items-center px-5">
          <Link
            href="/portal/dashboard"
            aria-label="CheckWise"
            className="inline-flex items-center"
          >
            <BrandLogo size="md" />
          </Link>
        </div>

        <div className="px-3 pt-1 pb-3">
          <WorkspaceCard session={session} />
        </div>

        <SidebarNav pathname={pathname ?? ""} items={PRIMARY_NAV} title="Operación" />
        <SidebarNav
          pathname={pathname ?? ""}
          items={SECONDARY_NAV}
          title="Cuenta"
        />

        <div className="mt-auto p-3">
          {pct !== null ? (
            <SidebarProgress pct={pct} complete={isComplete} />
          ) : null}
          <SupportFooter onLogout={onLogout} />
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
              <BrandLogo size="md" />
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
              items={PRIMARY_NAV}
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
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar
          session={session}
          pct={pct}
          isComplete={isComplete}
          onToggleMobile={() => setMobileOpen((v) => !v)}
          onLogout={onLogout}
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
      <WiseDock session={session} />
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
}: {
  items: NavItem[];
  pathname: string;
  title?: string;
  onNavigate?: () => void;
}) {
  return (
    <nav className="px-3 py-2" aria-label={title}>
      {title ? (
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
                className={cn(
                  "group relative flex items-center gap-2.5 rounded-md px-2.5 py-2 text-[13px] transition-colors duration-fast",
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
                <span className="min-w-0 flex-1 truncate">{item.label}</span>
                {item.badge ? (
                  <span className="rounded-full bg-[color:var(--surface-brand)] px-1.5 font-mono text-[10px] tabular-nums text-[color:var(--text-inverse)]">
                    {item.badge}
                  </span>
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
        onClick={onLogout}
        className="mt-2 inline-flex w-full items-center justify-center gap-1.5 rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)] px-2 py-1.5 text-[11px] font-medium text-[color:var(--text-secondary)] transition-colors hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--text-primary)]"
      >
        <SignOut className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
        Cerrar sesión
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
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onLogout}
            className="hidden sm:inline-flex"
          >
            <SignOut className="h-4 w-4" aria-hidden="true" />
            Salir
          </Button>
        </div>
      </div>
    </header>
  );
}
