import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import type { NextConfig } from "next";

const pkg = JSON.parse(
  readFileSync(join(__dirname, "package.json"), "utf8"),
) as { version?: string };

const appVersion = pkg.version ?? "0.0.0";
const gitSha = (
  process.env.VERCEL_GIT_COMMIT_SHA ||
  process.env.GIT_COMMIT_SHA ||
  ""
).slice(0, 7) || "local";

/**
 * Resolve the `distDir` Next.js should write builds into.
 *
 * Background:
 *   Next.js 15 + webpack stores absolute paths in the `.next/` manifests
 *   it generates. When the project's absolute path contains characters
 *   like em-dash (U+2014), some `fs.rename` and `require()` calls on
 *   macOS fail with ENOENT even though the directory exists. The dev
 *   server then loops on "Cannot find module '.next/server/middleware
 *   -manifest.json'" because the temp-to-final rename silently aborted.
 *
 *   Empirically the bug is keyed off the literal `.next` directory name
 *   under a path with non-ASCII characters. Renaming the dist dir to a
 *   different ASCII-only name (e.g. `.cw-next-<hash>`) sidesteps the
 *   race. On normal (ASCII) paths, we keep `.next` so tooling that
 *   targets it directly keeps working.
 *
 *   Override with `CHECKWISE_DIST_DIR=<path>` to force a specific dir.
 */

function pathHasNonAscii(s: string): boolean {
  for (let i = 0; i < s.length; i++) {
    if (s.charCodeAt(i) > 127) return true;
  }
  return false;
}

function resolveDistDir(): string {
  if (process.env.CHECKWISE_DIST_DIR) {
    return process.env.CHECKWISE_DIST_DIR;
  }
  if (!pathHasNonAscii(process.cwd())) {
    return ".next";
  }
  // Stable per-project hash so concurrent checkouts do not collide and
  // so CI cache keys remain deterministic.
  const hash = createHash("sha1").update(process.cwd()).digest("hex").slice(0, 10);
  return `.cw-next-${hash}`;
}

const nextConfig: NextConfig = {
  reactStrictMode: true,
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  distDir: resolveDistDir(),
  env: {
    NEXT_PUBLIC_APP_VERSION: appVersion,
    NEXT_PUBLIC_GIT_SHA: gitSha,
  },
  // FE-PERF-2 — @phosphor-icons/react is imported via its barrel in 130+
  // files, and motion (motion/react) in ~22. Without this, Next pulls the
  // whole module graph into dev compilation and can ship unused exports.
  // optimizePackageImports rewrites the barrel imports to per-export deep
  // imports automatically (no code change), shrinking route bundles and
  // speeding dev refresh.
  experimental: {
    optimizePackageImports: ["@phosphor-icons/react", "motion"],
  },
  // FE-SEC-5 — baseline security headers on every frontend response. The
  // API (Render) sets its own headers; these protect the user-facing app
  // (Vercel).
  async headers() {
    // CW-XSS-001 — Content-Security-Policy is ENFORCED in production and
    // report-only in dev. Enforcing it makes default-src/object-src/
    // frame-ancestors/base-uri actually block in prod, shrinking the XSS
    // attack surface (the exfiltration path the localStorage-token finding
    // depends on). 'unsafe-eval' is only needed by the dev overlay / HMR,
    // so it is added in DEV ONLY and dropped in prod. 'unsafe-inline' on
    // script-src must stay until a per-request nonce is wired (Next injects
    // an un-nonced inline bootstrap script); removing it now would
    // white-screen the app — a nonce migration is a separate, deliberate
    // change. connect-src is derived from the API origin; script/frame
    // allow the Calendly booking embed.
    const isProd = process.env.NODE_ENV === "production";
    let apiOrigin = "";
    try {
      const raw = process.env.NEXT_PUBLIC_API_BASE_URL;
      if (raw) apiOrigin = new URL(raw).origin;
    } catch {
      apiOrigin = "";
    }
    const csp = [
      "default-src 'self'",
      "base-uri 'self'",
      "object-src 'none'",
      "frame-ancestors 'none'",
      "form-action 'self'",
      // 'unsafe-inline' stays (un-nonced Next bootstrap). 'unsafe-eval' is
      // dev-overlay/HMR only → dropped in prod.
      `script-src 'self' 'unsafe-inline'${isProd ? "" : " 'unsafe-eval'"} https://assets.calendly.com`,
      "style-src 'self' 'unsafe-inline' https://assets.calendly.com",
      "img-src 'self' data: blob: https:",
      "font-src 'self' data:",
      `connect-src 'self' ${apiOrigin} https://calendly.com`.replace(/\s+/g, " ").trim(),
      // 'blob:' lets the document-upload wizard preview the just-selected
      // PDF in an <iframe src> built from URL.createObjectURL. Blob URLs are
      // same-origin (minted by the page itself), so this does NOT permit
      // arbitrary external frames. Without it the ENFORCED prod CSP silently
      // blocks the in-memory preview → blank "Vista previa del PDF"
      // (bug 2026-06-26: "No permite la visualización del documento").
      "frame-src 'self' blob: https://calendly.com https://*.calendly.com https://calendar.app.google",
      "worker-src 'self' blob:",
    ].join("; ");

    const securityHeaders = [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "X-Frame-Options", value: "DENY" },
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      {
        key: "Permissions-Policy",
        value: "camera=(), microphone=(), geolocation=()",
      },
      {
        key: "Strict-Transport-Security",
        value: "max-age=63072000; includeSubDomains; preload",
      },
      {
        // Enforce in production; report-only in dev so the dev overlay / HMR
        // (which needs 'unsafe-eval') keeps working without being blocked.
        key: isProd
          ? "Content-Security-Policy"
          : "Content-Security-Policy-Report-Only",
        value: csp,
      },
    ];
    return [{ source: "/:path*", headers: securityHeaders }];
  },
  // Operaciones consolidation (2026-06-30). The separate Plataforma
  // (/platform/*) superadmin console was retired and folded into the one
  // Operaciones console: account provisioning + the user directory now
  // live at /admin/cuentas, and feedback triage at /admin/feedback-reports
  // (both gated to operations_admin). These permanent redirects keep old
  // emails, bookmarks, and the prior /admin/users/new alias working. The
  // most specific sources come first (Next matches in array order), so
  // /platform/users/new wins over the /platform/users/:id param and the
  // /platform/:path* catch-all is the last resort.
  async redirects() {
    return [
      { source: "/admin/users/new", destination: "/admin/cuentas/new", permanent: true },
      { source: "/platform/users/new", destination: "/admin/cuentas/new", permanent: true },
      { source: "/platform/users/:id", destination: "/admin/cuentas/:id", permanent: true },
      { source: "/platform/users", destination: "/admin/cuentas", permanent: true },
      { source: "/platform/feedback-reports", destination: "/admin/feedback-reports", permanent: true },
      { source: "/platform/audit-log", destination: "/admin/audit-log", permanent: true },
      { source: "/platform/dashboard", destination: "/admin/dashboard", permanent: true },
      { source: "/platform", destination: "/admin/dashboard", permanent: true },
      // Safety net for any other legacy /platform/* deep link.
      { source: "/platform/:path*", destination: "/admin/dashboard", permanent: true },
    ];
  },
};

export default nextConfig;
