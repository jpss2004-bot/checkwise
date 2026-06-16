"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import {
  animate,
  motion,
  useInView,
  useMotionValue,
  useSpring,
  useTransform,
} from "motion/react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

import { useMotionPreference } from "@/components/marketing/motion-preference";
import { cn } from "@/lib/utils";

/**
 * Animated semáforo dashboard — the hero's signature motif, now staged in
 * 3D space.
 *
 * Layers, back to front:
 *   1. A true-WebGL 3D semáforo ring (hero-semaforo-3d), lazy-mounted on
 *      desktop only and paused when the hero scrolls offscreen.
 *   2. The live client-portfolio card: a count-up compliance donut,
 *      staggered provider rows, and a pulsing #hero-risk-dot the Stakes
 *      seam will zoom into on the way down.
 *
 * On pointer the card tilts gyroscopically while the ring shifts at its own
 * rate (z-depth parallax); on scroll a GSAP ScrollTrigger scrub drifts the
 * two layers apart. Everything is gated behind the resolved motion
 * preference: under reduced motion it renders the plain static card
 * (today's look) — no WebGL, no tilt, no triggers.
 */

const EASE = [0.16, 1, 0.3, 1] as const;

const HeroSemaforo3D = dynamic(() => import("./hero-semaforo-3d"), {
  ssr: false,
});

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
  const { reduced } = useMotionPreference();

  const hostRef = useRef<HTMLDivElement>(null);
  const cardScrollRef = useRef<HTMLDivElement>(null);
  const canvasWrapRef = useRef<HTMLDivElement>(null);

  const inView = useInView(hostRef, { amount: 0.3 });
  const inViewOnce = useInView(hostRef, { once: true, amount: 0.4 });

  const [mounted, setMounted] = useState(false);
  const [can3d, setCan3d] = useState(false);

  // Gyroscopic card tilt (no-op under reduced motion — handlers bail early).
  const mx = useMotionValue(0);
  const my = useMotionValue(0);
  const cfg = { stiffness: 140, damping: 18, mass: 0.4 };
  const rotateX = useSpring(useTransform(my, [-0.5, 0.5], [7, -7]), cfg);
  const rotateY = useSpring(useTransform(mx, [-0.5, 0.5], [-9, 9]), cfg);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    // WebGL only where it earns its weight: real pointer + desktop width.
    // Re-evaluate on resize too (window event fires where matchMedia change
    // may not), so crossing the breakpoint mounts/unmounts the 3D cleanly.
    const mq = window.matchMedia("(min-width: 768px) and (pointer: fine)");
    const update = () => setCan3d(mq.matches);
    update();
    mq.addEventListener("change", update);
    window.addEventListener("resize", update);
    return () => {
      mq.removeEventListener("change", update);
      window.removeEventListener("resize", update);
    };
  }, []);

  // Scroll-travel proof: the layers drift apart as the hero scrolls out.
  // The GSAP ticker + ScrollTrigger are wired globally by SmoothScroll;
  // here we attach a scrubbed parallax to the hero band — the card (front
  // plane) and the ring (back plane) move at different rates → real depth.
  useEffect(() => {
    if (reduced) return;
    gsap.registerPlugin(ScrollTrigger);
    const ctx = gsap.context(() => {
      const trig = {
        trigger: "#inicio",
        start: "top top",
        end: "bottom top",
        scrub: true,
      } as const;
      // Card recedes (shrinks + fades + lifts) while the ring grows: the
      // camera dollies forward past the hero on the way into Stakes.
      if (cardScrollRef.current) {
        gsap.to(cardScrollRef.current, {
          yPercent: -9,
          scale: 0.95,
          opacity: 0.65,
          ease: "none",
          scrollTrigger: trig,
        });
      }
      if (canvasWrapRef.current) {
        gsap.to(canvasWrapRef.current, {
          yPercent: 16,
          scale: 1.12,
          ease: "none",
          scrollTrigger: trig,
        });
      }
    });
    return () => ctx.revert();
  }, [reduced]);

  const onMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (reduced) return;
    const r = e.currentTarget.getBoundingClientRect();
    mx.set((e.clientX - r.left) / r.width - 0.5);
    my.set((e.clientY - r.top) / r.height - 0.5);
  };
  const onLeave = () => {
    mx.set(0);
    my.set(0);
  };

  const mount3d = mounted && can3d && !reduced;

  return (
    <div
      ref={hostRef}
      className="relative"
      onPointerMove={onMove}
      onPointerLeave={onLeave}
    >
      {/* back plane — 3D ring (desktop) or aura fallback, parallax-drifted */}
      <div
        ref={canvasWrapRef}
        aria-hidden="true"
        className="pointer-events-none absolute -inset-x-12 -inset-y-36 -z-10 will-change-transform"
      >
        {mount3d ? (
          <HeroSemaforo3D active={inView} />
        ) : (
          <Aura className="absolute inset-0" />
        )}
      </div>

      {/* front plane — the card: scroll-parallax outer, perspective + tilt inner */}
      <div
        ref={cardScrollRef}
        style={{ perspective: "1100px" }}
        className="will-change-transform"
      >
        <motion.div
          style={reduced ? undefined : { rotateX, rotateY }}
          className="will-change-transform"
        >
          <DashboardCard inView={inViewOnce} reduced={reduced} />
        </motion.div>
      </div>
    </div>
  );
}

function Aura({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        "pointer-events-none opacity-70 [background:radial-gradient(60%_55%_at_70%_28%,hsl(var(--teal-500)/0.12),transparent_70%)]",
        className,
      )}
    />
  );
}

function DashboardCard({
  inView,
  reduced,
}: {
  inView: boolean;
  reduced: boolean;
}) {
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
        <Donut inView={inView} reduced={reduced} />
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
