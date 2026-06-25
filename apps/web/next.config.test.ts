import { afterEach, describe, expect, it, vi } from "vitest";

import nextConfig from "./next.config";

/**
 * CW-XSS-001 regression guard. Fails CI if anyone reverts CSP to global
 * report-only, re-adds 'unsafe-eval' in prod, or silently changes the
 * 'unsafe-inline' assumption that the un-nonced Next bootstrap relies on.
 */

type Header = { key: string; value: string };

async function headersFor(nodeEnv: string): Promise<Header[]> {
  vi.stubEnv("NODE_ENV", nodeEnv);
  try {
    const groups = await (
      nextConfig.headers as () => Promise<{ source: string; headers: Header[] }[]>
    )();
    return groups[0].headers;
  } finally {
    vi.unstubAllEnvs();
  }
}

function cspHeader(headers: Header[]): Header | undefined {
  return headers.find(
    (h) =>
      h.key === "Content-Security-Policy" ||
      h.key === "Content-Security-Policy-Report-Only",
  );
}

afterEach(() => vi.unstubAllEnvs());

describe("next.config CSP", () => {
  it("exposes an async headers() function", () => {
    expect(typeof nextConfig.headers).toBe("function");
  });

  it("ENFORCES CSP in production and drops unsafe-eval", async () => {
    const headers = await headersFor("production");
    const keys = headers.map((h) => h.key);
    expect(keys).toContain("Content-Security-Policy");
    expect(keys).not.toContain("Content-Security-Policy-Report-Only");

    const csp = cspHeader(headers)!.value;
    expect(csp).not.toContain("'unsafe-eval'");
    // 'unsafe-inline' must remain until a nonce is wired (documents intent).
    expect(csp).toContain("'unsafe-inline'");
    // These directives now actually enforce in prod.
    expect(csp).toContain("object-src 'none'");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("base-uri 'self'");
  });

  it("stays REPORT-ONLY in dev and keeps unsafe-eval for the overlay", async () => {
    const headers = await headersFor("development");
    const keys = headers.map((h) => h.key);
    expect(keys).toContain("Content-Security-Policy-Report-Only");
    expect(keys).not.toContain("Content-Security-Policy");
    expect(cspHeader(headers)!.value).toContain("'unsafe-eval'");
  });
});
