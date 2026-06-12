import { CaretDown } from "@phosphor-icons/react/dist/ssr";

import { FAQ_ITEMS } from "@/lib/marketing/faq";

/**
 * Landing FAQ. Deliberately a server component built on native
 * `<details>/<summary>` — every question and answer ships in the
 * initial HTML so crawlers index the long-tail REPSE copy without
 * executing any JS, and the disclosure behavior costs zero bundle.
 * Questions are `<h3>`s so they land in the document outline.
 *
 * The visible copy comes from the same `FAQ_ITEMS` array the FAQPage
 * JSON-LD on `app/page.tsx` serializes, which keeps the structured
 * data honest.
 */
export function FaqSection() {
  return (
    <section
      id="faq"
      className="relative isolate border-t border-[color:var(--border-subtle)] bg-[color:var(--surface-page)]"
    >
      <div className="mx-auto max-w-[1320px] px-5 py-24 lg:py-28">
        <div className="max-w-[62ch]">
          <p className="cw-eyebrow text-[color:var(--text-teal)]">
            Preguntas frecuentes
          </p>
          <h2
            className="mt-3 font-semibold tracking-[-0.022em] text-[color:var(--text-primary)] [text-wrap:balance]"
            style={{ fontSize: "clamp(1.9rem, 2.9vw, 2.55rem)", lineHeight: 1.04 }}
          >
            REPSE y CheckWise,{" "}
            <span className="text-[color:var(--text-teal)]">
              explicados sin rodeos.
            </span>
          </h2>
          <p className="mt-4 text-[15px] leading-[1.6] text-[color:var(--text-secondary)]">
            Lo que proveedores y empresas contratantes nos preguntan antes de
            empezar: qué es el REPSE, qué obligaciones implica y qué hace
            exactamente una plataforma de cumplimiento.
          </p>
        </div>

        <div className="mt-12 grid grid-cols-1 gap-x-12 lg:grid-cols-2">
          {FAQ_ITEMS.map((item) => (
            <details
              key={item.question}
              className="cw-faq group border-b border-[color:var(--border-subtle)] py-5"
            >
              <summary className="flex cursor-pointer list-none items-start justify-between gap-4 [&::-webkit-details-marker]:hidden">
                <h3 className="text-[15.5px] font-medium leading-snug text-[color:var(--text-primary)] transition-colors group-hover:text-[color:var(--text-teal)] group-open:text-[color:var(--text-teal)]">
                  {item.question}
                </h3>
                <span
                  aria-hidden="true"
                  className="mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-[color:var(--border-default)] text-[color:var(--text-tertiary)] transition-colors duration-300 group-hover:border-[color:var(--border-ai)] group-hover:text-[color:var(--text-teal)] group-open:border-[color:var(--border-ai)] group-open:bg-[color:var(--surface-teal-muted)] group-open:text-[color:var(--text-teal)]"
                >
                  <CaretDown
                    weight="bold"
                    className="h-3 w-3 transition-transform duration-300 group-open:rotate-180"
                  />
                </span>
              </summary>
              <p className="mt-3 max-w-[58ch] text-[14.5px] leading-[1.65] text-[color:var(--text-secondary)]">
                {item.answer}
              </p>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}
