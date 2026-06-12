"use client";

import * as React from "react";
import {
  CaretDown,
  CaretRight,
  CheckCircle,
  CircleNotch,
  Info,
  Robot,
  ShieldWarning,
  WarningCircle,
  XCircle,
} from "@phosphor-icons/react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { confidenceLevelFromPercent } from "@/components/checkwise/confidence-badge";
import { track } from "@/lib/analytics";
import { validationLabel } from "@/lib/constants/validation";
import { cn } from "@/lib/utils";
import type { ConfidenceLevel } from "@/lib/types";
import type {
  ShadowAnalysisPayload,
  ShadowAnalysisSignals,
  SubmissionDetail,
  SubmissionReason,
} from "@/lib/api/portal";

/**
 * LecturaDelDocumento — admin reviewer "what we read from the document".
 *
 * Replaces the prior ReasonsCard ("Señales automáticas") and the
 * Phase-2 ShadowComparisonCard ("Comparación IA (interna)"), which
 * showed the same conceptual thing — automated extractions of the
 * document — in two separate cards with two different vocabularies.
 *
 * Single card, four sections:
 *
 *   1. **Headline verdict** in plain Spanish — what the AI thinks of
 *      this document in one sentence. Falls back to heuristic when AI
 *      hasn't run or errored. Mirrors what the provider's portal page
 *      shows, but written for a legal reviewer's perspective.
 *
 *   2. **Extracted-facts table** — 4 reviewer-relevant rows (document
 *      type, RFC, period/dates, issuing institution). Shows AI's
 *      reading as primary; when the heuristic disagrees, an inline
 *      badge surfaces the heuristic's value as a second opinion.
 *
 *   3. **Señales de prevalidación** expandable — the per-rule
 *      validation signals (the old ReasonsCard content). Collapsed
 *      by default; reviewers who need to see the deterministic check
 *      outcomes (file format, RFC match, period match, etc.) expand
 *      to read them.
 *
 *   4. **Datos técnicos** expandable — model name, prompt version,
 *      latency, raw error codes, raw rule_codes. Engineer-debugging
 *      surface that legal reviewers rarely need but support tickets
 *      do. Always last; always collapsed.
 *
 * If no inspection exists for this submission at all (very old data,
 * predating prevalidation), the card is hidden entirely.
 */

// ─────────────────────────────────────────────────────────────────────
// Error / state translation
// ─────────────────────────────────────────────────────────────────────

const SHADOW_ERROR_FRIENDLY: Record<string, string> = {
  timeout: "El análisis tardó más de lo esperado.",
  unsupported_size_or_type:
    "El archivo es demasiado grande o no es un PDF soportado para análisis automático.",
  daily_cap_exceeded:
    "Se alcanzó el límite diario de análisis automático para esta organización.",
  malformed_response: "No pudimos leerlo automáticamente. Revísalo manualmente.",
};

function friendlyShadowError(code: string | null): string {
  if (!code) return "No pudimos leerlo automáticamente. Revísalo manualmente.";
  if (code in SHADOW_ERROR_FRIENDLY) return SHADOW_ERROR_FRIENDLY[code];
  if (code.startsWith("provider_error") || code.startsWith("heuristic_error")) {
    return "No pudimos leerlo automáticamente. Revísalo manualmente.";
  }
  return "No pudimos leerlo automáticamente. Revísalo manualmente.";
}

// ─────────────────────────────────────────────────────────────────────
// Confidence formatting (per user pick: "73% — media")
//
// Buckets are delegated to ``confidenceLevelFromPercent`` so the
// qualitative word matches the design system's canonical thresholds
// (alta ≥95, media ≥70, baja ≥50) instead of an independent, more
// generous scale. This keeps the AI from being labelled "alta" at 80%
// here while the shared ConfidenceBadge reserves "alta" for ≥95% — the
// two surfaces must not disagree on the same score.
// ─────────────────────────────────────────────────────────────────────

