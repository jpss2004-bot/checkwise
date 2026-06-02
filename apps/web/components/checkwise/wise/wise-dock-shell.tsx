"use client";

import * as React from "react";
import { CaretDown, Sparkle, X } from "@phosphor-icons/react";

import { cn } from "@/lib/utils";

/**
 * Wise dock shell — surface-agnostic chrome.
 *
 * Owns ONLY structural behavior shared by every Wise surface (portal,
 * cliente, future admin): the floating FAB, the desktop floating-card
 * + mobile bottom-sheet panel, the localStorage-persisted collapsed
 * state, Esc-to-close, the mobile backdrop, and the three lifecycle
 * callbacks (first render, open, close).
 *
 * Owns NOTHING about the conversation:
 *   • Audience, intents, message bubbles → entry component's body.
 *   • Quick chips + input + ask plumbing → entry component's composer.
 *   • Pill labels, surface naming → entry component's header.
 *
 * Entries inject those via the three render-prop slots. Each slot is a
 * function (not a node) so re-renders triggered inside the slot don't
 * remount the shell.
 */

export interface WiseDockShellProps {
  /** localStorage key for the collapsed/expanded preference. MUST be
   *  unique per surface so portal and cliente prefs don't bleed. */
  storageKey: string;
  /** First-visit default. Portal defaults to expanded so onboarding
   *  gets help loud; quieter surfaces may prefer collapsed. */
  defaultCollapsed?: boolean;
  /** Accessible label on the dialog element. */
  ariaLabel: string;
  /** Accessible label on the collapsed FAB. */
  fabAriaLabel: string;
  /** Show the small warning pulse on the FAB. The shell never decides
   *  this — the entry computes it from its own message state. */
  hasWarning?: boolean;
  className?: string;

  /** Fired once per mount (after hydration completes). Use to send
   *  analytics; the shell never calls the network. */
  onFirstRender?: () => void;
  /** Fired every time the user transitions from collapsed → expanded.
   *  Use to lazy-fetch data on first open + emit analytics. */
  onOpen?: () => void;
  /** Fired every time the user transitions from expanded → collapsed
   *  (button, Esc, backdrop). */
  onClose?: () => void;

  /** Render slots. Receive `close` so the entry's header close button
   *  and composer can request collapse without re-implementing it. */
  renderHeader: (close: () => void) => React.ReactNode;
  renderBody: () => React.ReactNode;
  renderComposer: () => React.ReactNode;
}

