"use client";

import {
  type FormEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  CircleNotch,
  PaperPlaneRight,
  Sparkle,
  User,
  WarningCircle,
  X,
} from "@phosphor-icons/react";

import { Button } from "@/components/ui/button";
import type { ReportContent } from "@/lib/api/reports";
import {
  useReportConversation,
  type ConversationTurn,
} from "@/lib/reports/use-conversation";

/**
 * Right-rail compliance copilot.
 *
 * Embedded inside the editor route. The copilot:
 * - Streams replies token-by-token (SSE on the backend).
 * - Sees the current canvas summary so it can refer to "the executive
 *   summary" or "the risk matrix" coherently.
 * - Suggests follow-up prompts when the conversation is empty.
 * - Refuses to mutate the canvas — that's the user's job. See
 *   docs/REPORTS_ARCHITECTURE.md §10 + §17.
 */

interface ChatCopilotProps {
  reportId: string;
  content: ReportContent;
  onClose: () => void;
}

const SUGGESTED_PROMPTS = [
  "¿Qué proveedores están más en riesgo este mes?",
  "Hazme un resumen ejecutivo de una frase.",
  "¿Qué bloque agregarías para reforzar este reporte?",
  "Explica el score de cumplimiento.",
];

export function ChatCopilot({
  reportId,
  content,
  onClose,
}: ChatCopilotProps) {
  const { turns, status, error, send } = useReportConversation(reportId);
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  // Compact canvas summary the copilot sees: block types + key signal.
  const canvasSummary = useMemo(() => {
    return {
      block_count: content.blocks.length,
      blocks: content.blocks.map((b) => ({
        id: b.id,
        type: b.type,
        has_data: b.data != null,
        has_ai_summary: !!b.ai_summary?.text,
      })),
    };
  }, [content]);

  // Auto-scroll to bottom when turns change.
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [turns]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!draft.trim() || status === "sending" || status === "streaming") return;
    const message = draft.trim();
    setDraft("");
    await send(message, canvasSummary);
  };

  const isBusy = status === "sending" || status === "streaming" || status === "loading";

  return (
    <aside
      className="flex h-full w-[360px] shrink-0 flex-col border-l border-[color:var(--border-default)] bg-[color:var(--surface-raised)]"
      aria-label="Copiloto de cumplimiento"
    >
      <header className="flex items-center justify-between border-b border-[color:var(--border-subtle)] px-4 py-3">
        <div className="flex items-center gap-2">
          <Sparkle
            className="h-4 w-4 text-[color:var(--text-ai)]"
            weight="fill"
            aria-hidden="true"
          />
          <span className="cw-eyebrow">Copiloto</span>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Cerrar copiloto"
          className="rounded-sm p-1 text-[color:var(--text-tertiary)] hover:bg-[color:var(--surface-hover)]"
        >
          <X className="h-4 w-4" weight="bold" aria-hidden="true" />
        </button>
      </header>

      <div
        ref={scrollRef}
        className="flex-1 space-y-3 overflow-y-auto px-4 py-3"
      >
        {turns.length === 0 && status !== "loading" && (
          <EmptyState
            onPick={(prompt) => {
              setDraft(prompt);
            }}
          />
        )}
        {turns.map((turn) => (
          <TurnBubble key={turn.id} turn={turn} />
        ))}
        {error && (
          <div className="flex items-start gap-2 rounded-sm bg-[color:var(--status-error-bg)] p-2 text-[12px] text-[color:var(--status-error-text)]">
            <WarningCircle
              className="mt-0.5 h-3.5 w-3.5 shrink-0"
              weight="fill"
              aria-hidden="true"
            />
            <span>{error}</span>
          </div>
        )}
      </div>

      <form
        onSubmit={onSubmit}
        className="border-t border-[color:var(--border-subtle)] p-3"
      >
        <div className="flex items-end gap-2">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                onSubmit(e as unknown as FormEvent);
              }
            }}
            placeholder="Pregúntale algo sobre este reporte…"
            rows={2}
            disabled={isBusy}
            className="flex-1 resize-none rounded-sm border border-[color:var(--border-default)] bg-[color:var(--surface-page)] px-2 py-1.5 text-[13px] text-[color:var(--text-primary)] outline-none focus:border-[color:var(--border-focus)] disabled:opacity-50"
          />
          <Button
            type="submit"
            size="sm"
            disabled={!draft.trim() || isBusy}
            aria-label="Enviar"
          >
            {isBusy ? (
              <CircleNotch
                className="h-4 w-4 animate-spin"
                weight="bold"
                aria-hidden="true"
              />
            ) : (
              <PaperPlaneRight className="h-4 w-4" weight="bold" aria-hidden="true" />
            )}
          </Button>
        </div>
        <p className="mt-2 text-[10px] text-[color:var(--text-tertiary)]">
          El copiloto solo ve el alcance de este reporte. Verificar antes de
          compartir externamente.
        </p>
      </form>
    </aside>
  );
}

function TurnBubble({ turn }: { turn: ConversationTurn }) {
  const isUser = turn.role === "user";
  return (
    <div className={`flex gap-2 ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser && (
        <div
          className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[color:var(--status-ai-bg)] text-[color:var(--text-ai)]"
          aria-hidden="true"
        >
          <Sparkle className="h-3 w-3" weight="fill" />
        </div>
      )}
      <div
        className={`max-w-[80%] rounded-md px-3 py-2 text-[13px] leading-relaxed ${
          isUser
            ? "bg-[color:var(--surface-brand-muted)] text-[color:var(--text-primary)]"
            : "bg-[color:var(--surface-page)] text-[color:var(--text-primary)]"
        }`}
      >
        {turn.markdown || (turn.isStreaming ? <Pulse /> : "")}
        {turn.isStreaming && turn.markdown && (
          <span className="ml-0.5 inline-block h-3 w-1 animate-pulse bg-[color:var(--text-ai)] align-middle" />
        )}
      </div>
      {isUser && (
        <div
          className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[color:var(--surface-sunken)] text-[color:var(--text-secondary)]"
          aria-hidden="true"
        >
          <User className="h-3 w-3" weight="regular" />
        </div>
      )}
    </div>
  );
}

function Pulse() {
  return (
    <span className="inline-flex gap-1 text-[color:var(--text-tertiary)]">
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current [animation-delay:0ms]" />
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current [animation-delay:120ms]" />
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current [animation-delay:240ms]" />
    </span>
  );
}

function EmptyState({ onPick }: { onPick: (prompt: string) => void }) {
  return (
    <div className="space-y-3 py-2">
      <div className="rounded-md border border-[color:var(--status-ai-border)] bg-[color:var(--status-ai-bg)] p-3">
        <div className="mb-1 flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-[color:var(--text-ai)]">
          <Sparkle className="h-3 w-3" weight="fill" aria-hidden="true" />
          <span>Copiloto de cumplimiento</span>
        </div>
        <p className="text-[12px] text-[color:var(--text-primary)]">
          Pregúntame qué hay en este reporte, pídeme un resumen o sugiéreme
          qué bloque agregar.
        </p>
      </div>
      <div className="space-y-1.5">
        <p className="cw-eyebrow">Prompts sugeridos</p>
        {SUGGESTED_PROMPTS.map((prompt) => (
          <button
            key={prompt}
            type="button"
            onClick={() => onPick(prompt)}
            className="w-full rounded-sm border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] px-2 py-1.5 text-left text-[12px] text-[color:var(--text-primary)] transition-colors hover:border-[color:var(--border-focus)] hover:bg-[color:var(--surface-hover)]"
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
}
