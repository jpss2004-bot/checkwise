import type { MetadataRoute } from "next";

import { SITE_URL } from "@/lib/site";

/**
 * Public sitemap. Only routes that should be indexed live here — the
 * landing page, the REPSE content pages, the login entry and the three
 * legal documents. The authenticated app (portal/client/admin/
 * platform/reports) is omitted deliberately and also disallowed in
 * `app/robots.ts`.
 *
 * `lastModified` is a content-stable date, not the build time, so the
 * sitemap does not churn its timestamps on every deploy.
 */
const LAST_MODIFIED = "2026-06-12";

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    {
      url: SITE_URL,
      lastModified: LAST_MODIFIED,
      changeFrequency: "weekly",
      priority: 1,
    },
    {
      url: `${SITE_URL}/repse`,
      lastModified: LAST_MODIFIED,
      changeFrequency: "monthly",
      priority: 0.8,
    },
    {
      url: `${SITE_URL}/software-repse`,
      lastModified: LAST_MODIFIED,
      changeFrequency: "monthly",
      priority: 0.8,
    },
    {
      url: `${SITE_URL}/login`,
      lastModified: LAST_MODIFIED,
      changeFrequency: "monthly",
      priority: 0.4,
    },
    {
      url: `${SITE_URL}/legal/privacidad`,
      lastModified: LAST_MODIFIED,
      changeFrequency: "yearly",
      priority: 0.3,
    },
    {
      url: `${SITE_URL}/legal/terminos`,
      lastModified: LAST_MODIFIED,
      changeFrequency: "yearly",
      priority: 0.3,
    },
    {
      url: `${SITE_URL}/legal/consentimiento`,
      lastModified: LAST_MODIFIED,
      changeFrequency: "yearly",
      priority: 0.3,
    },
  ];
}
