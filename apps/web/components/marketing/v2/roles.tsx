import { Eyebrow, Section, SectionTitle } from "./_shared";
import { RolesSwitcher } from "./roles-switcher";

/**
 * Section 05 — Roles · Tres espacios, un expediente.
 * Meaning made literal: five views, one source of truth (RolesSwitcher).
 */
export function V2Roles() {
  return (
    <Section band="raised">
      <Eyebrow>Tres espacios, un expediente</Eyebrow>
      <SectionTitle accent="Todos ven la misma verdad." className="mt-4">
        Cada persona ve su trabajo.
      </SectionTitle>
      <p className="mt-5 max-w-[52ch] text-[16px] leading-[1.6] text-[color:var(--text-secondary)]">
        Cinco vistas, una sola fuente de verdad, conectadas por requisito,
        periodo, institución y evidencia.
      </p>
      <div className="mt-10">
        <RolesSwitcher />
      </div>
    </Section>
  );
}
