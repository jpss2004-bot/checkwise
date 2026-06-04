"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  CalendarCheck,
  ChartLineUp,
  ClipboardText,
  Gavel,
  type Icon,
} from "@phosphor-icons/react";

import { EASE_ENTER } from "./motion-helpers";
import { useMotionPreference } from "./motion-preference";
import { ProductShot, type ProductShotFocus } from "./product-shot";

type HeroScene = {
  id: string;
  label: string;
  title: string;
  body: string;
  metric: string;
  metricLabel: string;
  image: string;
  icon: Icon;
  focus: ProductShotFocus;
};

const SCENES: ReadonlyArray<HeroScene> = [
  {
    id: "calendar",
    label: "01 · Calendario REPSE",
    title: "Detecta lo que vence",
    body: "Cada obligación vive ligada a proveedor, institución, requisito y periodo.",
    metric: "151",
    metricLabel: "requisitos sembrados",
    image: "/marketing/generated/cw-hero-operating-loop.png",
    icon: CalendarCheck,
    focus: { zoom: 1, origin: "50% 50%", position: "center" },
  },
  {
    id: "upload",
    label: "02 · Carga guiada",
    title: "Recibe evidencia con contexto",
    body: "El proveedor no sube un archivo suelto: resuelve una obligación específica.",
    metric: "5",
    metricLabel: "pasos de intake",
    image: "/marketing/generated/cw-upload-guided.png",
    icon: ClipboardText,
    focus: { zoom: 1, origin: "50% 50%", position: "center" },
  },
  {
    id: "review",
    label: "03 · Revisión CheckWise",
    title: "Firma decisiones humanas",
    body: "Aprobación, rechazo, aclaración y excepción quedan en auditoría.",
    metric: "4",
    metricLabel: "decisiones canónicas",
    image: "/marketing/generated/cw-review-queue.png",
    icon: Gavel,
    focus: { zoom: 1, origin: "50% 50%", position: "center" },
  },
  {
    id: "reports",
    label: "04 · Reportes AI",
    title: "Convierte estado en reporte",
    body: "El copilot compone bloques editables con datos tenant-scoped.",
    metric: "30",
    metricLabel: "eventos SSE verificados",
    image: "/marketing/generated/cw-report-editor.png",
    icon: ChartLineUp,
    focus: { zoom: 1, origin: "50% 50%", position: "center" },
  },
];

const CYCLE_MS = 4400;

