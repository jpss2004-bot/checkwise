"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { readAdminSession } from "@/lib/session/admin";
import type { ReportBlock, ReportContent } from "@/lib/api/reports";

/**
 * Hook: useReportGeneration.
 *
 * Consumes the SSE stream from POST /api/v1/reports/{id}/generate and
 * hydrates the canvas block-by-block. The hook is fetch-based (not
 * EventSource) because EventSource is GET-only — the generate endpoint
 * needs a POST body. We use fetch + a ReadableStream reader to parse
 * SSE framing ourselves.
 *
 * Surface:
 *   const { content, status, error, startGeneration, cancel } =
 *     useReportGeneration(reportId);
 *
 *   await startGeneration("Resumen REPSE de mayo");
 *
 * `content` is the live canvas tree, mutated as events arrive.
 * `status` is one of:
 *   idle              before startGeneration runs
 *   planning          waiting for first 'plan' event
 *   streaming         actively receiving block events
 *   saving            stream complete, waiting for version_saved
 *   done              stream cleanly closed
 *   error             explicit failure
 *   cancelled         caller invoked cancel()
 *
 * Events accumulate into the canvas in plan order. The stale-skeleton
 * → block_data → ai_summary_delta → block_complete sequence drives
 * progressive UI hydration in the Canvas component.
 */

export type GenerationStatus =
  | "idle"
  | "planning"
  | "streaming"
  | "saving"
  | "done"
  | "error"
  | "cancelled";

export interface GenerationState {
  content: ReportContent | null;
  status: GenerationStatus;
  error: string | null;
  versionId: string | null;
  versionNumber: number | null;
}

