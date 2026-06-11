import type { Metadata } from "next";
import Link from "next/link";
import { ArrowUpRight } from "@phosphor-icons/react/dist/ssr";

import { BrandLogo } from "@/components/checkwise/brand-logo";
import { FeedbackLauncher } from "@/components/feedback/feedback-launcher";
import { ContactForm } from "@/components/marketing/contact-form";
import { FeaturesSection } from "@/components/marketing/features-section";
import { HeroSection } from "@/components/marketing/hero-section";
import { JourneySection } from "@/components/marketing/journey-section";
import { HumanReviewSection } from "@/components/marketing/human-review-section";
import { MarketingNav } from "@/components/marketing/marketing-nav";
import { Reveal } from "@/components/marketing/motion-helpers";
import { MotionPreferenceProvider } from "@/components/marketing/motion-preference";
import { SITE_NAME, SITE_URL } from "@/lib/site";
import { APP_VERSION, BUILD_SHA } from "@/lib/version";

// The page itself is a server component (every imported section carries
// its own "use client" pragma) so crawlers get the canonical tag, the
// structured data and the full hero copy in the initial HTML.
export const metadata: Metadata = {
  alternates: { canonical: "/" },
};

/**
 * Organization + WebSite + SoftwareApplication graph for the landing
 * page. Only claims we can stand behind — no ratings, no pricing.
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
  ],
} as const;

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
        <FeaturesSection />
        <JourneySection />
        <HumanReviewSection />
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

// ─── Footer ──────────────────────────────────────────────────────

/**
 * Marketing footer. Three editorial columns: brand + signature on the
 * left, quick nav in the middle, version + region stamp on the right.
 * No nested cards. Mono captions provide the operational signature.
 */
function MarketingFooter() {
  return (
    <footer className="border-t border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)]">
      <div className="mx-auto grid max-w-[1320px] grid-cols-1 gap-10 px-5 py-12 md:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1fr)] md:gap-12">
        {/* Brand column */}
        <div>
          <BrandLogo size="sm" />
          <p className="mt-4 max-w-[32ch] text-[13px] leading-[1.55] text-[color:var(--text-secondary)]">
            Sistema operativo REPSE para proveedor, cliente y equipo CheckWise,
            sobre un mismo expediente auditable.
          </p>
          <p className="mt-4 font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-tertiary)]">
            Una solución de{" "}
            <span className="text-[color:var(--text-secondary)]">Legal Shelf</span>
          </p>
        </div>

        {/* Nav column — mirrors the top-nav anchors so labels stay
            consistent across the page. */}
        <FooterColumn
          label="Producto"
          links={[
            { label: "Sistema", href: "#sistema" },
            { label: "Evidencia", href: "#evidencia" },
            { label: "AI + revisión", href: "#ai-revision" },
            { label: "Iniciar sesión", href: "/login" },
            { label: "Solicitar demo", href: "#contacto" },
          ]}
        />

        {/* Signature column. Build metadata stays in the title
            attribute for support diagnostics but is no longer visible
            text on the public landing. */}
        <div
          className="flex flex-col gap-3 md:items-end md:text-right"
          title={`CheckWise v${APP_VERSION} · ${BUILD_SHA}`}
        >
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-tertiary)]">
            Equipo CheckWise
          </p>
          <p className="text-[13px] text-[color:var(--text-secondary)]">
            Hecho en Ciudad de México.
          </p>
          <p className="text-[12px] text-[color:var(--text-tertiary)]">
            © {new Date().getFullYear()} CheckWise. Todos los derechos reservados.
          </p>
        </div>
      </div>

      {/* Legal strip — required near data collection for a compliance
          product; links to the existing /legal pages. */}
      <div className="border-t border-[color:var(--border-subtle)]">
        <div className="mx-auto flex max-w-[1320px] flex-col gap-3 px-5 py-5 text-[12px] sm:flex-row sm:items-center sm:justify-between">
          <p className="text-[color:var(--text-tertiary)]">
            CheckWise es una plataforma de control documental REPSE. No emite
            resoluciones legales ni garantiza el cumplimiento automático.
          </p>
          <ul className="flex flex-wrap items-center gap-x-5 gap-y-2">
            <li>
              <Link
                href="/legal/privacidad"
                className="text-[color:var(--text-secondary)] transition-colors hover:text-[color:var(--text-primary)]"
              >
                Aviso de privacidad
              </Link>
            </li>
            <li>
              <Link
                href="/legal/terminos"
                className="text-[color:var(--text-secondary)] transition-colors hover:text-[color:var(--text-primary)]"
              >
                Términos
              </Link>
            </li>
          </ul>
        </div>
      </div>
    </footer>
  );
}

function FooterColumn({
  label,
  links,
}: {
  label: string;
  links: ReadonlyArray<{ label: string; href: string }>;
}) {
  return (
    <div>
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-secondary)]">
        {label}
      </p>
      <ul className="mt-4 space-y-2.5">
        {links.map((link) => {
          const external = link.href.startsWith("http");
          const internal = link.href.startsWith("#") || link.href.startsWith("/");
          const className =
            "group inline-flex items-center gap-1.5 text-[13px] text-[color:var(--text-secondary)] transition-colors hover:text-[color:var(--text-primary)]";
          if (internal && !link.href.startsWith("#")) {
            return (
              <li key={link.href}>
                <Link href={link.href} className={className}>
                  <span>{link.label}</span>
                  <ArrowUpRight
                    className="h-3 w-3 opacity-0 transition-opacity group-hover:opacity-100"
                    weight="bold"
                    aria-hidden="true"
                  />
                </Link>
              </li>
            );
          }
          return (
            <li key={link.href}>
              <a
                href={link.href}
                className={className}
                target={external ? "_blank" : undefined}
                rel={external ? "noreferrer noopener" : undefined}
              >
                <span>{link.label}</span>
                <ArrowUpRight
                  className="h-3 w-3 opacity-0 transition-opacity group-hover:opacity-100"
                  weight="bold"
                  aria-hidden="true"
                />
              </a>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
