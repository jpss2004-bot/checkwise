/**
 * Portal session API client — CheckWise 1.8
 *
 * Wraps GET /api/v1/portal/me and POST /api/v1/portal/logout.
 *
 * Auth resolution:
 *   1. Authorization: Bearer <jwt> from the admin/user session
 *      (always works cross-origin, immune to third-party cookie
 *      blocking — the failure mode that broke the demo on
 *      Vercel↔Render).
 *   2. ``credentials: "include"`` so the httpOnly cookie still gets
 *      sent when the browser allows it (same-origin or permissive
 *      third-party cookie policy).
 *
 * Returns null on 401 — callers treat that as "no session, send the
 * user to /". Network failures are also treated as no-session for
 * UX (the alternative is a noisy redirect loop).
 */

const API_BASE_URL =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE_URL) ||
  "http://127.0.0.1:8000";

export type ExpedienteStatus = "not_started" | "in_progress" | "complete";

export type ContactPreference = "email" | "whatsapp" | "both";

export interface WorkspaceSummary {
  workspace_id: string;
  persona_type: string;
  client_name: string;
  vendor_name: string;
  vendor_rfc: string;
  filial_name: string | null;
  contract_reference: string | null;
  onboarding_completed_at: string | null;
  expediente_status: ExpedienteStatus;
  // Profile fields landed in migration 0016 + portal API ``PATCH
  // /workspaces/{id}/profile``. ``profile_confirmed_at`` is the
  // canonical "has the user confirmed their profile at least once"
  // marker — the entra-a-tu-espacio page reads it to branch between
  // the first-visit confirmation gate and the returning-user
  // settings view.
  full_name: string | null;
  contact_email: string | null;
  phone: string | null;
  job_title: string | null;
  contact_preference: ContactPreference;
  profile_confirmed_at: string | null;
  // Phase 1 / Slice 1A — legal-consent gate state. The gate fires
  // when ``legal_consent_accepted_at`` is null OR when
  // ``legal_consent_version`` differs from
  // ``current_legal_consent_version`` (Slice 1B — version-aware
  // re-prompt after a document bump).
  legal_consent_accepted_at: string | null;
  legal_consent_version: string | null;
  current_legal_consent_version: string | null;
}

export interface WorkspaceProfileUpdate {
  full_name?: string;
  phone?: string;
  job_title?: string;
  contact_preference?: ContactPreference;
}

function bearerHeader(): Record<string, string> {
  // FE-SEC-1: auth now rides the httpOnly session cookie (every fetch in
  // this module uses credentials:include); no localStorage bearer header.
  return {};
}

/** Fetch the current session summary. JWT-first, cookie-fallback. */
export async function fetchPortalMe(): Promise<WorkspaceSummary | null> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/portal/me`, {
      method: "GET",
      credentials: "include",
      headers: { Accept: "application/json", ...bearerHeader() },
    });
    if (response.status === 401) return null;
    if (!response.ok) return null;
    return (await response.json()) as WorkspaceSummary;
  } catch {
    return null;
  }
}

/** Clear the portal session cookie server-side. Best-effort. */
export async function postPortalLogout(): Promise<void> {
  try {
    await fetch(`${API_BASE_URL}/api/v1/portal/logout`, {
      method: "POST",
      credentials: "include",
      headers: bearerHeader(),
    });
  } catch {
    /* logout is best-effort */
  }
}

/**
 * Persist editable profile fields (full_name, phone, job_title,
 * contact_preference) for the current workspace. Returns the refreshed
 * WorkspaceSummary so callers can update their session cache without a
 * follow-up /me round-trip. Returns null on auth / network failure —
 * the caller surfaces a generic "no pudimos guardar" message.
 */
export interface LegalConsentResponse {
  workspace_id: string;
  legal_consent_accepted_at: string;
  legal_consent_version: string;
}

/**
 * Persist the provider's acceptance of the legal-consent gate.
 *
 * The backend owns the canonical document version string so the
 * client does not pass one. Idempotent — a second call on an
 * already-accepted workspace returns the existing acceptance without
 * mutating the row. Returns null on auth / network failure.
 */
export async function acceptLegalConsent(
  workspace_id: string,
): Promise<LegalConsentResponse | null> {
  try {
    const response = await fetch(
      `${API_BASE_URL}/api/v1/portal/workspaces/${encodeURIComponent(workspace_id)}/legal-consent`,
      {
        method: "POST",
        credentials: "include",
        headers: { Accept: "application/json", ...bearerHeader() },
      },
    );
    if (!response.ok) return null;
    return (await response.json()) as LegalConsentResponse;
  } catch {
    return null;
  }
}

export async function patchWorkspaceProfile(
  workspace_id: string,
  payload: WorkspaceProfileUpdate,
): Promise<WorkspaceSummary | null> {
  try {
    const response = await fetch(
      `${API_BASE_URL}/api/v1/portal/workspaces/${encodeURIComponent(workspace_id)}/profile`,
      {
        method: "PATCH",
        credentials: "include",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          ...bearerHeader(),
        },
        body: JSON.stringify(payload),
      },
    );
    if (!response.ok) return null;
    return (await response.json()) as WorkspaceSummary;
  } catch {
    return null;
  }
}
