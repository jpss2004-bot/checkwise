"use client";

import { useEffect, useState } from "react";

import { readAdminSession } from "@/lib/session/admin";

/**
 * Phase 4 — client seat tiers.
 *
 * An Approver (``client_admin``) — or internal support — may perform
 * portfolio writes (add / archive providers, edit the company profile).
 * A ``client_viewer`` is read + export only. These checks are
 * defense-in-depth: the backend enforces the same split server-side
 * (``ClientApprover`` gate), so hiding an affordance here is a UX nicety,
 * never the security boundary.
 */
export function isClientApprover(roles: readonly string[] | undefined): boolean {
  if (!roles) return false;
  // Approver = the client_admin tier, plus CheckWise staff (review team /
  // superadmin) who hold cross-tenant break-glass write access.
  return (
    roles.includes("client_admin") ||
    roles.includes("platform_admin") ||
    roles.includes("operations_admin")
  );
}

/** Live-session variant for client components. Returns ``false`` until the
 *  effect resolves (write affordances stay hidden, then reveal for an
 *  Approver) to keep SSR/hydration consistent. */
export function useClientApprover(): boolean {
  const [isApprover, setIsApprover] = useState(false);
  useEffect(() => {
    setIsApprover(isClientApprover(readAdminSession()?.roles));
  }, []);
  return isApprover;
}
