"use client";

import { useEffect, useState, type ComponentType } from "react";
import { usePathname, useRouter } from "next/navigation";

import { enterPortal } from "@/lib/api/auth";
import { clearAdminSession, readAdminSession } from "@/lib/session/admin";
import {
  fetchCurrentSession,
  readPortalSession,
  type PortalSession,
} from "./portal";

// Phase 1 / Slice 1A — legal-consent gate. Pages where the gate is
// resolved (entra-a-tu-espacio itself) MUST NOT redirect to itself, or
// the page would never render. Internal staff (internal_admin /
// reviewer) bypass the gate to match the onboarding-gate pattern.
const LEGAL_CONSENT_EXEMPT_PATHS = new Set([
  "/portal/entra-a-tu-espacio",
]);
const INTERNAL_ROLES = new Set(["internal_admin", "reviewer"]);

function isInternalStaff(): boolean {
  const admin = readAdminSession();
  if (!admin) return false;
  return admin.roles.some((r) => INTERNAL_ROLES.has(r));
}

// Slice 1B — the gate fires when the provider has never accepted, OR
// when the canonical version published by the backend has moved past
// their stored acceptance. When the backend omits the current version
// (legacy summaries during a rollout) we fall back to a null-only
// check so we never redirect-loop on missing data.
function legalConsentRequired(session: {
  legal_consent_accepted_at: string | null;
  legal_consent_version: string | null;
  current_legal_consent_version: string | null;
}): boolean {
  if (session.legal_consent_accepted_at === null) return true;
  if (session.current_legal_consent_version === null) return false;
  return (
    session.legal_consent_version !== session.current_legal_consent_version
  );
}

/**
 * Build a /login URL that asks the login page to redirect back to the
 * pathname (+ search) the user was originally trying to reach. The
 * login page validates ``next`` is a same-origin relative path before
 * honouring it, so it's safe to drop the current path in verbatim.
 *
 * Falls back to ``/login`` when no pathname is available (SSR) or
 * when the pathname is already ``/login`` itself.
 */
function loginUrlForCurrentPath(pathname: string | null, reason?: string): string {
  const params = new URLSearchParams();
  if (reason) params.set("reason", reason);
  if (!pathname || pathname === "/login") {
    const qs = params.toString();
    return qs ? `/login?${qs}` : "/login";
  }
  const search =
    typeof window !== "undefined" ? window.location.search : "";
  const next = `${pathname}${search}`;
  params.set("next", next);
  return `/login?${params.toString()}`;
}

function markPortalBootstrapFailed(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(
      "checkwise.portal.bootstrap_failed",
      "1",
    );
  } catch {
    /* ignore */
  }
}

/**
 * HOC that fronts a portal page with the standard session-check.
 *
 * CheckWise 1.8: there are two layers.
 *
 *   1. The httpOnly portal cookie (preferred) — checked via
 *      ``GET /api/v1/portal/me``. Set the first time the user calls
 *      ``POST /api/v1/portal/enter``.
 *   2. The admin/user JWT in localStorage — used to mint the cookie
 *      via ``/portal/enter`` when the cookie is missing or expired.
 *
 * Resolution order:
 *   - In-memory cache wins (populated by an earlier mount).
 *   - Otherwise call /portal/me. If 200, render.
 *   - If /portal/me 401 but we have a JWT, call /portal/enter and
 *     retry /portal/me.
 *   - If we have no JWT either, redirect to /login.
 */
export function withPortalSession<P extends { session: PortalSession }>(
  Component: ComponentType<P>,
) {
  return function Guarded(props: Omit<P, "session">) {
    const router = useRouter();
    const pathname = usePathname();
    const [session, setSession] = useState<PortalSession | null>(null);

    useEffect(() => {
      let cancelled = false;
      const cached = readPortalSession();
      if (cached) {
        setSession(cached);
        return;
      }

      void (async () => {
        let resolved = await fetchCurrentSession();
        if (cancelled) return;

        if (!resolved) {
          const admin = readAdminSession();
          if (!admin) {
            router.replace(loginUrlForCurrentPath(pathname));
            return;
          }
          try {
            await enterPortal(admin.access_token);
          } catch {
            markPortalBootstrapFailed();
            clearAdminSession();
            router.replace(
              loginUrlForCurrentPath(pathname, "portal_session_unavailable"),
            );
            return;
          }
          resolved = await fetchCurrentSession();
        }

        if (cancelled) return;
        if (!resolved) {
          // /enter succeeded but the cookie did not stick — almost
          // always a cross-origin SameSite/Secure mismatch. Don't loop:
          // surface the problem and force the user back to /login with
          // a flag so the login page can warn instead of bouncing.
          markPortalBootstrapFailed();
          clearAdminSession();
          router.replace("/login?reason=portal_session_unavailable");
          return;
        }
        setSession(resolved);
      })();

      return () => {
        cancelled = true;
      };
    }, [router, pathname]);

    // Phase 1 / Slice 1A — once a session exists, enforce the
    // legal-consent gate before rendering anything else. Slice 1B
    // broadened the trigger from "never accepted" to "accepted version
    // differs from current canonical version" so document bumps also
    // re-prompt. Internal staff bypass the gate.
    useEffect(() => {
      if (!session) return;
      if (!legalConsentRequired(session)) return;
      if (isInternalStaff()) return;
      if (pathname && LEGAL_CONSENT_EXEMPT_PATHS.has(pathname)) return;
      router.replace("/portal/entra-a-tu-espacio");
    }, [router, pathname, session]);

    if (!session) return null;
    // Block render on un-consented sessions for non-exempt paths so the
    // page doesn't flash while the redirect above resolves.
    if (
      legalConsentRequired(session) &&
      !isInternalStaff() &&
      pathname &&
      !LEGAL_CONSENT_EXEMPT_PATHS.has(pathname)
    ) {
      return null;
    }
    return <Component {...(props as P)} session={session} />;
  };
}
