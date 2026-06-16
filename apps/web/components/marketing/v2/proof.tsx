import { Container, Eyebrow, SectionTitle } from "./_shared";
import { Reveal } from "./motion";
import { CountUp } from "./count-up";

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
  const track = [...LOGOS, ...LOGOS];

  return (
    <section className="overflow-hidden bg-[color:var(--surface-page)]">
      <Container className="pt-[clamp(4.5rem,9vw,8.5rem)] pb-10">
        <Reveal>
          <Eyebrow>Confían en Legal Shelf</Eyebrow>
          <div className="mt-4 flex flex-col gap-8 lg:flex-row lg:items-end lg:justify-between">
            <SectionTitle accent="ya operan con CheckWise.">
              Empresas líderes
            </SectionTitle>
            <div className="flex flex-wrap gap-x-10 gap-y-6 lg:pb-1 lg:text-right">
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
        </Reveal>
      </Container>

      {/* Infinite marquee — full-bleed, outside Container intentionally */}
      <div
        className="mt-6 overflow-hidden border-y border-[color:var(--border-default)] pb-[clamp(4.5rem,9vw,8.5rem)]"
        aria-hidden="true"
      >
        <ul className="cw-marquee flex w-max gap-4 py-5">
          {track.map((logo, i) => (
            <li
              key={i}
              className="flex h-[76px] w-[172px] shrink-0 items-center justify-center rounded-2xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] font-display text-[15px] font-bold tracking-[-0.01em] text-[hsl(var(--navy-700))] shadow-[var(--shadow-xs)]"
            >
              {logo}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
