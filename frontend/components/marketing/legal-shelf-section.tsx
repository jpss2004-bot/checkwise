"use client";

import Image from "next/image";
import Link from "next/link";
import {
  CheckCircle,
  Gavel,
  PaperPlaneTilt,
  ShieldCheck,
  Stamp,
} from "@phosphor-icons/react";
import { motion } from "motion/react";

import { Button } from "@/components/ui/button";

import { EASE_ENTER, Reveal } from "./motion-helpers";
import { useMotionPreference } from "./motion-preference";

// Stage 2.5 (BL-T3, 2026-05-20) — TRUST_POINTS is now a function so
// the "Estándar REPSE <year>" label reads the current year at render
// time instead of carrying a stale "2026" literal.
const TRUST_POINTS = [
  { icon: Gavel, label: "Revisión legal humana" },
  {
    icon: ShieldCheck,
    label: `Estándar REPSE ${new Date().getFullYear()}`,
  },
  { icon: Stamp, label: "Auditable extremo a extremo" },
  { icon: CheckCircle, label: "Excepciones legales registradas" },
] as const;

/**
 * Dark navy block anchoring the legal-tech credibility of CheckWise.
 *
 * Composition: editorial copy + CTA on the left, anchored screenshot
 * of the admin reviewer queue on the right. The screenshot grounds the
 * "revisión humana" promise with a real product surface rather than
 * abstract icons. Trust points live below as border-divided rows.
 */
export function LegalShelfSection() {
  const { reduced: reduce } = useMotionPreference();
  return (
    <section className="relative isolate overflow-hidden bg-[color:var(--surface-brand)] text-[color:var(--text-inverse)]">
      {/* Subtle teal halo top-right */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -right-32 -top-32 hidden h-[520px] w-[520px] rounded-full bg-[hsl(var(--brand-teal)/0.10)] blur-3xl lg:block"
      />

      <div className="mx-auto grid max-w-[1320px] grid-cols-1 gap-12 px-5 py-20 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)] lg:gap-16 lg:py-28">
        {/* Left — narrative */}
        <Reveal className="flex min-w-0 flex-col">
          <p className="cw-eyebrow text-[hsl(var(--brand-teal))]">
            Powered by Legal Shelf
          </p>
          <h2
            className="mt-3 font-semibold tracking-[-0.02em]"
            style={{ fontSize: "clamp(1.85rem, 2.8vw, 2.5rem)", lineHeight: 1.1 }}
          >
            La capa humana detrás de cada documento crítico.
          </h2>
          <p className="mt-4 max-w-[55ch] text-[15px] leading-[1.65] text-[color:var(--text-inverse)]/80">
            Cuando un documento necesita criterio legal, la revisión queda en
            manos del equipo de Legal Shelf. CheckWise nunca firma documentos
            ni reemplaza al abogado, simplemente asegura que cada paso quede
            trazable y listo para auditoría.
          </p>

          <div className="mt-7 flex flex-wrap gap-3">
            <Button asChild size="lg" variant="secondary" className="rounded-full">
              <Link href="#contacto">
                <PaperPlaneTilt className="h-4 w-4" weight="bold" aria-hidden="true" />
                <span>Hablar con un asesor</span>
              </Link>
            </Button>
          </div>

          <ul className="mt-10 divide-y divide-white/10 border-y border-white/10">
            {TRUST_POINTS.map(({ icon: Icon, label }) => (
              <li key={label} className="flex items-center gap-3 py-3.5">
                <Icon
                  className="h-4 w-4 text-[hsl(var(--brand-teal))]"
                  weight="duotone"
                  aria-hidden="true"
                />
                <span className="text-[13.5px] font-medium leading-tight">
                  {label}
                </span>
              </li>
            ))}
          </ul>
        </Reveal>

        {/* Right — anchored screenshot */}
        <motion.div
          className="relative min-w-0 self-start"
          initial={reduce ? false : { opacity: 0, y: 20 }}
          whileInView={reduce ? { opacity: 1 } : { opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.2 }}
          transition={{ duration: 0.7, ease: EASE_ENTER, delay: 0.05 }}
        >
          <div className="relative overflow-hidden rounded-[1.25rem] border border-white/10 bg-[color:var(--surface-raised)] shadow-[0_36px_80px_-32px_rgba(0,0,0,0.6)]">
            <div className="flex items-center gap-2 border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-page)]/80 px-3 py-2">
              <span className="flex gap-1.5" aria-hidden="true">
                <span className="h-2 w-2 rounded-full bg-[color:var(--border-strong)]/80" />
                <span className="h-2 w-2 rounded-full bg-[color:var(--border-strong)]/60" />
                <span className="h-2 w-2 rounded-full bg-[color:var(--border-strong)]/40" />
              </span>
              <span className="ml-2 truncate font-mono text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-tertiary)]">
                Bandeja por revisar · Legal Shelf
              </span>
            </div>
            <Image
              src="/marketing/hero/admin-reviewer-queue.png"
              alt="Bandeja de revisión humana de CheckWise mostrando documentos por validar y su origen."
              width={1440}
              height={900}
              className="block h-auto w-full"
              sizes="(min-width: 1024px) 48vw, 92vw"
              loading="lazy"
            />
          </div>
          {/* Floating decision pill */}
          <motion.div
            initial={reduce ? false : { opacity: 0, y: -8 }}
            whileInView={reduce ? { opacity: 1 } : { opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.3 }}
            transition={{ duration: 0.55, ease: EASE_ENTER, delay: 0.4 }}
            className="absolute -left-4 top-6 hidden items-center gap-2 rounded-full border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-3 py-1.5 shadow-[0_18px_40px_-18px_rgba(0,0,0,0.5)] lg:inline-flex"
          >
            <Gavel
              className="h-3.5 w-3.5 text-[color:var(--text-teal)]"
              weight="fill"
              aria-hidden="true"
            />
            <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-secondary)]">
              Decisión humana
            </span>
            <span className="font-mono text-[11px] font-semibold text-[color:var(--text-primary)]">
              Ada Reyes
            </span>
          </motion.div>
        </motion.div>
      </div>
    </section>
  );
}
