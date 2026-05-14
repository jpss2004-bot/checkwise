"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ClipboardList,
  FileText,
  Gavel,
  History,
  Loader2,
  MessageCircleQuestion,
  ShieldCheck,
  XCircle,
} from "lucide-react";

import { BrandLogo } from "@/components/checkwise/brand-logo";
import { RequirementStatusBadge } from "@/components/checkwise/portal/requirement-status-badge";
import {
  ErrorState,
  NotFoundState,
  SubmissionDetailSkeleton,
} from "@/components/checkwise/portal/state-surfaces";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import {
  clearAdminSession,
  readAdminSession,
  type AdminSession,
} from "@/lib/admin-session";
import { INSTITUTION_LABELS, type SubmissionDetail } from "@/lib/portal-client";
import {
  type DecisionAction,
  getReviewerSubmission,
  ReviewerApiError,
  submitDecision,
} from "@/lib/reviewer-client";

type PageProps = {
  params: Promise<{ submission_id: string }>;
};

const REVIEWER_ROLES = ["reviewer", "internal_admin"] as const;

type DecisionState = {
  action: DecisionAction;
  reason: string;
};

export default function ReviewerSubmissionPage({ params }: PageProps) {
  const { submission_id } = use(params);
  const router = useRouter();
  const [session, setSession] = useState<AdminSession | null>(null);
  const [detail, setDetail] = useState<SubmissionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorKind, setErrorKind] = useState<"not_found" | "network" | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const [decision, setDecision] = useState<DecisionState | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [decided, setDecided] = useState<{ new_status: string; action: DecisionAction } | null>(
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

  async function onSubmitDecision() {
    if (!session || !decision || !detail) return;
    setDecisionError(null);
    const requiresReason = decision.action !== "approve";
    const reason = decision.reason.trim();
    if (requiresReason && !reason) {
      setDecisionError("Esta decisión necesita una razón.");
      return;
    }
    setSubmitting(true);
    try {
      const result = await submitDecision(
        session.access_token,
        detail.submission_id,
        decision.action,
        reason || null,
      );
      setDecided({ new_status: result.new_status, action: result.action });
      setDecision(null);
    } catch (err) {
      if (err instanceof ReviewerApiError && err.status === 409) {
        setDecisionError("Este documento ya tiene una decisión registrada.");
      } else if (err instanceof ReviewerApiError && err.status === 422) {
        setDecisionError("La razón es obligatoria para esta decisión.");
      } else {
        setDecisionError("No pudimos registrar la decisión. Intenta de nuevo.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (!session) return null;

  return (
    <main className="mx-auto max-w-6xl space-y-5 px-5 py-8">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0 space-y-2">
          <div className="flex items-center gap-3">
            <BrandLogo variant="compact" size="md" />
            <span className="hidden h-5 w-px bg-border sm:block" />
            <p className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              <ClipboardList className="h-4 w-4 text-primary" aria-hidden />
              Bandeja de revisión
            </p>
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {detail?.requirement.name ?? "Documento por revisar"}
          </h1>
        </div>
        <Button asChild variant="outline" size="sm">
          <Link href="/admin/reviewer">
            <ArrowLeft className="h-4 w-4" aria-hidden />
            Bandeja
          </Link>
        </Button>
      </header>

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
            <ReasonsCard detail={detail} />
            <ProviderCard detail={detail} />
            <TimelineCard detail={detail} />
          </div>
          <div className="space-y-5">
            <DecisionCard
              detail={detail}
              decision={decision}
              setDecision={setDecision}
              onSubmit={onSubmitDecision}
              submitting={submitting}
              decisionError={decisionError}
              decided={decided}
            />
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
    <section className="rounded-md border border-border bg-white p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-2">
          <RequirementStatusBadge status={detail.status} />
          <p className="text-base font-semibold">
            {detail.requirement.name ?? "Documento por revisar"}
          </p>
          <p className="text-sm text-muted-foreground">
            {institutionLabel}
            {detail.period.period_key ? ` · ${detail.period.period_key}` : ""}
          </p>
        </div>
        {decidedHint ? (
          <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-medium text-emerald-900">
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
    severity === "error" ? AlertCircle : severity === "warning" ? AlertTriangle : ShieldCheck;
  const iconColor =
    severity === "error"
      ? "text-red-600"
      : severity === "warning"
        ? "text-amber-600"
        : "text-primary";
  return (
    <div className="flex items-start gap-3 rounded-md border border-border bg-white p-3">
      <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${iconColor}`} aria-hidden />
      <div className="min-w-0">
        <p className="text-sm font-medium">{title}</p>
        <p className="mt-0.5 text-sm text-muted-foreground">{message}</p>
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

function TimelineCard({ detail }: { detail: SubmissionDetail }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <History className="h-4 w-4 text-primary" aria-hidden />
          <CardTitle>Línea de tiempo</CardTitle>
        </div>
      </CardHeader>
      <CardContent>
        {detail.history.length === 0 ? (
          <p className="rounded-md border border-border bg-muted/40 p-3 text-sm text-muted-foreground">
            Aún no hay cambios de estado registrados.
          </p>
        ) : (
          <ol className="space-y-3">
            {detail.history.map((h, i) => (
              <li key={`${h.occurred_at}-${i}`} className="flex items-start gap-3">
                <span
                  aria-hidden
                  className="mt-1.5 flex h-2.5 w-2.5 shrink-0 rounded-full bg-primary"
                />
                <div className="min-w-0">
                  <p className="text-sm font-medium">
                    {h.from_status ? `${h.from_status} → ${h.to_status}` : h.to_status}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {formatDate(h.occurred_at)} · {h.actor}
                  </p>
                  {h.reason ? (
                    <p className="mt-1 text-sm text-muted-foreground">{h.reason}</p>
                  ) : null}
                </div>
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}

const ACTIONS: {
  action: DecisionAction;
  label: string;
  icon: typeof Gavel;
  variant: "approve" | "reject" | "clarify" | "exception";
}[] = [
  { action: "approve", label: "Aprobar", icon: CheckCircle2, variant: "approve" },
  { action: "reject", label: "Rechazar", icon: XCircle, variant: "reject" },
  {
    action: "request_clarification",
    label: "Pedir aclaración",
    icon: MessageCircleQuestion,
    variant: "clarify",
  },
  { action: "mark_exception", label: "Excepción legal", icon: Gavel, variant: "exception" },
];

function DecisionCard({
  detail,
  decision,
  setDecision,
  onSubmit,
  submitting,
  decisionError,
  decided,
}: {
  detail: SubmissionDetail;
  decision: { action: DecisionAction; reason: string } | null;
  setDecision: (next: { action: DecisionAction; reason: string } | null) => void;
  onSubmit: () => void;
  submitting: boolean;
  decisionError: string | null;
  decided: { new_status: string; action: DecisionAction } | null;
}) {
  if (decided) {
    return (
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-emerald-600" aria-hidden />
            <CardTitle>Decisión registrada</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-sm">
            Este documento ahora está en{" "}
            <span className="font-medium">{decided.new_status}</span>. La línea
            de tiempo y el detalle del proveedor reflejan tu decisión.
          </p>
          <Button asChild className="mt-4 active:scale-[0.98]">
            <Link href="/admin/reviewer">
              <ArrowLeft className="h-4 w-4" aria-hidden />
              Volver a la bandeja
            </Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  // Resolved states (already decided previously) — no further actions.
  if (
    detail.status === "aprobado" ||
    detail.status === "rechazado" ||
    detail.status === "excepcion_legal"
  ) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Documento resuelto</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <p>
            Este documento ya tiene una decisión registrada como{" "}
            <span className="font-medium text-foreground">{detail.status}</span>.
            Solo una nueva carga del proveedor puede reabrirlo.
          </p>
        </CardContent>
      </Card>
    );
  }

  const requiresReason = decision?.action && decision.action !== "approve";
  return (
    <Card>
      <CardHeader>
        <CardTitle>Tu decisión</CardTitle>
        <p className="mt-1 text-sm text-muted-foreground">
          Elige una acción. Las que devuelven el documento al proveedor
          requieren una razón.
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {ACTIONS.map((opt) => {
            const Icon = opt.icon;
            const isActive = decision?.action === opt.action;
            return (
              <button
                key={opt.action}
                type="button"
                onClick={() =>
                  setDecision({ action: opt.action, reason: decision?.reason ?? "" })
                }
                className={`flex items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors active:scale-[0.98] ${
                  isActive
                    ? actionActiveClass(opt.variant)
                    : "border-border bg-white hover:bg-muted"
                }`}
                aria-pressed={isActive}
                data-action={opt.action}
              >
                <Icon className="h-4 w-4" aria-hidden />
                {opt.label}
              </button>
            );
          })}
        </div>
        {decision ? (
          <div className="space-y-2">
            <label
              htmlFor="decision-reason"
              className="block text-sm font-medium"
            >
              {requiresReason ? "Razón (obligatoria)" : "Nota (opcional)"}
            </label>
            <Textarea
              id="decision-reason"
              rows={3}
              value={decision.reason}
              onChange={(e) =>
                setDecision({ ...decision, reason: e.target.value })
              }
              placeholder={
                requiresReason
                  ? "Describe en una frase clara qué necesita corregir el proveedor."
                  : "Nota opcional para el registro."
              }
            />
          </div>
        ) : null}

        {decisionError ? (
          <div
            role="alert"
            className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900"
          >
            <div className="flex items-start gap-2">
              <AlertTriangle
                className="mt-0.5 h-4 w-4 shrink-0 text-amber-600"
                aria-hidden
              />
              <p>{decisionError}</p>
            </div>
          </div>
        ) : null}

        <Button
          type="button"
          disabled={!decision || submitting}
          onClick={onSubmit}
          className="w-full active:scale-[0.98]"
          data-testid="submit-decision"
        >
          {submitting ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          ) : (
            <Gavel className="h-4 w-4" aria-hidden />
          )}
          {submitting ? "Registrando decisión…" : "Registrar decisión"}
        </Button>
      </CardContent>
    </Card>
  );
}

function actionActiveClass(variant: "approve" | "reject" | "clarify" | "exception"): string {
  switch (variant) {
    case "approve":
      return "border-emerald-300 bg-emerald-50 text-emerald-900";
    case "reject":
      return "border-red-300 bg-red-50 text-red-900";
    case "clarify":
      return "border-amber-300 bg-amber-50 text-amber-900";
    case "exception":
      return "border-primary/40 bg-primary/5 text-primary";
  }
}

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
    <div className="rounded-md border border-border/70 bg-white p-3">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p className="mt-1 break-words text-sm font-medium">{value}</p>
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
