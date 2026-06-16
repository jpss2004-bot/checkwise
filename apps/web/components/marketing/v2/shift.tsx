import {
  BellRinging,
  MagnifyingGlass,
  SealCheck,
  ShieldCheck,
} from "@phosphor-icons/react/dist/ssr";

import { Eyebrow, Section, SectionTitle } from "./_shared";

/**
 * Section 03 — Shift · Reactivo → Preventivo.
 *
 * Meaning: "a compliance signal travels detect → prove." A teal pulse runs
 * the rail through the 4 nodes (CSS .cw-rail-pulse, reduced-motion-safe).
 * Light band = relief after the two dark risk scenes.
 */
const STEPS = [
  { n: "01", icon: MagnifyingGlass, title: "Detecta", body: "Faltantes y vencimientos por requisito." },
  { n: "02", icon: ShieldCheck, title: "Valida", body: "Verificación con IA y revisión humana." },
  { n: "03", icon: BellRinging, title: "Anticipa", body: "Recordatorios antes de cada vencimiento." },
  { n: "04", icon: SealCheck, title: "Demuestra", body: "Expediente auditable, siempre listo." },
] as const;

export function V2Shift() {
  return (
    <Section id="prevencion" band="soft">
      <div className="max-w-[44ch]">
        <Eyebrow>Prevención REPSE</Eyebrow>
        <SectionTitle accent="a la prevención del riesgo." className="mt-4">
          Del seguimiento reactivo
        </SectionTitle>
      </div>

      <div className="relative mt-16">
        {/* rail + traveling compliance signal */}
        <div
          aria-hidden="true"
          className="absolute left-[12%] right-[12%] top-7 hidden h-px bg-[linear-gradient(90deg,transparent,hsl(var(--teal-500)/0.5),transparent)] lg:block"
        >
          <span className="cw-rail-pulse absolute top-0 -mt-[3px] h-1.5 w-16 rounded-full bg-[hsl(var(--teal-400))]" />
        </div>

        <ol className="grid gap-x-6 gap-y-12 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((s) => {
            const Icon = s.icon;
            return (
              <li key={s.n} className="relative text-center lg:text-left">
                <div className="relative z-10 mx-auto flex h-14 w-14 items-center justify-center rounded-2xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] text-[color:var(--text-teal)] shadow-[var(--shadow-sm)] lg:mx-0">
                  <Icon className="h-6 w-6" weight="duotone" aria-hidden="true" />
                </div>
                <div className="mt-5 flex items-center justify-center gap-2 lg:justify-start">
                  <h3 className="font-display text-[20px] font-bold tracking-[-0.01em] text-[color:var(--text-primary)]">
                    {s.title}
                  </h3>
                  <span className="font-mono text-[12px] text-[color:var(--text-tertiary)]">
                    {s.n}
                  </span>
                </div>
                <p className="mx-auto mt-1.5 max-w-[24ch] text-[14px] leading-[1.5] text-[color:var(--text-secondary)] lg:mx-0">
                  {s.body}
                </p>
              </li>
            );
          })}
        </ol>
      </div>
    </Section>
  );
}
