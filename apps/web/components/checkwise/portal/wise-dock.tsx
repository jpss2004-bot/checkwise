"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import {
  ArrowRight,
  PaperPlaneTilt,
  Quotes,
  Warning,
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
  type WiseHistoryTurn,
  type WisePageContext,
} from "@/lib/api/portal";
import type { PortalSession } from "@/lib/session/portal";
import {
  WISE_QUICK_QUESTIONS,
  answerIntent,
  classifyIntent,
  type WiseQuickQuestion,
} from "@/lib/wise/intents";
import {
  buildWiseMessages,
  type WiseAudience,
  type WiseMessage,
} from "@/lib/wise/messages";
import {
  WiseDockHeader,
  WiseDockShell,
  WiseFeedbackRow,
  WiseTypingDots,
} from "@/components/checkwise/wise/wise-dock-shell";

/**
 * Wise — provider-portal copilot dock.
 *
 * Floating brand-navy chat dock that surfaces a small ordered list of
 * deterministic Spanish suggestions about the user's current state.
 * Lives in the bottom-LEFT on desktop (so it doesn't fight the
 * FeedbackLauncher's bottom-right FAB) and slides up as a sheet from
 * the bottom on mobile. State persists per-browser via localStorage.
 *
 * Phase 5 (2026-06-02): The chrome (FAB, panel positioning, hydration,
 * Esc-to-close, mobile backdrop, lifecycle events) lives in the
 * surface-agnostic ``WiseDockShell``. This file keeps only the
 * portal-specific data layer: dashboard/onboarding lazy-fetch,
 * audience classification, deterministic intent matcher, LLM fallback,
 * page-context derivation, allowed-CTA assembly. A parallel cliente
 * dock reuses the same shell with its own portfolio-shaped data layer.
 *
 * Analytics:
 *   ``wise.first_render`` once per mount.
 *   ``wise.opened``  / ``wise.collapsed`` on every toggle.
 *   ``wise.suggestion_clicked`` when a CTA is clicked.
 */

const STORAGE_KEY = "wise.dock.collapsed";

const AUDIENCE_PILL: Record<WiseAudience, string> = {
  net_new: "Primeros pasos",
  mid_onboarding: "En marcha",
  mature: "Cumplimiento al día",
};

