/**
 * Resolve a WorkspaceContext + access outcome.
 *
 * Today the input is a PortalSession (V1.5 mock) and a known
 * invitation record (when the user came through /activate?token=…).
 * Tomorrow the backend will hand back the same shape on every
 * session bootstrap.
 *
 * TODO[backend-integration]: replace the mock plumbing with a
 *   GET /api/v1/portal/workspace
 * call that returns ProtectedWorkspaceFields + EditableProfileFields
 * resolved server-side. Never trust the localStorage session for any
 * protected value.
 *
 * TODO[security-backend]: enforce every mismatch / expiry / role
 * dispute check on the backend. The frontend checks below exist
 * for UX clarity only — they must not be the access boundary.
 */

import type { Invitation } from "@/lib/mock/invitations";
import type { PortalSession } from "@/lib/session/portal";
import {
  countExpediente,
  MOCK_EXPEDIENTE,
  type ExpedienteRequirement,
} from "@/lib/mock/expediente";

import type {
  ProtectedWorkspaceFields,
  EditableProfileFields,
  WorkspaceContext,
  WorkspaceAccessOutcome,
} from "./types";

const GENERIC_DOMAINS = new Set([
  "gmail.com",
  "outlook.com",
  "hotmail.com",
  "icloud.com",
  "yahoo.com",
  "live.com",
  "msn.com",
  "protonmail.com",
  "proton.me",
]);

function domainOf(email: string): string {
  const at = email.lastIndexOf("@");
  if (at === -1) return "";
  return email.slice(at + 1).toLowerCase();
}

/**
 * Build a workspace snapshot. When `invitation` is present the
 * protected fields are seeded from it (tokens carry trusted-enough
 * identifiers for the demo). When absent we derive a best-effort
 * snapshot from the portal session — clearly an interim hack.
 *
 * TODO[backend-integration]: drop this function once the backend
 * returns the same shape.
 */
export function buildWorkspaceContext(
  session: PortalSession,
  invitation: Invitation | null,
): WorkspaceContext {
  const email = invitation?.email ?? "demo@checkwise.mx";
  const domain = domainOf(email);

  const protectedFields: ProtectedWorkspaceFields = {
    workspace_id: session.workspace_id,
    tenant_id: `tenant-${session.workspace_id}`,
    client_id: invitation?.role === "client" ? `cli-${session.workspace_id}` : null,
    provider_id: invitation?.role === "provider" ? `prv-${session.workspace_id}` : null,
    role: invitation?.role ?? "provider",
    rfc: session.vendor_rfc !== "PENDIENTE" ? session.vendor_rfc : null,
    email,
    company_legal_name: session.vendor_name,
    email_domain: domain,
  };

  const editable: EditableProfileFields = {
    first_name: invitation?.email?.split("@")[0]?.split(".")[0] ?? "",
    last_name: invitation?.email?.split("@")[0]?.split(".")[1] ?? "",
    phone: null,
    job_title: null,
    contact_preference: "email",
  };

  return {
    protected: protectedFields,
    editable,
    invitation_hints: {
      company_hint: invitation?.company_hint ?? null,
      inviter: invitation?.inviter ?? null,
    },
    confirmed_at_iso: null,
  };
}

/**
 * Compute the access outcome for the current workspace + expediente
 * snapshot.
 *
 * This is the single source of truth for the 1.6 routing rules:
 *
 *   blocked            → invitation problem (expired / used / revoked /
 *                        mismatch / unknown workspace)
 *   needs_confirmation → first entry, not yet confirmed (default for
 *                        first login & first activation success)
 *   redirect_onboarding → mandatory item missing / rejected / expired
 *   allow_provisional   → all mandatory uploaded, some still in_review
 *   allow              → all mandatory approved
 *
 * The frontend uses this for UX. The backend must enforce the same
 * decisions for actual authorization.
 */
export function decideWorkspaceAccess(input: {
  workspace: WorkspaceContext;
  /** Was this workspace already confirmed (e.g. user came back). */
  alreadyConfirmed: boolean;
  /** Optional invitation snapshot if coming from /activate. */
  invitation?: Invitation | null;
  /** Expediente snapshot. */
  requirements?: ExpedienteRequirement[];
}): WorkspaceAccessOutcome {
  const { workspace, alreadyConfirmed, invitation } = input;
  const requirements = input.requirements ?? MOCK_EXPEDIENTE;

  // ─── Block conditions (invitation problems) ─────────────────────
  if (invitation) {
    if (Date.parse(invitation.expires_at_iso) < Date.now()) {
      return { decision: "blocked", reason: "invitation_expired" };
    }
  }
  // Domain mismatch — only flag when token has a company hint we can
  // sanity-check and the email domain is non-generic.
  if (
    invitation?.company_hint &&
    workspace.protected.email_domain &&
    !GENERIC_DOMAINS.has(workspace.protected.email_domain) &&
    !slugMatches(
      workspace.protected.email_domain,
      invitation.company_hint,
    ) &&
    !slugMatches(
      workspace.protected.email_domain,
      workspace.protected.company_legal_name,
    )
  ) {
    return { decision: "blocked", reason: "domain_mismatch" };
  }

  if (!alreadyConfirmed) {
    return {
      decision: "needs_confirmation",
      route: "/portal/entra-a-tu-espacio",
      reason: "first_entry",
    };
  }

  // ─── Expediente-driven routing ──────────────────────────────────
  const counts = countExpediente(requirements);
  const mandatoryBlocking = requirements
    .filter((r) => r.required)
    .some((r) =>
      ["empty", "pending", "rejected", "expired", "needs_review"].includes(r.state),
    );

  if (mandatoryBlocking) {
    return {
      decision: "redirect_onboarding",
      route: "/portal/onboarding",
      reason: "mandatory_blocking",
    };
  }
  if (counts.in_review > 0) {
    return {
      decision: "allow_provisional",
      route: "/portal/dashboard",
      reason: "in_review",
    };
  }
  return { decision: "allow", route: "/portal/dashboard" };
}

/**
 * Loose comparison: does this email domain share a normalized
 * substring with the invitation company hint? Catches
 * "constructoraabc.com" ↔ "Constructora ABC" but never gives a
 * security guarantee — backend must do real validation.
 */
function slugMatches(domain: string, companyish: string): boolean {
  const slug = (s: string) =>
    s
      .toLowerCase()
      .normalize("NFKD")
      .replace(/[̀-ͯ]/g, "")
      .replace(/[^a-z0-9]+/g, "");
  const a = slug(domain.split(".")[0] ?? "");
  const b = slug(companyish);
  if (!a || !b) return false;
  return b.includes(a) || a.includes(b);
}
