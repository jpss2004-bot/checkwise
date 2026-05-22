"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import {
  ArrowRight,
  CaretDown,
  PaperPlaneTilt,
  Quotes,
  Sparkle,
  Warning,
  X,
} from "@phosphor-icons/react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  getDashboard,
  getOnboarding,
  postWiseAsk,
  postWiseEvent,
  type DashboardPayload,
  type OnboardingSummary,
  type WiseAskCta,
  type WisePageContext,
} from "@/lib/api/portal";
import type { PortalSession } from "@/lib/session/portal";
import {
  WISE_QUICK_QUESTIONS,
  answerIntent,
  classifyIntent,
} from "@/lib/wise/intents";
import {
  buildWiseMessages,
  type WiseAudience,
  type WiseMessage,
} from "@/lib/wise/messages";

/**
 * Wise — provider-portal copilot dock.
 *
 * Floating brand-navy chat dock that surfaces a small ordered list of
 * deterministic Spanish suggestions about the user's current state.
 * Lives in the bottom-LEFT on desktop (so it doesn't fight the
 * FeedbackLauncher's bottom-right FAB) and slides up as a sheet from
 * the bottom on mobile. State persists per-browser via localStorage.
 *
 * Composition:
 *   • Collapsed → 56px circular FAB with the Wise mark + tiny
 *     unread-priority pulse when there's at least one warning
 *     message and the user has never opened the dock this session.
 *   • Expanded  → 360px-wide panel (desktop) / bottom sheet (mobile)
 *     with a header (Wise mark, audience pill, close button), a
 *     scrollable list of messages, and a small footer.
 *
 * Analytics:
 *   ``wise.first_render`` once per mount.
 *   ``wise.opened``  / ``wise.collapsed`` on every toggle.
 *   ``wise.suggestion_clicked`` when a CTA is clicked.
 *
 * Accessibility:
 *   The expanded panel uses ``role="dialog"`` + ``aria-modal="false"``
 *   so screen readers announce it without trapping focus on desktop.
 *   Esc collapses it. The FAB is a labelled ``button``.
 */

const STORAGE_KEY = "wise.dock.collapsed";

const AUDIENCE_PILL: Record<WiseAudience, string> = {
  net_new: "Primeros pasos",
  mid_onboarding: "En marcha",
  mature: "Cumplimiento al día",
};

const TONE_BAR: Record<NonNullable<WiseMessage["tone"]>, string> = {
  brand: "bg-[color:var(--text-teal)]",
  info: "bg-[color:var(--status-info-text)]",
  warning: "bg-[color:var(--status-warning-text)]",
  success: "bg-[color:var(--status-success-text)]",
};

const TONE_TEXT: Record<NonNullable<WiseMessage["tone"]>, string> = {
  brand: "text-[color:var(--text-teal)]",
  info: "text-[color:var(--status-info-text)]",
  warning: "text-[color:var(--status-warning-text)]",
  success: "text-[color:var(--status-success-text)]",
};

interface WiseDockProps {
  session: PortalSession;
  /** Phase 4: ALL of the following are optional. When the dock is
   *  mounted on a page that already has the dashboard payload (the
   *  dashboard itself), the page can hand them down to avoid a
   *  redundant fetch. On every other portal page the dock self-
   *  fetches on first open. */
  audience?: WiseAudience;
  messages?: WiseMessage[];
  dashboard?: DashboardPayload;
  onboarding?: OnboardingSummary | null;
  className?: string;
}

type ChatTurn =
  | { kind: "wise"; message: WiseMessage }
  | { kind: "user"; id: string; text: string };

