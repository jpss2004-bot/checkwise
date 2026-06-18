"use client";

import { MagnifyingGlass, X } from "@phosphor-icons/react";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

/**
 * Shared search box: leading magnifying-glass icon + a clear (×) button that
 * appears once there's text. Standardizes the ~9 bespoke search inputs that
 * existed across the portals so every search looks and behaves the same and
 * always offers a one-click clear.
 *
 * Controlled — the caller owns the value and any debounce. `type="search"`
 * gives mobile keyboards a search key; the native WebKit clear glyph is hidden
 * so it doesn't double up with our × button.
 */
export function SearchInput({
  value,
  onValueChange,
  placeholder,
  ariaLabel,
  className,
  inputClassName,
  id,
  autoFocus,
}: {
  value: string;
  onValueChange: (value: string) => void;
  placeholder?: string;
  ariaLabel?: string;
  className?: string;
  inputClassName?: string;
  id?: string;
  autoFocus?: boolean;
}) {
  return (
    <div className={cn("relative", className)}>
      <MagnifyingGlass
        className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[color:var(--text-tertiary)]"
        weight="bold"
        aria-hidden="true"
      />
      <Input
        id={id}
        type="search"
        value={value}
        onChange={(e) => onValueChange(e.target.value)}
        placeholder={placeholder}
        aria-label={ariaLabel ?? placeholder}
        autoFocus={autoFocus}
        className={cn(
          "pl-8 [&::-webkit-search-cancel-button]:appearance-none",
          value ? "pr-8" : undefined,
          inputClassName,
        )}
      />
      {value ? (
        <button
          type="button"
          onClick={() => onValueChange("")}
          aria-label="Limpiar búsqueda"
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded-sm p-0.5 text-[color:var(--text-tertiary)] transition-colors duration-fast hover:text-[color:var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]/40"
        >
          <X className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
        </button>
      ) : null}
    </div>
  );
}
