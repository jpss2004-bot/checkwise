import { CheckCircle } from "@phosphor-icons/react/dist/ssr";

import { ProductFrame } from "@/components/marketing/product-frame";

import { Container, DarkAtmo, Eyebrow } from "./_shared";

const STEPS = [
  {
    n: "01",
    title: "La IA propone",
    body: "Lee el documento, detecta anomalías y redacta la observación en segundos.",
  },
  {
    n: "02",
    title: "El revisor decide",
    body: "Un abogado CheckWise aprueba o rechaza. La IA nunca tiene la última palabra.",
  },
  {
    n: "03",
    title: "Queda registrado",
    body: "Actor, acción, timestamp y dirección IP. Sin excepción, sin modificaciones retroactivas.",
  },
] as const;

const GUARDS = [
  "Cada revisión firmada: actor, acción y fecha",
  "La aprobación es siempre de una persona",
  "Historial completo e inalterable",
] as const;

export function V2AiHuman() {
  return (
    <section id="ia" className="relative overflow-hidden bg-[#03141f] text-white">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -top-[10%] left-[18%] -z-0 h-[520px] w-[520px] rounded-full opacity-25 blur-[150px] [background:radial-gradient(circle,#09c1b0,transparent_62%)]"
      />
      <DarkAtmo />
      <Container className="relative py-[clamp(4.5rem,9vw,8rem)]">
        <div className="grid items-center gap-12 lg:grid-cols-[1fr_1.15fr] lg:gap-16">
          {/* Left — copy + steps + guarantees */}
          <div>
            <Eyebrow tone="onNavy">IA + revisión humana</Eyebrow>
            <h2 className="font-display mt-4 max-w-[18ch] text-[clamp(2.3rem,4vw,3.6rem)] font-bold leading-[1.04] tracking-[-0.02em] [text-wrap:balance]">
              CheckWise acelera el criterio.{" "}
              <span className="text-[hsl(var(--teal-300))]">No lo reemplaza.</span>
            </h2>
            <p className="mt-6 max-w-[48ch] text-[17px] leading-[1.65] text-[hsl(var(--navy-200))]">
              La IA lee documentos, detecta anomalías y redacta observaciones.
              La aprobación de cada documento queda firmada por una persona.
            </p>

            <ol className="mt-10 space-y-6" aria-label="Cómo funciona la revisión">
              {STEPS.map((step) => (
                <li key={step.n} className="flex gap-4">
                  <span
                    aria-hidden="true"
                    className="mt-0.5 shrink-0 font-mono text-[11px] font-medium tracking-[0.14em] text-[hsl(var(--teal-400))]"
                  >
                    {step.n}
                  </span>
                  <div>
                    <p className="text-[15px] font-semibold leading-snug text-white">
                      {step.title}
                    </p>
                    <p className="mt-1 text-[14px] leading-[1.55] text-[hsl(var(--navy-200))]">
                      {step.body}
                    </p>
                  </div>
                </li>
              ))}
            </ol>

            <ul className="mt-8 space-y-2.5" aria-label="Garantías de auditoría">
              {GUARDS.map((g) => (
                <li
                  key={g}
                  className="flex items-center gap-2.5 text-[13px] text-[hsl(var(--navy-200))]"
                >
                  <CheckCircle
                    className="h-4 w-4 shrink-0 text-[hsl(var(--teal-400))]"
                    weight="fill"
                    aria-hidden="true"
                  />
                  {g}
                </li>
              ))}
            </ul>
          </div>

          {/* Right — reviewer queue screenshot */}
          <div className="hidden lg:block">
            <ProductFrame
              src="/marketing/product/admin-reviewer-queue.png"
              alt="Cola de revisión CheckWise: la IA propone una observación y el revisor la aprueba o rechaza con un clic"
              chrome="Revisión · cola de validación CheckWise"
              status="Vista en vivo"
              aspect="16/10"
              loading="lazy"
              sizes="(min-width: 1024px) 50vw, 92vw"
            />
          </div>
        </div>
      </Container>
    </section>
  );
}
