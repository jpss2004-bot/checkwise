/**
 * MOCK REPSE calendar data.
 *
 * One row per (year, month, institution, obligation). Mirrors the
 * Árbol Plataforma Proveedores REPSE structure: monthly SAT + IMSS,
 * bimonthly INFONAVIT, four-monthly STPS acuses, and the annual ISR
 * declaration.
 *
 * TODO[backend-integration]: Replace with the existing
 * /api/v1/portal/calendar response shape once it's been enriched with
 * the per-deadline drawer metadata (suggested_action, etc.).
 */

import type { DocumentStateCode } from "@/lib/types";

export type CalendarInstitution = "sat" | "imss" | "infonavit" | "stps_repse";

export interface CalendarEvent {
  id: string;
  year: number;
  /** 1–12. */
  month: number;
  institution: CalendarInstitution;
  /** Display name shown on the cell + drawer header. */
  obligation: string;
  /** Required document name shown in the drawer. */
  required_document: string;
  /** Deadline ISO date (YYYY-MM-DD). */
  deadline_iso: string;
  /** Current REPSE state for this slot. */
  state: DocumentStateCode;
  /** Plain-language suggested action. */
  suggested_action: string;
  /** Frequency tag. */
  frequency: "monthly" | "bimonthly" | "four_monthly" | "annual";
}

export const INSTITUTION_LABELS: Record<CalendarInstitution, string> = {
  sat: "SAT",
  imss: "IMSS",
  infonavit: "INFONAVIT",
  stps_repse: "STPS / REPSE",
};

export const MONTH_LABELS = [
  "Enero",
  "Febrero",
  "Marzo",
  "Abril",
  "Mayo",
  "Junio",
  "Julio",
  "Agosto",
  "Septiembre",
  "Octubre",
  "Noviembre",
  "Diciembre",
];

export const MONTH_LABELS_SHORT = [
  "Ene",
  "Feb",
  "Mar",
  "Abr",
  "May",
  "Jun",
  "Jul",
  "Ago",
  "Sep",
  "Oct",
  "Nov",
  "Dic",
];

function eventId(parts: (string | number)[]) {
  return parts.map(String).join("-");
}

/**
 * Build the 2026 mock calendar — a representative slice rather than
 * the full 100+ rows the real catalog produces.
 */
function buildMockCalendar(year: number): CalendarEvent[] {
  const events: CalendarEvent[] = [];

  // Monthly SAT (Opinión de Cumplimiento + Declaración IVA)
  for (let month = 1; month <= 12; month++) {
    const past = month < 5;
    const current = month === 5;
    const state: DocumentStateCode = past
      ? month === 3
        ? "rejected"
        : "approved"
      : current
        ? "pending"
        : "empty";
    events.push({
      id: eventId(["sat", year, month, "iva"]),
      year,
      month,
      institution: "sat",
      obligation: "Opinión de Cumplimiento SAT",
      required_document: "Opinión de Cumplimiento mensual (formato 32-D)",
      deadline_iso: `${year}-${String(month).padStart(2, "0")}-17`,
      state,
      suggested_action:
        state === "rejected"
          ? "El revisor pidió que vuelvas a descargar la opinión vigente."
          : state === "pending"
            ? "Descarga la opinión desde el portal del SAT y súbela aquí."
            : state === "approved"
              ? "Listo. Lo revisaremos el próximo periodo."
              : "Sube tu Opinión cuando esté disponible.",
      frequency: "monthly",
    });
  }

  // Monthly IMSS (Comprobante de pago de cuotas)
  for (let month = 1; month <= 12; month++) {
    const past = month < 5;
    const current = month === 5;
    const state: DocumentStateCode = past
      ? "approved"
      : current
        ? "pending"
        : "empty";
    events.push({
      id: eventId(["imss", year, month, "comp"]),
      year,
      month,
      institution: "imss",
      obligation: "Comp. de pago de cuotas IMSS",
      required_document: "Comprobante de pago bancario + CFDI",
      deadline_iso: `${year}-${String(month).padStart(2, "0")}-17`,
      state,
      suggested_action:
        state === "pending"
          ? "Confirma el pago a IMSS y sube el comprobante."
          : state === "approved"
            ? "Sin pendientes."
            : "Sube cuando tengas el comprobante del periodo.",
      frequency: "monthly",
    });
  }

  // Bimonthly INFONAVIT (Cuotas obrero-patronales)
  for (const period of [1, 3, 5, 7, 9, 11]) {
    const past = period < 5;
    const current = period === 5;
    const state: DocumentStateCode = past
      ? "approved"
      : current
        ? "uploaded"
        : "empty";
    events.push({
      id: eventId(["infonavit", year, period, "cuotas"]),
      year,
      month: period,
      institution: "infonavit",
      obligation: "Cuotas obrero-patronales INFONAVIT",
      required_document: "Resumen de liquidación bimestral",
      deadline_iso: `${year}-${String(period).padStart(2, "0")}-17`,
      state,
      suggested_action:
        state === "uploaded"
          ? "Recibimos tu documento. Está en cola de revisión."
          : state === "approved"
            ? "Sin pendientes."
            : "Sube tu resumen bimestral.",
      frequency: "bimonthly",
    });
  }

  // Four-monthly STPS (Acuse ICSOE)
  for (const period of [1, 5, 9]) {
    const past = period < 5;
    const current = period === 5;
    const state: DocumentStateCode = past
      ? "approved"
      : current
        ? "in_review"
        : "empty";
    events.push({
      id: eventId(["stps", year, period, "icsoe"]),
      year,
      month: period,
      institution: "stps_repse",
      obligation: "Acuse ICSOE cuatrimestral",
      required_document: "Acuse de envío ICSOE emitido por STPS",
      deadline_iso: `${year}-${String(period).padStart(2, "0")}-17`,
      state,
      suggested_action:
        state === "in_review"
          ? "Tu acuse está en revisión humana."
          : state === "approved"
            ? "Aprobado."
            : "Sube tu acuse al cierre del cuatrimestre.",
      frequency: "four_monthly",
    });
  }

  // Annual: Declaración anual ISR
  events.push({
    id: eventId(["sat", year, 3, "isr-anual"]),
    year,
    month: 3,
    institution: "sat",
    obligation: "Declaración anual ISR",
    required_document: "Acuse de declaración anual",
    deadline_iso: `${year}-03-31`,
    state: "approved",
    suggested_action: "Listo. La próxima toca el año entrante.",
    frequency: "annual",
  });

  return events;
}

export const MOCK_CALENDAR_2026: CalendarEvent[] = buildMockCalendar(2026);
