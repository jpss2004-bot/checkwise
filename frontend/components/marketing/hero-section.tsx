"use client";

import Link from "next/link";
import { motion } from "motion/react";
import {
  ArrowRight,
  Files,
  Gavel,
  Lock,
  ShieldCheck,
  Sparkle,
} from "@phosphor-icons/react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

import { HeroStage } from "./hero-stage";
import { useMotionPreference } from "./motion-preference";

const EASE_ENTER = [0.16, 1, 0.3, 1] as const;

/**
 * Public landing hero.
 *
 * Editorial split: a precise typographic column on the left, an
 * animated screenshot stage on the right ([[hero-stage]]). The hero
 * makes "what CheckWise actually looks like" the first thing the
 * visitor sees, instead of an invented cockpit.
 */
export function HeroSection() {
  const { reduced: reduce } = useMotionPreference();
  const fade = (delay: number) =>
    reduce
      ? ({ initial: false, animate: { opacity: 1 } } as const)
      : ({
          initial: { opacity: 0, y: 14 },
          animate: { opacity: 1, y: 0 },
          transition: { duration: 0.55, ease: EASE_ENTER, delay },
        } as const);

  return (
    <section className="relative isolate overflow-hidden">
      <HeroAmbient />

      <div className="relative mx-auto grid max-w-[1320px] grid-cols-1 items-center gap-12 px-5 pb-12 pt-14 sm:pt-16 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)] lg:gap-14 lg:pb-16 lg:pt-20 xl:gap-20">
        {/* ── Left rail: editorial type column ──────────────────── */}
        <div className="min-w-0">
          <motion.div
            {...fade(0)}
            className="flex flex-wrap items-center gap-3"
          >
            <Badge variant="teal" className="rounded-full px-3 py-1">
              <Sparkle className="h-3 w-3" weight="fill" aria-hidden="true" />
              Plataforma de cumplimiento REPSE
            </Badge>
            <span
              aria-hidden="true"
              className="hidden h-px w-8 bg-[color:var(--border-default)] sm:block"
            />
            <span className="hidden font-mono text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-tertiary)] sm:inline">
              {`México · ${new Date().getFullYear()}`}
            </span>
          </motion.div>

          <motion.h1
            {...fade(0.06)}
            className="mt-6 break-words font-semibold tracking-[-0.024em] text-[color:var(--text-primary)] [text-wrap:balance]"
            style={{
              fontSize: "clamp(2.1rem, 4.1vw, 3.4rem)",
              lineHeight: "1.04",
            }}
          >
            El expediente REPSE de cada proveedor,{" "}
            <span className="text-[color:var(--text-teal)]">
              en una sola plataforma operada con tu cliente.
            </span>
          </motion.h1>

          <motion.p
            {...fade(0.12)}
            className="mt-6 max-w-[48ch] text-[15px] leading-[1.65] text-[color:var(--text-secondary)] sm:text-[16.5px]"
          >
            CheckWise centraliza la evidencia REPSE, el calendario recurrente
            de SAT, IMSS, INFONAVIT y STPS, y los reportes ejecutivos para tu
            cliente. Cargas guiadas para proveedores, revisión humana de Legal
            Shelf y trazabilidad documental de extremo a extremo.
          </motion.p>

          <motion.div
            {...fade(0.18)}
            className="mt-7 flex flex-wrap items-center gap-3"
          >
            <Button
              asChild
              size="lg"
              className="group cw-hover-lift gap-2 rounded-full pl-6 pr-2 shadow-[0_12px_30px_-12px_hsl(var(--brand-navy)/0.50)]"
            >
              <Link href="#contacto">
                <span>Solicitar información</span>
                <span
                  aria-hidden="true"
                  className="ml-1 inline-flex h-8 w-8 items-center justify-center rounded-full bg-white/15 transition-transform duration-300 ease-nudge group-hover:translate-x-0.5"
                >
                  <ArrowRight className="h-3.5 w-3.5" weight="bold" />
                </span>
              </Link>
            </Button>
            <Button
              asChild
              variant="outline"
              size="lg"
              className="cw-hover-lift gap-2 rounded-full px-5"
            >
              <Link href="/login">
                <Lock className="h-4 w-4" weight="bold" aria-hidden="true" />
                <span>Iniciar sesión</span>
              </Link>
            </Button>
          </motion.div>

          {/* Product DNA caption */}
          <motion.div
            {...fade(0.24)}
            className="mt-7 flex flex-wrap items-center gap-x-3 gap-y-1.5 font-mono text-[10px] uppercase tracking-[0.22em] text-[color:var(--text-tertiary)]"
          >
            <span>Obligación</span>
            <span aria-hidden="true" className="text-[color:var(--text-teal)]">
              ×
            </span>
            <span>Evidencia</span>
            <span aria-hidden="true" className="text-[color:var(--text-teal)]">
              ×
            </span>
            <span>Período</span>
            <span aria-hidden="true" className="text-[color:var(--border-default)]">
              →
            </span>
            <span className="text-[color:var(--text-secondary)]">
              Estado actual
            </span>
          </motion.div>

          {/* Inline trust strip — folds into the same viewport */}
          <motion.ul
            {...fade(0.32)}
            className="mt-8 grid grid-cols-1 gap-3 border-t border-[color:var(--border-subtle)] pt-6 sm:grid-cols-3"
          >
            {[
              {
                icon: ShieldCheck,
                label: `REPSE ${new Date().getFullYear()}`,
                value: "SAT · IMSS · INFONAVIT · STPS",
              },
              {
                icon: Gavel,
                label: "Revisión humana",
                value: "Legal Shelf como respaldo",
              },
              {
                icon: Files,
                label: "Trazabilidad",
                value: "Hash · revisor · período",
              },
            ].map(({ icon: Icon, label, value }) => (
              <li key={label} className="flex items-start gap-2.5">
                <span
                  aria-hidden="true"
                  className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-[color:var(--surface-teal-muted)]"
                >
                  <Icon
                    className="h-3.5 w-3.5 text-[color:var(--text-teal)]"
                    weight="duotone"
                  />
                </span>
                <div className="min-w-0">
                  <p className="font-mono text-[9px] uppercase tracking-[0.18em] text-[color:var(--text-tertiary)]">
                    {label}
                  </p>
                  <p className="mt-0.5 text-[12.5px] font-medium leading-snug text-[color:var(--text-primary)]">
                    {value}
                  </p>
                </div>
              </li>
            ))}
          </motion.ul>
        </div>

        {/* ── Right canvas: animated screenshot stage ───────────── */}
        <motion.div
          className="relative min-w-0"
          initial={reduce ? false : { opacity: 0 }}
          animate={reduce ? { opacity: 1 } : { opacity: 1 }}
          transition={{ duration: 0.6, ease: EASE_ENTER }}
        >
          <HeroStage />
          {/* Operational metadata strip beneath the stage */}
          <motion.div
            initial={reduce ? false : { opacity: 0, y: 8 }}
            animate={reduce ? { opacity: 1 } : { opacity: 1, y: 0 }}
            transition={{
              duration: 0.55,
              ease: EASE_ENTER,
              delay: 1.45,
            }}
            className="mt-8 flex flex-wrap items-baseline gap-x-6 gap-y-1.5 border-t border-[color:var(--border-subtle)] pt-5"
          >
            <Metadata label="Workspaces" value="142 proveedores" />
            <Metadata label="Documentos" value="3,418 trazados" />
            <Metadata label="Próx. vencimiento" value="IMSS · 18 may" />
          </motion.div>
        </motion.div>
      </div>

      {/* Scroll hint — confirms there is more below the fold */}
      <ScrollHint />
    </section>
  );
}

