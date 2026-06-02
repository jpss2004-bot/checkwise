"use client";

import * as React from "react";
import {
  CheckCircle,
  XCircle,
  Question,
  Gavel,
  Warning,
  CircleNotch,
} from "@phosphor-icons/react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

/**
 * ReviewDecisionPanel — the operator's primary decision surface.
 *
 * Replaces the inline "DecisionCard" pattern with a token-styled
 * composition that:
 *   - exposes 4 chunky action chips (approve / reject / clarify /
 *     mark exception) — each carries the doc-state token of the
 *     resulting status so the reviewer sees what the document will
 *     look like *after* their click,
 *   - opens a Dialog confirmation for the three destructive paths
 *     (anything that returns the document to the provider) so a
 *     fast double-click can't push a wrong reason through,
 *   - drives the reason textarea through the Field primitive so
 *     aria-invalid + helper/error wiring is consistent with every
 *     other form in the product.
 *
 * Stays presentational — submission lives with the caller so the page
 * can own the network call, retries, and post-submit redirects.
 */

export type ReviewerAction =
  | "approve"
  | "reject"
  | "request_clarification"
  | "mark_exception";

interface ReviewDecisionPanelProps {
  /** Disable everything (e.g. submission already terminal). */
  disabled?: boolean;
  /** Reason behind the disabled state — shown as an Alert. */
  disabledReason?: string;
  /**
   * Async handler — receives action + trimmed reason + trimmed
   * observations. Phase 9 / Slice 9A added the third argument:
   * ``observations`` is an optional reviewer-authored note that
   * lands in the notification body distinct from the formal reason.
   * May throw.
   */
  onSubmit: (
    action: ReviewerAction,
    reason: string | null,
    observations: string | null,
  ) => Promise<void>;
  /** Optional override of the panel surface className. */
  className?: string;
  /**
   * Passive AI suggestion line shown above the action chips. ONLY
   * surfaced when the automatic lectura flagged a concern
   * (mismatch_reason set or low confidence). Never sets the action
   * for the reviewer — it's an informational nudge, not a binding
   * suggestion. Pass `null` (or omit) to hide the line entirely
   * — including when the AI thinks everything is fine — so reviewers
   * aren't anchored on AI for every routine approval.
   */
  aiHint?: string | null;
}

// Phase 9 / Slice 9A — common rejection reasons. Click a chip to
// append (or seed) the reason textarea so the reviewer can refine
// the wording before submitting. Used on the ``reject`` and
// ``request_clarification`` actions only. Approve / mark_exception
// have no required reason and these chips would be wrong copy on
// those paths. Wider operational set per the locked product
// decision.
const COMMON_REJECTION_REASONS: ReadonlyArray<string> = [
  "PDF cortado o ilegible",
  "RFC no coincide con el proveedor",
  "Periodo del documento es incorrecto",
  "Falta firma autorizada",
  "Versión obsoleta del documento",
  "Documento incompleto",
  "Documento duplicado en otro periodo",
  "Institución emisora incorrecta",
  "Acuse o sello digital faltante",
];

const ACTIONS: {
  action: ReviewerAction;
  label: string;
  icon: typeof Gavel;
  /** Token group used for the chip's selected-state palette. */
  tone: "approve" | "reject" | "clarify" | "exception";
  /** Spanish copy used in the Dialog confirmation. */
  confirmTitle: string;
  confirmBody: string;
  confirmCta: string;
}[] = [
  {
    action: "approve",
    label: "Aprobar",
    icon: CheckCircle,
    tone: "approve",
    confirmTitle: "Aprobar documento",
    confirmBody:
      "Marcarás este documento como aprobado. Quedará disponible al proveedor y a su cliente como evidencia válida.",
    confirmCta: "Aprobar",
  },
  {
    action: "reject",
    label: "Rechazar",
    icon: XCircle,
    tone: "reject",
    confirmTitle: "Rechazar documento",
    confirmBody:
      "El documento se devolverá al proveedor con tu razón. Tendrá que cargar uno nuevo para reabrir el caso.",
    confirmCta: "Rechazar",
  },
  {
    action: "request_clarification",
    label: "Pedir aclaración",
    icon: Question,
    tone: "clarify",
    confirmTitle: "Pedir aclaración",
    confirmBody:
      "El documento quedará pendiente de aclaración. El proveedor recibirá tu razón y podrá responder o re-cargar.",
    confirmCta: "Pedir aclaración",
  },
  {
    action: "mark_exception",
    label: "Excepción legal",
    icon: Gavel,
    tone: "exception",
    confirmTitle: "Marcar excepción legal",
    confirmBody:
      "Aprobarás bajo excepción documentada. La razón quedará en el audit log para soporte legal.",
    confirmCta: "Marcar excepción",
  },
];

