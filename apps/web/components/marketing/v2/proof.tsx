import { Eyebrow, Section, SectionTitle } from "./_shared";
import { CountUp } from "./count-up";

/**
 * Section 07 — Prueba · Logos + resultados.
 * Proof = logos + quantified facts only (no fabricated testimonials).
 * Count-up = real figures tallying.
 */
const LOGOS = [
  "Capgemini",
  "BIC",
  "Sekura",
  "Juguetrón",
  "Benotto",
  "Giormar",
  "Samano Abogados",
  "+ más",
] as const;

export function V2Proof() {
  return (
    <Section band="page">
      <div className="grid items-center gap-12 lg:grid-cols-[1fr_1fr] lg:gap-16">
        <div>
          <Eyebrow>Confían en Legal Shelf</Eyebrow>
          <SectionTitle accent="ya operan con CheckWise." className="mt-4">
            Empresas líderes
          </SectionTitle>
          <p className="mt-5 max-w-[44ch] text-[16px] leading-[1.6] text-[color:var(--text-secondary)]">
            Construido por Legal Shelf, la firma de abogados especializada en
            cumplimiento REPSE con sede en Ciudad de México.
          </p>

          <div className="mt-9 flex flex-wrap gap-x-10 gap-y-6">
            <div>
              <div className="font-display text-[44px] font-bold leading-none tracking-[-0.03em] text-[color:var(--text-primary)] tabular-nums">
                <CountUp to={151} />
              </div>
              <div className="mt-2 max-w-[22ch] text-[13.5px] text-[color:var(--text-secondary)]">
                obligaciones controladas por proveedor
              </div>
            </div>
            <div>
              <div className="font-display text-[44px] font-bold leading-[0.95] tracking-[-0.03em] text-[color:var(--text-teal)]">
                semanas
                <br />a horas
              </div>
              <div className="mt-2 max-w-[22ch] text-[13.5px] text-[color:var(--text-secondary)]">
                para preparar una auditoría REPSE desde cero
              </div>
            </div>
          </div>
        </div>

        <ul className="grid grid-cols-2 gap-3">
          {LOGOS.map((logo) => (
            <li
              key={logo}
              className="flex h-[88px] items-center justify-center rounded-2xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] font-display text-[16px] font-bold tracking-[-0.01em] text-[hsl(var(--navy-700))] shadow-[var(--shadow-xs)]"
            >
              {logo}
            </li>
          ))}
        </ul>
      </div>
    </Section>
  );
}
