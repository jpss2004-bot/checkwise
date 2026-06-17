"use client";

import { useEffect } from "react";
import {
  motion,
  useMotionValue,
  useScroll,
  useSpring,
  useTransform,
} from "motion/react";

import { useMotionPreference } from "@/components/marketing/motion-preference";

/**
 * Marketing atmosphere — one fixed, page-wide living backdrop.
 *
 * A scroll-reactive semáforo field sits behind the whole landing: soft
 * rose/teal/amber/green glows cross-fade as you scroll, so the page's mood
 * travels from residual risk through control toward proof (green), over a
 * faint grid and grain for depth. The flat light sections are translucent
 * (see _shared.tsx bands) so this bleeds through and gives them life; the
 * dark sections stay opaque and keep their own treatment.
 *
 * Lenis uses native scroll, so position:fixed holds and Framer useScroll
 * tracks progress. Transform/opacity only, pointer-events-none, aria-hidden.
 * Under reduced motion it renders a calm static wash with no scroll or
 * cursor reaction.
 */
export function MarketingAtmosphere() {
  const { reduced } = useMotionPreference();
  const { scrollYProgress } = useScroll();

  // Cursor parallax for depth (disabled under reduced motion).
  const pxRaw = useMotionValue(0);
  const pyRaw = useMotionValue(0);
  const px = useSpring(pxRaw, { stiffness: 40, damping: 22, mass: 0.6 });
  const py = useSpring(pyRaw, { stiffness: 40, damping: 22, mass: 0.6 });

  useEffect(() => {
    if (reduced) return;
    const onMove = (e: PointerEvent) => {
      pxRaw.set((e.clientX / window.innerWidth - 0.5) * 26);
      pyRaw.set((e.clientY / window.innerHeight - 0.5) * 26);
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    return () => window.removeEventListener("pointermove", onMove);
  }, [reduced, pxRaw, pyRaw]);

  // Semáforo hue travels with scroll. The light bands sit roughly between
  // 0.22 and 0.9 of the page, so the journey reads there: a residual rose
  // out of the risk band, warming through teal/amber, resolving to green.
  const rose = useTransform(scrollYProgress, [0.16, 0.3, 0.45], [0.2, 0.1, 0]);
  const teal = useTransform(scrollYProgress, [0.18, 0.36, 0.66], [0.3, 0.36, 0.1]);
  const amber = useTransform(scrollYProgress, [0.32, 0.52, 0.74], [0.05, 0.28, 0.08]);
  const green = useTransform(scrollYProgress, [0.56, 0.84, 1], [0, 0.32, 0.38]);

  if (reduced) {
    return (
      <div aria-hidden="true" className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
        <div className="absolute inset-0 [background:radial-gradient(58%_48%_at_28%_24%,hsl(var(--teal-500)/0.1),transparent_70%),radial-gradient(54%_44%_at_76%_82%,hsl(var(--green-500)/0.1),transparent_70%)]" />
        <GridGrain />
      </div>
    );
  }

  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
      <motion.div className="absolute inset-0" style={{ x: px, y: py }}>
        <motion.div
          style={{ opacity: rose }}
          className="absolute -left-[12%] top-[6%] h-[58vh] w-[58vw] rounded-full blur-[120px] [background:radial-gradient(circle,hsl(var(--red-500)),transparent_62%)]"
        />
        <motion.div
          style={{ opacity: teal }}
          className="absolute left-[6%] top-[26%] h-[66vh] w-[60vw] rounded-full blur-[130px] [background:radial-gradient(circle,hsl(var(--teal-500)),transparent_62%)]"
        />
        <motion.div
          style={{ opacity: amber }}
          className="absolute right-[2%] top-[46%] h-[58vh] w-[54vw] rounded-full blur-[130px] [background:radial-gradient(circle,hsl(var(--amber-500)),transparent_62%)]"
        />
        <motion.div
          style={{ opacity: green }}
          className="absolute -bottom-[6%] left-[26%] h-[66vh] w-[62vw] rounded-full blur-[140px] [background:radial-gradient(circle,hsl(var(--green-500)),transparent_62%)]"
        />
      </motion.div>
      <GridGrain />
    </div>
  );
}

function GridGrain() {
  return (
    <>
      {/* living grid — only reads through the translucent light bands */}
      <div
        className="absolute inset-0"
        style={{
          backgroundImage:
            "linear-gradient(to right, hsl(var(--brand-navy)/0.07) 1px, transparent 1px), linear-gradient(to bottom, hsl(var(--brand-navy)/0.07) 1px, transparent 1px)",
          backgroundSize: "56px 56px",
          maskImage:
            "linear-gradient(to bottom, transparent, #000 14%, #000 86%, transparent)",
          WebkitMaskImage:
            "linear-gradient(to bottom, transparent, #000 14%, #000 86%, transparent)",
        }}
      />
      {/* fine grain for paper-like depth */}
      <div
        className="absolute inset-0 opacity-[0.04] mix-blend-soft-light"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")",
        }}
      />
    </>
  );
}
