import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Multiline text input primitive.
 *
 * Picks up error styling automatically when `aria-invalid` is set,
 * which `<Field/>` does for you — same contract as `<Input/>`.
 */
const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, style, ...props }, ref) => (
    <textarea
      ref={ref}
      className={cn(
        "flex min-h-[96px] w-full rounded-sm border bg-[color:var(--surface-raised)] px-3 py-2",
        "text-sm text-[color:var(--text-primary)] outline-none",
        "border-[color:var(--border-default)]",
        "placeholder:text-[color:var(--text-tertiary)]",
        "transition-colors duration-fast",
        "focus-visible:border-[color:var(--border-focus)] focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]/20",
        "disabled:cursor-not-allowed disabled:bg-[color:var(--surface-sunken)] disabled:text-[color:var(--text-disabled)]",
        "aria-[invalid=true]:border-[color:var(--border-error)] aria-[invalid=true]:bg-[color:var(--status-error-bg)]/30",
        "aria-[invalid=true]:focus-visible:ring-[color:var(--border-error)]/30",
        className,
      )}
      style={style ?? {}}
      {...props}
    />
  ),
);
Textarea.displayName = "Textarea";

export { Textarea };
