"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { Eye, EyeSlash } from "@phosphor-icons/react";
import { useReducedMotion } from "motion/react";

/**
 * Motion preference layered on top of the OS-level `prefers-reduced-motion`.
 *
 * - Default behavior follows the OS setting (`useReducedMotion`).
 * - If the user explicitly opts out via the footer toggle, the choice is
 *   persisted in localStorage and OR'd into the OS setting.
 * - Components consume `useMotionPreference()` instead of calling
 *   `useReducedMotion` directly when they want to respect both.
 *
 * The shared `Reveal` / `Stagger` helpers and the hero stage already use
 * `useReducedMotion`. They keep working without changes — the toggle
 * here writes to a CSS class on `<html>` (`data-motion-reduced`) which
 * mirrors the OS preference, AND we expose a hook so any component can
 * read the combined value if it cares.
 */

const STORAGE_KEY = "cw-motion-preference";

type Preference = "system" | "reduced" | "full";

type Ctx = {
  /** Raw stored preference, defaults to "system". */
  preference: Preference;
  setPreference: (p: Preference) => void;
  /** True when motion should be reduced (OS reduced-motion OR user opt-out). */
  reduced: boolean;
};

const MotionPreferenceContext = createContext<Ctx | null>(null);

function readStored(): Preference {
  if (typeof window === "undefined") return "system";
  const raw = window.localStorage.getItem(STORAGE_KEY);
  return raw === "reduced" || raw === "full" ? raw : "system";
}

export function MotionPreferenceProvider({ children }: { children: ReactNode }) {
  const osReduced = useReducedMotion();
  const [preference, setPreferenceState] = useState<Preference>("system");

  // Hydrate from localStorage on mount.
  useEffect(() => {
    setPreferenceState(readStored());
  }, []);

  const reduced =
    preference === "reduced" ? true : preference === "full" ? false : !!osReduced;

  // Reflect the resolved preference on <html> so CSS can react too.
  useEffect(() => {
    if (typeof document === "undefined") return;
    document.documentElement.dataset.motionReduced = reduced ? "true" : "false";
  }, [reduced]);

  const setPreference = useCallback((p: Preference) => {
    setPreferenceState(p);
    if (typeof window === "undefined") return;
    if (p === "system") {
      window.localStorage.removeItem(STORAGE_KEY);
    } else {
      window.localStorage.setItem(STORAGE_KEY, p);
    }
  }, []);

  const value = useMemo<Ctx>(
    () => ({ preference, setPreference, reduced }),
    [preference, setPreference, reduced],
  );

  return (
    <MotionPreferenceContext.Provider value={value}>
      {children}
    </MotionPreferenceContext.Provider>
  );
}

export function useMotionPreference(): Ctx {
  const ctx = useContext(MotionPreferenceContext);
  if (!ctx) {
    // Standalone fallback so the hook is safe to call outside the provider.
    return {
      preference: "system",
      setPreference: () => {},
      reduced: false,
    };
  }
  return ctx;
}

/**
 * Subtle inline toggle. Renders a single button that cycles between
 * "Animación completa" and "Animación reducida". Defaults to the OS
 * setting; the first click sets an explicit override.
 */
export function MotionToggle({ className }: { className?: string }) {
  const { reduced, setPreference } = useMotionPreference();
  const onClick = () => setPreference(reduced ? "full" : "reduced");
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={reduced}
      title={reduced ? "Activar animación completa" : "Reducir animación"}
      className={`inline-flex items-center gap-1.5 rounded-full border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-secondary)] transition-colors hover:text-[color:var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]/40 ${className ?? ""}`}
    >
      {reduced ? (
        <EyeSlash className="h-3 w-3" weight="bold" aria-hidden="true" />
      ) : (
        <Eye className="h-3 w-3" weight="bold" aria-hidden="true" />
      )}
      <span>{reduced ? "Animación reducida" : "Animación completa"}</span>
    </button>
  );
}
