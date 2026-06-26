"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  ArrowSquareOut,
  CheckCircle,
  DownloadSimple,
  FileText,
} from "@phosphor-icons/react";

import {
  ReviewDecisionPanel,
  type ReviewerAction,
} from "@/components/checkwise/admin/review-decision-panel";
import { RequirementStatusBadge } from "@/components/checkwise/portal/requirement-status-badge";
import {
  ErrorState,
  NotFoundState,
  SubmissionDetailSkeleton,
} from "@/components/checkwise/portal/state-surfaces";
import { LecturaDelDocumento } from "@/components/checkwise/admin/lectura-del-documento";
import { ExpedienteAssessmentCard } from "@/components/checkwise/admin/expediente-assessment-card";
import { SubmissionTimeline } from "@/components/checkwise/portal/submission-timeline";
import { PdfPreview } from "@/components/checkwise/pdf-preview";
import { FeedbackLauncher } from "@/components/feedback/feedback-launcher";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MetadataStrip, type MetadataItem } from "@/components/ui/metadata-strip";
import { PageHeader } from "@/components/ui/page-header";
import { toast } from "@/components/ui/toast";
import { safeReturnTo, withReturnTo } from "@/lib/navigation/return-to";
import {
  clearAdminSession,
  readAdminSession,
  type AdminSession,
} from "@/lib/session/admin";
import {
  INSTITUTION_LABELS,
  type RfcAlignment,
  type SubmissionDetail,
} from "@/lib/api/portal";
import {
  fetchReviewerSubmissionDocumentBlob,
  getReviewerSubmission,
  ReviewerApiError,
  submitDecision,
  type AuthenticityReason,
  type ReviewerSubmissionDetail,
  type VerificationFolio,
  type VerificationQrCode,
} from "@/lib/api/reviewer";
import { personaLabel } from "@/lib/constants/labels";
import { formatDateTime } from "@/lib/format/datetime";
import {
  DocumentStatus,
  clientAcceptanceLabel,
  clientAcceptanceVariant,
  statusLabel,
  statusVariant,
} from "@/lib/constants/statuses";

type PageProps = {
  params: Promise<{ submission_id: string }>;
};

const REVIEWER_ROLES = ["platform_admin", "operations_admin"] as const;
const REVIEWER_RETURN_PREFIXES = [
  "/admin/reviewer",
  "/admin/vendors",
  "/admin/clients",
] as const;

function reviewerDetailHref(submissionId: string, returnToHref: string): string {
  return withReturnTo(`/admin/reviewer/${submissionId}`, returnToHref);
}

function returnLabel(returnToHref: string): string {
  return returnToHref.startsWith("/admin/reviewer") ? "Bandeja" : "Volver";
}

function returnLongLabel(returnToHref: string): string {
  return returnToHref.startsWith("/admin/reviewer")
    ? "Volver a la bandeja"
    : "Volver";
}

