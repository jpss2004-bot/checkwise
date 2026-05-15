"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  WarningCircle,
  Warning,
  ArrowLeft,
  ArrowRight,
  CheckCircle,
  Clock,
  FileText,
  ShieldCheck,
  CloudArrowUp,
} from "@phosphor-icons/react";

import { ProviderContextBar } from "@/components/checkwise/portal/provider-context-bar";
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
import {
  getSubmissionDetail,
  INSTITUTION_LABELS,
  PortalApiError,
  type RequirementStatus,
  type SubmissionDetail,
  type SubmissionPreviousAttempt,
  type SubmissionSuggestedAction,
} from "@/lib/api/portal";
import { DocumentStatus } from "@/lib/constants/statuses";
import { fetchCurrentSession, type PortalSession } from "@/lib/session/portal";

type PageProps = {
  params: Promise<{ submission_id: string }>;
};

type ErrorKind = "not_found" | "network";

export default function SubmissionDetailPage({ params }: PageProps) {
  const { submission_id } = use(params);
  const router = useRouter();
  const [session, setSession] = useState<PortalSession | null>(null);
  const [detail, setDetail] = useState<SubmissionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorKind, setErrorKind] = useState<ErrorKind | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    fetchCurrentSession().then((current) => {
      if (cancelled) return;
      if (!current) {
        router.replace("/");
        return;
      }
      setSession(current);
    });
    return () => {
      cancelled = true;
    };
  }, [router]);

  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    setLoading(true);
    setErrorKind(null);
    getSubmissionDetail(session, submission_id)
      .then((payload) => {
        if (!cancelled) setDetail(payload);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof PortalApiError && err.status === 404) {
          setErrorKind("not_found");
        } else {
          setErrorKind("network");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [session, submission_id, reloadKey]);

  const retry = useCallback(() => setReloadKey((k) => k + 1), []);

  if (!session) return null;

  return (
    <>
      <ProviderContextBar session={session} />
      <main className="mx-auto max-w-7xl space-y-5 px-5 py-6">
        <PageHeader
          eyebrow="Resultado de carga"
          title={detail?.requirement.name ?? "Detalle de documento"}
          description="Estado actual, razones, contexto regulatorio y línea de tiempo auditable de este documento."
          actions={
            <>
              <Button asChild variant="outline" size="sm">
                <Link href="/portal/dashboard">
                  <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                  Calendario
                </Link>
              </Button>
              <Button asChild variant="outline" size="sm">
                <Link href="/portal/onboarding">
                  <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                  Expediente
                </Link>
              </Button>
            </>
          }
        />

        {loading ? (
          <SubmissionDetailSkeleton />
        ) : errorKind === "not_found" ? (
          <NotFoundState
            title="No encontramos este documento"
            description="El enlace puede haber expirado, o el documento pertenece a otro workspace. Regresa al calendario para verlo desde ahí."
            action={
              <Button asChild>
                <Link href="/portal/dashboard">
                  <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                  Volver al calendario
                </Link>
              </Button>
            }
          />
        ) : errorKind === "network" ? (
          <ErrorState
            title="No pudimos cargar este documento"
            description="Tu conexión pudo haberse interrumpido. No perdiste nada: tu sesión sigue activa."
            onRetry={retry}
            secondary={
              <Button asChild variant="outline" size="sm">
                <Link href="/portal/dashboard">
                  <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                  Calendario
                </Link>
              </Button>
            }
          />
        ) : detail ? (
          <div className="grid gap-5 lg:grid-cols-3">
            <div className="space-y-5 lg:col-span-2">
              <StatusHero detail={detail} />
              <LineageStrip detail={detail} />
              <ReasonsCard detail={detail} />
              <ContextCard detail={detail} />
            </div>
            <div className="space-y-5">
              <SubmissionTimeline detail={detail} />
              <PreviousAttemptsCard previous={detail.previous_attempts} />
              <TraceabilityCard detail={detail} />
            </div>
          </div>
        ) : null}
      </main>
    </>
  );
}

// ---------------------------------------------------------------------------
// Status hero
// ---------------------------------------------------------------------------