// Dock-local on-dark palette. The shared status/teal tokens
// (``--text-teal`` = teal-800, ``--status-*-text``) are tuned for LIGHT
// surfaces and collapse to <3:1 on the navy dock (``--surface-brand`` =
// navy-800). These lighter steps of the same brand/status scales all
// clear ~7:1+ on navy-800 so the tone cue carries on the dark surface.
const DOCK_TEAL = "hsl(175 88% 60%)"; // teal-300 — 9.3:1 on navy-800
const DOCK_TONE_COLOR: Record<NonNullable<WiseMessage["tone"]>, string> = {
  brand: DOCK_TEAL,
  info: "hsl(214 75% 80%)", // blue-200 — 7.4:1 on navy-800
  warning: "hsl(38 85% 72%)", // amber-200 — 8.2:1 on navy-800
  success: "hsl(142 72% 72%)", // green-200 — 8.9:1 on navy-800
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
  /** Notifies the host shell when Wise expands/collapses, so the portal
   *  can collapse its left sidebar to make room for the drawer. */
  onOpenChange?: (open: boolean) => void;
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
  onOpenChange,
}: WiseDockProps) {
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
  // P2 (2026-06-13): per-answer thumbs rating, keyed by message id, so
  // a rated bubble shows its choice and can't be voted on twice.
  const [feedbackByMessage, setFeedbackByMessage] = React.useState<
    Record<string, "up" | "down">
  >({});
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
  //
  // P1 fix (2026-06-12): only seed while the conversation is still
  // pristine. Previously this re-ran on every ``messages`` identity
  // change — so a late dashboard/onboarding lazy-fetch landing
  // mid-chat would wipe the user's conversation and replace it with
  // the welcome bubbles. Guarding on "has the user said anything yet"
  // keeps the welcome fresh as data loads but never erases an active
  // chat.
  React.useEffect(() => {
    setTurns((prev) => {
      if (prev.some((turn) => turn.kind === "user")) return prev;
      return messages.map((message) => ({ kind: "wise", message }));
    });
  }, [messages]);

  // Auto-scroll to the bottom whenever a new turn lands so the most
  // recent message is always in view inside the panel.
  React.useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [turns]);

  // Submit a prompt through the hybrid pipeline:
  //   1. Exact quick-chip clicks (the canned questions above the input)
  //      reply synchronously from the deterministic ``answerIntent`` —
  //      instant, free, on-brand.
  //   2. EVERYTHING ELSE — all free text — goes to the LLM-backed
  //      /portal/wise/ask endpoint, which has the same state the canned
  //      answers use PLUS the page context and the conversation history.
  //
  // P1 change (2026-06-12): the keyword router used to intercept any
  // free-text prompt that merely *contained* a trigger word ("por qué",
  // "cuándo", "ahora", "estoy") and answer it with a canned reply that
  // ignored the rest of the sentence — e.g. "¿Por qué necesito la
  // opinión del SAT?" got "No tienes documentos rechazados". We now only
  // short-circuit on an exact match to a quick-chip prompt; real
  // questions reach the model. ``classifyIntent`` is kept solely for
  // the analytics label.
  const submitPrompt = React.useCallback(
    (prompt: string) => {
      const trimmed = prompt.trim();
      if (!trimmed) return;
      const userTurnId = `user-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      const userTurn: ChatTurn = { kind: "user", id: userTurnId, text: trimmed };
      const intent = classifyIntent(trimmed);
      const isQuickQuestion = WISE_QUICK_QUESTIONS.some(
        (q) => q.prompt === trimmed,
      );

      void postWiseEvent(session, "wise.question_asked", {
        audience,
        intent,
        prompt: trimmed.slice(0, 200),
        source: isQuickQuestion ? "chip" : "freetext",
      });

      if (isQuickQuestion && intent !== "unknown" && dashboardState) {
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

      // Free text (or a quick chip fired before the dashboard loaded)
      // → LLM. Show a placeholder while we wait. The backend assembles
      // the full workspace + catalog context from the DB; we ship the
      // page context (what screen / document is on the user) and the
      // recent conversation so follow-ups resolve.
      const history = turnsToHistory(turns);
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
      postWiseAsk(session, trimmed, ctas, pageContext, history)
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
    [audience, dashboardState, onboardingState, pageContext, session, turns],
  );

  // P2 — record a thumbs rating on a Wise answer. Idempotent per
  // message (a second click on the same bubble is ignored) and
  // fire-and-forget like every other dock event.
  const submitFeedback = React.useCallback(
    (messageId: string, rating: "up" | "down") => {
      setFeedbackByMessage((prev) => {
        if (prev[messageId]) return prev;
        void postWiseEvent(session, "wise.feedback", {
          audience,
          message_id: messageId,
          rating,
          route: pageContext.route,
        });
        return { ...prev, [messageId]: rating };
      });
    },
    [audience, pageContext.route, session],
  );

  // P2 — quick chips tailored to the screen the user is on. The four
  // base chips stay deterministic (exact match in WISE_QUICK_QUESTIONS);
  // page-specific ones are new prompts that route to the LLM.
  const quickQuestions = React.useMemo(
    () => quickQuestionsForRoute(pageContext.route),
    [pageContext.route],
  );

  const hasWarning = messages.some((m) => m.tone === "warning");

  // In-flight guard: a Wise answer is pending whenever a transient
  // ``wise-pending-`` placeholder is still in the conversation. Used to
  // disable the composer so rapid submits can't fan out into multiple
  // concurrent ``/wise/ask`` requests.
  const isAsking = turns.some(
    (turn) => turn.kind === "wise" && turn.message.id.startsWith("wise-pending-"),
  );

  return (
    <WiseDockShell
      storageKey={STORAGE_KEY}
      defaultCollapsed
      ariaLabel="Wise — copiloto de cumplimiento"
      tabAriaLabel={`Abrir Wise · ${AUDIENCE_PILL[audience]}`}
      hasWarning={hasWarning}
      className={className}
      onOpenChange={onOpenChange}
      onFirstRender={() => {
        void postWiseEvent(session, "wise.first_render", {
          audience,
          route: pageContext.route,
        });
      }}
      onOpen={() => {
        // Mark "has opened once" so the lazy-fetch effect for the
        // dashboard + onboarding payloads kicks in. We defer the
        // fetch until first open so the chat is fast to mount on
        // pages where the user never engages with Wise.
        setHasOpenedOnce(true);
        void postWiseEvent(session, "wise.opened", {
          audience,
          route: pageContext.route,
        });
      }}
      onClose={() => {
        void postWiseEvent(session, "wise.collapsed", {
          audience,
          route: pageContext.route,
        });
      }}
      renderHeader={(close) => (
        <WiseDockHeader
          title="Wise"
          pill={AUDIENCE_PILL[audience]}
          onClose={close}
        />
      )}
      renderBody={() => (
        <DockBody
          turns={turns}
          session={session}
          audience={audience}
          scrollRef={scrollRef}
          feedbackByMessage={feedbackByMessage}
          onFeedback={submitFeedback}
        />
      )}
      renderComposer={() => (
        <DockComposer
          quickQuestions={quickQuestions}
          inputValue={inputValue}
          onInputChange={setInputValue}
          pending={isAsking}
          onSubmit={(prompt) => {
            // Block new asks while one is still in flight so a fast
            // double-submit can't open two concurrent LLM requests.
            if (isAsking) return;
            submitPrompt(prompt);
            setInputValue("");
          }}
        />
      )}
    />
  );
}

// ─── Body ──────────────────────────────────────────────────────────

function DockBody({
  turns,
  session,
  audience,
  scrollRef,
  feedbackByMessage,
  onFeedback,
}: {
  turns: ChatTurn[];
  session: PortalSession;
  audience: WiseAudience;
  scrollRef: React.RefObject<HTMLDivElement | null>;
  feedbackByMessage: Record<string, "up" | "down">;
  onFeedback: (messageId: string, rating: "up" | "down") => void;
}) {
  return (
    <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-4">
      <ul className="space-y-3" aria-live="polite">
        {turns.map((turn) =>
          turn.kind === "wise" ? (
            <li key={turn.message.id}>
              <MessageBubble
                message={turn.message}
                feedback={feedbackByMessage[turn.message.id]}
                onFeedback={onFeedback}
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
              <p
                className="max-w-[78%] rounded-2xl rounded-br-md px-3.5 py-2 text-[13px] leading-snug text-[color:var(--surface-brand)]"
                style={{ backgroundColor: DOCK_TEAL }}
              >
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
  feedback,
  onFeedback,
  onCtaClick,
}: {
  message: WiseMessage;
  feedback?: "up" | "down";
  onFeedback: (messageId: string, rating: "up" | "down") => void;
  onCtaClick: () => void;
}) {
  // P2 — the transient pending placeholder renders an animated typing
  // indicator instead of a flat "Pensando…" line, so the wait reads as
  // Wise composing rather than a frozen bubble.
  const isPending = message.id.startsWith("wise-pending-");
  // Show thumbs on actual answers (LLM replies + deterministic intent
  // answers), never on the seeded welcome / suggestion bubbles.
  const isAnswer =
    message.id.startsWith("wise-llm-") || message.id.startsWith("wise-answer-");

  return (
    <article
      className={cn(
        "relative overflow-hidden rounded-xl border border-white/10 bg-white/[0.04] p-3.5",
      )}
    >
      <span
        aria-hidden="true"
        className="absolute inset-y-0 left-0 w-1"
        style={{ backgroundColor: DOCK_TONE_COLOR[message.tone] }}
      />
      <div className="space-y-2 pl-2">
        {message.meta ? (
          <p className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wide text-white/55">
            {message.tone === "warning" ? (
              <Warning
                className="h-3 w-3"
                style={{ color: DOCK_TONE_COLOR[message.tone] }}
                weight="fill"
                aria-hidden="true"
              />
            ) : null}
            <span className="truncate">{message.meta}</span>
          </p>
        ) : null}
        {isPending ? (
          <WiseTypingDots />
        ) : (
          <p className="text-[13px] leading-[1.5] text-white">{message.body}</p>
        )}
        {message.reviewerNote ? (
          <blockquote className="flex gap-2 rounded-md border border-white/10 bg-white/[0.05] px-3 py-2 text-[12px] italic leading-snug text-white/85">
            <Quotes
              className="h-3.5 w-3.5 shrink-0"
              style={{ color: DOCK_TEAL }}
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
            style={{ backgroundColor: DOCK_TEAL }}
            className="text-[color:var(--surface-brand)] hover:opacity-90"
          >
            <Link href={message.ctaHref} onClick={onCtaClick}>
              <span>{message.ctaLabel}</span>
              <ArrowRight className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
            </Link>
          </Button>
        ) : null}
        {isAnswer && !isPending ? (
          <WiseFeedbackRow
            messageId={message.id}
            feedback={feedback}
            onFeedback={onFeedback}
          />
        ) : null}
      </div>
    </article>
  );
}

// ─── Composer (quick chips + text input) ──────────────────────────

function DockComposer({
  quickQuestions,
  inputValue,
  onInputChange,
  onSubmit,
  pending,
}: {
  quickQuestions: readonly WiseQuickQuestion[];
  inputValue: string;
  onInputChange: (value: string) => void;
  onSubmit: (prompt: string) => void;
  /** True while a Wise answer is in flight — disables send + Enter so
   *  rapid submits can't fan out into concurrent LLM requests. */
  pending: boolean;
}) {
  const textareaRef = React.useRef<HTMLTextAreaElement | null>(null);

  // Auto-grow the textarea from 1 up to ~4 rows as the user types a
  // multi-line question, so longer prompts stay fully visible instead of
  // scrolling out of a single line. Caps the height; past the cap it
  // scrolls internally.
  const MAX_TEXTAREA_HEIGHT = 112; // ~4 rows at the 13px/1.5 line box
  React.useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_TEXTAREA_HEIGHT)}px`;
  }, [inputValue]);

  const canSend = inputValue.trim().length > 0 && !pending;

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canSend) return;
    onSubmit(inputValue);
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter sends; Shift+Enter inserts a newline so providers can write
    // multi-line questions and proofread before sending.
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (!canSend) return;
      onSubmit(inputValue);
    }
  };

  return (
    <footer className="border-t border-white/10 bg-[color:var(--surface-brand)]/95 px-4 py-3">
      <p className="mb-1.5 font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-inverse-muted)]">
        Sugerencias
      </p>
      <div className="mb-2 flex flex-wrap gap-1.5">
        {quickQuestions.map((q) => (
          <button
            key={q.id}
            type="button"
            disabled={pending}
            onClick={() => onSubmit(q.prompt)}
            className="inline-flex items-center rounded-full border border-white/15 bg-white/[0.04] px-2.5 py-1 text-[11px] text-white/80 transition-colors hover:border-[color:var(--text-teal)]/60 hover:bg-[color:var(--text-teal)]/15 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--text-teal)]/60 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {q.label}
          </button>
        ))}
      </div>
      <form onSubmit={handleSubmit} className="flex items-end gap-2">
        <label htmlFor="wise-input" className="sr-only">
          Pregúntale a Wise
        </label>
        <textarea
          id="wise-input"
          ref={textareaRef}
          rows={1}
          autoComplete="off"
          value={inputValue}
          onChange={(event) => onInputChange(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Pregúntale a Wise…"
          className="flex-1 resize-none rounded-2xl border border-white/15 bg-white/[0.06] px-3.5 py-1.5 text-[13px] leading-[1.5] text-white placeholder:text-[color:var(--text-inverse-muted)] focus:border-[color:var(--text-teal)]/60 focus:outline-none focus:ring-2 focus:ring-[color:var(--text-teal)]/40"
        />
        <button
          type="submit"
          aria-label="Enviar"
          aria-busy={pending}
          disabled={!canSend}
          style={{ backgroundColor: DOCK_TEAL }}
          className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[color:var(--surface-brand)] transition-all hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--text-teal)]/40 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {pending ? (
            <span
              aria-hidden="true"
              className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent"
            />
          ) : (
            <PaperPlaneTilt className="h-4 w-4" weight="fill" aria-hidden="true" />
          )}
        </button>
      </form>
    </footer>
  );
}

