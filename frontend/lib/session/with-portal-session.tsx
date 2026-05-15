"use client";

import { useEffect, useState, type ComponentType } from "react";
import { useRouter } from "next/navigation";

import { enterPortal } from "@/lib/api/auth";
import { readAdminSession } from "@/lib/session/admin";
import {
  fetchCurrentSession,
  readPortalSession,
  type PortalSession,
} from "./portal";

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
            router.replace("/login");
            return;
          }
          try {
            await enterPortal(admin.access_token);
          } catch {
            router.replace("/login");
            return;
          }
          resolved = await fetchCurrentSession();
        }

        if (cancelled) return;
        if (!resolved) {
          router.replace("/login");
          return;
        }
        setSession(resolved);
      })();

      return () => {
        cancelled = true;
      };
    }, [router]);

    if (!session) return null;
    return <Component {...(props as P)} session={session} />;
  };
}
