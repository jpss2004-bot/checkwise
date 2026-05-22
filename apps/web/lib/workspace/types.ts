/**
 * Workspace + correction types for CheckWise 1.6.
 *
 * These types model the post-auth workspace confirmation step. They
 * deliberately separate **protected** identifiers (which only the
 * backend can mutate) from **editable** profile fields (which the
 * user may update inline).
 *
 * Security rule of thumb: every value a token provides is a *display
 * hint*. The backend remains the source of truth. The frontend never
 * writes to a protected field directly — it submits a
 * ProfileCorrectionRequest that goes through review.
 *
 * Spec: docs/CHECKWISE_1_6.md
 */

import type { InvitationRole } from "@/lib/email/welcome";

/**
 * Sensitive identifiers that map a user to a tenant + relationship.
 *
 * The frontend MUST NOT allow free editing of these fields. Any user
 * intent to change them goes through a ProfileCorrectionRequest with
 * `requires_admin_review = true`.
 *
 * TODO[security-backend]: backend must verify every value below
 * against the authenticated session — never trust the client copy.
 */
export interface ProtectedWorkspaceFields {
  /** Internal workspace handle. */
  workspace_id: string;
  /** Tenant the workspace lives in. Null until the backend exposes it
   *  in the session payload; the UI must not fabricate one. */
  tenant_id: string | null;
  /** Resolved client / provider IDs. Null until the session carries them. */
  client_id: string | null;
  provider_id: string | null;
  /** Canonical role assigned by the invitation / admin, not by UI. */
  role: InvitationRole;
  /** Legal RFC, locked once the workspace is created. */
  rfc: string | null;
  /** Email anchor of the invitation. Null until the backend surfaces
   *  the authenticated user's contact email on this surface. */
  email: string | null;
  /** Canonical legal company name. */
  company_legal_name: string;
  /** Domain portion of the email (for mismatch checks). Null when
   *  ``email`` is null. */
  email_domain: string | null;
}

/**
 * Fields the user is allowed to edit inline on the workspace
 * confirmation page. Everything here is profile-scoped (not tenant-
 * scoped), so changes are safe to persist without admin review.
 */
export interface EditableProfileFields {
  first_name: string;
  last_name: string;
  phone: string | null;
  job_title: string | null;
  /** Preferred channel for CheckWise notifications. */
  contact_preference: "email" | "whatsapp" | "both";
}

/**
 * Combined snapshot the workspace confirmation page renders.
 */
export interface WorkspaceContext {
  /** Tenant-locked identifiers. Display-only on the client. */
  protected: ProtectedWorkspaceFields;
  /** Profile fields the user can edit inline. */
  editable: EditableProfileFields;
  /** Optional display hints from the invitation (company hint, inviter). */
  invitation_hints: {
    company_hint: string | null;
    inviter: string | null;
  };
  /** Whether the user already confirmed this workspace before. */
  confirmed_at_iso: string | null;
}

/**
 * Phase 6 — ``WorkspaceAccessOutcome`` and the matching
 * ``decideWorkspaceAccess`` helper were deleted. Real routing now reads
 * ``session.expediente_status`` straight from the backend at every
 * post-auth surface (``/login``, ``/portal/entra-a-tu-espacio``,
 * ``withOnboardingGate``), so the granular access-decision type was
 * dead code. If future flows need a structured outcome again, restore
 * the type alongside its first real consumer.
 */

/**
 * Body of a profile / workspace correction request. Anything beyond
 * the EditableProfileFields surface must go through this object so
 * the backend can audit + decide.
 */
export interface ProfileCorrectionRequest {
  /** Stable client-side id; backend can reissue. */
  id: string;
  workspace_id: string;
  /** Field name as it appears in the canonical record. */
  field: keyof ProtectedWorkspaceFields | "company_display_name" | "other";
  /** Value the user currently sees. */
  current_value: string;
  /** Value the user wants. */
  proposed_value: string;
  /** Free-text reason. Required if changing a protected field. */
  reason: string;
  /** Optional additional context (email thread, doc link, etc.). */
  message?: string;
  /** Always true when touching a ProtectedWorkspaceFields key. */
  requires_admin_review: boolean;
  /** Set client-side when the request is created. */
  created_at_iso: string;
}

/**
 * Map a protected field name to a Spanish display label. Single
 * source of truth so the UI never spells these out inline.
 */
export const PROTECTED_FIELD_LABEL: Record<
  keyof ProtectedWorkspaceFields,
  string
> = {
  workspace_id: "ID de workspace",
  tenant_id: "ID de tenant",
  client_id: "ID de cliente",
  provider_id: "ID de proveedor",
  role: "Rol asignado",
  rfc: "RFC",
  email: "Correo de invitación",
  company_legal_name: "Razón social",
  email_domain: "Dominio del correo",
};

export const EDITABLE_FIELD_LABEL: Record<keyof EditableProfileFields, string> = {
  first_name: "Nombre",
  last_name: "Apellido",
  phone: "Teléfono",
  job_title: "Cargo o puesto",
  contact_preference: "Canal de contacto",
};