// ─── Helpers: contextual quick chips ──────────────────────────────

/**
 * Quick-question chips tailored to the screen the user is on.
 *
 * The four base chips (``WISE_QUICK_QUESTIONS``) stay deterministic —
 * an exact match short-circuits to the instant rules-based answer in
 * ``submitPrompt``. The page-specific chips are NEW prompts, so they
 * fall through to the LLM, which has the page context + document focus
 * to answer "¿qué va aquí?" / "¿por qué está así?" about the exact
 * thing on screen.
 */
function quickQuestionsForRoute(
  route: string,
): readonly WiseQuickQuestion[] {
  if (/^\/portal\/submissions\/[^/]+$/.test(route)) {
    return [
      {
        id: "qq-ctx-doc-why",
        label: "¿Por qué está así?",
        prompt: "¿Por qué está en este estado este documento?",
      },
      {
        id: "qq-ctx-doc-next",
        label: "¿Qué hago ahora?",
        prompt: "¿Qué tengo que hacer ahora con esta carga?",
      },
      WISE_QUICK_QUESTIONS[3], // ¿Cómo voy?
    ];
  }
  if (/^\/portal\/upload$/.test(route)) {
    return [
      {
        id: "qq-ctx-up-what",
        label: "¿Qué va aquí?",
        prompt: "¿Qué documento tengo que subir aquí?",
      },
      {
        id: "qq-ctx-up-where",
        label: "¿Dónde lo obtengo?",
        prompt: "¿Dónde obtengo este documento?",
      },
      WISE_QUICK_QUESTIONS[0], // ¿Qué sigue?
    ];
  }
  if (/^\/portal\/onboarding$/.test(route)) {
    return [
      {
        id: "qq-ctx-onb-missing",
        label: "¿Qué me falta?",
        prompt: "¿Qué documentos me faltan del expediente inicial?",
      },
      WISE_QUICK_QUESTIONS[0], // ¿Qué sigue?
      WISE_QUICK_QUESTIONS[3], // ¿Cómo voy?
    ];
  }
  if (/^\/portal\/calendar$/.test(route)) {
    return [
      {
        id: "qq-ctx-cal-due",
        label: "¿Qué vence este mes?",
        prompt: "¿Qué obligaciones vencen este mes?",
      },
      WISE_QUICK_QUESTIONS[2], // ¿Cuándo vence el próximo?
      WISE_QUICK_QUESTIONS[0], // ¿Qué sigue?
    ];
  }
  return WISE_QUICK_QUESTIONS;
}

