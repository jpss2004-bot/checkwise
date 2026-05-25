"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import {
  AnimatePresence,
  motion,
  useMotionValueEvent,
  useScroll,
} from "motion/react";
import {
  Archive,
  ChartLineUp,
  ClipboardText,
  Gavel,
  type Icon,
} from "@phosphor-icons/react";

import { EASE_ENTER, Reveal } from "./motion-helpers";
import { useMotionPreference } from "./motion-preference";

/**
 * Journey — four acts of the REPSE workflow.
 *
 * The previous version walked through seven nearly-identical steps with a
 * scroll-snapped column of screenshots; that's the dump pattern the
 * critique called out. This version compresses the story to four acts and
 * uses a sticky cinema stage: the right column shows ONE screen at a time,
 * crossfading as scroll progresses through the section.
 *
 * Each act answers three questions: who uses it, what they do, what
 * evidence is produced.
 */

type Act = {
  id: number;
  eyebrow: string;
  title: string;
  who: string;
  doing: string;
  evidence: string;
  icon: Icon;
  image: string;
  chrome: string;
};

const ACTS: ReadonlyArray<Act> = [
  {
    id: 1,
    eyebrow: "Acto 01 · Acceso",
    title: "El proveedor entra a su expediente",
    who: "Proveedor REPSE",
    doing: "Confirma identidad, contacto y consentimiento legal",
    evidence: "Workspace firmado y trazable",
    icon: ClipboardText,
    image: "/marketing/product/portal-dashboard.png",
    chrome: "Portal proveedor · dashboard",
  },
  {
    id: 2,
    eyebrow: "Acto 02 · Carga",
    title: "Evidencia con contexto regulatorio",
    who: "Proveedor con copilot Wise",
    doing: "Sube requisito, periodo, institución y archivo en un solo flujo",
    evidence: "Documento ligado a cliente, periodo e institución",
    icon: Archive,
    image: "/marketing/product/portal-upload.png",
    chrome: "Carga documental · intake guiado",
  },
  {
    id: 3,
    eyebrow: "Acto 03 · Decisión",
    title: "Legal Shelf decide en cola priorizada",
    who: "Ada Reyes · revisión humana",
    doing: "Aprueba, rechaza, pide aclaración o registra excepción legal",
    evidence: "Registro firmado con actor, acción y cambio",
    icon: Gavel,
    image: "/marketing/product/admin-audit-log.png",
    chrome: "Registro de auditoría · actor · acción · entidad",
  },
  {
    id: 4,
    eyebrow: "Acto 04 · Reporte",
    title: "Reporte ejecutivo y paquete para auditor",
    who: "Cliente o auditor externo",
    doing: "Genera el reporte con copilot LLM o arma el ZIP filtrado",
    evidence: "PDF, Excel, HTML, ZIP con índice firmado",
    icon: ChartLineUp,
    image: "/marketing/product/admin-report-editor.png",
    chrome: "Editor de reportes · generación asistida",
  },
];

