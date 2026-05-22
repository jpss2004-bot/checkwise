/**
 * App version + build SHA for the marketing footer.
 *
 * Values are injected at build time via [next.config.ts]:
 *   - NEXT_PUBLIC_APP_VERSION ← apps/web/package.json "version"
 *   - NEXT_PUBLIC_GIT_SHA     ← VERCEL_GIT_COMMIT_SHA (short) or "local"
 *
 * Fallbacks keep local `next dev` working when the env vars are missing.
 */

export const APP_VERSION =
  process.env.NEXT_PUBLIC_APP_VERSION?.trim() || "0.0.0";

export const BUILD_SHA =
  process.env.NEXT_PUBLIC_GIT_SHA?.trim() || "local";
