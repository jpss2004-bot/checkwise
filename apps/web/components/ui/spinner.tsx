// dist/ssr build: no IconContext, so the spinner (and therefore
// Button) can render inside server components — the marketing article
// pages use Button outside any "use client" tree. Nothing in the app
// sets IconContext, so the two builds render identically.
import { CircleNotch } from "@phosphor-icons/react/dist/ssr";

import { cn } from "@/lib/utils";

interface SpinnerProps {
  className?: string;
  /** Accessible label. Default: "Cargando". Pass `null` to suppress. */
  label?: string | null;
}

/**
 * Inline spinner for button-loading and small in-flow loaders.
 *
 * For initial page loads use <Skeleton/> instead — spinners on
 * skeletal pages cause CLS and feel unstable. See
 * DESIGN_SYSTEM.md §6.7.
 */
export function Spinner({ className, label = "Cargando" }: SpinnerProps) {
  return (
    <span
      role={label ? "status" : "presentation"}
      aria-live={label ? "polite" : undefined}
      className={cn("inline-flex items-center", className)}
    >
      <CircleNotch
        className="h-4 w-4 animate-spin text-current"
        weight="bold"
        aria-hidden="true"
      />
      {label ? <span className="sr-only">{label}</span> : null}
    </span>
  );
}
