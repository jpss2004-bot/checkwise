import type { MetadataRoute } from "next";

import { SITE_URL } from "@/lib/site";

/**
 * Crawler policy for the public site.
 *
 * Only the marketing landing, the legal pages and the login entry are
 * meant to be indexed. Everything behind authentication — the provider
 * portal, the client workspace, the admin/platform consoles and the
 * report routes — is disallowed so crawlers do not waste budget on
 * pages that require a session (and would only ever render a 404 or a
 * redirect to /login).
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: [
        "/admin",
        "/platform",
        "/portal",
        "/client",
        "/reports",
        "/activate",
        "/forgot-password",
        "/reset-password",
        "/api/",
      ],
    },
    sitemap: `${SITE_URL}/sitemap.xml`,
    host: SITE_URL,
  };
}
