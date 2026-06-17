"use client";

import * as React from "react";
import {
  CheckCircle,
  Info,
  Stack,
  WarningCircle,
  XCircle,
} from "@phosphor-icons/react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type {
  ExpedienteCoherence,
  FindingSeverity,
  SubmissionDetail,
} from "@/lib/api/portal";

/**
 * ExpedienteAssessmentCard — Phase 2/3 admin reviewer surface for the
 * situational pass. Where "Lectura del documento" reads ONE document,
 * this card shows what only emerges from the whole expediente: the
 * IMSS headcount against the contract's estimated workers, the REPSE
 * authorized activity against the contracted service, period/entity
 * coherence across documents, and obligation coverage gaps.
 *
 * Reviewer-facing and advisory only — it never changes a status. Hidden
 * entirely until the situational pass has produced an assessment for the
 * provider+period scope.
 */

type Tone = "ok" | "attention" | "error" | "neutral";

const COHERENCE_META: Record<
  ExpedienteCoherence,
  { label: string; icon: typeof CheckCircle; tone: Tone }
> = {
  coherent: { label: "Expediente coherente", icon: CheckCircle, tone: "ok" },
  minor_issues: {
    label: "Inconsistencias menores",
    icon: WarningCircle,
    tone: "attention",
  },
  incoherent: { label: "Expediente incoherente", icon: XCircle, tone: "error" },
  indeterminate: {
    label: "No se pudo determinar",
    icon: Info,
    tone: "neutral",
  },
};

function toneBoxClasses(tone: Tone): string {
  switch (tone) {
    case "ok":
      return "border-[color:var(--status-success-border,transparent)] bg-[color:var(--status-success-bg,transparent)]";
    case "attention":
      return "border-[color:var(--status-warning-border,transparent)] bg-[color:var(--status-warning-bg,transparent)]";
    case "error":
      return "border-[color:var(--status-error-border,transparent)] bg-[color:var(--status-error-bg,transparent)]";
    default:
      return "border-[color:var(--border-subtle)] bg-[color:var(--bg-muted)]";
  }
}

function severityDotClass(severity: FindingSeverity): string {
  switch (severity) {
    case "high":
      return "bg-[color:var(--status-error-text,currentColor)]";
    case "medium":
      return "bg-[color:var(--status-warning-text,currentColor)]";
    default:
      return "bg-[color:var(--text-tertiary)]";
  }
}

export function ExpedienteAssessmentCard({
  detail,
}: {
  detail: SubmissionDetail;
}) {
  const assessment = detail.expediente_assessment ?? null;
  if (!assessment) return null;

  const meta =
    (assessment.coherence && COHERENCE_META[assessment.coherence]) ||
    COHERENCE_META.indeterminate;
  const Icon = meta.icon;

  return (
    <Card
      aria-label="Coherencia del expediente"
      data-internal="expediente-assessment"
    >
      <CardHeader>
        <div className="flex items-center gap-2">
          <Stack
            className="h-4 w-4 text-[color:var(--text-tertiary)]"
            weight="duotone"
            aria-hidden="true"
          />
          <CardTitle>Coherencia del expediente</CardTitle>
        </div>
        <p className="mt-1 text-xs text-[color:var(--text-tertiary)]">
          Análisis del conjunto de documentos del proveedor para el periodo
          {assessment.document_count
            ? ` (${assessment.document_count} documento${
                assessment.document_count === 1 ? "" : "s"
              })`
            : ""}
          . La decisión final es tuya.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        <div
          className={cn(
            "flex items-start gap-3 rounded-md border px-4 py-3",
            toneBoxClasses(meta.tone),
          )}
        >
          <Icon
            className="mt-0.5 h-5 w-5 shrink-0 text-[color:var(--text-secondary)]"
            weight={meta.tone === "ok" ? "fill" : "regular"}
            aria-hidden={true}
          />
          <div className="min-w-0 space-y-1">
            <p className="text-sm font-medium leading-snug text-[color:var(--text-primary)]">
              {meta.label}
            </p>
            {assessment.summary_for_reviewer ? (
              <p className="text-xs leading-snug text-[color:var(--text-secondary)]">
                {assessment.summary_for_reviewer}
              </p>
            ) : null}
          </div>
        </div>

        {assessment.findings.length > 0 ? (
          <div className="space-y-2">
            <p className="text-xs font-medium uppercase tracking-wide text-[color:var(--text-tertiary)]">
              Hallazgos
            </p>
            <ul className="space-y-2">
              {assessment.findings.map((f, i) => (
                <li
                  key={`${f.code}-${i}`}
                  className="flex items-start gap-2 text-sm text-[color:var(--text-primary)]"
                >
                  <span
                    className={cn(
                      "mt-1.5 h-2 w-2 shrink-0 rounded-full",
                      severityDotClass(f.severity),
                    )}
                    aria-hidden={true}
                  />
                  <span className="min-w-0 break-words">
                    {f.detail_es}
                    {f.evidence ? (
                      <span className="block text-xs text-[color:var(--text-tertiary)]">
                        {f.evidence}
                      </span>
                    ) : null}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {assessment.coverage_gaps.length > 0 ? (
          <div className="space-y-2">
            <p className="text-xs font-medium uppercase tracking-wide text-[color:var(--text-tertiary)]">
              Obligaciones faltantes
            </p>
            <ul className="space-y-1">
              {assessment.coverage_gaps.map((g, i) => (
                <li
                  key={`${g.requirement_code}-${i}`}
                  className="flex items-start gap-2 text-sm text-[color:var(--text-primary)]"
                >
                  <WarningCircle
                    className="mt-0.5 h-4 w-4 shrink-0 text-[color:var(--status-warning-text,inherit)]"
                    weight="fill"
                    aria-hidden={true}
                  />
                  <span className="min-w-0 break-words">{g.detail_es}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