const TONE_ACTIVE: Record<(typeof ACTIONS)[number]["tone"], string> = {
  approve:
    "border-[color:var(--doc-approved-border)] bg-[color:var(--doc-approved-bg)] text-[color:var(--doc-approved-text)]",
  reject:
    "border-[color:var(--doc-rejected-border)] bg-[color:var(--doc-rejected-bg)] text-[color:var(--doc-rejected-text)]",
  clarify:
    "border-[color:var(--doc-needs-review-border)] bg-[color:var(--doc-needs-review-bg)] text-[color:var(--doc-needs-review-text)]",
  exception:
    "border-[color:var(--status-info-border)] bg-[color:var(--status-info-bg)] text-[color:var(--status-info-text)]",
};

export function ReviewDecisionPanel({
  disabled = false,
  disabledReason,
  onSubmit,
  className,
  aiHint,
}: ReviewDecisionPanelProps) {
  const [action, setAction] = React.useState<ReviewerAction | null>(null);
  const [reason, setReason] = React.useState("");
  // Phase 9 / Slice 9A — optional reviewer observation. Distinct
  // from the formal reason; lands in the notification body as a
  // second sentence so the provider sees both pieces of context.
  const [observations, setObservations] = React.useState("");
  const [reasonError, setReasonError] = React.useState<string | null>(null);
  const [networkError, setNetworkError] = React.useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = React.useState(false);
  const [submitting, setSubmitting] = React.useState(false);

  const requiresReason = action !== null && action !== "approve";
  // Common-reason chips only make sense when the action returns the
  // document to the provider. Approve / mark_exception use the
  // optional "Nota interna" path, where canned phrases don't fit.
  const showCommonReasons =
    action === "reject" || action === "request_clarification";

  function appendCommonReason(phrase: string) {
    setReason((current) => {
      const trimmed = current.trim();
      if (!trimmed) return phrase;
      // Avoid duplicating a chip the reviewer already clicked.
      if (trimmed.includes(phrase)) return current;
      return `${trimmed} ${phrase}`;
    });
    setReasonError(null);
  }

  if (disabled) {
    return (
      <section
        className={cn(
          "rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-5 shadow-xs",
          className,
        )}
        aria-label="Decisión bloqueada"
      >
        <h2 className="text-[15px] font-semibold text-[color:var(--text-primary)]">
          Documento resuelto
        </h2>
        <p className="mt-2 text-sm text-[color:var(--text-secondary)]">
          {disabledReason ??
            "Este documento ya tiene una decisión registrada. Solo una nueva carga del proveedor puede reabrirlo."}
        </p>
      </section>
    );
  }

  function handleChip(next: ReviewerAction) {
    setAction(next);
    setReasonError(null);
    setNetworkError(null);
  }

  function attemptSubmit() {
    if (!action) return;
    const trimmed = reason.trim();
    if (requiresReason && !trimmed) {
      setReasonError("Esta decisión necesita una razón.");
      return;
    }
    setReasonError(null);
    setConfirmOpen(true);
  }

  async function confirmSubmit() {
    if (!action) return;
    setSubmitting(true);
    setNetworkError(null);
    try {
      const trimmedObservations = observations.trim();
      await onSubmit(
        action,
        requiresReason ? reason.trim() : null,
        // Observations are only meaningful when the document is being
        // returned to the provider — on approve we keep the existing
        // "Nota interna" semantics (reason field, not surfaced to
        // provider) and don't send observations.
        requiresReason && trimmedObservations ? trimmedObservations : null,
      );
      setConfirmOpen(false);
      setAction(null);
      setReason("");
      setObservations("");
    } catch (err) {
      const message =
        err instanceof Error
          ? err.message
          : "No pudimos registrar la decisión. Intenta de nuevo.";
      setNetworkError(message);
    } finally {
      setSubmitting(false);
    }
  }

  const activeAction = action ? ACTIONS.find((a) => a.action === action) ?? null : null;

  return (
    <section
      className={cn(
        "rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-xs",
        className,
      )}
      aria-label="Panel de decisión del revisor"
    >
      <header className="border-b border-[color:var(--border-subtle)] px-5 py-3">
        <div className="flex items-center gap-2">
          <Gavel
            className="h-4 w-4 text-[color:var(--text-brand)]"
            weight="duotone"
            aria-hidden="true"
          />
          <h2 className="text-[13px] font-semibold uppercase tracking-wide text-[color:var(--text-primary)]">
            Tu decisión
          </h2>
        </div>
        <p className="mt-1 text-xs text-[color:var(--text-secondary)]">
          Elige una acción. Las que devuelven el documento al proveedor requieren
          una razón. Confirmamos antes de registrar.
        </p>
      </header>

      <div className="space-y-4 p-5">
        {aiHint ? (
          <div
            role="note"
            aria-label="Sugerencia automática"
            className="flex items-start gap-2 rounded-md border border-[color:var(--status-warning-border,transparent)] bg-[color:var(--status-warning-bg,transparent)] px-3 py-2 text-xs"
          >
            <Warning
              className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[color:var(--status-warning-text,#d97706)]"
              weight="fill"
              aria-hidden="true"
            />
            <p className="text-[color:var(--text-primary)]">
              <span className="font-semibold">Sugerencia automática: </span>
              <span className="italic">{aiHint}</span>
            </p>
          </div>
        ) : null}
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {ACTIONS.map((opt) => {
            const Icon = opt.icon;
            const isActive = action === opt.action;
            return (
              <button
                key={opt.action}
                type="button"
                onClick={() => handleChip(opt.action)}
                className={cn(
                  "group flex items-center gap-2 rounded-md border px-3 py-2.5 text-sm font-medium transition-colors duration-fast",
                  "focus:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]/40 focus-visible:ring-offset-2 focus-visible:ring-offset-[color:var(--surface-raised)]",
                  isActive
                    ? TONE_ACTIVE[opt.tone]
                    : "border-[color:var(--border-default)] bg-[color:var(--surface-raised)] text-[color:var(--text-primary)] hover:bg-[color:var(--surface-hover)]",
                )}
                aria-pressed={isActive}
                data-action={opt.action}
              >
                <Icon className="h-4 w-4" weight="bold" aria-hidden="true" />
                {opt.label}
              </button>
            );
          })}
        </div>

        {action ? (
          <Field
            label={requiresReason ? "Razón (obligatoria)" : "Nota (opcional)"}
            htmlFor="reviewer-reason"
            required={requiresReason}
            helper={
              requiresReason
                ? "Una frase clara que el proveedor entienda."
                : "Queda en el registro aunque el proveedor no la vea."
            }
            error={reasonError ?? undefined}
          >
            {showCommonReasons ? (
              <div
                className="mb-2 flex flex-wrap gap-1.5"
                role="group"
                aria-label="Razones comunes"
              >
                {COMMON_REJECTION_REASONS.map((phrase) => (
                  <button
                    key={phrase}
                    type="button"
                    onClick={() => appendCommonReason(phrase)}
                    className="rounded-full border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-2.5 py-1 text-[11px] font-medium text-[color:var(--text-secondary)] transition-colors hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--text-primary)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]/40"
                  >
                    {phrase}
                  </button>
                ))}
              </div>
            ) : null}
            <Textarea
              id="reviewer-reason"
              rows={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder={
                requiresReason
                  ? "Ejemplo: la opinión IMSS adjuntada corresponde al periodo anterior."
                  : "Nota interna opcional."
              }
            />
          </Field>
        ) : null}

        {action && requiresReason ? (
          <Field
            label="Observaciones para el proveedor (opcional)"
            htmlFor="reviewer-observations"
            helper="Contexto adicional, recomendaciones o pasos sugeridos. Aparece en la notificación del proveedor en una línea separada de la razón."
          >
            <Textarea
              id="reviewer-observations"
              rows={2}
              value={observations}
              onChange={(e) => setObservations(e.target.value)}
              placeholder="Ejemplo: regenera el comprobante desde el portal del SAT con la versión actualizada."
            />
          </Field>
        ) : null}

        {networkError ? (
          <Alert variant="error">
            <AlertDescription>{networkError}</AlertDescription>
          </Alert>
        ) : null}

        <Button
          type="button"
          disabled={!action}
          onClick={attemptSubmit}
          className="w-full"
          data-testid="open-decision-confirm"
        >
          <Gavel className="h-4 w-4" weight="bold" aria-hidden="true" />
          {action ? "Revisar y confirmar" : "Selecciona una acción"}
        </Button>
      </div>

      {activeAction ? (
        <Dialog
          open={confirmOpen}
          onOpenChange={(next) => {
            if (!submitting) setConfirmOpen(next);
          }}
        >
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{activeAction.confirmTitle}</DialogTitle>
              <DialogDescription>{activeAction.confirmBody}</DialogDescription>
            </DialogHeader>
            {requiresReason && reason.trim() ? (
              <div className="rounded-sm border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] p-3 text-sm text-[color:var(--text-secondary)]">
                <p className="mb-1 font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                  Razón que verá el proveedor
                </p>
                <p className="leading-[1.5]">{reason.trim()}</p>
              </div>
            ) : null}
            {requiresReason && observations.trim() ? (
              <div className="rounded-sm border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] p-3 text-sm text-[color:var(--text-secondary)]">
                <p className="mb-1 font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                  Observación adicional
                </p>
                <p className="leading-[1.5]">{observations.trim()}</p>
              </div>
            ) : null}
            {networkError ? (
              <Alert variant="error">
                <AlertDescription className="flex items-center gap-2">
                  <Warning className="h-4 w-4" weight="bold" aria-hidden="true" />
                  {networkError}
                </AlertDescription>
              </Alert>
            ) : null}
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setConfirmOpen(false)}
                disabled={submitting}
              >
                Cancelar
              </Button>
              <Button
                type="button"
                onClick={confirmSubmit}
                loading={submitting}
                variant={
                  activeAction.tone === "reject" ? "destructive" : "default"
                }
              >
                {!submitting ? (
                  <CheckCircle className="h-4 w-4" weight="bold" aria-hidden="true" />
                ) : (
                  <CircleNotch className="h-4 w-4 animate-spin" aria-hidden="true" />
                )}
                {submitting ? "Registrando…" : activeAction.confirmCta}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      ) : null}
    </section>
  );
}