const STATUS_HEADLINE: Partial<Record<RequirementStatus, string>> = {
  rechazado: "Este documento fue rechazado y necesita corrección",
  vencido: "Este documento ya no cubre el periodo vigente",
  posible_mismatch: "Este documento podría no coincidir con el requisito",
  requiere_aclaracion: "Este documento requiere una aclaración",
  pendiente_revision: "Tu documento está en revisión",
  prevalidado: "Pasó las prevalidaciones automáticas",
  recibido: "Recibimos tu documento",
  aprobado: "Documento aprobado",
  excepcion_legal: "Aprobado bajo excepción legal",
  no_aplica: "Este requisito no aplica para tu caso",
  pendiente: "Aún no hemos recibido este documento",
};

const CTA_LABEL: Record<SubmissionSuggestedAction, string> = {
  reupload: "Corregir y volver a cargar",
  verify_and_reupload: "Verificar y volver a cargar",
  wait_for_review: "Ver mi calendario",
  no_action: "Ver mi calendario",
};

function StatusHero({ detail }: { detail: SubmissionDetail }) {
  const tone = toneForStatus(detail.status);
  const headline =
    STATUS_HEADLINE[detail.status] ?? "Estado actual del documento";

  const containerClass =
    tone === "attention"
      ? "rounded-lg border border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-bg)] p-5"
      : tone === "approved"
        ? "rounded-lg border border-[color:var(--status-success-border)] bg-[color:var(--status-success-bg)] p-5"
        : "rounded-lg border border-[color:var(--surface-brand-muted)] bg-[color:var(--surface-brand-muted)] p-5";
  const iconClass =
    tone === "attention"
      ? "bg-[color:var(--status-warning-text)] text-[color:var(--text-inverse)]"
      : tone === "approved"
        ? "bg-[color:var(--status-success-text)] text-[color:var(--text-inverse)]"
        : "bg-[color:var(--interactive-primary)] text-[color:var(--text-inverse)]";
  const Icon =
    tone === "attention"
      ? Warning
      : tone === "approved"
        ? CheckCircle
        : Clock;
  const ctaHref = buildReuploadHref(detail);
  const showPrimaryCta =
    detail.suggested_action === "reupload" ||
    detail.suggested_action === "verify_and_reupload";

  return (
    <section className={containerClass} aria-label="Resumen del documento">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-start gap-3">
          <div
            className={`mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${iconClass}`}
          >
            <Icon className="h-5 w-5" aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <RequirementStatusBadge status={detail.status} />
            <p className="mt-2 text-base font-semibold text-[color:var(--text-primary)]">
              {headline}
            </p>
            <p className="mt-1 text-sm text-[color:var(--text-secondary)]">
              {INSTITUTION_LABELS[detail.requirement.institution ?? ""] ??
                detail.requirement.institution ??
                ""}
              {detail.period.period_key ? ` · ${detail.period.period_key}` : ""}
              {detail.period.code && detail.period.code !== detail.period.period_key
                ? ` · ${detail.period.code}`
                : ""}
            </p>
          </div>
        </div>
        {showPrimaryCta ? (
          <Button asChild className="self-start sm:self-auto">
            <Link href={ctaHref}>
              {CTA_LABEL[detail.suggested_action]}
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          </Button>
        ) : (
          <Button asChild variant="outline" className="self-start sm:self-auto">
            <Link href="/portal/dashboard">
              {CTA_LABEL[detail.suggested_action]}
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          </Button>
        )}
      </div>
    </section>
  );
}

function toneForStatus(status: RequirementStatus): "attention" | "approved" | "neutral" {
  if (
    status === DocumentStatus.RECHAZADO ||
    status === DocumentStatus.VENCIDO ||
    status === DocumentStatus.POSIBLE_MISMATCH ||
    status === DocumentStatus.REQUIERE_ACLARACION
  )
    return "attention";
  if (
    status === DocumentStatus.APROBADO ||
    status === DocumentStatus.EXCEPCION_LEGAL ||
    status === DocumentStatus.NO_APLICA
  )
    return "approved";
  return "neutral";
}

