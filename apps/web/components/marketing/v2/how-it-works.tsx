"use client";

import { useEffect, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import {
  CalendarBlank,
  Eye,
  FileText,
  UploadSimple,
} from "@phosphor-icons/react";

import { ProductFrame } from "../product-frame";
import { Eyebrow, Section, SectionTitle } from "./_shared";
import { HowBeats, type Beat } from "./how-beats";

/**
 * Section 04 — Cómo funciona · El sistema (the section "Ver cómo funciona"
 * scrolls to). The four beats cycle calendario → evidencia → revisión →
 * reporte (slow + pausable), and the framed screenshot on the right
 * crossfades to the view that matches the active beat — so the words and the
 * product always show the same step. Click any beat to jump to it. Reduced
 * motion → no auto-cycle, instant swap.
 */
const EASE = [0.16, 1, 0.3, 1] as const;
const CYCLE_MS = 5500;

type FlowBeat = Beat & { img: string; chrome: string; alt: string };

const BEATS: readonly FlowBeat[] = [
  {
    n: "01",
    icon: CalendarBlank,
    title: "Calendario",
    body: "151 obligaciones por proveedor, periodo e institución.",
    img: "/marketing/product/portal-calendar.png",
    chrome: "Calendario · obligaciones por requisito",
    alt: "Calendario de obligaciones REPSE por proveedor, periodo e institución.",
  },
  {
    n: "02",
    icon: UploadSimple,
    title: "Evidencia",
    body: "Carga guiada en 5 pasos, en su lugar exacto.",
    img: "/marketing/product/portal-upload.png",
    chrome: "Evidencia · carga guiada en 5 pasos",
    alt: "Carga guiada de evidencia documental por requisito, en cinco pasos.",
  },
  {
    n: "03",
    icon: Eye,
    title: "Revisión",
    body: "Verificación con IA y decisión del equipo.",
    img: "/marketing/product/admin-reviewer-queue.png",
    chrome: "Revisión · cola de validación CheckWise",
    alt: "Cola de revisión CheckWise: verificación con IA y decisión humana.",
  },
  {
    n: "04",
    icon: FileText,
    title: "Reporte",
    body: "Genera el reporte automáticamente, auditable y firmado.",
    img: "/marketing/product/admin-report-editor.png",
    chrome: "Reporte · paquete auditable",
    alt: "Editor de reportes CheckWise: paquete auditable con trazabilidad firmada.",
  },
];

export function V2HowItWorks() {
  const reduced = useReducedMotion();
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    if (reduced || paused) return;
    const id = setInterval(
      () => setActive((a) => (a + 1) % BEATS.length),
      CYCLE_MS,
    );
    return () => clearInterval(id);
  }, [reduced, paused]);

  return (
    <Section id="sistema" band="page">
      <div
        className="grid items-center gap-12 lg:grid-cols-[0.82fr_1.18fr] lg:gap-16"
        onMouseEnter={() => setPaused(true)}
        onMouseLeave={() => setPaused(false)}
        onFocusCapture={() => setPaused(true)}
        onBlurCapture={() => setPaused(false)}
      >
        <div>
          <Eyebrow>El sistema</Eyebrow>
          <SectionTitle accent="Un solo expediente." className="mt-4">
            Calendario, evidencia, revisión y reporte.
          </SectionTitle>
          <p className="mt-5 max-w-[44ch] text-[17px] leading-[1.6] text-[color:var(--text-secondary)]">
            Una sola fuente de verdad por requisito, periodo e institución.
            Toca cualquier paso para verlo.
          </p>
          <div className="mt-9">
            <HowBeats beats={BEATS} active={active} onSelect={setActive} />
          </div>
        </div>

        <div className="lg:pl-2">
          <div className="grid">
            {BEATS.map((b, i) => {
              const on = i === active;
              return (
                <motion.div
                  key={b.n}
                  aria-hidden={!on}
                  initial={false}
                  animate={{ opacity: on ? 1 : 0 }}
                  transition={{ duration: reduced ? 0 : 0.55, ease: EASE }}
                  className={`col-start-1 row-start-1 ${on ? "" : "pointer-events-none"}`}
                >
                  <ProductFrame
                    src={b.img}
                    alt={b.alt}
                    chrome={b.chrome}
                    status="Vista en vivo"
                    aspect="16/11"
                    sizes="(min-width: 1024px) 58vw, 92vw"
                    loading="lazy"
                  />
                </motion.div>
              );
            })}
          </div>
        </div>
      </div>
    </Section>
  );
}
