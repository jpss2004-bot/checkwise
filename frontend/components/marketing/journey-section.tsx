"use client";

import Image from "next/image";
import { useRef, useState } from "react";
import {
  motion,
  useMotionValueEvent,
  useScroll,
  useTransform,
} from "motion/react";
import {
  CalendarBlank,
  Files,
  Gavel,
  type Icon,
  ChartLineUp,
} from "@phosphor-icons/react";

import { Badge } from "@/components/ui/badge";

import { EASE_ENTER, Reveal } from "./motion-helpers";
import { useMotionPreference } from "./motion-preference";

/**
 * Storytelling Journey section.
 *
 * The hero answers "what is CheckWise" with a layered stage. This
 * section answers the next question: "what happens when a provider
 * uses it?" by walking through the four real product moments:
 *
 *   1. Obligación — REPSE calendar period activates
 *   2. Evidencia  — provider uploads guided documents
 *   3. Revisión   — Legal Shelf reviewer validates
 *   4. Reporte    — executive report ships to the client
 *
 * Layout:
 *   - Desktop: sticky left rail (intro + steps + progress bar) plus a
 *     scroll-snapped vertical column of large screenshots on the right.
 *   - Mobile : single vertical chain, each step preceded by its label.
 *
 * Animation discipline (ui-ux-pro-max):
 *   - duration 150–400ms for state changes
 *   - whileInView entrance, once: true
 *   - reduced-motion respected everywhere
 */

type Step = {
  id: number;
  eyebrow: string;
  title: string;
  body: string;
  caption: string;
  badge: { label: string; variant: "doc-pending" | "doc-uploaded" | "doc-in-review" | "doc-approved" };
  icon: Icon;
  image: string;
  imageAlt: string;
  objectPosition?: string;
};

const STEPS: Step[] = [
  {
    id: 1,
    eyebrow: "01 · Obligación",
    title: "Cada periodo abre con su mapa REPSE",
    body:
      "El calendario activa las obligaciones de SAT, IMSS, INFONAVIT y STPS para el periodo en curso. El proveedor ve exactamente qué le falta y para cuándo.",
    caption: "Calendario REPSE · 4 instituciones · 12 meses",
    badge: { label: "Periodo activo", variant: "doc-pending" },
    icon: CalendarBlank,
    image: "/marketing/hero/portal-calendar.png",
    imageAlt:
      "Calendario REPSE de CheckWise con instituciones SAT, IMSS, INFONAVIT y STPS por mes.",
    objectPosition: "left top",
  },
  {
    id: 2,
    eyebrow: "02 · Evidencia",
    title: "El expediente se llena con cargas guiadas",
    body:
      "Cada requisito explica qué subir, en qué formato y por qué se pide. Sin instrucciones por correo, sin spreadsheets paralelos.",
    caption: "Expediente inicial · documentos obligatorios y opcionales",
    badge: { label: "Subido", variant: "doc-uploaded" },
    icon: Files,
    image: "/marketing/hero/portal-dashboard.png",
    imageAlt:
      "Portal del proveedor con la lista de documentos pendientes y la próxima acción sugerida.",
    objectPosition: "left top",
  },
  {
    id: 3,
    eyebrow: "03 · Revisión",
    title: "Un revisor humano valida lo crítico",
    body:
      "El equipo de Legal Shelf revisa el documento, registra el dictamen y deja huella auditable. CheckWise nunca firma documentos.",
    caption: "Bandeja por revisar · FIFO con prioridad",
    badge: { label: "En revisión", variant: "doc-in-review" },
    icon: Gavel,
    image: "/marketing/hero/admin-reviewer-queue.png",
    imageAlt:
      "Bandeja de revisión de CheckWise mostrando documentos por validar y su origen.",
    objectPosition: "left top",
  },
  {
    id: 4,
    eyebrow: "04 · Reporte",
    title: "El cliente recibe el reporte ejecutivo",
    body:
      "Cumplimiento, faltantes, riesgos y vencimientos del portafolio, listos para enviar a dirección o auditoría con un clic.",
    caption: "Reportes ejecutivos · matriz de riesgo y faltantes",
    badge: { label: "Aprobado", variant: "doc-approved" },
    icon: ChartLineUp,
    image: "/marketing/hero/client-reports.png",
    imageAlt:
      "Vista de reportes ejecutivos para el cliente con plantillas y reportes recientes.",
    objectPosition: "left top",
  },
];

