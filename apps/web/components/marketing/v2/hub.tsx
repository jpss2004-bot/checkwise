import Link from "next/link";
import { ArrowRight, BookOpen, Stack } from "@phosphor-icons/react/dist/ssr";

import { Eyebrow, Lead, Section, SectionTitle } from "./_shared";

/**
 * Section 08 — Recursos REPSE. Two committed page destinations (per the
 * landing notes: the ICSOE / SISUB / responsabilidad-solidaria / renovación
 * cards all dead-ended at the same place, so they were removed; their topics
 * are folded into the Guía card body to keep the on-page keywords). Both
 * cards go to dedicated pages — "commit to one idea."
 */
const CARDS = [
  {
    icon: BookOpen,
    kw: "Guía REPSE",
    title: "¿Qué es el REPSE?",
    body: "Registro ante la STPS, obligaciones, ICSOE y SISUB, responsabilidad solidaria y sanciones — explicado claro, sin tecnicismos.",
    href: "/repse",
    cta: "Leer la Guía REPSE",
    featured: true,
  },
  {
    icon: Stack,
    kw: "El software",
    title: "Software de cumplimiento REPSE",
    body: "Qué debe resolver un software de cumplimiento y cómo CheckWise lo hace, de punta a punta.",
    href: "/software-repse",
    cta: "Conocer el software",
    featured: false,
  },
] as const;

export function V2Hub() {
  return (
    <Section id="recursos" band="soft">
      <Eyebrow>Recursos REPSE</Eyebrow>
      <SectionTitle accent="sin rodeos." className="mt-4">
        Entiende el REPSE
      </SectionTitle>
      <Lead className="mt-5">
        Dos lecturas para resolverlo: qué te obliga la ley y cómo el software
        lo mantiene en regla.
      </Lead>

      <div className="mt-12 grid gap-5 lg:grid-cols-2">
        {CARDS.map((c) => {
          const Icon = c.icon;
          return (
            <Link
              key={c.title}
              href={c.href}
              className={`group flex flex-col rounded-3xl border p-8 shadow-[var(--shadow-xs)] transition-[transform,box-shadow,border-color] duration-200 hover:-translate-y-1 hover:shadow-[var(--shadow-lg)] sm:p-10 ${
                c.featured
                  ? "border-[color:var(--border-ai)] bg-[color:var(--surface-teal-muted)]"
                  : "border-[color:var(--border-default)] bg-[color:var(--surface-raised)] hover:border-[color:var(--border-strong)]"
              }`}
            >
              <span className="inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-[color:var(--surface-raised)] text-[color:var(--text-teal)] shadow-[var(--shadow-xs)]">
                <Icon className="h-7 w-7" weight="duotone" aria-hidden="true" />
              </span>
              <p className="mt-6 font-mono text-[12px] uppercase tracking-[0.14em] text-[color:var(--text-teal)]">
                {c.kw}
              </p>
              <h3 className="font-display mt-2 text-[clamp(1.5rem,2.2vw,2rem)] font-bold tracking-[-0.01em] text-[color:var(--text-primary)]">
                {c.title}
              </h3>
              <p className="mt-3 max-w-[46ch] text-[16px] leading-[1.6] text-[color:var(--text-secondary)]">
                {c.body}
              </p>
              <span className="mt-7 inline-flex items-center gap-1.5 text-[15px] font-semibold text-[color:var(--text-brand)]">
                {c.cta}
                <ArrowRight
                  className="h-4 w-4 transition-transform group-hover:translate-x-1"
                  weight="bold"
                  aria-hidden="true"
                />
              </span>
            </Link>
          );
        })}
      </div>
    </Section>
  );
}
