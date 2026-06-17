"use client";

import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent, PointerEvent as ReactPointerEvent } from "react";
import { AnimatePresence, animate, motion } from "motion/react";
import { ArrowUp, FileText, SealCheck } from "@phosphor-icons/react/dist/ssr";

import { cn } from "@/lib/utils";

/**
 * Playable expediente — the hero's signature interaction.
 *
 * The portfolio card is a playable demo of the whole loop. Three providers
 * start out of compliance; the visitor clears a queue of pending documents
 * one by one (drag each onto its provider, or tap it). Each runs the real
 * loop in ~1.5s — detecta → la IA valida → revisión humana → "Al día" — the
 * provider flips amber/red→green and the compliance donut climbs 78%→100%,
 * ending on an all-green "Portafolio al día" finale.
 *
 * This is the front plane; the 3D semáforo ring (hero-semaforo-3d) stays the
 * back plane. Drag uses pointer events (mouse + touch) with tap and keyboard
 * fallbacks. Under reduced motion the drag is disabled and the doc becomes a
 * tap-to-validate button that resolves instantly — still playable, no motion.
 */

const EASE = [0.16, 1, 0.3, 1] as const;

type Phase = "idle" | "dragging" | "validating" | "signing";
type Tone = "v" | "a" | "r";

const DOT: Record<Tone, string> = {
  v: "hsl(var(--teal-500))",
  a: "hsl(var(--amber-500))",
  r: "hsl(var(--red-500))",
};

type Provider = { name: string; tone: Tone; status: string; doc?: string };

const PROVIDERS: Provider[] = [
  { name: "Servicios Aurora", tone: "v", status: "Al día" },
  { name: "Constructora Pacífico", tone: "v", status: "Al día" },
  { name: "Logística del Bajío", tone: "a", status: "Vence en 9 días", doc: "Acuse de REPSE" },
  { name: "Mantenimiento GMX", tone: "a", status: "2 faltantes", doc: "Constancia de situación fiscal" },
  { name: "Transportes Núñez", tone: "r", status: "En riesgo", doc: "Opinión de cumplimiento" },
];

// Resolution order (provider indices): the at-risk one first, then the two
// expiring. resolvedCount tells us how many of these are already cleared.
const QUEUE = [4, 3, 2] as const;
// Compliance donut % after 0/1/2/3 resolutions.
const DONUT = [78, 86, 93, 100] as const;

const donutGradient = (pct: number) =>
  `conic-gradient(hsl(var(--teal-500)) 0 ${pct}%, hsl(var(--brand-navy)/0.1) ${pct}% 100%)`;

