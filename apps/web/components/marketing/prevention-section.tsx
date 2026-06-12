import Link from "next/link";
import { ArrowRight } from "@phosphor-icons/react/dist/ssr";

import { Reveal } from "./motion-helpers";

/**
 * Prevention section — the strategic core inherited from the old
 * legalshelf.mx/checkwise/repse page, whose internal benchmark board
 * labeled every iteration "PREVENCIÓN". The old site argued it with a
 * knight-vs-hydra illustration; here the same model is restated in the
 * new system's editorial language: a four-stage chain rendered as a
 * quiet numbered grid, no diagram theatrics.
 *
 * Server component on purpose: this is the page's densest
 * keyword-bearing copy (prevención REPSE, riesgo, multas,
 * responsabilidad solidaria, auditoría) and must ship in static HTML.
 * Motion is limited to the shared Reveal entrance used by every other
 * section.
 */
const STAGES = [
  {
    n: "01",
    kicker: "Detecta",
    body: "El calendario de obligaciones y el semáforo del portafolio muestran qué falta, qué vence y qué proveedor está en riesgo — por requisito, periodo e institución.",
  },
  {
    n: "02",
    kicker: "Valida",
    body: "Cada documento se revisa contra el requisito, el periodo y el proveedor correctos. La IA analiza y detecta inconsistencias; una persona firma la decisión.",
  },
  {
    n: "03",
    kicker: "Anticipa",
    body: "Renovación REPSE, ICSOE, SISUB y opiniones de cumplimiento se siguen antes de la fecha límite — la alerta llega cuando todavía se puede corregir.",
  },
  {
    n: "04",
    kicker: "Demuestra",
    body: "Cuando llega una auditoría o inspección, el expediente auditable y los reportes ejecutivos responden por ti, sin reconstruir meses de correos.",
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

        <Reveal className="mt-14 grid grid-cols-1 gap-x-10 gap-y-10 sm:grid-cols-2 lg:mt-16 lg:grid-cols-4">
          {STAGES.map((stage) => (
            <div
              key={stage.n}
              className="border-t border-[color:var(--border-default)] pt-5"
            >
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-teal)]">
                {stage.n} · {stage.kicker}
              </p>
              <p className="mt-3 text-[14.5px] leading-[1.6] text-[color:var(--text-secondary)]">
                {stage.body}
              </p>
            </div>
          ))}
        </Reveal>

        <Reveal className="mt-12">
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
