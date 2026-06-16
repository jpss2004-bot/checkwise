import { Plus } from "@phosphor-icons/react/dist/ssr";

import { Eyebrow, Section, SectionTitle } from "./_shared";

/**
 * Section 09 — FAQ · mapeada a búsquedas.
 *
 * Questions are the keywords (interrogative long-tail + ICSOE/SISUB/
 * responsabilidad solidaria). Native <details> with the .cw-faq animation;
 * the FAQPage JSON-LD gets serialized from this same list in the AEO pass.
 */

const FAQS = [
  {
    q: "¿Cómo controlar los documentos de mis proveedores?",
    a: "CheckWise organiza cada documento por requisito en un expediente auditable: ves qué falta, qué vence y qué está en riesgo de cada proveedor, con carga guiada y revisión humana asistida por IA.",
  },
  {
    q: "¿Cómo organizar el expediente de proveedores para una auditoría?",
    a: "Cada obligación vive en su lugar exacto por requisito, periodo e institución. Al llegar una inspección exportas el paquete auditable en PDF, Excel o HTML, con trazabilidad firmada.",
  },
  {
    q: "¿Qué es la responsabilidad solidaria en REPSE?",
    a: "Es el riesgo de que las obligaciones laborales y fiscales de un proveedor incumplido recaigan sobre tu empresa contratante. Monitorear su cumplimiento documental es la forma de protegerte.",
  },
  {
    q: "¿Qué son el ICSOE y el SISUB?",
    a: "Son informes que los proveedores de servicios especializados deben presentar (ICSOE ante el IMSS; SISUB ante IMSS e Infonavit). CheckWise los integra al calendario de obligaciones de cada proveedor.",
  },
  {
    q: "¿La IA aprueba documentos por sí sola?",
    a: "No. La IA explica, redacta y detecta faltantes, pero la decisión legal siempre es del equipo CheckWise. Cada cambio queda firmado con actor, acción y fecha.",
  },
  {
    q: "¿Qué es el REPSE y quién debe registrarse?",
    a: "El REPSE es el registro de prestadoras de servicios especializados ante la STPS. Debe registrarse toda empresa que preste servicios u obras especializadas con personal propio.",
  },
] as const;

export function V2Faq() {
  return (
    <Section id="faq" band="page">
      <div className="text-center">
        <Eyebrow>Preguntas frecuentes</Eyebrow>
        <SectionTitle accent="explicados sin rodeos." className="mx-auto mt-4 text-center">
          REPSE y CheckWise,
        </SectionTitle>
      </div>

      <div className="mx-auto mt-12 grid max-w-[1000px] gap-4 md:grid-cols-2">
        {FAQS.map((f) => (
          <details
            key={f.q}
            className="cw-faq group rounded-2xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-5 open:shadow-[var(--shadow-sm)]"
          >
            <summary className="flex cursor-pointer list-none items-start justify-between gap-4">
              <h3 className="font-display text-[15.5px] font-semibold leading-[1.35] text-[color:var(--text-primary)]">
                {f.q}
              </h3>
              <Plus
                className="mt-0.5 h-4 w-4 shrink-0 text-[color:var(--text-teal)] transition-transform duration-200 group-open:rotate-45"
                weight="bold"
                aria-hidden="true"
              />
            </summary>
            <p className="mt-3 max-w-[60ch] text-[13.5px] leading-[1.6] text-[color:var(--text-secondary)]">
              {f.a}
            </p>
          </details>
        ))}
      </div>
    </Section>
  );
}
