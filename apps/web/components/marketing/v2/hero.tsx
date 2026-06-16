import Link from "next/link";
import { ArrowRight } from "@phosphor-icons/react/dist/ssr";

import { Button } from "@/components/ui/button";

import { Container } from "./_shared";
import { HeroSemaforo } from "./hero-semaforo";

/**
 * Section 01 — Hero · Control.
 *
 * Bold direction: a dark, vivid hero (deep navy base + teal/blue/violet
 * aurora glows) so color pops; huge headline; ONE-line subhead; glowing
 * gradient CTA; the live semáforo dashboard floating bright against the
 * dark. Visual-first, low-text. H1 stays server-rendered for LCP/SEO.
 */

const PROOF = [
  { value: "151", detail: "obligaciones REPSE" },
  { value: "5 pasos", detail: "carga guiada" },
  { value: "PDF · Excel", detail: "listo para auditar" },
] as const;

export function V2Hero() {
  return (
    <section
      id="inicio"
      className="relative isolate overflow-hidden bg-[#03141f] text-white"
    >
      {/* aurora glows */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 -z-10 overflow-hidden"
      >
        <div className="absolute -top-[20%] left-[46%] h-[820px] w-[820px] rounded-full opacity-55 blur-[130px] [background:radial-gradient(circle,#09c1b0,transparent_62%)]" />
        <div className="absolute top-[4%] -left-[6%] h-[560px] w-[560px] rounded-full opacity-40 blur-[130px] [background:radial-gradient(circle,#0470a8,transparent_62%)]" />
        <div className="absolute -bottom-[16%] left-[30%] h-[640px] w-[640px] rounded-full opacity-25 blur-[150px] [background:radial-gradient(circle,#0e7490,transparent_62%)]" />
        <div className="absolute inset-0 [background:radial-gradient(130%_110%_at_50%_-5%,transparent_38%,#03141f_82%)]" />
      </div>
      <div
        aria-hidden="true"
        className="cw-grid-pattern absolute inset-0 -z-10 opacity-[0.14]"
      />

      <Container className="grid grid-cols-1 items-center gap-12 py-20 md:py-24 lg:min-h-[calc(100dvh-66px)] lg:grid-cols-[minmax(0,0.92fr)_minmax(0,1.08fr)] lg:gap-16">
        <div className="min-w-0">
          <span className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/[0.06] px-3 py-1 font-mono text-[10.5px] uppercase tracking-[0.18em] text-[hsl(var(--teal-300))] backdrop-blur">
            <span className="cw-pulse-soft h-1.5 w-1.5 rounded-full bg-[hsl(var(--teal-400))]" />
            Cumplimiento y prevención REPSE
          </span>

          <h1
            className="font-display mt-6 max-w-[15ch] font-bold tracking-[-0.025em] [text-wrap:balance]"
            style={{ fontSize: "clamp(2.7rem, 5.2vw, 5rem)", lineHeight: "0.98" }}
          >
            Controla el cumplimiento REPSE de todos tus{" "}
            <span className="text-[hsl(var(--teal-300))]">proveedores</span>.
          </h1>

          <p className="mt-6 max-w-[44ch] text-[17px] leading-[1.6] text-[hsl(var(--navy-200))] md:text-[18px]">
            El expediente auditable que ve qué falta, qué vence y qué está en
            riesgo. Antes de la inspección.
          </p>

          <div className="mt-9 flex flex-wrap items-center gap-3.5">
            <Button
              asChild
              size="lg"
              className="group gap-2 rounded-full border-0 bg-[linear-gradient(135deg,#09c1b0,#3ad6c8)] pl-6 pr-2 text-[#04302c] shadow-[0_12px_44px_-10px_rgba(9,193,176,0.65)] hover:opacity-95"
            >
              <Link href="#contacto">
                <span>Solicitar demo</span>
                <span
                  aria-hidden="true"
                  className="ml-1 inline-flex h-8 w-8 items-center justify-center rounded-full bg-[#04302c]/15 transition-transform duration-300 group-hover:translate-x-0.5"
                >
                  <ArrowRight className="h-3.5 w-3.5" weight="bold" />
                </span>
              </Link>
            </Button>
            <Button
              asChild
              variant="ghost"
              size="lg"
              className="gap-2 rounded-full border border-white/20 px-5 text-white hover:bg-white/10 hover:text-white"
            >
              <Link href="#sistema">Ver cómo funciona</Link>
            </Button>
          </div>

          <dl className="mt-10 flex max-w-[560px] flex-wrap gap-x-7 gap-y-4">
            {PROOF.map((p) => (
              <div
                key={p.detail}
                className="sm:border-l sm:border-white/15 sm:pl-4 sm:first:border-l-0 sm:first:pl-0"
              >
                <dd className="font-display text-[20px] font-bold tracking-[-0.02em] tabular-nums text-white">
                  {p.value}
                </dd>
                <dt className="mt-0.5 text-[12px] text-[hsl(var(--navy-200))]">
                  {p.detail}
                </dt>
              </div>
            ))}
          </dl>
        </div>

        <div className="min-w-0">
          <HeroSemaforo />
        </div>
      </Container>
    </section>
  );
}