export function WiseDock({
  session,
  audience: audienceProp,
  messages: messagesProp,
  dashboard: dashboardProp,
  onboarding: onboardingProp,
  className,
}: WiseDockProps) {
  const [collapsed, setCollapsed] = React.useState<boolean>(true);
  const [hydrated, setHydrated] = React.useState(false);
  // Phase 4: dock self-fetches when the host page doesn't pass these
  // in (i.e. every page except /portal/dashboard). The fetch defers
  // until the user actually opens the dock so the chat is fast to
  // mount on pages where they never engage with it.
  const [dashboardState, setDashboardState] = React.useState<
    DashboardPayload | null
  >(dashboardProp ?? null);
  const [onboardingState, setOnboardingState] = React.useState<
    OnboardingSummary | null
  >(onboardingProp ?? null);
  const [hasOpenedOnce, setHasOpenedOnce] = React.useState(false);
  const [turns, setTurns] = React.useState<ChatTurn[]>([]);
  const [inputValue, setInputValue] = React.useState("");
  const firedFirstRender = React.useRef(false);
  const scrollRef = React.useRef<HTMLDivElement | null>(null);

  // Page context: derived live from the URL so the dock knows what
  // screen the user is on without each page having to pass it in.
  const pageContext = useDerivedPageContext();

  // Keep local state in sync when the host page does provide the
  // payloads (the dashboard page passes them).
  React.useEffect(() => {
    if (dashboardProp) setDashboardState(dashboardProp);
  }, [dashboardProp]);
  React.useEffect(() => {
    if (onboardingProp !== undefined) setOnboardingState(onboardingProp);
  }, [onboardingProp]);

  // Lazy-fetch dashboard + onboarding the first time the dock opens
  // on a page that didn't pass them in. Subsequent opens reuse the
  // already-fetched state.
  React.useEffect(() => {
    if (!hasOpenedOnce || dashboardState !== null) return;
    let cancelled = false;
    Promise.all([
      getDashboard(session).catch(() => null),
      getOnboarding(session).catch(() => null),
    ]).then(([dash, onb]) => {
      if (cancelled) return;
      if (dash) setDashboardState(dash);
      setOnboardingState(onb);
    });
    return () => {
      cancelled = true;
    };
  }, [hasOpenedOnce, dashboardState, session]);

  // Compute welcome messages + audience whenever the underlying
  // state changes. When the host page passes ``messagesProp`` we
  // honor it (lets the dashboard page keep its existing wiring);
  // otherwise we derive everything from the dock-fetched payloads.
  const derived = React.useMemo(() => {
    if (messagesProp && audienceProp) {
      return { audience: audienceProp, messages: messagesProp };
    }
    if (!dashboardState) {
      // No dashboard yet — show a single generic greeting bubble.
      return {
        audience: "mature" as WiseAudience,
        messages: [
          {
            id: "wise-greet-loading",
            tone: "brand" as const,
            body: "Hola, soy Wise. Pregúntame lo que quieras del cumplimiento de tu proveedor.",
          },
        ],
      };
    }
    return buildWiseMessages({
      session,
      dashboard: dashboardState,
      onboarding: onboardingState,
      limit: 4,
    });
  }, [messagesProp, audienceProp, dashboardState, onboardingState, session]);

  const audience = derived.audience;
  const messages = derived.messages;

  // Seed the conversation with the initial wise messages so the
  // chat-style scrollback shows the welcome + suggestions first.
  // Re-seeds when the upstream messages array changes (e.g. a
  // dashboard refetch surfaces a new action).
  React.useEffect(() => {
    setTurns(messages.map((message) => ({ kind: "wise", message })));
  }, [messages]);

  // Auto-scroll to the bottom whenever a new turn lands so the most
  // recent message is always in view inside the panel.
  React.useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [turns, collapsed]);

  // Submit a prompt through the hybrid pipeline:
  //   1. Classify the intent locally. Known intents
  //      (next_action, deadline, rejection, status, help) reply
  //      synchronously from the deterministic answerIntent — instant,
  //      free, on-brand.
  //   2. ``unknown`` intents fall back to the LLM-backed
  //      /portal/wise/ask endpoint. We push a placeholder "pensando…"
  //      bubble first so the dock feels responsive, then swap it in
  //      place when the reply arrives. Network/auth errors degrade
  //      to a deterministic apology bubble so the dock never freezes.
  const submitPrompt = React.useCallback(
    (prompt: string) => {
      const trimmed = prompt.trim();
      if (!trimmed) return;
      const userTurnId = `user-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      const userTurn: ChatTurn = { kind: "user", id: userTurnId, text: trimmed };
      const intent = classifyIntent(trimmed);

      void postWiseEvent(session, "wise.question_asked", {
        audience,
        intent,
        prompt: trimmed.slice(0, 200),
      });

      if (intent !== "unknown" && dashboardState) {
        const reply = answerIntent({
          intent,
          session,
          dashboard: dashboardState,
          onboarding: onboardingState,
        });
        const replyTurn: ChatTurn = {
          kind: "wise",
          message: { ...reply, id: `${reply.id}-${userTurnId}` },
        };
        setTurns((prev) => [...prev, userTurn, replyTurn]);
        return;
      }

      // Unknown intent OR dashboard not yet loaded → LLM fallback.
      // Show a placeholder while we wait. The backend assembles the
      // full workspace + catalog context from the DB, and we ship
      // the page context so the model knows what screen the user is
      // on and what specific task they're in the middle of.
      const placeholderId = `wise-pending-${userTurnId}`;
      const placeholder: ChatTurn = {
        kind: "wise",
        message: {
          id: placeholderId,
          tone: "info",
          body: "Pensando…",
        },
      };
      setTurns((prev) => [...prev, userTurn, placeholder]);

      const ctas = dashboardState ? buildAllowedCtas(dashboardState) : [];
      postWiseAsk(session, trimmed, ctas, pageContext)
        .then((response) => {
          setTurns((prev) =>
            prev.map((turn) =>
              turn.kind === "wise" && turn.message.id === placeholderId
                ? {
                    kind: "wise",
                    message: {
                      id: `wise-llm-${userTurnId}`,
                      tone: response.source === "llm" ? "brand" : "info",
                      body: response.body,
                      ctaLabel: response.cta_label ?? undefined,
                      ctaHref: response.cta_href ?? undefined,
                    },
                  }
                : turn,
            ),
          );
        })
        .catch(() => {
          setTurns((prev) =>
            prev.map((turn) =>
              turn.kind === "wise" && turn.message.id === placeholderId
                ? {
                    kind: "wise",
                    message: {
                      id: `wise-error-${userTurnId}`,
                      tone: "warning",
                      body: "Tuve un problema al responder. Intenta de nuevo en un momento.",
                    },
                  }
                : turn,
            ),
          );
        });
    },
    [audience, dashboardState, onboardingState, pageContext, session],
  );

  // Hydrate from localStorage on mount. First-ever visit:
  // default to EXPANDED so onboarding gets help loud. After the
  // user collapses it once, the preference sticks.
  React.useEffect(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw === null) {
        setCollapsed(false); // first visit
      } else {
        setCollapsed(raw === "true");
      }
    } catch {
      setCollapsed(false);
    }
    setHydrated(true);
  }, []);

  // Fire wise.first_render once per dock mount. Includes the route
  // so we can later answer "which pages does the dock actually get
  // seen on?" via the wise_events analytics table.
  React.useEffect(() => {
    if (firedFirstRender.current) return;
    if (!hydrated) return;
    firedFirstRender.current = true;
    void postWiseEvent(session, "wise.first_render", {
      audience,
      route: pageContext.route,
    });
  }, [session, audience, hydrated, pageContext]);

  // Persist + emit on toggle.
  const setCollapsedAndPersist = React.useCallback(
    (next: boolean) => {
      setCollapsed(next);
      if (!next) {
        // Mark "has opened once" so the lazy-fetch effect for the
        // dashboard + onboarding payloads kicks in. We defer the
        // fetch until first open so the chat is fast to mount on
        // pages where the user never engages with Wise.
        setHasOpenedOnce(true);
      }
      try {
        window.localStorage.setItem(STORAGE_KEY, String(next));
      } catch {
        // localStorage may be unavailable (private mode); state stays in-memory.
      }
      void postWiseEvent(session, next ? "wise.collapsed" : "wise.opened", {
        audience,
        route: pageContext.route,
      });
    },
    [session, audience, pageContext],
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

  const hasWarning = messages.some((m) => m.tone === "warning");

  return (
    <>
      {/* Collapsed FAB — always rendered, fades when expanded. */}
      <button
        type="button"
        aria-label={`Abrir Wise · ${AUDIENCE_PILL[audience]}`}
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

      {/* Expanded panel — desktop floating card, mobile bottom sheet. */}
      {!collapsed ? (
        <>
          {/* Mobile-only backdrop */}
          <div
            aria-hidden="true"
            onClick={() => setCollapsedAndPersist(true)}
            className="fixed inset-0 z-40 bg-[color:var(--surface-brand)]/40 backdrop-blur-sm sm:hidden"
          />
          <section
            role="dialog"
            aria-modal="false"
            aria-label="Wise — copiloto de cumplimiento"
            className={cn(
              "fixed z-50 flex flex-col overflow-hidden bg-[color:var(--surface-brand)] text-white shadow-2xl",
              // Mobile: bottom sheet — full width, rounded top corners, ~70vh.
              "inset-x-0 bottom-0 max-h-[78vh] rounded-t-2xl",
              // Desktop: floating card pinned bottom-LEFT, ~380px wide.
              // Mirrors the FAB so the panel opens out from where the
              // launcher was sitting, keeping bottom-right free for the
              // FeedbackLauncher.
              "sm:inset-x-auto sm:bottom-6 sm:left-6 sm:max-h-[min(620px,calc(100vh-6rem))] sm:w-[380px] sm:rounded-2xl",
            )}
          >
            <DockHeader
              audience={audience}
              onClose={() => setCollapsedAndPersist(true)}
            />
            <DockBody
              turns={turns}
              session={session}
              audience={audience}
              scrollRef={scrollRef}
            />
            <DockComposer
              inputValue={inputValue}
              onInputChange={setInputValue}
              onSubmit={(prompt) => {
                submitPrompt(prompt);
                setInputValue("");
              }}
            />
          </section>
        </>
      ) : null}
    </>
  );
}

// ─── Header ────────────────────────────────────────────────────────

function DockHeader({
  audience,
  onClose,
}: {
  audience: WiseAudience;
  onClose: () => void;
}) {
  return (
    <header className="relative flex items-center justify-between gap-3 border-b border-white/10 px-5 py-3.5">
      {/* Decorative teal glow */}
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
          <p className="text-[14px] font-semibold text-white">Wise</p>
          <p className="font-mono text-[10px] uppercase tracking-wide text-white/60">
            {AUDIENCE_PILL[audience]}
          </p>
        </div>
      </div>
      <div className="relative flex items-center gap-1">
        <button
          type="button"
          onClick={onClose}
          aria-label="Minimizar Wise"
          className="hidden h-8 w-8 items-center justify-center rounded-md text-white/70 transition-colors hover:bg-white/10 hover:text-white sm:inline-flex"
        >
          <CaretDown className="h-4 w-4" weight="bold" />
        </button>
        <button
          type="button"
          onClick={onClose}
          aria-label="Cerrar Wise"
          className="inline-flex h-8 w-8 items-center justify-center rounded-md text-white/70 transition-colors hover:bg-white/10 hover:text-white sm:hidden"
        >
          <X className="h-4 w-4" weight="bold" />
        </button>
      </div>
    </header>
  );
}

// ─── Body ──────────────────────────────────────────────────────────

function DockBody({
  turns,
  session,
  audience,
  scrollRef,
}: {
  turns: ChatTurn[];
  session: PortalSession;
  audience: WiseAudience;
  scrollRef: React.RefObject<HTMLDivElement | null>;
}) {
  if (turns.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-2 px-5 py-10 text-center text-white/80">
        <Sparkle className="h-6 w-6 text-[color:var(--text-teal)]" weight="fill" aria-hidden="true" />
        <p className="text-[13px]">Estás al día. Te aviso cuando pase algo.</p>
      </div>
    );
  }
  return (
    <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-4">
      <ul className="space-y-3" aria-live="polite">
        {turns.map((turn) =>
          turn.kind === "wise" ? (
            <li key={turn.message.id}>
              <MessageBubble
                message={turn.message}
                onCtaClick={() => {
                  void postWiseEvent(session, "wise.suggestion_clicked", {
                    audience,
                    message_id: turn.message.id,
                    href: turn.message.ctaHref,
                  });
                }}
              />
            </li>
          ) : (
            <li key={turn.id} className="flex justify-end">
              <p className="max-w-[78%] rounded-2xl rounded-br-md bg-[color:var(--text-teal)] px-3.5 py-2 text-[13px] leading-snug text-[color:var(--surface-brand)]">
                {turn.text}
              </p>
            </li>
          ),
        )}
      </ul>
    </div>
  );
}

function MessageBubble({
  message,
  onCtaClick,
}: {
  message: WiseMessage;
  onCtaClick: () => void;
}) {
  return (
    <article
      className={cn(
        "relative overflow-hidden rounded-xl border border-white/10 bg-white/[0.04] p-3.5",
      )}
    >
      <span
        aria-hidden="true"
        className={cn("absolute inset-y-0 left-0 w-1", TONE_BAR[message.tone])}
      />
      <div className="space-y-2 pl-2">
        {message.meta ? (
          <p className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wide text-white/55">
            {message.tone === "warning" ? (
              <Warning
                className={cn("h-3 w-3", TONE_TEXT[message.tone])}
                weight="fill"
                aria-hidden="true"
              />
            ) : null}
            <span className="truncate">{message.meta}</span>
          </p>
        ) : null}
        <p className="text-[13px] leading-[1.5] text-white">{message.body}</p>
        {message.reviewerNote ? (
          <blockquote className="flex gap-2 rounded-md border border-white/10 bg-white/[0.05] px-3 py-2 text-[12px] italic leading-snug text-white/85">
            <Quotes
              className="h-3.5 w-3.5 shrink-0 text-[color:var(--text-teal)]"
              weight="fill"
              aria-hidden="true"
            />
            <span className="min-w-0">{message.reviewerNote}</span>
          </blockquote>
        ) : null}
        {message.ctaLabel && message.ctaHref ? (
          <Button
            asChild
            size="sm"
            className="bg-[color:var(--text-teal)] text-[color:var(--surface-brand)] hover:bg-[color:var(--text-teal)]/90"
          >
            <Link href={message.ctaHref} onClick={onCtaClick}>
              <span>{message.ctaLabel}</span>
              <ArrowRight className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
            </Link>
          </Button>
        ) : null}
      </div>
    </article>
  );
}

// ─── Composer (quick chips + text input) ──────────────────────────

function DockComposer({
  inputValue,
  onInputChange,
  onSubmit,
}: {
  inputValue: string;
  onInputChange: (value: string) => void;
  onSubmit: (prompt: string) => void;
}) {
  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSubmit(inputValue);
  };
  return (
    <footer className="border-t border-white/10 bg-[color:var(--surface-brand)]/95 px-4 py-3">
      <div className="mb-2 flex flex-wrap gap-1.5">
        {WISE_QUICK_QUESTIONS.map((q) => (
          <button
            key={q.id}
            type="button"
            onClick={() => onSubmit(q.prompt)}
            className="inline-flex items-center rounded-full border border-white/15 bg-white/[0.04] px-2.5 py-1 text-[11px] text-white/80 transition-colors hover:border-[color:var(--text-teal)]/60 hover:bg-[color:var(--text-teal)]/15 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--text-teal)]/60"
          >
            {q.label}
          </button>
        ))}
      </div>
      <form onSubmit={handleSubmit} className="flex items-center gap-2">
        <label htmlFor="wise-input" className="sr-only">
          Pregúntale a Wise
        </label>
        <input
          id="wise-input"
          type="text"
          autoComplete="off"
          value={inputValue}
          onChange={(event) => onInputChange(event.target.value)}
          placeholder="Pregúntale a Wise…"
          className="flex-1 rounded-full border border-white/15 bg-white/[0.06] px-3.5 py-1.5 text-[13px] text-white placeholder:text-white/40 focus:border-[color:var(--text-teal)]/60 focus:outline-none focus:ring-2 focus:ring-[color:var(--text-teal)]/40"
        />
        <button
          type="submit"
          aria-label="Enviar"
          disabled={inputValue.trim().length === 0}
          className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-[color:var(--text-teal)] text-[color:var(--surface-brand)] transition-all hover:bg-[color:var(--text-teal)]/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--text-teal)]/40 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <PaperPlaneTilt className="h-4 w-4" weight="fill" aria-hidden="true" />
        </button>
      </form>
    </footer>
  );
}

// ─── Helpers: allowed CTAs for the LLM ────────────────────────────

/**
 * Compose the allowed-CTA list the model can pick from. Drawn from
 * the same backend payloads the deterministic intent matcher uses,
 * so the model can never link to anything the user didn't already
 * have access to. ``id`` is the canonical matcher; the backend
 * validates against this exact list before echoing label+href.
 *
 * Phase 3 (2026-05-21): the workspace+catalog state digest moved to
 * the backend, so this is the only frontend-side context the dock
 * still ships with each ``/wise/ask`` call.
 */
function buildAllowedCtas(dashboard: DashboardPayload): WiseAskCta[] {
  const ctas: WiseAskCta[] = [];
  for (const action of dashboard.suggested_actions.slice(0, 5)) {
    ctas.push({
      id: action.id,
      label: ctaLabelForAction(action.type),
      href: action.href,
      description: action.title,
    });
  }
  for (const deadline of dashboard.upcoming_deadlines.slice(0, 3)) {
    ctas.push({
      id: deadline.id,
      label: "Ver obligación",
      href: deadline.href,
      description: deadline.title,
    });
  }
  return ctas;
}

const ACTION_CTA_LABEL_LOCAL: Record<
  DashboardPayload["suggested_actions"][number]["type"],
  string
> = {
  reupload: "Corregir carga",
  clarify: "Responder observación",
  verify_mismatch: "Verificar documento",
  complete_onboarding: "Subir documento",
  upcoming: "Subir documento",
  regularize: "Regularizar",
};

function ctaLabelForAction(
  type: DashboardPayload["suggested_actions"][number]["type"],
): string {
  return ACTION_CTA_LABEL_LOCAL[type] ?? "Abrir";
}

// ─── Helpers: page-context derivation ─────────────────────────────

/** Spanish page labels keyed by portal route. ``/portal/submissions/[id]``
 *  collapses to "Detalle de carga" so the user-facing label stays
 *  meaningful even when the id is missing. */
const PORTAL_PAGE_LABELS: { match: RegExp; label: string }[] = [
  { match: /^\/portal\/dashboard$/, label: "Dashboard de cumplimiento" },
  { match: /^\/portal\/onboarding$/, label: "Expediente inicial" },
  { match: /^\/portal\/calendar$/, label: "Calendario REPSE" },
  { match: /^\/portal\/upload$/, label: "Cargar documento" },
  { match: /^\/portal\/submissions\/[^/]+$/, label: "Detalle de carga" },
  { match: /^\/portal\/submissions$/, label: "Mis cargas" },
  { match: /^\/portal\/reports\/[^/]+\/print$/, label: "Reporte (impresión)" },
  { match: /^\/portal\/reports\/[^/]+$/, label: "Reporte" },
  { match: /^\/portal\/reports$/, label: "Reportes" },
  { match: /^\/portal\/entra-a-tu-espacio$/, label: "Entrar al portal" },
];

function labelForRoute(route: string): string {
  for (const entry of PORTAL_PAGE_LABELS) {
    if (entry.match.test(route)) return entry.label;
  }
  // Default catch-all so the dock always sends a non-empty label
  // even on an undocumented portal sub-route.
  return route.startsWith("/portal/") ? "Portal del proveedor" : route;
}

/**
 * Derive the per-request page context from the URL. Read live with
 * Next's ``usePathname`` + ``useSearchParams`` so navigating to a
 * different page re-derives without re-mounting the dock.
 *
 * Pulls common task descriptors out of the search params:
 *   * ``requirement_code`` + ``requirement`` (the human name)
 *   * ``period_key``
 *   * ``replaces`` (a prior submission id when correcting)
 *
 * The submission detail page (``/portal/submissions/[id]``) embeds
 * the id in the path; ``useDerivedPageContext`` extracts it so Wise
 * knows which submission is on screen.
 */
function useDerivedPageContext(): WisePageContext {
  const pathname = usePathname();
  const params = useSearchParams();
  return React.useMemo(() => {
    const route = pathname || "/portal";
    const label = labelForRoute(route);
    const ctx: WisePageContext = { route, page_label: label };

    const reqCode = params.get("requirement_code");
    const reqName = params.get("requirement");
    const periodKey = params.get("period_key");
    if (reqCode) ctx.requirement_code = reqCode;
    if (reqName) ctx.requirement_name = reqName;
    if (periodKey) ctx.period_key = periodKey;

    // Submission detail route: /portal/submissions/<id>
    const submissionMatch = /^\/portal\/submissions\/([^/]+)$/.exec(route);
    if (submissionMatch) ctx.submission_id = submissionMatch[1];
    // The "replaces" search param signals a re-upload flow — useful
    // context for Wise on /portal/upload too.
    const replaces = params.get("replaces");
    if (replaces && !ctx.submission_id) ctx.submission_id = replaces;

    return ctx;
  }, [pathname, params]);
}
