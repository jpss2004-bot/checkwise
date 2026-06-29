/**
 * Shared error/expiry handling for the staff + client data clients.
 *
 * Two concerns, both surfaced by the 2026-06-29 audit:
 *
 *  1. Raw-JSON leak — the data clients used to throw the raw response body
 *     as the error message, so pages rendered the literal
 *     `{"detail":"…"}` envelope in their error cards. ``humanizeApiError``
 *     extracts the FastAPI ``detail`` string (or a generic Spanish
 *     fallback) so users never see raw JSON.
 *
 *  2. Cold-load / blocked-cookie 401 — after a hard reload (or when the
 *     cross-site session cookie is blocked, e.g. Safari ITP) the in-memory
 *     bearer is gone and the first data call 401s. The documented behavior
 *     (see ``lib/session/admin.ts``) is to route the user back to /login,
 *     NOT to render a broken error card. ``redirectToLoginIfSessionLost``
 *     performs that redirect exactly once, and only when we hold no
 *     in-memory token — so a normal in-session 401 (e.g. a permission
 *     issue) is left for the caller to surface.
 */

import { clearAdminSession, getAdminAccessToken } from "@/lib/session/admin";

let redirecting = false;

/** Turn an API error body into a human, non-leaking message. */
export function humanizeApiError(rawBody: string, statusText: string): string {
  const generic = "Ocurrió un error. Vuelve a intentarlo.";
  if (!rawBody) return statusText || generic;
  try {
    const parsed = JSON.parse(rawBody) as {
      detail?: unknown;
    };
    const detail = parsed?.detail;
    if (typeof detail === "string" && detail.trim()) return detail.trim();
    if (
      Array.isArray(detail) &&
      detail[0] &&
      typeof (detail[0] as { msg?: unknown }).msg === "string"
    ) {
      return String((detail[0] as { msg: string }).msg);
    }
  } catch {
    // not JSON — fall through
  }
  const trimmed = rawBody.trim();
  // Never echo a raw JSON / HTML / object envelope back to the user.
  if (
    trimmed.startsWith("{") ||
    trimmed.startsWith("[") ||
    trimmed.startsWith("<")
  ) {
    return statusText || generic;
  }
  return trimmed.length > 0 && trimmed.length <= 200
    ? trimmed
    : statusText || generic;
}

/**
 * If a staff/client data call 401s and we hold no in-memory bearer (the
 * cold-load / blocked-cookie case), clear the stale identity slice and
 * route to /login with a friendly reason + a return path. Returns true
 * when a redirect was initiated so the caller can stop rendering.
 */
export function redirectToLoginIfSessionLost(status: number): boolean {
  if (status !== 401) return false;
  if (typeof window === "undefined") return false;
  // A 401 while we still hold a token is a genuine in-session
  // permission/expiry issue — leave it to the caller.
  if (getAdminAccessToken()) return false;
  const path = window.location.pathname;
  if (
    path === "/login" ||
    path === "/activate" ||
    path.startsWith("/legal")
  ) {
    return false;
  }
  if (redirecting) return true;
  redirecting = true;
  clearAdminSession();
  const next = encodeURIComponent(
    window.location.pathname + window.location.search,
  );
  window.location.replace(`/login?reason=session_expired&next=${next}`);
  return true;
}
