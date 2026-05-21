"use client";

import Image from "next/image";
import { useEffect, useReducer, useRef } from "react";
import {
  AnimatePresence,
  motion,
  useMotionValue,
  useScroll,
  useSpring,
  useTransform,
} from "motion/react";

import { useMotionPreference } from "./motion-preference";
import {
  CheckCircle,
  Files,
  Hourglass,
  ShieldCheck,
  Sparkle,
} from "@phosphor-icons/react";

/**
 * Hero product stage.
 *
 * Three real CheckWise screenshots layered into a depth composition:
 *
 *   back-left   admin-dashboard.png   (operator cockpit)
 *   back-right  portal-calendar.png   (REPSE calendar lattice)
 *   front       portal-dashboard.png  (provider compliance dashboard)
 *
 * On top of the front plate, two product moments fly in:
 *
 *   - a "submission approved" floating card (status pill morphs through
 *     en_revision -> aprobado)
 *   - a deadline-pressure pill clipped to the upper right shoulder
 *
 * Motion is staged: peeks slide+rotate into place first, the front
 * plate eases up, then the overlays land. A pointer-driven parallax
 * gives the stage genuine depth on desktop. All animation respects
 * prefers-reduced-motion.
 */

const EASE_ENTER = [0.16, 1, 0.3, 1] as const;

const STATE_CYCLE = [
  {
    key: "uploaded",
    label: "Recibido",
    tone: "uploaded",
  },
  {
    key: "in_review",
    label: "En revisión humana",
    tone: "in_review",
  },
  {
    key: "approved",
    label: "Aprobado",
    tone: "approved",
  },
] as const;

type StateKey = (typeof STATE_CYCLE)[number]["key"];

function nextState(current: StateKey): StateKey {
  const idx = STATE_CYCLE.findIndex((s) => s.key === current);
  return STATE_CYCLE[(idx + 1) % STATE_CYCLE.length].key;
}

const TONE_CLASS: Record<StateKey, string> = {
  uploaded:
    "bg-[color:var(--doc-uploaded-bg)] text-[color:var(--doc-uploaded-text)] border-[color:var(--doc-uploaded-border)]",
  in_review:
    "bg-[color:var(--doc-in-review-bg)] text-[color:var(--doc-in-review-text)] border-[color:var(--doc-in-review-border)]",
  approved:
    "bg-[color:var(--doc-approved-bg)] text-[color:var(--doc-approved-text)] border-[color:var(--doc-approved-border)]",
};

