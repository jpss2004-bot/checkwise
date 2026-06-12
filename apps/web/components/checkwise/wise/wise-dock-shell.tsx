"use client";

import * as React from "react";
import { CaretRight, Sparkle, X } from "@phosphor-icons/react";

import { cn } from "@/lib/utils";

/**
 * Wise dock shell — surface-agnostic chrome.
 *
 * Owns ONLY structural behavior shared by every Wise surface (portal,
 * cliente, future admin): the closed edge tab, the desktop right-edge
 * drawer + mobile bottom-sheet panel, the localStorage-persisted
 * collapsed state, Esc-to-close, the mobile backdrop, the enter/exit
 * animation, and the three lifecycle callbacks (first render, open,
 * close).
 *
 * Owns NOTHING about the conversation:
 *   • Audience, intents, message bubbles → entry component's body.
 *   • Quick chips + input + ask plumbing → entry component's composer.
 *   • Pill labels, surface naming → entry component's header.
 *
 * Entries inject those via the three render-prop slots. Each slot is a
 * function (not a node) so re-renders triggered inside the slot don't
 * remount the shell.
 *
 * Phase 6 (2026-06-12) — Wise moved from a bottom-left floating dock to
 * a right-edge drawer. Closed, it shows a thin vertical tab on the
 * right edge; open, it slides in a full-height 480px panel. On wide
 * viewports (≥1440px) the drawer PUSHES page content left (see the
 * ``--wise-drawer-w`` / ``[data-wise-drawer-open]`` rules in
 * globals.css + the ``wise-push-target`` class on each shell's main
 * column) so nothing is ever covered; on narrower laptops it overlays.
 * Mobile keeps the bottom sheet.
 */

/** Keep in sync with the ``transition-transform`` duration on the
 *  drawer panel below. The exit timer waits this long (+ a frame of
 *  slack) before unmounting so the slide-out animation can finish. */
const DRAWER_ANIM_MS = 380;

export interface WiseDockShellProps {
  /** localStorage key for the collapsed/expanded preference. MUST be
   *  unique per surface so portal and cliente prefs don't bleed. */
  storageKey: string;
  /** First-visit default. Defaults to collapsed (tab only) so the
   *  drawer never covers the page until the user reaches for it. */
  defaultCollapsed?: boolean;
  /** Accessible label on the dialog element. */
  ariaLabel: string;
  /** Accessible label on the closed edge tab. */
  tabAriaLabel: string;
  /** Show the small warning pulse on the tab. The shell never decides
   *  this — the entry computes it from its own message state. */
  hasWarning?: boolean;
  className?: string;
  /** Optional override for the expanded drawer panel. */
  panelClassName?: string;

  /** Fired once per mount (after hydration completes). Use to send
   *  analytics; the shell never calls the network. */
  onFirstRender?: () => void;
  /** Fired every time the user transitions from collapsed → expanded.
   *  Use to lazy-fetch data on first open + emit analytics. */
  onOpen?: () => void;
  /** Fired every time the user transitions from expanded → collapsed
   *  (tab, Esc, backdrop, close button). */
  onClose?: () => void;
  /** State-sync callback fired whenever the open/closed state changes —
   *  including the initial hydration, unlike onOpen/onClose which only
   *  fire on user-driven transitions. Use this (not onOpen) when a host
   *  needs to mirror Wise's state on mount too, e.g. the provider portal
   *  collapsing its sidebar when Wise is already open on load. */
  onOpenChange?: (open: boolean) => void;

  /** Render slots. Receive `close` so the entry's header close button
   *  and composer can request collapse without re-implementing it. */
  renderHeader: (close: () => void) => React.ReactNode;
  renderBody: () => React.ReactNode;
  renderComposer: () => React.ReactNode;
}

