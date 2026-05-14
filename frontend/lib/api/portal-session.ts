/**
 * Portal session API client — CheckWise 1.7
 *
 * Wraps GET /api/v1/portal/me and POST /api/v1/portal/logout. Both
 * use `credentials: "include"` so the browser sends the
 * checkwise_portal_session httpOnly cookie.
 *
 * Returns null on 401 — callers treat that as "no session, send the
 * user to /". Network failures are also treated as no-session for
 * UX (the alternative is a noisy redirect loop).
 */

const API_BASE_URL =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE_URL) ||
  "http://127.0.0.1:8000";

export interface WorkspaceSummary {
  workspace_id: string;
  persona_type: string;
  client_name: string;
  vendor_name: string;
  vendor_rfc: string;
  filial_name: string | null;
  contract_reference: string | null;
  onboarding_completed_at: string | null;
}

/** Fetch the current session summary from the cookie-protected /me endpoint. */
export async function fetchPortalMe(): Promise<WorkspaceSummary | null> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/portal/me`, {
      method: "GET",
      credentials: "include",
      headers: { Accept: "application/json" },
    });
    if (response.status === 401) return null;
    if (!response.ok) return null;
    return (await response.json()) as WorkspaceSummary;
  } catch {
    return null;
  }
}

/** Clear the portal session cookie server-side. */
export async function postPortalLogout(): Promise<void> {
  try {
    await fetch(`${API_BASE_URL}/api/v1/portal/logout`, {
      method: "POST",
      credentials: "include",
    });
  } catch {
    /* logout is best-effort */
  }
}
