"use client";

import {
  BellRinging,
  MagnifyingGlass,
  SealCheck,
  ShieldCheck,
} from "@phosphor-icons/react/dist/ssr";
import { motion } from "motion/react";

import { EASE_ENTER } from "../motion-helpers";
import { useMotionPreference } from "../motion-preference";
import { Eyebrow, Lead, Section, SectionTitle } from "./_shared";

/**
 * Prevención REPSE — the "del seguimiento reactivo a la prevención" beat.
 *
 * Earlier this was a closed clockwise circuit: four identical icon tiles at
 * the corners of a dashed rectangle, the headline boxed in the dead center,
 * and a comet looping the perimeter forever. A loop is the wrong shape for a
 * story that goes *from* one state *to* another, and the perpetual motion
 * read as decoration.
 *
 * Now it is a directional semáforo timeline. One rail flows through the four
 * compliance states the product actually tracks:
 *   navy  → you can see what is missing (Detecta)
 *   teal  → the system reasons, a person signs (Valida)
 *   amber → a deadline is near but still correctable (Anticipa)
 *   green → proven, ready for the inspection (Demuestra)
 * A single signal draws down the rail on scroll, lighting each stage as it
 * passes and sealing on the green node. Color carries state (graphic
 * elements at >=3:1); the copy stays high-contrast. Reduced motion renders
 * the whole rail drawn and every word still ships server-side for SEO.
 */
const STEPS = [
  {
    n: "01",
    icon: MagnifyingGlass,
    title: "Detecta",
    body: "Ve qué falta y qué vence por proveedor, requisito y periodo, en un expediente auditable con reportes automáticos.",
    tone: "--brand-navy",
  },
  {
    n: "02",
    icon: ShieldCheck,
    title: "Valida",
    body: "La IA clasifica el documento. El equipo CheckWise firma la decisión.",
    tone: "--teal-500",
  },
  {
    n: "03",
    icon: BellRinging,
    title: "Anticipa",
    body: "Alertas 30 días antes del vencimiento, por correo y en el semáforo.",
    tone: "--amber-500",
  },
  {
    n: "04",
    icon: SealCheck,
    title: "Demuestra",
    body: "Exporta el expediente firmado en PDF, Excel o HTML, listo para la inspección.",
    tone: "--green-500",
  },
] as const;

const VIEWPORT = { once: true, amount: 0.25 } as const;

export function V2Shift() {
  const { reduced } = useMotionPreference();

  return (
    <Section id="prevencion" band="soft">
      <div className="grid gap-x-[clamp(2rem,5vw,5rem)] gap-y-14 lg:grid-cols-[minmax(0,0.82fr)_minmax(0,1.18fr)]">
        {/* Anchored header — calm left column, not a centered stack. */}
        <header className="lg:sticky lg:top-[6.5rem] lg:self-start">
          <Eyebrow>Prevención REPSE</Eyebrow>
          <SectionTitle accent="a la prevención del riesgo." className="mt-4">
            Del seguimiento reactivo
          </SectionTitle>
          <Lead className="mt-6 max-w-[42ch]">
            Un solo flujo: detecta, valida, anticipa y demuestra, antes de que
            llegue la inspección.
          </Lead>
        </header>

        {/* Semáforo timeline — one rail, four states, navy to green. */}
        <ol className="relative">
          {STEPS.map((step, i) => {
            const Icon = step.icon;
            const isLast = i === STEPS.length - 1;
            const tone = `hsl(var(${step.tone}))`;
            const nodeDelay = 0.2 + i * 0.22;

            return (
              <li
                key={step.n}
                className="grid grid-cols-[2.75rem_minmax(0,1fr)]"
              >
                {/* Rail gutter: the node, then the segment down to the next. */}
                <div className="relative flex flex-col items-center">
                  <motion.span
                    className="relative z-10 mt-[0.35rem] block h-3.5 w-3.5 shrink-0 rounded-full"
                    style={{
                      backgroundColor: tone,
                      boxShadow: `0 0 0 3px var(--surface-raised), 0 0 0 6px hsl(var(${step.tone}) / 0.16)`,
                    }}
                    initial={reduced ? false : { scale: 0.3, opacity: 0 }}
                    whileInView={{ scale: 1, opacity: 1 }}
                    viewport={VIEWPORT}
                    transition={
                      reduced
                        ? undefined
                        : { duration: 0.45, ease: EASE_ENTER, delay: nodeDelay }
                    }
                  >
                    {/* One-time "sealed" ring on the proven (green) node. */}
                    {isLast && !reduced ? (
                      <motion.span
                        aria-hidden="true"
                        className="absolute inset-0 rounded-full"
                        style={{ border: `2px solid ${tone}` }}
                        initial={{ scale: 1, opacity: 0.7 }}
                        whileInView={{ scale: 2.6, opacity: 0 }}
                        viewport={VIEWPORT}
                        transition={{
                          duration: 0.9,
                          ease: EASE_ENTER,
                          delay: nodeDelay + 0.35,
                        }}
                      />
                    ) : null}
                  </motion.span>

                  {!isLast ? (
                    <span
                      aria-hidden="true"
                      className="relative -mt-1 mb-[-0.5rem] w-[2px] flex-1 overflow-hidden rounded-full"
                    >
                      <span
                        className="absolute inset-0 rounded-full"
                        style={{ backgroundColor: "hsl(var(--brand-navy) / 0.1)" }}
                      />
                      <motion.span
                        className="absolute inset-0 origin-top rounded-full"
                        style={{
                          backgroundImage: `linear-gradient(to bottom, hsl(var(${step.tone})), hsl(var(${STEPS[i + 1].tone})))`,
                        }}
                        initial={reduced ? false : { scaleY: 0 }}
                        whileInView={{ scaleY: 1 }}
                        viewport={VIEWPORT}
                        transition={
                          reduced
                            ? undefined
                            : {
                                duration: 0.7,
                                ease: EASE_ENTER,
                                delay: 0.32 + i * 0.22,
                              }
                        }
                      />
                    </span>
                  ) : null}
                </div>

                {/* Stage copy. */}
                <motion.div
                  className={isLast ? "" : "pb-[clamp(2.25rem,4vw,3.25rem)]"}
                  initial={reduced ? false : { opacity: 0, y: 12 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={VIEWPORT}
                  transition={
                    reduced
                      ? undefined
                      : { duration: 0.5, ease: EASE_ENTER, delay: nodeDelay + 0.06 }
                  }
                >
                  <div className="flex items-center gap-2.5">
                    <span className="font-mono text-[12px] font-medium tabular-nums text-[color:var(--text-tertiary)]">
                      {step.n}
                    </span>
                    <Icon
                      className="h-[18px] w-[18px] shrink-0"
                      weight="duotone"
                      style={{ color: tone }}
                      aria-hidden="true"
                    />
                    <h3 className="font-display text-[19px] font-bold leading-none tracking-[-0.01em] text-[color:var(--text-primary)]">
                      {step.title}
                    </h3>
                  </div>
                  <p className="mt-2.5 max-w-[44ch] text-[14.5px] leading-[1.55] text-[color:var(--text-secondary)]">
                    {step.body}
                  </p>
                </motion.div>
              </li>
            );
          })}
        </ol>
      </div>
    </Section>
  );
}
