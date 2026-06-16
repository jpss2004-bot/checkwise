import { ProductFrame } from "../product-frame";
import { Eyebrow, Section, SectionTitle } from "./_shared";
import { HowBeats } from "./how-beats";

/**
 * Section 04 — Cómo funciona · El sistema.
 *
 * The product loop, grounded in the real dashboard. The cycling active
 * beat (HowBeats) reads as one document moving through the loop. Light.
 */
export function V2HowItWorks() {
  return (
    <Section id="sistema" band="page">
      <div className="grid items-center gap-12 lg:grid-cols-[0.85fr_1.15fr] lg:gap-16">
        <div>
          <Eyebrow>El sistema</Eyebrow>
          <SectionTitle accent="Un solo expediente." className="mt-4">
            Calendario, evidencia, revisión y reporte.
          </SectionTitle>
          <p className="mt-5 max-w-[42ch] text-[16px] leading-[1.6] text-[color:var(--text-secondary)]">
            Una sola fuente de verdad por requisito, periodo e institución.
          </p>
          <div className="mt-9">
            <HowBeats />
          </div>
        </div>

        <div className="lg:pl-4">
          <ProductFrame
            src="/marketing/product/client-dashboard.png"
            alt="Sistema CheckWise: calendario de obligaciones y evidencia por requisito, con el expediente del proveedor a la vista."
            chrome="Sistema · calendario y evidencia por requisito"
            status="Vista en vivo"
            aspect="16/11"
            sizes="(min-width: 1024px) 56vw, 92vw"
          />
        </div>
      </div>
    </Section>
  );
}
