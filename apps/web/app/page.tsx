import type { Metadata } from "next";

import { FeedbackLauncher } from "@/components/feedback/feedback-launcher";
import { MotionPreferenceProvider } from "@/components/marketing/motion-preference";
import { V2AiHuman } from "@/components/marketing/v2/ai-human";
import { MarketingAtmosphere } from "@/components/marketing/v2/atmosphere";
import { V2CloseDemo } from "@/components/marketing/v2/close-demo";
import { V2Faq } from "@/components/marketing/v2/faq";
import { V2Footer } from "@/components/marketing/v2/footer";
import { V2Hero } from "@/components/marketing/v2/hero";
import { V2HowItWorks } from "@/components/marketing/v2/how-it-works";
import { V2MidCta } from "@/components/marketing/v2/mid-cta";
import { SmoothScroll } from "@/components/marketing/v2/motion";
import { V2Nav } from "@/components/marketing/v2/nav";
import { V2Roles } from "@/components/marketing/v2/roles";
import { V2Shift } from "@/components/marketing/v2/shift";
import { V2Stakes } from "@/components/marketing/v2/stakes";
import { FAQ_ITEMS } from "@/lib/marketing/faq";
import { SITE_NAME, SITE_URL } from "@/lib/site";

// Server component: every section carries its own "use client" pragma, so
// crawlers still get the canonical tag, the structured data and the full
// hero copy in the initial HTML. This is the redesigned landing (formerly
// /v2), promoted to be the live homepage.
export const metadata: Metadata = {
  alternates: { canonical: "/" },
};

/**
 * Organization + WebSite + SoftwareApplication + FAQPage graph for the
 * landing page. Only claims we can stand behind — no ratings, no pricing.
 * The FAQPage mainEntity serializes the same FAQ_ITEMS the visible accordion
 * (V2Faq) renders, so markup and on-page copy cannot drift.
 */
const STRUCTURED_DATA = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      "@id": `${SITE_URL}/#organization`,
      name: SITE_NAME,
      url: SITE_URL,
      logo: `${SITE_URL}/og.png`,
      parentOrganization: { "@type": "Organization", name: "Legal Shelf" },
      address: {
        "@type": "PostalAddress",
        addressLocality: "Ciudad de México",
        addressCountry: "MX",
      },
    },
    {
      "@type": "WebSite",
      "@id": `${SITE_URL}/#website`,
      name: SITE_NAME,
      url: SITE_URL,
      inLanguage: "es-MX",
      publisher: { "@id": `${SITE_URL}/#organization` },
    },
    {
      "@type": "SoftwareApplication",
      name: SITE_NAME,
      url: SITE_URL,
      applicationCategory: "BusinessApplication",
      operatingSystem: "Web",
      inLanguage: "es-MX",
      description:
        "Plataforma de cumplimiento REPSE: calendario de obligaciones, expediente auditable, revisión humana y reportes asistidos por IA para proveedores y clientes.",
      publisher: { "@id": `${SITE_URL}/#organization` },
    },
    {
      "@type": "FAQPage",
      "@id": `${SITE_URL}/#faq`,
      inLanguage: "es-MX",
      mainEntity: FAQ_ITEMS.map((item) => ({
        "@type": "Question",
        name: item.question,
        acceptedAnswer: { "@type": "Answer", text: item.answer },
      })),
    },
  ],
};

export default function PublicHome() {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(STRUCTURED_DATA) }}
      />
      <MotionPreferenceProvider>
        <SmoothScroll>
          <MarketingAtmosphere />
          <div className="relative z-10">
            <V2Nav />
            <main>
              <V2Hero />
              <V2Stakes />
              <V2Shift />
              <V2HowItWorks />
              <V2Roles />
              <V2MidCta />
              <V2AiHuman />
              <V2Faq />
              <V2CloseDemo />
            </main>
            <V2Footer />
            <FeedbackLauncher allowPublic />
          </div>
        </SmoothScroll>
      </MotionPreferenceProvider>
    </>
  );
}