const CONFIDENCE_QUAL_ES: Record<ConfidenceLevel, string> = {
  high: "alta",
  medium: "media",
  low: "baja",
  none: "sin señal clara",
};

function confidenceLabel(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const pct = Math.round(value * 100);
  return `${pct}% — ${CONFIDENCE_QUAL_ES[confidenceLevelFromPercent(pct)]}`;
}

function confidenceTone(value: number | null | undefined): "ok" | "warn" | "low" | "neutral" {
  if (value === null || value === undefined) return "neutral";
  const level = confidenceLevelFromPercent(Math.round(value * 100));
  if (level === "high") return "ok";
  if (level === "medium") return "warn";
  if (level === "low") return "low";
  return "neutral";
}

// ─────────────────────────────────────────────────────────────────────
// Verdict synthesis — one sentence the reviewer reads first
// ─────────────────────────────────────────────────────────────────────

type Verdict = {
  text: string;
  tone: "ok" | "attention" | "neutral" | "error";
  icon: React.ComponentType<{ className?: string; weight?: "fill" | "regular"; "aria-hidden"?: boolean }>;
};

function buildVerdict(
  payload: ShadowAnalysisPayload | null | undefined,
  mismatchReason: string | null,
): Verdict | null {
  if (!payload) return null;
  const shadow = payload.shadow;

  // Shadow run still in flight and no heuristic fallback is available.
  if (
    shadow.completed_at === null &&
    shadow.error === null &&
    !shadow.signals &&
    !payload.heuristic.signals
  ) {
    return {
      text: "Procesando la lectura automática del documento…",
      tone: "neutral",
      icon: CircleNotch,
    };
  }

  // Shadow errored
  if (shadow.error) {
    return {
      text: friendlyShadowError(shadow.error),
      tone: "error",
      icon: WarningCircle,
    };
  }

  // Use AI signals when available, fall back to heuristic
  const primary = shadow.signals ?? payload.heuristic.signals;
  if (!primary) {
    return {
      text: "No tenemos lectura automática disponible para este documento.",
      tone: "neutral",
      icon: Info,
    };
  }

  const reason = primary.mismatch_reason ?? mismatchReason;
  const conf = primary.requirement_match_confidence;

  if (reason) {
    return {
      text: `Posible inconsistencia: ${reason}`,
      tone: "attention",
      icon: ShieldWarning,
    };
  }

  if (conf !== null && conf !== undefined && conf < 0.5) {
    return {
      text:
        "Confianza baja en la coincidencia con el requisito. Revisa el documento con cuidado.",
      tone: "attention",
      icon: ShieldWarning,
    };
  }

  return {
    text: "Parece coincidir con el requisito esperado.",
    tone: "ok",
    icon: CheckCircle,
  };
}

// ─────────────────────────────────────────────────────────────────────
// Facts table (4 rows, AI primary, heuristic as second opinion)
// ─────────────────────────────────────────────────────────────────────

type FactRow = {
  label: string;
  primaryValue: string;
  secondaryValue: string | null;
  hasDisagreement: boolean;
};

function fmtValue(value: string | null | undefined): string {
  if (!value || value === "") return "—";
  return value;
}

function fmtList(items: string[] | null | undefined, max = 3): string {
  if (!items || items.length === 0) return "—";
  if (items.length <= max) return items.join(", ");
  return `${items.slice(0, max).join(", ")} (+${items.length - max})`;
}

