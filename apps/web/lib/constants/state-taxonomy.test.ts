import { describe, expect, it } from "vitest";

import {
  RISK_LABEL,
  SEMAPHORE_DOT,
} from "@/components/checkwise/calendar/calendar-shared";

import {
  DocumentStatus,
  SEMAPHORE_DOT_CLASS,
  SemaphoreLevel,
  SlotState,
  documentStatusToSlotState,
  semaphoreLabel,
  slotStateLabel,
  slotStateVariant,
  statusLabel,
  statusVariant,
} from "./statuses";

/**
 * Taxonomy drift guard (state-vocabulary unification, 2026-06-19).
 *
 * Locks the THREE state axes to ONE vocabulary + ONE tone scale so a future
 * surface can't re-introduce the "rejected = Requiere corrección here but
 * Rechazado there, blue here but navy there" drift this consolidation removed.
 * If any axis is re-labelled or re-toned out of sync, one of these fails.
 */
describe("state taxonomy — one word + one tone per concept", () => {
  it("every DocumentStatus renders the same label as its SlotState projection", () => {
    for (const status of Object.values(DocumentStatus)) {
      const slot = documentStatusToSlotState(status);
      expect(statusLabel(status)).toBe(slotStateLabel(slot));
    }
  });

  it("every DocumentStatus shares the same tone as its SlotState projection", () => {
    for (const status of Object.values(DocumentStatus)) {
      const slot = documentStatusToSlotState(status);
      expect(statusVariant(status)).toBe(slotStateVariant(slot));
    }
  });

  it("the calendar reuses the canonical words for the shared (non-time) concepts", () => {
    // in_review / action_required / on_track are lifecycle concepts the
    // calendar shares with the rest of the portal — they MUST read identically.
    expect(RISK_LABEL.in_review).toBe(slotStateLabel(SlotState.IN_REVIEW));
    expect(RISK_LABEL.action_required).toBe(
      statusLabel(DocumentStatus.RECHAZADO),
    );
    expect(RISK_LABEL.on_track).toBe(semaphoreLabel("green"));
    // due_soon / upcoming are calendar-only (time) states and are intentionally
    // exempt — they have no lifecycle equivalent.
  });

  it("the semáforo dot tone is defined once and agrees across modules", () => {
    const levels: SemaphoreLevel[] = ["green", "yellow", "red"];
    for (const level of levels) {
      expect(SEMAPHORE_DOT_CLASS[level]).toBe(SEMAPHORE_DOT[level]);
    }
  });

  it("every slot state resolves to a non-empty label and a known tone", () => {
    const tones = new Set([
      "success",
      "warning",
      "info",
      "destructive",
      "secondary",
    ]);
    for (const state of Object.values(SlotState)) {
      expect(slotStateLabel(state).length).toBeGreaterThan(0);
      expect(tones.has(slotStateVariant(state))).toBe(true);
    }
  });
});
