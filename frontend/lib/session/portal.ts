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
 *   * `writePortalSession()` — transition shim used only by the
 *     mocked /activate flow until P1-1 wires real activation to
 *     /portal/access. It populates the in-memory cache but does NOT
 *     persist anywhere; a reload bounces the user back to /.
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

function summaryToSession(summary: WorkspaceSummary): PortalSession {
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
  };
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

/**
 * Transition shim. Used only by the mocked /activate flow to
 * populate the in-memory cache when activation succeeds without
 * actually minting a backend session. Logs a deprecation hint and
 * does NOT persist anywhere — a reload bounces the user to /.
 *
 * TODO[backend-integration]: when P1-1 wires activation to a real
 * /api/v1/activation/* endpoint that returns a cookie, remove this
 * shim entirely.
 */
export function writePortalSession(session: PortalSession): void {
  if (typeof console !== "undefined") {
    console.warn(
      "[checkwise] writePortalSession is a transition shim; the real session is the httpOnly cookie minted by POST /api/v1/portal/enter.",
    );
  }
  cached = session;
}