export function HeroStage() {
  const { reduced: reduce } = useMotionPreference();
  const [active, setActive] = useState(0);
  const scene = SCENES[active];

  useEffect(() => {
    if (reduce) return;
    const id = window.setInterval(() => {
      setActive((current) => (current + 1) % SCENES.length);
    }, CYCLE_MS);
    return () => window.clearInterval(id);
  }, [reduce]);

  return (
    <motion.div
      className="relative min-w-0"
      initial={reduce ? false : { opacity: 0, x: 28 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.78, ease: EASE_ENTER, delay: 0.1 }}
    >
      <div className="absolute -inset-8 -z-10 hidden rounded-[32px] border border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)]/40 lg:block" />
      <div
        aria-hidden="true"
        className="cw-grid-pattern pointer-events-none absolute -inset-10 -z-20 opacity-[0.58]"
      />

      <div className="overflow-hidden rounded-[18px] border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-[0_48px_120px_-54px_hsl(var(--brand-navy)/0.62),0_18px_44px_-28px_hsl(var(--brand-navy)/0.24)]">
        <div className="flex items-center gap-3 border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-page)]/92 px-4 py-3">
          <span className="flex gap-1.5" aria-hidden="true">
            <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--border-strong)]/70" />
            <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--border-strong)]/45" />
            <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--border-strong)]/30" />
          </span>
          <span className="truncate font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-tertiary)]">
            CheckWise operating loop
          </span>
          <span className="ml-auto inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-teal)]">
            <span className="cw-pulse-soft h-1.5 w-1.5 rounded-full bg-[color:var(--text-teal)]" />
            Sistema real
          </span>
        </div>

        <div className="grid min-h-[500px] grid-cols-1 lg:grid-cols-[minmax(0,1fr)_260px] xl:grid-cols-[minmax(0,1fr)_300px]">
          <div className="relative min-h-[360px] overflow-hidden border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] lg:border-b-0 lg:border-r">
            <AnimatePresence mode="wait">
              <motion.div
                key={scene.id}
                className="absolute inset-0"
                initial={reduce ? false : { opacity: 0, scale: 1.012 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.992 }}
                transition={{ duration: 0.52, ease: EASE_ENTER }}
              >
                <ProductShot
                  src={scene.image}
                  alt=""
                  priority={active === 0}
                  sizes="(min-width: 1280px) 64vw, (min-width: 1024px) 70vw, 160vw"
                  focus={scene.focus}
                />
              </motion.div>
            </AnimatePresence>
            <div className="pointer-events-none absolute inset-x-0 bottom-0 h-32 bg-gradient-to-t from-[color:var(--surface-raised)] via-[color:var(--surface-raised)]/72 to-transparent" />
            <AnimatePresence mode="wait">
              <motion.div
                key={`caption-${scene.id}`}
                className="absolute bottom-5 left-5 right-5"
                initial={reduce ? false : { opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={reduce ? { opacity: 0 } : { opacity: 0, y: -6 }}
                transition={{ duration: 0.38, ease: EASE_ENTER, delay: 0.12 }}
              >
                <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-tertiary)]">
                  {scene.label}
                </p>
                <p className="mt-1 max-w-[34ch] text-[18px] font-semibold leading-tight text-[color:var(--text-primary)]">
                  {scene.title}
                </p>
              </motion.div>
            </AnimatePresence>
          </div>

          <aside className="flex min-w-0 flex-col bg-[color:var(--surface-raised)]">
            <div className="border-b border-[color:var(--border-subtle)] px-4 py-4">
              <p className="cw-eyebrow text-[color:var(--text-teal)]">
                La operación completa
              </p>
              <p className="mt-2 text-[14px] leading-[1.55] text-[color:var(--text-secondary)]">
                Una misma fuente de verdad para proveedor, cliente y equipo CheckWise.
              </p>
            </div>

            <div className="divide-y divide-[color:var(--border-subtle)]">
              {SCENES.map((item, index) => {
                const Icon = item.icon;
                const selected = index === active;
                return (
                  <button
                    key={item.id}
                    type="button"
                    aria-pressed={selected}
                    onClick={() => setActive(index)}
                    className={`group grid w-full grid-cols-[34px_minmax(0,1fr)] gap-3 px-4 py-3.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]/40 ${
                      selected
                        ? "bg-[color:var(--surface-brand-muted)]"
                        : "hover:bg-[color:var(--surface-page)]"
                    }`}
                  >
                    <span
                      aria-hidden="true"
                      className={`mt-0.5 flex h-8 w-8 items-center justify-center rounded-md transition-colors ${
                        selected
                          ? "bg-[color:var(--surface-brand)] text-[color:var(--text-inverse)]"
                          : "bg-[color:var(--surface-teal-muted)] text-[color:var(--text-teal)]"
                      }`}
                    >
                      <Icon className="h-3.5 w-3.5" weight="duotone" />
                    </span>
                    <span className="min-w-0">
                      <span className="block font-mono text-[9px] uppercase tracking-[0.16em] text-[color:var(--text-tertiary)]">
                        {item.label}
                      </span>
                      <span
                        className={`mt-1 block text-[13px] font-semibold leading-tight transition-colors ${
                          selected
                            ? "text-[color:var(--text-primary)]"
                            : "text-[color:var(--text-secondary)] group-hover:text-[color:var(--text-primary)]"
                        }`}
                      >
                        {item.title}
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>

            <AnimatePresence mode="wait">
              <motion.div
                key={`metric-${scene.id}`}
                className="mt-auto border-t border-[color:var(--border-subtle)] px-4 py-4"
                initial={reduce ? false : { opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={reduce ? { opacity: 0 } : { opacity: 0, y: -4 }}
                transition={{ duration: 0.32, ease: EASE_ENTER }}
              >
                <p className="text-[34px] font-semibold tracking-[-0.03em] text-[color:var(--text-primary)]">
                  {scene.metric}
                </p>
                <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-tertiary)]">
                  {scene.metricLabel}
                </p>
                <p className="mt-3 text-[12.5px] leading-[1.5] text-[color:var(--text-secondary)]">
                  {scene.body}
                </p>
              </motion.div>
            </AnimatePresence>
          </aside>
        </div>
      </div>
    </motion.div>
  );
}
