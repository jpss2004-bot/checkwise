"use client";

import { useEffect, useState, type ComponentType } from "react";
import { useRouter } from "next/navigation";

import { fetchCurrentSession, readPortalSession, type PortalSession } from "./portal";

/**
 * HOC that fronts a portal page with the standard session-check.
 *
 * CheckWise 1.7: session lives in an httpOnly cookie. The HOC tries
 * the in-memory cache first (populated by a prior fetch in the same
 * SPA navigation), then falls back to `GET /api/v1/portal/me`. A
 * 401 / network failure redirects to `/`.
 *
 * Usage:
 *   function DashboardInner({ session }: { session: PortalSession }) { ... }
 *   export default withPortalSession(DashboardInner);
 *
 * Spec: docs/DESIGN_SYSTEM.md §5 (Auth Guard Pattern)
 */
export function withPortalSession<P extends { session: PortalSession }>(
  Component: ComponentType<P>,
) {
  return function Guarded(props: Omit<P, "session">) {
    const router = useRouter();
    const [session, setSession] = useState<PortalSession | null>(null);

    useEffect(() => {
      let cancelled = false;
      const cached = readPortalSession();
      if (cached) {
        setSession(cached);
        return;
      }
      fetchCurrentSession().then((s) => {
        if (cancelled) return;
        if (!s) {
          router.replace("/");
          return;
        }
        setSession(s);
      });
      return () => {
        cancelled = true;
      };
    }, [router]);

    if (!session) return null;
    return <Component {...(props as P)} session={session} />;
  };
}