export function PlayableExpediente({
  reduced,
  inView,
  onDraggingChange,
}: {
  reduced: boolean;
  inView: boolean;
  onDraggingChange?: (dragging: boolean) => void;
}) {
  const [resolvedCount, setResolvedCount] = useState(0);
  const [phase, setPhase] = useState<Phase>("idle");
  const [drag, setDrag] = useState<{ x: number; y: number } | null>(null);
  const [over, setOver] = useState(false);
  const [pct, setPct] = useState(0);

  const targetRef = useRef<HTMLLIElement>(null);
  const docRef = useRef<HTMLButtonElement>(null);
  const startRef = useRef({ px: 0, py: 0 });
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const pctRef = useRef(0);

  const allDone = resolvedCount >= QUEUE.length;
  const activeIdx = allDone ? -1 : QUEUE[resolvedCount];
  const active = activeIdx >= 0 ? PROVIDERS[activeIdx] : null;

  const clearTimers = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  };
  useEffect(() => () => clearTimers(), []);

  // Donut climbs to the stage for the current resolved count: 0→78 on first
  // reveal, then 78→86→93→100 as each provider is cleared.
  useEffect(() => {
    if (resolvedCount === 0 && !inView) return;
    const target = DONUT[resolvedCount];
    if (reduced) {
      pctRef.current = target;
      setPct(target);
      return;
    }
    const controls = animate(pctRef.current, target, {
      duration: 0.9,
      ease: EASE,
      onUpdate: (v) => {
        pctRef.current = v;
        setPct(Math.round(v));
      },
    });
    return () => controls.stop();
  }, [resolvedCount, inView, reduced]);

  const isOver = (x: number, y: number) => {
    const r = targetRef.current?.getBoundingClientRect();
    return !!r && x >= r.left && x <= r.right && y >= r.top && y <= r.bottom;
  };

  const runValidate = () => {
    if (phase === "validating" || phase === "signing" || allDone) return;
    clearTimers();
    setOver(false);
    setDrag(null);
    if (reduced) {
      setResolvedCount((c) => c + 1);
      setPhase("idle");
      return;
    }
    setPhase("validating");
    timers.current.push(setTimeout(() => setPhase("signing"), 900));
    timers.current.push(
      setTimeout(() => {
        setResolvedCount((c) => c + 1);
        setPhase("idle");
      }, 1500),
    );
  };

  const reset = () => {
    clearTimers();
    setResolvedCount(0);
    setPhase("idle");
    setDrag(null);
    setOver(false);
    pctRef.current = 0;
    setPct(0);
  };

  const onPointerDown = (e: ReactPointerEvent<HTMLButtonElement>) => {
    if (reduced || phase !== "idle" || allDone) return;
    if (e.pointerType === "mouse" && e.button !== 0) return;
    try {
      docRef.current?.setPointerCapture(e.pointerId);
    } catch {
      // pointer capture is a progressive enhancement; drag still tracks via state
    }
    startRef.current = { px: e.clientX, py: e.clientY };
    setPhase("dragging");
    onDraggingChange?.(true);
    setDrag({ x: 0, y: 0 });
  };
  const onPointerMove = (e: ReactPointerEvent<HTMLButtonElement>) => {
    if (phase !== "dragging") return;
    setDrag({ x: e.clientX - startRef.current.px, y: e.clientY - startRef.current.py });
    setOver(isOver(e.clientX, e.clientY));
  };
  const onPointerUp = (e: ReactPointerEvent<HTMLButtonElement>) => {
    if (phase !== "dragging") return;
    onDraggingChange?.(false);
    const moved =
      Math.hypot(e.clientX - startRef.current.px, e.clientY - startRef.current.py) > 6;
    if (!moved || isOver(e.clientX, e.clientY)) runValidate();
    else {
      setDrag(null);
      setOver(false);
      setPhase("idle");
    }
  };
  const onKeyDown = (e: KeyboardEvent<HTMLButtonElement>) => {
    if ((e.key === "Enter" || e.key === " ") && phase === "idle" && !allDone) {
      e.preventDefault();
      runValidate();
    }
  };

  // Per-row display given how many are resolved + the active doc's phase.
  function rowView(i: number): { tone: Tone; status: string; sealed: boolean; active: boolean } {
    const qpos = QUEUE.indexOf(i as (typeof QUEUE)[number]);
    if (qpos === -1) return { tone: PROVIDERS[i].tone, status: PROVIDERS[i].status, sealed: false, active: false };
    if (qpos < resolvedCount) return { tone: "v", status: "Al día", sealed: true, active: false };
    const isActive = i === activeIdx;
    if (isActive && phase === "validating") return { tone: "a", status: "Validando con IA…", sealed: false, active: true };
    if (isActive && phase === "signing") return { tone: "a", status: "Revisión humana…", sealed: true, active: true };
    return { tone: PROVIDERS[i].tone, status: PROVIDERS[i].status, sealed: false, active: isActive };
  }

  return (
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
        <Donut pct={pct} allDone={allDone} reduced={reduced} />
        <ul className="flex min-w-0 flex-col gap-2">
          {PROVIDERS.map((p, i) => {
            const v = rowView(i);
            return (
              <motion.li
                key={p.name}
                ref={i === activeIdx ? targetRef : undefined}
                initial={reduced ? false : { opacity: 0, x: 12 }}
                animate={inView || reduced ? { opacity: 1, x: 0 } : undefined}
                transition={{ duration: 0.4, ease: EASE, delay: reduced ? 0 : 0.2 + i * 0.07 }}
                className={cn(
                  "relative flex items-center gap-2.5 overflow-hidden rounded-md px-1.5 py-1 text-[13px] transition-[box-shadow,background-color] duration-200",
                  over && v.active
                    ? "bg-[hsl(var(--teal-500)/0.08)] shadow-[inset_0_0_0_1.5px_hsl(var(--teal-500))]"
                    : v.active && !allDone
                      ? v.tone === "r"
                        ? "shadow-[inset_0_0_0_1px_hsl(var(--red-500)/0.4)]"
                        : "shadow-[inset_0_0_0_1px_hsl(var(--amber-500)/0.4)]"
                      : "",
                )}
              >
                <Dot tone={v.tone} ping={v.active && !allDone && (phase === "idle" || phase === "dragging")} riskId={i === 4} />
                <span className="truncate font-medium text-[color:var(--text-primary)]">{p.name}</span>
                <span
                  className={cn(
                    "ml-auto inline-flex shrink-0 items-center gap-1 text-[11.5px]",
                    v.tone === "v" ? "text-[color:var(--text-teal)]" : "text-[color:var(--text-secondary)]",
                  )}
                >
                  {v.sealed && <SealCheck className="h-3.5 w-3.5" weight="fill" aria-hidden="true" />}
                  {v.status}
                </span>

                {v.active && phase === "validating" && !reduced && (
                  <span aria-hidden="true" className="pointer-events-none absolute inset-0">
                    <motion.span
                      className="absolute inset-y-0 w-1/3 bg-[linear-gradient(90deg,transparent,hsl(var(--teal-500)/0.28),transparent)]"
                      initial={{ x: "-130%" }}
                      animate={{ x: "330%" }}
                      transition={{ duration: 0.8, ease: "linear", repeat: 1 }}
                    />
                  </span>
                )}
              </motion.li>
            );
          })}
        </ul>
      </div>

      {/* interaction zone */}
      <div className="flex min-h-[58px] items-center border-t border-[color:var(--border-subtle)] px-5 py-3 sm:px-7">
        <AnimatePresence mode="wait" initial={false}>
          {allDone ? (
            <motion.div
              key="done"
              initial={reduced ? false : { opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, ease: EASE }}
              className="flex w-full items-center gap-2.5"
            >
              <span className="inline-flex items-center gap-2 rounded-lg border border-[hsl(var(--teal-500)/0.35)] bg-[hsl(var(--teal-500)/0.08)] px-2.5 py-1.5 text-[11.5px] font-medium text-[color:var(--text-primary)]">
                <SealCheck className="h-4 w-4 text-[color:var(--text-teal)]" weight="fill" aria-hidden="true" />
                Portafolio al día · 0 proveedores en riesgo
              </span>
              <button
                type="button"
                onClick={reset}
                className="ml-auto shrink-0 rounded-md px-2 py-1 font-mono text-[10.5px] uppercase tracking-[0.14em] text-[color:var(--text-secondary)] transition-colors hover:text-[color:var(--text-primary)]"
              >
                Reiniciar
              </button>
            </motion.div>
          ) : phase === "validating" || phase === "signing" ? (
            <motion.div
              key="proc"
              initial={reduced ? false : { opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={reduced ? undefined : { opacity: 0 }}
              transition={{ duration: 0.25, ease: EASE }}
              className="flex w-full items-center gap-2 text-[11.5px] text-[color:var(--text-secondary)]"
            >
              <span className="cw-pulse-soft h-2 w-2 rounded-full bg-[color:var(--text-teal)]" />
              {phase === "signing" ? "Firmando revisión humana…" : "La IA está validando el documento…"}
            </motion.div>
          ) : (
            <motion.div
              key="doc"
              initial={false}
              animate={{ opacity: 1 }}
              exit={reduced ? undefined : { opacity: 0 }}
              className="flex w-full items-center gap-3"
            >
              <button
                ref={docRef}
                type="button"
                onPointerDown={reduced ? undefined : onPointerDown}
                onPointerMove={reduced ? undefined : onPointerMove}
                onPointerUp={reduced ? undefined : onPointerUp}
                onClick={reduced ? runValidate : undefined}
                onKeyDown={onKeyDown}
                aria-label={`Validar el documento pendiente de ${active?.name ?? ""}`}
                style={{
                  transform: drag ? `translate(${drag.x}px, ${drag.y}px)` : undefined,
                  touchAction: "none",
                }}
                className={cn(
                  "relative inline-flex min-w-0 select-none items-center gap-2 rounded-lg border px-2.5 py-1.5 text-[11.5px] font-medium text-[color:var(--text-primary)] outline-none",
                  active?.tone === "r"
                    ? "border-[hsl(var(--red-500)/0.45)] bg-[hsl(var(--red-500)/0.08)]"
                    : "border-[hsl(var(--amber-500)/0.5)] bg-[hsl(var(--amber-500)/0.1)]",
                  "focus-visible:shadow-[var(--shadow-focus)]",
                  phase === "dragging"
                    ? "z-50 scale-105 cursor-grabbing shadow-[0_16px_30px_-12px_hsl(var(--brand-navy)/0.5)]"
                    : "cursor-grab transition-transform hover:-translate-y-0.5",
                )}
              >
                <FileText
                  className={active?.tone === "r" ? "h-4 w-4 text-[hsl(var(--red-500))]" : "h-4 w-4 text-[hsl(var(--amber-500))]"}
                  weight="duotone"
                  aria-hidden="true"
                />
                <span className="truncate">{active?.doc}</span>
              </button>

              <span className="inline-flex min-w-0 items-center gap-1.5 text-[11px] text-[color:var(--text-secondary)]">
                {!reduced && (
                  <ArrowUp
                    className="cw-pulse-soft h-3.5 w-3.5 shrink-0 text-[color:var(--text-teal)]"
                    weight="bold"
                    aria-hidden="true"
                  />
                )}
                <span className="truncate">
                  {reduced ? "Toca para validarlo" : `Arrástralo a ${active?.name}`}
                </span>
                <span className="ml-1 shrink-0 font-mono text-[10px] text-[color:var(--text-tertiary)]">
                  {resolvedCount + 1}/{QUEUE.length}
                </span>
              </span>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

function Dot({ tone, ping, riskId }: { tone: Tone; ping?: boolean; riskId?: boolean }) {
  return (
    <span className="relative flex h-2.5 w-2.5 shrink-0 items-center justify-center">
      {ping && (
        <span
          id={riskId ? "hero-risk-dot" : undefined}
          className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-60"
          style={{ backgroundColor: DOT[tone] }}
        />
      )}
      <span
        className="relative inline-flex h-2.5 w-2.5 rounded-full transition-colors duration-500"
        style={{ backgroundColor: DOT[tone] }}
      />
    </span>
  );
}

function Donut({ pct, allDone, reduced }: { pct: number; allDone: boolean; reduced: boolean }) {
  return (
    <div className="relative grid h-[124px] w-[124px] place-items-center rounded-full" style={{ background: donutGradient(pct) }}>
      {/* one-time celebratory ring when the portfolio hits 100% */}
      {allDone && !reduced && (
        <motion.span
          aria-hidden="true"
          className="absolute inset-0 rounded-full"
          style={{ border: "2px solid hsl(var(--teal-500))" }}
          initial={{ scale: 1, opacity: 0.7 }}
          animate={{ scale: 1.35, opacity: 0 }}
          transition={{ duration: 0.9, ease: EASE }}
        />
      )}
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
