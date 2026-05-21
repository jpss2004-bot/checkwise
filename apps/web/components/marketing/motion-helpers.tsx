"use client";

import { motion } from "motion/react";
import type { HTMLMotionProps } from "motion/react";
import type { ReactNode } from "react";

import { useMotionPreference } from "./motion-preference";

/**
 * Shared motion primitives for the marketing surface.
 *
 * Centralizing these keeps every reveal on the same easing curve and
 * duration tier, which is what makes a multi-section landing page
 * feel composed instead of stitched.
 *
 * `--ease-enter` lives in [[globals.css]] (cubic-bezier(0.16, 1, 0.3, 1)).
 */

export const EASE_ENTER = [0.16, 1, 0.3, 1] as const;

type RevealProps = Omit<HTMLMotionProps<"div">, "children"> & {
  children: ReactNode;
  delay?: number;
  y?: number;
  /** Trigger on first scroll-into-view instead of mount. */
  whenInView?: boolean;
  /** Override the default duration. */
  duration?: number;
};

/**
 * One-shot reveal — slight upward translate + fade. Honors
 * prefers-reduced-motion by rendering instantly.
 */
export function Reveal({
  children,
  delay = 0,
  y = 14,
  whenInView = true,
  duration = 0.55,
  ...rest
}: RevealProps) {
  const { reduced: reduce } = useMotionPreference();

  if (reduce) {
    return (
      <motion.div {...rest} initial={false} animate={{ opacity: 1 }}>
        {children}
      </motion.div>
    );
  }

  const transition = { duration, ease: EASE_ENTER, delay } as const;

  if (whenInView) {
    return (
      <motion.div
        {...rest}
        initial={{ opacity: 0, y }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, amount: 0.25 }}
        transition={transition}
      >
        {children}
      </motion.div>
    );
  }

  return (
    <motion.div
      {...rest}
      initial={{ opacity: 0, y }}
      animate={{ opacity: 1, y: 0 }}
      transition={transition}
    >
      {children}
    </motion.div>
  );
}

type StaggerProps = Omit<HTMLMotionProps<"ul">, "children"> & {
  children: ReactNode;
  itemDelay?: number;
};

/**
 * Apply to a parent `<ul>`/`<ol>`. Children should wrap inside
 * `<StaggerItem>`. Cascade is ~60ms which lines up with the
 * existing CSS-based `.cw-stagger` helper.
 */
export function Stagger({ children, itemDelay = 0.06, ...rest }: StaggerProps) {
  const { reduced: reduce } = useMotionPreference();
  if (reduce) {
    return (
      <motion.ul {...rest} initial={false}>
        {children}
      </motion.ul>
    );
  }
  return (
    <motion.ul
      {...rest}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, amount: 0.2 }}
      variants={{
        hidden: {},
        visible: { transition: { staggerChildren: itemDelay } },
      }}
    >
      {children}
    </motion.ul>
  );
}

export const STAGGER_ITEM_VARIANTS = {
  hidden: { opacity: 0, y: 12 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.5, ease: EASE_ENTER },
  },
} as const;