export function JourneySection() {
  const { reduced: reduce } = useMotionPreference();
  const sectionRef = useRef<HTMLDivElement | null>(null);
  const [active, setActive] = useState(0);

  const { scrollYProgress } = useScroll({
    target: sectionRef,
    offset: ["start 60%", "end 40%"],
  });

  // Discrete active-step tracking. Each step occupies an even slice of
  // the section's scroll range; clamp keeps the last step active while
  // the rail's tail scrolls past.
  useMotionValueEvent(scrollYProgress, "change", (latest) => {
    const idx = Math.min(STEPS.length - 1, Math.floor(latest * STEPS.length));
    setActive(idx);
  });

  const railProgress = useTransform(scrollYProgress, [0, 1], ["0%", "100%"]);

  return (
    <section
      id="producto"
      ref={sectionRef}
      className="relative isolate border-y border-[color:var(--border-subtle)] bg-[color:var(--surface-page)]"
    >
      {/* Subtle navy grid, masked to the section top — gives the band
          its own quiet texture without a third color. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[40%] cw-grid-pattern opacity-[0.7]"
      />

      <div className="mx-auto max-w-[1320px] px-5 py-20 lg:py-28">
        {/* ── Section header ───────────────────────────────────── */}
        <Reveal className="max-w-3xl">
          <p className="cw-eyebrow text-[color:var(--text-teal)]">
            El recorrido del cumplimiento
          </p>
          <h2
            className="mt-3 font-semibold tracking-[-0.02em] text-[color:var(--text-primary)] [text-wrap:balance]"
            style={{ fontSize: "clamp(1.75rem, 2.8vw, 2.5rem)", lineHeight: 1.1 }}
          >
            De una obligación pendiente al reporte ejecutivo,{" "}
            <span className="text-[color:var(--text-teal)]">en cuatro pasos reales.</span>
          </h2>
          <p className="mt-4 max-w-[55ch] text-[15px] leading-[1.65] text-[color:var(--text-secondary)]">
            CheckWise transforma cada obligación REPSE en un objeto trazable.
            Estas son las cuatro pantallas que tu proveedor, tu equipo y tu
            cliente recorren cada mes.
          </p>
        </Reveal>

        {/* ── Body: sticky rail + scroll column ────────────────── */}
        <div className="mt-12 grid grid-cols-1 gap-12 lg:mt-16 lg:grid-cols-[minmax(0,340px)_minmax(0,1fr)] lg:gap-16 xl:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
          {/* Sticky rail — desktop only */}
          <div className="hidden lg:block">
            <div className="sticky top-24">
              <p className="cw-eyebrow">
                Hilo conductor
              </p>
              <div className="mt-4 space-y-1">
                {STEPS.map((step, i) => {
                  const isActive = i === active;
                  return (
                    <button
                      key={step.id}
                      type="button"
                      onClick={() => {
                        const el = document.getElementById(`journey-step-${step.id}`);
                        el?.scrollIntoView({
                          behavior: reduce ? "auto" : "smooth",
                          block: "start",
                        });
                      }}
                      className="group block w-full rounded-lg text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]/40"
                      aria-current={isActive ? "step" : undefined}
                    >
                      <div className="flex items-start gap-3 px-2 py-2">
                        <span
                          className={`mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border font-mono text-[10px] font-semibold tabular-nums transition-colors ${
                            isActive
                              ? "border-[color:var(--border-brand)] bg-[color:var(--surface-brand)] text-[color:var(--text-inverse)]"
                              : "border-[color:var(--border-default)] bg-[color:var(--surface-raised)] text-[color:var(--text-tertiary)]"
                          }`}
                        >
                          {step.id}
                        </span>
                        <div className="min-w-0">
                          <p
                            className={`text-[14px] font-semibold leading-tight transition-colors ${
                              isActive
                                ? "text-[color:var(--text-primary)]"
                                : "text-[color:var(--text-secondary)] group-hover:text-[color:var(--text-primary)]"
                            }`}
                          >
                            {step.title}
                          </p>
                          <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-tertiary)]">
                            {step.eyebrow}
                          </p>
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>

              {/* Progress bar — driven by scroll */}
              <div className="mt-6 ml-2 mr-4 h-[3px] overflow-hidden rounded-full bg-[color:var(--border-subtle)]">
                <motion.div
                  className="h-full origin-left bg-[color:var(--text-teal)]"
                  style={
                    reduce
                      ? { width: "100%" }
                      : { width: railProgress, willChange: "width" }
                  }
                />
              </div>
              <p className="mt-3 ml-2 font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-tertiary)]">
                Paso{" "}
                <span className="font-semibold tabular-nums text-[color:var(--text-secondary)]">
                  {String(active + 1).padStart(2, "0")}
                </span>{" "}
                / {String(STEPS.length).padStart(2, "0")}
              </p>
            </div>
          </div>

          {/* Right column — large screenshot stages */}
          <ol className="space-y-12 lg:space-y-20">
            {STEPS.map((step, idx) => (
              <li
                key={step.id}
                id={`journey-step-${step.id}`}
                className="scroll-mt-24"
              >
                <Reveal>
                  <div className="grid grid-cols-1 items-start gap-5 lg:hidden">
                    {/* Mobile/tablet — header above the screenshot */}
                    <StepHeader step={step} />
                  </div>
                  <div className="grid grid-cols-1 gap-6 lg:gap-7">
                    <StepScreenshot
                      step={step}
                      idx={idx}
                      isLast={idx === STEPS.length - 1}
                    />
                    {/* Desktop — caption strip beneath the stage */}
                    <div className="hidden lg:block">
                      <StepCaption step={step} />
                    </div>
                  </div>
                </Reveal>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}

function StepHeader({ step }: { step: Step }) {
  return (
    <div>
      <div className="flex items-center gap-3">
        <span
          aria-hidden="true"
          className="flex h-9 w-9 items-center justify-center rounded-full bg-[color:var(--surface-brand)] font-mono text-[12px] font-semibold tabular-nums text-[color:var(--text-inverse)]"
        >
          {step.id}
        </span>
        <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-[color:var(--text-teal)]">
          {step.eyebrow}
        </p>
      </div>
      <h3 className="mt-3 text-[20px] font-semibold leading-tight text-[color:var(--text-primary)]">
        {step.title}
      </h3>
      <p className="mt-2 max-w-[58ch] text-[14px] leading-[1.65] text-[color:var(--text-secondary)]">
        {step.body}
      </p>
    </div>
  );
}

function StepCaption({ step }: { step: Step }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2 border-t border-[color:var(--border-subtle)] pt-4">
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1">
        <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-tertiary)]">
          {step.caption}
        </span>
      </div>
      <Badge variant={step.badge.variant} className="rounded-full">
        <step.icon className="h-3 w-3" weight="bold" aria-hidden="true" />
        {step.badge.label}
      </Badge>
    </div>
  );
}

function StepScreenshot({
  step,
  idx,
  isLast,
}: {
  step: Step;
  idx: number;
  isLast: boolean;
}) {
  const { reduced: reduce } = useMotionPreference();
  const screenRef = useRef<HTMLDivElement | null>(null);
  const { scrollYProgress } = useScroll({
    target: screenRef,
    offset: ["start end", "end start"],
  });
  // Image gently translates within its frame as the step scrolls past
  // its own viewport — pure parallax depth, no layout shift.
  const innerY = useTransform(
    scrollYProgress,
    [0, 1],
    [reduce ? 0 : -16, reduce ? 0 : 16],
  );

  return (
    <div className="relative">
      {/* Desktop — eyebrow + title above stage */}
      <div className="mb-5 hidden items-end justify-between gap-6 lg:flex">
        <div>
          <div className="flex items-center gap-3">
            <span
              aria-hidden="true"
              className="flex h-9 w-9 items-center justify-center rounded-full bg-[color:var(--surface-brand)] font-mono text-[12px] font-semibold tabular-nums text-[color:var(--text-inverse)]"
            >
              {step.id}
            </span>
            <p className="cw-eyebrow text-[color:var(--text-teal)]">
              {step.eyebrow}
            </p>
          </div>
          <h3 className="mt-3 max-w-[44ch] text-[22px] font-semibold leading-tight tracking-tight text-[color:var(--text-primary)]">
            {step.title}
          </h3>
          <p className="mt-2 max-w-[58ch] text-[14px] leading-[1.65] text-[color:var(--text-secondary)]">
            {step.body}
          </p>
        </div>
      </div>

      {/* Screenshot stage — browser chrome + image */}
      <motion.div
        ref={screenRef}
        className="relative overflow-hidden rounded-[1.25rem] border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-[0_36px_80px_-40px_hsl(var(--brand-navy)/0.30),0_12px_28px_-14px_hsl(var(--brand-navy)/0.12)]"
        initial={reduce ? false : { opacity: 0, y: 22 }}
        whileInView={reduce ? { opacity: 1 } : { opacity: 1, y: 0 }}
        viewport={{ once: true, amount: 0.2 }}
        transition={{ duration: 0.7, ease: EASE_ENTER, delay: 0.05 }}
      >
        <div className="flex items-center gap-2 border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-page)]/70 px-3 py-2">
          <span className="flex gap-1.5" aria-hidden="true">
            <span className="h-2 w-2 rounded-full bg-[color:var(--border-strong)]/80" />
            <span className="h-2 w-2 rounded-full bg-[color:var(--border-strong)]/60" />
            <span className="h-2 w-2 rounded-full bg-[color:var(--border-strong)]/40" />
          </span>
          <span className="ml-2 truncate font-mono text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-tertiary)]">
            {step.caption}
          </span>
          <span className="ml-auto inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--text-teal)]">
            <span className="cw-pulse-soft inline-block h-1.5 w-1.5 rounded-full bg-[color:var(--text-teal)]" />
            En vivo
          </span>
        </div>
        <div className="relative aspect-[16/10] overflow-hidden">
          <motion.div
            className="absolute inset-0"
            style={reduce ? undefined : { y: innerY, willChange: "transform" }}
          >
            <Image
              src={step.image}
              alt={step.imageAlt}
              width={1440}
              height={900}
              className="block h-full w-full object-cover"
              style={{ objectPosition: step.objectPosition ?? "center top" }}
              sizes="(min-width: 1024px) 60vw, 92vw"
              priority={idx === 0}
              loading={idx <= 1 ? "eager" : "lazy"}
            />
          </motion.div>
        </div>
      </motion.div>

      {/* Mobile caption strip — below the stage */}
      <div className="mt-4 lg:hidden">
        <StepCaption step={step} />
      </div>

      {/* Connector — visible on mobile only, threads between stages */}
      {!isLast ? (
        <div
          aria-hidden="true"
          className="mx-auto mt-8 h-10 w-px bg-[color:var(--border-default)] lg:hidden"
        />
      ) : null}
    </div>
  );
}