export function HeroStage() {
  const { reduced: reduce } = useMotionPreference();

  // Pointer parallax — only active when motion is allowed.
  const rootRef = useRef<HTMLDivElement | null>(null);
  const px = useMotionValue(0);
  const py = useMotionValue(0);
  const springX = useSpring(px, { stiffness: 120, damping: 18, mass: 0.6 });
  const springY = useSpring(py, { stiffness: 120, damping: 18, mass: 0.6 });

  const frontTx = useTransform(springX, [-1, 1], [-6, 6]);
  const pointerFrontY = useTransform(springY, [-1, 1], [-4, 4]);
  const pointerLeftX = useTransform(springX, [-1, 1], [-14, 4]);
  const pointerLeftY = useTransform(springY, [-1, 1], [-8, 6]);
  const pointerRightX = useTransform(springX, [-1, 1], [4, -14]);
  const pointerRightY = useTransform(springY, [-1, 1], [-8, 6]);

  // Scroll-linked depth — peeks drift up as user scrolls past hero,
  // the front plate barely moves so the reveal feels grounded.
  // `offset: ["start start", "end start"]` runs the progress from 0
  // (hero top at viewport top) to 1 (hero bottom at viewport top).
  const { scrollYProgress } = useScroll({
    target: rootRef,
    offset: ["start start", "end start"],
  });
  const scrollFront = useTransform(scrollYProgress, [0, 1], [0, reduce ? 0 : -18]);
  const scrollMid = useTransform(scrollYProgress, [0, 1], [0, reduce ? 0 : -44]);
  const scrollFar = useTransform(scrollYProgress, [0, 1], [0, reduce ? 0 : -72]);
  const scrollOpacity = useTransform(
    scrollYProgress,
    [0, 0.6, 1],
    [1, 1, reduce ? 1 : 0.5],
  );

  // Sum pointer + scroll motion values into a single Y per layer so
  // the `style` object stays JSX-friendly (one motion value per axis).
  const frontTy = useTransform([pointerFrontY, scrollFront], ([p, s]) => Number(p) + Number(s));
  const leftTy = useTransform([pointerLeftY, scrollMid], ([p, s]) => Number(p) + Number(s));
  const rightTy = useTransform([pointerRightY, scrollFar], ([p, s]) => Number(p) + Number(s));

  useEffect(() => {
    if (reduce) return;
    const el = rootRef.current;
    if (!el) return;
    let raf = 0;
    const onMove = (e: PointerEvent) => {
      const r = el.getBoundingClientRect();
      const nx = ((e.clientX - r.left) / r.width) * 2 - 1;
      const ny = ((e.clientY - r.top) / r.height) * 2 - 1;
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        px.set(Math.max(-1, Math.min(1, nx)));
        py.set(Math.max(-1, Math.min(1, ny)));
      });
    };
    const onLeave = () => {
      px.set(0);
      py.set(0);
    };
    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerleave", onLeave);
    return () => {
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerleave", onLeave);
      cancelAnimationFrame(raf);
    };
  }, [reduce, px, py]);

  // Sequenced state morph for the approval card.
  const [state, advance] = useReducer(nextState, "uploaded");
  useEffect(() => {
    if (reduce) return;
    const id = window.setInterval(() => advance(), 2600);
    return () => window.clearInterval(id);
  }, [reduce]);

  return (
    <div
      ref={rootRef}
      className="relative isolate aspect-[4/3] w-full min-w-0 sm:aspect-[5/4] lg:aspect-[6/5]"
      aria-label="Vista previa de CheckWise"
    >
      {/* ── Back left peek — admin cockpit ──────────────────────── */}
      <motion.div
        className="absolute left-[-4%] top-[14%] hidden h-[64%] w-[52%] origin-bottom-right overflow-hidden rounded-2xl border border-[color:var(--border-default)]/70 bg-[color:var(--surface-raised)] shadow-[0_28px_60px_-32px_hsl(var(--brand-navy)/0.32)] sm:block"
        initial={reduce ? false : { opacity: 0, x: -32, y: 18, rotate: -10 }}
        animate={
          reduce ? { opacity: 1 } : { opacity: 1, x: 0, y: 0, rotate: -7 }
        }
        transition={{ duration: 0.9, ease: EASE_ENTER, delay: 0.15 }}
        style={
          reduce
            ? undefined
            : { x: pointerLeftX, y: leftTy, opacity: scrollOpacity }
        }
        aria-hidden="true"
      >
        <Image
          src="/marketing/hero/admin-dashboard.png"
          alt=""
          width={1440}
          height={900}
          priority={false}
          className="h-full w-full object-cover object-left-top"
          sizes="(min-width: 1024px) 28vw, 40vw"
        />
        <div className="absolute inset-0 bg-gradient-to-tr from-white/0 via-white/0 to-white/50" />
      </motion.div>

      {/* ── Back right peek — REPSE calendar ─────────────────────── */}
      <motion.div
        className="absolute right-[-5%] top-[6%] hidden h-[58%] w-[48%] origin-bottom-left overflow-hidden rounded-2xl border border-[color:var(--border-default)]/70 bg-[color:var(--surface-raised)] shadow-[0_28px_60px_-32px_hsl(var(--brand-navy)/0.32)] sm:block"
        initial={reduce ? false : { opacity: 0, x: 32, y: 18, rotate: 10 }}
        animate={
          reduce ? { opacity: 1 } : { opacity: 1, x: 0, y: 0, rotate: 6 }
        }
        transition={{ duration: 0.9, ease: EASE_ENTER, delay: 0.28 }}
        style={
          reduce
            ? undefined
            : { x: pointerRightX, y: rightTy, opacity: scrollOpacity }
        }
        aria-hidden="true"
      >
        <Image
          src="/marketing/hero/portal-calendar.png"
          alt=""
          width={1440}
          height={900}
          priority
          className="h-full w-full object-cover object-left-top"
          sizes="(min-width: 1024px) 26vw, 40vw"
        />
        <div className="absolute inset-0 bg-gradient-to-tl from-white/0 via-white/0 to-white/40" />
      </motion.div>

      {/* ── Front plate — provider dashboard ─────────────────────── */}
      <motion.div
        className="relative z-10 ml-auto mt-[6%] w-[94%] overflow-hidden rounded-[1.5rem] border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-[0_44px_100px_-44px_hsl(var(--brand-navy)/0.42),0_18px_36px_-18px_hsl(var(--brand-navy)/0.18)] sm:w-[88%]"
        initial={reduce ? false : { opacity: 0, y: 28, scale: 0.97 }}
        animate={reduce ? { opacity: 1 } : { opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.95, ease: EASE_ENTER, delay: 0.06 }}
        style={reduce ? undefined : { x: frontTx, y: frontTy }}
      >
        {/* Faux browser chrome */}
        <div className="flex items-center gap-2 border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-page)]/70 px-3 py-2">
          <span className="flex gap-1.5">
            <span className="h-2 w-2 rounded-full bg-[color:var(--border-strong)]/80" />
            <span className="h-2 w-2 rounded-full bg-[color:var(--border-strong)]/60" />
            <span className="h-2 w-2 rounded-full bg-[color:var(--border-strong)]/40" />
          </span>
          <span className="ml-2 truncate font-mono text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-tertiary)]">
            app.checkwise.mx · /portal/dashboard
          </span>
          <span className="ml-auto flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-[color:var(--text-teal)]">
            <span className="cw-pulse-soft inline-block h-1.5 w-1.5 rounded-full bg-[color:var(--text-teal)]" />
            En vivo
          </span>
        </div>
        <Image
          src="/marketing/hero/portal-dashboard.png"
          alt="Portal de cumplimiento CheckWise mostrando el expediente del proveedor, semáforo y próximas acciones."
          width={1440}
          height={900}
          priority
          className="block h-auto w-full"
          sizes="(min-width: 1024px) 42vw, 92vw"
        />
      </motion.div>

      {/* ── Floating deadline pill (top-right) ───────────────────── */}
      <motion.div
        className="absolute right-[-3%] top-[2%] z-20 inline-flex items-center gap-2 rounded-full border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-3 py-1.5 shadow-[0_14px_32px_-14px_hsl(var(--brand-navy)/0.35)] sm:right-[2%]"
        initial={reduce ? false : { opacity: 0, y: -8, scale: 0.94 }}
        animate={reduce ? { opacity: 1 } : { opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.6, ease: EASE_ENTER, delay: 1.05 }}
      >
        <Hourglass
          className="h-3.5 w-3.5 text-[color:var(--status-warning-text)]"
          weight="fill"
          aria-hidden="true"
        />
        <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-secondary)]">
          IMSS Mayo · vence en
        </span>
        <span className="font-mono text-[11px] font-semibold tabular-nums text-[color:var(--text-primary)]">
          1d 04h
        </span>
      </motion.div>

      {/* ── Floating reviewer-decision card (bottom-left) ───────── */}
      <motion.div
        className="absolute bottom-[3%] left-[2%] z-20 w-[64%] max-w-[280px] overflow-hidden rounded-2xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-[0_28px_60px_-26px_hsl(var(--brand-navy)/0.40)] sm:left-[-6%] sm:w-[58%] sm:max-w-none lg:w-[62%]"
        initial={reduce ? false : { opacity: 0, x: -22, y: 12 }}
        animate={reduce ? { opacity: 1 } : { opacity: 1, x: 0, y: 0 }}
        transition={{ duration: 0.7, ease: EASE_ENTER, delay: 1.25 }}
      >
        <div className="flex items-center gap-2 border-b border-[color:var(--border-subtle)] px-3 py-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-md bg-[color:var(--surface-teal-muted)]">
            <Files
              className="h-3.5 w-3.5 text-[color:var(--text-teal)]"
              weight="duotone"
              aria-hidden="true"
            />
          </span>
          <div className="min-w-0">
            <p className="truncate text-[12px] font-semibold leading-tight text-[color:var(--text-primary)]">
              Opinión IMSS · Mar 2026
            </p>
            <p className="font-mono text-[9px] uppercase tracking-[0.14em] text-[color:var(--text-tertiary)]">
              Distribuidora Nogal · S‑2826
            </p>
          </div>
        </div>
        <div className="space-y-2 px-3 py-2.5">
          <div className="flex items-center justify-between gap-2">
            <span className="font-mono text-[9px] uppercase tracking-[0.16em] text-[color:var(--text-tertiary)]">
              Estado
            </span>
            <AnimatePresence mode="popLayout" initial={false}>
              <motion.span
                key={state}
                initial={
                  reduce ? false : { opacity: 0, y: 6, filter: "blur(4px)" }
                }
                animate={
                  reduce
                    ? { opacity: 1 }
                    : { opacity: 1, y: 0, filter: "blur(0px)" }
                }
                exit={
                  reduce
                    ? { opacity: 0 }
                    : { opacity: 0, y: -6, filter: "blur(4px)" }
                }
                transition={{ duration: 0.32, ease: EASE_ENTER }}
                className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${TONE_CLASS[state]}`}
              >
                {state === "approved" ? (
                  <CheckCircle className="h-3 w-3" weight="fill" aria-hidden="true" />
                ) : state === "in_review" ? (
                  <Sparkle className="h-3 w-3" weight="fill" aria-hidden="true" />
                ) : (
                  <ShieldCheck className="h-3 w-3" weight="bold" aria-hidden="true" />
                )}
                {STATE_CYCLE.find((s) => s.key === state)?.label}
              </motion.span>
            </AnimatePresence>
          </div>
          <div className="flex items-center justify-between gap-2">
            <span className="font-mono text-[9px] uppercase tracking-[0.16em] text-[color:var(--text-tertiary)]">
              Revisor
            </span>
            <span className="font-mono text-[10px] tabular-nums text-[color:var(--text-primary)]">
              Ada Reyes · Legal Shelf
            </span>
          </div>
          <div className="flex items-center justify-between gap-2">
            <span className="font-mono text-[9px] uppercase tracking-[0.16em] text-[color:var(--text-tertiary)]">
              Hash
            </span>
            <span className="truncate font-mono text-[10px] tabular-nums text-[color:var(--text-tertiary)]">
              sha256 · 7f3e…b21a
            </span>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
