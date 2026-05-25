"use client";

import Image from "next/image";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  Buildings,
  ClipboardText,
  Gavel,
  Sparkle,
  type Icon,
} from "@phosphor-icons/react";

import { useMotionPreference } from "./motion-preference";

const EASE_ENTER = [0.16, 1, 0.3, 1] as const;

type Layer = {
  id: string;
  src: string;
  alt: string;
  icon: Icon;
  chrome: string;
  caption: string;
  chip: { label: string; value: string };
};

const LAYERS: Layer[] = [
  {
    id: "provider",
    src: "/marketing/product/portal-dashboard.png",
    alt: "Dashboard del proveedor con cumplimiento, próximas acciones y copilot Wise abierto.",
    icon: ClipboardText,
    chrome: "Portal proveedor",
    caption: "Servicios Especializados Aurora · expediente activo",
    chip: { label: "Siguiente acción", value: "Corregir declaración IVA" },
  },
  {
    id: "review",
    src: "/marketing/product/admin-reviewer-queue.png",
    alt: "Bandeja de Legal Shelf con documentos en cola, edad y estado de revisión.",
    icon: Gavel,
    chrome: "Bandeja Legal Shelf",
    caption: "Documentos por revisar · institución, periodo, proveedor",
    chip: { label: "Decisión humana", value: "Ada Reyes · FIFO" },
  },
  {
    id: "client",
    src: "/marketing/product/client-dashboard.png",
    alt: "Resumen del cliente con portafolio en semáforo y faltantes obligatorios.",
    icon: Buildings,
    chrome: "Portal cliente",
    caption: "Portafolio Operadora Multinacional · 3 proveedores",
    chip: { label: "Faltantes", value: "387 obligatorios" },
  },
  {
    id: "report",
    src: "/marketing/product/admin-report-editor.png",
    alt: "Editor de reportes con copilot, exportación PDF y Excel.",
    icon: Sparkle,
    chrome: "Reportes + copilot LLM",
    caption: "Reporte ejecutivo · versión v2 · listo para compartir",
    chip: { label: "Copilot", value: "Generar · Refrescar · Exportar" },
  },
];

const CYCLE_MS = 4200;

/**
 * Hero stage — layered product cockpit.
 *
 * One screen dominates at the front; the other three recede behind it in a
 * fanned stack with progressively higher blur, lower scale, and a slight
 * angular offset. Every CYCLE_MS the active layer rotates forward; the
 * outgoing front slides into the stack. Hovering the stack pauses the
 * cycle so the viewer can read the active screen.
 *
 * The composition is asymmetric on purpose. The active screen sits to the
 * right of the typographic column and overflows the section edge a touch,
 * so the page reads as "this is the product, the words are framing."
 */
