"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Warning,
  ArrowRight,
  Calendar,
  CheckCircle,
  CaretLeft,
  CaretRight,
  Eye,
  FileText,
  CircleNotch,
  Lock,
  PencilSimple,
  ShieldCheck,
  CloudArrowUp,
  UserCheck,
} from "@phosphor-icons/react";

import { institutions, loadTypes, requirementGuides, requirements } from "@/lib/api/catalogs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ValidationSignal, ValidationSummary } from "@/components/checkwise/validation-summary";
import { checkDuplicateBySha256, type DuplicateCheck } from "@/lib/api/portal";
import { DocumentStatus } from "@/lib/constants/statuses";
import { readPortalSession } from "@/lib/session/portal";

type SubmissionResponse = {
  submission_id: string;
  document_id: string;
  status: string;
  sha256: string;
  storage_key: string;
  validations: ValidationSignal[];
  validation_events?: Array<{
    event_type: string;
    result: string;
    severity: string;
    message?: string | null;
    confidence?: number | null;
  }>;
  inspection?: {
    is_pdf: boolean;
    is_corrupt: boolean;
    is_encrypted: boolean;
    page_count: number | null;
    text_char_count: number;
    has_text: boolean;
    is_probably_scanned: boolean;
  } | null;
  document_signals?: {
    detected_institution?: string | null;
    detected_document_type?: string | null;
    detected_rfcs: string[];
    detected_dates: string[];
    period_mentions: string[];
    requirement_match_confidence?: number | null;
    mismatch_reason?: string | null;
    anomaly_codes: string[];
  } | null;
  message: string;
};

type IntakeForm = {
  client_name: string;
  vendor_name: string;
  vendor_rfc: string;
  contract_reference: string;
  period_code: string;
  load_type: string;
  institution_code: string;
  requirement_name: string;
  comments: string;
  // Canonical IDs introduced by the Reconciliation Patch. Both empty by
  // default; populated by deep-links from the calendar / onboarding and sent
  // to the backend so /submissions can bind to the catalog instead of
  // creating phantom requirements / periods.
  requirement_code: string;
  period_key: string;
};

const steps = ["Contexto", "Requisito", "Upload", "Prevalidación", "Confirmación"];
const maxUploadSizeBytes = 15 * 1024 * 1024;

const initialForm: IntakeForm = {
  client_name: "",
  vendor_name: "",
  vendor_rfc: "",
  contract_reference: "",
  period_code: "2026-05",
  load_type: "mensual",
  institution_code: "sat",
  requirement_name: requirements[5] ?? requirements[0],
  comments: "",
  requirement_code: "",
  period_key: "",
};

export type IntakeWizardPrefill = Partial<IntakeForm>;

export type IntakeLockedField = keyof IntakeForm;

const LOCKED_FIELD_LABELS: Record<IntakeLockedField, string> = {
  client_name: "Cliente",
  vendor_name: "Proveedor",
  vendor_rfc: "RFC proveedor",
  contract_reference: "Contrato",
  period_code: "Periodo",
  load_type: "Tipo de carga",
  institution_code: "Institución",
  requirement_name: "Requisito",
  comments: "Comentarios",
  // Canonical IDs — carried in state, never rendered as a locked field.
  requirement_code: "Código canónico",
  period_key: "Periodo canónico",
};

const LOCKED_FIELD_SOURCE: Partial<Record<IntakeLockedField, string>> = {
  client_name: "Viene de tu sesión",
  vendor_name: "Viene de tu sesión",
  vendor_rfc: "Viene de tu sesión",
  contract_reference: "Viene de tu sesión",
  period_code: "Viene del calendario",
  load_type: "Viene del expediente o calendario",
  institution_code: "Viene del expediente o calendario",
  requirement_name: "Viene del expediente o calendario",
};

