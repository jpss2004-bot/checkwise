/**
 * Build a snapshot of the authenticated provider's workspace.
 *
 * Phase 6 — the previous ``decideWorkspaceAccess`` routing helper has
 * been removed. Real routing today reads ``session.expediente_status``
 * straight from the backend (``GET /portal/me`` / ``POST /portal/enter``),
 * so the dead V1.6 access-decision branch isn't needed. What remains
 * here is the small ``buildWorkspaceContext`` synthesiser that wraps
 * a ``PortalSession`` (plus an optional activation-time invitation)
 * into the ``WorkspaceContext`` shape the workspace-identity card +
 * the entra-a-tu-espacio confirmation step both render.
 *
 * TODO[backend-integration]: replace this synthesiser with a real
 *   GET /api/v1/portal/workspace
 * call that returns ``ProtectedWorkspaceFields`` + ``EditableProfileFields``
 * resolved server-side. Never trust the localStorage session for any
 * protected value.
 */

import type { Invitation } from "@/lib/mock/invitations";
import type { PortalSession } from "@/lib/session/portal";

import type {
  EditableProfileFields,
  ProtectedWorkspaceFields,
  WorkspaceContext,
} from "./types";

function domainOf(email: string): string {
  const at = email.lastIndexOf("@");
  if (at === -1) return "";
  return email.slice(at + 1).toLowerCase();
}

/**
 * Build a workspace snapshot. When ``invitation`` is present the
 * protected fields are seeded from it (tokens carry trusted-enough
 * identifiers for the demo). When absent we derive a best-effort
 * snapshot from the portal session — clearly an interim hack.
 *
 * TODO[backend-integration]: drop this function once the backend
 * returns the same shape from ``GET /api/v1/portal/workspace``.
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
