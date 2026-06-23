import { describe, expect, it } from "vitest";

import {
  cadenceLabel,
  entityStatusLabel,
  entityStatusVariant,
  personaLabel,
  riskLabel,
  riskVariant,
  roleLabel,
  roleLabels,
} from "./labels";

describe("roleLabel", () => {
  it("maps known membership roles to Spanish", () => {
    expect(roleLabel("operations_admin")).toBe("Administrador de operaciones");
    expect(roleLabel("platform_admin")).toBe("Equipo CheckWise");
    expect(roleLabel("client_admin")).toBe("Administrador del cliente");
    expect(roleLabel("client_viewer")).toBe("Solo lectura");
  });

  it("humanises unknown role codes instead of leaking raw snake_case", () => {
    expect(roleLabel("some_new_role")).toBe("Some new role");
  });

  it("joins a list of roles", () => {
    expect(roleLabels(["operations_admin", "platform_admin"])).toBe(
      "Administrador de operaciones, Equipo CheckWise",
    );
  });
});

describe("personaLabel", () => {
  it("maps persona codes", () => {
    expect(personaLabel("moral")).toBe("Persona moral");
    expect(personaLabel("fisica")).toBe("Persona física");
  });

  it("returns an em-dash-free placeholder for null", () => {
    expect(personaLabel(null)).toBe("—");
    expect(personaLabel(undefined)).toBe("—");
  });
});

describe("riskLabel / riskVariant", () => {
  it("maps both English and Spanish risk codes to one Spanish label", () => {
    expect(riskLabel("medium")).toBe("Medio");
    expect(riskLabel("alto")).toBe("Alto");
    expect(riskLabel("low")).toBe("Bajo");
    expect(riskLabel("critical")).toBe("Crítico");
  });

  it("picks a badge variant per canonical bucket", () => {
    expect(riskVariant("low")).toBe("success");
    expect(riskVariant("alto")).toBe("destructive");
    expect(riskVariant("unknown")).toBe("outline");
  });
});

describe("cadenceLabel", () => {
  it("prettifies the backend cadence vocabulary", () => {
    expect(cadenceLabel("mensual")).toBe("Mensual");
    expect(cadenceLabel("alta_inicial")).toBe("Alta inicial");
    expect(cadenceLabel("unica_vez")).toBe("Única vez");
  });

  it("humanises unknown cadence codes", () => {
    expect(cadenceLabel("trimestral_especial")).toBe("Trimestral especial");
  });
});

describe("entityStatusLabel / entityStatusVariant", () => {
  it("maps entity status to Spanish + variant", () => {
    expect(entityStatusLabel("active")).toBe("Activo");
    expect(entityStatusLabel("inactive")).toBe("Inactivo");
    expect(entityStatusVariant("active")).toBe("success");
    expect(entityStatusVariant("suspended")).toBe("warning");
  });

  it("falls back to outline for unknown status", () => {
    expect(entityStatusVariant("frozen")).toBe("outline");
    expect(entityStatusLabel("frozen")).toBe("Frozen");
  });
});
