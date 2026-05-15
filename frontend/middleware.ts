import { NextResponse, type NextRequest } from "next/server";

/**
 * Server-side route protection for /portal/*.
 *
 * Two layers of defense protect the provider portal:
 *
 *   1. The httpOnly portal session cookie ``checkwise_portal_session``
 *      (issued by POST /api/v1/portal/enter). The middleware checks
 *      *only* for the cookie's presence — signature validation lives in
 *      the backend, where it has access to the JWT secret.
 *
 *   2. Client-side guards in the page components themselves. If the
 *      cookie is missing the page falls back to /login.
 *
 * The middleware is the cheap first hop: it stops a logged-out user
 * from even loading the SPA bundle for /portal/* routes. Server-side
 * APIs still enforce the real check.
 *
 * The /admin/* routes use a localStorage-backed JWT and therefore
 * cannot be checked by the edge middleware (no cookie). Those routes
 * rely on their existing client-side ``readAdminSession`` guards.
 */

const PORTAL_COOKIE_NAME = "checkwise_portal_session";

export function middleware(request: NextRequest) {
  const cookie = request.cookies.get(PORTAL_COOKIE_NAME);
  if (!cookie || !cookie.value) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("from", request.nextUrl.pathname);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  // /portal/entra-a-tu-espacio is exempt because that page is the one
  // that *mints* the cookie via /portal/enter. All other /portal/*
  // routes require the cookie up-front.
  matcher: [
    "/portal/dashboard/:path*",
    "/portal/onboarding/:path*",
    "/portal/calendar/:path*",
    "/portal/upload/:path*",
    "/portal/reports/:path*",
    "/portal/submissions/:path*",
  ],
};
