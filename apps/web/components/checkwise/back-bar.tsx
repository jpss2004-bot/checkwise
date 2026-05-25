"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft } from "@phosphor-icons/react";

/**
 * Shell-level back-navigation bar.
 *
 * Renders a quiet "← Volver" button anchored to the top-left of the page
 * canvas. The button is intentionally global so every inner page gets a
 * consistent way back without each route needing its own ArrowLeft. Pages
 * that already render a contextual back button (e.g. drilling out of a
 * vendor detail to its list with a smart href) keep working — the two
 * coexist for now, and the global one is the safety net.
 *
 * Visibility rules:
 *   1. Hidden until the component mounts on the client (avoids an SSR
 *      flash where ``window.history`` is unavailable).
 *   2. Hidden when the current route IS the role's home (no real
 *      "previous step" from the home dashboard).
 *   3. Hidden when there is no browser history to navigate back into
 *      (e.g. the user opened the URL directly).
 *
 * The shell passes ``homeHref`` so the component knows which route to
 * treat as the role's home. Additional hidden routes can be passed via
 * ``hiddenOn`` for surfaces that genuinely shouldn't show a back button
 * (e.g. a forced-onboarding gate where the user must finish, not back
 * out).
 */
export function BackBar({
  homeHref,
  hiddenOn = [],
}: {
  homeHref: string;
  hiddenOn?: ReadonlyArray<string>;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [hasHistory, setHasHistory] = useState(false);

  useEffect(() => {
    // ``window.history.length`` is at least 1 even on a fresh tab, so we
    // treat 2+ as "there is something to go back to". On a deep link the
    // length is exactly 1 and the bar stays hidden — the user can use
    // the in-app nav to move around instead.
    if (typeof window !== "undefined") {
      setHasHistory(window.history.length > 1);
    }
  }, [pathname]);

  if (!hasHistory) return null;
  if (pathname === homeHref) return null;
  if (hiddenOn.includes(pathname ?? "")) return null;

  return (
    <div className="mx-auto w-full max-w-7xl px-5 pt-4">
      <button
        type="button"
        onClick={() => router.back()}
        aria-label="Volver a la página anterior"
        className="group inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[12.5px] font-medium text-[color:var(--text-tertiary)] transition-colors hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]/40"
      >
        <ArrowLeft
          className="h-3.5 w-3.5 transition-transform duration-200 ease-out group-hover:-translate-x-0.5"
          weight="bold"
          aria-hidden="true"
        />
        <span>Volver</span>
      </button>
    </div>
  );
}
