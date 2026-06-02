"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
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
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
} from "@/lib/api/reviewer";
import { DocumentStatus } from "@/lib/constants/statuses";

type PageProps = {
  params: Promise<{ submission_id: string }>;
};

const REVIEWER_ROLES = ["reviewer", "internal_admin"] as const;

export default function ReviewerSubmissionPage({ params }: PageProps) {
  const { submission_id } = use(params);
  const router = useRouter();
  const [session, setSession] = useState<AdminSession | null>(null);
  const [detail, setDetail] = useState<SubmissionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorKind, setErrorKind] = useState<"not_found" | "network" | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const [decided, setDecided] = useState<{ new_status: string; action: ReviewerAction } | null>(
    null,
  );

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
        setDecided({ new_status: result.new_status, action: result.action as ReviewerAction });
        toast.success("Decisión registrada", {
          description: `Este documento ahora está en ${result.new_status}.`,
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
        eyebrow="Reviewer workbench"
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
            <ReviewerSubmissionPreview detail={detail} session={session} />
            <LineageStrip detail={detail} />
            <LecturaDelDocumento detail={detail} />
            <ProviderCard detail={detail} />
            <SubmissionTimeline detail={detail} />
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
                  <Button asChild className="mt-4">
                    <Link href="/admin/reviewer">
                      <ArrowLeft className="h-4 w-4" aria-hidden />
                      Volver a la bandeja
                    </Link>
                  </Button>
                </CardContent>
              </Card>
            ) : (
              <ReviewDecisionPanel
                disabled={panelDisabled}
                disabledReason={
                  isTerminal
                    ? `Este documento ya está en ${detail.status}. Solo una nueva carga del proveedor puede reabrirlo.`
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
            Decisión registrada · ahora {decidedHint}
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

function TraceabilityCard({ detail }: { detail: SubmissionDetail }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-muted-foreground" aria-hidden />
          <CardTitle>Trazabilidad</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="space-y-1 text-xs text-muted-foreground">
        <p>
          <span className="font-medium text-foreground">Submission:</span>{" "}
          <span className="break-all">{detail.submission_id}</span>
        </p>
        {detail.document ? (
          <>
            <p>
              <span className="font-medium text-foreground">Documento:</span>{" "}
              {detail.document.filename}
            </p>
            <p>
              <span className="font-medium text-foreground">SHA-256:</span>{" "}
              <span className="break-all">{detail.document.sha256}</span>
            </p>
          </>
        ) : null}
        {detail.requirement.requirement_code ? (
          <p>
            <span className="font-medium text-foreground">Código canónico:</span>{" "}
            <span className="break-all">{detail.requirement.requirement_code}</span>
          </p>
        ) : null}
      </CardContent>
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
