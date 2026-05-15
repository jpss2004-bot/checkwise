"use client";

import * as React from "react";
import * as CheckboxPrimitive from "@radix-ui/react-checkbox";
import { Check, Minus } from "@phosphor-icons/react";

import { cn } from "@/lib/utils";

/**
 * Checkbox primitive built on Radix.
 *
 * Accepts `checked={true | false | "indeterminate"}` for tri-state usage
 * (e.g. "select all" rows in a table where some are selected). The
 * indicator renders a Check on `true` and a Minus on `"indeterminate"`.
 */
const Checkbox = React.forwardRef<
  React.ElementRef<typeof CheckboxPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof CheckboxPrimitive.Root>
>(({ className, ...props }, ref) => (
  <CheckboxPrimitive.Root
    ref={ref}
    className={cn(
      "peer h-4 w-4 shrink-0 rounded-sharp border",
      "border-[color:var(--border-strong)] bg-[color:var(--surface-raised)]",
      "transition-colors duration-fast",
      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]/40 focus-visible:ring-offset-1 focus-visible:ring-offset-[color:var(--surface-page)]",
      "disabled:cursor-not-allowed disabled:opacity-50",
      "data-[state=checked]:border-[color:var(--interactive-primary)] data-[state=checked]:bg-[color:var(--interactive-primary)] data-[state=checked]:text-[color:var(--text-inverse)]",
      "data-[state=indeterminate]:border-[color:var(--interactive-primary)] data-[state=indeterminate]:bg-[color:var(--interactive-primary)] data-[state=indeterminate]:text-[color:var(--text-inverse)]",
      "aria-[invalid=true]:border-[color:var(--border-error)]",
      className,
    )}
    {...props}
  >
    <CheckboxPrimitive.Indicator className="flex items-center justify-center text-current">
      {props.checked === "indeterminate" ? (
        <Minus className="h-3 w-3" weight="bold" aria-hidden="true" />
      ) : (
        <Check className="h-3 w-3" weight="bold" aria-hidden="true" />
      )}
    </CheckboxPrimitive.Indicator>
  </CheckboxPrimitive.Root>
));
Checkbox.displayName = CheckboxPrimitive.Root.displayName;

export { Checkbox };
