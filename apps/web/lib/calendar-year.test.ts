import { describe, expect, it } from "vitest";

import {
  CALENDAR_MAX_YEAR,
  CALENDAR_MIN_YEAR,
  parseCalendarYear,
} from "./calendar-year";

describe("parseCalendarYear", () => {
  const currentYear = new Date().getFullYear();

  // Regression — prod bug 2026-06-12: a bare /client/calendar visit
  // (no ?year= param) defaulted to 2021 because Number(null) is 0,
  // which is finite, so the clamp floored it to CALENDAR_MIN_YEAR
  // instead of taking the current-year fallback.
  it("defaults to the current year when the param is missing", () => {
    expect(parseCalendarYear(null)).toBe(currentYear);
  });

  it("defaults to the current year when the param is empty or blank", () => {
    expect(parseCalendarYear("")).toBe(currentYear);
    expect(parseCalendarYear("   ")).toBe(currentYear);
  });

  it("defaults to the current year when the param is not a number", () => {
    expect(parseCalendarYear("abc")).toBe(currentYear);
    expect(parseCalendarYear("20x6")).toBe(currentYear);
  });

  it("passes through an explicit in-range year", () => {
    expect(parseCalendarYear("2021")).toBe(2021);
    expect(parseCalendarYear("2026")).toBe(2026);
    expect(parseCalendarYear("2030")).toBe(2030);
  });

  it("truncates fractional input", () => {
    expect(parseCalendarYear("2026.9")).toBe(2026);
  });

  it("clamps out-of-range years to the UI bounds", () => {
    expect(parseCalendarYear("1999")).toBe(CALENDAR_MIN_YEAR);
    expect(parseCalendarYear("2099")).toBe(CALENDAR_MAX_YEAR);
  });
});
