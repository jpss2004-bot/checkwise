import { Eyebrow, Lead, Section, SectionTitle } from "./_shared";
import { RolesSwitcher } from "./roles-switcher";

/**
 * Section 05 — Roles · Cinco vistas, un expediente.
 * Meaning made literal: five views, one source of truth (RolesSwitcher),
 * each with a real product preview. The chosen tab is highlighted and the
 * others stay visible — "la opción elegida se remarca; no se elimina."
 */
export function V2Roles() {
  return (
    <Section id="roles" band="raised">
      <Eyebrow>Cinco vistas, un expediente</Eyebrow>
      <SectionTitle accent="Todos ven la misma verdad." className="mt-4">
        Cada persona ve su trabajo.
      </SectionTitle>
      <Lead className="mt-5">
        Una sola fuente de verdad, conectada por requisito, periodo,
        institución y evidencia.
      </Lead>
      <div className="mt-10">
        <RolesSwitcher />
      </div>
    </Section>
  );
}
