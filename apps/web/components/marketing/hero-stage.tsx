"use client";

import Image from "next/image";
import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "motion/react";
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
  /**
   * Focal-point zoom applied when this layer is the front (active).
   * - ``zoom``: CSS scale value (1 = no zoom, 1.2 = 20 % closer)
   * - ``originX``/``originY``: CSS background-style position, in %.
   *
   * The Frame component honors these to highlight the screenshot's
   * single most insightful element. Back-stack layers stay at zoom 1.
   */
  focus: { zoom: number; originX: string; originY: string };
};

const LAYERS: Layer[] = [
  {
    id: "provider",
    src: "/marketing/product/portal-dashboard.png",
    alt: "Vista del proveedor con cumplimiento, próximas acciones y asistente Wise.",
    icon: ClipboardText,
    chrome: "Vista del proveedor",
    caption: "Servicios Especializados Aurora · expediente activo",
    chip: { label: "Siguiente acción", value: "Corregir declaración IVA" },
    // Zoom to the right-hand "Tu siguiente acción" card so the buyer
    // immediately sees the actionable next-step pattern.
    focus: { zoom: 1.15, originX: "68%", originY: "30%" },
  },
  {
    id: "review",
    src: "/marketing/product/admin-audit-log.png",
    alt: "Registro de auditoría firmado con actor, acción y entidad.",
    icon: Gavel,
    chrome: "Registro de auditoría",
    caption: "Eventos firmados · actor · acción · entidad",
    chip: { label: "Decisión humana", value: "Ada Reyes · firmada" },
    // Zoom to the table rows where actor/action/entity columns live.
    focus: { zoom: 1.18, originX: "50%", originY: "55%" },
  },
  {
    id: "client",
    src: "/marketing/product/client-dashboard.png",
    alt: "Vista cliente con portafolio en semáforo y faltantes obligatorios.",
    icon: Buildings,
    chrome: "Vista del cliente",
    caption: "Portafolio Operadora Multinacional · 3 proveedores",
    chip: { label: "Faltantes", value: "387 obligatorios" },
    // Zoom to the "Tienes 3 proveedores en rojo" + 387 faltantes card.
    focus: { zoom: 1.15, originX: "50%", originY: "28%" },
  },
  {
    id: "report",
    src: "/marketing/product/admin-report-editor.png",
    alt: "Editor de reportes con asistente, exportación PDF, Excel y HTML.",
    icon: Sparkle,
    chrome: "Reporte ejecutivo",
    caption: "Versión publicada · lista para compartir",
    chip: { label: "Asistente de reportes", value: "Generar · Refrescar · Exportar" },
    // Zoom to the action toolbar ("Generar con IA · Copiloto · ...").
    focus: { zoom: 1.18, originX: "50%", originY: "22%" },
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
        <div className="absolute right-[2%] top-1/2 h-[74%] w-[52%] -translate-y-1/2 xl:right-[3%] xl:w-[50%]">
          {LAYERS.map((layer, i) => {
            const depth = stackIndex(i); // 0 = front
            const settled = depth === 0;
            // Fanned arrangement: each layer behind the front sits a bit
            // higher, a touch smaller, slightly rotated, and progressively
            // softened by blur. Back layers are heavily dimmed so the
            // front screen owns the eye; they remain clickable affordances
            // for the visitor who wants to bring one forward.
            const offsets = [
              { x: 0, y: 0, scale: 1, rot: 0, blur: 0, opacity: 1 },
              { x: -48, y: -34, scale: 0.94, rot: -2.4, blur: 6, opacity: 0.55 },
              { x: -88, y: -62, scale: 0.88, rot: -4.2, blur: 10, opacity: 0.35 },
              { x: -120, y: -86, scale: 0.83, rot: -5.6, blur: 14, opacity: 0.2 },
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
      <div className="relative aspect-[16/9.4] w-full overflow-hidden">
        <div
          className="absolute inset-0 transition-transform duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]"
          style={
            active
              ? {
                  transform: `scale(${layer.focus.zoom})`,
                  transformOrigin: `${layer.focus.originX} ${layer.focus.originY}`,
                }
              : { transform: "scale(1)", transformOrigin: "center top" }
          }
        >
          <Image
            src={layer.src}
            alt={layer.alt}
            fill
            priority={priority}
            sizes="(min-width: 1280px) 56vw, 70vw"
            className="object-cover object-top"
          />
        </div>

        {/* Focal-point chip — sits ON the active layer (not next to it)
            so the takeaway reads as part of the system surface. Only
            renders on active layers; back-stack layers stay clean. */}
        {active ? <FocalChip layer={layer} /> : null}
      </div>
    </div>
  );
}

function FocalChip({ layer }: { layer: Layer }) {
  // Each layer places its focal chip somewhere that mirrors the
  // focal-area zoom: provider's "siguiente acción" is on the right, so
  // the chip sits in the right area; the audit log's actor column is
  // mid-frame, so the chip sits lower-left, etc.
  const positions: Record<string, string> = {
    provider: "right-3 top-[58%] -translate-y-1/2",
    review: "left-3 bottom-3",
    client: "right-3 top-3",
    report: "left-3 bottom-3",
  };
  const Icon = layer.icon;
  return (
    <motion.div
      initial={{ opacity: 0, y: 6, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.55, ease: EASE_ENTER, delay: 0.35 }}
      className={`pointer-events-none absolute z-10 inline-flex items-center gap-2 rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)]/95 px-3 py-2 shadow-[0_18px_36px_-18px_hsl(var(--brand-navy)/0.45)] backdrop-blur-sm ${positions[layer.id] ?? "right-3 top-3"}`}
    >
      <span
        aria-hidden="true"
        className="flex h-6 w-6 items-center justify-center rounded-md bg-[color:var(--surface-teal-muted)] text-[color:var(--text-teal)]"
      >
        <Icon className="h-3 w-3" weight="duotone" />
      </span>
      <div className="min-w-0">
        <p className="font-mono text-[9px] uppercase tracking-[0.18em] text-[color:var(--text-tertiary)]">
          {layer.chip.label}
        </p>
        <p className="text-[12px] font-semibold leading-snug text-[color:var(--text-primary)]">
          {layer.chip.value}
        </p>
      </div>
    </motion.div>
  );
}