interface UseReportGeneration {
  state: GenerationState;
  startGeneration: (prompt: string, period?: string) => Promise<void>;
  cancel: () => void;
  reset: () => void;
}

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export function useReportGeneration(reportId: string): UseReportGeneration {
  const [state, setState] = useState<GenerationState>({
    content: null,
    status: "idle",
    error: null,
    versionId: null,
    versionNumber: null,
  });

  const abortRef = useRef<AbortController | null>(null);
  // Mutable content buffer — keeps the React state immutable while
  // the SSE handler accumulates updates fast.
  const contentRef = useRef<ReportContent | null>(null);

  const cancel = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    setState((s) => ({ ...s, status: "cancelled" }));
  }, []);

  const reset = useCallback(() => {
    cancel();
    contentRef.current = null;
    setState({
      content: null,
      status: "idle",
      error: null,
      versionId: null,
      versionNumber: null,
    });
  }, [cancel]);

  // Auto-cancel on unmount.
  useEffect(
    () => () => {
      if (abortRef.current) abortRef.current.abort();
    },
    [],
  );

  const startGeneration = useCallback(
    async (prompt: string, period?: string) => {
      const session = readAdminSession();
      if (!session?.access_token) {
        setState((s) => ({
          ...s,
          status: "error",
          error: "No hay sesión activa.",
        }));
        return;
      }

      const ctrl = new AbortController();
      abortRef.current = ctrl;

      contentRef.current = { schema_version: 1, blocks: [], global: {} };
      setState({
        content: contentRef.current,
        status: "planning",
        error: null,
        versionId: null,
        versionNumber: null,
      });

      let resp: Response;
      try {
        resp = await fetch(
          `${API_BASE_URL}/api/v1/reports/${reportId}/generate`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${session.access_token}`,
              Accept: "text/event-stream",
            },
            body: JSON.stringify({
              prompt,
              period: period ?? null,
            }),
            signal: ctrl.signal,
          },
        );
      } catch (e) {
        if (ctrl.signal.aborted) return;
        setState((s) => ({
          ...s,
          status: "error",
          error:
            e instanceof Error ? e.message : "Conexión al motor de IA falló.",
        }));
        return;
      }

      if (!resp.ok || !resp.body) {
        const detail = await resp.text().catch(() => "");
        setState((s) => ({
          ...s,
          status: "error",
          error: `Error ${resp.status}: ${detail}`,
        }));
        return;
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      try {
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          // SSE events are delimited by blank lines.
          let boundary = buffer.indexOf("\n\n");
          while (boundary !== -1) {
            const raw = buffer.slice(0, boundary);
            buffer = buffer.slice(boundary + 2);
            handleFrame(raw, contentRef, setState);
            boundary = buffer.indexOf("\n\n");
          }
        }
      } catch (e) {
        if (ctrl.signal.aborted) return;
        setState((s) => ({
          ...s,
          status: "error",
          error: e instanceof Error ? e.message : "Stream interrumpido.",
        }));
      } finally {
        if (abortRef.current === ctrl) abortRef.current = null;
      }
    },
    [reportId],
  );

  return { state, startGeneration, cancel, reset };
}

// ─── Frame handler ──────────────────────────────────────────────

function handleFrame(
  raw: string,
  contentRef: React.MutableRefObject<ReportContent | null>,
  setState: React.Dispatch<React.SetStateAction<GenerationState>>,
): void {
  let event = "";
  const dataLines: string[] = [];
  for (const line of raw.split("\n")) {
    if (!line) continue;
    if (line.startsWith("event: ")) {
      event = line.slice(7).trim();
    } else if (line.startsWith("data: ")) {
      dataLines.push(line.slice(6));
    }
  }
  if (!event || dataLines.length === 0) return;
  let payload: Record<string, unknown>;
  try {
    payload = JSON.parse(dataLines.join("\n"));
  } catch {
    return;
  }
  applyEvent(event, payload, contentRef, setState);
}

function applyEvent(
  event: string,
  payload: Record<string, unknown>,
  contentRef: React.MutableRefObject<ReportContent | null>,
  setState: React.Dispatch<React.SetStateAction<GenerationState>>,
): void {
  const c = contentRef.current;
  if (!c) return;

  switch (event) {
    case "plan": {
      const plan = (payload.plan as
        | { blocks: Array<{ id: string; type: string; config: unknown }> }
        | undefined) ?? { blocks: [] };
      c.blocks = plan.blocks.map((b) => ({
        id: b.id,
        type: b.type,
        config: b.config as ReportBlock["config"],
        data: undefined,
        ai_summary: null,
        layout: { width: "full" as const },
      }));
      // Snapshot the new array for React.
      contentRef.current = { ...c, blocks: [...c.blocks] };
      setState((s) => ({ ...s, content: contentRef.current, status: "streaming" }));
      break;
    }
    case "block_start": {
      // No-op — block is already present from the plan event. The
      // canvas can use this signal to flip a "loading" flag if we
      // expose one later.
      break;
    }
    case "block_data": {
      const blockId = payload.block_id as string;
      const block = c.blocks.find((b) => b.id === blockId);
      if (block) {
        block.data = payload.data;
        contentRef.current = { ...c, blocks: [...c.blocks] };
        setState((s) => ({ ...s, content: contentRef.current }));
      }
      break;
    }
    case "ai_summary_delta": {
      const blockId = payload.block_id as string;
      const delta = (payload.delta as string) ?? "";
      const block = c.blocks.find((b) => b.id === blockId);
      if (block) {
        const existing = block.ai_summary?.text ?? "";
        block.ai_summary = {
          ...(block.ai_summary ?? {
            model: "",
            prompt_hash: "",
            generated_at: new Date().toISOString(),
            source_snapshot_id: "",
          }),
          text: existing + delta,
        };
        contentRef.current = { ...c, blocks: [...c.blocks] };
        setState((s) => ({ ...s, content: contentRef.current }));
      }
      break;
    }
    case "block_complete": {
      // No-op — content for this block is already accumulated. We
      // could clear a per-block loading flag here if we expose one.
      break;
    }
    case "version_saved": {
      setState((s) => ({
        ...s,
        status: "saving",
        versionId: (payload.version_id as string) ?? null,
        versionNumber: (payload.version_number as number) ?? null,
      }));
      break;
    }
    case "done": {
      setState((s) => ({ ...s, status: "done" }));
      break;
    }
    case "error": {
      const msg = (payload.message as string) ?? "Error de generación";
      setState((s) => ({ ...s, status: "error", error: msg }));
      break;
    }
  }
}