export function WiseDockShell({
  storageKey,
  defaultCollapsed = true,
  ariaLabel,
  tabAriaLabel,
  hasWarning = false,
  className,
  panelClassName,
  onFirstRender,
  onOpen,
  onClose,
  onOpenChange,
  renderHeader,
  renderBody,
  renderComposer,
}: WiseDockShellProps) {
  const [collapsed, setCollapsed] = React.useState<boolean>(true);
  const [hydrated, setHydrated] = React.useState(false);
  const reportedOpenRef = React.useRef<boolean | null>(null);
  // ``mounted`` keeps the panel in the DOM for the duration of the
  // open + slide-out window; ``entered`` drives the in-place transform
  // + staggered content reveal. Splitting them lets the exit animate.
  const [mounted, setMounted] = React.useState(false);
  const [entered, setEntered] = React.useState(false);
  const firedFirstRender = React.useRef(false);
  const exitTimer = React.useRef<number | null>(null);

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

  // Drive the mount → enter → exit lifecycle off the logical collapsed
  // state. Opening mounts then flips ``entered`` on the next frame so
  // the CSS transition runs. Closing flips ``entered`` off immediately
  // (slide-out) and unmounts once the animation window elapses.
  React.useEffect(() => {
    if (!hydrated) return;
    if (exitTimer.current !== null) {
      window.clearTimeout(exitTimer.current);
      exitTimer.current = null;
    }
    if (!collapsed) {
      setMounted(true);
      // Flip ``entered`` a tick after mount so the browser commits the
      // off-screen "from" state first and the slide-in transition runs.
      // A short timeout (not requestAnimationFrame) so it still fires
      // when rAF is throttled on a backgrounded/non-painting tab.
      const t = window.setTimeout(() => setEntered(true), 30);
      return () => window.clearTimeout(t);
    }
    setEntered(false);
    exitTimer.current = window.setTimeout(() => {
      setMounted(false);
      exitTimer.current = null;
    }, DRAWER_ANIM_MS + 40);
    return () => {
      if (exitTimer.current !== null) {
        window.clearTimeout(exitTimer.current);
        exitTimer.current = null;
      }
    };
  }, [collapsed, hydrated]);

  // Reflect open state on <html> so the page can react in pure CSS:
  //   • ``[data-wise-drawer-open]`` → content push (≥1440px) + the
  //     feedback launcher stepping aside.
  //   • ``[data-wise-drawer-mounted]`` → ``overflow-x: clip`` for the
  //     duration of the slide so the off-screen panel never spawns a
  //     transient horizontal scrollbar.
  React.useEffect(() => {
    if (!hydrated) return;
    document.documentElement.dataset.wiseDrawerOpen = collapsed
      ? "false"
      : "true";
  }, [collapsed, hydrated]);

  React.useEffect(() => {
    if (!hydrated) return;
    const root = document.documentElement;
    if (mounted) root.dataset.wiseDrawerMounted = "true";
    else delete root.dataset.wiseDrawerMounted;
  }, [mounted, hydrated]);

  // Clean the global flags if the dock unmounts mid-open (e.g. route
  // change tearing down the shell) so a stale push/clip never sticks.
  React.useEffect(
    () => () => {
      const root = document.documentElement;
      delete root.dataset.wiseDrawerOpen;
      delete root.dataset.wiseDrawerMounted;
    },
    [],
  );

  // Report open-state changes to the host — including the initial
  // hydrated state, which onOpen/onClose miss (they only fire on
  // user-driven transitions). Guarded by ``reportedOpenRef`` so it fires
  // only on an actual change, never on every re-render: re-firing the
  // same value would clobber a host's restore bookkeeping (e.g. the
  // portal's sidebar ``wiseRestoreRef``).
  React.useEffect(() => {
    if (!hydrated) return;
    const open = !collapsed;
    if (reportedOpenRef.current === open) return;
    reportedOpenRef.current = open;
    onOpenChange?.(open);
  }, [collapsed, hydrated, onOpenChange]);

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
      {/* Closed affordance — a thin vertical tab pinned to the right
          edge. Peeks left on hover. Sits at z-40 so the open drawer
          (z-50) cleanly covers it; fades out rather than translating
          off-screen to avoid any overflow. */}
      <button
        type="button"
        aria-label={tabAriaLabel}
        aria-expanded={!collapsed}
        onClick={() => setCollapsedAndPersist(false)}
        className={cn(
          "group fixed right-0 top-1/2 z-40 flex -translate-y-1/2 flex-col items-center gap-2 rounded-l-2xl border border-r-0 border-white/10 py-4 pl-2.5 pr-1.5 shadow-lg",
          "bg-[color:var(--surface-brand)] text-white",
          "transition-[transform,opacity,padding,box-shadow] duration-300 ease-out",
          "hover:-translate-x-1 hover:pr-2.5 hover:shadow-xl",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--text-teal)]/60 focus-visible:ring-offset-2",
          collapsed
            ? "pointer-events-auto opacity-100"
            : "pointer-events-none opacity-0",
          className,
        )}
      >
        <span
          aria-hidden="true"
          className="absolute inset-0 rounded-l-2xl bg-[color:var(--text-teal)] opacity-0 blur-md transition-opacity duration-300 group-hover:opacity-20"
        />
        <Sparkle
          className="relative h-5 w-5 text-[color:var(--text-teal)]"
          weight="fill"
        />
        <span className="relative text-[11px] font-semibold uppercase tracking-wide [writing-mode:vertical-rl]">
          Wise
        </span>
        {hasWarning ? (
          <span
            aria-hidden="true"
            className="absolute -left-1 top-2 h-2.5 w-2.5 rounded-full bg-[color:var(--status-warning-text)] ring-2 ring-[color:var(--surface-brand)]"
          />
        ) : null}
      </button>

      {/* Expanded panel — mobile bottom sheet (with backdrop) / desktop
          right-edge full-height drawer. */}
      {mounted ? (
        <>
          {/* Mobile-only backdrop. Clicking it collapses the dock. */}
          <div
            aria-hidden="true"
            onClick={close}
            className={cn(
              "fixed inset-0 z-40 bg-[color:var(--surface-brand)]/40 backdrop-blur-sm transition-opacity duration-300 lg:hidden",
              entered ? "opacity-100" : "opacity-0",
            )}
          />
          <section
            role="dialog"
            aria-modal="false"
            aria-label={ariaLabel}
            data-entered={entered ? "true" : "false"}
            className={cn(
              "wise-drawer fixed z-50 flex flex-col overflow-hidden bg-[color:var(--surface-brand)] text-white shadow-2xl",
              "transition-transform duration-[380ms] ease-[cubic-bezier(0.22,1,0.36,1)] will-change-transform",
              // Below lg (mobile + small tablet): bottom sheet — full
              // width, rounded top, ~78vh so the user can still see
              // what's behind the dock, and it never covers the top bar.
              "inset-x-0 bottom-0 max-h-[78vh] rounded-t-2xl",
              // Desktop (≥lg): full-height 380px drawer flush to the
              // right edge, rounded + bordered on the left. The page is
              // pushed left by this width (globals.css) so nothing is
              // covered. ``top-0 bottom-0`` (not ``inset-y-0``) so it
              // pins to the full viewport height without colliding with
              // the bottom-sheet ``bottom-0`` utility.
              "lg:left-auto lg:right-0 lg:top-0 lg:bottom-0 lg:max-h-none lg:w-[380px] lg:rounded-l-2xl lg:rounded-r-none lg:border-l lg:border-white/10",
              // Enter / exit transforms. Bottom sheet slides on Y,
              // desktop drawer on X.
              entered
                ? "translate-y-0 lg:translate-x-0"
                : "translate-y-full lg:translate-y-0 lg:translate-x-full",
              panelClassName,
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

// ─── Welcome hero ───────────────────────────────────────────────
//
// Centered greeting for the drawer's fresh state. The right-edge drawer
// is full height, so a lone greeting bubble pinned to the top leaves a
// large void; this fills it with a calm sparkle medallion + greeting
// until the conversation starts.

export function WiseWelcome({ body }: { body: string }) {
  return (
    <>
      <span
        aria-hidden="true"
        className="relative inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-[color:var(--text-teal)]/15 text-[color:var(--text-teal)]"
      >
        <span className="absolute inset-0 rounded-2xl bg-[color:var(--text-teal)] opacity-20 blur-xl" />
        <Sparkle className="relative h-7 w-7" weight="fill" />
      </span>
      <div className="space-y-1.5">
        <p className="text-[16px] font-semibold text-white">Hola, soy Wise</p>
        <p className="mx-auto max-w-[15rem] text-[13px] leading-relaxed text-white/65">
          {body}
        </p>
      </div>
    </>
  );
}

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
      <button
        type="button"
        onClick={onClose}
        aria-label="Cerrar"
        className="relative inline-flex h-8 w-8 items-center justify-center rounded-md text-white/70 transition-colors hover:bg-white/10 hover:text-white"
      >
        {/* Caret on the desktop drawer (slides back to the edge) / X on
            the bottom sheet (<lg). */}
        <CaretRight className="hidden h-4 w-4 lg:block" weight="bold" />
        <X className="h-4 w-4 lg:hidden" weight="bold" />
      </button>
    </header>
  );
}
