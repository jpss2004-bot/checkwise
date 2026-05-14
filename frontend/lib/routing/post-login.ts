/**
 * Centralized post-login routing decisions.
 *
 * Reads the expediente state and returns the correct portal route +
 * a banner hint for the destination. Keeping this in one place lets
 * /login, /activate, and any future entry path stay in sync on the
 * "where do we send the user next?" question.
 *
 * Routing rules (from CheckWise 1.5):
 *
 *   A. Public visitor             → / (this helper is not called)
 *   B. Clicks login               → /login
 *   C. Invited, not activated     → /activate (or /activate?token=…)
 *   D. Active + expediente empty  → /portal/onboarding (gate locked)
 *   E. Active + expediente uploaded but pending review
 *                                 → /portal/dashboard with a
 *                                   "provisional access" banner; the
 *                                   gate remains open as long as no
 *                                   mandatory item is rejected or empty
 *   F. Active + expediente complete → /portal/dashboard, no banner
 *   G. Admin role                 → see /login Admin path; this helper
 *                                   does NOT cover admin routing today
 *
 * Mandatory items in rejected / expired / pending / empty / needs_review
 * keep the user gated at /portal/onboarding. Optional items never block.
 *
 * TODO[backend-integration]: replace the in-memory expediente check
 * with a fetch from /api/v1/portal/onboarding once the API returns
 * the enriched shape we already mock locally.
 */

import {
  countExpediente,
  type ExpedienteRequirement,
} from "@/lib/mock/expediente";

export type PostLoginRoute = "/portal/onboarding" | "/portal/dashboard";

export type PostLoginBanner =
  | "none"
  | "provisional_access"
  | "expediente_blocked";

export interface PostLoginDecision {
  route: PostLoginRoute;
  banner: PostLoginBanner;
  /** Human-readable hint for telemetry / logs / banner copy. */
  reason: string;
  /** Snapshot of the expediente counts that drove the decision. */
  counts: ReturnType<typeof countExpediente>;
}

/**
 * Decide where to send a freshly-authenticated user.
 *
 * Pass the current expediente snapshot. Returns:
 *   - route: where to redirect
 *   - banner: which banner the destination should show
 *   - reason: short text for logs
 */
export function decidePostLoginRoute(
  requirements: ExpedienteRequirement[],
): PostLoginDecision {
  const counts = countExpediente(requirements);

  // Has any mandatory item left to act on (empty / pending / rejected
  // / expired / needs_review)? → keep at the gate.
  const mandatoryBlocking = requirements
    .filter((r) => r.required)
    .some((r) =>
      ["empty", "pending", "rejected", "expired", "needs_review"].includes(r.state),
    );

  if (mandatoryBlocking) {
    return {
      route: "/portal/onboarding",
      banner: "expediente_blocked",
      reason: "mandatory_requirement_needs_action",
      counts,
    };
  }

  // No blocking item but some mandatory items are uploaded / in_review.
  // The user has done their part — let them in, but make it clear the
  // expediente is still pending final approval.
  if (counts.in_review > 0) {
    return {
      route: "/portal/dashboard",
      banner: "provisional_access",
      reason: "expediente_in_review",
      counts,
    };
  }

  // All mandatory items approved → free access.
  return {
    route: "/portal/dashboard",
    banner: "none",
    reason: "expediente_complete",
    counts,
  };
}
