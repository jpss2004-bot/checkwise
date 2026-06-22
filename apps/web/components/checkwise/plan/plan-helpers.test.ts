import { describe, expect, it } from "vitest";

import { daysUntil } from "@/components/checkwise/plan/demo-countdown";
import { usageTone } from "@/components/checkwise/plan/usage-meter";

describe("usageTone", () => {
  it("is success under 80%", () => {
    expect(usageTone(0)).toBe("success");
    expect(usageTone(79)).toBe("success");
  });
  it("is warning between 80 and 99%", () => {
    expect(usageTone(80)).toBe("warning");
    expect(usageTone(99)).toBe("warning");
  });
  it("is error at 100% and over", () => {
    expect(usageTone(100)).toBe("error");
    expect(usageTone(140)).toBe("error");
  });
});

describe("daysUntil", () => {
  const now = new Date("2026-06-22T00:00:00Z").getTime();
  it("counts whole days ahead", () => {
    expect(daysUntil("2026-06-29T00:00:00Z", now)).toBe(7);
  });
  it("is <= 0 once the deadline has passed", () => {
    expect(daysUntil("2026-06-21T00:00:00Z", now)).toBeLessThanOrEqual(0);
  });
});
