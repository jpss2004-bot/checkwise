"use client";

import { motion } from "motion/react";
import { CalendarX, ShieldCheck, Warning } from "@phosphor-icons/react";

import { EASE_ENTER } from "./motion-helpers";
import { useMotionPreference } from "./motion-preference";
import { ProductFrame } from "./product-frame";

/**
 * Hero proof — Option A ("Tu operación, a la vista").
 *
 * A single, static, legible capture of the REAL client dashboard
 * (``client-dashboard.png``) framed in browser chrome. This replaced an
 * auto-rotating four-scene carousel built on synthetic composite
 * mockups: the carousel duplicated its captions, cropped illegibly on
 * mobile, and labelled marketing renders as "live". One honest
 * screenshot reads stronger for the client buyer and behaves on every
 * viewport.
 *
 * The signal strip below the screenshot names what the dashboard
 * surfaces (semáforo, faltantes, vencimientos) — qualitative labels, no
 * tenant-specific numbers, so it never goes stale or over-claims.
 */

const SIGNALS = [
  {
    icon: ShieldCheck,
    label: "Semáforo",
    body: "Cada proveedor en verde, amarillo o rojo según su evidencia.",
  },
  {
    icon: Warning,
    label: "Faltantes",
    body: "Documentos obligatorios pendientes, por requisito e institución.",
  },
  {
    icon: CalendarX,
    label: "Vencimientos",
    body: "Obligaciones próximas a vencer, antes de que sean un riesgo.",
  },
] as const;

export function HeroStage() {
  const { reduced: reduce } = useMotionPreference();

  return (
    <motion.div
      className="relative min-w-0"
      initial={reduce ? false : { opacity: 0, x: 24 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.78, ease: EASE_ENTER, delay: 0.1 }}
    >
      <div className="absolute -inset-8 -z-10 hidden rounded-[32px] border border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)]/40 lg:block" />
      <div
        aria-hidden="true"
        className="cw-grid-pattern pointer-events-none absolute -inset-10 -z-20 opacity-[0.58]"
      />

      <ProductFrame
        src="/marketing/product/client-dashboard.png"
        alt="Resumen del cliente en CheckWise: nivel de cumplimiento, proveedores en semáforo, faltantes obligatorios y vencimientos próximos del portafolio."
        chrome="Vista cliente · resumen del portafolio"
        status="Vista en vivo"
        aspect="16/10"
        priority
        sizes="(min-width: 1280px) 56vw, (min-width: 1024px) 60vw, 92vw"
        footer={
          <div className="grid grid-cols-1 divide-y divide-[color:var(--border-subtle)] sm:grid-cols-3 sm:divide-x sm:divide-y-0">
            {SIGNALS.map((signal) => {
              const Icon = signal.icon;
              return (
                <div key={signal.label} className="flex gap-3 px-4 py-3.5">
                  <span
                    aria-hidden="true"
                    className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-[color:var(--surface-teal-muted)] text-[color:var(--text-teal)]"
                  >
                    <Icon className="h-4 w-4" weight="duotone" />
                  </span>
                  <div className="min-w-0">
                    <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-secondary)]">
                      {signal.label}
                    </p>
                    <p className="mt-1 text-[12.5px] leading-[1.45] text-[color:var(--text-secondary)]">
                      {signal.body}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        }
      />
    </motion.div>
  );
}
