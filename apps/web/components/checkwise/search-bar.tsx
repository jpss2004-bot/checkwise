"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { MagnifyingGlass } from "@phosphor-icons/react";

/**
 * Shell-level search input.
 *
 * One smart input wired to a role-specific /buscar route. The backend
 * detects the query type by shape (provider/client name, RFC, periodo,
 * folio) so the user never has to pick a "search type" up front.
 * Submitting navigates to ``${resultsHref}?q=<value>`` where the
 * results page renders the matches.
 *
 * Placement: lives inside each shell's header next to the user menu /
 * notifications bell. Hidden on the narrowest mobile viewports
 * (``hidden sm:flex``) — small screens reach the same /buscar route via
 * the "Buscar" entry in the hamburger nav drawer.
 */
export function SearchBar({
  resultsHref,
  placeholder = "Buscar por nombre, RFC, folio o periodo…",
  className = "",
}: {
  resultsHref: string;
  placeholder?: string;
  className?: string;
}) {
  const router = useRouter();
  const [value, setValue] = useState("");

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = value.trim();
    if (!trimmed) return;
    router.push(`${resultsHref}?q=${encodeURIComponent(trimmed)}`);
  }

  return (
    <form
      onSubmit={onSubmit}
      role="search"
      aria-label="Buscar"
      className={`hidden sm:flex ${className}`}
    >
      <div className="group relative">
        <MagnifyingGlass
          className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[color:var(--text-tertiary)] transition-colors group-focus-within:text-[color:var(--text-secondary)]"
          weight="bold"
          aria-hidden="true"
        />
        <input
          type="search"
          name="q"
          inputMode="search"
          autoComplete="off"
          placeholder={placeholder}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          aria-label="Buscar por nombre de proveedor, RFC, folio o periodo"
          className="h-8 w-[240px] rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] pl-7 pr-2 text-[12.5px] text-[color:var(--text-primary)] placeholder:text-[color:var(--text-tertiary)] focus-visible:border-[color:var(--border-focus)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]/30 lg:w-[280px]"
        />
      </div>
    </form>
  );
}
