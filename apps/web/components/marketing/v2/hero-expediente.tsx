"use client";

import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent, PointerEvent as ReactPointerEvent } from "react";
import { AnimatePresence, animate, motion } from "motion/react";
import { ArrowUp, FileText, SealCheck } from "@phosphor-icons/react/dist/ssr";

import { cn } from "@/lib/utils";

/**
 * Playable expediente — the hero's signature interaction.
 *
 * The portfolio card is no longer a passive loop: a pending document sits in
 * the footer and the visitor DRAGS it onto the at-risk provider (or taps it).
 * That plays the real product loop in ~1.6s — detecta → la IA valida →
 * revisión humana → "Al día" — the risky row flips red→green and the
 * compliance donut counts up as the red slice disappears.
 *
 * This is the front plane; the 3D semáforo ring (hero-semaforo-3d) stays the
 * back plane. Drag uses pointer events (mouse + touch) with a tap/keyboard
 * fallback. Under reduced motion the drag is disabled and the doc becomes a
 * "Validar" button that resolves instantly — still playable, no motion.
 */

const EASE = [0.16, 1, 0.3, 1] as const;

type Phase = "idle" | "dragging" | "validating" | "signing" | "done";
type Tone = "v" | "a" | "r";

const DOT: Record<Tone, string> = {
  v: "hsl(var(--teal-500))",
  a: "hsl(var(--amber-500))",
  r: "hsl(var(--red-500))",
};

const ROWS: { name: string; tone: Tone; status: string }[] = [
  { name: "Servicios Aurora", tone: "v", status: "Al día" },
  { name: "Constructora Pacífico", tone: "v", status: "Al día" },
  { name: "Logística del Bajío", tone: "a", status: "Vence en 9 días" },
  { name: "Mantenimiento GMX", tone: "a", status: "2 faltantes" },
];

const TARGET_NAME = "Transportes Núñez";

const donutGradient = (greenEnd: number, amberEnd: number) =>
  `conic-gradient(hsl(var(--teal-500)) 0 ${greenEnd}%, hsl(var(--amber-500)) ${greenEnd}% ${amberEnd}%, hsl(var(--red-500)) ${amberEnd}% 100%)`;