function buildReuploadHref(detail: SubmissionDetail): string {
  const params = new URLSearchParams();
  if (detail.requirement.name) params.set("requirement", detail.requirement.name);
  if (detail.requirement.requirement_code)
    params.set("requirement_code", detail.requirement.requirement_code);
  if (detail.requirement.institution)
    params.set("institution", detail.requirement.institution);
  if (detail.load_type) params.set("load_type", detail.load_type);
  if (detail.period.code) params.set("period_label", detail.period.code);
  if (detail.period.period_key) params.set("period_key", detail.period.period_key);
  // Phase 3 — when the suggested action is to reupload (i.e. this
  // submission is in a replacement-eligible state), thread its id
  // through so the wizard POSTs ``supersedes_submission_id`` and the
  // backend can link the new attempt to this one.
  if (
    detail.suggested_action === "reupload" ||
    detail.suggested_action === "verify_and_reupload"
  ) {
    params.set("replaces", detail.submission_id);
  }
  return `/portal/upload?${params.toString()}`;
}

// ---------------------------------------------------------------------------
// Reasons
// ---------------------------------------------------------------------------

function ReasonsCard({ detail }: { detail: SubmissionDetail }) {
  if (detail.reasons.length === 0 && !detail.document?.mismatch_reason) {
    return null;
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>Por qué se devolvió</CardTitle>
        <p className="mt-1 text-sm text-muted-foreground">
          Estos son los puntos que la revisión humana o las prevalidaciones
          automáticas marcaron sobre este documento.
        </p>
      </CardHeader>
      <CardContent className="space-y-2">
        {detail.document?.mismatch_reason ? (
          <ReasonRow
            severity="warning"
            title="Posible mismatch detectado"
            message={detail.document.mismatch_reason}
          />
        ) : null}
        {detail.reasons.map((reason) => (
          <ReasonRow
            key={reason.rule_code}
            severity={reason.severity}
            title={REASON_TITLES[reason.rule_code] ?? reason.rule_code}
            message={reason.message ?? "Sin detalle adicional."}
            humanReview={reason.requires_human_review}
          />
        ))}
      </CardContent>
    </Card>
  );
}

const REASON_TITLES: Record<string, string> = {
  pdf_encrypted: "PDF protegido con contraseña",
  pdf_readable_text: "Texto del PDF no es legible",
  duplicate_hash: "Documento duplicado",
  vendor_match: "Confirmación de proveedor pendiente",
  period_match: "Confirmación de periodo pendiente",
  requirement_match: "Coincidencia con requisito",
  document_intelligence: "Señales documentales automáticas",
  human_review_required: "Revisión humana requerida",
  expired_document: "Documento vencido",
};

