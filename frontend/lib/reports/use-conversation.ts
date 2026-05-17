"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { readAdminSession } from "@/lib/session/admin";

/**
 * Hook: useReportConversation.
 *
 * Manages the right-rail copilot chat for one report. Reads existing
 * conversation history on mount + appends new turns + streams the
 * assistant's reply via SSE.
 *
 * State shape:
 *   - turns: ordered list of {role, kind, markdown, ...}
 *   - status: idle | loading | sending | streaming | error
 *   - error: optional error message
 */

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export type ConversationRole = "user" | "assistant" | "system" | "tool";

export interface ConversationTurn {
  id: string;
  turn_number: number;
  role: ConversationRole;
  /** Text-shaped turn content (the only kind 3.3c persists). */
  markdown: string;
  isStreaming?: boolean;
}

export type ConversationStatus =
  | "idle"
  | "loading"
  | "sending"
  | "streaming"
  | "error";

interface UseReportConversation {
  turns: ConversationTurn[];
  status: ConversationStatus;
  error: string | null;
  send: (message: string, canvasSummary?: unknown) => Promise<void>;
  reload: () => Promise<void>;
}

export function useReportConversation(reportId: string): UseReportConversation {
  const [turns, setTurns] = useState<ConversationTurn[]>([]);
  const [status, setStatus] = useState<ConversationStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const reload = useCallback(async () => {
    const session = readAdminSession();
    if (!session?.access_token || !reportId) return;
    setStatus("loading");
    setError(null);
    try {
      const resp = await fetch(
        `${API_BASE_URL}/api/v1/reports/${reportId}/conversation`,
        { headers: { Authorization: `Bearer ${session.access_token}` } },
      );
      if (!resp.ok) {
        setStatus("error");
        setError(`Error ${resp.status} cargando conversación.`);
        return;
      }
      const data = (await resp.json()) as {
        items: Array<{
          id: string;
          turn_number: number;
          role: ConversationRole;
          content: { kind: string; markdown?: string };
        }>;
      };
      setTurns(
        data.items
          .filter((t) => t.content?.kind === "text")
          .map((t) => ({
            id: t.id,
            turn_number: t.turn_number,
            role: t.role,
            markdown: t.content.markdown ?? "",
          })),
      );
      setStatus("idle");
    } catch (e) {
      setStatus("error");
      setError(e instanceof Error ? e.message : "Error de red.");
    }
  }, [reportId]);

  useEffect(() => {
    reload();
  }, [reload]);

  // Auto-cancel any in-flight SSE on unmount.
  useEffect(
    () => () => {
      if (abortRef.current) abortRef.current.abort();
    },
    [],
  );

  const send = useCallback(
    async (message: string, canvasSummary?: unknown) => {
      const session = readAdminSession();
      if (!session?.access_token || !reportId || !message.trim()) return;

      // Optimistic user turn.
      const optimisticUserTurn: ConversationTurn = {
        id: `temp-user-${Date.now()}`,
        turn_number: (turns[turns.length - 1]?.turn_number ?? 0) + 1,
        role: "user",
        markdown: message.trim(),
      };
      // Streaming assistant placeholder.
      const optimisticAssistantTurn: ConversationTurn = {
        id: `temp-asst-${Date.now()}`,
        turn_number: optimisticUserTurn.turn_number + 1,
        role: "assistant",
        markdown: "",
        isStreaming: true,
      };
      setTurns((prev) => [...prev, optimisticUserTurn, optimisticAssistantTurn]);
      setStatus("sending");
      setError(null);

      const ctrl = new AbortController();
      abortRef.current = ctrl;

      let resp: Response;
      try {
        resp = await fetch(
          `${API_BASE_URL}/api/v1/reports/${reportId}/conversation`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${session.access_token}`,
              Accept: "text/event-stream",
            },
            body: JSON.stringify({
              message: message.trim(),
              canvas_summary: canvasSummary,
            }),
            signal: ctrl.signal,
          },
        );
      } catch (e) {
        if (ctrl.signal.aborted) return;
        setStatus("error");
        setError(e instanceof Error ? e.message : "Red caída.");
        return;
      }

      if (!resp.ok || !resp.body) {
        const detail = await resp.text().catch(() => "");
        setStatus("error");
        setError(`Error ${resp.status}: ${detail}`);
        return;
      }

      setStatus("streaming");
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      let accumulated = "";

      try {
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          let boundary = buf.indexOf("\n\n");
          while (boundary !== -1) {
            const raw = buf.slice(0, boundary);
            buf = buf.slice(boundary + 2);
            const ev = parseSseFrame(raw);
            if (ev?.event === "delta") {
              const delta = (ev.data.text as string) ?? "";
              accumulated += delta;
              const snapshot = accumulated;
              setTurns((prev) =>
                prev.map((t) =>
                  t.id === optimisticAssistantTurn.id
                    ? { ...t, markdown: snapshot }
                    : t,
                ),
              );
            } else if (ev?.event === "turn_complete") {
              const turn = (ev.data as { turn: { id: string; turn_number: number } }).turn;
              setTurns((prev) =>
                prev.map((t) =>
                  t.id === optimisticAssistantTurn.id
                    ? {
                        ...t,
                        id: turn.id,
                        turn_number: turn.turn_number,
                        isStreaming: false,
                      }
                    : t,
                ),
              );
            } else if (ev?.event === "error") {
              setStatus("error");
              setError((ev.data.message as string) ?? "Error del copiloto.");
            }
            boundary = buf.indexOf("\n\n");
          }
        }
        setStatus("idle");
      } catch (e) {
        if (ctrl.signal.aborted) return;
        setStatus("error");
        setError(e instanceof Error ? e.message : "Stream interrumpido.");
      } finally {
        if (abortRef.current === ctrl) abortRef.current = null;
      }
    },
    [reportId, turns],
  );

  return { turns, status, error, send, reload };
}

function parseSseFrame(raw: string): { event: string; data: Record<string, unknown> } | null {
  let event = "";
  const dataLines: string[] = [];
  for (const line of raw.split("\n")) {
    if (!line) continue;
    if (line.startsWith("event: ")) event = line.slice(7).trim();
    else if (line.startsWith("data: ")) dataLines.push(line.slice(6));
  }
  if (!event || dataLines.length === 0) return null;
  try {
    return { event, data: JSON.parse(dataLines.join("\n")) };
  } catch {
    return null;
  }
}
