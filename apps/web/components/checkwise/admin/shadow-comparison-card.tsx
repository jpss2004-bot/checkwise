"use client";

import * as React from "react";
import {
  CaretDown,
  CaretRight,
  CircleNotch,
  Robot,
  ShieldWarning,
  WarningCircle,
} from "@phosphor-icons/react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type {
  ShadowAnalysisPayload,
  ShadowAnalysisSignals,
} from "@/lib/api/portal";

/**
 * ShadowComparisonCard — admin-only "Comparación IA (interna)" card.
 *
 * Renders side-by-side the heuristic (regex) provider's signals against
 * Claude's shadow extraction. The card is hidden from the provider
 * portal entirely: this component is only mounted on the admin
 * reviewer detail page, and the backend's `shadow_analysis` block is
 * only returned by the reviewer endpoint.
 *
 * The card has four mutually-exclusive states:
 *   1. **Análisis pendiente** — shadow row exists but `shadow.completed_at`
 *      is null. The Claude BackgroundTask hasn't finished yet (or
 *      shadow mode is disabled and no run was scheduled).
 *   2. **Análisis no disponible** — `shadow.error` is set. We show the
 *      error code in plain Spanish.
 *   3. **Comparación lista** — both providers produced signals; show
 *      the per-field diff with disagreements highlighted.
 *   4. **Sin inspección** — payload itself is null; render nothing.
 *
 * The provider never sees this card. The card is a triage aid for the
 * legal team during the Phase-2 pilot — never a decision surface.
 */

const SHADOW_ERROR_LABELS: Record<string, string> = {
  timeout: "El análisis tardó más de lo permitido.",
  unsupported_size_or_type:
    "El archivo es demasiado grande o no es un PDF soportado por el modelo.",
  malformed_response: "El modelo devolvió una respuesta no válida.",
  daily_cap_exceeded:
    "Se alcanzó el límite diario de análisis para esta organización.",
};

function describeShadowError(code: string | null): string {
  if (!code) return "Sin detalle.";
  if (code in SHADOW_ERROR_LABELS) return SHADOW_ERROR_LABELS[code];
  if (code.startsWith("provider_error"))
    return "Error temporal del proveedor de IA.";
  if (code.startsWith("heuristic_error"))
    return "No se pudo procesar el documento con la heurística.";
  return "El análisis no pudo completarse.";
}