export function JourneySection() {
  const { reduced: reduce } = useMotionPreference();
  const sectionRef = useRef<HTMLDivElement | null>(null);
  const [active, setActive] = useState(0);

  const { scrollYProgress } = useScroll({
    target: sectionRef,
    offset: ["start 70%", "end 30%"],
  });

  useMotionValueEvent(scrollYProgress, "change", (latest) => {
    const idx = Math.min(ACTS.length - 1, Math.max(0, Math.floor(latest * ACTS.length)));
    if (idx !== active) setActive(idx);
  });

  // Reduced-motion friendly: cycle the active act on a timer.
  useEffect(() => {
    if (!reduce) return;
    const id = window.setInterval(() => {
      setActive((i) => (i + 1) % ACTS.length);
    }, 6000);
    return () => window.clearInterval(id);
  }, [reduce]);

  return (
    <section
      id="producto"
      ref={sectionRef}
      className="relative isolate border-y border-[color:var(--border-subtle)] bg-[color:var(--surface-page)]"
    >
      {/* Quiet texture, masked to the top so the band has its own surface. */}
      <div
        aria-hidden="true"
        className="cw-grid-pattern pointer-events-none absolute inset-x-0 top-0 -z-10 h-[40%] opacity-[0.55]"
      />

      <div className="mx-auto max-w-[1320px] px-5 py-24 lg:py-28">
        <Reveal className="max-w-3xl">
          <p className="cw-eyebrow text-[color:var(--text-teal)]">
            Cómo funciona
          </p>
          <h2
            className="mt-3 font-semibold tracking-[-0.022em] text-[color:var(--text-primary)] [text-wrap:balance]"
            style={{ fontSize: "clamp(1.85rem, 2.9vw, 2.55rem)", lineHeight: 1.06 }}
          >
            Del calendario al reporte ejecutivo, sobre el mismo expediente.
          </h2>
        </Reveal>

        <div className="mt-14 grid grid-cols-1 gap-12 lg:mt-16 lg:grid-cols-[minmax(0,360px)_minmax(0,1fr)] lg:gap-16">
          {/* Sticky narrative rail. */}
          <div className="lg:sticky lg:top-24 lg:self-start">
            <div className="space-y-1.5">
              {ACTS.map((act, i) => {
                const isActive = i === active;
                const Icon = act.icon;
                return (
                  <button
                    key={act.id}
                    type="button"
                    onClick={() => {
                      // Scroll into the act's own anchor so the user lands
                      // mid-section. Manual override.
                      const el = document.getElementById(`act-${act.id}`);
                      el?.scrollIntoView({
                        behavior: reduce ? "auto" : "smooth",
                        block: "center",
                      });
                    }}
                    aria-current={isActive ? "step" : undefined}
                    className={`group block w-full rounded-[10px] border px-4 py-3.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]/40 ${
                      isActive
                        ? "border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-[0_18px_38px_-30px_hsl(var(--brand-navy)/0.4)]"
                        : "border-transparent hover:bg-[color:var(--surface-raised)]"
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <span
                        aria-hidden="true"
                        className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-md transition-colors ${
                          isActive
                            ? "bg-[color:var(--surface-brand)] text-[color:var(--text-inverse)]"
                            : "bg-[color:var(--surface-teal-muted)] text-[color:var(--text-teal)]"
                        }`}
                      >
                        <Icon className="h-4 w-4" weight="duotone" />
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-tertiary)]">
                          {act.eyebrow}
                        </p>
                        <p
                          className={`mt-0.5 text-[14.5px] font-semibold leading-tight transition-colors ${
                            isActive
                              ? "text-[color:var(--text-primary)]"
                              : "text-[color:var(--text-secondary)] group-hover:text-[color:var(--text-primary)]"
                          }`}
                        >
                          {act.title}
                        </p>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>

            {/* Progress meter — links visual scrolling progress to the rail. */}
            <div className="mt-5 ml-1 mr-4 h-px overflow-hidden bg-[color:var(--border-subtle)]">
              <motion.div
                className="h-full origin-left bg-[color:var(--text-teal)]"
                style={
                  reduce
                    ? { transform: `scaleX(${(active + 1) / ACTS.length})` }
                    : { scaleX: scrollYProgress, willChange: "transform" }
                }
              />
            </div>
            <p className="mt-3 ml-1 font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-tertiary)]">
              Acto{" "}
              <span className="font-semibold tabular-nums text-[color:var(--text-secondary)]">
                {String(active + 1).padStart(2, "0")}
              </span>{" "}
              / {String(ACTS.length).padStart(2, "0")}
            </p>
          </div>

          {/* Cinema stage — a single sticky screen crossfades as the user
              scrolls through act anchors. */}
          <div className="relative">
            {/* Anchors for scroll-into-view from the rail. */}
            <div className="absolute inset-x-0 top-0 -z-10">
              {ACTS.map((act, i) => (
                <div
                  key={act.id}
                  id={`act-${act.id}`}
                  style={{
                    position: "absolute",
                    top: `${(i * 100) / ACTS.length}%`,
                    width: 1,
                    height: 1,
                  }}
                />
              ))}
            </div>

            <div className="sticky top-28">
              <div className="relative overflow-hidden rounded-[14px] border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-[0_44px_120px_-44px_hsl(var(--brand-navy)/0.42),0_14px_28px_-18px_hsl(var(--brand-navy)/0.16)]">
                <div className="flex items-center gap-2 border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-page)]/85 px-3 py-2">
                  <span className="flex gap-1.5" aria-hidden="true">
                    <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--border-strong)]/70" />
                    <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--border-strong)]/45" />
                    <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--border-strong)]/30" />
                  </span>
                  <AnimatePresence mode="wait">
                    <motion.span
                      key={`chrome-${active}`}
                      initial={reduce ? false : { opacity: 0, x: -4 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={reduce ? { opacity: 0 } : { opacity: 0, x: 4 }}
                      transition={{ duration: 0.25, ease: EASE_ENTER }}
                      className="ml-1 truncate font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-tertiary)]"
                    >
                      {ACTS[active].chrome}
                    </motion.span>
                  </AnimatePresence>
                  <span className="ml-auto inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-teal)]">
                    <span className="cw-pulse-soft inline-block h-1.5 w-1.5 rounded-full bg-[color:var(--text-teal)]" />
                    En vivo
                  </span>
                </div>
                <div className="relative aspect-[16/9.4] w-full overflow-hidden">
                  <AnimatePresence mode="wait">
                    <motion.div
                      key={`shot-${active}`}
                      className="absolute inset-0"
                      initial={reduce ? false : { opacity: 0, scale: 1.015 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.995 }}
                      transition={{ duration: 0.4, ease: EASE_ENTER }}
                    >
                      <Image
                        src={ACTS[active].image}
                        alt={`Captura de CheckWise · ${ACTS[active].title}`}
                        fill
                        sizes="(min-width: 1024px) 60vw, 92vw"
                        className="object-cover object-top"
                        priority={active === 0}
                      />
                    </motion.div>
                  </AnimatePresence>
                </div>
              </div>

              {/* Three-line story strip below the stage. */}
              <AnimatePresence mode="wait">
                <motion.dl
                  key={`story-${active}`}
                  initial={reduce ? false : { opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={reduce ? { opacity: 0 } : { opacity: 0, y: -3 }}
                  transition={{ duration: 0.28, ease: EASE_ENTER }}
                  className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-3"
                >
                  <StoryItem label="Quién" value={ACTS[active].who} />
                  <StoryItem label="Qué hace" value={ACTS[active].doing} />
                  <StoryItem label="Evidencia" value={ACTS[active].evidence} />
                </motion.dl>
              </AnimatePresence>
            </div>

            {/* Spacer creates the scroll budget per act so the sticky stage
                can crossfade through all four acts. Tightened from 70vh
                to 38vh per act so the section doesn't dominate page
                rhythm. */}
            <div
              aria-hidden="true"
              style={{ height: `${ACTS.length * 38}vh` }}
            />
          </div>
        </div>
      </div>
    </section>
  );
}

function StoryItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="border-t border-[color:var(--border-subtle)] pt-3">
      <dt className="font-mono text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-tertiary)]">
        {label}
      </dt>
      <dd className="mt-1.5 text-[13.5px] leading-[1.5] text-[color:var(--text-primary)]">
        {value}
      </dd>
    </div>
  );
}