// ─── Helpers: conversation history for the LLM ────────────────────

/** Number of trailing turns shipped to ``/wise/ask`` for follow-up
 *  resolution. Keeps the request small; the backend caps at 12. */
const WISE_HISTORY_LIMIT = 8;

/**
 * Map the dock's ``turns`` into the ``{role, content}`` history the
 * backend expects, keeping only the most recent ``WISE_HISTORY_LIMIT``.
 *
 * Both deterministic (quick-chip) and LLM replies are included so a
 * follow-up after a canned answer still has context. The transient
 * "Pensando…" placeholder is skipped — it carries no real content. The
 * backend drops any leading assistant turns (the seeded welcome
 * bubbles) so the Anthropic messages array always starts with a user
 * turn.
 */
function turnsToHistory(turns: ChatTurn[]): WiseHistoryTurn[] {
  const mapped: WiseHistoryTurn[] = [];
  for (const turn of turns) {
    if (turn.kind === "user") {
      const content = turn.text.trim();
      if (content) mapped.push({ role: "user", content });
    } else {
      const body = (turn.message.body ?? "").trim();
      if (body && body !== "Pensando…") {
        mapped.push({ role: "assistant", content: body });
      }
    }
  }
  return mapped.slice(-WISE_HISTORY_LIMIT);
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
