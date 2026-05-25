"use client";

import Link from "next/link";
import { CheckCircle } from "@phosphor-icons/react";

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

function RequestInformation() {
  const bullets = [
    "Demo guiada del portal proveedor y la vista cliente",
    "Recorrido por reportes, copilot LLM y descargas de auditoría",
    "Mapa de implementación para tu operación REPSE",
  ];
  return (
    <section id="contacto" className="bg-[color:var(--surface-page)]">
      <div className="mx-auto grid max-w-[1320px] grid-cols-1 gap-12 px-5 py-20 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] lg:gap-16 lg:py-28">
        <Reveal className="space-y-4">
          <p className="cw-eyebrow text-[color:var(--text-teal)]">
            Solicita información
          </p>
          <h2
            className="font-semibold tracking-[-0.02em] text-[color:var(--text-primary)]"
            style={{ fontSize: "clamp(1.75rem, 2.8vw, 2.5rem)", lineHeight: 1.1 }}
          >
            ¿Listo para ver CheckWise en acción?
          </h2>
          <p className="max-w-[55ch] text-[15px] leading-[1.65] text-[color:var(--text-secondary)]">
            Cuéntanos qué necesitas y te agendamos una demo personalizada.
            Solemos responder el mismo día hábil.
          </p>
          <ul className="space-y-3 pt-3">
            {bullets.map((item) => (
              <li key={item} className="flex items-start gap-2 text-[14px]">
                <CheckCircle
                  className="mt-0.5 h-4 w-4 shrink-0 text-[color:var(--text-teal)]"
                  weight="fill"
                  aria-hidden="true"
                />
                <span className="text-[color:var(--text-primary)]">{item}</span>
              </li>
            ))}
          </ul>
        </Reveal>
        <Reveal>
          <div className="rounded-[1.25rem] border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-6 shadow-[0_22px_50px_-32px_hsl(var(--brand-navy)/0.22)] sm:p-8">
            <ContactForm />
          </div>
        </Reveal>
      </div>
    </section>
  );
}

// ─── Footer ──────────────────────────────────────────────────────

function MarketingFooter() {
  return (
    <footer className="border-t border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)]">
      <div className="mx-auto flex max-w-[1320px] flex-col gap-4 px-5 py-8 sm:flex-row sm:items-center sm:justify-between">
        <BrandLogo size="sm" poweredBy />
        <div className="flex flex-wrap items-center gap-4 text-xs text-[color:var(--text-tertiary)]">
          <Link href="/login" className="hover:text-[color:var(--text-primary)]">
            Iniciar sesión
          </Link>
          <a href="#contacto" className="hover:text-[color:var(--text-primary)]">
            Contacto
          </a>
          <span
            className="font-mono text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-tertiary)]"
            title={`Build ${BUILD_SHA}`}
          >
            v{APP_VERSION} · {BUILD_SHA}
          </span>
        </div>
      </div>
    </footer>
  );
}
