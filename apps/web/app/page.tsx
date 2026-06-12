import type { Metadata } from "next";
import { ArrowUpRight } from "@phosphor-icons/react/dist/ssr";

import { FeedbackLauncher } from "@/components/feedback/feedback-launcher";
import { ContactForm } from "@/components/marketing/contact-form";
import { FaqSection } from "@/components/marketing/faq-section";
import { FeaturesSection } from "@/components/marketing/features-section";
import { HeroSection } from "@/components/marketing/hero-section";
import { JourneySection } from "@/components/marketing/journey-section";
import { HumanReviewSection } from "@/components/marketing/human-review-section";
import { MarketingFooter } from "@/components/marketing/marketing-footer";
import { MarketingNav } from "@/components/marketing/marketing-nav";
import { PreventionSection } from "@/components/marketing/prevention-section";
import { Reveal } from "@/components/marketing/motion-helpers";
import { MotionPreferenceProvider } from "@/components/marketing/motion-preference";
import { TrustSection } from "@/components/marketing/trust-section";
import { DEMO_BOOKING_URL } from "@/lib/marketing/booking";
import { FAQ_ITEMS } from "@/lib/marketing/faq";
import { SITE_NAME, SITE_URL } from "@/lib/site";

// The page itself is a server component (every imported section carries
// its own "use client" pragma) so crawlers get the canonical tag, the
// structured data and the full hero copy in the initial HTML.
export const metadata: Metadata = {
  alternates: { canonical: "/" },
};

/**
 * Organization + WebSite + SoftwareApplication + FAQPage graph for the
 * landing page. Only claims we can stand behind — no ratings, no
 * pricing. The FAQPage mainEntity serializes the same FAQ_ITEMS the
 * visible accordion renders, so markup and on-page copy cannot drift.
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
    <MotionPreferenceProvider>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(STRUCTURED_DATA) }}
      />
      <main className="min-h-[100dvh] bg-[color:var(--surface-page)]">
        <MarketingNav />
        <HeroSection />
        <TrustSection />
        <FeaturesSection />
        <JourneySection />
        <PreventionSection />
        <HumanReviewSection />
        <FaqSection />
        <RequestInformation />
        <MarketingFooter />
        <FeedbackLauncher allowPublic />
      </main>
    </MotionPreferenceProvider>
  );
}

// ─── Request information ─────────────────────────────────────────

/**
 * Contact slice. The form is not wrapped in a nested card — it sits
 * directly on the surface-page background, with a chrome bar above it
 * that mirrors the live-system signature used by every other section
 * on this page. The narrative column on the left carries three
 * numbered statements (same composition pattern as the human review
 * section) so the whole landing reads with one editorial voice.
 */
function RequestInformation() {
  return (
    <section
      id="contacto"
      className="relative isolate border-t border-[color:var(--border-subtle)] bg-[color:var(--surface-page)]"
    >
      <div className="mx-auto grid max-w-[1320px] grid-cols-1 gap-12 px-5 py-24 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-20 lg:py-28">
        <Reveal className="flex min-w-0 flex-col">
          <p className="cw-eyebrow text-[color:var(--text-teal)]">
            Solicitar demo
          </p>
          <h2
            className="mt-3 font-semibold tracking-[-0.022em] text-[color:var(--text-primary)] [text-wrap:balance]"
            style={{ fontSize: "clamp(1.9rem, 2.9vw, 2.55rem)", lineHeight: 1.04 }}
          >
            ¿Listo para ver tu operación en CheckWise?{" "}
            <span className="text-[color:var(--text-teal)]">
              Te abrimos una demo guiada sobre el producto real.
            </span>
          </h2>
          <p className="mt-4 max-w-[44ch] text-[15px] leading-[1.6] text-[color:var(--text-secondary)]">
            Recorremos calendario, expediente, revisión CheckWise y reportes
            AI con datos de ejemplo. Sin video pregrabado.
          </p>

          <ol className="mt-9 space-y-5 border-l border-[color:var(--border-default)] pl-5">
            <DemoStep
              n="01"
              kicker="Sistema"
              body="Vista proveedor, vista cliente y consola CheckWise sobre el mismo expediente."
            />
            <DemoStep
              n="02"
              kicker="Evidencia"
              body="Slots por requisito, periodo e institución, con estado, reemplazos y decisión firmada."
            />
            <DemoStep
              n="03"
              kicker="AI + auditoría"
              body="Reportes asistidos, exportación ejecutiva y registro listo para auditoría."
            />
          </ol>

          <p className="mt-9 font-mono text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-tertiary)]">
            <span className="cw-pulse-soft mr-2 inline-block h-1.5 w-1.5 rounded-full bg-[color:var(--text-teal)] align-middle" />
            Respondemos el mismo día hábil · CDMX
          </p>
        </Reveal>

        <Reveal>
          <div className="relative">
            {/* Chrome bar above the form — public-friendly framing.
                Names what this is (a demo request) instead of leaking
                the underlying API endpoint. */}
            <div className="flex items-center gap-2 rounded-t-[10px] border-x border-t border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-4 py-2.5">
              <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-tertiary)]">
                Solicitud de demo
              </span>
              <span className="ml-auto inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-teal)]">
                <span className="cw-pulse-soft inline-block h-1.5 w-1.5 rounded-full bg-[color:var(--text-teal)]" />
                Respuesta el mismo día hábil
              </span>
            </div>
            <div className="rounded-b-[10px] border border-[color:var(--border-default)] border-t-0 bg-[color:var(--surface-raised)] px-6 py-8 shadow-[0_22px_50px_-32px_hsl(var(--brand-navy)/0.22)] sm:px-10 sm:py-10">
              <ContactForm />
            </div>

            {/* Direct-booking alternative — the conversion path the old
                site relied on. One quiet line, not a competing card:
                the form stays primary, the calendar removes friction
                for visitors who already decided. */}
            <p className="mt-5 text-center text-[13px] text-[color:var(--text-secondary)]">
              ¿Prefieres elegir horario directamente?{" "}
              <a
                href={DEMO_BOOKING_URL}
                target="_blank"
                rel="noreferrer noopener"
                className="group inline-flex items-center gap-1 font-medium text-[color:var(--text-teal)] underline-offset-2 hover:underline"
              >
                Agenda 30 minutos con el equipo
                <ArrowUpRight
                  className="h-3 w-3 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5"
                  weight="bold"
                  aria-hidden="true"
                />
              </a>
            </p>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function DemoStep({
  n,
  kicker,
  body,
}: {
  n: string;
  kicker: string;
  body: string;
}) {
  return (
    <li className="relative">
      <span
        aria-hidden="true"
        className="absolute -left-[1.65rem] top-1 font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-teal)]"
      >
        {n}
      </span>
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-tertiary)]">
        {kicker}
      </p>
      <p className="mt-1.5 max-w-[44ch] text-[14.5px] leading-[1.55] text-[color:var(--text-primary)]">
        {body}
      </p>
    </li>
  );
}
