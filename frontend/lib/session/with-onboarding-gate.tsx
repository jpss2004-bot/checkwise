"use client";

import { useEffect, type ComponentType } from "react";
import { useRouter } from "next/navigation";

import { withPortalSession } from "./with-portal-session";
import type { PortalSession } from "./portal";

/**
 * Centralised dashboard gate.
 *
 * Wraps any portal page that should ONLY be reachable after the user
 * has completed their initial expediente. The single rule:
 *
 *   ``session.expediente_status === "complete"`` ⇒ render the page.
 *   anything else                                ⇒ redirect to
 *                                                  ``/portal/onboarding``.
 *
 * Why centralised: this rule must hold after login, after account
 * creation, on page refresh, and on any direct URL hit. Putting it
 * in one HOC means there is exactly one place to change the policy.
 *
 * Defense in depth — the backend is the real authority. This guard
 * is a UX redirect; data endpoints still verify ownership server-side
 * via the bearer JWT (see ``current_portal_workspace`` in
 * ``backend/app/api/v1/portal.py``). A user who manually pokes a
 * dashboard URL just sees a flicker and lands on /portal/onboarding.
 */
export function withOnboardingGate<P extends { session: PortalSession }>(
  Component: ComponentType<P>,
) {
  function Gated(props: P) {
    const router = useRouter();
    const status = props.session.expediente_status;

    useEffect(() => {
      if (status !== "complete") {
        router.replace("/portal/onboarding");
      }
    }, [router, status]);

    if (status !== "complete") return null;
    return <Component {...props} />;
  }
  // Compose with the existing session HOC so callers only need to
  // wrap once: ``export default withOnboardingGate(Inner);``
  return withPortalSession(Gated);
}
