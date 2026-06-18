import * as React from "react";

import { cn } from "@/lib/utils";

const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, children, ...props }, ref) => (
    <select
      ref={ref}
      className={cn(
        // Token-aligned with <Input> (input.tsx) so Selects and text
        // fields read as one family: same surface/border tokens, focus
        // ring, disabled treatment, and aria-invalid styling.
        "flex h-10 w-full rounded-sm border bg-[color:var(--surface-raised)] px-3 py-2",
        "text-sm text-[color:var(--text-primary)] outline-none",
        "border-[color:var(--border-default)]",
        "transition-colors duration-fast",
        "focus-visible:border-[color:var(--border-focus)] focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]/20",
        "disabled:cursor-not-allowed disabled:bg-[color:var(--surface-sunken)] disabled:text-[color:var(--text-disabled)]",
        "aria-[invalid=true]:border-[color:var(--border-error)] aria-[invalid=true]:bg-[color:var(--status-error-bg)]/30",
        "aria-[invalid=true]:focus-visible:ring-[color:var(--border-error)]/30",
        className,
      )}
      {...props}
    >
      {children}
    </select>
  ),
);
Select.displayName = "Select";

export { Select };
