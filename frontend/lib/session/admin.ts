/**
 * Admin (internal-staff) session helpers backed by localStorage.
 *
 * Patch 6 (Auth + RBAC) introduces real LegalShelf-staff accounts. The
 * frontend stores the bearer JWT plus a small denormalised slice of the
 * user identity so the admin shell can render the header without an
 * extra /auth/me round trip on every navigation.
 *
 * Intentionally separate from ``portal-session.ts``: the provider
 * portal continues to authenticate via opaque workspace tokens, so a
 * shared user can hold both at the same time (e.g. a LegalShelf staffer
 * looking at their own demo workspace).
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
    if (!parsed.access_token || !parsed.user?.id) return null;
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
}

function isExpired(session: AdminSession): boolean {
  const ms = Date.parse(session.expires_at);
  if (Number.isNaN(ms)) return false;
  return ms <= Date.now();
}
