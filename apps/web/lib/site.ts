/**
 * Canonical public origin for the deployed frontend.
 *
 * checkwise.com.mx is the production domain (the Vercel deployment
 * 307-redirects there). Note that checkwise.mx — without `.com` — is a
 * different, unrelated site; never use it in metadata or sitemaps.
 *
 * Used by the metadata base in `app/layout.tsx`, `app/robots.ts` and
 * `app/sitemap.ts` so canonical URLs, the sitemap and Open Graph
 * images all resolve against the same origin, including on Vercel
 * preview deployments.
 */
export const SITE_URL = "https://checkwise.com.mx";

export const SITE_NAME = "CheckWise";
