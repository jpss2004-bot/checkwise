"use client";

import { FormEvent, useMemo, useState } from "react";
import { AlertCircle, CheckCircle2, Loader2, UploadCloud } from "lucide-react";

import { institutions, loadTypes, requirements } from "@/lib/catalogs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

type ValidationSignal = {
  rule_code: string;
  rule_type: string;
  result: string;
  severity: string;
  message: string;
  requires_human_review: boolean;
};

type SubmissionResponse = {
  submission_id: string;
  document_id: string;
  status: string;
  sha256: string;
  storage_key: string;
  validations: ValidationSignal[];
  message: string;
};

export function DocumentSubmissionForm() {
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
    [],
  );
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [result, setResult] = useState<SubmissionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setResult(null);
    setError(null);

    const formData = new FormData(event.currentTarget);
    formData.set("initial_status", "pendiente_revision");

    try {
      const response = await fetch(`${apiBaseUrl}/api/v1/submissions`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail ?? "No fue posible registrar la carga.");
      }

      const payload = (await response.json()) as SubmissionResponse;
      setResult(payload);
      event.currentTarget.reset();
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Error inesperado.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <CardTitle>Registro de evidencia documental</CardTitle>
          <p className="mt-1 text-sm text-muted-foreground">
            Captura inicial compatible con cliente, proveedor, periodo, requisito, archivo y auditoría.
          </p>
        </div>
        <Badge variant="warning">pendiente_revision</Badge>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-6">
          <input type="hidden" name="initial_status" value="pendiente_revision" />

          <fieldset className="space-y-4">
            <legend className="text-sm font-semibold text-primary">Relación cliente-proveedor</legend>
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Cliente" htmlFor="client_name">
                <Input id="client_name" name="client_name" placeholder="Cliente o filial" required />
              </Field>
              <Field label="Proveedor" htmlFor="vendor_name">
                <Input id="vendor_name" name="vendor_name" placeholder="Razón social del proveedor" required />
              </Field>
              <Field label="RFC proveedor" htmlFor="vendor_rfc">
                <Input
                  id="vendor_rfc"
                  name="vendor_rfc"
                  placeholder="ABC010203AB1"
                  minLength={12}
                  maxLength={13}
                  required
                />
              </Field>
              <Field label="Contrato, si aplica" htmlFor="contract_reference">
                <Input id="contract_reference" name="contract_reference" placeholder="Referencia interna" />
              </Field>
            </div>
          </fieldset>

          <fieldset className="space-y-4">
            <legend className="text-sm font-semibold text-primary">Periodo y requisito</legend>
            <div className="grid gap-4 md:grid-cols-2">
              <Field label="Periodo" htmlFor="period_code">
                <Input id="period_code" name="period_code" placeholder="2026-05 / Ene-Abr 2026" required />
              </Field>
              <Field label="Tipo de carga" htmlFor="load_type">
                <Select id="load_type" name="load_type" defaultValue="mensual" required>
                  {loadTypes.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Institución" htmlFor="institution_code">
                <Select id="institution_code" name="institution_code" defaultValue="sat" required>
                  {institutions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Requisito / documento" htmlFor="requirement_name">
                <Select id="requirement_name" name="requirement_name" defaultValue={requirements[0]} required>
                  {requirements.map((requirement) => (
                    <option key={requirement} value={requirement}>
                      {requirement}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>
          </fieldset>

          <fieldset className="space-y-4">
            <legend className="text-sm font-semibold text-primary">Evidencia</legend>
            <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
              <Field label="Archivo" htmlFor="file">
                <Input
                  id="file"
                  name="file"
                  type="file"
                  accept=".pdf,.xml,.docx,.jpg,.jpeg,.png"
                  required
                />
              </Field>
              <Field label="Comentarios" htmlFor="comments">
                <Textarea
                  id="comments"
                  name="comments"
                  placeholder="Observaciones del proveedor, periodo o excepción"
                />
              </Field>
            </div>
          </fieldset>

          <div className="flex flex-col gap-3 border-t border-border pt-5 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-muted-foreground">
              Estado inicial fijo: <span className="font-medium text-foreground">pendiente_revision</span>
            </p>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <UploadCloud className="h-4 w-4" aria-hidden="true" />
              )}
              Registrar carga
            </Button>
          </div>
        </form>

        {error ? (
          <div className="mt-5 rounded-md border border-destructive/30 bg-red-50 p-4 text-sm text-destructive">
            <div className="flex gap-2">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <span>{error}</span>
            </div>
          </div>
        ) : null}

        {result ? (
          <div className="mt-5 rounded-md border border-primary/25 bg-emerald-50 p-4">
            <div className="flex gap-2 text-sm font-medium text-primary">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <span>{result.message}</span>
            </div>
            <div className="mt-3 grid gap-2 text-xs text-muted-foreground md:grid-cols-2">
              <span>Submission: {result.submission_id}</span>
              <span>Documento: {result.document_id}</span>
              <span className="md:col-span-2">SHA-256: {result.sha256}</span>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              {result.validations.slice(0, 6).map((validation) => (
                <Badge
                  key={validation.rule_code}
                  variant={validation.severity === "warning" ? "warning" : "secondary"}
                >
                  {validation.rule_code}: {validation.result}
                </Badge>
              ))}
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
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