function fmtConfidence(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${Math.round(value * 100)}%`;
}

function fmtList(items: string[] | null | undefined): string {
  if (!items || items.length === 0) return "—";
  return items.join(", ");
}

function fmtString(value: string | null | undefined): string {
  if (!value) return "—";
  return value;
}

type Row = {
  label: string;
  heuristicValue: string;
  shadowValue: string;
  disagreement: boolean;
};

function buildRows(
  heuristic: ShadowAnalysisSignals,
  shadow: ShadowAnalysisSignals,
): Row[] {
  const rows: Array<Omit<Row, "disagreement">> = [
    {
      label: "Institución detectada",
      heuristicValue: fmtString(heuristic.detected_institution),
      shadowValue: fmtString(shadow.detected_institution),
    },
    {
      label: "Tipo de documento detectado",
      heuristicValue: fmtString(heuristic.detected_document_type),
      shadowValue: fmtString(shadow.detected_document_type),
    },
    {
      label: "RFC detectados",
      heuristicValue: fmtList(heuristic.detected_rfcs),
      shadowValue: fmtList(shadow.detected_rfcs),
    },
    {
      label: "Fechas detectadas",
      heuristicValue: fmtList(heuristic.detected_dates),
      shadowValue: fmtList(shadow.detected_dates),
    },
    {
      label: "Menciones de periodo",
      heuristicValue: fmtList(heuristic.period_mentions),
      shadowValue: fmtList(shadow.period_mentions),
    },
    {
      label: "Confianza de coincidencia",
      heuristicValue: fmtConfidence(heuristic.requirement_match_confidence),
      shadowValue: fmtConfidence(shadow.requirement_match_confidence),
    },
    {
      label: "Razón de no coincidencia",
      heuristicValue: fmtString(heuristic.mismatch_reason),
      shadowValue: fmtString(shadow.mismatch_reason),
    },
  ];

  return rows.map((row) => ({
    ...row,
    disagreement:
      row.heuristicValue !== row.shadowValue &&
      row.heuristicValue !== "—" &&
      row.shadowValue !== "—",
  }));
}

export function ShadowComparisonCard({
  payload,
}: {
  payload: ShadowAnalysisPayload | null | undefined;
}) {
  const [open, setOpen] = React.useState<boolean>(false);

  if (!payload) return null;

  const { heuristic, shadow } = payload;
  const isPending = shadow.completed_at === null && shadow.error === null;
  const hasError = shadow.error !== null;
  const hasSignals = shadow.signals !== null;

  const summary = (() => {
    if (isPending) return "Análisis pendiente";
    if (hasError) return "Análisis no disponible";
    if (!hasSignals) return "Sin señales registradas";
    const disagreements = buildRows(heuristic.signals, shadow.signals!).filter(
      (r) => r.disagreement,
    ).length;
    if (disagreements === 0) return "Sin diferencias significativas";
    return `${disagreements} diferencia${disagreements === 1 ? "" : "s"} detectada${
      disagreements === 1 ? "" : "s"
    }`;
  })();

  return (
    <Card data-internal="shadow-comparison">
      <CardHeader>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex w-full items-center justify-between text-left"
          aria-expanded={open}
        >
          <div className="flex items-center gap-2">
            <Robot
              className="h-4 w-4 text-[color:var(--text-tertiary)]"
              weight="duotone"
              aria-hidden
            />
            <CardTitle>Comparación IA (interna)</CardTitle>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-[color:var(--text-tertiary)]">
              {summary}
            </span>
            {open ? (
              <CaretDown
                className="h-4 w-4 text-[color:var(--text-tertiary)]"
                aria-hidden
              />
            ) : (
              <CaretRight
                className="h-4 w-4 text-[color:var(--text-tertiary)]"
                aria-hidden
              />
            )}
          </div>
        </button>
        <p className="mt-2 text-xs text-[color:var(--text-tertiary)]">
          Vista interna del equipo legal. No es visible para el proveedor.
          La decisión de cumplimiento sigue siendo manual.
        </p>
      </CardHeader>
      {open ? (
        <CardContent className="space-y-4">
          {isPending ? (
            <ShadowPending />
          ) : hasError ? (
            <ShadowError code={shadow.error} />
          ) : !hasSignals ? (
            <ShadowError code="malformed_response" />
          ) : (
            <ShadowDiffTable
              heuristic={heuristic.signals}
              shadow={shadow.signals!}
            />
          )}
          <ShadowFooter
            providerId={shadow.provider_id}
            promptVersion={shadow.prompt_version}
            latencyMs={shadow.latency_ms}
            completedAt={shadow.completed_at}
          />
        </CardContent>
      ) : null}
    </Card>
  );
}

function ShadowPending() {
  return (
    <div className="flex items-center gap-3 rounded-md border border-dashed border-[color:var(--border-subtle)] bg-[color:var(--bg-muted)] px-4 py-3 text-sm text-[color:var(--text-secondary)]">
      <CircleNotch
        className="h-4 w-4 animate-spin text-[color:var(--text-tertiary)]"
        aria-hidden
      />
      <span>
        Análisis pendiente — la corrida en sombra aún no termina o no se
        programó para este documento.
      </span>
    </div>
  );
}

function ShadowError({ code }: { code: string | null }) {
  return (
    <div className="flex items-start gap-3 rounded-md border border-[color:var(--status-warning-border,transparent)] bg-[color:var(--status-warning-bg,transparent)] px-4 py-3 text-sm">
      <WarningCircle
        className="mt-0.5 h-4 w-4 text-[color:var(--status-warning-text,var(--text-secondary))]"
        weight="fill"
        aria-hidden
      />
      <div>
        <p className="font-medium text-[color:var(--text-primary)]">
          Análisis IA no disponible
        </p>
        <p className="text-[color:var(--text-secondary)]">
          {describeShadowError(code)}
        </p>
        {code ? (
          <p className="mt-1 text-xs text-[color:var(--text-tertiary)]">
            Código técnico: <code>{code}</code>
          </p>
        ) : null}
      </div>
    </div>
  );
}

function ShadowDiffTable({
  heuristic,
  shadow,
}: {
  heuristic: ShadowAnalysisSignals;
  shadow: ShadowAnalysisSignals;
}) {
  const rows = buildRows(heuristic, shadow);
  return (
    <div className="overflow-hidden rounded-md border border-[color:var(--border-subtle)]">
      <table className="w-full text-left text-sm">
        <thead className="bg-[color:var(--bg-muted)] text-xs uppercase tracking-wide text-[color:var(--text-tertiary)]">
          <tr>
            <th className="px-3 py-2 font-medium">Campo</th>
            <th className="px-3 py-2 font-medium">Heurística</th>
            <th className="px-3 py-2 font-medium">IA en sombra</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={row.label}
              className={cn(
                i % 2 === 1 ? "bg-[color:var(--bg-muted)]/40" : "",
                row.disagreement
                  ? "border-l-2 border-l-[color:var(--status-warning-text,#d97706)]"
                  : "",
              )}
            >
              <td className="px-3 py-2 align-top text-[color:var(--text-secondary)]">
                <div className="flex items-center gap-1">
                  {row.disagreement ? (
                    <ShieldWarning
                      className="h-3.5 w-3.5 text-[color:var(--status-warning-text,#d97706)]"
                      weight="fill"
                      aria-label="Diferencia"
                    />
                  ) : null}
                  <span>{row.label}</span>
                </div>
              </td>
              <td className="px-3 py-2 align-top text-[color:var(--text-primary)]">
                {row.heuristicValue}
              </td>
              <td
                className={cn(
                  "px-3 py-2 align-top text-[color:var(--text-primary)]",
                  row.disagreement ? "font-medium" : "",
                )}
              >
                {row.shadowValue}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ShadowFooter({
  providerId,
  promptVersion,
  latencyMs,
  completedAt,
}: {
  providerId: string | null;
  promptVersion: string | null;
  latencyMs: number | null;
  completedAt: string | null;
}) {
  const parts: string[] = [];
  if (providerId) parts.push(providerId);
  if (promptVersion) parts.push(`prompt ${promptVersion}`);
  if (latencyMs !== null) parts.push(`${(latencyMs / 1000).toFixed(1)} s`);
  if (completedAt) {
    try {
      const date = new Date(completedAt);
      parts.push(date.toLocaleString("es-MX"));
    } catch {
      parts.push(completedAt);
    }
  }
  if (parts.length === 0) return null;
  return (
    <p className="text-xs text-[color:var(--text-tertiary)]">
      {parts.join(" · ")}
    </p>
  );
}
