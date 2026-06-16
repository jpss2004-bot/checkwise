"use client";

import { useEffect, useRef, useState } from "react";
import { animate, useInView, useReducedMotion } from "motion/react";

/**
 * Count-up on first view — numbers tally as you arrive (meaning: real,
 * accumulating figures, not static decoration). Reduced-motion → final.
 */
export function CountUp({
  to,
  suffix = "",
  className,
}: {
  to: number;
  suffix?: string;
  className?: string;
}) {
  const reduced = useReducedMotion();
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.6 });
  const [value, setValue] = useState(reduced ? to : 0);

  useEffect(() => {
    if (reduced || !inView) return;
    const controls = animate(0, to, {
      duration: 1.1,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => setValue(Math.round(v)),
    });
    return () => controls.stop();
  }, [inView, to, reduced]);

  return (
    <span ref={ref} className={className}>
      {value}
      {suffix}
    </span>
  );
}
