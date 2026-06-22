import { describe, expect, it } from "vitest";

import { ClientApiError } from "@/lib/api/client";
import { parseClientErrorCode } from "@/lib/api/error-detail";

function apiErr(status: number, detail: unknown): ClientApiError {
  return new ClientApiError(status, JSON.stringify({ detail }));
}

describe("parseClientErrorCode", () => {
  it("parses provider_limit_reached with limit/used", () => {
    const p = parseClientErrorCode(
      apiErr(409, {
        code: "provider_limit_reached",
        limit: 5,
        used: 5,
        message: "Tu plan permite un máximo de 5 proveedores activos.",
      }),
    );
    expect(p.code).toBe("provider_limit_reached");
    expect(p.limit).toBe(5);
    expect(p.used).toBe(5);
    expect(p.detail).toContain("máximo");
  });

  it("parses provider_archived with vendor_id", () => {
    const p = parseClientErrorCode(
      apiErr(409, {
        code: "provider_archived",
        vendor_id: "v1",
        message: "Ya tienes un proveedor archivado con ese RFC.",
      }),
    );
    expect(p.code).toBe("provider_archived");
    expect(p.vendor_id).toBe("v1");
  });

  it("parses plan_capability_required with capability", () => {
    const p = parseClientErrorCode(
      apiErr(403, {
        code: "plan_capability_required",
        capability: "bulk_export",
        message: "Esta funcionalidad requiere un plan de pago.",
      }),
    );
    expect(p.code).toBe("plan_capability_required");
    expect(p.capability).toBe("bulk_export");
  });

  it("falls back to the plain string detail (no code)", () => {
    const p = parseClientErrorCode(apiErr(400, "Mensaje simple."));
    expect(p.code).toBeUndefined();
    expect(p.detail).toBe("Mensaje simple.");
  });

  it("handles a non-JSON body", () => {
    const p = parseClientErrorCode(new ClientApiError(500, "boom"));
    expect(p.code).toBeUndefined();
    expect(p.detail).toBe("boom");
  });

  it("handles a non-ClientApiError", () => {
    const p = parseClientErrorCode(new Error("nope"));
    expect(p.code).toBeUndefined();
    expect(p.detail).toBe("nope");
  });
});
