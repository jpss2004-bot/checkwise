"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Warning,
  ArrowLeft,
  ArrowRight,
  CheckCircle,
  Clock,
  DownloadSimple,
  FileText,
} from "@phosphor-icons/react";

import { PortalAppShell } from "@/components/checkwise/portal/portal-app-shell";
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
  fetchSubmissionDocumentBlob,
  getSubmissionDetail,
  INSTITUTION_LABELS,
  PortalApiError,
  submissionDownloadUrl,
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
    <PortalAppShell session={session}>
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
            description="El enlace puede haber expirado, o el documento pertenece a otro expediente. Regresa al calendario para verlo desde ahí."
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
              <ReviewerNoteCard detail={detail} />
              <SubmissionPreview detail={detail} session={session} />
              <LineageStrip detail={detail} />
              <ContextCard detail={detail} />
            </div>
            <div className="space-y-5">
              <SubmissionTimeline detail={detail} />
              <PreviousAttemptsCard previous={detail.previous_attempts} />
            </div>
          </div>
        ) : null}
      </main>
    </PortalAppShell>
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
// Phase 2 / Slice 2B — reviewer-note hero card
// ---------------------------------------------------------------------------
//
// Replaces the former ``<ReasonsCard>`` which exposed every
// prevalidation signal (pdf_encrypted, sha256_hash, vendor_match, …)
// to providers. The reviewer's plain-Spanish reason is the headline
// information on an actionable submission; the prevalidation diagnostic
// signals belong on the admin/reviewer surface, not the provider page.
//
// Card renders when the submission is in an actionable state AND
// either the reviewer left a note OR the automatic detector emitted
// a ``mismatch_reason``. For ``rechazado`` / ``requiere_aclaracion``
// the reviewer's words drive the message; for ``posible_mismatch``
// without a reviewer decision yet, the detector's reason takes over.

const REVIEWER_NOTE_STATUSES: ReadonlySet<RequirementStatus> = new Set<
  RequirementStatus
>([
  DocumentStatus.RECHAZADO,
  DocumentStatus.REQUIERE_ACLARACION,
  DocumentStatus.POSIBLE_MISMATCH,
]);

const REVIEWER_NOTE_HEADINGS: Partial<Record<RequirementStatus, string>> = {
  rechazado: "Motivo del rechazo",
  requiere_aclaracion: "Aclaración solicitada",
  posible_mismatch: "Posible discrepancia",
};

function ReviewerNoteCard({ detail }: { detail: SubmissionDetail }) {
  if (!REVIEWER_NOTE_STATUSES.has(detail.status)) return null;
  const note =
    detail.reviewer_note ?? detail.document?.mismatch_reason ?? null;
  if (!note) return null;
  const heading =
    REVIEWER_NOTE_HEADINGS[detail.status] ?? "Nota del revisor";
  const sourceLabel = detail.reviewer_note
    ? "Nota del revisor"
    : "Detectado automáticamente";
  return (
    <Card
      role="region"
      aria-label={heading}
      className="border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-bg)]"
    >
      <CardHeader>
        <div className="flex items-center gap-2">
          <Warning
            className="h-4 w-4 text-[color:var(--status-warning-text)]"
            weight="fill"
            aria-hidden="true"
          />
          <CardTitle>{heading}</CardTitle>
        </div>
        <p className="mt-1 text-xs font-mono uppercase tracking-wide text-[color:var(--text-tertiary)]">
          {sourceLabel}
        </p>
      </CardHeader>
      <CardContent>
        <p className="text-[15px] leading-relaxed text-[color:var(--text-primary)]">
          {note}
        </p>
      </CardContent>
    </Card>
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
// (see apps/web/components/checkwise/portal/submission-timeline.tsx).

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

// Phase 2 / Slice 2A — the former ``<TraceabilityCard />`` was removed
// from this surface. It exposed Submission ID, Document ID, SHA-256,
// page count and the canonical requirement_code to providers, which
// violates the project non-negotiable "do not expose file hashes, OCR
// internals, or technical validation details to providers." If a
// support workflow ever needs those identifiers, surface them on the
// admin/reviewer page or behind a staff-gated detail view — never
// here.

// ---------------------------------------------------------------------------
// Inline PDF preview (Jorge feedback 2026-05-21)
// ---------------------------------------------------------------------------

function SubmissionPreview({
  detail,
  session,
}: {
  detail: SubmissionDetail;
  session: PortalSession;
}) {
  // Fetch the PDF via the portal API client (Bearer + cookie) and
  // serve it to the iframe as a Blob URL. Pointing the iframe at the
  // API URL directly relied on the cross-site cookie surviving
  // ``SameSite=Lax`` in dev and third-party cookie blocking in prod;
  // both can drop the cookie. The Blob path authenticates with the
  // JWT every portal page already holds and works regardless of
  // cookie policy. ``URL.revokeObjectURL`` runs on unmount and on
  // submission id change so we never leak object URLs.
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [loadError, setLoadError] = useState(false);
  const submissionId = detail.submission_id;
  const documentId = detail.document?.document_id ?? null;

  useEffect(() => {
    if (!documentId) {
      setBlobUrl(null);
      return;
    }
    let cancelled = false;
    let issuedUrl: string | null = null;
    setLoadError(false);
    fetchSubmissionDocumentBlob(session, submissionId)
      .then((url) => {
        if (cancelled) {
          URL.revokeObjectURL(url);
          return;
        }
        issuedUrl = url;
        setBlobUrl(url);
      })
      .catch(() => {
        if (!cancelled) setLoadError(true);
      });
    return () => {
      cancelled = true;
      if (issuedUrl) URL.revokeObjectURL(issuedUrl);
    };
  }, [session, submissionId, documentId]);

  if (!detail.document) return null;
  // Phase 5 / Slice 5A — "Descargar PDF" anchor. Points at the same
  // backend endpoint as the preview iframe but with ?download=1 so
  // the browser triggers a save dialog AND the backend writes a
  // ``provider.document_downloaded`` audit row. The anchor is a
  // top-level navigation (``target=_blank``) so cookie auth carries
  // even when the iframe Blob path can't (the iframe uses Bearer
  // JWT via fetch; a plain anchor cannot set headers).
  const downloadHref = submissionDownloadUrl(session, detail.submission_id);
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
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
          {detail.document.filename} · cargado el {formatDate(detail.submitted_at)}
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
          <p className="text-sm text-muted-foreground">
            No pudimos cargar la vista previa. Recarga la página o
            inténtalo de nuevo en unos momentos.
          </p>
        ) : (
          <div
            className="h-[640px] w-full animate-pulse rounded-md border border-border bg-muted/40"
            aria-label="Cargando vista previa"
          />
        )}
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