function buildFactRows(
  ai: ShadowAnalysisSignals | null,
  heuristic: ShadowAnalysisSignals,
): FactRow[] {
  // Primary = AI when present; secondary surfaces heuristic only on
  // disagreement so the reviewer's eye lands on the AI reading first.
  const useAi = ai !== null;
  const primary = useAi ? ai! : heuristic;
  const secondary = useAi ? heuristic : null;

  function row(
    label: string,
    primaryRaw: unknown,
    secondaryRaw: unknown,
    fmt: (v: unknown) => string,
  ): FactRow {
    const p = fmt(primaryRaw);
    const s = secondaryRaw === undefined ? null : fmt(secondaryRaw);
    const disagreement =
      secondary !== null && s !== null && s !== "—" && s !== p;
    return {
      label,
      primaryValue: p,
      secondaryValue: disagreement ? s : null,
      hasDisagreement: disagreement,
    };
  }

  const str = (v: unknown) => fmtValue(typeof v === "string" ? v : null);
  const list = (v: unknown) => fmtList(Array.isArray(v) ? (v as string[]) : null);
  const conc = (v: unknown) => {
    const dates = list(v);
    return dates;
  };

  return [
    row(
      "Tipo de documento",
      primary.detected_document_type,
      secondary?.detected_document_type,
      str,
    ),
    row(
      "RFC detectado",
      primary.detected_rfcs,
      secondary?.detected_rfcs,
      list,
    ),
    row(
      "Fechas / periodo",
      [
        ...(primary.detected_dates ?? []),
        ...(primary.period_mentions ?? []),
      ],
      secondary
        ? [
            ...(secondary.detected_dates ?? []),
            ...(secondary.period_mentions ?? []),
          ]
        : undefined,
      conc,
    ),
    row(
      "Institución emisora",
      primary.detected_institution,
      secondary?.detected_institution,
      str,
    ),
  ];
}

// ─────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────

