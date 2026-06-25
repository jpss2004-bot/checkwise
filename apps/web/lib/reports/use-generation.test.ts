import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";

vi.mock("@/lib/session/admin", () => ({
  // Identity presence gates the request; the in-memory bearer rides in
  // via adminAuthHeader (FE-SEC-1 — no token in the persisted session).
  readAdminSession: () => ({
    user: { id: "u1" },
    roles: [],
    organization_ids: [],
    expires_at: "2999-01-01T00:00:00Z",
  }),
  adminAuthHeader: () => ({ Authorization: "Bearer test-token" }),
}));

import { useReportGeneration } from "@/lib/reports/use-generation";

function sseBody(frames: string[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const f of frames) controller.enqueue(enc.encode(f));
      controller.close();
    },
  });
}

const FRAMES = [
  `event: plan\ndata: ${JSON.stringify({
    plan: { blocks: [{ id: "b1", type: "executive_summary", config: {} }] },
  })}\n\n`,
  `event: ai_summary_delta\ndata: ${JSON.stringify({
    block_id: "b1",
    delta: "Hola ",
  })}\n\n`,
  `event: ai_summary_delta\ndata: ${JSON.stringify({
    block_id: "b1",
    delta: "mundo",
  })}\n\n`,
  `event: version_saved\ndata: ${JSON.stringify({
    version_id: "v1",
    version_number: 2,
  })}\n\n`,
  `event: done\ndata: ${JSON.stringify({})}\n\n`,
];

describe("useReportGeneration — batched streaming", () => {
  beforeEach(() => {
    // Run the rAF-coalesced flush synchronously so the test is deterministic.
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
      cb(0);
      return 1;
    });
    vi.stubGlobal("cancelAnimationFrame", () => {});
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        body: sseBody(FRAMES),
        text: async () => "",
      })),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("lands the full accumulated content on done (not a frame behind)", async () => {
    const { result } = renderHook(() => useReportGeneration("rep-1"));

    await act(async () => {
      await result.current.startGeneration("Resumen REPSE");
    });

    await waitFor(() => expect(result.current.state.status).toBe("done"));

    const blocks = result.current.state.content?.blocks ?? [];
    expect(blocks).toHaveLength(1);
    // The two deltas must both be present even though the terminal `done`
    // event cancels the pending coalesced flush — it carries the final
    // content synchronously.
    expect(blocks[0]?.ai_summary?.text).toBe("Hola mundo");
    expect(result.current.state.versionNumber).toBe(2);
  });
});
