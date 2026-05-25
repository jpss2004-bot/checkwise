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
 * Hero — typographic column anchors a layered product stage.
 *
 * The page opens with a single sentence carrying the product thesis, two
 * shorter context lines, and a paired CTA. The stage to the right
 * carries the proof: layered live screenshots that auto-rotate so the
 * visitor sees provider, review, client, and reports without scrolling.
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
    <section className="relative isolate min-h-[calc(100dvh-64px)] overflow-hidden bg-[color:var(--surface-page)]">
      <HeroStage />

      <div className="relative mx-auto flex min-h-[calc(100dvh-64px)] max-w-[1320px] items-center px-5 py-14 lg:py-20">
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
              fontSize: "clamp(2.2rem, 4.4vw, 3.6rem)",
              lineHeight: "1.02",
            }}
          >
            Una sola operación REPSE para{" "}
            <span className="text-[color:var(--text-teal)]">
              proveedor, cliente y Legal Shelf.
            </span>
          </motion.h1>

          <motion.p
            {...fade(0.12)}
            className="mt-5 max-w-[40ch] text-[16px] leading-[1.55] text-[color:var(--text-secondary)]"
          >
            Portales propios, revisión humana, copilot de reportes y
            paquetes listos para auditoría. Todo sobre el mismo expediente.
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
                <span>Agendar demo</span>
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
              <Link href="/login">
                <Lock className="h-4 w-4" weight="bold" aria-hidden="true" />
                <span>Iniciar sesión</span>
              </Link>
            </Button>
          </motion.div>

          {/* Mobile-only inline screenshot — shows the product on small
              screens where the desktop stage is hidden. */}
          <motion.div
            {...fade(0.22)}
            className="mt-9 overflow-hidden rounded-[12px] border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-[0_24px_60px_-36px_hsl(var(--brand-navy)/0.35)] md:hidden"
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

          {/* Compact line of proof — replaces the trust-strip row. */}
          <motion.div
            {...fade(0.28)}
            className="mt-9 flex flex-wrap items-center gap-x-5 gap-y-2 font-mono text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-tertiary)]"
          >
            <span>Portal proveedor</span>
            <Dot />
            <span>Portal cliente</span>
            <Dot />
            <span>Revisión Legal Shelf</span>
            <Dot />
            <span>Reportes con copilot</span>
            <Dot />
            <span>Paquete auditor</span>
          </motion.div>
        </div>
      </div>

      <ScrollHint />
    </section>
  );
}

function Dot() {
  return (
    <span
      aria-hidden="true"
      className="inline-block h-1 w-1 rounded-full bg-[color:var(--text-teal)]/70"
    />
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
