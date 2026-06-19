/**
 * Legacy MOCK expediente inicial data.
 *
 * The live `/portal/onboarding` route now consumes the enriched backend
 * onboarding API directly. This file remains as a compatibility fixture
 * for older adapters/tests and should not be treated as the source of
 * truth for provider onboarding copy.
 */

import type { DocumentStateCode } from "@/lib/types";

export interface ExpedienteRequirement {
  /** Stable id for React keys and upload routing. */
  id: string;
  /** Backend requirement_code (REQ-ONB-xxx) where known. */
  requirement_code: string | null;
  /** Display name shown on the card. */
  name: string;
  /** Issuing institution code (matches Institution StrEnum). */
  institution: "sat" | "stps_repse" | "imss" | "infonavit" | "interno_cliente";
  /** Plain-language "why this matters" copy. */
  why: string;
  /** Accepted upload format. */
  format: string;
  /** Current REPSE state for this requirement. */
  state: DocumentStateCode;
  /** Plain-language action the provider should take next. */
  next_action: string;
  /** Reviewer-supplied rejection / clarification note. */
  reviewer_note?: string;
  /** Whether the requirement is hard-blocking (true) or optional (false). */
  required: boolean;
  /** Original PDF filename of the attached document, when one exists.
   *  Card shows this in the file box once uploaded; null = nothing
   *  attached yet, card shows the format hint instead. */
  filename?: string | null;
}

/**
 * Seed expediente inicial for the mock. Mix of states so we can
 * exercise every variant in the UI.
 */
export const MOCK_EXPEDIENTE: ExpedienteRequirement[] = [
  {
    id: "csf",
    requirement_code: "REQ-ONB-001",
    name: "Constancia de Situación Fiscal",
    institution: "sat",
    why: "Es la base para validar que tu RFC esté activo ante el SAT y que tu régimen permita facturar servicios especializados.",
    format: "PDF · descarga oficial desde el portal del SAT",
    state: "approved",
    next_action: "Listo. La revisaremos cada 90 días para mantenerla vigente.",
    required: true,
  },
  {
    id: "repse",
    requirement_code: "REQ-ONB-002",
    name: "Constancia REPSE vigente",
    institution: "stps_repse",
    why: "Sin un registro REPSE activo, tu cliente no puede contratarte para servicios especializados — es el documento más importante del expediente.",
    format: "PDF · acuse emitido por la STPS al renovar",
    state: "in_review",
    next_action: "Tu documento está en revisión humana. Te avisaremos por correo en menos de 24 horas hábiles.",
    required: true,
  },
  {
    id: "acta",
    requirement_code: "REQ-ONB-003",
    name: "Acta constitutiva",
    institution: "interno_cliente",
    why: "Demuestra la existencia legal de tu empresa y nos permite verificar el objeto social registrado para tu actividad.",
    format: "PDF · escaneo legible del documento original (sello notarial visible)",
    state: "uploaded",
    next_action: "Recibimos tu documento. Va a la cola de revisión.",
    required: true,
  },
  {
    id: "rfc-rep",
    requirement_code: "REQ-ONB-004",
    name: "RFC del representante legal",
    institution: "sat",
    why: "Nos ayuda a validar la identidad de quien firma los contratos en nombre de la empresa.",
    format: "PDF · Constancia de Situación Fiscal del representante",
    state: "rejected",
    next_action: "El archivo subido era del proveedor, no del representante legal. Vuelve a subir la CSF de la persona que firma.",
    reviewer_note: "El documento corresponde a la persona moral, no al representante legal nombrado en el acta.",
    required: true,
  },
  {
    id: "patronal",
    requirement_code: "REQ-ONB-005",
    name: "Registro patronal IMSS",
    institution: "imss",
    why: "Confirma que tienes una relación patronal activa con el IMSS y que tus trabajadores están dados de alta.",
    format: "PDF · Tarjeta de identificación patronal o constancia IDSE",
    state: "needs_review",
    next_action: "Detectamos un dato que no coincide. Revisa el documento subido y confirma si está bien.",
    reviewer_note: "El número de registro patronal parece corresponder a otra razón social.",
    required: true,
  },
  {
    id: "infonavit",
    requirement_code: "REQ-ONB-006",
    name: "Aviso de inscripción ante INFONAVIT",
    institution: "infonavit",
    why: "Acredita que tus trabajadores acceden a las prestaciones de vivienda exigidas por la ley.",
    format: "PDF · Aviso de inscripción emitido por INFONAVIT",
    state: "pending",
    next_action: "Sube este documento para destrabar tu expediente inicial.",
    required: true,
  },
  {
    id: "poliza",
    requirement_code: "REQ-ONB-007",
    name: "Póliza de seguros de riesgos de trabajo",
    institution: "interno_cliente",
    why: "Opcional para algunos giros, requerido cuando tu actividad implica trabajo de alto riesgo.",
    format: "PDF · Caratula vigente emitida por la aseguradora",
    state: "empty",
    next_action: "Si tu actividad lo requiere, sube la póliza vigente. Si no aplica, déjala así.",
    required: false,
  },
  {
    id: "contrato",
    requirement_code: "REQ-ONB-008",
    name: "Contrato firmado con el cliente",
    institution: "interno_cliente",
    why: "Cierra la relación comercial y deja registro del objeto del servicio, vigencia y responsable.",
    format: "PDF · Contrato escaneado con firmas autógrafas",
    state: "expired",
    next_action: "Tu contrato anterior venció. Sube la versión actualizada para mantener tu cumplimiento activo.",
    reviewer_note: "Vigencia 31-mar-2026.",
    required: true,
  },
];

/**
 * Counts that drive the gate.
 *
 * `is_gate_satisfied` is true when every required item is in
 * `approved` or `in_review` — meaning the provider has done their
 * part. The dashboard treats this as "you can move on".
 */
export interface ExpedienteCounts {
  total_required: number;
  completed: number;
  in_review: number;
  needs_action: number;
  optional_pending: number;
  completion_pct: number;
  is_gate_satisfied: boolean;
}

export function countExpediente(reqs: ExpedienteRequirement[]): ExpedienteCounts {
  const required = reqs.filter((r) => r.required);
  const total_required = required.length;
  const completed = required.filter((r) => r.state === "approved").length;
  const in_review = required.filter((r) =>
    ["uploaded", "in_review"].includes(r.state),
  ).length;
  const needs_action = required.filter((r) =>
    ["pending", "empty", "rejected", "expired", "possible_mismatch", "needs_review"].includes(r.state),
  ).length;
  const optional_pending = reqs.filter((r) => !r.required && r.state !== "approved").length;
  const completion_pct =
    total_required === 0
      ? 100
      : Math.round(((completed + in_review) / total_required) * 100);
  const is_gate_satisfied = needs_action === 0;
  return {
    total_required,
    completed,
    in_review,
    needs_action,
    optional_pending,
    completion_pct,
    is_gate_satisfied,
  };
}
