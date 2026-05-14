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
  isProtectedField,
  submitCorrection,
} from "@/lib/mock/corrections";
import {
  EDITABLE_FIELD_LABEL,
  PROTECTED_FIELD_LABEL,
  type ProfileCorrectionRequest,
  type ProtectedWorkspaceFields,
} from "@/lib/workspace/types";

type FieldKey =
  | keyof ProtectedWorkspaceFields
  | "company_display_name"
  | "other";

interface FieldOption {
  value: FieldKey;
  label: string;
}

interface Props {
  workspace_id: string;
  /** Defaults for the field selector + current value, when context is known. */
  initialField?: FieldKey;
  initialCurrentValue?: string;
}

// Fields the user might want to dispute. Profile-only edits use the
// inline editor, not this form — so we don't list first_name/last_name
// here. The form is for tenant-locked changes + the catch-all "other".
const FIELD_OPTIONS: FieldOption[] = [
  { value: "rfc", label: PROTECTED_FIELD_LABEL.rfc },
  { value: "company_legal_name", label: PROTECTED_FIELD_LABEL.company_legal_name },
  { value: "company_display_name", label: "Nombre comercial / display" },
  { value: "role", label: PROTECTED_FIELD_LABEL.role },
  { value: "email", label: PROTECTED_FIELD_LABEL.email },
  { value: "client_id", label: PROTECTED_FIELD_LABEL.client_id },
  { value: "provider_id", label: PROTECTED_FIELD_LABEL.provider_id },
  { value: "other", label: "Otro" },
];

/**
 * Friendly correction-request form.
 *
 * Lives next to the workspace identity card; submits a
 * ProfileCorrectionRequest into the mock store. The mock's
 * isProtectedField() decides whether the change requires admin review;
 * the UI reflects that decision so the user knows their request will
 * be moderated.
 *
 * Spec: docs/CHECKWISE_1_6.md §11.
 */
export function CorrectionRequestForm({
  workspace_id,
  initialField = "rfc",
  initialCurrentValue = "",
}: Props) {
  const [field, setField] = useState<FieldKey>(initialField);
  const [currentValue, setCurrentValue] = useState(initialCurrentValue);
  const [proposedValue, setProposedValue] = useState("");
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<ProfileCorrectionRequest | null>(null);

  const requiresReview = field === "other" || field === "company_display_name" || isProtectedField(field);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    const result = await submitCorrection({
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
      } else {
        setError("No pudimos guardar la solicitud. Intenta de nuevo.");
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
            La revisaremos antes de actualizar los datos sensibles. Te avisaremos
            por correo cuando se aplique o si necesitamos más información.
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
      <Field label="¿Qué campo deseas corregir?" htmlFor="cor-field">
        <Select
          id="cor-field"
          value={field}
          onChange={(e) => setField(e.target.value as FieldKey)}
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
          helper="Lo correcto, según la documentación que tienes."
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
        required={requiresReview}
        helper={
          requiresReview
            ? "Mínimo 4 caracteres. Los cambios sensibles requieren contexto."
            : "Opcional para cambios no sensibles."
        }
      >
        <Input
          id="cor-reason"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Cambio de razón social tras reestructura, etc."
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
          placeholder="Adjuntamos por correo el acta constitutiva actualizada…"
        />
      </Field>

      {requiresReview && (
        <Alert variant="info">
          <AlertTitle className="flex items-center gap-2">
            <ShieldWarning className="h-4 w-4" weight="bold" aria-hidden="true" />
            Este cambio será revisado por seguridad
          </AlertTitle>
          <AlertDescription>
            Algunos campos están protegidos para evitar reasignaciones cruzadas
            entre empresas. Tu solicitud queda registrada y un revisor la valida
            antes de aplicarse.
          </AlertDescription>
        </Alert>
      )}

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
