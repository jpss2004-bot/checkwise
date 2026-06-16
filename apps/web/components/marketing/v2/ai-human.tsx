import { AiHandoff } from "./ai-handoff";
import { Container, Eyebrow } from "./_shared";

/**
 * Section 06 — IA + Humano · Confianza.
 * Bold dark band (gravity/trust). The hand-off cycles IA → human → signed.
 */
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
      <Container className="relative py-[clamp(4.5rem,9vw,8rem)]">
        <Eyebrow tone="onNavy">AI + revisión humana</Eyebrow>
        <h2 className="font-display mt-4 max-w-[18ch] text-[clamp(2.3rem,4vw,3.6rem)] font-bold leading-[1.04] tracking-[-0.02em] [text-wrap:balance]">
          CheckWise acelera el criterio.{" "}
          <span className="text-[hsl(var(--teal-300))]">No lo reemplaza.</span>
        </h2>
        <p className="mt-6 max-w-[54ch] text-[18px] leading-[1.6] text-[hsl(var(--navy-200))] md:text-[19px]">
          La IA lee documentos, detecta anomalías y redacta observaciones.
          La aprobación de cada documento queda firmada por una persona, con
          actor, acción y fecha registrada.
        </p>
        <div className="mt-12">
          <AiHandoff />
        </div>
        <div className="mt-8 flex flex-wrap gap-2.5">
          {GUARDS.map((g) => (
            <span
              key={g}
              className="rounded-full border border-white/14 px-3.5 py-1.5 text-[12.5px] text-[hsl(var(--navy-200))]"
            >
              {g}
            </span>
          ))}
        </div>
      </Container>
    </section>
  );
}
