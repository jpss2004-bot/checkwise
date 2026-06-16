"use client";

import { useEffect, useRef, useState } from "react";
import { animate, motion, useInView, useReducedMotion } from "motion/react";

/**
 * Animated semáforo dashboard — the hero's signature motif.
 *
 * A bespoke, live version of the client portfolio view: a count-up
 * compliance donut, staggered provider rows, and a pulsing red "En riesgo"
 * dot (#hero-risk-dot) that the scroll-travel seam will zoom into on the
 * way to Stakes. Honors prefers-reduced-motion (static final state).
 */

const EASE = [0.16, 1, 0.3, 1] as const;

const ROWS = [
  { name: "Servicios Aurora", tone: "v", status: "Al día" },
  { name: "Constructora Pacífico", tone: "v", status: "Al día" },
  { name: "Logística del Bajío", tone: "a", status: "Vence en 9 días" },
  { name: "Mantenimiento GMX", tone: "a", status: "2 faltantes" },
  { name: "Transportes Núñez", tone: "r", status: "En riesgo" },
] as const;

const DOT: Record<string, string> = {
  v: "hsl(var(--teal-500))",
  a: "hsl(var(--amber-500))",
  r: "hsl(var(--red-500))",
};

export function HeroSemaforo() {
  const reduced = useReducedMotion();
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.5 });

  return (
    <div ref={ref} className="relative">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -inset-10 -z-10 opacity-70 [background:radial-gradient(60%_55%_at_70%_28%,hsl(var(--teal-500)/0.12),transparent_70%)]"
      />
      <div className="overflow-hidden rounded-[18px] border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-[0_38px_90px_-44px_hsl(var(--brand-navy)/0.45),0_14px_28px_-18px_hsl(var(--brand-navy)/0.18)]">
        {/* chrome bar */}
        <div className="flex items-center gap-2 border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-page)]/88 px-3.5 py-2.5">
          <span className="flex gap-1.5" aria-hidden="true">
            <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--border-strong)]/70" />
            <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--border-strong)]/45" />
            <span className="h-1.5 w-1.5 rounded-full bg-[color:var(--border-strong)]/30" />
          </span>
          <span className="ml-1 truncate font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-secondary)]">
            Vista cliente · resumen del portafolio
          </span>
          <span className="ml-auto inline-flex shrink-0 items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-teal)]">
            <span className="cw-pulse-soft inline-block h-1.5 w-1.5 rounded-full bg-[color:var(--text-teal)]" />
            Vista en vivo
          </span>
        </div>

        {/* body */}
        <div className="grid grid-cols-[auto_1fr] items-center gap-6 p-5 sm:p-7">
          <Donut inView={inView} reduced={!!reduced} />
          <ul className="flex min-w-0 flex-col gap-2.5">
            {ROWS.map((r, i) => (
              <motion.li
                key={r.name}
                initial={reduced ? false : { opacity: 0, x: 12 }}
                animate={inView || reduced ? { opacity: 1, x: 0 } : undefined}
                transition={{
                  duration: 0.4,
                  ease: EASE,
                  delay: reduced ? 0 : 0.2 + i * 0.08,
                }}
                className="flex items-center gap-2.5 text-[13px]"
              >
                <span className="relative flex h-2.5 w-2.5 shrink-0 items-center justify-center">
                  {r.tone === "r" && !reduced ? (
                    <span
                      id="hero-risk-dot"
                      className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-60"
                      style={{ backgroundColor: DOT[r.tone] }}
                    />
                  ) : null}
                  <span
                    className="relative inline-flex h-2.5 w-2.5 rounded-full"
                    style={{ backgroundColor: DOT[r.tone] }}
                  />
                </span>
                <span className="truncate font-medium text-[color:var(--text-primary)]">
                  {r.name}
                </span>
                <span className="ml-auto shrink-0 text-[11.5px] text-[color:var(--text-secondary)]">
                  {r.status}
                </span>
              </motion.li>
            ))}
          </ul>
        </div>

        {/* footer */}
        <div className="flex flex-wrap gap-2 border-t border-[color:var(--border-subtle)] px-5 py-3.5 sm:px-7">
          <span className="inline-flex items-center gap-2 rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-page)] px-2.5 py-1.5 text-[11.5px] font-medium text-[color:var(--text-primary)]">
            <span
              className="cw-pulse-soft h-2 w-2 rounded-full"
              style={{ backgroundColor: DOT.a }}
            />
            Próximo vencimiento · ICSOE 30 jun
          </span>
          <span className="inline-flex items-center rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-page)] px-2.5 py-1.5 text-[11.5px] font-medium text-[color:var(--text-secondary)]">
            3 documentos por revisar
          </span>
        </div>
      </div>
    </div>
  );
}

function Donut({ inView, reduced }: { inView: boolean; reduced: boolean }) {
  const [pct, setPct] = useState(reduced ? 78 : 0);

  useEffect(() => {
    if (reduced || !inView) return;
    const controls = animate(0, 78, {
      duration: 1.1,
      ease: EASE,
      onUpdate: (v) => setPct(Math.round(v)),
    });
    return () => controls.stop();
  }, [inView, reduced]);

  return (
    <div
      className="relative grid h-[124px] w-[124px] place-items-center rounded-full"
      style={{
        background:
          "conic-gradient(hsl(var(--teal-500)) 0 78%, hsl(var(--amber-500)) 78% 90%, hsl(var(--red-500)) 90% 100%)",
      }}
    >
      <div className="absolute h-[92px] w-[92px] rounded-full bg-[color:var(--surface-raised)]" />
      <div className="relative text-center">
        <div className="font-display text-[24px] font-bold tabular-nums text-[color:var(--text-primary)]">
          {pct}%
        </div>
        <div className="text-[10px] text-[color:var(--text-secondary)]">al día</div>
      </div>
    </div>
  );
}
