import { describe, expect, it } from "vitest";

import { isClientApprover } from "./client-tier";

/**
 * Phase 4 — the client seat-tier predicate that gates every client-portal
 * write affordance (add/archive provider, edit profile, generate report).
 * It is defense-in-depth — the backend ``ClientApprover`` gate is the real
 * boundary — but a regression here would silently re-expose write buttons
 * to read-only Viewers, so the role→tier mapping is pinned exactly.
 */
describe("isClientApprover", () => {
  it("treats client_admin (Approver) as a writer", () => {
    expect(isClientApprover(["client_admin"])).toBe(true);
  });

  it("treats internal_admin (support) as a writer", () => {
    expect(isClientApprover(["internal_admin"])).toBe(true);
  });

  it("does NOT treat client_viewer (Viewer) as a writer", () => {
    expect(isClientApprover(["client_viewer"])).toBe(false);
  });

  it("grants write when an Approver role sits alongside a Viewer role", () => {
    // A user holding both seats writes via the Approver row — the Viewer
    // membership never downgrades them.
    expect(isClientApprover(["client_viewer", "client_admin"])).toBe(true);
  });

  it("is read-only for unrelated roles (e.g. reviewer/provider)", () => {
    expect(isClientApprover(["reviewer"])).toBe(false);
    expect(isClientApprover(["provider"])).toBe(false);
  });

  it("fails closed on empty or undefined roles", () => {
    expect(isClientApprover([])).toBe(false);
    expect(isClientApprover(undefined)).toBe(false);
  });
});
