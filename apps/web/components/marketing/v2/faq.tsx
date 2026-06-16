import { Plus } from "@phosphor-icons/react/dist/ssr";

import { FAQ_ITEMS } from "@/lib/marketing/faq";

import { Eyebrow, Section, SectionTitle } from "./_shared";

/**
 * Section 09 — FAQ · mapeada a búsquedas.
 *
 * Renders the canonical FAQ_ITEMS (single source of truth) so the visible
 * accordion never drifts from the FAQPage JSON-LD serialized in app/page.tsx
 * — a Google rich-results requirement. Native <details> + .cw-faq animation.
 */
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
        {FAQ_ITEMS.map((f) => (
          <details
            key={f.question}
            className="cw-faq group rounded-2xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-5 open:shadow-[var(--shadow-sm)]"
          >
            <summary className="flex cursor-pointer list-none items-start justify-between gap-4">
              <h3 className="font-display text-[15.5px] font-semibold leading-[1.35] text-[color:var(--text-primary)]">
                {f.question}
              </h3>
              <Plus
                className="mt-0.5 h-4 w-4 shrink-0 text-[color:var(--text-teal)] transition-transform duration-200 group-open:rotate-45"
                weight="bold"
                aria-hidden="true"
              />
            </summary>
            <p className="mt-3 max-w-[64ch] text-[13.5px] leading-[1.6] text-[color:var(--text-secondary)]">
              {f.answer}
            </p>
          </details>
        ))}
      </div>
    </Section>
  );
}
