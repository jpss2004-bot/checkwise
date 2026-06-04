"use client";

import Image from "next/image";
import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  CalendarCheck,
  ChartLineUp,
  CheckCircle,
  ClipboardText,
  ClockClockwise,
  Gavel,
  WarningCircle,
  XCircle,
  type Icon,
} from "@phosphor-icons/react";

import { EASE_ENTER, Reveal } from "./motion-helpers";
import { useMotionPreference } from "./motion-preference";

type LoopStep = {
  id: string;
  label: string;
  title: string;
  body: string;
  output: string;
  icon: Icon;
};

type Slot = {
  name: string;
  period: string;
  institution: string;
  status: "approved" | "review" | "missing" | "rejected";
};

const LOOP: ReadonlyArray<LoopStep> = [
  {
    id: "calendar",
    label: "01 · Calendario",
    title: "Se abre la obligación correcta",
    body: "CheckWise parte de requisitos reales por cliente, proveedor, institución y periodo. No hay carga suelta.",
    output: "Slot creado",
    icon: CalendarCheck,
  },
  {
    id: "upload",
    label: "02 · Carga guiada",
    title: "El proveedor entrega evidencia con contexto",
    body: "El flujo pide el archivo correcto, captura metadatos y conserva reemplazos para no perder linaje.",
    output: "Evidencia recibida",
    icon: ClipboardText,
  },
  {
    id: "review",
    label: "03 · Revisión",
    title: "Legal Shelf decide con trazabilidad",
    body: "Aprobar, rechazar, pedir aclaración o registrar excepción queda firmado en auditoría.",
    output: "Decisión humana",
    icon: Gavel,
  },
  {
    id: "report",
    label: "04 · Reporte",
    title: "La operación se convierte en reporte",
    body: "El canvas AI arma bloques editables con datos tenant-scoped y exportación ejecutiva.",
    output: "PDF · Excel · HTML",
    icon: ChartLineUp,
  },
] as const;

const SLOTS: ReadonlyArray<Slot> = [
  {
    name: "Constancia fiscal",
    period: "Junio 2026",
    institution: "SAT",
    status: "approved",
  },
  {
    name: "Opinión IMSS",
    period: "Junio 2026",
    institution: "IMSS",
    status: "review",
  },
  {
    name: "REPSE vigente",
    period: "Anual 2026",
    institution: "STPS",
    status: "approved",
  },
  {
    name: "Pago INFONAVIT",
    period: "Bimestre 03",
    institution: "INFONAVIT",
    status: "missing",
  },
  {
    name: "Nómina timbrada",
    period: "Mayo 2026",
    institution: "SAT",
    status: "review",
  },
  {
    name: "IVA trasladado",
    period: "Mayo 2026",
    institution: "SAT",
    status: "rejected",
  },
] as const;