export function HeroStage() {
  const { reduced: reduce } = useMotionPreference();
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);
  const order = useMemo(() => LAYERS.map((_, i) => i), []);

  useEffect(() => {
    if (reduce || paused) return;
    const id = window.setInterval(() => {
      setActive((i) => (i + 1) % LAYERS.length);
    }, CYCLE_MS);
    return () => window.clearInterval(id);
  }, [reduce, paused]);

  const stackIndex = useCallback(
    (i: number) => {
      const n = LAYERS.length;
      return (i - active + n) % n;
    },
    [active],
  );

  return (
    <div
      className="absolute inset-0 -z-10 overflow-hidden"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
    >
      {/* Quiet grid texture, masked to the right half so the typographic
          column stays calm. */}
      <div
        aria-hidden="true"
        className="cw-grid-pattern pointer-events-none absolute inset-y-0 right-0 w-[58%] opacity-[0.55]"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-y-0 left-0 w-[46%] bg-gradient-to-r from-[color:var(--surface-page)] via-[color:var(--surface-page)] to-transparent"
      />

      {/* Desktop stage. Mobile users get the inline mini-screenshot in
          hero-section.tsx instead — saving them from a heavy stage they
          can't read. */}
      <div className="hidden h-full md:block">
        <div className="absolute right-[-4%] top-1/2 h-[78%] w-[58%] -translate-y-1/2 xl:right-[-2%] xl:w-[56%]">
          {LAYERS.map((layer, i) => {
            const depth = stackIndex(i); // 0 = front
            const settled = depth === 0;
            // Fanned arrangement: each layer behind the front sits a bit
            // higher, a touch smaller, slightly rotated, and progressively
            // softened by blur. Values stay tight to keep the composition
            // calm rather than gimmicky.
            const offsets = [
              { x: 0, y: 0, scale: 1, rot: 0, blur: 0, opacity: 1 },
              { x: -54, y: -38, scale: 0.94, rot: -2.4, blur: 4, opacity: 0.85 },
              { x: -98, y: -68, scale: 0.88, rot: -4.2, blur: 8, opacity: 0.6 },
              { x: -132, y: -92, scale: 0.82, rot: -5.6, blur: 12, opacity: 0.38 },
            ];
            const t = offsets[Math.min(depth, offsets.length - 1)];

            return (
              <motion.button
                key={layer.id}
                type="button"
                aria-label={
                  settled
                    ? `${layer.chrome} (vista activa)`
                    : `Mostrar ${layer.chrome}`
                }
                aria-pressed={settled}
                onClick={() => setActive(i)}
                className={`absolute inset-0 origin-center rounded-[14px] text-left transition-shadow focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--text-teal)]/40 focus-visible:ring-offset-2 focus-visible:ring-offset-[color:var(--surface-page)] ${
                  settled ? "cursor-default" : "cursor-pointer"
                }`}
                style={{ zIndex: 100 - depth }}
                initial={false}
                animate={
                  reduce
                    ? { opacity: settled ? 1 : 0.6 }
                    : {
                        x: t.x,
                        y: t.y,
                        scale: t.scale,
                        rotate: t.rot,
                        opacity: t.opacity,
                        filter: `blur(${t.blur}px) saturate(${settled ? 1 : 0.85})`,
                      }
                }
                whileHover={
                  reduce || settled
                    ? undefined
                    : {
                        x: t.x + 14,
                        y: t.y - 4,
                        scale: t.scale + 0.015,
                        opacity: Math.min(1, t.opacity + 0.12),
                        filter: `blur(${Math.max(0, t.blur - 2)}px) saturate(0.95)`,
                      }
                }
                transition={{ duration: 0.55, ease: EASE_ENTER }}
              >
                <Frame layer={layer} active={settled} priority={i === 0} />
              </motion.button>
            );
          })}
        </div>

        {/* Floating context chips — tied to the active layer's chip data
            so the chip content rotates with the cycle. */}
        <AnimatePresence mode="wait">
          <motion.div
            key={`chip-${active}`}
            className="absolute right-[8%] top-[14%] hidden items-center gap-2 rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]/95 px-3 py-2 shadow-[0_18px_44px_-22px_hsl(var(--brand-navy)/0.45)] backdrop-blur-sm lg:inline-flex"
            initial={reduce ? false : { opacity: 0, y: -6 }}
            animate={reduce ? { opacity: 1 } : { opacity: 1, y: 0 }}
            exit={reduce ? { opacity: 0 } : { opacity: 0, y: -4 }}
            transition={{ duration: 0.45, ease: EASE_ENTER }}
          >
            <span
              className="flex h-7 w-7 items-center justify-center rounded-md bg-[color:var(--surface-teal-muted)] text-[color:var(--text-teal)]"
              aria-hidden="true"
            >
              {(() => {
                const I = LAYERS[active].icon;
                return <I className="h-3.5 w-3.5" weight="duotone" />;
              })()}
            </span>
            <div className="min-w-0">
              <p className="font-mono text-[9px] uppercase tracking-[0.18em] text-[color:var(--text-tertiary)]">
                {LAYERS[active].chip.label}
              </p>
              <p className="text-[12.5px] font-semibold leading-snug text-[color:var(--text-primary)]">
                {LAYERS[active].chip.value}
              </p>
            </div>
          </motion.div>
        </AnimatePresence>

        {/* Stage controls — dot rail that doubles as a tap target. */}
        <div className="pointer-events-auto absolute bottom-[6%] right-[8%] hidden items-center gap-2 lg:flex">
          {order.map((i) => {
            const isActive = i === active;
            return (
              <button
                key={i}
                type="button"
                aria-label={`Mostrar ${LAYERS[i].chrome}`}
                onClick={() => setActive(i)}
                className="group relative h-2 w-2 cursor-pointer"
              >
                <span
                  className={`absolute inset-0 rounded-full transition-all duration-300 ${
                    isActive
                      ? "bg-[color:var(--text-teal)] scale-100"
                      : "bg-[color:var(--border-strong)]/60 group-hover:bg-[color:var(--border-strong)] scale-90"
                  }`}
                />
                {isActive ? (
                  <span className="absolute -inset-1.5 rounded-full border border-[color:var(--text-teal)]/40" />
                ) : null}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function Frame({
  layer,
  active,
  priority,
}: {
  layer: Layer;
  active: boolean;
  priority: boolean;
}) {
  return (
    <div
      className={`relative h-full w-full overflow-hidden rounded-[14px] border bg-[color:var(--surface-raised)] transition-shadow duration-500 ${
        active
          ? "border-[color:var(--border-default)] shadow-[0_44px_120px_-44px_hsl(var(--brand-navy)/0.55),0_18px_36px_-22px_hsl(var(--brand-navy)/0.18)]"
          : "border-[color:var(--border-subtle)] shadow-[0_24px_60px_-40px_hsl(var(--brand-navy)/0.4)]"
      }`}
    >
      <div className="flex items-center gap-2 border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-page)]/90 px-3 py-2">
        <span className="flex gap-1.5" aria-hidden="true">
          <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--border-strong)]/70" />
          <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--border-strong)]/45" />
          <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--border-strong)]/30" />
        </span>
        <span className="ml-1 truncate font-mono text-[9px] uppercase tracking-[0.18em] text-[color:var(--text-tertiary)]">
          {layer.chrome}
        </span>
        {active ? (
          <span className="ml-auto inline-flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.16em] text-[color:var(--text-teal)]">
            <span className="cw-pulse-soft inline-block h-1.5 w-1.5 rounded-full bg-[color:var(--text-teal)]" />
            En vivo
          </span>
        ) : null}
      </div>
      <div className="relative aspect-[16/9.4] w-full">
        <Image
          src={layer.src}
          alt={layer.alt}
          fill
          priority={priority}
          sizes="(min-width: 1280px) 56vw, 70vw"
          className="object-cover object-top"
        />
      </div>
    </div>
  );
}
