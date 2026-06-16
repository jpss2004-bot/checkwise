"use client";

import { motion, useReducedMotion } from "motion/react";

/**
 * Risk meter — meaningful motion for Stakes: "your exposure is rising and
 * uncontrolled." A semáforo gradient bar that fills green→red on view.
 * scaleX (transform, GPU) not width. Reduced-motion → final state.
 */
const EASE = [0.16, 1, 0.3, 1] as const;

export function RiskMeter() {
  const reduced = useReducedMotion();
  return (
    <div>
      <div className="flex items-center justify-between font-mono text-[11px] uppercase tracking-[0.12em]">
        <span className="text-[hsl(var(--navy-200))]">Tu exposición</span>
        <span className="text-[#ff8a8a]">Alta · sin control</span>
      </div>
      <div className="mt-2.5 h-2.5 w-full overflow-hidden rounded-full bg-white/10">
        <motion.div
          className="h-full w-full origin-left rounded-full [background:linear-gradient(90deg,#09c1b0,#f5a623,#e5484d)]"
          initial={{ scaleX: reduced ? 0.85 : 0 }}
          whileInView={{ scaleX: 0.85 }}
          viewport={{ once: true, amount: 0.6 }}
          transition={reduced ? { duration: 0 } : { duration: 1.2, ease: EASE }}
        />
      </div>
    </div>
  );
}