const STATUS = {
  approved: {
    label: "Aprobado",
    icon: CheckCircle,
    className:
      "border-[color:var(--doc-approved-border)] bg-[color:var(--doc-approved-bg)] text-[color:var(--doc-approved-text)]",
  },
  review: {
    label: "En revisión",
    icon: ClockClockwise,
    className:
      "border-[color:var(--doc-in-review-border)] bg-[color:var(--doc-in-review-bg)] text-[color:var(--doc-in-review-text)]",
  },
  missing: {
    label: "Faltante",
    icon: WarningCircle,
    className:
      "border-[color:var(--doc-needs-review-border)] bg-[color:var(--doc-needs-review-bg)] text-[color:var(--doc-needs-review-text)]",
  },
  rejected: {
    label: "Rechazado",
    icon: XCircle,
    className:
      "border-[color:var(--doc-rejected-border)] bg-[color:var(--doc-rejected-bg)] text-[color:var(--doc-rejected-text)]",
  },
} as const;

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
              Evidence Slot System
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
            El producto no organiza archivos por carpeta: organiza obligaciones
            por proveedor, periodo, institución, estado y decisión.
          </p>
        </Reveal>

        <div className="mt-14 grid grid-cols-1 gap-12 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] lg:gap-16">
          <Reveal className="lg:sticky lg:top-24 lg:self-start">
            <p className="cw-eyebrow">Compliance loop</p>
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

          <div className="min-w-0">
            <Reveal>
              <div className="overflow-hidden rounded-[14px] border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-[0_38px_90px_-44px_hsl(var(--brand-navy)/0.42),0_14px_28px_-18px_hsl(var(--brand-navy)/0.16)]">
                <div className="flex items-center gap-2 border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-page)]/88 px-3 py-2">
                  <span className="flex gap-1.5" aria-hidden="true">
                    <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--border-strong)]/70" />
                    <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--border-strong)]/45" />
                    <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--border-strong)]/30" />
                  </span>
                  <span className="ml-1 truncate font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-tertiary)]">
                    Expediente · evidencia por slot
                  </span>
                  <span className="ml-auto inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-teal)]">
                    <span className="cw-pulse-soft inline-block h-1.5 w-1.5 rounded-full bg-[color:var(--text-teal)]" />
                    Trazable
                  </span>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_320px]">
                  <div className="border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] p-4 lg:border-b-0 lg:border-r">
                    <div className="grid grid-cols-1 gap-3">
                      {SLOTS.map((slot, index) => (
                        <SlotTile key={`${slot.name}-${slot.period}`} slot={slot} index={index} />
                      ))}
                    </div>
                  </div>

                  <aside className="flex flex-col bg-[color:var(--surface-raised)]">
                    <AnimatePresence mode="wait">
                      <motion.div
                        key={step.id}
                        initial={reduce ? false : { opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={reduce ? { opacity: 0 } : { opacity: 0, y: -6 }}
                        transition={{ duration: 0.35, ease: EASE_ENTER }}
                        className="flex h-full flex-col"
                      >
                        <div className="border-b border-[color:var(--border-subtle)] px-5 py-5">
                          <span className="flex h-10 w-10 items-center justify-center rounded-md bg-[color:var(--surface-brand)] text-[color:var(--text-inverse)]">
                            <Icon className="h-4 w-4" weight="duotone" aria-hidden="true" />
                          </span>
                          <p className="mt-4 font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-tertiary)]">
                            {step.label}
                          </p>
                          <h3 className="mt-2 text-[20px] font-semibold leading-tight tracking-[-0.018em] text-[color:var(--text-primary)]">
                            {step.title}
                          </h3>
                          <p className="mt-3 text-[13.5px] leading-[1.58] text-[color:var(--text-secondary)]">
                            {step.body}
                          </p>
                        </div>
                        <div className="mt-auto px-5 py-5">
                          <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-tertiary)]">
                            Resultado
                          </p>
                          <p className="mt-1 text-[15px] font-semibold text-[color:var(--text-primary)]">
                            {step.output}
                          </p>
                        </div>
                      </motion.div>
                    </AnimatePresence>
                  </aside>
                </div>
              </div>
            </Reveal>

            <Reveal delay={0.08}>
              <div className="mt-8 overflow-hidden rounded-[14px] border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]">
                <div className="relative aspect-[16/10] bg-[color:var(--surface-page)]">
                  <Image
                    src="/marketing/product/portal-upload.png"
                    alt="Flujo de carga guiada de CheckWise con requisito, periodo e institución."
                    fill
                    sizes="(min-width: 1024px) 58vw, 92vw"
                    className="object-contain object-top p-3"
                    loading="lazy"
                  />
                </div>
              </div>
            </Reveal>
          </div>
        </div>
      </div>
    </section>
  );
}

function SlotTile({ slot, index }: { slot: Slot; index: number }) {
  const status = STATUS[slot.status];
  const StatusIcon = status.icon;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.2 }}
      transition={{ duration: 0.38, ease: EASE_ENTER, delay: index * 0.035 }}
      className="rounded-[8px] border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-3.5"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[14px] font-semibold leading-tight text-[color:var(--text-primary)]">
            {slot.name}
          </p>
          <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-tertiary)]">
            {slot.institution}
          </p>
        </div>
        <span
          className={`inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-1 font-mono text-[9px] uppercase tracking-[0.14em] ${status.className}`}
        >
          <StatusIcon className="h-3 w-3" weight="bold" aria-hidden="true" />
          {status.label}
        </span>
      </div>
      <div className="mt-4 h-px bg-[color:var(--border-subtle)]" />
      <p className="mt-2.5 text-[12.5px] text-[color:var(--text-secondary)]">
        Periodo: <span className="font-medium text-[color:var(--text-primary)]">{slot.period}</span>
      </p>
    </motion.div>
  );
}
