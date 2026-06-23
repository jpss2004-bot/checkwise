"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import {
  Bell,
  CalendarBlank,
  ChartLineUp,
  ClockClockwise,
  Files,
  FileXls,
  Gauge,
  List,
  MagnifyingGlass,
  Package,
  ShieldWarning,
  Storefront,
  X,
  type Icon,
} from "@phosphor-icons/react";

import { BackBar } from "@/components/checkwise/back-bar";
import { BrandLogo } from "@/components/checkwise/brand-logo";
import { FeedbackLauncher } from "@/components/feedback/feedback-launcher";
import { ClientWiseDock } from "@/components/checkwise/wise/client-wise-dock";
import { SearchBar } from "@/components/checkwise/search-bar";
import { UserMenu } from "@/components/checkwise/user-menu";
import { MetadataStrip } from "@/components/ui/metadata-strip";
import { cn } from "@/lib/utils";
import {
  ClientApiError,
  getClientMe,
  getClientNotificationSummary,
} from "@/lib/api/client";
import { useUrlClientId } from "@/lib/workspace/use-url-client-id";
import { withClientId } from "@/lib/navigation/with-client-id";
import {
  type AdminSession,
  clearAdminSession,
  readAdminSession,
} from "@/lib/session/admin";
import { parseClientErrorCode } from "@/lib/api/error-detail";
import { ClientPlanProvider } from "@/lib/plan/plan-context";
import { PlanBadgeConnected } from "@/components/checkwise/plan/plan-badge";
import { DemoCountdownConnected } from "@/components/checkwise/plan/demo-countdown";
import { UpgradeWall } from "@/components/checkwise/plan/upgrade-wall";

/**
 * ClientShell — premium-dense cliente corporativo console (V2.1).
 *
 * Same architectural shape as AdminShell with the client palette.
 * Density: dense. Horizontal nav with drawer fallback <1024px.
 * Workspace identity rendered as MetadataStrip below the title.
 */

// Legal-consent gate (v2+). A client_admin is blocked from the client
// console until they accept the current legal package. The acceptance
// screen at /client/consentimiento is standalone (no ClientShell) so it
// never gates itself; internal staff bypass to match the provider gate.
const CLIENT_CONSENT_PATH = "/client/consentimiento";
const INTERNAL_ROLES = new Set(["internal_admin", "reviewer"]);

function clientLegalConsentRequired(me: {
  legal_consent_accepted_at: string | null;
  legal_consent_version: string | null;
  current_legal_consent_version: string | null;
}): boolean {
  if (me.legal_consent_accepted_at === null) return true;
  if (me.current_legal_consent_version === null) return false;
  return me.legal_consent_version !== me.current_legal_consent_version;
}

// Best-effort HTTP status from a thrown API error. Prefers
// ``ClientApiError`` but falls back to duck-typing a numeric ``status``
// so a 401/403 is still recognised even if the error crosses a module
// boundary (e.g. dev HMR) and breaks ``instanceof``.
function httpStatusOf(err: unknown): number | null {
  if (err instanceof ClientApiError) return err.status;
  if (
    typeof err === "object" &&
    err !== null &&
    typeof (err as { status?: unknown }).status === "number"
  ) {
    return (err as { status: number }).status;
  }
  return null;
}

// Reportes sits next to the decision loop (Inicio→Proveedores→Calendario
// →Entregas→Reportes) and Auditoría — the inspector-ready ZIP builder, a
// headline value prop — is now reachable from every surface instead of
// only the Proveedores banner. Notificaciones is also reachable via the
// header bell, so its nav slot is the lower-priority tail alongside
// Metadata (a power-user export) and Actividad.
const NAV: { href: string; label: string; icon: Icon }[] = [
  { href: "/client/dashboard", label: "Inicio", icon: Gauge },
  { href: "/client/vendors", label: "Proveedores", icon: Storefront },
  { href: "/client/calendar", label: "Calendario", icon: CalendarBlank },
  { href: "/client/submissions", label: "Entregas", icon: Files },
  { href: "/client/reports", label: "Reportes", icon: ChartLineUp },
  { href: "/client/auditoria", label: "Auditoría", icon: Package },
  { href: "/client/notifications", label: "Notificaciones", icon: Bell },
  { href: "/client/metadata", label: "Metadata", icon: FileXls },
  { href: "/client/activity", label: "Actividad", icon: ClockClockwise },
];