function Metadata({ label, value }: { label: string; value: string }) {
  return (
    <div className="inline-flex items-baseline gap-2">
      <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-tertiary)]">
        {label}
      </span>
      <span className="font-mono text-[12px] tabular-nums text-[color:var(--text-primary)]">
        {value}
      </span>
    </div>
  );
}

function HeroAmbient() {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 -z-10 overflow-hidden"
    >
      {/* Navy 56px grid, masked toward center-top. Provides texture
          without introducing a third color (per Restrained palette). */}
      <div className="cw-grid-pattern absolute inset-0" />
      {/* Single soft teal halo at the upper-right shoulder of the
          stage — caps under 10% surface coverage. */}
      <div className="absolute -right-32 top-[-12%] hidden h-[480px] w-[480px] rounded-full bg-[color:var(--surface-teal-muted)] opacity-60 blur-3xl lg:block" />
    </div>
  );
}

function ScrollHint() {
  const { reduced: reduce } = useMotionPreference();
  return (
    <motion.div
      aria-hidden="true"
      className="pointer-events-none absolute inset-x-0 bottom-2 z-0 flex justify-center"
      initial={reduce ? false : { opacity: 0 }}
      animate={reduce ? { opacity: 1 } : { opacity: 1 }}
      transition={{ duration: 0.4, delay: 1.6 }}
    >
      <motion.span
        className="inline-flex items-center gap-2 font-mono text-[9px] uppercase tracking-[0.2em] text-[color:var(--text-tertiary)]"
        animate={reduce ? undefined : { y: [0, 4, 0] }}
        transition={
          reduce
            ? undefined
            : { duration: 2.6, repeat: Infinity, ease: "easeInOut" }
        }
      >
        <span className="h-px w-6 bg-[color:var(--border-default)]" />
        Continúa
        <span className="h-px w-6 bg-[color:var(--border-default)]" />
      </motion.span>
    </motion.div>
  );
}
