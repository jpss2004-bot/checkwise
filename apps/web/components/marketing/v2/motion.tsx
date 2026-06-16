"use client";

import { useEffect } from "react";
import type { ReactNode } from "react";
import { motion, useReducedMotion } from "motion/react";
import Lenis from "lenis";

/**
 * v2 motion foundation.
 *
 * - SmoothScroll: Lenis inertia scroll, the substrate for the cinematic
 *   scroll-travel. Disabled entirely under prefers-reduced-motion (native
 *   scroll), so the "wow" never costs accessibility.
 * - Reveal: one-shot fade+rise on scroll-into-view, reduced-motion aware.
 *
 * Built on the already-installed `motion` (Framer Motion); only Lenis was
 * added. CWV-safe: transform/opacity only, no layout animation, content
 * stays in the DOM (SEO/AEO unaffected).
 */

const EASE = [0.16, 1, 0.3, 1] as const;

export function SmoothScroll({ children }: { children: ReactNode }) {
  const reduced = useReducedMotion();

  useEffect(() => {
    if (reduced) return;
    const lenis = new Lenis({ lerp: 0.1, smoothWheel: true });
    let id = requestAnimationFrame(function raf(time) {
      lenis.raf(time);
      id = requestAnimationFrame(raf);
    });
    return () => {
      cancelAnimationFrame(id);
      lenis.destroy();
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
