"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
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
import { SubmissionTimeline } from "@/components/checkwise/portal/submission-timeline";
import { FeedbackLauncher } from "@/components/feedback/feedback-launcher";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MetadataStrip, type MetadataItem } from "@/components/ui/metadata-strip";
import { PageHeader } from "@/components/ui/page-header";
import { toast } from "@/components/ui/toast";
import {
  clearAdminSession,
  readAdminSession,
  type AdminSession,
} from "@/lib/session/admin";
import { INSTITUTION_LABELS, type SubmissionDetail } from "@/lib/api/portal";
import {
  fetchReviewerSubmissionDocumentBlob,
  getReviewerSubmission,
  reviewerDocumentDownloadUrl,
  ReviewerApiError,
  submitDecision,
  type ReviewerSubmissionDetail,
} from "@/lib/api/reviewer";
import { personaLabel } from "@/lib/constants/labels";
import {
  DocumentStatus,
  statusLabel,
  statusVariant,
} from "@/lib/constants/statuses";

type PageProps = {
  params: Promise<{ submission_id: string }>;
};

const REVIEWER_ROLES = ["reviewer", "internal_admin"] as const;

export default function ReviewerSubmissionPage({ params }: PageProps) {
  const { submission_id } = use(params);
  const router = useRouter();
  const [session, setSession] = useState<AdminSession | null>(null);
  const [detail, setDetail] = useState<ReviewerSubmissionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorKind, setErrorKind] = useState<"not_found" | "network" | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const [decided, setDecided] = useState<{
    new_status: string;
    action: ReviewerAction;
    /** Oldest still-pending submission (FIFO) — drives "Siguiente
     *  documento". Null when the queue is drained. */
    next_pending_submission_id: string | null;
  } | null>(null);

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
    getReviewerSubmission(session.access_token, submission_id)
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
    ) => {
      if (!session || !detail) return;
      try {
        const result = await submitDecision(
          session.access_token,
          detail.submission_id,
          action,
          reason,
          observations,
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
        router.push(`/admin/reviewer/${nextId}`);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [decided, router]);

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
            <Link href="/admin/reviewer">
              <ArrowLeft className="h-4 w-4" aria-hidden />
              Bandeja
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
              <Link href="/admin/reviewer">
                <ArrowLeft className="h-4 w-4" aria-hidden />
                Volver a la bandeja
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
            <ReviewerSubmissionPreview detail={detail} session={session} />
            <LineageStrip detail={detail} />
            <LecturaDelDocumento detail={detail} />
            <ProviderCard detail={detail} />
            <PreviousAttemptsCard detail={detail} />
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
                            `/admin/reviewer/${decided.next_pending_submission_id}`,
                          )
                        }
                      >
                        Siguiente documento
                        <ArrowRight className="h-4 w-4" aria-hidden />
                      </Button>
                      <Button asChild variant="outline" className="w-full">
                        <Link href="/admin/reviewer">
                          <ArrowLeft className="h-4 w-4" aria-hidden />
                          Volver a la bandeja
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
                        <Link href="/admin/reviewer">
                          <ArrowLeft className="h-4 w-4" aria-hidden />
                          Volver a la bandeja
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
function LineageStrip({ detail }: { detail: SubmissionDetail }) {
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
            href={`/admin/reviewer/${detail.supersedes_submission_id}`}
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
            href={`/admin/reviewer/${detail.superseded_by_submission_id}`}
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

type RfcComparison =
  | { state: "unknown"; expected: string | null; detected: string | null }
  | { state: "match" | "mismatch"; expected: string; detected: string };

/**
 * Pull the OCR/AI-detected RFCs from the inspection payload, mirroring
 * <LecturaDelDocumento/>'s primary-signal choice (AI shadow signals
 * when the shadow run produced them, heuristic otherwise) so this
 * comparison never disagrees with the "RFC detectado" row below it.
 */
function detectedRfcs(detail: SubmissionDetail): string[] {
  const payload = detail.shadow_analysis ?? null;
  if (!payload) return [];
  const signals = payload.shadow?.signals ?? payload.heuristic?.signals ?? null;
  return signals?.detected_rfcs ?? [];
}

/**
 * Case-insensitive, trimmed comparison of the registry's expected RFC
 * against the detected candidates. Any candidate matching counts as a
 * match (multi-RFC documents like contratos list both parties). When
 * either side is missing we surface a neutral "Sin comparación" state
 * instead of a scary ✗.
 */
function compareRfc(
  expectedRaw: string | null,
  detected: string[],
): RfcComparison {
  const expected = expectedRaw?.trim() || null;
  const candidates = detected
    .map((rfc) => rfc.trim())
    .filter((rfc) => rfc.length > 0);
  if (!expected || candidates.length === 0) {
    return { state: "unknown", expected, detected: candidates[0] ?? null };
  }
  const matched = candidates.find(
    (rfc) => rfc.toUpperCase() === expected.toUpperCase(),
  );
  if (matched) {
    return { state: "match", expected, detected: matched };
  }
  return { state: "mismatch", expected, detected: candidates[0] };
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

  const comparison = compareRfc(vendor.vendor_rfc, detectedRfcs(detail));

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
            {comparison.detected ?? "—"}
          </span>
          {comparison.state === "match" ? (
            <Badge variant="success">✓ Coincide</Badge>
          ) : comparison.state === "mismatch" ? (
            <Badge variant="destructive">✗ No coincide</Badge>
          ) : (
            <Badge variant="secondary">Sin comparación</Badge>
          )}
        </span>
      ),
    },
  ];

  return <MetadataStrip items={items} />;
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
function PreviousAttemptsCard({ detail }: { detail: SubmissionDetail }) {
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
                href={`/admin/reviewer/${attempt.submission_id}`}
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
  session,
}: {
  detail: SubmissionDetail;
  session: AdminSession;
}) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const submissionId = detail.submission_id;
  const documentId = detail.document?.document_id ?? null;
  const token = session.access_token;

  useEffect(() => {
    if (!documentId) {
      setBlobUrl(null);
      return;
    }
    let cancelled = false;
    let issuedUrl: string | null = null;
    setLoadError(null);
    fetchReviewerSubmissionDocumentBlob(token, submissionId)
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
  }, [token, submissionId, documentId]);

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

  const downloadHref = reviewerDocumentDownloadUrl(submissionId);

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
          <Button asChild size="sm" variant="outline">
            <a
              href={downloadHref}
              target="_blank"
              rel="noreferrer"
              download={detail.document.filename}
            >
              <DownloadSimple
                className="h-3.5 w-3.5"
                weight="bold"
                aria-hidden="true"
              />
              Descargar PDF
            </a>
          </Button>
        </div>
        <p className="mt-1 text-sm text-muted-foreground">
          {detail.document.filename} · cargado el{" "}
          {formatDate(detail.submitted_at)}
        </p>
      </CardHeader>
      <CardContent>
        {blobUrl ? (
          <>
            <iframe
              src={blobUrl}
              title={`Vista previa de ${detail.document.filename}`}
              className="h-[640px] w-full rounded-md border border-border bg-white"
            />
            <p className="mt-2 text-xs text-muted-foreground">
              Si la vista previa no carga,{" "}
              <a
                href={blobUrl}
                target="_blank"
                rel="noreferrer"
                className="text-primary hover:underline"
              >
                ábrelo en una pestaña nueva
              </a>
              .
            </p>
          </>
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
