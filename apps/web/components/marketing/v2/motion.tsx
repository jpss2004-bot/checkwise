"use client";

import { useEffect } from "react";
import type { ReactNode } from "react";
import { motion, useReducedMotion } from "motion/react";
import Lenis from "lenis";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

import { useMotionPreference } from "@/components/marketing/motion-preference";

/**
 * v2 motion foundation + cinematic scroll-travel controller.
 *
 * - SmoothScroll: Lenis inertia scroll wired to the GSAP ticker, with
 *   ScrollTrigger registered and kept in sync. This is the single substrate
 *   the cinematic layer rides on — scrubbed camera timelines, pinning, and
 *   zoom-into-element scene seams all attach to ScrollTrigger, which Lenis
 *   now drives off one clock. The whole controller is gated behind the
 *   resolved motion preference (OS reduced-motion OR the footer toggle):
 *   under reduced motion the page falls back to native scroll with no Lenis,
 *   no triggers and no 3D, so the "wow" never costs accessibility.
 * - Reveal: one-shot fade+rise on scroll-into-view, reduced-motion aware.
 *
 * CWV-safe: transform/opacity only, no layout animation, content stays in
 * the DOM (SEO/AEO unaffected). The 3D layer lazy-mounts after first paint.
 */

const EASE = [0.16, 1, 0.3, 1] as const;

export function SmoothScroll({ children }: { children: ReactNode }) {
  const { reduced } = useMotionPreference();

  useEffect(() => {
    if (reduced) return;

    gsap.registerPlugin(ScrollTrigger);

    const lenis = new Lenis({ lerp: 0.1, smoothWheel: true });

    // Lenis drives ScrollTrigger; the GSAP ticker drives Lenis. One clock
    // for smooth scroll and every scrubbed / pinned timeline on the page.
    lenis.on("scroll", ScrollTrigger.update);
    const onTick = (time: number) => lenis.raf(time * 1000);
    gsap.ticker.add(onTick);
    gsap.ticker.lagSmoothing(0);

    // Sections register their own triggers in child effects (which run
    // before this parent effect), so refresh once everything is mounted.
    ScrollTrigger.refresh();

    return () => {
      gsap.ticker.remove(onTick);
      lenis.off("scroll", ScrollTrigger.update);
      lenis.destroy();
      ScrollTrigger.getAll().forEach((t) => t.kill());
    };
  }, [reduced]);

  return <>{children}</>;
}

export function Reveal({
  children,
  className,
  delay = 0,
  y = 14,
  amount = 0.2,
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
  y?: number;
  amount?: number;
}) {
  const reduced = useReducedMotion();

  if (reduced) return <div className={className}>{children}</div>;

  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount }}
      transition={{ duration: 0.5, ease: EASE, delay }}
    >
      {children}
    </motion.div>
  );
}
