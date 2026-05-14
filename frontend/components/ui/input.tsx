import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Text input primitive.
 *
 * Picks up error styling automatically when `aria-invalid` is set,
 * which `<Field/>` does for you. Spec: DESIGN_SYSTEM.md §6.4.
 */
const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <input
      type={type}
      className={cn(
        "flex h-10 w-full rounded-sm border bg-[color:var(--surface-raised)] px-3 py-2",
        "text-sm text-[color:var(--text-primary)] outline-none",
        "border-[color:var(--border-default)]",
        "placeholder:text-[color:var(--text-tertiary)]",
        "transition-colors duration-fast",
        "file:border-0 file:bg-transparent file:text-sm file:font-medium",
        "focus-visible:border-[color:var(--border-focus)] focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]/20",
        "disabled:cursor-not-allowed disabled:bg-[color:var(--surface-sunken)] disabled:text-[color:var(--text-disabled)]",
        "aria-[invalid=true]:border-[color:var(--border-error)] aria-[invalid=true]:bg-[color:var(--status-error-bg)]/30",
        "aria-[invalid=true]:focus-visible:ring-[color:var(--border-error)]/30",
        className,
      )}
      ref={ref}
      {...props}
    />
  ),
);
Input.displayName = "Input";

export { Input };
