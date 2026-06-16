import Link from "next/link";
import {
  ArrowRight,
  ArrowsClockwise,
  BookOpen,
  ClipboardText,
  Scales,
  Stack,
} from "@phosphor-icons/react/dist/ssr";

import { Eyebrow, Section, SectionTitle } from "./_shared";

/**
 * Section 08 — Hub REPSE · Recursos. Asymmetric bento of keyword-rich
 * internal links to the content cluster (SEO engine on the landing).
 */
const CARDS = [
  { icon: BookOpen, kw: "Guía", title: "¿Qué es el REPSE?", body: "Registro ante la STPS, obligaciones y sanciones, explicado claro.", href: "/repse", span: "lg:col-span-3", featured: true },
  { icon: Stack, kw: "Software", title: "Software de cumplimiento REPSE", body: "Qué debe resolver y cómo lo hace CheckWise.", href: "/software-repse", span: "lg:col-span-3", featured: false },
  { icon: ClipboardText, kw: "Obligación", title: "ICSOE", body: "Qué es y cómo presentarlo ante el IMSS.", href: "/repse", span: "lg:col-span-2", featured: false },
  { icon: ClipboardText, kw: "Obligación", title: "SISUB", body: "Cómo cumplir con IMSS e Infonavit.", href: "/repse", span: "lg:col-span-2", featured: false },
  { icon: Scales, kw: "Riesgo", title: "Responsabilidad solidaria", body: "Cómo protegerte como empresa contratante.", href: "/repse", span: "lg:col-span-2", featured: false },
  { icon: ArrowsClockwise, kw: "Vigencia", title: "Renovación del REPSE", body: "Plazos, requisitos y consecuencias de no renovar a tiempo.", href: "/repse", span: "lg:col-span-6", featured: false },
] as const;

export function V2Hub() {
  return (
    <Section id="recursos" band="soft">
      <Eyebrow>Recursos REPSE</Eyebrow>
      <SectionTitle accent="ICSOE y SISUB." className="mt-4">
        Aprende REPSE: registro, obligaciones,
      </SectionTitle>

      <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-6">
        {CARDS.map((c) => {
          const Icon = c.icon;
          return (
            <Link
              key={c.title}
              href={c.href}
              className={`group flex flex-col rounded-3xl border p-7 shadow-[var(--shadow-xs)] transition-[transform,box-shadow,border-color] duration-200 hover:-translate-y-1 hover:shadow-[var(--shadow-md)] ${c.span} ${
                c.featured
                  ? "border-[color:var(--border-ai)] bg-[color:var(--surface-teal-muted)]"
                  : "border-[color:var(--border-default)] bg-[color:var(--surface-raised)] hover:border-[color:var(--border-strong)]"
              }`}
            >
              <span className="inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-[color:var(--surface-raised)] text-[color:var(--text-teal)] shadow-[var(--shadow-xs)]">
                <Icon className="h-6 w-6" weight="duotone" aria-hidden="true" />
              </span>
              <p className="mt-5 font-mono text-[11px] uppercase tracking-[0.14em] text-[color:var(--text-teal)]">
                {c.kw}
              </p>
              <h3 className="font-display mt-1.5 text-[19px] font-bold tracking-[-0.01em] text-[color:var(--text-primary)]">
                {c.title}
              </h3>
              <p className="mt-1.5 max-w-[42ch] text-[13.5px] leading-[1.55] text-[color:var(--text-secondary)]">
                {c.body}
              </p>
              <span className="mt-4 inline-flex items-center gap-1.5 text-[13px] font-semibold text-[color:var(--text-brand)]">
                Leer
                <ArrowRight
                  className="h-3.5 w-3.5 transition-transform group-hover:translate-x-1"
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
