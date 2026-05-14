"use client";

import { useEffect, useState, type ComponentType } from "react";
import { useRouter } from "next/navigation";

import { readPortalSession, type PortalSession } from "./portal";

/**
 * HOC that fronts a portal page with the standard session-check.
 *
 * Replaces the 4x-duplicated pattern from V1.2:
 *   const [session, setSession] = useState<PortalSession | null>(null);
 *   useEffect(() => {
 *     const s = readPortalSession();
 *     if (!s) { router.replace("/"); return; }
 *     setSession(s);
 *   }, [router]);
 *   if (!session) return null;
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
      const s = readPortalSession();
      if (!s) {
        router.replace("/");
        return;
      }
      setSession(s);
    }, [router]);

    if (!session) return null;
    return <Component {...(props as P)} session={session} />;
  };
}
