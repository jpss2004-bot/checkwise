import { describe, expect, it } from "vitest";

import {
  ACTIVITY_ACTION_LABELS_ES,
  ACTIVITY_ACTOR_LABELS_ES,
  activityActionLabel,
  activityActorLabel,
} from "./activity-labels";

// Locks the client Activity audit-trail vocabulary to its canonical
// Spanish labels (audit P2.13). The /client/activity endpoint emits these
// exact tokens; if the backend adds a new one, add the ES label here too.
describe("activity audit-trail labels", () => {
  it("maps every actor token the backend emits", () => {
    for (const token of ["supplier", "reviewer", "system", "client_admin"]) {
      expect(ACTIVITY_ACTOR_LABELS_ES[token]).toBeTruthy();
    }
  });

  it("maps every action token the activity feed emits", () => {
    for (const token of [
      "submission.uploaded",
      "reviewer.decision",
      "submission.replacement_linked",
      "submission.replaced",
      "metadata.ready",
      "metadata.pending",
    ]) {
      expect(ACTIVITY_ACTION_LABELS_ES[token]).toBeTruthy();
    }
  });

  it("never echoes a raw dotted/underscored machine token", () => {
    expect(activityActionLabel("submission.uploaded")).toBe("Carga de documento");
    expect(activityActorLabel("supplier")).toBe("Proveedor");
    // Unknown tokens degrade to a humanized label, never the raw dotted form.
    expect(activityActionLabel("future.unknown_event")).not.toContain(".");
    expect(activityActionLabel("future.unknown_event")).not.toContain("_");
  });
});
