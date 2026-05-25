"use client";

import Link from "next/link";
import { ArrowUpRight } from "@phosphor-icons/react";

import { BrandLogo } from "@/components/checkwise/brand-logo";
import { FeedbackLauncher } from "@/components/feedback/feedback-launcher";
import { ContactForm } from "@/components/marketing/contact-form";
import { FeaturesSection } from "@/components/marketing/features-section";
import { HeroSection } from "@/components/marketing/hero-section";
import { JourneySection } from "@/components/marketing/journey-section";
import { LegalShelfSection } from "@/components/marketing/legal-shelf-section";
import { MarketingNav } from "@/components/marketing/marketing-nav";
import { Reveal } from "@/components/marketing/motion-helpers";
import { MotionPreferenceProvider } from "@/components/marketing/motion-preference";
import { APP_VERSION, BUILD_SHA } from "@/lib/version";

export default function PublicHome() {
  return (
    <MotionPreferenceProvider>
      <main className="min-h-[100dvh] bg-[color:var(--surface-page)]">
        <MarketingNav />
        <HeroSection />
        <FeaturesSection />
        <JourneySection />
        <LegalShelfSection />
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
 * numbered statements (same composition pattern as the Legal Shelf
 * section) so the whole landing reads with one editorial voice.
 */
function RequestInformation() {
  return (
    <section
      id="contacto"
      className="relative isolate border-t border-[color:var(--border-subtle)] bg-[color:var(--surface-page)]"
    >
      <div className="mx-auto grid max-w-[1320px] grid-cols-1 gap-12 px-5 py-20 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-16 lg:py-28">
        <Reveal className="flex min-w-0 flex-col">
          <p className="cw-eyebrow text-[color:var(--text-teal)]">
            Solicitar información
          </p>
          <h2
            className="mt-3 font-semibold tracking-[-0.022em] text-[color:var(--text-primary)] [text-wrap:balance]"
            style={{ fontSize: "clamp(1.9rem, 2.9vw, 2.55rem)", lineHeight: 1.04 }}
          >
            ¿Listo para entrar al sistema?{" "}
            <span className="text-[color:var(--text-teal)]">
              Te abrimos una demo guiada.
            </span>
          </h2>
          <p className="mt-4 max-w-[44ch] text-[15px] leading-[1.6] text-[color:var(--text-secondary)]">
            Veinte minutos sobre el sistema real con tus datos de ejemplo.
            Sin presentación, sin video pregrabado.
          </p>

          <ol className="mt-9 space-y-5 border-l border-[color:var(--border-default)] pl-5">
            <DemoStep
              n="01"
              kicker="Recorrido"
              body="Portal proveedor, vista cliente y bandeja Legal Shelf sobre un mismo expediente real."
            />
            <DemoStep
              n="02"
              kicker="Reportes"
              body="Editor con copilot LLM, generación, exportación PDF, Excel y HTML en vivo."
            />
            <DemoStep
              n="03"
              kicker="Auditoría"
              body="Audit log firmado, paquete ZIP con índice y metadata exportable a tu auditor."
            />
          </ol>

          <p className="mt-9 font-mono text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-tertiary)]">
            <span className="cw-pulse-soft mr-2 inline-block h-1.5 w-1.5 rounded-full bg-[color:var(--text-teal)] align-middle" />
            Respondemos el mismo día hábil · CDMX
          </p>
        </Reveal>

        <Reveal>
          <div className="relative">
            {/* Chrome bar above the form — matches the live-system
                signature used on every other section. */}
            <div className="flex items-center gap-2 border-x border-t border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-3 py-2 rounded-t-[10px]">
              <span className="flex gap-1.5" aria-hidden="true">
                <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--border-strong)]/70" />
                <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--border-strong)]/45" />
                <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--border-strong)]/30" />
              </span>
              <span className="ml-1 truncate font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-tertiary)]">
                POST · /api/v1/contact
              </span>
              <span className="ml-auto inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-teal)]">
                <span className="cw-pulse-soft inline-block h-1.5 w-1.5 rounded-full bg-[color:var(--text-teal)]" />
                En línea
              </span>
            </div>
            <div className="rounded-b-[10px] border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-6 shadow-[0_22px_50px_-32px_hsl(var(--brand-navy)/0.22)] sm:p-8">
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
          <BrandLogo size="sm" poweredBy />
          <p className="mt-4 max-w-[32ch] text-[13px] leading-[1.55] text-[color:var(--text-secondary)]">
            Sistema operativo REPSE para proveedor, cliente y Legal Shelf,
            sobre un mismo expediente auditable.
          </p>
        </div>

        {/* Nav column */}
        <FooterColumn
          label="Producto"
          links={[
            { label: "Recorrido", href: "#features" },
            { label: "Cuatro actos", href: "#producto" },
            { label: "Iniciar sesión", href: "/login" },
            { label: "Solicitar demo", href: "#contacto" },
          ]}
        />

        {/* Signature column */}
        <div className="flex flex-col gap-3 md:items-end md:text-right">
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-tertiary)]">
            Powered by Legal Shelf
          </p>
          <p className="text-[13px] text-[color:var(--text-secondary)]">
            Hecho en Ciudad de México.
          </p>
          <span
            className="font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-tertiary)]"
            title={`Build ${BUILD_SHA}`}
          >
            v{APP_VERSION} · {BUILD_SHA}
          </span>
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
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-tertiary)]">
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
