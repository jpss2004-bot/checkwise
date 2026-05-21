"use client";

import { useEffect, type ComponentType } from "react";
import { useRouter } from "next/navigation";

import { withPortalSession } from "./with-portal-session";
import type { PortalSession } from "./portal";
import { readAdminSession } from "./admin";

/**
 * Centralised dashboard gate.
 *
 * Wraps any portal page that should ONLY be reachable after the user
 * has completed their initial expediente. The rule:
 *
 *   ``session.expediente_status === "complete"`` ⇒ render the page.
 *   anything else, AND the user is a provider     ⇒ redirect to
 *                                                   ``/portal/onboarding``.
 *
 * Phase 5 (V2.1) adds a role-aware bypass: internal staff
 * (``internal_admin`` / ``reviewer``) who land on ``/portal/*`` are
 * allowed through without an expediente. Real auth scope-checks live
 * server-side (see ``current_portal_workspace`` in
 * ``apps/api/app/api/v1/portal.py``); this gate is UX-only.
 */
const INTERNAL_ROLES = new Set(["internal_admin", "reviewer"]);

function isInternalStaff(): boolean {
  const admin = readAdminSession();
  if (!admin) return false;
  return admin.roles.some((r) => INTERNAL_ROLES.has(r));
}

export function withOnboardingGate<P extends { session: PortalSession }>(
  Component: ComponentType<P>,
) {
  function Gated(props: P) {
    const router = useRouter();
    const status = props.session.expediente_status;
    const internal = isInternalStaff();

    useEffect(() => {
      if (status !== "complete" && !internal) {
        router.replace("/portal/onboarding");
      }
    }, [router, status, internal]);

    if (status !== "complete" && !internal) return null;
    return <Component {...props} />;
  }
  return withPortalSession(Gated);
}
