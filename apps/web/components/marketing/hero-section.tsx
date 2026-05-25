"use client";

import Image from "next/image";
import Link from "next/link";
import { motion } from "motion/react";
import { ArrowRight, Lock } from "@phosphor-icons/react";

import { Button } from "@/components/ui/button";

import { HeroStage } from "./hero-stage";
import { useMotionPreference } from "./motion-preference";

const EASE_ENTER = [0.16, 1, 0.3, 1] as const;

/**
 * Hero — pain-first typographic column + layered product stage.
 *
 * The page opens on a single sentence framed around the problem ("stop
 * chasing REPSE documents"), a tight subhead that names what CheckWise
 * is, and one primary CTA. The stage to the right carries the live
 * proof. The mobile path collapses to the typographic column + an
 * inline product screenshot.
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
    <section className="relative isolate min-h-[640px] overflow-hidden bg-[color:var(--surface-page)] md:min-h-[min(88vh,860px)]">
      <HeroStage />

      <div className="relative mx-auto flex min-h-[640px] max-w-[1320px] items-center px-5 py-16 md:min-h-[min(88vh,860px)] md:py-20">
        <div className="max-w-[560px] min-w-0">
          <motion.div
            {...fade(0)}
            className="inline-flex items-center gap-2 rounded-full border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]/85 px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-secondary)] backdrop-blur-sm"
          >
            <span className="cw-pulse-soft inline-block h-1.5 w-1.5 rounded-full bg-[color:var(--text-teal)]" />
            CheckWise · Sistema operativo REPSE
          </motion.div>

          <motion.h1
            {...fade(0.06)}
            className="mt-6 font-semibold tracking-[-0.025em] text-[color:var(--text-primary)] [text-wrap:balance]"
            style={{
              fontSize: "clamp(2rem, 4vw, 3.25rem)",
              lineHeight: "1.04",
            }}
          >
            Controla la documentación REPSE de tus proveedores{" "}
            <span className="text-[color:var(--text-teal)]">
              sin perseguir archivos cada mes.
            </span>
          </motion.h1>

          <motion.p
            {...fade(0.12)}
            className="mt-5 max-w-[44ch] text-[16px] leading-[1.55] text-[color:var(--text-secondary)]"
          >
            Calendario, carga guiada, revisión humana y reportes
            ejecutivos sobre un mismo expediente trazable.
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
              <Link href="#features">
                <span>Ver cómo funciona</span>
              </Link>
            </Button>
          </motion.div>

          {/* Mobile-only inline screenshot — shows the product on small
              screens where the desktop stage is hidden. */}
          <motion.div
            {...fade(0.22)}
            className="mt-10 overflow-hidden rounded-[12px] border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-[0_24px_60px_-36px_hsl(var(--brand-navy)/0.35)] md:hidden"
          >
            <div className="flex items-center gap-1.5 border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] px-3 py-2">
              <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--border-strong)]/70" />
              <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--border-strong)]/45" />
              <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--border-strong)]/30" />
              <span className="ml-2 font-mono text-[9px] uppercase tracking-[0.16em] text-[color:var(--text-tertiary)]">
                Portal proveedor · en vivo
              </span>
            </div>
            <Image
              src="/marketing/product/portal-dashboard.png"
              alt="Dashboard del proveedor con cumplimiento y próximas acciones."
              width={1920}
              height={1080}
              priority
              className="block h-auto w-full"
              sizes="92vw"
            />
          </motion.div>

          {/* Quiet utility note — replaces the prior chip-trail of role
              names. One line, one promise. */}
          <motion.p
            {...fade(0.28)}
            className="mt-10 inline-flex items-center gap-2 text-[12.5px] text-[color:var(--text-tertiary)]"
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

      <ScrollHint />
    </section>
  );
}

function ScrollHint() {
  const { reduced: reduce } = useMotionPreference();
  return (
    <motion.div
      aria-hidden="true"
      className="pointer-events-none absolute inset-x-0 bottom-3 z-0 flex justify-center"
      initial={reduce ? false : { opacity: 0 }}
      animate={{ opacity: 1 }}
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
