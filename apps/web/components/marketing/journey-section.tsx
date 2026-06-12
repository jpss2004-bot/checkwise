"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  CalendarCheck,
  ChartLineUp,
  ClipboardText,
  Gavel,
  type Icon,
} from "@phosphor-icons/react";

import { EASE_ENTER, Reveal } from "./motion-helpers";
import { useMotionPreference } from "./motion-preference";
import { ProductShot, type ProductShotFocus } from "./product-shot";

type LoopStep = {
  id: string;
  label: string;
  title: string;
  body: string;
  output: string;
  icon: Icon;
  image: string;
  chrome: string;
  focus: ProductShotFocus;
};

const LOOP: ReadonlyArray<LoopStep> = [
  {
    id: "calendar",
    label: "01 · Calendario",
    title: "Se abre la obligación correcta",
    body: "CheckWise parte de requisitos reales por cliente, proveedor, institución y periodo. No hay carga suelta.",
    output: "Obligación abierta",
    icon: CalendarCheck,
    image: "/marketing/product/portal-calendar.png",
    chrome: "Portal proveedor · calendario REPSE",
    focus: { position: "top center" },
  },
  {
    id: "upload",
    label: "02 · Carga guiada",
    title: "El proveedor entrega evidencia con contexto",
    body: "El flujo pide el archivo correcto, captura metadatos y conserva reemplazos para no perder linaje.",
    output: "Evidencia recibida",
    icon: ClipboardText,
    image: "/marketing/product/portal-upload.png",
    chrome: "Carga documental · intake guiado",
    focus: { position: "top center" },
  },
  {
    id: "review",
    label: "03 · Revisión",
    title: "El equipo CheckWise decide con trazabilidad",
    body: "Aprobar, rechazar, pedir aclaración o registrar excepción queda firmado en auditoría.",
    output: "Decisión humana",
    icon: Gavel,
    image: "/marketing/product/admin-reviewer-queue.png",
    chrome: "Bandeja CheckWise · revisión",
    focus: { position: "top center" },
  },
  {
    id: "report",
    label: "04 · Reporte",
    title: "La operación se convierte en reporte",
    body: "El editor con copiloto arma bloques editables con datos del expediente y exportación ejecutiva.",
    output: "PDF · Excel · HTML",
    icon: ChartLineUp,
    image: "/marketing/product/admin-report-editor.png",
    chrome: "Editor de reportes · copiloto",
    focus: { position: "top center" },
  },
] as const;

