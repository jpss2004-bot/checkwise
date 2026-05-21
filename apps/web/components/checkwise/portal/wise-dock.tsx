"use client";

import * as React from "react";
import Link from "next/link";
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
  postWiseEvent,
  type DashboardPayload,
  type OnboardingSummary,
} from "@/lib/api/portal";
import type { PortalSession } from "@/lib/session/portal";
import {
  WISE_QUICK_QUESTIONS,
  answerIntent,
  classifyIntent,
} from "@/lib/wise/intents";
import type { WiseAudience, WiseMessage } from "@/lib/wise/messages";

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
  audience: WiseAudience;
  /** Initial messages — the welcome line + suggestions surfaced
   *  when the dock first opens, before any conversation. */
  messages: WiseMessage[];
  /** Live dashboard + onboarding payloads so the chat-layer
   *  intent matcher can answer questions against the current
   *  state (next-action, deadline, rejection, status). */
  dashboard: DashboardPayload;
  onboarding: OnboardingSummary | null;
  className?: string;
}

type ChatTurn =
  | { kind: "wise"; message: WiseMessage }
  | { kind: "user"; id: string; text: string };

export function WiseDock({
  session,
  audience,
  messages,
  dashboard,
  onboarding,
  className,
}: WiseDockProps) {
  const [collapsed, setCollapsed] = React.useState<boolean>(true);
  const [hydrated, setHydrated] = React.useState(false);
  const [turns, setTurns] = React.useState<ChatTurn[]>([]);
  const [inputValue, setInputValue] = React.useState("");
  const firedFirstRender = React.useRef(false);
  const scrollRef = React.useRef<HTMLDivElement | null>(null);

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

  // Submit a prompt through the deterministic intent pipeline. Used
  // by both the free-text input and the quick-question chips so
  // there's only one codepath.
  const submitPrompt = React.useCallback(
    (prompt: string) => {
      const trimmed = prompt.trim();
      if (!trimmed) return;
      const userTurn: ChatTurn = {
        kind: "user",
        id: `user-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        text: trimmed,
      };
      const intent = classifyIntent(trimmed);
      const reply = answerIntent({ intent, session, dashboard, onboarding });
      // Give the reply a stable id keyed off the user-turn id so React
      // doesn't collide when the same intent fires twice (e.g. user
      // asks "qué sigue" twice in a row).
      const replyTurn: ChatTurn = {
        kind: "wise",
        message: { ...reply, id: `${reply.id}-${userTurn.id}` },
      };
      setTurns((prev) => [...prev, userTurn, replyTurn]);
      void postWiseEvent(session, "wise.question_asked", {
        audience,
        intent,
        prompt: trimmed.slice(0, 200),
      });
    },
    [audience, dashboard, onboarding, session],
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

  // Fire wise.first_render once per dock mount.
  React.useEffect(() => {
    if (firedFirstRender.current) return;
    if (!hydrated) return;
    firedFirstRender.current = true;
    void postWiseEvent(session, "wise.first_render", { audience });
  }, [session, audience, hydrated]);

  // Persist + emit on toggle.
  const setCollapsedAndPersist = React.useCallback(
    (next: boolean) => {
      setCollapsed(next);
      try {
        window.localStorage.setItem(STORAGE_KEY, String(next));
      } catch {
        // localStorage may be unavailable (private mode); state stays in-memory.
      }
      void postWiseEvent(session, next ? "wise.collapsed" : "wise.opened", {
        audience,
      });
    },
    [session, audience],
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