export function ClientShell({
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
   * When true, skip the shell's internal page header. Same purpose as
   * AdminShell.unframed — lets the shared <ReportEditor> render its
   * own full-width header inside the client shell without duplicating
   * the title block.
   */
  unframed?: boolean;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const urlClientId = useUrlClientId();
  const [session, setSession] = useState<AdminSession | null>(null);
  const [ready, setReady] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  // Mobile drawer a11y (audit P3.15): the panel is the only nav < 1024px, so
  // it must behave like a real dialog — trap Tab, close on Escape, focus the
  // panel on open, and restore focus to the trigger on close.
  const drawerPanelRef = useRef<HTMLElement | null>(null);
  const drawerReturnFocusRef = useRef<HTMLElement | null>(null);
  const [unreadCount, setUnreadCount] = useState(0);
  // "checking" until /client/me resolves; "ok" to render; "blocked"
  // while the consent redirect is in flight; "error" when we could not
  // verify consent. The console only renders on "ok" — the gate fails
  // CLOSED (a legal gate must never let an unverified user through).
  const [consentState, setConsentState] = useState<
    "checking" | "ok" | "blocked" | "error"
  >("checking");
  const [consentReloadKey, setConsentReloadKey] = useState(0);
  // Human-readable detail for the fail-closed error screen so a stuck
  // user (and support) can see *why* verification failed instead of a
  // generic "revisa tu conexión".
  const [consentErrorDetail, setConsentErrorDetail] = useState<string | null>(
    null,
  );
  // Phase C3 — a frozen/expired demo client trips the backend trial gate
  // (403 trial_expired) on /client/me; render the upgrade wall instead of
  // bouncing them to /login like a normal auth-403.
  const [trialExpired, setTrialExpired] = useState(false);

  useEffect(() => {
    const current = readAdminSession();
    if (!current) {
      router.replace("/login");
      return;
    }
    if (
      !current.roles.includes("client_admin") &&
      !current.roles.includes("client_viewer") &&
      !current.roles.includes("internal_admin")
    ) {
      router.replace("/admin");
      return;
    }
    setSession(current);
    setReady(true);
    // Phase 7 / Slice N9b — bell badge counts only red+yellow
    // unread rows. Info-tier and green-tier unreads are visible in
    // the in-app feed but never inflate the count, keeping the
    // badge as a "you need to act on this" signal.
    getClientNotificationSummary(
      urlClientId ? { client_id: urlClientId } : undefined,
    )
      .then((summary) => setUnreadCount(summary.unread_actionable_count))
      .catch(() => setUnreadCount(0));
  }, [router, urlClientId]);

  useEffect(() => {
    setDrawerOpen(false);
  }, [pathname]);

  // Dialog focus management for the mobile nav drawer.
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
      // Restore focus to whatever opened the drawer (the hamburger).
      drawerReturnFocusRef.current?.focus();
    };
  }, [drawerOpen]);

  // Legal-consent gate. Runs once the session is ready: internal staff
  // and the acceptance page itself are exempt; everyone else must have
  // accepted the current legal version or they are routed to the
  // acceptance screen. Fails CLOSED — on a /me error the console is held
  // behind a retry rather than letting an unverified user through.
  useEffect(() => {
    if (!session) return;
    if (
      session.roles.some((r) => INTERNAL_ROLES.has(r)) ||
      pathname === CLIENT_CONSENT_PATH
    ) {
      setConsentState("ok");
      return;
    }
    let cancelled = false;
    setConsentState("checking");
    setConsentErrorDetail(null);
    getClientMe()
      .then((me) => {
        if (cancelled) return;
        if (clientLegalConsentRequired(me)) {
          setConsentState("blocked");
          router.replace(CLIENT_CONSENT_PATH);
        } else {
          setConsentState("ok");
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const status = httpStatusOf(err);
        // Phase C3 — a trial-expiry 403 is NOT an invalid token: show the
        // upgrade wall (logout stays available) rather than clearing the
        // session. The ``code`` field is the discriminator vs. an auth-403.
        if (
          status === 403 &&
          parseClientErrorCode(err).code === "trial_expired"
        ) {
          setTrialExpired(true);
          setConsentState("ok");
          return;
        }
        // A 401/403 means the stored token is invalid (rotated secret,
        // signature mismatch, or a session minted before this gate
        // shipped). readAdminSession() only checks *expiry*, so such a
        // token never bounces to /login on its own and a plain retry
        // re-sends the same dead token forever. Recover by clearing the
        // session and routing to re-login, which mints a fresh token.
        if (status === 401 || status === 403) {
          clearAdminSession();
          router.replace("/login?reason=session_expired");
          return;
        }
        setConsentErrorDetail(
          status != null
            ? `Error ${status}`
            : err instanceof Error && err.message
              ? err.message
              : null,
        );
        setConsentState("error");
      });
    return () => {
      cancelled = true;
    };
  }, [session, pathname, router, consentReloadKey]);

  function onLogout() {
    clearAdminSession();
    router.replace("/login");
  }

  if (!ready || !session) return null;
  // Could not verify legal consent — fail closed with a retry instead of
  // rendering the console or bouncing the user.
  if (consentState === "error") {
    return (
      <div className="flex min-h-dvh flex-col items-center justify-center gap-4 bg-[color:var(--surface-page)] px-5 text-center">
        <p className="max-w-sm text-sm text-[color:var(--text-secondary)]">
          No pudimos verificar tu aceptación de los avisos legales. Revisa tu
          conexión e intenta de nuevo.
        </p>
        {consentErrorDetail ? (
          <p className="max-w-sm font-mono text-[11px] text-[color:var(--text-tertiary)]">
            {consentErrorDetail}
          </p>
        ) : null}
        <div className="flex flex-wrap items-center justify-center gap-2">
          <button
            type="button"
            onClick={() => setConsentReloadKey((k) => k + 1)}
            className="rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-3 py-1.5 text-sm font-medium text-[color:var(--text-primary)] transition-colors hover:bg-[color:var(--surface-hover)]"
          >
            Reintentar
          </button>
          {/* Escape hatch: if retry can't help (invalid session), let the
              user re-authenticate instead of being trapped behind the
              fail-closed gate. */}
          <button
            type="button"
            onClick={() => {
              clearAdminSession();
              router.replace("/login");
            }}
            className="rounded-md px-3 py-1.5 text-sm font-medium text-[color:var(--text-secondary)] transition-colors hover:text-[color:var(--text-primary)]"
          >
            Iniciar sesión de nuevo
          </button>
        </div>
      </div>
    );
  }
  // Hold the render until consent is confirmed so the console never
  // flashes for an un-consented client_admin mid-redirect.
  if (consentState !== "ok") return null;

  // Phase C3 — frozen/expired demo: the upgrade wall (logout stays available)
  // replaces the console until the client upgrades or logs out.
  if (trialExpired) return <UpgradeWall onLogout={onLogout} />;

  // Transparency half of break-glass: when CheckWise-internal staff view
  // a client's portal (an internal_admin who is not themselves a
  // client_admin of this org), surface a banner so the access is never
  // silent. The backend writes the forensic audit row
  // (client.cross_tenant_access) in _resolve_client_id; this is its
  // visible counterpart.
  const isSupportSession =
    session.roles.includes("internal_admin") &&
    !session.roles.includes("client_admin");

  return (
    <ClientPlanProvider clientId={urlClientId}>
    <div
      data-density="dense"
      // ``wise-push-target``: at ≥1024px the open Wise drawer reserves
      // 380px on the right so it never covers the console top bar; below
      // that Wise is a bottom sheet (no push). See globals.css.
      className="wise-push-target min-h-screen bg-[color:var(--surface-page)]"
    >
      {/* Skip-to-content: first focusable element, visually hidden until
          focused, so keyboard/SR users bypass the logo + search + bell +
          nav chips on every route (WCAG 2.4.1, audit P3.16). */}
      <a
        href="#client-main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-3 focus:z-50 focus:rounded-md focus:border focus:border-[color:var(--border-focus)] focus:bg-[color:var(--surface-raised)] focus:px-3 focus:py-1.5 focus:text-sm focus:font-medium focus:text-[color:var(--text-primary)] focus:shadow-md"
      >
        Saltar al contenido
      </a>
      <header className="sticky top-0 z-30 border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)]/95 backdrop-blur supports-[backdrop-filter]:bg-[color:var(--surface-raised)]/85">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-5 py-2.5">
          <Link
            href={withClientId("/client/dashboard", urlClientId)}
            aria-label="CheckWise · vista cliente"
          >
            <BrandLogo size="md" />
          </Link>
          <span className="hidden h-6 w-px bg-[color:var(--border-subtle)] lg:block" />
          <p className="hidden font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-teal)] lg:block">
            Vista cliente · cumplimiento del portafolio
          </p>
          <div className="ml-auto flex items-center gap-2">
            <SearchBar resultsHref={withClientId("/client/buscar", urlClientId)} />
            <Link
              href={withClientId("/client/notifications", urlClientId)}
              aria-label={
                unreadCount > 0
                  ? `${unreadCount} notificaciones sin leer`
                  : "Notificaciones"
              }
              className="relative inline-flex h-8 w-8 items-center justify-center rounded-md border border-[color:var(--border-subtle)] text-[color:var(--text-secondary)] transition-colors hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--text-primary)]"
            >
              <Bell className="h-4 w-4" weight={unreadCount > 0 ? "fill" : "bold"} />
              {unreadCount > 0 ? (
                <span className="absolute -right-1 -top-1 min-w-4 rounded-full bg-[color:var(--status-error-bg)] px-1 text-center font-mono text-[10px] font-semibold leading-4 text-[color:var(--status-error-text)]">
                  {unreadCount > 9 ? "9+" : unreadCount}
                </span>
              ) : null}
            </Link>
            <UserMenu
              name={session.user.full_name || session.user.email}
              email={session.user.email}
              roles={session.roles}
              profileHref="/client/onboarding"
              profileLabel="Datos de mi empresa"
              secondaryLinks={[
                {
                  href: withClientId(
                    "/client/configuracion/usuarios",
                    urlClientId,
                  ),
                  label: "Usuarios y accesos",
                },
                {
                  href: withClientId(
                    "/client/configuracion/aceptacion",
                    urlClientId,
                  ),
                  label: "Aceptación de documentos",
                },
                {
                  href: withClientId(
                    "/client/configuracion/notificaciones",
                    urlClientId,
                  ),
                  label: "Preferencias de notificaciones",
                },
              ]}
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
                href={withClientId(item.href, urlClientId)}
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

      {isSupportSession ? (
        <div
          role="status"
          className="border-b border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-bg)] px-5 py-2"
        >
          <p className="mx-auto flex max-w-7xl items-center gap-2 text-[12px] font-medium text-[color:var(--status-warning-text)]">
            <ShieldWarning
              className="h-4 w-4 shrink-0"
              weight="fill"
              aria-hidden="true"
            />
            <span>
              Acceso de soporte · estás viendo el portal de un cliente como
              personal interno de CheckWise. Esta sesión queda registrada en
              la bitácora{urlClientId ? ` (cliente ${urlClientId})` : ""}.
            </span>
          </p>
        </div>
      ) : null}

      <DemoCountdownConnected />

      {drawerOpen ? (
        <div
          role="dialog"
          aria-modal="true"
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
            ref={drawerPanelRef}
            aria-label="Menú de navegación"
            className="relative ml-auto flex h-full w-72 max-w-[85vw] flex-col gap-1 border-l border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)] p-4 shadow-lg"
          >
            <p className="cw-eyebrow mb-2">Navegación</p>
            {/* The header SearchBar is hidden < 640px, so the drawer is the
                only way to reach search on a phone. */}
            <Link
              href={withClientId("/client/buscar", urlClientId)}
              aria-current={pathname === "/client/buscar" ? "page" : undefined}
              className={cn(
                "flex items-center gap-2 rounded-md border px-3 py-2 text-sm font-medium transition-colors",
                pathname === "/client/buscar"
                  ? "border-[color:var(--border-brand)] bg-[color:var(--surface-brand)] text-[color:var(--text-inverse)]"
                  : "border-transparent text-[color:var(--text-secondary)] hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--text-primary)]",
              )}
            >
              <MagnifyingGlass
                className="h-4 w-4"
                weight={pathname === "/client/buscar" ? "fill" : "bold"}
                aria-hidden="true"
              />
              Buscar
            </Link>
            {NAV.map((item) => {
              const isActive =
                pathname === item.href || pathname?.startsWith(item.href + "/");
              const IconComponent = item.icon;
              return (
                <Link
                  key={item.href}
                  href={withClientId(item.href, urlClientId)}
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

      <BackBar
        homeHref={withClientId("/client/dashboard", urlClientId)}
        hiddenOn={[
          "/client/onboarding",
          "/client/auditoria",
          // Detail routes render their own deterministic "Volver"; the
          // trailing slash hides only the dynamic child, not the list.
          "/client/vendors/",
          "/client/reports/",
        ]}
      />

      <main
        id="client-main"
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
                <div className="flex items-center gap-2">
                  <p className="cw-eyebrow">Cliente · CheckWise</p>
                  <PlanBadgeConnected />
                </div>
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
        )}
        <section>{children}</section>
      </main>

      <footer className="mx-auto max-w-7xl px-5 py-6 text-center font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
        Powered by Legal Shelf · CheckWise
      </footer>
      <FeedbackLauncher />
      {/* ClientWiseDock uses useSearchParams() to read ?client_id and
          derive page context. Wrapping in <Suspense fallback={null}>
          satisfies Next 15's bailout requirement during static
          prerender so cliente pages (/client/auditoria,
          /client/notifications, ...) build cleanly on Vercel. */}
      <Suspense fallback={null}>
        <ClientWiseDock />
      </Suspense>
    </div>
    </ClientPlanProvider>
  );
}
