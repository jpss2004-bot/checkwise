"use client";

import {
  Buildings,
  CalendarBlank,
  ChartLineUp,
  ClipboardText,
  Files,
  Gavel,
  Lightbulb,
  Robot,
  type Icon,
} from "@phosphor-icons/react";
import { motion } from "motion/react";

import { Reveal, Stagger, STAGGER_ITEM_VARIANTS, EASE_ENTER } from "./motion-helpers";
import { useMotionPreference } from "./motion-preference";

/**
 * Asymmetric features block.
 *
 * The legacy 4-col equal-card grid violates the visual-direction
 * doctrine (anti-pattern: "Identical card grids"). This rebuild uses a
 * left-anchored "headline feature" plus a right-side vertical list of
 * border-divided rows — same content, much less visual monotony.
 */

const HEADLINE = {
  icon: ClipboardText,
  eyebrow: "La columna vertebral",
  title: "Un expediente operativo, no un repositorio",
  body:
    "Cada documento se carga contra una obligación específica, con su periodo, su requisito y su responsable. Lo que para tu cliente es un reporte, para CheckWise es un objeto trazable que puede explicar quién hizo qué, cuándo y con qué evidencia.",
  metrics: [
    { label: "Instituciones", value: "SAT · IMSS · INFONAVIT · STPS" },
    { label: "Periodicidad", value: "Mensual / Bimestral / Cuatrimestral / Anual" },
    { label: "Trazabilidad", value: "Hash · revisor · periodo · resultado" },
  ],
} as const;

type Feature = { icon: Icon; title: string; body: string };

const FEATURES: Feature[] = [
  {
    icon: CalendarBlank,
    title: "Calendario REPSE 2026",
    body:
      "12 meses × 4 instituciones en una sola vista. Cada celda abre la obligación y su evidencia.",
  },
  {
    icon: Lightbulb,
    title: "Recordatorios accionables",
    body:
      "Alertas antes del vencimiento, con la acción exacta que el proveedor debe ejecutar.",
  },
  {
    icon: Files,
    title: "Trazabilidad documental",
    body:
      "Hash, periodo, revisor humano y resultado. Auditable de extremo a extremo.",
  },
  {
    icon: Gavel,
    title: "Revisión legal humana",
    body:
      "Legal Shelf valida lo crítico. CheckWise nunca firma documentos, sólo guía la operación.",
  },
  {
    icon: Robot,
    title: "Validación lista para OCR/IA",
    body:
      "Prevalidación determinística hoy, extracción estructurada con niveles de confianza en camino.",
  },
  {
    icon: ChartLineUp,
    title: "Reportes ejecutivos",
    body:
      "Cumplimiento, faltantes, riesgos y vencimientos, listos para enviar a dirección o auditoría.",
  },
  {
    icon: Buildings,
    title: "Experiencia premium para proveedores",
    body:
      "Portal claro, en español, pensado para usuarios no técnicos. Menos errores, menos roces.",
  },
];

export function FeaturesSection() {
  const { reduced: reduce } = useMotionPreference();
  const HeadlineIcon = HEADLINE.icon;
  return (
    <section className="bg-[color:var(--surface-raised)]">
      <div className="mx-auto max-w-[1320px] px-5 py-20 lg:py-28">
        <Reveal className="max-w-3xl">
          <p className="cw-eyebrow text-[color:var(--text-teal)]">Por qué CheckWise</p>
          <h2
            className="mt-3 font-semibold tracking-[-0.02em] text-[color:var(--text-primary)]"
            style={{ fontSize: "clamp(1.75rem, 2.8vw, 2.5rem)", lineHeight: 1.1 }}
          >
            Lo que separa una bandeja de archivos de un sistema de cumplimiento.
          </h2>
        </Reveal>

        <div className="mt-12 grid grid-cols-1 gap-10 lg:mt-16 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)] lg:gap-16">
          {/* Headline feature */}
          <Reveal className="min-w-0">
            <article className="relative flex h-full flex-col gap-6 rounded-[1.25rem] border border-[color:var(--border-default)] bg-[color:var(--surface-page)] p-7 lg:p-9">
              <span
                aria-hidden="true"
                className="inline-flex h-11 w-11 items-center justify-center rounded-xl bg-[color:var(--surface-teal-muted)]"
              >
                <HeadlineIcon
                  className="h-5 w-5 text-[color:var(--text-teal)]"
                  weight="duotone"
                />
              </span>
              <div>
                <p className="cw-eyebrow text-[color:var(--text-teal)]">
                  {HEADLINE.eyebrow}
                </p>
                <h3 className="mt-2 text-[22px] font-semibold leading-tight tracking-tight text-[color:var(--text-primary)] lg:text-[24px]">
                  {HEADLINE.title}
                </h3>
                <p className="mt-3 max-w-[55ch] text-[14.5px] leading-[1.65] text-[color:var(--text-secondary)]">
                  {HEADLINE.body}
                </p>
              </div>
              <dl className="mt-2 grid grid-cols-1 gap-3 border-t border-[color:var(--border-subtle)] pt-5 sm:grid-cols-3">
                {HEADLINE.metrics.map((m) => (
                  <div key={m.label} className="flex flex-col gap-1">
                    <dt className="font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-tertiary)]">
                      {m.label}
                    </dt>
                    <dd className="text-[12.5px] font-medium leading-snug text-[color:var(--text-primary)]">
                      {m.value}
                    </dd>
                  </div>
                ))}
              </dl>
            </article>
          </Reveal>

          {/* Vertical list */}
          <Stagger className="min-w-0 divide-y divide-[color:var(--border-subtle)] border-y border-[color:var(--border-subtle)]">
            {FEATURES.map(({ icon: Icon, title, body }) => (
              <motion.li
                key={title}
                variants={reduce ? undefined : STAGGER_ITEM_VARIANTS}
                transition={reduce ? undefined : { duration: 0.5, ease: EASE_ENTER }}
                className="group flex items-start gap-4 py-5 transition-colors hover:bg-[color:var(--surface-page)]"
              >
                <span
                  aria-hidden="true"
                  className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[color:var(--surface-page)] transition-colors group-hover:bg-[color:var(--surface-teal-muted)]"
                >
                  <Icon
                    className="h-4.5 w-4.5 text-[color:var(--text-teal)]"
                    weight="duotone"
                  />
                </span>
                <div className="min-w-0 flex-1">
                  <h4 className="text-[14.5px] font-semibold leading-snug text-[color:var(--text-primary)]">
                    {title}
                  </h4>
                  <p className="mt-1 text-[13px] leading-[1.6] text-[color:var(--text-secondary)]">
                    {body}
                  </p>
                </div>
              </motion.li>
            ))}
          </Stagger>
        </div>
      </div>
    </section>
  );
}
