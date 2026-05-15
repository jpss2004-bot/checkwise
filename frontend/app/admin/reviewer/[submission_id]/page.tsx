"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  WarningCircle,
  Warning,
  ArrowLeft,
  CheckCircle,
  FileText,
  ShieldCheck,
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
import { SubmissionTimeline } from "@/components/checkwise/portal/submission-timeline";
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
  getReviewerSubmission,
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
      router.replace("/admin/login");
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
          router.replace("/admin/login");
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
    async (action: ReviewerAction, reason: string | null) => {
      if (!session || !detail) return;
      try {
        const result = await submitDecision(
          session.access_token,
          detail.submission_id,
          action,
          reason,
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
            <LineageStrip detail={detail} />
            <ReasonsCard detail={detail} />
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
                    Este documento ahora está en{" "}
                    <span className="font-medium text-[color:var(--text-primary)]">
                      {decided.new_status}
                    </span>
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
              />
            )}
            <TraceabilityCard detail={detail} />
          </div>
        </div>
      ) : null}
    </main>
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

function ReasonsCard({ detail }: { detail: SubmissionDetail }) {
  if (detail.reasons.length === 0 && !detail.document?.mismatch_reason) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Señales automáticas</CardTitle>
        <p className="mt-1 text-sm text-muted-foreground">
          Lo que la prevalidación detectó. La decisión final es tuya.
        </p>
      </CardHeader>
      <CardContent className="space-y-2">
        {detail.document?.mismatch_reason ? (
          <SignalRow
            severity="warning"
            title="Posible mismatch"
            message={detail.document.mismatch_reason}
          />
        ) : null}
        {detail.reasons.map((r) => (
          <SignalRow
            key={r.rule_code}
            severity={r.severity}
            title={r.rule_code}
            message={r.message ?? "Sin detalle adicional."}
          />
        ))}
      </CardContent>
    </Card>
  );
}

function SignalRow({
  severity,
  title,
  message,
}: {
  severity: string;
  title: string;
  message: string;
}) {
  const Icon =
    severity === "error" ? WarningCircle : severity === "warning" ? Warning : ShieldCheck;
  const iconColor =
    severity === "error"
      ? "text-[color:var(--status-error-text)]"
      : severity === "warning"
        ? "text-[color:var(--status-warning-text)]"
        : "text-[color:var(--text-brand)]";
  return (
    <div className="flex items-start gap-3 rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-3">
      <Icon
        className={`mt-0.5 h-4 w-4 shrink-0 ${iconColor}`}
        weight="fill"
        aria-hidden
      />
      <div className="min-w-0">
        <p className="text-sm font-medium text-[color:var(--text-primary)]">{title}</p>
        <p className="mt-0.5 text-sm text-[color:var(--text-secondary)]">{message}</p>
      </div>
    </div>
  );
}

function ProviderCard({ detail }: { detail: SubmissionDetail }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Origen del documento</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3 sm:grid-cols-2 text-sm">
        <Field
          label="Carga"
          value={formatDate(detail.submitted_at)}
        />
        <Field
          label="Tipo"
          value={detail.load_type}
        />
        <Field
          label="Periodo regulatorio"
          value={detail.period.period_key ?? "—"}
        />
        <Field
          label="Periodo capturado"
          value={detail.period.code ?? "—"}
        />
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
