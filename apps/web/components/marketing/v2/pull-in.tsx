"use client";

import type { ReactNode } from "react";
import { motion, useReducedMotion } from "motion/react";

/**
 * Pull-back reveal — a one-shot scale-down from slightly-zoomed to rest as
 * the element enters, reading as the camera stepping back to take in the
 * whole picture. Used at the close. Reduced motion → plain, final state.
 */
const EASE = [0.16, 1, 0.3, 1] as const;

export function PullIn({
  children,
  className,
  amount = 0.4,
}: {
  children: ReactNode;
  className?: string;
  amount?: number;
}) {
  const reduced = useReducedMotion();
  if (reduced) return <div className={className}>{children}</div>;
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, scale: 1.07 }}
      whileInView={{ opacity: 1, scale: 1 }}
      viewport={{ once: true, amount }}
      transition={{ duration: 0.7, ease: EASE }}
    >
      {children}
    </motion.div>
  );
}