export default function ReviewerSubmissionPage({ params }: PageProps) {
  const { submission_id } = use(params);
  const router = useRouter();
  const [session, setSession] = useState<AdminSession | null>(null);
  const [detail, setDetail] = useState<ReviewerSubmissionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorKind, setErrorKind] = useState<"not_found" | "network" | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [returnToHref, setReturnToHref] = useState("/admin/reviewer");

  const [decided, setDecided] = useState<{
    new_status: string;
    action: ReviewerAction;
    /** Oldest still-pending submission (FIFO) — drives "Siguiente
     *  documento". Null when the queue is drained. */
    next_pending_submission_id: string | null;
  } | null>(null);

  useEffect(() => {
    const raw = new URLSearchParams(window.location.search).get("returnTo");
    setReturnToHref(
      safeReturnTo(raw, REVIEWER_RETURN_PREFIXES, "/admin/reviewer"),
    );
  }, [submission_id]);

  useEffect(() => {
    const current = readAdminSession();
    if (!current) {
      router.replace("/login");
      return;
    }
    if (!current.roles.some((r) => (REVIEWER_ROLES as readonly string[]).includes(r))) {
      router.replace("/admin");
      return;
    }
    setSession(current);
  }, [router]);

  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    setLoading(true);
    setErrorKind(null);
    // Auto-advance navigates to a new submission_id within the same
    // mounted page — reset the decided card so the next document opens
    // on a fresh decision panel.
    setDecided(null);
    getReviewerSubmission(submission_id)
      .then((payload) => {
        if (!cancelled) setDetail(payload);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ReviewerApiError && err.status === 401) {
          clearAdminSession();
          router.replace("/login");
          return;
        }
        if (err instanceof ReviewerApiError && err.status === 404) {
          setErrorKind("not_found");
          return;
        }
        setErrorKind("network");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [session, submission_id, reloadKey, router]);

  const retry = useCallback(() => setReloadKey((k) => k + 1), []);

  const handleDecision = useCallback(
    async (
      action: ReviewerAction,
      reason: string | null,
      observations: string | null,
      acceptedSuggestion: boolean | null,
    ) => {
      if (!session || !detail) return;
      try {
        const result = await submitDecision(
          detail.submission_id,
          action,
          reason,
          observations,
          acceptedSuggestion,
        );
        setDecided({
          new_status: result.new_status,
          action: result.action as ReviewerAction,
          next_pending_submission_id: result.next_pending_submission_id ?? null,
        });
        toast.success("Decisión registrada", {
          description: `Este documento ahora está en "${statusLabel(result.new_status)}".`,
        });
      } catch (err) {
        if (err instanceof ReviewerApiError && err.status === 409) {
          throw new Error("Este documento ya tiene una decisión registrada.");
        }
        if (err instanceof ReviewerApiError && err.status === 422) {
          throw new Error("La razón es obligatoria para esta decisión.");
        }
        throw new Error("No pudimos registrar la decisión. Intenta de nuevo.");
      }
    },
    [session, detail],
  );

  // After a decision lands, Enter or N jumps to the next pending
  // document — the keyboard reviewer never has to reach for the mouse
  // between documents. Ignored while a form control has focus (e.g.
  // the feedback launcher) so we never steal typed characters.
  useEffect(() => {
    const nextId = decided?.next_pending_submission_id;
    if (!nextId) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const el = document.activeElement;
      if (
        el instanceof HTMLElement &&
        (el.tagName === "INPUT" ||
          el.tagName === "TEXTAREA" ||
          el.tagName === "SELECT" ||
          el.isContentEditable)
      ) {
        return;
      }
      if (event.key === "Enter" || event.key.toLowerCase() === "n") {
        event.preventDefault();
        router.push(reviewerDetailHref(nextId!, returnToHref));
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [decided, returnToHref, router]);

  if (!session) return null;

  const terminalStatuses: string[] = [
    DocumentStatus.APROBADO,
    DocumentStatus.RECHAZADO,
    DocumentStatus.EXCEPCION_LEGAL,
  ];
  const isTerminal = !!detail && terminalStatuses.includes(detail.status);
  const panelDisabled = isTerminal || !!decided;

  return (
    <>
    <main className="mx-auto max-w-6xl space-y-5 px-5 py-8">
      <PageHeader
        eyebrow="Mesa de revisión"
        title={detail?.requirement.name ?? "Documento por revisar"}
        description="Revisa señales automáticas, contexto del proveedor y la línea de tiempo. Tu decisión queda en el audit log."
        actions={
          <Button asChild variant="outline" size="sm">
            <Link href={returnToHref}>
              <ArrowLeft className="h-4 w-4" aria-hidden />
              {returnLabel(returnToHref)}
            </Link>
          </Button>
        }
      />

      {loading ? (
        <SubmissionDetailSkeleton />
      ) : errorKind === "not_found" ? (
        <NotFoundState
          title="No encontramos este documento"
          description="El enlace puede haber expirado o el documento ya no existe."
          action={
            <Button asChild>
              <Link href={returnToHref}>
                <ArrowLeft className="h-4 w-4" aria-hidden />
                {returnLongLabel(returnToHref)}
              </Link>
            </Button>
          }
        />
      ) : errorKind === "network" ? (
        <ErrorState
          title="No pudimos cargar este documento"
          description="Tu conexión pudo haberse interrumpido. Reintenta en un momento."
          onRetry={retry}
        />
      ) : detail ? (
        <div className="grid gap-5 lg:grid-cols-3">
          <div className="space-y-5 lg:col-span-2">
            <StatusHeader detail={detail} decidedHint={decided?.new_status ?? null} />
            <VendorIdentityStrip detail={detail} />
            <VerdictCard detail={detail} />
            <PrevalidationEvidenceCard detail={detail} />
            <VerificationCard detail={detail} />
            <ReviewerSubmissionPreview detail={detail} />
            <LineageStrip detail={detail} returnToHref={returnToHref} />
            <LecturaDelDocumento detail={detail} />
            <ExpedienteAssessmentCard detail={detail} />
            <ProviderCard detail={detail} />
            <PreviousAttemptsCard detail={detail} returnToHref={returnToHref} />
            <SubmissionTimeline detail={detail} audience="admin" />
          </div>
          <div className="space-y-5">
            {decided ? (
              <Card>
                <CardHeader>
                  <div className="flex items-center gap-2">
                    <CheckCircle
                      className="h-4 w-4 text-[color:var(--status-success-text)]"
                      weight="fill"
                      aria-hidden
                    />
                    <CardTitle>Decisión registrada</CardTitle>
                  </div>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-[color:var(--text-secondary)]">
                    Decisión registrada. Estado actual:{" "}
                    <RequirementStatusBadge
                      status={decided.new_status as Parameters<typeof RequirementStatusBadge>[0]["status"]}
                    />
                    . La línea de tiempo refleja tu decisión.
                  </p>
                  {decided.next_pending_submission_id ? (
                    <div className="mt-4 space-y-2">
                      <Button
                        className="w-full"
                        onClick={() =>
                          router.push(
                            reviewerDetailHref(
                              decided.next_pending_submission_id!,
                              returnToHref,
                            ),
                          )
                        }
                      >
                        Siguiente documento
                        <ArrowRight className="h-4 w-4" aria-hidden />
                      </Button>
                      <Button asChild variant="outline" className="w-full">
                        <Link href={returnToHref}>
                          <ArrowLeft className="h-4 w-4" aria-hidden />
                          {returnLongLabel(returnToHref)}
                        </Link>
                      </Button>
                      <p className="text-center text-[11px] text-[color:var(--text-tertiary)]">
                        Enter o N para pasar al siguiente
                      </p>
                    </div>
                  ) : (
                    <>
                      <p className="mt-3 text-sm font-medium text-[color:var(--status-success-text)]">
                        Bandeja despejada 🎉 No quedan documentos pendientes
                        por revisar.
                      </p>
                      <Button asChild className="mt-4">
                        <Link href={returnToHref}>
                          <ArrowLeft className="h-4 w-4" aria-hidden />
                          {returnLongLabel(returnToHref)}
                        </Link>
                      </Button>
                    </>
                  )}
                </CardContent>
              </Card>
            ) : (
              <ReviewDecisionPanel
                key={detail.submission_id}
                disabled={panelDisabled}
                disabledReason={
                  isTerminal
                    ? `Este documento ya está en "${statusLabel(detail.status)}". Solo una nueva carga del proveedor puede reabrirlo.`
                    : undefined
                }
                onSubmit={handleDecision}
                aiHint={deriveAiHint(detail)}
                suggestion={detail.approval_suggestion}
              />
            )}
            <TraceabilityCard detail={detail} />
          </div>
        </div>
      ) : null}
    </main>
    <FeedbackLauncher />
    </>
  );
}

// ---------------------------------------------------------------------------
// Components
// ---------------------------------------------------------------------------

/**
 * Phase 9 — surfaces the Phase 4 replacement-lineage pointers that
 * already arrive on the reviewer detail payload. Mirrors the provider
 * portal's lineage strip so both surfaces render the same affordance
 * when a submission is part of a replacement chain.
 *
 * Backend source: ``GET /api/v1/reviewer/submissions/{id}`` →
 * ``supersedes_submission_id`` / ``superseded_by_submission_id``.
 * Returns null when the submission stands alone.
 */
function LineageStrip({
  detail,
  returnToHref,
}: {
  detail: SubmissionDetail;
  returnToHref: string;
}) {
  if (!detail.supersedes_submission_id && !detail.superseded_by_submission_id) {
    return null;
  }
  return (
    <section
      aria-label="Replacement lineage"
      className="rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-sunken)] p-4 text-sm"
    >
      {detail.supersedes_submission_id ? (
        <p>
          <span className="font-medium text-[color:var(--text-primary)]">
            Reemplaza intento anterior:
          </span>{" "}
          <Link
            href={reviewerDetailHref(
              detail.supersedes_submission_id,
              returnToHref,
            )}
            className="font-mono text-xs text-[color:var(--text-brand)] underline-offset-2 hover:underline"
          >
            {detail.supersedes_submission_id}
          </Link>
        </p>
      ) : null}
      {detail.superseded_by_submission_id ? (
        <p className={detail.supersedes_submission_id ? "mt-2" : ""}>
          <span className="font-medium text-[color:var(--text-primary)]">
            Reemplazado por intento más reciente:
          </span>{" "}
          <Link
            href={reviewerDetailHref(
              detail.superseded_by_submission_id,
              returnToHref,
            )}
            className="font-mono text-xs text-[color:var(--text-brand)] underline-offset-2 hover:underline"
          >
            {detail.superseded_by_submission_id}
          </Link>
        </p>
      ) : null}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Vendor identity + RFC match (P1 audit fix, 2026-06-10)
// ---------------------------------------------------------------------------

/**
 * Pull the OCR/AI-detected RFCs from the inspection payload, mirroring
 * <LecturaDelDocumento/>'s primary-signal choice (AI shadow signals
 * when the shadow run produced them, heuristic otherwise) so this
 * comparison never disagrees with the "RFC detectado" row below it.
 */
function detectedRfcs(detail: SubmissionDetail): string[] {
  if (detail.document?.detected_rfcs?.length) {
    return detail.document.detected_rfcs;
  }
  const payload = detail.shadow_analysis ?? null;
  if (!payload) return [];
  const signals = payload.shadow?.signals ?? payload.heuristic?.signals ?? null;
  return signals?.detected_rfcs ?? [];
}

function rfcAlignment(detail: SubmissionDetail): RfcAlignment | null {
  return (
    detail.document?.rfc_alignment ??
    detail.shadow_analysis?.heuristic?.signals?.rfc_alignment ??
    detail.shadow_analysis?.shadow?.signals?.rfc_alignment ??
    null
  );
}

function RfcAlignmentBadge({ alignment }: { alignment: RfcAlignment | null }) {
  if (alignment === "match") return <Badge variant="success">RFC coincide</Badge>;
  if (alignment === "homoclave_mismatch") {
    return <Badge variant="warning">Posible error de homoclave</Badge>;
  }
  if (alignment === "mismatch") {
    return <Badge variant="destructive">RFC no coincide</Badge>;
  }
  if (alignment === "absent") {
    return <Badge variant="secondary">RFC no detectado</Badge>;
  }
  if (alignment === "no_expected") {
    return <Badge variant="secondary">Sin RFC esperado</Badge>;
  }
  return <Badge variant="secondary">Sin comparación</Badge>;
}

/**
 * Vendor identity block — answers "WHOSE document is this?" before the
 * reviewer reads a single signal, and makes the most common fraud
 * vector (right document type, wrong company) a one-glance ✓/✗ check
 * instead of a memory exercise against the queue row. Null-safe:
 * legacy rows can carry ``vendor: null`` — the strip simply doesn't
 * render and the page reads exactly as before.
 */
function VendorIdentityStrip({ detail }: { detail: ReviewerSubmissionDetail }) {
  const vendor = detail.vendor;
  if (!vendor) return null;

  const detected = detectedRfcs(detail);
  const detectedText = detected.length ? detected.join(", ") : "—";
  const alignment = rfcAlignment(detail);

  const items: MetadataItem[] = [
    { label: "Proveedor", value: vendor.vendor_name ?? "—" },
    { label: "RFC esperado", value: vendor.vendor_rfc ?? "—", mono: true },
    { label: "Cliente", value: vendor.client_name ?? "—" },
    { label: "Persona", value: personaLabel(vendor.persona_type) },
    {
      label: "RFC detectado",
      value: (
        <span className="inline-flex items-center gap-1.5">
          <span className="font-mono tabular-nums">
            {detectedText}
          </span>
          <RfcAlignmentBadge alignment={alignment} />
        </span>
      ),
    },
  ];

  return <MetadataStrip items={items} />;
}

// ---------------------------------------------------------------------------
// Phase A — verdict card (Coincidencia + Autenticidad, 2026-06-11)
// ---------------------------------------------------------------------------

/**
 * Pull the requirement-match confidence the same way
 * <LecturaDelDocumento/> picks its primary signals (AI shadow signals
 * when the shadow run produced them, heuristic otherwise), so the big
 * percentage in the verdict card can never disagree with the
 * "Confianza" chip the Lectura shows below it.
 */
function matchConfidence(detail: SubmissionDetail): number | null {
  const payload = detail.shadow_analysis ?? null;
  if (!payload) return null;
  const signals = payload.shadow?.signals ?? payload.heuristic?.signals ?? null;
  const conf = signals?.requirement_match_confidence;
  return conf === null || conf === undefined ? null : conf;
}

/** Canonical Spanish labels + badge tones for the authenticity risk. */
const RISK_META: Record<
  "clean" | "suspicious" | "high_risk",
  { label: string; variant: "success" | "warning" | "destructive" }
> = {
  clean: { label: "Limpio", variant: "success" },
  suspicious: { label: "Sospechoso", variant: "warning" },
  high_risk: { label: "Alto riesgo", variant: "destructive" },
};

/** Tone bands for the match percentage: ≥85 success, 60–84 warning,
 *  <60 destructive. */
function confidenceBandClass(pct: number): string {
  if (pct >= 85) return "text-[color:var(--status-success-text)]";
  if (pct >= 60) return "text-[color:var(--status-warning-text)]";
  return "text-[color:var(--status-error-text)]";
}

const REASON_SEVERITY_DOT: Record<AuthenticityReason["severity"], string> = {
  high: "bg-[color:var(--status-error-text)]",
  medium: "bg-[color:var(--status-warning-text)]",
  info: "bg-[color:var(--text-tertiary)]",
};

/**
 * Render one forensics value. ``*_date`` keys get an es-MX date when
 * parseable; everything else falls back to a mono string.
 */
function formatForensicValue(key: string, value: unknown): string {
  if (key.endsWith("_date") && typeof value === "string") {
    const parsed = new Date(value);
    if (!Number.isNaN(parsed.getTime())) {
      return parsed.toLocaleDateString("es-MX", {
        day: "2-digit",
        month: "short",
        year: "numeric",
      });
    }
  }
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  try {
    return JSON.stringify(value) ?? String(value);
  } catch {
    return String(value);
  }
}

/**
 * Phase A document revalidation — the headline verdict. TWO separate
 * scores, deliberately never blended into one number:
 *
 *   1. **Coincidencia** — how confident the lectura is that this is
 *      the EXPECTED document (type + RFC + periodo). Same value the
 *      Lectura card's confidence chip shows.
 *   2. **Autenticidad** — whether the PDF-forensics analyzer thinks
 *      the file itself was tampered with, with the analyzer's named
 *      reasons listed under the badge.
 *
 * A 98% match can still be high-risk (real document, edited dates)
 * and a 40% match can be clean (wrong document, untouched file) —
 * blending them would hide exactly the cases the reviewer must catch.
 */
function VerdictCard({ detail }: { detail: ReviewerSubmissionDetail }) {
  const [forensicsOpen, setForensicsOpen] = useState(false);

  const confidence = matchConfidence(detail);
  const pct = confidence === null ? null : Math.round(confidence * 100);

  const auth = detail.authenticity;
  const analyzed = auth?.analyzed === true;
  const riskMeta = analyzed && auth?.risk ? RISK_META[auth.risk] : null;
  const reasons = riskMeta ? auth?.reasons ?? [] : [];

  // Forensic evidence only makes sense when the analyzer actually ran;
  // null values are noise (absent extractors), so they're hidden.
  const forensicEntries =
    analyzed && auth?.forensics
      ? Object.entries(auth.forensics).filter(
          ([, value]) => value !== null && value !== undefined,
        )
      : [];

  return (
    <Card aria-label="Veredicto del documento">
      <CardHeader>
        <CardTitle>Veredicto del documento</CardTitle>
        <p className="mt-1 text-xs text-[color:var(--text-tertiary)]">
          Dos lecturas independientes: que sea el documento correcto y que el
          archivo no esté alterado.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        {detail.client_acceptance &&
        detail.client_acceptance !== "pending" ? (
          <div className="rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-[color:var(--text-tertiary)]">
              Decisión del cliente · aceptación
            </p>
            <div className="mt-1.5 flex flex-wrap items-center gap-2">
              <Badge variant={clientAcceptanceVariant(detail.client_acceptance)}>
                {clientAcceptanceLabel(detail.client_acceptance)}
              </Badge>
              {detail.client_decided_at ? (
                <span className="text-xs text-[color:var(--text-tertiary)]">
                  {formatDateTime(detail.client_decided_at, {
                    dateStyle: "medium",
                    timeStyle: "short",
                  })}
                </span>
              ) : null}
            </div>
            {detail.client_decision_reason ? (
              <p className="mt-2 text-sm text-[color:var(--text-secondary)]">
                <span className="font-medium">Motivo:</span>{" "}
                {detail.client_decision_reason}
              </p>
            ) : null}
            <p className="mt-2 text-[11px] text-[color:var(--text-tertiary)]">
              Independiente del dictamen de cumplimiento de CheckWise.
            </p>
          </div>
        ) : null}
        <div className="grid gap-3 sm:grid-cols-2">
          {/* Coincidencia — is this the document we expected? */}
          <div className="rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-[color:var(--text-tertiary)]">
              Coincidencia
            </p>
            {pct !== null ? (
              <>
                <p
                  className={`mt-1 text-3xl font-semibold tabular-nums ${confidenceBandClass(pct)}`}
                >
                  {pct}%
                </p>
                <p className="mt-1 text-xs text-[color:var(--text-secondary)]">
                  que sea el documento esperado (tipo · RFC · periodo)
                </p>
              </>
            ) : (
              <p className="mt-2 text-sm font-medium text-[color:var(--text-secondary)]">
                Sin análisis de coincidencia
              </p>
            )}
          </div>

          {/* Autenticidad — was the file tampered with? */}
          <div className="rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-[color:var(--text-tertiary)]">
              Autenticidad
            </p>
            <div className="mt-1.5">
              {riskMeta ? (
                <Badge variant={riskMeta.variant}>{riskMeta.label}</Badge>
              ) : (
                <Badge variant="secondary">Sin analizar</Badge>
              )}
            </div>
            {riskMeta ? (
              reasons.length > 0 ? (
                <ul className="mt-2.5 space-y-1.5">
                  {reasons.map((reason) => (
                    <li
                      key={reason.code}
                      title={reason.code}
                      className="flex items-start gap-2 text-xs text-[color:var(--text-secondary)]"
                    >
                      <span
                        aria-hidden
                        className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full ${REASON_SEVERITY_DOT[reason.severity]}`}
                      />
                      <span className="min-w-0 break-words">
                        {reason.detail_es}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-xs text-[color:var(--text-tertiary)]">
                  Sin señales de alteración detectadas.
                </p>
              )
            ) : (
              <p className="mt-2 text-xs text-[color:var(--text-tertiary)]">
                El análisis forense no se ejecutó para este documento.
              </p>
            )}
          </div>
        </div>

        {/* Collapsed forensic evidence — TraceabilityCard idiom. */}
        {forensicEntries.length > 0 ? (
          <div className="rounded-md border border-[color:var(--border-subtle)]">
            <button
              type="button"
              onClick={() => setForensicsOpen((v) => !v)}
              aria-expanded={forensicsOpen}
              className="flex w-full items-center justify-between px-3 py-2 text-left"
            >
              <span className="text-sm font-medium text-[color:var(--text-primary)]">
                Evidencia forense
              </span>
              <span className="text-xs text-muted-foreground">
                {forensicsOpen ? "Ocultar" : "Mostrar"}
              </span>
            </button>
            {forensicsOpen ? (
              <div className="space-y-2 border-t border-[color:var(--border-subtle)] px-3 py-3">
                {forensicEntries.map(([key, value]) => (
                  <p key={key} className="text-xs text-[color:var(--text-secondary)]">
                    <span className="font-medium text-[color:var(--text-primary)]">
                      {key}:
                    </span>{" "}
                    <span className="break-all font-mono">
                      {formatForensicValue(key, value)}
                    </span>
                  </p>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function alignmentBadge(value: string | null | undefined) {
  if (value === "match") return <Badge variant="success">Coincide</Badge>;
  if (value === "client_match") return <Badge variant="warning">Cliente, no proveedor</Badge>;
  if (value === "homoclave_mismatch") return <Badge variant="warning">Homoclave</Badge>;
  if (value === "mismatch") return <Badge variant="destructive">No coincide</Badge>;
  if (value === "absent") return <Badge variant="secondary">No detectado</Badge>;
  if (value === "no_expected" || value === "not_expected") {
    return <Badge variant="secondary">No esperado</Badge>;
  }
  return <Badge variant="secondary">Sin dato</Badge>;
}

function evidenceList(values: string[] | undefined): string {
  return values && values.length ? values.join(", ") : "—";
}

function EvidenceRow({
  label,
  expected,
  extracted,
  alignment,
}: {
  label: string;
  expected: string;
  extracted: string;
  alignment: string | null | undefined;
}) {
  return (
    <div className="grid gap-2 border-b border-[color:var(--border-subtle)] px-3 py-2.5 text-sm last:border-b-0 md:grid-cols-[1fr_1fr_auto]">
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-[color:var(--text-tertiary)]">
          {label} esperado
        </p>
        <p className="mt-0.5 break-words font-medium text-[color:var(--text-primary)]">
          {expected}
        </p>
      </div>
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-[color:var(--text-tertiary)]">
          Detectado
        </p>
        <p className="mt-0.5 break-words font-mono text-xs text-[color:var(--text-primary)]">
          {extracted}
        </p>
      </div>
      <div className="flex items-center md:justify-end">
        {alignmentBadge(alignment)}
      </div>
    </div>
  );
}

function PrevalidationEvidenceCard({ detail }: { detail: ReviewerSubmissionDetail }) {
  const evidence = detail.prevalidation_evidence;
  if (!evidence) return null;

  const identifiers = evidence.extracted.identifiers ?? {};
  const findings = evidence.findings ?? [];
  const score = evidence.scores?.requirement_match_confidence;
  const scoreText =
    typeof score === "number" ? `${Math.round(score * 100)}%` : "—";

  return (
    <Card aria-label="Evidencia de prevalidación">
      <CardHeader>
        <CardTitle>Evidencia de prevalidación</CardTitle>
        <p className="mt-1 text-xs text-[color:var(--text-tertiary)]">
          Contexto esperado contra datos extraídos del PDF.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="rounded-md border border-[color:var(--border-subtle)]">
          <EvidenceRow
            label="Proveedor"
            expected={`${evidence.expected.provider?.name ?? "—"} · ${
              evidence.expected.provider?.rfc ?? "—"
            }`}
            extracted={evidenceList(identifiers.rfcs)}
            alignment={evidence.alignment.provider_identity}
          />
          <EvidenceRow
            label="Periodo"
            expected={evidence.expected.requirement?.period ?? "—"}
            extracted={evidenceList(identifiers.period_keys)}
            alignment={evidence.alignment.period}
          />
          <EvidenceRow
            label="Documento"
            expected={evidence.expected.requirement?.document_type ?? "—"}
            extracted={evidence.extracted.document_type ?? "—"}
            alignment={evidence.alignment.document_type}
          />
          <EvidenceRow
            label="Institución"
            expected={evidence.expected.requirement?.institution ?? "—"}
            extracted={evidence.extracted.institution ?? "—"}
            alignment={evidence.alignment.institution}
          />
        </div>

        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Confianza" value={scoreText} />
          <Field
            label="Registro patronal"
            value={evidenceList(identifiers.registro_patronal)}
          />
          <Field label="REPSE" value={evidenceList(identifiers.repse_ids)} />
        </div>

        {findings.length ? (
          <ul className="space-y-1.5">
            {findings.map((finding) => (
              <li
                key={`${finding.code}-${finding.detail_es}`}
                className="flex items-start gap-2 text-xs text-[color:var(--text-secondary)]"
              >
                <span
                  aria-hidden
                  className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full ${
                    finding.severity === "error"
                      ? "bg-[color:var(--status-error-text)]"
                      : finding.severity === "warning"
                        ? "bg-[color:var(--status-warning-text)]"
                        : "bg-[color:var(--text-tertiary)]"
                  }`}
                />
                <span>{finding.detail_es}</span>
              </li>
            ))}
          </ul>
        ) : null}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Phase B — verificación oficial (QR + folios, 2026-06-11)
// ---------------------------------------------------------------------------

/** Uppercase institution label for the "Verificar en …" button. Falls
 *  back to "portal oficial" when the backend couldn't guess. */
const QR_INSTITUTION_LABELS: Record<
  NonNullable<VerificationQrCode["institution_guess"]>,
  string
> = {
  sat: "SAT",
  imss: "IMSS",
  infonavit: "INFONAVIT",
  stps: "STPS",
};

/** Known folio kinds → reviewer-facing Spanish labels. Unknown kinds
 *  are humanized (underscores → spaces, first letter capitalized) so a
 *  new backend extractor never renders a raw snake_case key. */
const FOLIO_KIND_LABELS: Record<string, string> = {
  cfdi_uuid: "Folio fiscal (CFDI)",
  sat_opinion_folio: "Folio SAT",
  imss_opinion_folio: "Folio IMSS",
};

function folioKindLabel(kind: string): string {
  const known = FOLIO_KIND_LABELS[kind];
  if (known) return known;
  const humanized = kind.replace(/_/g, " ").trim();
  return humanized.charAt(0).toUpperCase() + humanized.slice(1);
}

/** Cap raw QR payloads at ~80 chars for display; the full value lives
 *  in the row's ``title`` attribute. */
function truncateQrContent(content: string, max = 80): string {
  return content.length <= max ? content : `${content.slice(0, max)}…`;
}

const QR_DISPLAY_CAP = 5;

/**
 * One decoded QR row.
 *
 * SECURITY RULE (non-negotiable): a clickable link may ONLY be rendered
 * when ``qr.official === true``. The backend allowlists government
 * domains (sat.gob.mx, imss.gob.mx, infonavit.org.mx, stps.gob.mx,
 * gob.mx) before setting that flag. Anything else — even a perfectly
 * plausible-looking URL — is rendered as INERT text, because a
 * malicious upload could embed a phishing QR and the reviewer must not
 * be handed a clickable trap on the decision screen. Non-official QRs
 * on official documents already raise a "Requiere corrección"-style
 * reason in the Autenticidad card, so this row stays factual, not
 * alarmist.
 */
function QrRow({ qr }: { qr: VerificationQrCode }) {
  if (qr.official && qr.is_url) {
    const institution = qr.institution_guess
      ? QR_INSTITUTION_LABELS[qr.institution_guess]
      : "portal oficial";
    return (
      <li className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5 rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] px-3 py-2">
        <div className="min-w-0">
          <p className="truncate font-mono text-xs text-[color:var(--text-secondary)]">
            {qr.host}
          </p>
          <p className="text-[11px] text-[color:var(--text-tertiary)]">
            página {qr.page}
          </p>
        </div>
        <Button asChild size="sm" variant="outline">
          <a href={qr.content} target="_blank" rel="noopener noreferrer">
            Verificar en {institution}
            <ArrowSquareOut className="h-3.5 w-3.5" aria-hidden />
          </a>
        </Button>
      </li>
    );
  }

  if (qr.is_url) {
    // Non-official URL → inert text, never an anchor (see rule above).
    return (
      <li
        title={qr.content}
        className="rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] px-3 py-2"
      >
        <div className="flex items-center gap-2">
          <span
            aria-hidden
            className="h-1.5 w-1.5 shrink-0 rounded-full bg-[color:var(--status-warning-text)]"
          />
          <span className="min-w-0 truncate font-mono text-xs text-[color:var(--text-primary)]">
            {qr.host ?? "—"}
          </span>
          <span className="ml-auto shrink-0 text-[11px] text-[color:var(--text-tertiary)]">
            página {qr.page}
          </span>
        </div>
        <p className="mt-1 text-[11px] text-[color:var(--status-warning-text)]">
          QR apunta a un dominio NO oficial
        </p>
        <p className="mt-0.5 break-all font-mono text-[11px] text-[color:var(--text-tertiary)]">
          {truncateQrContent(qr.content)}
        </p>
      </li>
    );
  }

  // Plain payload (not a URL at all) — e.g. CFDI sello strings.
  return (
    <li
      title={qr.content}
      className="rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] px-3 py-2"
    >
      <div className="flex items-center justify-between gap-3">
        <p className="text-[11px] text-[color:var(--text-tertiary)]">
          Contenido QR (no es URL)
        </p>
        <span className="shrink-0 text-[11px] text-[color:var(--text-tertiary)]">
          página {qr.page}
        </span>
      </div>
      <p className="mt-0.5 break-all font-mono text-xs text-[color:var(--text-secondary)]">
        {truncateQrContent(qr.content)}
      </p>
    </li>
  );
}

/** One extracted folio with click-to-copy (TraceabilityCard idiom:
 *  brief "Copiado" confirmation, quiet failure when the Clipboard API
 *  is blocked). */
function FolioRow({ folio }: { folio: VerificationFolio }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(folio.value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  };

  return (
    <li className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5 rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] px-3 py-2">
      <div className="min-w-0">
        <p className="text-[11px] font-medium uppercase tracking-wide text-[color:var(--text-tertiary)]">
          {folioKindLabel(folio.kind)}
        </p>
        <p className="break-all font-mono text-xs text-[color:var(--text-primary)]">
          {folio.value}
        </p>
      </div>
      <button
        type="button"
        onClick={copy}
        className="shrink-0 rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-page)] px-2.5 py-1 text-xs font-medium text-[color:var(--text-primary)] hover:bg-[color:var(--surface-hover)]"
      >
        {copied ? "Copiado ✓" : "Copiar"}
      </button>
    </li>
  );
}

/**
 * Phase B document revalidation — verification anchors. Surfaces the
 * QR codes and folios extracted from the PDF so the reviewer can jump
 * to the institution's own verification portal (official QRs) or paste
 * a folio into it (CFDI/SAT/IMSS folios) instead of trusting the file
 * on its face. Hidden entirely for legacy/unanalyzed rows; when the
 * analyzer ran and found nothing, the empty state says so explicitly —
 * absence of anchors on a doc that should have them is itself a signal.
 */
function VerificationCard({ detail }: { detail: ReviewerSubmissionDetail }) {
  const verification = detail.verification;
  // Legacy rows (pre-0039) or extraction failure → nothing to assert
  // either way; don't render a card that can only say "no sé".
  if (!verification || !verification.analyzed) return null;

  const qrCodes = verification.qr_codes;
  const folios = verification.folios;
  const visibleQrs = qrCodes.slice(0, QR_DISPLAY_CAP);
  const hiddenQrCount = qrCodes.length - visibleQrs.length;

  return (
    <Card aria-label="Verificación oficial">
      <CardHeader>
        <CardTitle>Verificación oficial</CardTitle>
        <p className="mt-1 text-xs text-[color:var(--text-tertiary)]">
          Códigos QR y folios extraídos del documento para verificarlo en la
          fuente oficial.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        {qrCodes.length === 0 && folios.length === 0 ? (
          <p className="text-sm text-[color:var(--text-secondary)]">
            No se encontraron códigos QR ni folios en el documento.
          </p>
        ) : (
          <>
            {qrCodes.length > 0 ? (
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-[color:var(--text-tertiary)]">
                  Códigos QR ({qrCodes.length})
                </p>
                <ul className="mt-2 space-y-2">
                  {visibleQrs.map((qr, index) => (
                    <QrRow key={`${qr.page}-${index}`} qr={qr} />
                  ))}
                </ul>
                {hiddenQrCount > 0 ? (
                  <p className="mt-2 text-[11px] text-[color:var(--text-tertiary)]">
                    y {hiddenQrCount}{" "}
                    {hiddenQrCount === 1 ? "código más" : "códigos más"} no
                    mostrados
                  </p>
                ) : null}
              </div>
            ) : null}
            {folios.length > 0 ? (
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-[color:var(--text-tertiary)]">
                  Folios ({folios.length})
                </p>
                <ul className="mt-2 space-y-2">
                  {folios.map((folio, index) => (
                    <FolioRow key={`${folio.kind}-${index}`} folio={folio} />
                  ))}
                </ul>
              </div>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Previous attempts (2026-06-10)
// ---------------------------------------------------------------------------

/**
 * Compact history of earlier submissions on the same slot. The detail
 * payload has carried ``previous_attempts`` since Phase 4 but nothing
 * rendered it — reviewers walked the raw-UUID lineage strip one hop at
 * a time instead. Each row links straight to the sibling decision
 * screen. Hidden when the submission is the first attempt.
 */
function PreviousAttemptsCard({
  detail,
  returnToHref,
}: {
  detail: SubmissionDetail;
  returnToHref: string;
}) {
  const attempts = detail.previous_attempts ?? [];
  if (attempts.length === 0) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          Intentos anteriores ({attempts.length})
        </CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="space-y-2">
          {attempts.map((attempt) => (
            <li key={attempt.submission_id}>
              <Link
                href={reviewerDetailHref(attempt.submission_id, returnToHref)}
                className="flex items-center justify-between gap-3 rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] px-3 py-2 transition-colors hover:bg-[color:var(--surface-hover)]"
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium text-[color:var(--text-primary)]">
                    {formatShortDate(attempt.submitted_at)}
                  </p>
                  <p className="truncate font-mono text-xs text-[color:var(--text-tertiary)]">
                    {attempt.filename ?? "Sin archivo"}
                  </p>
                </div>
                <Badge variant={statusVariant(attempt.status)}>
                  {statusLabel(attempt.status)}
                </Badge>
              </Link>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function StatusHeader({
  detail,
  decidedHint,
}: {
  detail: SubmissionDetail;
  decidedHint: string | null;
}) {
  const institutionLabel = detail.requirement.institution
    ? INSTITUTION_LABELS[detail.requirement.institution] ??
      detail.requirement.institution
    : "—";
  return (
    <section className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-5 shadow-xs">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-2">
          <RequirementStatusBadge status={detail.status} />
          <p className="text-base font-semibold text-[color:var(--text-primary)]">
            {detail.requirement.name ?? "Documento por revisar"}
          </p>
          <p className="text-sm text-[color:var(--text-secondary)]">
            {institutionLabel}
            {detail.period.period_key ? ` · ${detail.period.period_key}` : ""}
          </p>
        </div>
        {decidedHint ? (
          <div className="rounded-md border border-[color:var(--status-success-border)] bg-[color:var(--status-success-bg)] px-3 py-2 text-xs font-medium text-[color:var(--status-success-text)]">
            Decisión registrada · ahora {statusLabel(decidedHint)}
          </div>
        ) : null}
      </div>
    </section>
  );
}

/**
 * Build the optional one-line "Sugerencia automática" the Decision
 * Panel shows above the action chips. Only surfaces when the AI lectura
 * flagged a concern — clean approvals don't get a hint, so reviewers
 * aren't anchored on AI for every routine submission.
 *
 * Concern conditions (in priority order):
 *   1. AI returned a mismatch_reason → show it as the hint text.
 *   2. AI confidence < 0.5 → show "Confianza baja, revisa con cuidado".
 *   3. Heuristic mismatch_reason set (AI didn't run / no AI data) →
 *      show the heuristic's reason.
 *
 * Returns null when nothing actionable — the panel hides the hint
 * block entirely in that case.
 */
function deriveAiHint(detail: SubmissionDetail): string | null {
  const shadow = detail.shadow_analysis?.shadow;
  if (shadow?.signals?.mismatch_reason) {
    return shadow.signals.mismatch_reason;
  }
  const conf = shadow?.signals?.requirement_match_confidence;
  if (conf !== null && conf !== undefined && conf < 0.5) {
    return "Confianza baja en la coincidencia con el requisito. Revisa el documento con cuidado.";
  }
  if (detail.document?.mismatch_reason) {
    return detail.document.mismatch_reason;
  }
  return null;
}

// ReasonsCard + SignalRow + ShadowComparisonCard were merged into
// <LecturaDelDocumento/> (apps/web/components/checkwise/admin/
// lectura-del-documento.tsx) during the 2026-06-02 UX rework. The
// merged card surfaces the AI verdict as the primary read, with the
// per-rule prevalidation signals tucked inside a "Señales de
// prevalidación" expandable so reviewers who want them can expand,
// but the default view is no longer dominated by N rule rows.

function ProviderCard({ detail }: { detail: SubmissionDetail }) {
  // Vocabulary pass (2026-06-02): dropped `load_type` (engineer-facing
  // intake mechanism — meaningless to a legal reviewer) and the dual
  // period fields (period.period_key + period.code shown side by side
  // confused reviewers about which was authoritative). We now show
  // one human-readable period, preferring the canonical key, falling
  // back to the raw code only when the key is missing.
  const periodValue =
    detail.period.period_key ?? detail.period.code ?? "—";
  return (
    <Card>
      <CardHeader>
        <CardTitle>Origen del documento</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3 sm:grid-cols-2 text-sm">
        <Field label="Carga" value={formatDate(detail.submitted_at)} />
        <Field label="Periodo" value={periodValue} />
      </CardContent>
    </Card>
  );
}

// Timeline + decision UI now live in shared compositions:
// - <SubmissionTimeline/> in components/checkwise/portal/submission-timeline.tsx
// - <ReviewDecisionPanel/> in components/checkwise/admin/review-decision-panel.tsx

// Collapsed by default. Reviewers need these IDs occasionally — to
// paste into a support ticket, to cross-reference an audit log row —
// but on most visits they don't, so the always-visible card was
// stealing visual attention. One click expands; "Copiar todo" gives
// the reviewer the whole bundle in a single clipboard write.
function TraceabilityCard({ detail }: { detail: SubmissionDetail }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const rows: Array<{ label: string; value: string }> = [
    { label: "Submission", value: detail.submission_id },
  ];
  if (detail.document) {
    rows.push({ label: "Documento", value: detail.document.filename });
    rows.push({ label: "SHA-256", value: detail.document.sha256 });
  }
  if (detail.requirement.requirement_code) {
    rows.push({
      label: "Código canónico",
      value: detail.requirement.requirement_code,
    });
  }

  const copyAll = async () => {
    const bundle = rows.map((r) => `${r.label}: ${r.value}`).join("\n");
    try {
      await navigator.clipboard.writeText(bundle);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      // Clipboard API blocked by browser permissions; surface a quiet
      // failure instead of crashing the reviewer flow.
      setCopied(false);
    }
  };

  return (
    <Card>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between px-5 py-3 text-left"
      >
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-muted-foreground" aria-hidden />
          <CardTitle className="text-sm">Datos para auditoría</CardTitle>
        </div>
        <span className="text-xs text-muted-foreground">
          {open ? "Ocultar" : "Mostrar"}
        </span>
      </button>
      {open ? (
        <CardContent className="space-y-3 border-t border-[color:var(--border-subtle)] pt-3 text-xs text-muted-foreground">
          {rows.map((r) => (
            <p key={r.label}>
              <span className="font-medium text-foreground">{r.label}:</span>{" "}
              <span className="break-all font-mono">{r.value}</span>
            </p>
          ))}
          <button
            type="button"
            onClick={copyAll}
            className="rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-page)] px-2.5 py-1 text-xs font-medium text-[color:var(--text-primary)] hover:bg-[color:var(--surface-hover)]"
          >
            {copied ? "Copiado ✓" : "Copiar todo"}
          </button>
        </CardContent>
      ) : null}
    </Card>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] p-3">
      <p className="text-xs font-medium uppercase tracking-wide text-[color:var(--text-tertiary)]">
        {label}
      </p>
      <p className="mt-1 break-words text-sm font-medium text-[color:var(--text-primary)]">
        {value}
      </p>
    </div>
  );
}

/** Date-only variant for compact lists (previous attempts). */
function formatShortDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("es-MX", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString("es-MX", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

// ---------------------------------------------------------------------------
// Junta 2026-05-23 — visor PDF para el reviewer/admin
// ---------------------------------------------------------------------------
//
// Mirrors the provider-side ``SubmissionPreview`` so Isaac/Paco pueden
// abrir el documento que están a punto de aprobar/rechazar sin salir
// de la pantalla. Backend endpoint:
// ``GET /api/v1/reviewer/submissions/{id}/document`` (gated por rol
// reviewer/internal_admin). El iframe consume un Blob URL para
// evitar problemas de cookies cross-site; el botón "Descargar PDF"
// usa una navegación top-level y dispara ``?download=1`` para el
// audit row.

function ReviewerSubmissionPreview({
  detail,
}: {
  detail: SubmissionDetail;
}) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

  const submissionId = detail.submission_id;
  const documentId = detail.document?.document_id ?? null;

  useEffect(() => {
    if (!documentId) {
      setBlobUrl(null);
      return;
    }
    let cancelled = false;
    let issuedUrl: string | null = null;
    setLoadError(null);
    fetchReviewerSubmissionDocumentBlob(submissionId)
      .then((url) => {
        if (cancelled) {
          URL.revokeObjectURL(url);
          return;
        }
        issuedUrl = url;
        setBlobUrl(url);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ReviewerApiError && err.status === 404) {
          setLoadError(
            "El archivo no está disponible en el almacenamiento. Pide al proveedor que vuelva a subirlo.",
          );
        } else {
          setLoadError("No pudimos cargar la vista previa del documento.");
        }
      });
    return () => {
      cancelled = true;
      if (issuedUrl) URL.revokeObjectURL(issuedUrl);
    };
  }, [submissionId, documentId]);

  const handleDownload = useCallback(async () => {
    if (!detail.document || downloading) return;
    setDownloading(true);
    try {
      const url = await fetchReviewerSubmissionDocumentBlob(submissionId, {
        download: true,
      });
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = detail.document.filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch {
      toast.error("No pudimos descargar el PDF.");
    } finally {
      setDownloading(false);
    }
  }, [detail.document, downloading, submissionId]);

  if (!detail.document) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Documento</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-[color:var(--text-secondary)]">
            Este envío no tiene un archivo asociado.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <FileText
              className="h-4 w-4 text-muted-foreground"
              aria-hidden="true"
            />
            <CardTitle>Vista previa del documento</CardTitle>
          </div>
          <Button
            size="sm"
            variant="outline"
            loading={downloading}
            onClick={handleDownload}
          >
            <DownloadSimple
              className="h-3.5 w-3.5"
              weight="bold"
              aria-hidden="true"
            />
            Descargar PDF
          </Button>
        </div>
        <p className="mt-1 text-sm text-muted-foreground">
          {detail.document.filename} · cargado el{" "}
          {formatDate(detail.submitted_at)}
        </p>
      </CardHeader>
      <CardContent>
        {blobUrl ? (
          <PdfPreview
            blobUrl={blobUrl}
            fileName={detail.document.filename}
            title={`Vista previa de ${detail.document.filename}`}
            className="h-[640px] w-full"
          />
        ) : loadError ? (
          <p className="text-sm text-[color:var(--status-error-text)]">
            {loadError}
          </p>
        ) : (
          <p className="text-sm text-muted-foreground">
            Cargando vista previa…
          </p>
        )}
      </CardContent>
    </Card>
  );
}
