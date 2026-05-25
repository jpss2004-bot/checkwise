"use client";

import Image from "next/image";
import Link from "next/link";
import { Gavel, PaperPlaneTilt, Stamp } from "@phosphor-icons/react";
import { motion } from "motion/react";

import { Button } from "@/components/ui/button";

import { EASE_ENTER, Reveal } from "./motion-helpers";
import { useMotionPreference } from "./motion-preference";

/**
 * Legal Shelf · the human decision layer.
 *
 * Composition: tight typographic statement on the left, audit log
 * screenshot anchored on the right with two floating overlay chips that
 * sit ON the screenshot, not next to it. The chips name the actor and the
 * decision so the proof reads at a glance: "the human signed this."
 */
export function LegalShelfSection() {
  const { reduced: reduce } = useMotionPreference();

  return (
    <section
      id="legal-shelf"
      className="relative isolate overflow-hidden bg-[color:var(--surface-brand)] text-[color:var(--text-inverse)]"
    >
      {/* Background — quiet horizontal lines, no decorative orbs. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 opacity-[0.07]"
        style={{
          backgroundImage:
            "repeating-linear-gradient(0deg, rgba(255,255,255,0.6) 0 1px, transparent 1px 64px)",
        }}
      />

      <div className="relative mx-auto grid max-w-[1320px] grid-cols-1 gap-12 px-5 py-24 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)] lg:gap-16 lg:py-28">
        {/* Statement column. */}
        <Reveal className="flex min-w-0 flex-col">
          <p className="cw-eyebrow text-[hsl(var(--brand-teal))]">
            Legal Shelf · capa humana
          </p>
          <h2
            className="mt-3 font-semibold tracking-[-0.022em] [text-wrap:balance]"
            style={{ fontSize: "clamp(1.9rem, 2.9vw, 2.55rem)", lineHeight: 1.06 }}
          >
            La decisión legal sigue siendo humana.{" "}
            <span className="text-[hsl(var(--brand-teal))]">
              CheckWise guarda la prueba.
            </span>
          </h2>
          <p className="mt-4 max-w-[46ch] text-[15px] leading-[1.6] text-[color:var(--text-inverse)]/82">
            Cada documento crítico pasa por revisión de Legal Shelf.
            CheckWise nunca firma: registra actor, acción, entidad y cambio
            en un registro de auditoría firmado.
          </p>

          {/* Numbered statements — replaces the bullet list. */}
          <ol className="mt-9 space-y-5 border-l border-white/15 pl-5">
            <Statement
              n="01"
              kicker="Revisión"
              body="Ada Reyes y el equipo Legal Shelf deciden documento por documento, no por reglas ciegas."
            />
            <Statement
              n="02"
              kicker="Firma"
              body="Cada decisión firma el registro de auditoría inmediatamente, con actor, acción y cambio registrado."
            />
            <Statement
              n="03"
              kicker="Excepciones"
              body="Las excepciones legales quedan registradas con motivo y autor — listas para defensa ante auditor."
            />
          </ol>

          <div className="mt-9 flex flex-wrap gap-3">
            <Button asChild size="lg" variant="secondary" className="rounded-full">
              <Link href="#contacto">
                <PaperPlaneTilt className="h-4 w-4" weight="bold" aria-hidden="true" />
                <span>Hablar con Legal Shelf</span>
              </Link>
            </Button>
          </div>
        </Reveal>

        {/* Composed proof stage — audit log + overlays. */}
        <motion.div
          className="relative min-w-0 self-start"
          initial={reduce ? false : { opacity: 0, y: 22 }}
          whileInView={reduce ? { opacity: 1 } : { opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.2 }}
          transition={{ duration: 0.75, ease: EASE_ENTER, delay: 0.05 }}
        >
          <div className="relative overflow-hidden rounded-[14px] border border-white/10 bg-[color:var(--surface-raised)] shadow-[0_44px_120px_-44px_rgba(0,0,0,0.65),0_18px_36px_-22px_rgba(0,0,0,0.4)]">
            <div className="flex items-center gap-2 border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-page)]/85 px-3 py-2">
              <span className="flex gap-1.5" aria-hidden="true">
                <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--border-strong)]/70" />
                <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--border-strong)]/45" />
                <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--border-strong)]/30" />
              </span>
              <span className="ml-1 truncate font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-tertiary)]">
                Registro de auditoría · actor · acción · cambio
              </span>
              <span className="ml-auto inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-teal)]">
                <span className="cw-pulse-soft inline-block h-1.5 w-1.5 rounded-full bg-[color:var(--text-teal)]" />
                Firmado
              </span>
            </div>
            <div className="relative aspect-[16/9.6] w-full overflow-hidden">
              <Image
                src="/marketing/product/admin-audit-log.png"
                alt="Audit log de CheckWise con eventos firmados de actor, acción y entidad afectada."
                fill
                sizes="(min-width: 1024px) 56vw, 92vw"
                className="object-cover object-top"
                loading="lazy"
              />
            </div>
          </div>

          {/* Overlay chip — "decisión humana". Sits ON the screenshot
              corner so the proof reads as part of the system, not next to
              it. */}
          <motion.div
            initial={reduce ? false : { opacity: 0, y: -8 }}
            whileInView={reduce ? { opacity: 1 } : { opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.3 }}
            transition={{ duration: 0.55, ease: EASE_ENTER, delay: 0.35 }}
            className="absolute -left-3 top-9 hidden items-center gap-2 rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-3 py-2 shadow-[0_18px_40px_-18px_rgba(0,0,0,0.5)] lg:inline-flex"
          >
            <Gavel
              className="h-3.5 w-3.5 text-[color:var(--text-teal)]"
              weight="fill"
              aria-hidden="true"
            />
            <div className="text-[color:var(--text-primary)]">
              <p className="font-mono text-[9px] uppercase tracking-[0.18em] text-[color:var(--text-tertiary)]">
                Decisión humana
              </p>
              <p className="text-[12.5px] font-semibold leading-snug">
                Ada Reyes · Legal Shelf
              </p>
            </div>
          </motion.div>

          {/* Overlay chip — "firmado". Bottom-right corner. */}
          <motion.div
            initial={reduce ? false : { opacity: 0, y: 8 }}
            whileInView={reduce ? { opacity: 1 } : { opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.3 }}
            transition={{ duration: 0.55, ease: EASE_ENTER, delay: 0.5 }}
            className="absolute -right-3 bottom-12 hidden items-center gap-2 rounded-md border border-white/15 bg-[color:var(--surface-brand)] px-3 py-2 text-[color:var(--text-inverse)] shadow-[0_18px_40px_-18px_rgba(0,0,0,0.5)] lg:inline-flex"
          >
            <Stamp
              className="h-3.5 w-3.5 text-[hsl(var(--brand-teal))]"
              weight="fill"
              aria-hidden="true"
            />
            <div>
              <p className="font-mono text-[9px] uppercase tracking-[0.18em] text-white/55">
                Evento registrado
              </p>
              <p className="text-[12.5px] font-semibold leading-snug">
                Consentimiento legal aceptado
              </p>
            </div>
          </motion.div>
        </motion.div>
      </div>
    </section>
  );
}

function Statement({
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
        className="absolute -left-[1.65rem] top-1 font-mono text-[10px] uppercase tracking-[0.18em] text-[hsl(var(--brand-teal))]"
      >
        {n}
      </span>
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-inverse)]/55">
        {kicker}
      </p>
      <p className="mt-1.5 max-w-[44ch] text-[14.5px] leading-[1.55] text-[color:var(--text-inverse)]/92">
        {body}
      </p>
    </li>
  );
}