export function PlayableExpediente({
  reduced,
  inView,
  onDraggingChange,
}: {
  reduced: boolean;
  inView: boolean;
  onDraggingChange?: (dragging: boolean) => void;
}) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [drag, setDrag] = useState<{ x: number; y: number } | null>(null);
  const [over, setOver] = useState(false);

  const [pct, setPct] = useState(0);
  const [greenEnd, setGreenEnd] = useState(78);
  const [amberEnd, setAmberEnd] = useState(90);

  const targetRef = useRef<HTMLLIElement>(null);
  const docRef = useRef<HTMLButtonElement>(null);
  const startRef = useRef({ px: 0, py: 0 });
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const introRan = useRef(false);

  const clearTimers = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  };
  useEffect(() => () => clearTimers(), []);

  // Intro count-up 0→78 on first reveal (number only; the ring rests at 78/90).
  useEffect(() => {
    if (introRan.current) return;
    if (reduced) {
      introRan.current = true;
      setPct(78);
      return;
    }
    if (!inView) return;
    introRan.current = true;
    const c = animate(0, 78, {
      duration: 1.1,
      ease: EASE,
      onUpdate: (v) => setPct(Math.round(v)),
    });
    return () => c.stop();
  }, [inView, reduced]);

  // Resolve the donut once the loop completes: green grows to 92, red vanishes.
  useEffect(() => {
    if (phase !== "done") return;
    if (reduced) {
      setPct(92);
      setGreenEnd(92);
      setAmberEnd(100);
      return;
    }
    const c = animate(0, 1, {
      duration: 1,
      ease: EASE,
      onUpdate: (t) => {
        setPct(Math.round(78 + 14 * t));
        setGreenEnd(78 + 14 * t);
        setAmberEnd(90 + 10 * t);
      },
    });
    return () => c.stop();
  }, [phase, reduced]);

  const isOver = (x: number, y: number) => {
    const r = targetRef.current?.getBoundingClientRect();
    return !!r && x >= r.left && x <= r.right && y >= r.top && y <= r.bottom;
  };

  const runValidate = () => {
    if (phase === "validating" || phase === "signing" || phase === "done") return;
    clearTimers();
    setOver(false);
    setDrag(null);
    if (reduced) {
      setPhase("done");
      return;
    }
    setPhase("validating");
    timers.current.push(setTimeout(() => setPhase("signing"), 950));
    timers.current.push(setTimeout(() => setPhase("done"), 1600));
  };

  const reset = () => {
    clearTimers();
    setPhase("idle");
    setDrag(null);
    setOver(false);
    setPct(78);
    setGreenEnd(78);
    setAmberEnd(90);
  };

  const onPointerDown = (e: ReactPointerEvent<HTMLButtonElement>) => {
    if (reduced || phase !== "idle") return;
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
    if ((e.key === "Enter" || e.key === " ") && phase === "idle") {
      e.preventDefault();
      runValidate();
    }
  };

  const targetTone: Tone =
    phase === "done" ? "v" : phase === "validating" || phase === "signing" ? "a" : "r";
  const targetStatus =
    phase === "done"
      ? "Al día"
      : phase === "signing"
        ? "Revisión humana…"
        : phase === "validating"
          ? "Validando con IA…"
          : "En riesgo";

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
        <Donut pct={pct} greenEnd={greenEnd} amberEnd={amberEnd} />
        <ul className="flex min-w-0 flex-col gap-2">
          {ROWS.map((r, i) => (
            <motion.li
              key={r.name}
              initial={reduced ? false : { opacity: 0, x: 12 }}
              animate={inView || reduced ? { opacity: 1, x: 0 } : undefined}
              transition={{ duration: 0.4, ease: EASE, delay: reduced ? 0 : 0.2 + i * 0.08 }}
              className="flex items-center gap-2.5 text-[13px]"
            >
              <Dot tone={r.tone} />
              <span className="truncate font-medium text-[color:var(--text-primary)]">
                {r.name}
              </span>
              <span className="ml-auto shrink-0 text-[11.5px] text-[color:var(--text-secondary)]">
                {r.status}
              </span>
            </motion.li>
          ))}

          {/* interactive target row */}
          <motion.li
            ref={targetRef}
            initial={reduced ? false : { opacity: 0, x: 12 }}
            animate={inView || reduced ? { opacity: 1, x: 0 } : undefined}
            transition={{ duration: 0.4, ease: EASE, delay: reduced ? 0 : 0.2 + ROWS.length * 0.08 }}
            className={cn(
              "relative flex items-center gap-2.5 overflow-hidden rounded-md px-1.5 py-1 text-[13px] transition-[box-shadow,background-color] duration-200",
              over
                ? "bg-[hsl(var(--teal-500)/0.08)] shadow-[inset_0_0_0_1.5px_hsl(var(--teal-500))]"
                : phase === "idle"
                  ? "shadow-[inset_0_0_0_1px_hsl(var(--red-500)/0.35)]"
                  : "",
            )}
          >
            <Dot tone={targetTone} ping={targetTone === "r" && !reduced} riskId />
            <span className="truncate font-medium text-[color:var(--text-primary)]">
              {TARGET_NAME}
            </span>
            <span
              className={cn(
                "ml-auto inline-flex shrink-0 items-center gap-1 text-[11.5px]",
                phase === "done"
                  ? "text-[color:var(--text-teal)]"
                  : phase === "validating" || phase === "signing"
                    ? "text-[color:var(--text-primary)]"
                    : "text-[color:var(--text-secondary)]",
              )}
            >
              {(phase === "signing" || phase === "done") && (
                <SealCheck className="h-3.5 w-3.5" weight="fill" aria-hidden="true" />
              )}
              {targetStatus}
            </span>

            {/* AI scan shimmer while validating */}
            {phase === "validating" && !reduced && (
              <span aria-hidden="true" className="pointer-events-none absolute inset-0">
                <motion.span
                  className="absolute inset-y-0 w-1/3 bg-[linear-gradient(90deg,transparent,hsl(var(--teal-500)/0.28),transparent)]"
                  initial={{ x: "-130%" }}
                  animate={{ x: "330%" }}
                  transition={{ duration: 0.85, ease: "linear", repeat: 1 }}
                />
              </span>
            )}
          </motion.li>
        </ul>
      </div>

      {/* interaction zone */}
      <div className="flex min-h-[58px] items-center border-t border-[color:var(--border-subtle)] px-5 py-3 sm:px-7">
        <AnimatePresence mode="wait" initial={false}>
          {phase === "done" ? (
            <motion.div
              key="done"
              initial={reduced ? false : { opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={reduced ? undefined : { opacity: 0, y: -6 }}
              transition={{ duration: 0.3, ease: EASE }}
              className="flex w-full items-center gap-2.5"
            >
              <span className="inline-flex items-center gap-2 rounded-lg border border-[hsl(var(--teal-500)/0.35)] bg-[hsl(var(--teal-500)/0.08)] px-2.5 py-1.5 text-[11.5px] font-medium text-[color:var(--text-primary)]">
                <SealCheck
                  className="h-4 w-4 text-[color:var(--text-teal)]"
                  weight="fill"
                  aria-hidden="true"
                />
                Expediente actualizado · 1 proveedor regularizado
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
              {phase === "signing"
                ? "Firmando revisión humana…"
                : "La IA está validando el documento…"}
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
                aria-label={`Validar el documento pendiente de ${TARGET_NAME}`}
                style={{
                  transform: drag ? `translate(${drag.x}px, ${drag.y}px)` : undefined,
                  touchAction: "none",
                }}
                className={cn(
                  "relative inline-flex select-none items-center gap-2 rounded-lg border px-2.5 py-1.5 text-[11.5px] font-medium text-[color:var(--text-primary)] outline-none",
                  "border-[hsl(var(--amber-500)/0.5)] bg-[hsl(var(--amber-500)/0.1)]",
                  "focus-visible:shadow-[var(--shadow-focus)]",
                  phase === "dragging"
                    ? "z-50 scale-105 cursor-grabbing shadow-[0_16px_30px_-12px_hsl(var(--brand-navy)/0.5)]"
                    : "cursor-grab transition-transform hover:-translate-y-0.5",
                )}
              >
                <FileText
                  className="h-4 w-4 text-[color:var(--amber-600,hsl(var(--amber-500)))]"
                  weight="duotone"
                  aria-hidden="true"
                />
                Opinión de cumplimiento
                <span className="text-[color:var(--text-tertiary)]">· pendiente</span>
              </button>

              <span className="inline-flex items-center gap-1.5 text-[11px] text-[color:var(--text-secondary)]">
                {!reduced && (
                  <ArrowUp
                    className="cw-pulse-soft h-3.5 w-3.5 text-[color:var(--text-teal)]"
                    weight="bold"
                    aria-hidden="true"
                  />
                )}
                {reduced ? "Toca para validarlo" : "Arrástralo al proveedor en riesgo"}
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

function Donut({
  pct,
  greenEnd,
  amberEnd,
}: {
  pct: number;
  greenEnd: number;
  amberEnd: number;
}) {
  return (
    <div
      className="relative grid h-[124px] w-[124px] place-items-center rounded-full"
      style={{ background: donutGradient(greenEnd, amberEnd) }}
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
