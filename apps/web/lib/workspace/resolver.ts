/**
 * Build a snapshot of the authenticated provider's workspace.
 *
 * The previous version (CheckWise 1.6) fabricated values the session
 * doesn't actually carry: a "demo@checkwise.mx" placeholder email, a
 * "tenant-<workspace_id>" synthetic id, first/last-name guesses from
 * the local part of the placeholder email, and client/provider id
 * prefixes. Once invitations were retired, those defaults started
 * showing up verbatim in the UI — every test user saw "Tu próximo
 * paso, demo" and a locked "demo@checkwise.mx" identity row.
 *
 * Today the function returns only what the session actually knows.
 * Fields the backend hasn't surfaced yet (email, tenant id, client
 * id, provider id, first/last name) come back as null / empty
 * strings, and the consuming UI (WorkspaceIdentityCard, the
 * confirmation form) is responsible for branching on absence rather
 * than rendering a fabricated value.
 *
 * TODO[backend-integration]: when ``GET /api/v1/portal/workspace``
 * lands, replace this synthesiser with the backend call and remove
 * the null branches from the UI.
 */

import type { PortalSession } from "@/lib/session/portal";

import type {
  EditableProfileFields,
  ProtectedWorkspaceFields,
  WorkspaceContext,
} from "./types";

/**
 * Build a workspace snapshot from the portal session. No fabricated
 * values — fields the session doesn't expose come back as null so the
 * UI can render an empty / "aún no registrado" state instead of an
 * incorrect placeholder.
 */
export function buildWorkspaceContext(session: PortalSession): WorkspaceContext {
  const protectedFields: ProtectedWorkspaceFields = {
    workspace_id: session.workspace_id,
    // The session does not yet carry tenant / client / provider ids.
    // Surfacing fabricated "tenant-<wsid>" / "cli-<wsid>" prefixes was
    // misleading; the workspace identity card no longer renders them.
    tenant_id: null,
    client_id: null,
    provider_id: null,
    // Every authenticated portal user is a provider today. When the
    // session learns to distinguish client_admin / staff entries on
    // this surface, swap to ``session.role`` here.
    role: "provider",
    rfc: session.vendor_rfc !== "PENDIENTE" ? session.vendor_rfc : null,
    // The portal session does not currently expose the authenticated
    // user's email. Returning null is honest; the correction form's
    // initialCurrentValue branches on this and shows an empty field.
    email: null,
    company_legal_name: session.vendor_name,
    email_domain: null,
  };

  const editable: EditableProfileFields = {
    first_name: "",
    last_name: "",
    phone: null,
    job_title: null,
    contact_preference: "email",
  };

  return {
    protected: protectedFields,
    editable,
    invitation_hints: {
      company_hint: null,
      inviter: null,
    },
    confirmed_at_iso: null,
  };
}
