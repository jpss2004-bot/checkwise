import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * FE-SEC-2 — edge route guard for the staff/client surfaces.
 *
 * These segments authenticate with the httpOnly ``checkwise_session``
 * cookie (FE-SEC-1). Before FE-SEC-1 there was no server-side guard at
 * all — the route bundle shipped regardless of auth and protection was
 * 100% client-side. This redirects unauthenticated requests to /login
 * at the edge, before the protected shell renders, as defense-in-depth
 * on top of the per-page gates (the API remains the real authz boundary).
 *
 * Scope is deliberately narrow:
 *   * Only the ``checkwise_session`` surfaces — /admin, /client,
 *     /platform. The provider /portal uses a different cookie and has
 *     its own entry/mint flow, so it's left to its existing gate.
 *   * /reports/pdf is NOT matched — the backend Playwright renderer
 *     loads it server-side to produce export PDFs and must not redirect.
 *   * /admin/login is the login page itself, so it's exempted.
 *
 * Presence-only check: the cookie's signature/expiry is validated by the
 * API on the actual data request. This only stops the obvious
 * "no session at all" case cheaply at the edge.
 */

const SESSION_COOKIE = "checkwise_session";
const PUBLIC_EXCEPTIONS = ["/admin/login"];

export function middleware(request: NextRequest): NextResponse {
  const { pathname } = request.nextUrl;

  if (
    PUBLIC_EXCEPTIONS.some(
      (p) => pathname === p || pathname.startsWith(`${p}/`),
    )
  ) {
    return NextResponse.next();
  }

  if (request.cookies.has(SESSION_COOKIE)) {
    return NextResponse.next();
  }

  const loginUrl = request.nextUrl.clone();
  loginUrl.pathname = "/login";
  // /login sanitizes ``next`` against open-redirect / javascript: URLs.
  loginUrl.searchParams.set("next", pathname);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: ["/admin/:path*", "/client/:path*", "/platform/:path*"],
};
