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

import { readAdminSession } from "@/lib/session/admin";

const API_BASE_URL =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE_URL) ||
  "http://127.0.0.1:8000";

export type ExpedienteStatus = "not_started" | "in_progress" | "complete";

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
}

function bearerHeader(): Record<string, string> {
  const session = readAdminSession();
  return session?.access_token
    ? { Authorization: `Bearer ${session.access_token}` }
    : {};
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