export function JourneySection() {
  const { reduced: reduce } = useMotionPreference();
  const [active, setActive] = useState(0);
  const step = LOOP[active];
  const Icon = step.icon;

  return (
    <section
      id="evidencia"
      className="relative isolate border-y border-[color:var(--border-subtle)] bg-[color:var(--surface-page)]"
    >
      <div
        aria-hidden="true"
        className="cw-grid-pattern pointer-events-none absolute inset-x-0 top-0 -z-10 h-[42%] opacity-[0.5]"
      />

      <div className="mx-auto max-w-[1320px] px-5 py-24 lg:py-28">
        <Reveal className="grid gap-6 md:grid-cols-[minmax(0,1.4fr)_minmax(0,0.8fr)] md:items-end">
          <div>
            <p className="cw-eyebrow text-[color:var(--text-teal)]">
              Sistema de evidencia por requisito
            </p>
            <h2
              className="mt-3 font-semibold tracking-[-0.022em] text-[color:var(--text-primary)] [text-wrap:balance]"
              style={{
                fontSize: "clamp(1.9rem, 3vw, 2.65rem)",
                lineHeight: 1.04,
              }}
            >
              Cada documento entra en un lugar exacto del expediente.
            </h2>
          </div>
          <p className="text-[14px] leading-[1.65] text-[color:var(--text-secondary)] md:text-right">
            El producto no organiza archivos por carpeta: organiza el control
            documental REPSE por proveedor, periodo, institución, estado y
            decisión.
          </p>
        </Reveal>

        <div className="mt-14 grid grid-cols-1 gap-12 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] lg:gap-16">
          <Reveal className="lg:sticky lg:top-24 lg:self-start">
            <p className="cw-eyebrow text-[color:var(--text-secondary)]">
              Ciclo de cumplimiento
            </p>
            <div className="mt-5 space-y-2">
              {LOOP.map((item, index) => {
                const ItemIcon = item.icon;
                const selected = index === active;
                return (
                  <button
                    key={item.id}
                    type="button"
                    aria-pressed={selected}
                    onClick={() => setActive(index)}
                    className={`group grid w-full grid-cols-[42px_minmax(0,1fr)] gap-3 rounded-[10px] border px-4 py-3.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]/40 ${
                      selected
                        ? "border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-[0_18px_38px_-30px_hsl(var(--brand-navy)/0.4)]"
                        : "border-transparent hover:bg-[color:var(--surface-raised)]"
                    }`}
                  >
                    <span
                      aria-hidden="true"
                      className={`mt-0.5 flex h-10 w-10 items-center justify-center rounded-md transition-colors ${
                        selected
                          ? "bg-[color:var(--surface-brand)] text-[color:var(--text-inverse)]"
                          : "bg-[color:var(--surface-teal-muted)] text-[color:var(--text-teal)]"
                      }`}
                    >
                      <ItemIcon className="h-4 w-4" weight="duotone" />
                    </span>
                    <span className="min-w-0">
                      <span className="block font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-tertiary)]">
                        {item.label}
                      </span>
                      <span className="mt-1 block text-[15px] font-semibold leading-tight text-[color:var(--text-primary)]">
                        {item.title}
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
          </Reveal>

          <Reveal className="min-w-0">
            <div className="overflow-hidden rounded-[14px] border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-[0_38px_90px_-44px_hsl(var(--brand-navy)/0.42),0_14px_28px_-18px_hsl(var(--brand-navy)/0.16)]">
              <div className="flex items-center gap-2 border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-page)]/88 px-3 py-2">
                <span className="flex gap-1.5" aria-hidden="true">
                  <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--border-strong)]/70" />
                  <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--border-strong)]/45" />
                  <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--border-strong)]/30" />
                </span>
                <AnimatePresence mode="wait">
                  <motion.span
                    key={step.chrome}
                    initial={reduce ? false : { opacity: 0, x: -4 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={reduce ? { opacity: 0 } : { opacity: 0, x: 4 }}
                    transition={{ duration: 0.25, ease: EASE_ENTER }}
                    className="ml-1 truncate font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-tertiary)]"
                  >
                    {step.chrome}
                  </motion.span>
                </AnimatePresence>
                <span className="ml-auto inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-teal)]">
                  <span className="cw-pulse-soft inline-block h-1.5 w-1.5 rounded-full bg-[color:var(--text-teal)]" />
                  Sincronizado
                </span>
              </div>

              <div className="bg-[color:var(--surface-raised)]">
                <div className="relative aspect-[16/10] overflow-hidden bg-[color:var(--surface-page)]">
                  <AnimatePresence mode="wait">
                    <motion.div
                      key={step.id}
                      className="absolute inset-0"
                      initial={reduce ? false : { opacity: 0, scale: 1.012 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.992 }}
                      transition={{ duration: 0.42, ease: EASE_ENTER }}
                    >
                      <ProductShot
                        src={step.image}
                        alt={`Captura de CheckWise para ${step.title.toLowerCase()}.`}
                        sizes="(min-width: 1024px) 72vw, 160vw"
                        loading="lazy"
                        focus={step.focus}
                      />
                    </motion.div>
                  </AnimatePresence>
                </div>

                <AnimatePresence mode="wait">
                  <motion.div
                    key={`detail-${step.id}`}
                    initial={reduce ? false : { opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={reduce ? { opacity: 0 } : { opacity: 0, y: -4 }}
                    transition={{ duration: 0.3, ease: EASE_ENTER }}
                    className="grid grid-cols-1 border-t border-[color:var(--border-subtle)] md:grid-cols-[minmax(0,1fr)_190px]"
                  >
                    <div className="grid grid-cols-[44px_minmax(0,1fr)] gap-4 px-5 py-5">
                      <span className="flex h-11 w-11 items-center justify-center rounded-md bg-[color:var(--surface-brand)] text-[color:var(--text-inverse)]">
                        <Icon className="h-4 w-4" weight="duotone" aria-hidden="true" />
                      </span>
                      <div className="min-w-0">
                        <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-tertiary)]">
                          {step.label}
                        </p>
                        <h3 className="mt-2 text-[20px] font-semibold leading-tight tracking-[-0.018em] text-[color:var(--text-primary)]">
                          {step.title}
                        </h3>
                        <p className="mt-3 max-w-[58ch] text-[13.5px] leading-[1.58] text-[color:var(--text-secondary)]">
                          {step.body}
                        </p>
                      </div>
                    </div>
                    <div className="border-t border-[color:var(--border-subtle)] px-5 py-5 md:border-l md:border-t-0">
                      <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-tertiary)]">
                        Resultado
                      </p>
                      <p className="mt-1 text-[15px] font-semibold text-[color:var(--text-primary)]">
                        {step.output}
                      </p>
                    </div>
                  </motion.div>
                </AnimatePresence>
              </div>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
