import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Skeleton loader with a shimmer pass.
 *
 * Replaces Loader2-style spinners on initial data loads, per
 * DESIGN_SYSTEM.md §6.7. Spinners are reserved for inline actions
 * (button submitting, uploading) — see <Spinner/>.
 */
function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        "relative isolate overflow-hidden rounded-sm bg-[color:var(--surface-sunken)]",
        "after:absolute after:inset-0 after:-translate-x-full after:bg-gradient-to-r",
        "after:from-transparent after:via-white/55 after:to-transparent",
        "after:animate-shimmer motion-reduce:after:hidden",
        className,
      )}
      {...props}
    />
  );
}

export { Skeleton };
