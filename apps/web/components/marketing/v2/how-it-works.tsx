"use client";

import { useRef } from "react";
import {
  motion,
  useReducedMotion,
  useScroll,
  useSpring,
  useTransform,
} from "motion/react";

import { ProductFrame } from "../product-frame";
import { Eyebrow, Section, SectionTitle } from "./_shared";
import { HowBeats } from "./how-beats";

/**
 * Section 04 — Cómo funciona · El sistema.
 *
 * The product loop, grounded in the real dashboard. As the section travels
 * through the viewport the camera dollies INTO the dashboard (a scroll-linked
 * zoom on the product frame), while the cycling beats read as one document
 * moving through the loop. The scroll target is the untransformed column so
 * the zoom never feeds back into its own measurement. Reduced motion → a
 * static frame, no zoom.
 */
export function V2HowItWorks() {
  const reduced = useReducedMotion();
  const colRef = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({
    target: colRef,
    offset: ["start end", "end start"],
  });
  const scaleRaw = useTransform(scrollYProgress, [0, 0.5, 1], [0.96, 1.06, 1.0]);
  const yRaw = useTransform(scrollYProgress, [0, 1], [26, -26]);
  const scale = useSpring(scaleRaw, { stiffness: 110, damping: 26, mass: 0.4 });
  const y = useSpring(yRaw, { stiffness: 110, damping: 26, mass: 0.4 });

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

        <div ref={colRef} className="lg:pl-4" style={{ perspective: "1200px" }}>
          <motion.div
            style={reduced ? undefined : { scale, y }}
            className="will-change-transform"
          >
            <ProductFrame
              src="/marketing/product/client-dashboard.png"
              alt="Sistema CheckWise: calendario de obligaciones y evidencia por requisito, con el expediente del proveedor a la vista."
              chrome="Sistema · calendario y evidencia por requisito"
              status="Vista en vivo"
              aspect="16/11"
              sizes="(min-width: 1024px) 56vw, 92vw"
            />
          </motion.div>
        </div>
      </div>
    </Section>
  );
}
