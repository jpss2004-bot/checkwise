/**
 * Admin (internal-staff / client / reviewer) session metadata.
 *
 * FE-SEC-1 (audit 2026-06-15): the real bearer JWT is NO LONGER stored
 * here. Authentication rides an httpOnly cookie the backend sets at
 * login (mirroring the provider portal); ``access_token`` now carries a
 * ``"cookie-managed"`` placeholder. localStorage keeps only the
 * non-credential identity slice (user, roles, expiry) so the shell can
 * render its header without an extra /auth/me round trip. An XSS can no
 * longer read a usable credential from localStorage.
 *
 * Intentionally separate from ``portal-session.ts`` (provider portal),
 * so a shared user can hold both at once (a staffer viewing their own
 * demo workspace).
 */

const STORAGE_KEY = "checkwise.admin.session.v1";
const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

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

export type AdminSession = {
  access_token: string;
  expires_at: string;
  user: AdminSessionUser;
  roles: string[];
  organization_ids: string[];
};

export function readAdminSession(): AdminSession | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as AdminSession;
    // FE-SEC-1: validity is "do we have an identity + is it unexpired",
    // not "do we hold a token" (the token now lives in the cookie).
    if (!parsed.user?.id) return null;
    if (isExpired(parsed)) {
      window.localStorage.removeItem(STORAGE_KEY);
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function writeAdminSession(session: AdminSession): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

export function clearAdminSession(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEY);
  // FE-SEC-1: also clear the httpOnly session cookie server-side —
  // dropping the localStorage metadata alone would leave the cookie
  // (the real credential) valid. ``keepalive`` lets the request finish
  // even when the caller redirects to /login immediately after. Fire-
  // and-forget: a logout must never throw, and the cookie also expires
  // on its own. The endpoint requires no auth, so it's safe on the
  // 401-cleanup paths too.
  try {
    void fetch(`${API_BASE_URL}/api/v1/auth/logout`, {
      method: "POST",
      credentials: "include",
      keepalive: true,
    }).catch(() => {});
  } catch {
    /* ignore */
  }
}

function isExpired(session: AdminSession): boolean {
  const ms = Date.parse(session.expires_at);
  if (Number.isNaN(ms)) return false;
  return ms <= Date.now();
}