export function IntakeWizard({
  prefill,
  lockedFields,
}: {
  prefill?: IntakeWizardPrefill;
  lockedFields?: IntakeLockedField[];
} = {}) {
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const demoModeEnabled = process.env.NEXT_PUBLIC_DEMO_MODE === "true";
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<IntakeForm>(() => ({ ...initialForm, ...(prefill ?? {}) }));
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [result, setResult] = useState<SubmissionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [unlockedOverride, setUnlockedOverride] = useState(false);
  const [filePreviewUrl, setFilePreviewUrl] = useState<string | null>(null);
  const [duplicateCheck, setDuplicateCheck] = useState<DuplicateCheck | null>(null);
  const [duplicateChecking, setDuplicateChecking] = useState(false);

  const lockedSet = useMemo(() => {
    if (unlockedOverride) return new Set<IntakeLockedField>();
    const effective = (lockedFields ?? []).filter((field) => {
      const value = form[field];
      return typeof value === "string" && value.trim().length > 0;
    });
    return new Set<IntakeLockedField>(effective);
  }, [lockedFields, form, unlockedOverride]);

  const selectedRequirement =
    requirementGuides.find((requirement) => requirement.name === form.requirement_name) ??
    requirementGuides[0];

  function updateField(field: keyof IntakeForm, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
    setError(null);
  }

  function selectFile(nextFile: File | null) {
    setFileError(null);
    setDuplicateCheck(null);
    // Revoke the previous preview URL before replacing it.
    if (filePreviewUrl) {
      URL.revokeObjectURL(filePreviewUrl);
      setFilePreviewUrl(null);
    }
    if (!nextFile) {
      setFile(null);
      return;
    }
    if (!nextFile.name.toLowerCase().endsWith(".pdf")) {
      setFile(null);
      setFileError("Solo se aceptan archivos PDF en esta fase.");
      return;
    }
    if (nextFile.size === 0) {
      setFile(null);
      setFileError("El archivo está vacío.");
      return;
    }
    if (nextFile.size > maxUploadSizeBytes) {
      setFile(null);
      setFileError("El PDF excede el máximo de 15 MB para esta demo.");
      return;
    }
    setFile(nextFile);
    setError(null);
    // Generate an in-memory preview URL for the iframe.
    try {
      const url = URL.createObjectURL(nextFile);
      setFilePreviewUrl(url);
    } catch {
      // Older browsers — preview unavailable but upload still works.
      setFilePreviewUrl(null);
    }
    // Fire-and-forget duplicate pre-check against the workspace.
    void runDuplicatePreCheck(nextFile);
  }

  async function runDuplicatePreCheck(target: File) {
    const session = readPortalSession();
    if (!session) return;
    setDuplicateChecking(true);
    try {
      const hash = await sha256OfFile(target);
      const result = await checkDuplicateBySha256(session, hash);
      setDuplicateCheck(result);
    } catch {
      // Pre-check is advisory; failures must not block the provider.
      setDuplicateCheck(null);
    } finally {
      setDuplicateChecking(false);
    }
  }

  // Clean up the preview blob URL on unmount or wizard reset.
  useEffect(() => {
    return () => {
      if (filePreviewUrl) URL.revokeObjectURL(filePreviewUrl);
    };
  }, [filePreviewUrl]);

  async function useDemoFile() {
    setFileError(null);
    setError(null);
    try {
      const response = await fetch("/demo/checkwise_demo_opinion_sat.pdf");
      if (!response.ok) {
        throw new Error("No encontré el PDF demo en el frontend.");
      }
      const blob = await response.blob();
      selectFile(
        new File([blob], "checkwise_demo_opinion_sat.pdf", {
          type: "application/pdf",
        }),
      );
    } catch (demoFileError) {
      setFile(null);
      setFileError(
        demoFileError instanceof Error
          ? demoFileError.message
          : "No fue posible cargar el PDF demo.",
      );
    }
  }

  function validateStep(targetStep: number): string | null {
    if (targetStep === 0) {
      if (form.client_name.trim().length < 2) {
        return "Captura el cliente para mantener trazabilidad de la evidencia.";
      }
      if (form.vendor_name.trim().length < 2) {
        return "Captura el proveedor que entrega la evidencia.";
      }
      const vendorRfc = form.vendor_rfc.trim();
      if (vendorRfc.length < 12 || vendorRfc.length > 13) {
        return "Captura un RFC de proveedor de 12 o 13 caracteres.";
      }
      if (form.period_code.trim().length < 4) {
        return "Captura el periodo que debe cubrir el documento.";
      }
    }

    if (targetStep === 2 && !file) {
      return "Selecciona el PDF de evidencia antes de confirmar la carga.";
    }

    return null;
  }

  function handleContinue() {
    const validationError = validateStep(step);
    if (validationError) {
      setError(validationError);
      return;
    }
    setError(null);
    setStep((current) => current + 1);
  }

  async function handleSubmit(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();

    for (const targetStep of [0, 2]) {
      const validationError = validateStep(targetStep);
      if (validationError) {
        setError(validationError);
        setStep(targetStep);
        return;
      }
    }

    setIsSubmitting(true);
    setResult(null);
    setError(null);

    const body = new FormData();
    const normalizedForm: IntakeForm = {
      ...form,
      client_name: form.client_name.trim(),
      vendor_name: form.vendor_name.trim(),
      vendor_rfc: form.vendor_rfc.trim().toUpperCase(),
      contract_reference: form.contract_reference.trim(),
      period_code: form.period_code.trim(),
      comments: form.comments.trim(),
    };
    Object.entries(normalizedForm).forEach(([key, value]) => body.set(key, value));
    body.set("initial_status", DocumentStatus.PENDIENTE_REVISION);
    body.set("file", file as File);

    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/submissions`, {
        method: "POST",
        body,
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(formatApiError(payload));
      }

      setResult((await response.json()) as SubmissionResponse);
      setStep(4);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Error inesperado.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <CardTitle>Intake documental nativo</CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              Cada carga queda ligada a cliente, proveedor, periodo, institución, requisito,
              archivo, validación y revisión humana.
            </p>
          </div>
          <Badge variant="outline">PDF-only</Badge>
        </div>
        <div className="mt-5 grid gap-2 sm:grid-cols-5">
          {steps.map((label, index) => (
            <div
              key={label}
              className={`rounded-md border px-3 py-2 text-xs ${
                index === step
                  ? "border-primary bg-primary text-primary-foreground"
                  : index < step
                    ? "border-primary/30 bg-emerald-50 text-primary"
                    : "border-border bg-white text-muted-foreground"
              }`}
            >
              <span className="font-semibold">{index + 1}.</span> {label}
            </div>
          ))}
        </div>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} data-testid="native-intake-form">
          {step === 0 ? (
            <ContextStep
              form={form}
              updateField={updateField}
              lockedSet={lockedSet}
              canUnlock={(lockedFields?.length ?? 0) > 0}
              unlocked={unlockedOverride}
              onToggleUnlock={() => setUnlockedOverride((current) => !current)}
            />
          ) : null}
          {step === 1 ? <RequirementStep requirement={selectedRequirement} /> : null}
          {step === 2 ? (
            <UploadStep
              file={file}
              fileError={fileError}
              onFileSelected={selectFile}
              onUseDemoFile={demoModeEnabled ? useDemoFile : undefined}
              comments={form.comments}
              onCommentsChange={(value) => updateField("comments", value)}
              filePreviewUrl={filePreviewUrl}
              duplicateCheck={duplicateCheck}
              duplicateChecking={duplicateChecking}
              requirement={selectedRequirement}
            />
          ) : null}
          {step === 3 ? (
            <PrevalidationStep
              form={form}
              file={file}
              requirement={selectedRequirement}
              duplicateCheck={duplicateCheck}
            />
          ) : null}
          {step === 4 ? <ConfirmationStep result={result} error={error} /> : null}

          {error && step !== 4 ? (
            <div
              role="alert"
              className="mt-5 rounded-md border border-amber-300 bg-amber-50 p-4"
            >
              <div className="flex gap-3">
                <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-amber-500 text-white">
                  <Warning className="h-4 w-4" aria-hidden="true" />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-amber-900">
                    {step === 3
                      ? "No pudimos enviar tu documento"
                      : "Revisa este paso antes de continuar"}
                  </p>
                  <p className="mt-1 text-sm text-amber-900/80">{error}</p>
                  {step === 3 ? (
                    <p className="mt-1 text-xs text-amber-900/70">
                      Tu archivo y los datos siguen aquí. Puedes volver a intentarlo.
                    </p>
                  ) : null}
                </div>
              </div>
            </div>
          ) : null}

          <div className="mt-6 flex flex-col gap-3 border-t border-border pt-5 sm:flex-row sm:items-center sm:justify-between">
            <Button
              type="button"
              variant="outline"
              disabled={step === 0 || isSubmitting}
              onClick={() => setStep((current) => Math.max(0, current - 1))}
              className="active:scale-[0.98]"
            >
              <CaretLeft className="h-4 w-4" aria-hidden="true" />
              Atrás
            </Button>

            {step < 3 ? (
              <Button
                type="button"
                data-testid="continue-step"
                onClick={handleContinue}
                className="active:scale-[0.98]"
              >
                Continuar
                <CaretRight className="h-4 w-4" aria-hidden="true" />
              </Button>
            ) : step === 3 ? (
              <Button
                type="submit"
                data-testid="submit-submission"
                disabled={isSubmitting}
                className="active:scale-[0.98]"
              >
                {isSubmitting ? (
                  <CircleNotch className="h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  <CloudArrowUp className="h-4 w-4" aria-hidden="true" />
                )}
                {isSubmitting ? "Enviando…" : "Enviar a revisión"}
              </Button>
            ) : (
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setResult(null);
                  setFile(null);
                  setStep(0);
                }}
                className="active:scale-[0.98]"
              >
                Nueva carga
              </Button>
            )}
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function ContextStep({
  form,
  updateField,
  lockedSet,
  canUnlock,
  unlocked,
  onToggleUnlock,
}: {
  form: IntakeForm;
  updateField: (field: keyof IntakeForm, value: string) => void;
  lockedSet: Set<IntakeLockedField>;
  canUnlock: boolean;
  unlocked: boolean;
  onToggleUnlock: () => void;
}) {
  const lockedItems = Array.from(lockedSet);
  const lockedItemDisplay = (field: IntakeLockedField): string => {
    if (field === "load_type") {
      return loadTypes.find((option) => option.value === form.load_type)?.label ?? form.load_type;
    }
    if (field === "institution_code") {
      return (
        institutions.find((option) => option.value === form.institution_code)?.label ??
        form.institution_code
      );
    }
    return form[field] ?? "";
  };

  return (
    <section className="space-y-4">
      <StepHeading title="Contexto regulatorio" />

      {lockedItems.length > 0 ? (
        <div className="rounded-md border border-primary/20 bg-primary/5 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex items-start gap-2">
              <Lock className="mt-0.5 h-4 w-4 text-primary" aria-hidden="true" />
              <div className="min-w-0">
                <p className="text-sm font-semibold text-primary">
                  Contexto bloqueado para evitar errores
                </p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  Estos datos vienen de tu sesión y del calendario REPSE. Si necesitas cambiarlos,
                  desbloquéalos abajo.
                </p>
              </div>
            </div>
          </div>
          <dl className="mt-3 grid gap-2 sm:grid-cols-2">
            {lockedItems.map((field) => (
              <div
                key={field}
                className="rounded-md border border-primary/15 bg-white px-3 py-2"
                data-locked-field={field}
              >
                <dt className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-muted-foreground">
                  <Lock className="h-3 w-3" aria-hidden="true" />
                  {LOCKED_FIELD_LABELS[field]}
                </dt>
                <dd className="mt-0.5 break-words text-sm font-medium text-foreground">
                  {lockedItemDisplay(field)}
                </dd>
                {LOCKED_FIELD_SOURCE[field] ? (
                  <p className="mt-0.5 text-[11px] text-muted-foreground">
                    {LOCKED_FIELD_SOURCE[field]}
                  </p>
                ) : null}
              </div>
            ))}
          </dl>
        </div>
      ) : null}

      {canUnlock ? (
        <button
          type="button"
          onClick={onToggleUnlock}
          className="inline-flex items-center gap-1.5 text-xs font-medium text-primary underline-offset-4 hover:underline"
        >
          <PencilSimple className="h-3 w-3" aria-hidden="true" />
          {unlocked ? "Volver a bloquear el contexto" : "Necesito cambiar algo del contexto"}
        </button>
      ) : null}

      <div className="grid gap-4 md:grid-cols-2">
        {!lockedSet.has("client_name") ? (
          <Field label="Cliente" htmlFor="client_name">
            <Input
              id="client_name"
              value={form.client_name}
              onChange={(event) => updateField("client_name", event.target.value)}
              placeholder="Cliente o filial"
              required
            />
          </Field>
        ) : null}
        {!lockedSet.has("vendor_name") ? (
          <Field label="Proveedor" htmlFor="vendor_name">
            <Input
              id="vendor_name"
              value={form.vendor_name}
              onChange={(event) => updateField("vendor_name", event.target.value)}
              placeholder="Razón social del proveedor"
              required
            />
          </Field>
        ) : null}
        {!lockedSet.has("vendor_rfc") ? (
          <Field label="RFC proveedor" htmlFor="vendor_rfc">
            <Input
              id="vendor_rfc"
              value={form.vendor_rfc}
              onChange={(event) => updateField("vendor_rfc", event.target.value.toUpperCase())}
              placeholder="ABC010203AB1"
              minLength={12}
              maxLength={13}
              required
            />
          </Field>
        ) : null}
        {!lockedSet.has("contract_reference") ? (
          <Field label="Contrato, si aplica" htmlFor="contract_reference">
            <Input
              id="contract_reference"
              value={form.contract_reference}
              onChange={(event) => updateField("contract_reference", event.target.value)}
              placeholder="Referencia interna"
            />
          </Field>
        ) : null}
        {!lockedSet.has("period_code") ? (
          <Field label="Periodo" htmlFor="period_code">
            <Input
              id="period_code"
              value={form.period_code}
              onChange={(event) => updateField("period_code", event.target.value)}
              placeholder="2026-05 / Ene-Abr 2026"
              required
            />
          </Field>
        ) : null}
        {!lockedSet.has("load_type") ? (
          <Field label="Tipo de carga" htmlFor="load_type">
            <Select
              id="load_type"
              value={form.load_type}
              onChange={(event) => updateField("load_type", event.target.value)}
            >
              {loadTypes.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </Field>
        ) : null}
        {!lockedSet.has("institution_code") ? (
          <Field label="Institución" htmlFor="institution_code">
            <Select
              id="institution_code"
              value={form.institution_code}
              onChange={(event) => updateField("institution_code", event.target.value)}
            >
              {institutions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </Field>
        ) : null}
        {!lockedSet.has("requirement_name") ? (
          <Field label="Requisito / documento" htmlFor="requirement_name">
            <Select
              id="requirement_name"
              value={form.requirement_name}
              onChange={(event) => updateField("requirement_name", event.target.value)}
            >
              {requirements.map((requirement) => (
                <option key={requirement} value={requirement}>
                  {requirement}
                </option>
              ))}
            </Select>
          </Field>
        ) : null}
      </div>
    </section>
  );
}

function RequirementStep({ requirement }: { requirement: (typeof requirementGuides)[number] }) {
  return (
    <section className="space-y-4">
      <StepHeading title="Requisito esperado" />
      <div className="rounded-md border border-border bg-muted/40 p-5">
        <div className="flex flex-wrap items-center gap-2">
          <Badge>{requirement.institution}</Badge>
          <Badge variant="warning">Riesgo {requirement.risk}</Badge>
          <Badge variant="outline">{requirement.frequency}</Badge>
        </div>
        <h3 className="mt-4 text-xl font-semibold">{requirement.name}</h3>
        <p className="mt-3 text-sm text-muted-foreground">{requirement.why}</p>
        <div className="mt-5 grid gap-4 md:grid-cols-2">
          <div>
            <p className="text-sm font-semibold">Ejemplo válido</p>
            <p className="mt-1 text-sm text-muted-foreground">{requirement.validExample}</p>
          </div>
          <div>
            <p className="text-sm font-semibold">Causas comunes de rechazo</p>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
              {requirement.rejectionCauses.map((cause) => (
                <li key={cause}>{cause}</li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}

function UploadStep({
  file,
  fileError,
  onFileSelected,
  onUseDemoFile,
  comments,
  onCommentsChange,
  filePreviewUrl,
  duplicateCheck,
  duplicateChecking,
  requirement,
}: {
  file: File | null;
  fileError: string | null;
  onFileSelected: (file: File | null) => void;
  onUseDemoFile?: () => void;
  comments: string;
  onCommentsChange: (value: string) => void;
  filePreviewUrl: string | null;
  duplicateCheck: DuplicateCheck | null;
  duplicateChecking: boolean;
  requirement: (typeof requirementGuides)[number];
}) {
  return (
    <section className="space-y-4">
      <StepHeading title="Sube el documento" />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-4">
          <label
            htmlFor="native-file"
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              onFileSelected(event.dataTransfer.files?.[0] ?? null);
            }}
            className="flex min-h-[180px] cursor-pointer flex-col items-center justify-center rounded-md border border-dashed border-primary/40 bg-emerald-50/50 p-6 text-center transition-colors hover:bg-emerald-50"
          >
            <CloudArrowUp className="h-9 w-9 text-primary" aria-hidden="true" />
            <p className="mt-3 text-sm font-semibold">
              Arrastra o selecciona el PDF
            </p>
            <p className="mt-1 text-sm text-muted-foreground">
              Solo PDF, máximo 15 MB. No subas archivos protegidos con contraseña.
            </p>
            <input
              id="native-file"
              type="file"
              accept=".pdf,application/pdf"
              className="sr-only"
              onChange={(event) =>
                onFileSelected(event.target.files?.[0] ?? null)
              }
            />
          </label>

          {file ? (
            <div className="rounded-md border border-border bg-white p-3 text-sm">
              <div className="flex items-center gap-2 font-medium">
                <FileText className="h-4 w-4 text-primary" aria-hidden="true" />
                {file.name}
              </div>
              <p className="mt-1 text-muted-foreground">
                {Math.ceil(file.size / 1024)} KB
              </p>
            </div>
          ) : null}

          {duplicateChecking ? (
            <div className="flex items-center gap-2 rounded-md border border-border bg-muted/40 p-3 text-xs text-muted-foreground">
              <CircleNotch className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
              Verificando si ya habías subido este mismo archivo…
            </div>
          ) : null}

          {duplicateCheck?.exists ? (
            <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
              <div className="flex items-start gap-2">
                <Warning
                  className="mt-0.5 h-4 w-4 shrink-0 text-amber-700"
                  aria-hidden="true"
                />
                <div className="min-w-0">
                  <p className="font-medium">Ya habías subido este archivo</p>
                  <p className="mt-1 text-xs">
                    Mismo SHA-256 que una carga anterior
                    {duplicateCheck.filename ? ` (${duplicateCheck.filename})` : ""}
                    {duplicateCheck.requirement_name
                      ? ` para "${duplicateCheck.requirement_name}"`
                      : ""}
                    {duplicateCheck.status
                      ? ` con estado "${duplicateCheck.status}"`
                      : ""}
                    . Puedes continuar si es a propósito; si no, revisa la carga
                    anterior.
                  </p>
                  {duplicateCheck.submission_id ? (
                    <Link
                      href={`/portal/submissions/${duplicateCheck.submission_id}`}
                      className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-amber-900 underline"
                    >
                      Ver carga anterior
                      <ArrowRight className="h-3 w-3" aria-hidden="true" />
                    </Link>
                  ) : null}
                </div>
              </div>
            </div>
          ) : null}

          {filePreviewUrl ? (
            <div className="overflow-hidden rounded-md border border-border bg-muted/30">
              <div className="flex items-center gap-2 border-b border-border bg-white px-3 py-2 text-xs font-medium text-muted-foreground">
                <Eye className="h-3.5 w-3.5" aria-hidden="true" />
                Vista previa del PDF
              </div>
              <iframe
                src={filePreviewUrl}
                title="Vista previa del PDF seleccionado"
                className="block h-[420px] w-full"
              />
            </div>
          ) : null}

          {fileError ? (
            <p className="text-sm text-destructive">{fileError}</p>
          ) : null}

          {onUseDemoFile ? (
            <Button
              type="button"
              variant="outline"
              className="w-fit"
              data-testid="use-demo-pdf"
              onClick={onUseDemoFile}
            >
              <FileText className="h-4 w-4" aria-hidden="true" />
              Usar PDF demo
            </Button>
          ) : null}

          <Field label="Comentarios o aclaraciones" htmlFor="comments">
            <Textarea
              id="comments"
              value={comments}
              onChange={(event) => onCommentsChange(event.target.value)}
              placeholder="Ej. El documento cubre el periodo de mayo 2026; el acuse fue emitido el día..."
            />
          </Field>
        </div>

        <aside className="space-y-3" aria-label="Guía del requisito">
          <RequirementGuideCard requirement={requirement} />
        </aside>
      </div>
    </section>
  );
}

function RequirementGuideCard({
  requirement,
}: {
  requirement: (typeof requirementGuides)[number];
}) {
  return (
    <div className="space-y-3 rounded-md border border-border bg-white p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">{requirement.institution}</Badge>
        <Badge variant="outline">{requirement.frequency}</Badge>
      </div>
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Qué necesitamos
        </p>
        <h3 className="mt-1 text-sm font-semibold">{requirement.name}</h3>
        <p className="mt-1 text-xs text-muted-foreground">{requirement.why}</p>
      </div>
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Ejemplo válido
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          {requirement.validExample}
        </p>
      </div>
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Causas comunes de rechazo
        </p>
        <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-muted-foreground">
          {requirement.rejectionCauses.map((cause) => (
            <li key={cause}>{cause}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function PrevalidationStep({
  form,
  file,
  requirement,
  duplicateCheck,
}: {
  form: IntakeForm;
  file: File | null;
  requirement: (typeof requirementGuides)[number];
  duplicateCheck: DuplicateCheck | null;
}) {
  return (
    <section className="space-y-4">
      <StepHeading title="Revisa antes de enviar" />
      <div className="grid gap-4 md:grid-cols-2">
        <ReviewItem label="Cliente" value={form.client_name || "Pendiente"} />
        <ReviewItem
          label="Proveedor / RFC"
          value={`${form.vendor_name || "Pendiente"} / ${form.vendor_rfc || "-"}`}
        />
        <ReviewItem label="Periodo" value={form.period_code} />
        <ReviewItem label="Requisito" value={requirement.name} />
        <ReviewItem label="Archivo" value={file?.name ?? "Sin archivo"} />
        <ReviewItem label="Estado inicial" value="pendiente_revision" />
      </div>

      {duplicateCheck?.exists ? (
        <div className="rounded-md border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
          <div className="flex items-start gap-2">
            <Warning
              className="mt-0.5 h-4 w-4 shrink-0 text-amber-700"
              aria-hidden="true"
            />
            <div>
              <p className="font-medium">Este archivo ya existe en tu expediente</p>
              <p className="mt-1 text-xs">
                Si es a propósito (re-envío para corregir) puedes continuar. Si no,
                regresa y elige el archivo correcto.
              </p>
            </div>
          </div>
        </div>
      ) : null}

      <div className="rounded-md border border-primary/25 bg-primary/5 p-4">
        <p className="text-xs font-medium uppercase tracking-wide text-primary">
          Lo que sigue al enviar
        </p>
        <ol className="mt-2 space-y-2 text-sm">
          <li className="flex items-start gap-2">
            <ShieldCheck
              className="mt-0.5 h-4 w-4 shrink-0 text-primary"
              aria-hidden="true"
            />
            <span>
              Calculamos hash SHA-256, inspeccionamos la estructura PDF y leemos
              señales determinísticas. Nada se aprueba automáticamente.
            </span>
          </li>
          <li className="flex items-start gap-2">
            <UserCheck
              className="mt-0.5 h-4 w-4 shrink-0 text-primary"
              aria-hidden="true"
            />
            <span>
              Pasa a revisión humana del equipo de cumplimiento. La aprobación
              final siempre es humana.
            </span>
          </li>
          <li className="flex items-start gap-2">
            <Calendar
              className="mt-0.5 h-4 w-4 shrink-0 text-primary"
              aria-hidden="true"
            />
            <span>
              Puedes consultar el estado en tu calendario o en el detalle del
              documento cuando termine la revisión.
            </span>
          </li>
        </ol>
      </div>
    </section>
  );
}

function ConfirmationStep({
  result,
  error,
}: {
  result: SubmissionResponse | null;
  error: string | null;
}) {
  if (error) {
    return (
      <div
        role="alert"
        className="rounded-md border border-amber-300 bg-amber-50 p-5"
      >
        <div className="flex gap-3">
          <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-amber-500 text-white">
            <Warning className="h-4 w-4" aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-amber-900">
              No pudimos enviar tu documento
            </p>
            <p className="mt-1 text-sm text-amber-900/80">{error}</p>
            <p className="mt-1 text-xs text-amber-900/70">
              Tu archivo y los datos siguen aquí. Vuelve al paso anterior para reintentar.
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (!result) {
    return (
      <div className="rounded-md border border-border bg-muted/40 p-4 text-sm text-muted-foreground">
        Envía la carga para ver el resultado de prevalidación.
      </div>
    );
  }

  const isMismatch = Boolean(result.document_signals?.mismatch_reason);
  const isClarification = result.status === DocumentStatus.REQUIERE_ACLARACION;
  const isAttention = isMismatch || isClarification;
  const heroTone = isAttention
    ? "border-amber-300 bg-amber-50"
    : "border-emerald-200 bg-emerald-50";
  const heroIconBg = isAttention
    ? "bg-amber-500 text-white"
    : "bg-emerald-500 text-white";
  const HeroIcon = isAttention ? Warning : CheckCircle;
  const heroHeadline = isMismatch
    ? "Recibimos tu documento, pero detectamos una posible inconsistencia"
    : isClarification
      ? "Recibimos tu documento, pero necesitamos una aclaración"
      : "Recibimos tu documento";
  const heroSubcopy = isMismatch
    ? "Tu archivo entró al sistema y queda como evidencia, pero el revisor humano lo verá con una alerta. Si subiste el documento equivocado, vuelve a cargar el correcto."
    : isClarification
      ? "El documento entró al sistema, pero el revisor humano necesita más información antes de aprobarlo."
      : "Tu archivo entró al sistema y pasó las prevalidaciones automáticas iniciales. El revisor humano dará el dictamen final.";

  return (
    <section className="space-y-5">
      <div className={`cw-fade-up rounded-md border p-5 ${heroTone}`}>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex gap-3">
            <div
              className={`cw-success-ring mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${heroIconBg}`}
              aria-hidden="true"
            >
              {isAttention ? (
                <HeroIcon className="h-5 w-5" aria-hidden="true" />
              ) : (
                <AnimatedCheck />
              )}
            </div>
            <div className="min-w-0">
              <p className="text-base font-semibold">{heroHeadline}</p>
              <p className="mt-1 text-sm text-muted-foreground">{heroSubcopy}</p>
            </div>
          </div>
          <Badge>{result.status}</Badge>
        </div>
      </div>

      <div className="cw-fade-up rounded-md border border-primary/25 bg-primary/5 p-5">
        <p className="text-xs font-medium uppercase tracking-wide text-primary">
          Lo que sigue
        </p>
        <ol className="cw-stagger mt-3 space-y-3 text-sm">
          <li className="flex items-start gap-3">
            <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
              1
            </span>
            <div>
              <p className="font-medium">Prevalidaciones automáticas</p>
              <p className="text-xs text-muted-foreground">
                Hash SHA-256, estructura PDF, texto legible, señales documentales.
                Ya corrieron al recibir tu archivo.
              </p>
            </div>
          </li>
          <li className="flex items-start gap-3">
            <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
              2
            </span>
            <div>
              <p className="font-medium">Revisión humana del equipo de cumplimiento</p>
              <p className="text-xs text-muted-foreground">
                Una persona autorizada decide aprobar, rechazar o pedir aclaración.
                La automatización no aprueba.
              </p>
            </div>
          </li>
          <li className="flex items-start gap-3">
            <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
              3
            </span>
            <div>
              <p className="font-medium">Verás el resultado en tu calendario</p>
              <p className="text-xs text-muted-foreground">
                Si te piden corregir algo, te llevaremos al detalle del documento
                con la razón exacta.
              </p>
            </div>
          </li>
        </ol>
        <div className="mt-5 flex flex-wrap gap-2">
          <Button asChild className="active:scale-[0.98]">
            <Link href="/portal/dashboard">
              <Calendar className="h-4 w-4" aria-hidden="true" />
              Ver mi calendario
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          </Button>
          <Button asChild variant="outline" className="active:scale-[0.98]">
            <Link href={`/portal/submissions/${result.submission_id}`}>
              <FileText className="h-4 w-4" aria-hidden="true" />
              Ver detalle del documento
            </Link>
          </Button>
        </div>
      </div>

      <details className="rounded-md border border-border bg-white p-4 text-sm">
        <summary className="cursor-pointer text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Datos de trazabilidad
        </summary>
        <div className="mt-3 grid gap-2 text-xs text-muted-foreground md:grid-cols-2">
          <span className="break-all">Submission: {result.submission_id}</span>
          <span className="break-all">Documento: {result.document_id}</span>
          <span>
            Eventos registrados: {result.validation_events?.length ?? 0}
          </span>
          <span>Páginas PDF: {result.inspection?.page_count ?? "N/D"}</span>
          <span className="break-all md:col-span-2">
            SHA-256: {result.sha256}
          </span>
        </div>
      </details>

      <ValidationSummary validations={result.validations} />
    </section>
  );
}

function StepHeading({ title }: { title: string }) {
  return (
    <div className="flex items-center gap-2">
      <ShieldCheck className="h-5 w-5 text-primary" aria-hidden="true" />
      <h2 className="text-lg font-semibold">{title}</h2>
    </div>
  );
}

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
    </div>
  );
}

function ReviewItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border bg-white p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 break-words text-sm font-medium">{value}</p>
    </div>
  );
}

async function sha256OfFile(file: File): Promise<string> {
  const buf = await file.arrayBuffer();
  const hash = await crypto.subtle.digest("SHA-256", buf);
  return Array.from(new Uint8Array(hash))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function formatApiError(payload: unknown): string {
  if (!payload || typeof payload !== "object" || !("detail" in payload)) {
    return "No fue posible registrar la carga.";
  }

  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string") {
    return detail;
  }

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (!item || typeof item !== "object") {
          return null;
        }
        const detailItem = item as { loc?: unknown; msg?: unknown };
        const message = typeof detailItem.msg === "string" ? detailItem.msg : null;
        const location =
          Array.isArray(detailItem.loc)
            ? detailItem.loc.filter((part: unknown): part is string => typeof part === "string").join(" > ")
            : null;
        return [location, message].filter(Boolean).join(": ");
      })
      .filter(Boolean);

    if (messages.length > 0) {
      return messages.join(" · ");
    }
  }

  return "No fue posible registrar la carga.";
}

// Confirmation hero check mark. The path stroke draws in (via the
// .cw-draw-check selector in globals.css) right after the success ring
// pops, giving the moment a real "done" beat without animating layout.
function AnimatedCheck() {
  return (
    <svg
      className="cw-draw-check h-5 w-5"
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        d="M5 12.5 L10 17.5 L19 7.5"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
