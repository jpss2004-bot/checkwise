"use client";

import {
  type FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  CircleNotch,
  PaperPlaneRight,
  Plus,
  Sparkle,
  User,
  WarningCircle,
  X,
} from "@phosphor-icons/react";

import { Button } from "@/components/ui/button";
import {
  ReportsApiError,
  suggestBlocks,
  type BlockSuggestion,
  type ReportBlock,
  type ReportContent,
} from "@/lib/api/reports";
import { getBlockDefinition } from "@/lib/reports/registry";
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
  /**
   * R6: when present, the copilot exposes a "Sugerir bloques" CTA
   * that fetches structured drafts from the backend. Clicking
   * "Aplicar" on a card calls this callback with the draft; the
   * editor splices it into the canvas via its existing autosave
   * path. Omit to hide the affordance entirely (useful for surfaces
   * that don't own the canvas).
   */
  onInsertBlock?: (block: ReportBlock) => void;
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
  onInsertBlock,
}: ChatCopilotProps) {
  const { turns, status, error, send } = useReportConversation(reportId);
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  // R6 — suggest-blocks panel state. Stays local to the copilot so
  // the editor doesn't have to know it exists; the editor only sees
  // the ``onInsertBlock`` callback firing when the user applies one.
  const [suggestions, setSuggestions] = useState<BlockSuggestion[] | null>(
    null,
  );
  const [suggestStatus, setSuggestStatus] = useState<"idle" | "loading">(
    "idle",
  );
  const [suggestError, setSuggestError] = useState<string | null>(null);
  const [appliedIndices, setAppliedIndices] = useState<Set<number>>(
    () => new Set(),
  );

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

  const onRequestSuggestions = useCallback(async () => {
    if (suggestStatus === "loading") return;
    setSuggestStatus("loading");
    setSuggestError(null);
    setAppliedIndices(new Set());
    try {
      const resp = await suggestBlocks(reportId, {
        intent:
          "Sugiéreme entre 1 y 4 bloques que reforzarían este reporte tal como está.",
        canvas_summary: canvasSummary,
      });
      setSuggestions(resp.suggestions);
    } catch (err) {
      setSuggestions([]);
      setSuggestError(
        err instanceof ReportsApiError
          ? err.message
          : "No pudimos pedir sugerencias.",
      );
    } finally {
      setSuggestStatus("idle");
    }
  }, [reportId, canvasSummary, suggestStatus]);

  const onApplySuggestion = useCallback(
    (suggestion: BlockSuggestion, index: number) => {
      if (!onInsertBlock) return;
      const id = cryptoUuid();
      onInsertBlock({
        id,
        type: suggestion.type,
        config: suggestion.config,
        ai_summary: null,
        layout: { width: "full" },
      });
      setAppliedIndices((prev) => {
        const next = new Set(prev);
        next.add(index);
        return next;
      });
    },
    [onInsertBlock],
  );

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

        {onInsertBlock && (
          <SuggestionPanel
            status={suggestStatus}
            suggestions={suggestions}
            error={suggestError}
            appliedIndices={appliedIndices}
            onRequest={onRequestSuggestions}
            onApply={onApplySuggestion}
          />
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

// R6 — suggestion panel: the copilot's structured-output surface.
//
// One panel per copilot session. Idle state shows a single CTA;
// loading state shows a spinner; ready state shows a card per
// suggestion with the block's icon, label, rationale, and an
// Apply button. Each card flips to a confirmed state once Apply
// is clicked so the user can apply several in a row without
// losing track of what they already inserted.
function SuggestionPanel({
  status,
  suggestions,
  error,
  appliedIndices,
  onRequest,
  onApply,
}: {
  status: "idle" | "loading";
  suggestions: BlockSuggestion[] | null;
  error: string | null;
  appliedIndices: Set<number>;
  onRequest: () => void;
  onApply: (suggestion: BlockSuggestion, index: number) => void;
}) {
  const isLoading = status === "loading";
  const hasSuggestions = (suggestions?.length ?? 0) > 0;

  return (
    <div className="rounded-md border border-[color:var(--status-ai-border)] bg-[color:var(--status-ai-bg)] p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-[color:var(--text-ai)]">
          <Sparkle className="h-3 w-3" weight="fill" aria-hidden="true" />
          <span>Sugerencias de bloques</span>
        </div>
        <button
          type="button"
          onClick={onRequest}
          disabled={isLoading}
          className="inline-flex items-center gap-1 rounded-sm border border-[color:var(--text-ai)]/30 bg-transparent px-2 py-0.5 text-[11px] font-medium text-[color:var(--text-ai)] hover:bg-[color:var(--text-ai)]/10 disabled:opacity-50"
        >
          {isLoading ? (
            <CircleNotch
              className="h-3 w-3 animate-spin"
              weight="bold"
              aria-hidden="true"
            />
          ) : (
            <Sparkle className="h-3 w-3" weight="bold" aria-hidden="true" />
          )}
          {isLoading
            ? "Pensando…"
            : suggestions === null
              ? "Sugerir bloques"
              : "Pedir otra vez"}
        </button>
      </div>

      {error ? (
        <p className="text-[12px] text-[color:var(--status-error-text)]">{error}</p>
      ) : suggestions === null ? (
        <p className="text-[12px] text-[color:var(--text-primary)]">
          El copiloto propondrá entre 1 y 4 bloques que reforzarían el reporte
          tal como está. Cada propuesta es un borrador validado: lo aplicas con
          un clic y lo ordenas desde el lienzo.
        </p>
      ) : !hasSuggestions ? (
        <p className="text-[12px] text-[color:var(--text-primary)]">
          El copiloto no encontró bloques adicionales que aporten en este
          momento. Si crees que faltan datos, pídeselo con detalle en el chat.
        </p>
      ) : (
        <ul className="space-y-2">
          {suggestions.map((s, idx) => (
            <SuggestionCard
              key={`${s.type}-${idx}`}
              suggestion={s}
              applied={appliedIndices.has(idx)}
              onApply={() => onApply(s, idx)}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function SuggestionCard({
  suggestion,
  applied,
  onApply,
}: {
  suggestion: BlockSuggestion;
  applied: boolean;
  onApply: () => void;
}) {
  const def = getBlockDefinition(suggestion.type);
  // If a block in the registry was removed since the suggestion was
  // generated, gracefully degrade to a text-only card with the raw
  // type code rather than crashing the panel.
  const label = def?.label ?? suggestion.type;
  const Icon = def?.icon ?? Sparkle;
  return (
    <li className="rounded-sm border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] p-2">
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-start gap-2">
          <Icon
            className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[color:var(--text-secondary)]"
            weight="regular"
            aria-hidden="true"
          />
          <div className="min-w-0 space-y-0.5">
            <div className="text-[12px] font-medium text-[color:var(--text-primary)]">
              {label}
            </div>
            <p className="text-[11px] leading-relaxed text-[color:var(--text-secondary)]">
              {suggestion.rationale}
            </p>
          </div>
        </div>
        <Button
          type="button"
          size="sm"
          variant={applied ? "ghost" : "outline"}
          onClick={onApply}
          disabled={applied}
          aria-label={
            applied ? "Bloque aplicado" : `Aplicar ${label} al lienzo`
          }
        >
          <Plus className="h-3 w-3" weight="bold" aria-hidden="true" />
          {applied ? "Aplicado" : "Aplicar"}
        </Button>
      </div>
    </li>
  );
}

function cryptoUuid(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `block-${Math.random().toString(36).slice(2)}-${Date.now().toString(36)}`;
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
