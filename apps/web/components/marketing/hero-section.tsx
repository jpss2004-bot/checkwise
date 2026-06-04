"use client";

import Link from "next/link";
import { motion } from "motion/react";
import {
  ArrowRight,
  CalendarCheck,
  CheckCircle,
  Gavel,
  Lock,
} from "@phosphor-icons/react";

import { Button } from "@/components/ui/button";

import { HeroStage } from "./hero-stage";
import { useMotionPreference } from "./motion-preference";

const EASE_ENTER = [0.16, 1, 0.3, 1] as const;

const HERO_PROOF = [
  { label: "Obligaciones", value: "151", detail: "requisitos REPSE sembrados" },
  { label: "Flujo", value: "5", detail: "pasos de carga guiada" },
  { label: "Salida", value: "PDF", detail: "Excel, HTML y paquete auditor" },
] as const;

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
    <section className="relative isolate overflow-hidden border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-page)]">
      <div
        aria-hidden="true"
        className="cw-grid-pattern pointer-events-none absolute inset-x-0 top-0 -z-10 h-[72%] opacity-[0.62]"
      />

      <div className="mx-auto grid max-w-[1320px] grid-cols-1 items-center gap-10 px-5 py-10 md:py-14 lg:min-h-[calc(100dvh-64px)] lg:grid-cols-[minmax(0,0.86fr)_minmax(0,1.14fr)] lg:gap-14 lg:py-12">
        <div className="min-w-0">
          <motion.div
            {...fade(0)}
            className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]/90 px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-secondary)] shadow-[0_12px_28px_-24px_hsl(var(--brand-navy)/0.45)] backdrop-blur-sm"
          >
            <span className="cw-pulse-soft inline-block h-1.5 w-1.5 rounded-full bg-[color:var(--text-teal)]" />
            CheckWise · cumplimiento REPSE
          </motion.div>

          <motion.h1
            {...fade(0.06)}
            className="mt-6 max-w-[15ch] font-semibold tracking-[-0.025em] text-[color:var(--text-primary)] [text-wrap:balance]"
            style={{
              fontSize: "clamp(2.3rem, 5vw, 4.6rem)",
              lineHeight: "0.98",
            }}
          >
            Controla el cumplimiento REPSE de todos tus proveedores.
          </motion.h1>

          <motion.p
            {...fade(0.12)}
            className="mt-6 max-w-[52ch] text-[16px] leading-[1.65] text-[color:var(--text-secondary)] md:text-[17px]"
          >
            CheckWise reúne calendario, evidencia, revisión humana y reportes en
            un solo expediente auditable. Ve qué falta, qué vence y qué está en
            riesgo en tu portafolio — antes de una inspección. La IA asiste; la
            decisión legal sigue siendo humana.
          </motion.p>

          <motion.div {...fade(0.18)} className="mt-8 flex flex-wrap gap-3">
            <Button
              asChild
              size="lg"
              className="group cw-hover-lift gap-2 rounded-full pl-6 pr-2 shadow-[0_12px_30px_-12px_hsl(var(--brand-navy)/0.50)]"
            >
              <Link href="#contacto">
                <span>Solicitar demo</span>
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
              variant="ghost"
              size="lg"
              className="cw-hover-lift gap-2 rounded-full px-4 text-[color:var(--text-secondary)]"
            >
              <Link href="#sistema">Ver el sistema</Link>
            </Button>
          </motion.div>
        </div>

        <div className="min-w-0 lg:row-span-2">
          <HeroStage />
        </div>

        <div className="min-w-0">
          <motion.div
            {...fade(0.24)}
            className="mt-6 grid max-w-[560px] grid-cols-1 gap-3 sm:grid-cols-3"
          >
            {HERO_PROOF.map((item) => (
              <div
                key={item.label}
                className="border-t border-[color:var(--border-default)] pt-3"
              >
                <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-secondary)]">
                  {item.label}
                </p>
                <p className="mt-1 text-[24px] font-semibold tracking-[-0.03em] text-[color:var(--text-primary)]">
                  {item.value}
                </p>
                <p className="mt-1 text-[12.5px] leading-[1.45] text-[color:var(--text-secondary)]">
                  {item.detail}
                </p>
              </div>
            ))}
          </motion.div>

          <motion.div
            {...fade(0.3)}
            className="mt-8 flex flex-wrap items-center gap-x-5 gap-y-2 text-[12.5px] text-[color:var(--text-secondary)]"
          >
            <span className="inline-flex items-center gap-2">
              <CalendarCheck className="h-3.5 w-3.5 text-[color:var(--text-teal)]" weight="bold" />
              Calendario y periodos
            </span>
            <span className="inline-flex items-center gap-2">
              <Gavel className="h-3.5 w-3.5 text-[color:var(--text-teal)]" weight="bold" />
              Revisión humana
            </span>
            <span className="inline-flex items-center gap-2">
              <CheckCircle className="h-3.5 w-3.5 text-[color:var(--text-teal)]" weight="bold" />
              Registro auditable
            </span>
          </motion.div>

          <motion.p
            {...fade(0.34)}
            className="mt-7 inline-flex items-center gap-2 text-[12.5px] text-[color:var(--text-tertiary)]"
          >
            <Lock className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
            <span>
              ¿Ya tienes acceso?{" "}
              <Link
                href="/login"
                className="font-medium text-[color:var(--text-secondary)] underline-offset-2 hover:text-[color:var(--text-primary)] hover:underline"
              >
                Iniciar sesión
              </Link>
            </span>
          </motion.p>
        </div>
      </div>
    </section>
  );
}
