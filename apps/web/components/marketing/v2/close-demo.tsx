import Link from "next/link";
import { ArrowRight, CalendarCheck, CheckCircle } from "@phosphor-icons/react/dist/ssr";

import { Button } from "@/components/ui/button";
import { DEMO_BOOKING_URL } from "@/lib/marketing/booking";

import { Container, Eyebrow } from "./_shared";
import { PullIn } from "./pull-in";

/**
 * Section 10 — Cierre · Demo guiada. Bold dark conversion moment (primary
 * goal = demo bookings). Glowing gradient CTA, branded booking card that
 * pulls back into view (camera steps back to take in the whole picture).
 */
const POINTS = [
  "Demo en vivo sobre el producto real, no diapositivas.",
  "30 minutos: vista cliente, proveedor y consola CheckWise.",
  "Respondemos el mismo día hábil. CDMX.",
] as const;

export function V2CloseDemo() {
  return (
    <section
      id="contacto"
      className="relative overflow-hidden bg-[#03141f] text-white"
    >
      <div
        aria-hidden="true"
        className="pointer-events-none absolute left-1/2 top-[-10%] -z-0 h-[560px] w-[560px] -translate-x-1/2 rounded-full opacity-25 blur-[150px] [background:radial-gradient(circle,#09c1b0,transparent_62%)]"
      />
      <Container className="relative py-[clamp(4.5rem,9vw,8rem)]">
        <div className="grid items-center gap-12 lg:grid-cols-[1fr_0.85fr] lg:gap-16">
          <div>
            <Eyebrow tone="onNavy">Solicitar demo</Eyebrow>
            <h2 className="font-display mt-4 max-w-[16ch] text-[clamp(2.3rem,4vw,3.7rem)] font-bold leading-[1.04] tracking-[-0.02em] [text-wrap:balance]">
              Ve tu propia operación{" "}
              <span className="text-[hsl(var(--teal-300))]">
                en una demo guiada
              </span>
              .
            </h2>
            <p className="mt-6 max-w-[46ch] text-[18px] leading-[1.6] text-[hsl(var(--navy-200))] md:text-[19px]">
              Recorremos calendario, expediente, revisión CheckWise y reportes
              con IA usando datos de ejemplo. Sin video pregrabado.
            </p>
            <ul className="mt-7 space-y-3">
              {POINTS.map((p) => (
                <li key={p} className="flex items-start gap-3 text-[14.5px] text-white">
                  <CheckCircle
                    className="mt-0.5 h-4 w-4 shrink-0 text-[hsl(var(--teal-300))]"
                    weight="duotone"
                    aria-hidden="true"
                  />
                  {p}
                </li>
              ))}
            </ul>
          </div>

          <PullIn className="rounded-3xl border border-white/12 bg-white/[0.04] p-8 shadow-[0_30px_80px_-30px_rgba(0,0,0,0.6)] backdrop-blur">
            <div className="flex items-center gap-3">
              <span className="inline-flex h-11 w-11 items-center justify-center rounded-xl bg-[hsl(var(--teal-500))]/15 text-[hsl(var(--teal-300))]">
                <CalendarCheck className="h-5 w-5" weight="duotone" aria-hidden="true" />
              </span>
              <div>
                <p className="font-display text-[16px] font-semibold text-white">
                  Demo guiada CheckWise
                </p>
                <p className="text-[12.5px] text-[hsl(var(--navy-200))]">
                  30 min · en línea
                </p>
              </div>
            </div>
            <p className="mt-5 text-[13.5px] leading-[1.55] text-[hsl(var(--navy-200))]">
              Agenda directo en el calendario, o escríbenos y coordinamos el
              horario que te funcione.
            </p>
            <div className="mt-6 flex flex-col gap-2.5">
              <Button
                asChild
                size="lg"
                className="group w-full justify-center gap-2 rounded-full border-0 bg-[linear-gradient(135deg,#09c1b0,#3ad6c8)] text-[#04302c] shadow-[0_12px_40px_-12px_rgba(9,193,176,0.6)] hover:opacity-95"
              >
                <a href={DEMO_BOOKING_URL} target="_blank" rel="noreferrer noopener">
                  Agendar 30 min
                  <ArrowRight
                    className="h-4 w-4 transition-transform group-hover:translate-x-0.5"
                    weight="bold"
                    aria-hidden="true"
                  />
                </a>
              </Button>
              <Button
                asChild
                variant="ghost"
                size="lg"
                className="w-full justify-center rounded-full border border-white/20 text-white hover:bg-white/10 hover:text-white"
              >
                <Link href="/login">Ya tengo acceso</Link>
              </Button>
            </div>
          </PullIn>
        </div>
      </Container>
    </section>
  );
}