function ReasonRow({
  severity,
  title,
  message,
  humanReview,
}: {
  severity: string;
  title: string;
  message: string;
  humanReview?: boolean;
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
        aria-hidden="true"
      />
      <div className="min-w-0">
        <p className="text-sm font-medium text-[color:var(--text-primary)]">{title}</p>
        <p className="mt-0.5 text-sm text-[color:var(--text-secondary)]">{message}</p>
        {humanReview ? (
          <p className="mt-1 text-xs font-medium uppercase tracking-wide text-[color:var(--text-tertiary)]">
            Requiere revisión humana
          </p>
        ) : null}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Context card
// ---------------------------------------------------------------------------

function ContextCard({ detail }: { detail: SubmissionDetail }) {
  const submittedDate = formatDate(detail.submitted_at);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Contexto del documento</CardTitle>
        <p className="mt-1 text-sm text-muted-foreground">
          Estos datos quedaron registrados al momento de la carga y se usan para
          relacionar el documento con tu expediente regulatorio.
        </p>
      </CardHeader>
      <CardContent>
        <dl className="grid gap-3 sm:grid-cols-2">
          <Field label="Requisito" value={detail.requirement.name ?? "—"} />
          <Field
            label="Institución"
            value={
              INSTITUTION_LABELS[detail.requirement.institution ?? ""] ??
              detail.requirement.institution ??
              "—"
            }
          />
          <Field label="Periodo regulatorio" value={detail.period.period_key ?? "—"} />
          <Field
            label="Periodo capturado"
            value={detail.period.code ?? "—"}
          />
          <Field label="Tipo de carga" value={detail.load_type} />
          <Field label="Carga registrada" value={submittedDate} />
        </dl>
      </CardContent>
    </Card>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border/70 bg-white px-3 py-2">
      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </dt>
      <dd className="mt-1 break-words text-sm font-medium">{value}</dd>
    </div>
  );
}

// Timeline now lives in <SubmissionTimeline/> — merges history + events
// (see frontend/components/checkwise/portal/submission-timeline.tsx).

// ---------------------------------------------------------------------------
// Previous attempts
// ---------------------------------------------------------------------------

function PreviousAttemptsCard({
  previous,
}: {
  previous: SubmissionPreviousAttempt[];
}) {
  if (previous.length === 0) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Cargas anteriores</CardTitle>
        <p className="mt-1 text-sm text-muted-foreground">
          Otros intentos para esta misma obligación regulatoria.
        </p>
      </CardHeader>
      <CardContent>
        <ul className="space-y-2">
          {previous.map((attempt) => (
            <li
              key={attempt.submission_id}
              className="flex items-center gap-2 rounded-md border border-border bg-white p-3"
            >
              <FileText
                className="h-4 w-4 shrink-0 text-muted-foreground"
                aria-hidden="true"
              />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">
                  {attempt.filename ?? "Documento sin nombre"}
                </p>
                <p className="text-xs text-muted-foreground">
                  {formatDate(attempt.submitted_at)}
                </p>
              </div>
              <Link
                href={`/portal/submissions/${attempt.submission_id}`}
                className="text-xs font-medium text-primary hover:underline"
              >
                Ver
              </Link>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Traceability footer
// ---------------------------------------------------------------------------

function TraceabilityCard({ detail }: { detail: SubmissionDetail }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <CloudArrowUp className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          <CardTitle>Datos de trazabilidad</CardTitle>
        </div>
        <p className="mt-1 text-sm text-muted-foreground">
          Conserva esta información si necesitas referenciar el documento.
        </p>
      </CardHeader>
      <CardContent className="space-y-2 text-xs text-muted-foreground">
        <p>
          <span className="font-medium text-foreground">Submission ID:</span>{" "}
          <span className="break-all">{detail.submission_id}</span>
        </p>
        {detail.document ? (
          <>
            <p>
              <span className="font-medium text-foreground">Document ID:</span>{" "}
              <span className="break-all">{detail.document.document_id}</span>
            </p>
            <p>
              <span className="font-medium text-foreground">Archivo:</span>{" "}
              {detail.document.filename}
            </p>
            <p>
              <span className="font-medium text-foreground">SHA-256:</span>{" "}
              <span className="break-all">{detail.document.sha256}</span>
            </p>
            <p>
              <span className="font-medium text-foreground">Páginas PDF:</span>{" "}
              {detail.document.page_count ?? "—"}
            </p>
          </>
        ) : null}
        {detail.requirement.requirement_code ? (
          <p>
            <span className="font-medium text-foreground">Código canónico:</span>{" "}
            <span className="break-all">
              {detail.requirement.requirement_code}
            </span>
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Replacement lineage strip (Phase 4)
// ---------------------------------------------------------------------------

function LineageStrip({ detail }: { detail: SubmissionDetail }) {
  if (!detail.supersedes_submission_id && !detail.superseded_by_submission_id) {
    return null;
  }
  return (
    <section
      aria-label="Lineage de reemplazos"
      className="rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-sunken)] p-4 text-sm"
    >
      {detail.supersedes_submission_id ? (
        <p>
          <span className="font-medium text-[color:var(--text-primary)]">
            Reemplaza intento anterior:
          </span>{" "}
          <Link
            href={`/portal/submissions/${detail.supersedes_submission_id}`}
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
            href={`/portal/submissions/${detail.superseded_by_submission_id}`}
            className="font-mono text-xs text-[color:var(--text-brand)] underline-offset-2 hover:underline"
          >
            {detail.superseded_by_submission_id}
          </Link>
        </p>
      ) : null}
    </section>
  );
}

function formatDate(iso: string): string {
  try {
    const date = new Date(iso);
    return date.toLocaleString("es-MX", {
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
