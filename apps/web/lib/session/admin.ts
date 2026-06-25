/**
 * Admin (internal-staff / client) session helpers.
 *
 * Patch 6 (Auth + RBAC) introduced real LegalShelf-staff accounts. The
 * frontend used to store the bearer JWT *and* the identity slice in
 * localStorage so the admin shell could render the header without an
 * extra /auth/me round trip on every navigation.
 *
 * FE-SEC-1 / CW-FE (F6) — the bearer JWT is the keys-to-the-kingdom
 * secret; any XSS or same-origin script could read it out of
 * localStorage. It now lives ONLY in a module-level in-memory variable
 * (gone on reload) and, server-side, in the httpOnly ``checkwise_session``
 * cookie the backend sets at /auth/login. localStorage keeps just the
 * NON-secret identity slice (user / roles / organization_ids /
 * expires_at) so the shells can still render synchronously.
 *
 * Auth resolution on every request mirrors ``portal-session.ts``:
 *   1. ``Authorization: Bearer <in-memory token>`` when we still hold it
 *      (this page lifetime) — cross-origin safe, immune to third-party
 *      cookie blocking.
 *   2. ``credentials: "include"`` so the httpOnly cookie authenticates
 *      after a reload (when the in-memory token is gone). If the
 *      cross-site cookie is blocked (Safari ITP), the call 401s and the
 *      caller routes the user back to /login.
 *
 * Intentionally separate from ``portal-session.ts``: the provider
 * portal keeps its own cookie-based path, so a shared user can hold
 * both at the same time (e.g. a LegalShelf staffer looking at their own
 * demo workspace).
 */

const STORAGE_KEY = "checkwise.admin.session.v1";

export type AdminSessionUser = {
  id: string;
  email: string;
  full_name: string;
  status: string;
  last_login_at: string | null;
  /**
   * Forced-first-login flag. Set when the user logged in with a
   * temporary password and has not yet rotated it via /activate.
   * /login's boot effect routes such sessions back to /activate so
   * the user cannot bypass the rotation by closing the activation
   * page (security fix CW-AUD-P1-01).
   */
  must_change_password?: boolean;
};

/**
 * The persisted identity slice. NOTE: no ``access_token`` — the bearer
 * JWT is held in memory (see ``setAdminAccessToken``) and the httpOnly
 * cookie, never in localStorage.
 */
export type AdminSession = {
  expires_at: string;
  user: AdminSessionUser;
  roles: string[];
  organization_ids: string[];
};

// ---------------------------------------------------------------------------
// In-memory access token (FE-SEC-1)
// ---------------------------------------------------------------------------
//
// Module-level — survives client-side navigation within a single page
// lifetime, gone on a full reload. On reload the httpOnly cookie carries
// authentication instead; if it's blocked, requests 401 and the user
// re-logs in.

let inMemoryAccessToken: string | null = null;

/** Set (or clear, with ``null``) the in-memory bearer token. */
export function setAdminAccessToken(token: string | null): void {
  inMemoryAccessToken = token;
}

/** Read the in-memory bearer token. ``null`` after a reload or logout. */
export function getAdminAccessToken(): string | null {
  return inMemoryAccessToken;
}

/**
 * Authorization header for staff API calls: the in-memory bearer when we
 * hold it, otherwise empty so the httpOnly cookie (``credentials:
 * "include"``) authenticates. Mirrors ``portal-session.ts::bearerHeader``.
 */
export function adminAuthHeader(): Record<string, string> {
  return inMemoryAccessToken
    ? { Authorization: `Bearer ${inMemoryAccessToken}` }
    : {};
}

// ---------------------------------------------------------------------------
// Persisted identity slice
// ---------------------------------------------------------------------------

export function readAdminSession(): AdminSession | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as AdminSession & {
      access_token?: unknown;
    };
    if (!parsed.user?.id) return null;
    if (isExpired(parsed)) {
      window.localStorage.removeItem(STORAGE_KEY);
      return null;
    }
    // FE-SEC-1 migration — older builds persisted the bearer JWT under
    // ``access_token``. If a stale one is still sitting in localStorage,
    // rewrite the entry without it so the secret can't linger or be
    // exfiltrated. The in-memory token + cookie are the only sources of
    // truth now; we intentionally do NOT adopt the stale token.
    if ("access_token" in parsed) {
      const identity = toIdentity(parsed);
      writeAdminSession(identity);
      return identity;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function writeAdminSession(session: AdminSession): void {
  if (typeof window === "undefined") return;
  // Persist ONLY the identity slice — never the bearer token, even if a
  // caller hands us a wider object.
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(toIdentity(session)));
}

/**
 * Drop the session: clear the persisted identity AND the in-memory
 * bearer token. (Does not touch the server cookie — call
 * ``logoutAdmin`` for an explicit user-initiated logout.)
 */
export function clearAdminSession(): void {
  inMemoryAccessToken = null;
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEY);
}

function toIdentity(session: AdminSession): AdminSession {
  return {
    expires_at: session.expires_at,
    user: session.user,
    roles: session.roles,
    organization_ids: session.organization_ids,
  };
}

function isExpired(session: AdminSession): boolean {
  const ms = Date.parse(session.expires_at);
  if (Number.isNaN(ms)) return false;
  return ms <= Date.now();
}
