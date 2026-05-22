/**
 * Build a snapshot of the authenticated provider's workspace.
 *
 * Reads everything from the backend-resolved ``PortalSession``.
 * ``email``, ``full_name``, ``phone``, ``job_title`` and
 * ``contact_preference`` come from the User row owning the workspace
 * (surfaced by ``GET /portal/me`` after migration 0016 landed the
 * supporting columns). Tenant / client / provider IDs stay null on
 * this surface — they aren't currently consumed by any caller and
 * the previous fabricated prefixes were misleading.
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
    // Authenticated user's email lives in session.contact_email after
    // migration 0016. ``email_domain`` is still derived here on the
    // client because no caller actually consumes it for verification
    // — it's display-only when present.
    email: session.contact_email,
    company_legal_name: session.vendor_name,
    email_domain: session.contact_email
      ? session.contact_email.split("@")[1]?.toLowerCase() ?? null
      : null,
  };

  // Split full_name at the first space so the form's two-field shape
  // round-trips reasonably. The form below uses the same convention
  // and re-joins on save, so the backend always stores the canonical
  // full_name; the split is purely a presentation concern.
  const fullName = session.full_name ?? "";
  const firstSpace = fullName.indexOf(" ");
  const firstName = firstSpace === -1 ? fullName : fullName.slice(0, firstSpace);
  const lastName = firstSpace === -1 ? "" : fullName.slice(firstSpace + 1);

  const editable: EditableProfileFields = {
    first_name: firstName,
    last_name: lastName,
    phone: session.phone,
    job_title: session.job_title,
    contact_preference: session.contact_preference,
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
