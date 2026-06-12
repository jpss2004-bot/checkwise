/**
 * Portal session — CheckWise 1.7
 *
 * Source of truth is now the httpOnly cookie issued by the backend at
 * POST /api/v1/portal/access and validated by GET /api/v1/portal/me.
 * The browser cannot read or write that cookie.
 *
 * What this module exposes:
 *   * Types (PortalSession, PersonaType) — unchanged shape
 *   * `fetchCurrentSession()` (async) — hits /me, caches in-memory
 *   * `readPortalSession()` (sync) — returns the in-memory cache or null
 *   * `clearPortalSession()` — async: posts /logout + clears cache
 *
 * Note: localStorage is no longer touched. Any stale entry under
 * `checkwise.portal.session.v1` is cleared on first `fetchCurrentSession`.
 */

import {
  fetchPortalMe,
  postPortalLogout,
  type WorkspaceSummary,
} from "@/lib/api/portal-session";

const LEGACY_LOCAL_STORAGE_KEY = "checkwise.portal.session.v1";

export type PersonaType = "moral" | "fisica";

export type ExpedienteStatus = "not_started" | "in_progress" | "complete";

export type ContactPreference = "email" | "whatsapp" | "both";

export type PortalSession = {
  workspace_id: string;
  /** Kept on the type for backward compatibility with existing code paths.
   *  Browser never sees the real access token in 1.7+. */
  access_token: string;
  persona_type: PersonaType;
  client_name: string;
  vendor_name: string;
  vendor_rfc: string;
  filial_name: string | null;
  contract_reference: string | null;
  onboarding_completed_at: string | null;
  /** Initial-expediente lifecycle marker.
   *  Only "complete" unlocks the dashboard. */
  expediente_status: ExpedienteStatus;
  /** Editable profile fields. ``full_name`` and ``contact_email`` are
   *  the User row's canonical name and email; the rest were added in
   *  migration 0016. ``profile_confirmed_at`` is the marker the
   *  /portal/entra-a-tu-espacio page uses to branch between the
   *  first-visit confirmation gate and the returning-user settings
   *  view. */
  full_name: string | null;
  contact_email: string | null;
  phone: string | null;
  job_title: string | null;
  contact_preference: ContactPreference;
  profile_confirmed_at: string | null;
  /** Phase 1 / Slice 1A — legal-consent gate state. The gate fires
   *  when ``legal_consent_accepted_at`` is null OR when
   *  ``legal_consent_version`` differs from
   *  ``current_legal_consent_version`` (Slice 1B — version-aware
   *  re-prompt). The current version is owned by the backend so a
   *  document bump cleanly invalidates older acceptances. */
  legal_consent_accepted_at: string | null;
  legal_consent_version: string | null;
  current_legal_consent_version: string | null;
};

let cached: PortalSession | null = null;

function clearLegacyLocalStorage(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(LEGACY_LOCAL_STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

export function summaryToSession(summary: WorkspaceSummary): PortalSession {
  return {
    workspace_id: summary.workspace_id,
    // Browser no longer holds the real access_token. We carry a
    // placeholder so existing TypeScript consumers continue to compile
    // — the cookie is what actually authenticates the request.
    access_token: "cookie-managed",
    persona_type: summary.persona_type as PersonaType,
    client_name: summary.client_name,
    vendor_name: summary.vendor_name,
    vendor_rfc: summary.vendor_rfc,
    filial_name: summary.filial_name,
    contract_reference: summary.contract_reference,
    onboarding_completed_at: summary.onboarding_completed_at,
    expediente_status: summary.expediente_status,
    full_name: summary.full_name,
    contact_email: summary.contact_email,
    phone: summary.phone,
    job_title: summary.job_title,
    contact_preference: summary.contact_preference,
    profile_confirmed_at: summary.profile_confirmed_at,
    legal_consent_accepted_at: summary.legal_consent_accepted_at,
    legal_consent_version: summary.legal_consent_version,
    current_legal_consent_version: summary.current_legal_consent_version,
  };
}

/** Replace the cached portal session in place (e.g. after PATCH
 *  /portal/.../profile resolves with a refreshed summary). */
export function setCachedPortalSession(session: PortalSession): void {
  cached = session;
}

/**
 * Read the in-memory session cache. Synchronous — returns null until
 * `fetchCurrentSession()` has populated the cache for the current
 * page lifetime. Most callers should prefer the async fetch.
 */
export function readPortalSession(): PortalSession | null {
  return cached;
}

/**
 * Bootstrap the session from the backend.
 *
 * Calls GET /api/v1/portal/me with credentials=include so the
 * httpOnly cookie is sent. Caches the response in memory. Returns
 * null on 401 (no valid cookie) or any network failure.
 */
export async function fetchCurrentSession(): Promise<PortalSession | null> {
  clearLegacyLocalStorage();
  const summary = await fetchPortalMe();
  if (!summary) {
    cached = null;
    return null;
  }
  cached = summaryToSession(summary);
  return cached;
}

/**
 * Clear the cookie + cache. Async because logout hits the backend.
 */
export async function clearPortalSession(): Promise<void> {
  cached = null;
  await postPortalLogout();
}
