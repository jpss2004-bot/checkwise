import { describe, expect, it } from "vitest";

import {
  SLOT_STATE_LABELS_ES,
  SlotState,
  type SlotStateCode,
} from "@/lib/constants/statuses";
import type { DocumentStateCode } from "@/lib/types";

import { DOC_STATE_LABELS } from "./doc-state-badge";
import { STATE_LABEL_FALLBACK } from "./portal/evidence-slot-card";

/**
 * CW-03 taxonomy guard.
 *
 * Per-document state lives in two parallel vocabularies: the frontend
 * `DocumentStateCode` used by the badge components, and the backend-projected
 * `SlotStateCode` in lib/constants/statuses. Their *codes* differ (empty /
 * pending / needs_review vs missing / needs_correction / …), but the Spanish
 * *labels* for the corresponding concept MUST read identically — otherwise the
 * calendar, submissions, expediente grid and reports show two words for one
 * state (digitized-notes finding CW-03). The maps were hand-synced on
 * 2026-06-10 with nothing stopping them from drifting again. This is that stop.
 */
const DOC_STATE_TO_SLOT: Record<DocumentStateCode, SlotStateCode> = {
  empty: SlotState.MISSING,
  pending: SlotState.MISSING,
  uploaded: SlotState.UPLOADED,
  in_review: SlotState.IN_REVIEW,
  approved: SlotState.APPROVED,
  rejected: SlotState.REJECTED,
  expired: SlotState.EXPIRED,
  needs_review: SlotState.NEEDS_CORRECTION,
};

describe("CW-03 — per-document state label vocabulary stays unified", () => {
  const docStates = Object.keys(DOC_STATE_TO_SLOT) as DocumentStateCode[];

  it.each(docStates)(
    "DOC_STATE_LABELS[%s] reads the same word as the canonical slot label",
    (state) => {
      expect(DOC_STATE_LABELS[state]).toBe(
        SLOT_STATE_LABELS_ES[DOC_STATE_TO_SLOT[state]],
      );
    },
  );

  it("the provider slot-card fallback labels match the badge labels exactly", () => {
    // Two byte-identical maps today; locking them means a change to one is a
    // deliberate change to both, never silent drift.
    expect(STATE_LABEL_FALLBACK).toEqual(DOC_STATE_LABELS);
  });
});
