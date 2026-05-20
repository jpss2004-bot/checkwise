"use client";

import { useState, type FormEvent } from "react";
import { ArrowRight, CheckCircle, ShieldWarning } from "@phosphor-icons/react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  TIER_B_FIELDS,
  TIER_B_FIELD_LABEL_ES,
  submitCorrectionRequest,
  type CorrectionRequestRecord,
  type TierBField,
} from "@/lib/api/corrections";
import { EDITABLE_FIELD_LABEL } from "@/lib/workspace/types";

interface Props {
  workspace_id: string;
  /** Defaults for the field selector + current value, when context is known. */
  initialField?: TierBField;
  initialCurrentValue?: string;
}

interface FieldOption {
  value: TierBField;
  label: string;
}

// Stage 2.7-a: the form's field list is the locked Tier B whitelist.
// RFC, razón social, contract reference, role and other sensitive
// attributes no longer appear here — those must route through support.
const FIELD_OPTIONS: FieldOption[] = TIER_B_FIELDS.map((value) => ({
  value,
  label: TIER_B_FIELD_LABEL_ES[value],
}));

/**
 * Provider workspace correction-request form.
 *
 * Mounted next to the workspace identity card on `/portal/entra-a-tu-espacio`.
 * Submits a request that lands as an ``audit_log`` row on the backend
 * and (best-effort) a Slack notification to the support channel.
 * Every request goes through admin review — the form never applies
 * the change directly.
 *
 * Spec: PROVIDER_EXPERIENCE_IMPROVEMENT_PLAN.md §18 (Tier B);
 *       HANDOFF_2026-05-20.md §2.7-a.
 */
export function CorrectionRequestForm({
  workspace_id,
  initialField = "contact_email",
  initialCurrentValue = "",
}: Props) {
  const [field, setField] = useState<TierBField>(initialField);
  const [currentValue, setCurrentValue] = useState(initialCurrentValue);
  const [proposedValue, setProposedValue] = useState("");
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<CorrectionRequestRecord | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    const result = await submitCorrectionRequest({
      workspace_id,
      field,
      current_value: currentValue,
      proposed_value: proposedValue,
      reason,
      message,
    });
    setSubmitting(false);
    if (!result.ok) {
      if (result.error === "no_change") {
        setError("Captura un valor distinto al actual.");
      } else if (result.error === "missing_reason") {
        setError("Captura una razón breve. Los cambios sensibles requieren contexto.");
      } else if (result.error === "rate_limited") {
        setError(
          result.detail ??
            "Has enviado varias solicitudes recientemente. Inténtalo de nuevo en una hora.",
        );
      } else if (result.error === "unauthorized") {
        setError(
          "Tu sesión expiró o no tiene permisos para enviar esta solicitud. Vuelve a iniciar sesión.",
        );
      } else if (result.error === "unknown_field") {
        setError(
          result.detail ??
            "Este dato no se puede corregir desde el portal. Escríbenos a soporte@checkwise.mx.",
        );
      } else {
        setError("No pudimos enviar tu solicitud. Intenta de nuevo en unos segundos.");
      }
      return;
    }
    setDone(result.request ?? null);
  }

  if (done) {
    return (
      <div
        className="flex flex-col items-center gap-3 rounded-xl border border-[color:var(--status-success-border)] bg-[color:var(--status-success-bg)] px-6 py-7 text-center"
        role="status"
      >
        <span
          className="cw-success-ring flex h-11 w-11 items-center justify-center rounded-full bg-[color:var(--status-success-text)] text-white"
          aria-hidden="true"
        >
          <CheckCircle className="h-6 w-6" weight="fill" />
        </span>
        <div>
          <h3 className="text-base font-semibold text-[color:var(--text-primary)]">
            Recibimos tu solicitud
          </h3>
          <p className="mt-1 max-w-prose text-[13px] text-[color:var(--text-secondary)]">
            La revisaremos antes de actualizar los datos de contacto. Te
            avisaremos por correo cuando se aplique o si necesitamos más
            información.
          </p>
          <p className="mt-3 font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
            Folio: {done.id}
          </p>
        </div>
      </div>
    );
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-col gap-4"
      noValidate
      aria-label="Solicitar corrección de información"
    >
      <Field label="¿Qué dato deseas corregir?" htmlFor="cor-field">
        <Select
          id="cor-field"
          value={field}
          onChange={(e) => setField(e.target.value as TierBField)}
        >
          {FIELD_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </Select>
      </Field>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label="Valor actual"
          htmlFor="cor-current"
          helper="Lo que ves hoy en tu perfil."
        >
          <Input
            id="cor-current"
            value={currentValue}
            onChange={(e) => setCurrentValue(e.target.value)}
            placeholder="—"
          />
        </Field>
        <Field
          label="Valor propuesto"
          htmlFor="cor-proposed"
          required
          helper="Lo correcto, según tu documentación."
        >
          <Input
            id="cor-proposed"
            value={proposedValue}
            onChange={(e) => setProposedValue(e.target.value)}
            placeholder="—"
          />
        </Field>
      </div>

      <Field
        label="Razón breve"
        htmlFor="cor-reason"
        required
        helper="Mínimo 4 caracteres. Los cambios de contacto requieren contexto."
      >
        <Input
          id="cor-reason"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Cambio de correo del responsable, número anterior obsoleto, etc."
        />
      </Field>

      <Field
        label="Mensaje al equipo CheckWise"
        htmlFor="cor-message"
        helper="Opcional. Adjunta contexto extra que ayude a la revisión."
      >
        <Textarea
          id="cor-message"
          rows={3}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Adjuntamos por correo el comprobante del nuevo dato…"
        />
      </Field>

      <Alert variant="info">
        <AlertTitle className="flex items-center gap-2">
          <ShieldWarning className="h-4 w-4" weight="bold" aria-hidden="true" />
          Tu solicitud entra a revisión
        </AlertTitle>
        <AlertDescription>
          Los datos de contacto se aplican después de que un revisor de CheckWise
          confirme tu solicitud. Si necesitas modificar RFC, razón social u otros
          datos sensibles, escríbenos a{" "}
          <a
            className="font-medium underline"
            href="mailto:soporte@checkwise.mx"
          >
            soporte@checkwise.mx
          </a>
          .
        </AlertDescription>
      </Alert>

      {error && (
        <Alert variant="error">
          <AlertTitle>No pudimos enviar tu solicitud</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <Button type="submit" loading={submitting} className="self-start">
        <span>Enviar solicitud</span>
        {!submitting && <ArrowRight className="h-4 w-4" weight="bold" aria-hidden="true" />}
      </Button>
    </form>
  );
}

// Keep editable-field label table in this module's barrel so callers
// importing the form don't need to wire it separately.
export { EDITABLE_FIELD_LABEL };
