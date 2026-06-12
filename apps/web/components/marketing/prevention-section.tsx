"use client";

import Link from "next/link";
import { ArrowRight } from "@phosphor-icons/react";
import { motion } from "motion/react";

import { EASE_ENTER, Reveal } from "./motion-helpers";
import { useMotionPreference } from "./motion-preference";

/**
 * Prevention section — the strategic core inherited from the old
 * legalshelf.mx/checkwise/repse page, whose internal benchmark board
 * labeled every iteration "PREVENCIÓN". The old site argued it with a
 * knight-vs-hydra illustration; the previous CheckWise version restated
 * it as a flat numbered grid. This version renders the same four-stage
 * model as a horizontal compliance pipeline: a signal travels
 * detect → validate → anticipate → prove, the connector draws in on
 * scroll, and each stage carries a semáforo status node. The diagram is
 * on-brand (a timeline, not a decorative card) and every word of copy
 * still ships in the server-rendered HTML, so the keyword-bearing
 * prevention copy stays indexable.
 *
 * Each stage maps to a compliance state so the colour means something:
 * navy = you can see it, teal = the system is reasoning, amber = a
 * deadline is approaching but still correctable, green = proven.
 */
const STAGES = [
  {
    n: "01",
    kicker: "Detecta",
    body: "El calendario de obligaciones y el semáforo del portafolio muestran qué falta, qué vence y qué proveedor está en riesgo — por requisito, periodo e institución.",
    tone: "hsl(var(--brand-navy))",
  },
  {
    n: "02",
    kicker: "Valida",
    body: "Cada documento se revisa contra el requisito, el periodo y el proveedor correctos. La IA analiza y detecta inconsistencias; una persona firma la decisión.",
    tone: "hsl(var(--brand-teal))",
  },
  {
    n: "03",
    kicker: "Anticipa",
    body: "Renovación REPSE, ICSOE, SISUB y opiniones de cumplimiento se siguen antes de la fecha límite — la alerta llega cuando todavía se puede corregir.",
    tone: "hsl(var(--amber-500))",
  },
  {
    n: "04",
    kicker: "Demuestra",
    body: "Cuando llega una auditoría o inspección, el expediente auditable y los reportes ejecutivos responden por ti, sin reconstruir meses de correos.",
    tone: "hsl(var(--green-500))",
  },
] as const;

export function PreventionSection() {
  return (
    <section
      id="prevencion"
      className="relative isolate border-t border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)]"
    >
      <div className="mx-auto max-w-[1320px] px-5 py-24 lg:py-28">
        <Reveal className="grid gap-6 md:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)] md:items-end">
          <div>
            <p className="cw-eyebrow text-[color:var(--text-teal)]">
              Prevención REPSE
            </p>
            <h2
              className="mt-3 font-semibold tracking-[-0.022em] text-[color:var(--text-primary)] [text-wrap:balance]"
              style={{
                fontSize: "clamp(1.9rem, 3vw, 2.65rem)",
                lineHeight: 1.04,
              }}
            >
              Del seguimiento reactivo{" "}
              <span className="text-[color:var(--text-teal)]">
                a la prevención del riesgo.
              </span>
            </h2>
          </div>
          <p className="text-[14px] leading-[1.65] text-[color:var(--text-secondary)] md:text-right">
            Un proveedor incumplido se traduce en multas, pérdida de
            deducibilidad y responsabilidad solidaria — para tu empresa, no
            solo para él. CheckWise convierte ese riesgo en un proceso que se
            detecta, se corrige y se demuestra a tiempo.
          </p>
        </Reveal>

        <PreventionPipeline />

        <Reveal className="mt-14">
          <p className="text-[13px] text-[color:var(--text-tertiary)]">
            ¿Nuevo en el tema?{" "}
            <Link
              href="/repse"
              className="group inline-flex items-center gap-1 font-medium text-[color:var(--text-secondary)] transition-colors hover:text-[color:var(--text-primary)]"
            >
              Lee la guía REPSE: registro, obligaciones y sanciones
              <ArrowRight
                className="h-3 w-3 transition-transform group-hover:translate-x-0.5"
                weight="bold"
                aria-hidden="true"
              />
            </Link>
          </p>
        </Reveal>
      </div>
    </section>
  );
}

function PreventionPipeline() {
  const { reduced: reduce } = useMotionPreference();

  return (
    <ol className="mt-16 grid grid-cols-1 gap-x-8 gap-y-12 sm:grid-cols-2 lg:mt-20 lg:grid-cols-4">
      {STAGES.map((stage, i) => {
        const isLast = i === STAGES.length - 1;
        const delay = reduce ? 0 : 0.15 + i * 0.14;
        return (
          <motion.li
            key={stage.n}
            className="group relative"
            initial={reduce ? false : { opacity: 0, y: 18 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.4 }}
            transition={{ duration: 0.55, ease: EASE_ENTER, delay }}
          >
            <div className="flex items-center gap-3 lg:block">
              <span
                className="relative inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full border bg-[color:var(--surface-raised)] font-mono text-[12px] font-semibold tracking-[0.04em] text-[color:var(--text-primary)] transition-colors duration-300 group-hover:border-[hsl(var(--brand-teal))]"
                style={{ borderColor: stage.tone }}
              >
                {stage.n}
                {/* Status node — semáforo dot pinned to the marker. */}
                <span
                  aria-hidden="true"
                  className="absolute -right-0.5 -top-0.5 h-3 w-3 rounded-full border-2 border-[color:var(--surface-raised)]"
                  style={{ backgroundColor: stage.tone }}
                />
              </span>

              {/* Connector to the next node — desktop only. A grey track
                  with a teal fill that draws in as this node reveals, so
                  the signal appears to travel detect → prove. The marker's
                  opaque bg occludes its own segment, keeping joints clean. */}
              {!isLast ? (
                <span
                  aria-hidden="true"
                  className="absolute left-[3.25rem] right-[-2rem] top-[1.375rem] hidden h-px overflow-hidden bg-[color:var(--border-default)] lg:block"
                >
                  <motion.span
                    className="absolute inset-0 origin-left bg-[hsl(var(--brand-teal))]"
                    initial={reduce ? false : { scaleX: 0 }}
                    whileInView={{ scaleX: 1 }}
                    viewport={{ once: true, amount: 0.4 }}
                    transition={{
                      duration: 0.7,
                      ease: EASE_ENTER,
                      delay: delay + 0.35,
                    }}
                  />
                </span>
              ) : null}

              {/* Text stays dark for AA contrast on white; the stage's
                  semáforo colour is carried by the marker border and the
                  status dot (graphic elements, ≥3:1), never by the copy. */}
              <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-[color:var(--text-primary)] lg:mt-5">
                {stage.kicker}
              </p>
            </div>
            <p className="mt-3 text-[14.5px] leading-[1.6] text-[color:var(--text-secondary)] lg:max-w-[30ch]">
              {stage.body}
            </p>
          </motion.li>
        );
      })}
    </ol>
  );
}