export function WiseDockShell({
  storageKey,
  defaultCollapsed = false,
  ariaLabel,
  fabAriaLabel,
  hasWarning = false,
  className,
  onFirstRender,
  onOpen,
  onClose,
  renderHeader,
  renderBody,
  renderComposer,
}: WiseDockShellProps) {
  const [collapsed, setCollapsed] = React.useState<boolean>(true);
  const [hydrated, setHydrated] = React.useState(false);
  const firedFirstRender = React.useRef(false);

  // Hydrate from localStorage on mount. First-ever visit honors the
  // entry's `defaultCollapsed` preference; subsequent visits stick to
  // whatever the user chose.
  React.useEffect(() => {
    try {
      const raw = window.localStorage.getItem(storageKey);
      if (raw === null) {
        setCollapsed(defaultCollapsed);
      } else {
        setCollapsed(raw === "true");
      }
    } catch {
      setCollapsed(defaultCollapsed);
    }
    setHydrated(true);
  }, [storageKey, defaultCollapsed]);

  // Fire onFirstRender once per mount, after hydration so the entry's
  // analytics call carries the correct collapsed/expanded state.
  React.useEffect(() => {
    if (firedFirstRender.current) return;
    if (!hydrated) return;
    firedFirstRender.current = true;
    onFirstRender?.();
  }, [hydrated, onFirstRender]);

  const setCollapsedAndPersist = React.useCallback(
    (next: boolean) => {
      setCollapsed(next);
      try {
        window.localStorage.setItem(storageKey, String(next));
      } catch {
        // localStorage may be unavailable (private mode); state stays
        // in-memory and the preference resets next mount.
      }
      if (next) onClose?.();
      else onOpen?.();
    },
    [storageKey, onOpen, onClose],
  );

  // Esc closes when expanded.
  React.useEffect(() => {
    if (collapsed) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setCollapsedAndPersist(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [collapsed, setCollapsedAndPersist]);

  if (!hydrated) return null;

  const close = () => setCollapsedAndPersist(true);

  return (
    <>
      {/* Collapsed FAB — always rendered, fades when expanded so the
          transition reads as "the FAB expanded into the panel" rather
          than "two separate things popped in and out". */}
      <button
        type="button"
        aria-label={fabAriaLabel}
        aria-expanded={!collapsed}
        onClick={() => setCollapsedAndPersist(false)}
        className={cn(
          "group fixed z-40 inline-flex h-14 w-14 items-center justify-center rounded-full shadow-lg transition-all duration-fast",
          "bg-[color:var(--surface-brand)] text-white",
          "hover:scale-105 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--text-teal)]/60 focus-visible:ring-offset-2",
          // Bottom-LEFT on desktop. FeedbackLauncher owns bottom-right
          // at z-50; we mirror to the opposite corner at z-40 so the
          // two never overlap. On mobile the FAB still sits in the
          // bottom-left so users can swipe it open from the same side.
          "bottom-5 left-5 sm:bottom-6 sm:left-6",
          collapsed
            ? "pointer-events-auto scale-100 opacity-100"
            : "pointer-events-none scale-90 opacity-0",
          className,
        )}
      >
        <span
          aria-hidden="true"
          className="absolute inset-0 rounded-full bg-[color:var(--text-teal)] opacity-15 blur-md transition-opacity group-hover:opacity-30"
        />
        <Sparkle className="relative h-6 w-6 text-[color:var(--text-teal)]" weight="fill" />
        {hasWarning ? (
          <span
            aria-hidden="true"
            className="absolute right-1 top-1 h-2.5 w-2.5 rounded-full bg-[color:var(--status-warning-text)] ring-2 ring-[color:var(--surface-brand)]"
          />
        ) : null}
      </button>

      {/* Expanded panel — desktop floating card pinned bottom-left,
          mobile bottom sheet with backdrop. */}
      {!collapsed ? (
        <>
          {/* Mobile-only backdrop. Clicking it collapses the dock. */}
          <div
            aria-hidden="true"
            onClick={close}
            className="fixed inset-0 z-40 bg-[color:var(--surface-brand)]/40 backdrop-blur-sm sm:hidden"
          />
          <section
            role="dialog"
            aria-modal="false"
            aria-label={ariaLabel}
            className={cn(
              "fixed z-50 flex flex-col overflow-hidden bg-[color:var(--surface-brand)] text-white shadow-2xl",
              // Mobile: bottom sheet — full width, rounded top corners,
              // ~78vh max so the user can still see what they were
              // doing behind the dock.
              "inset-x-0 bottom-0 max-h-[78vh] rounded-t-2xl",
              // Desktop: floating card pinned bottom-LEFT, ~380px wide.
              // Mirrors the FAB so the panel opens out from where the
              // launcher was sitting, keeping bottom-right free for the
              // FeedbackLauncher.
              "sm:inset-x-auto sm:bottom-6 sm:left-6 sm:max-h-[min(620px,calc(100vh-6rem))] sm:w-[380px] sm:rounded-2xl",
            )}
          >
            {renderHeader(close)}
            {renderBody()}
            {renderComposer()}
          </section>
        </>
      ) : null}
    </>
  );
}

// ─── Reusable header chrome ─────────────────────────────────────
//
// The header is the most uniform of the three slots — every Wise
// surface wants the brand glow + sparkle icon + an audience pill + a
// close affordance. Entries can compose their own header if they need
// something different, but this default covers portal and cliente.

export interface WiseDockHeaderProps {
  title: string;
  pill: string;
  onClose: () => void;
}

export function WiseDockHeader({ title, pill, onClose }: WiseDockHeaderProps) {
  return (
    <header className="relative flex items-center justify-between gap-3 border-b border-white/10 px-5 py-3.5">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -right-12 -top-12 h-36 w-36 rounded-full bg-[color:var(--text-teal)] opacity-15 blur-3xl"
      />
      <div className="relative flex items-center gap-2.5">
        <span
          aria-hidden="true"
          className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-[color:var(--text-teal)]/15 text-[color:var(--text-teal)]"
        >
          <Sparkle className="h-4 w-4" weight="fill" />
        </span>
        <div className="min-w-0 leading-tight">
          <p className="text-[14px] font-semibold text-white">{title}</p>
          <p className="font-mono text-[10px] uppercase tracking-wide text-white/60">
            {pill}
          </p>
        </div>
      </div>
      <div className="relative flex items-center gap-1">
        <button
          type="button"
          onClick={onClose}
          aria-label="Minimizar"
          className="hidden h-8 w-8 items-center justify-center rounded-md text-white/70 transition-colors hover:bg-white/10 hover:text-white sm:inline-flex"
        >
          <CaretDown className="h-4 w-4" weight="bold" />
        </button>
        <button
          type="button"
          onClick={onClose}
          aria-label="Cerrar"
          className="inline-flex h-8 w-8 items-center justify-center rounded-md text-white/70 transition-colors hover:bg-white/10 hover:text-white sm:hidden"
        >
          <X className="h-4 w-4" weight="bold" />
        </button>
      </div>
    </header>
  );
}
