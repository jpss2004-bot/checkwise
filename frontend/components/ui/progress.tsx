import * as React from "react";

import { cn } from "@/lib/utils";

interface ProgressProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Value in [0, 100]. Clamps. */
  value: number;
  /** Visual + a11y label for the progress bar. */
  label?: string;
  /** Show the percentage to the right of the track. */
  showValue?: boolean;
  /** Tonal variant — defaults to "brand" (navy). */
  tone?: "brand" | "teal" | "success" | "warning" | "error";
}

const TONE_FILL: Record<NonNullable<ProgressProps["tone"]>, string> = {
  brand:   "bg-[color:var(--interactive-primary)]",
  teal:    "bg-[color:var(--interactive-secondary)]",
  success: "bg-[color:var(--status-success-text)]",
  warning: "bg-[color:var(--status-warning-text)]",
  error:   "bg-[color:var(--status-error-text)]",
};

/**
 * Determinate progress bar with optional label + percentage readout.
 *
 * Spec: docs/DESIGN_SYSTEM.md §5 (Primitives) + §6.1 (Onboarding count).
 */
export function Progress({
  value,
  label,
  showValue = false,
  tone = "brand",
  className,
  ...props
}: ProgressProps) {
  const clamped = Math.max(0, Math.min(100, value));
  const rounded = Math.round(clamped);
  return (
    <div className={cn("flex flex-col gap-2", className)} {...props}>
      {(label || showValue) && (
        <div className="flex items-baseline justify-between gap-3">
          {label && (
            <p className="text-[13px] font-medium text-[color:var(--text-primary)]">
              {label}
            </p>
          )}
          {showValue && (
            <p className="font-mono text-xs tabular-nums text-[color:var(--text-secondary)]">
              {rounded}%
            </p>
          )}
        </div>
      )}
      <div
        role="progressbar"
        aria-label={label ?? "Progreso"}
        aria-valuenow={rounded}
        aria-valuemin={0}
        aria-valuemax={100}
        className="relative h-1.5 w-full overflow-hidden rounded-full bg-[color:var(--surface-sunken)]"
      >
        <div
          className={cn(
            "absolute inset-y-0 left-0 rounded-full transition-[width] duration-500 ease-enter",
            TONE_FILL[tone],
          )}
          style={{ width: `${clamped}%` }}
        />
      </div>
    </div>
  );
}