export function LecturaDelDocumento({
  detail,
}: {
  detail: SubmissionDetail;
}) {
  const payload = detail.shadow_analysis ?? null;
  const reasons = detail.reasons ?? [];
  const mismatchReason = detail.document?.mismatch_reason ?? null;
  const [signalsOpen, setSignalsOpen] = React.useState(false);
  const [tecnicosOpen, setTecnicosOpen] = React.useState(false);

  const verdict = buildVerdict(payload, mismatchReason);

  // Effect MUST run before any conditional return so the hook order
  // stays stable across renders (Rules of Hooks). Effect body itself
  // is conditional — the empty-data case is a cheap noop.
  React.useEffect(() => {
    if (verdict && payload?.shadow.signals && payload.heuristic.signals) {
      const facts = buildFactRows(payload.shadow.signals, payload.heuristic.signals);
      const disagreements = facts.filter((f) => f.hasDisagreement).length;
      if (disagreements > 0) {
        track("prevalidation.lectura.disagreement_shown", {
          disagreement_count: disagreements,
        });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // If we have neither a verdict nor any reasons nor a mismatch reason,
  // there's nothing to show. Hide the card entirely (matches the
  // pre-Phase-2 "old submissions" decision).
  const hasAnything =
    verdict !== null || reasons.length > 0 || mismatchReason !== null;
  if (!hasAnything) return null;

  return (
    <Card aria-label="Lectura del documento" data-internal="lectura-del-documento">
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2">
            <Robot
              className="h-4 w-4 text-[color:var(--text-tertiary)]"
              weight="duotone"
              aria-hidden="true"
            />
            <CardTitle>Lectura del documento</CardTitle>
          </div>
          {payload?.shadow.signals?.requirement_match_confidence !== undefined &&
          payload.shadow.signals.requirement_match_confidence !== null ? (
            <ConfidenceChip value={payload.shadow.signals.requirement_match_confidence} />
          ) : null}
        </div>
        <p className="mt-1 text-xs text-[color:var(--text-tertiary)]">
          Lo que la lectura automática detectó. La decisión final es tuya.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        {verdict ? <VerdictRow verdict={verdict} /> : null}

        {payload?.shadow.signals || payload?.heuristic.signals ? (
          <FactsTable
            ai={payload.shadow.signals ?? null}
            heuristic={payload.heuristic.signals}
          />
        ) : null}

        <Expandable
          label="Señales de prevalidación"
          subtitle={`${reasons.length} señal${reasons.length === 1 ? "" : "es"} registrada${
            reasons.length === 1 ? "" : "s"
          }`}
          open={signalsOpen}
          onToggle={() => setSignalsOpen((v) => !v)}
        >
          <SignalsList reasons={reasons} />
        </Expandable>

        <Expandable
          label="Datos técnicos"
          subtitle="Detalles del modelo, latencia y códigos internos"
          open={tecnicosOpen}
          onToggle={() => {
            setTecnicosOpen((v) => !v);
            if (!tecnicosOpen) {
              track("prevalidation.tecnicos.expanded", {});
            }
          }}
        >
          <TechnicalDetails payload={payload} reasons={reasons} />
        </Expandable>
      </CardContent>
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Subcomponents
// ─────────────────────────────────────────────────────────────────────

function VerdictRow({ verdict }: { verdict: Verdict }) {
  const Icon = verdict.icon;
  const tone =
    verdict.tone === "ok"
      ? "border-[color:var(--status-success-border,transparent)] bg-[color:var(--status-success-bg,transparent)] text-[color:var(--status-success-text,inherit)]"
      : verdict.tone === "attention"
        ? "border-[color:var(--status-warning-border,transparent)] bg-[color:var(--status-warning-bg,transparent)] text-[color:var(--status-warning-text,inherit)]"
        : verdict.tone === "error"
          ? "border-[color:var(--status-error-border,transparent)] bg-[color:var(--status-error-bg,transparent)] text-[color:var(--status-error-text,inherit)]"
          : "border-[color:var(--border-subtle)] bg-[color:var(--bg-muted)] text-[color:var(--text-secondary)]";
  return (
    <div className={cn("flex items-start gap-3 rounded-md border px-4 py-3", tone)}>
      <Icon
        className={cn("mt-0.5 h-5 w-5 shrink-0", verdict.tone === "neutral" ? "animate-spin" : "")}
        weight={verdict.tone === "ok" ? "fill" : "regular"}
        aria-hidden={true}
      />
      <p className="text-sm font-medium leading-snug text-[color:var(--text-primary)]">
        {verdict.text}
      </p>
    </div>
  );
}

function ConfidenceChip({ value }: { value: number }) {
  const tone = confidenceTone(value);
  const badgeVariant: "secondary" | "warning" | "destructive" | "outline" =
    tone === "ok" ? "secondary" : tone === "warn" ? "warning" : tone === "low" ? "destructive" : "outline";
  return (
    <Badge variant={badgeVariant} className="whitespace-nowrap">
      Confianza {confidenceLabel(value)}
    </Badge>
  );
}

function FactsTable({
  ai,
  heuristic,
}: {
  ai: ShadowAnalysisSignals | null;
  heuristic: ShadowAnalysisSignals;
}) {
  const rows = buildFactRows(ai, heuristic);
  // Mobile: stack label + value vertically (label as small caption,
  // value below in full row width). Desktop: side-by-side grid with
  // a fixed-width label column.
  return (
    <div className="overflow-hidden rounded-md border border-[color:var(--border-subtle)]">
      <dl className="divide-y divide-[color:var(--border-subtle)]">
        {rows.map((row) => (
          <div
            key={row.label}
            className="flex flex-col gap-1 px-3 py-2 text-sm sm:grid sm:grid-cols-[200px_1fr] sm:gap-3"
          >
            <dt className="text-xs uppercase tracking-wide text-[color:var(--text-tertiary)] sm:text-sm sm:normal-case sm:tracking-normal">
              {row.label}
            </dt>
            <dd className="text-[color:var(--text-primary)]">
              <div className="flex flex-wrap items-baseline gap-2">
                <span className={row.hasDisagreement ? "break-words font-medium" : "break-words"}>
                  {row.primaryValue}
                </span>
                {row.hasDisagreement && row.secondaryValue ? (
                  <Badge variant="outline" className="text-xs">
                    Heurística: {row.secondaryValue}
                  </Badge>
                ) : null}
              </div>
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function Expandable({
  label,
  subtitle,
  open,
  onToggle,
  children,
}: {
  label: string;
  subtitle: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-md border border-[color:var(--border-subtle)]">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm"
      >
        {/* Label can grow and wrap; caret stays glued to the right.
            Subtitle hides on the smallest screens (where the title +
            caret already tell the user enough) and re-appears at sm+. */}
        <span className="min-w-0 flex-1 font-medium text-[color:var(--text-primary)]">
          {label}
        </span>
        <span className="flex shrink-0 items-center gap-2">
          <span className="hidden text-xs text-[color:var(--text-tertiary)] sm:inline">
            {subtitle}
          </span>
          {open ? (
            <CaretDown className="h-4 w-4 text-[color:var(--text-tertiary)]" aria-hidden={true} />
          ) : (
            <CaretRight className="h-4 w-4 text-[color:var(--text-tertiary)]" aria-hidden={true} />
          )}
        </span>
      </button>
      {open ? <div className="border-t border-[color:var(--border-subtle)] px-3 py-3">{children}</div> : null}
    </div>
  );
}

function SignalsList({ reasons }: { reasons: SubmissionReason[] }) {
  if (reasons.length === 0) {
    return (
      <p className="text-sm text-[color:var(--text-tertiary)]">
        Sin señales escaladas. Todas las verificaciones automáticas pasaron.
      </p>
    );
  }
  return (
    <ul className="space-y-2">
      {reasons.map((r) => {
        const Icon =
          r.severity === "error" ? XCircle : r.severity === "warning" ? WarningCircle : CheckCircle;
        const tone =
          r.severity === "error"
            ? "text-[color:var(--status-error-text,#dc2626)]"
            : r.severity === "warning"
              ? "text-[color:var(--status-warning-text,#d97706)]"
              : "text-[color:var(--status-success-text,#16a34a)]";
        return (
          <li
            key={r.rule_code}
            className="flex items-start gap-2 text-sm"
            title={r.rule_code}
          >
            <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", tone)} weight="fill" aria-hidden={true} />
            <div className="min-w-0">
              <p className="font-medium text-[color:var(--text-primary)]">
                {validationLabel(r.rule_code)}
              </p>
              {r.message ? (
                <p className="text-[color:var(--text-secondary)]">{r.message}</p>
              ) : null}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function TechnicalDetails({
  payload,
  reasons,
}: {
  payload: ShadowAnalysisPayload | null;
  reasons: SubmissionReason[];
}) {
  return (
    <div className="space-y-3 text-xs text-[color:var(--text-secondary)]">
      {payload?.shadow ? (
        // Single-column on mobile (timestamps + tech identifiers can be
        // long; cramming them into 2 columns on 375px breaks layouts).
        // Two-column at sm+ where there's room.
        <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 font-mono sm:grid-cols-2">
          <dt>Proveedor de IA</dt>
          <dd className="break-all">{payload.shadow.provider_id ?? "—"}</dd>
          <dt>Versión del prompt</dt>
          <dd className="break-all">{payload.shadow.prompt_version ?? "—"}</dd>
          <dt>Latencia</dt>
          <dd>
            {payload.shadow.latency_ms !== null
              ? `${(payload.shadow.latency_ms / 1000).toFixed(2)} s`
              : "—"}
          </dd>
          <dt>Completado</dt>
          <dd className="break-words">
            {payload.shadow.completed_at
              ? new Date(payload.shadow.completed_at).toLocaleString("es-MX")
              : "—"}
          </dd>
          <dt>Código de error</dt>
          <dd className="break-all">{payload.shadow.error ?? "—"}</dd>
        </dl>
      ) : (
        <p>No hay datos del análisis automático.</p>
      )}
      {reasons.length > 0 ? (
        <div>
          <p className="font-medium text-[color:var(--text-primary)]">Códigos de regla</p>
          <p className="break-all font-mono">
            {reasons.map((r) => r.rule_code).join(", ")}
          </p>
        </div>
      ) : null}
    </div>
  );
}
