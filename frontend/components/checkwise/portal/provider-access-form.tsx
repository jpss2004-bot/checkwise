"use client";

import { FormEvent, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Key } from "@phosphor-icons/react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { createPortalAccess, PortalApiError } from "@/lib/api/portal";
import { DEMO_CLIENTS } from "@/lib/demo-clients";
import { writePortalSession, type PersonaType } from "@/lib/session/portal";

type FormState = {
  client_name: string;
  filial_name: string;
  vendor_name: string;
  vendor_rfc: string;
  persona_type: PersonaType;
  contract_reference: string;
};

const initialState: FormState = {
  client_name: DEMO_CLIENTS[0]?.name ?? "",
  filial_name: DEMO_CLIENTS[0]?.filiales[0]?.name ?? "",
  vendor_name: "",
  vendor_rfc: "",
  persona_type: "moral",
  contract_reference: "",
};

interface FieldErrors {
  vendor_name?: string;
  vendor_rfc?: string;
}

export function ProviderAccessForm() {
  const router = useRouter();
  const [form, setForm] = useState<FormState>(initialState);
  const [submitting, setSubmitting] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});

  const selectedClient = useMemo(
    () => DEMO_CLIENTS.find((c) => c.name === form.client_name) ?? DEMO_CLIENTS[0],
    [form.client_name],
  );

  function updateField<K extends keyof FormState>(field: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [field]: value }));
    if (field === "vendor_name" || field === "vendor_rfc") {
      setFieldErrors((current) => ({ ...current, [field]: undefined }));
    }
  }

  function handleClientChange(name: string) {
    const client = DEMO_CLIENTS.find((c) => c.name === name);
    setForm((current) => ({
      ...current,
      client_name: name,
      filial_name: client?.filiales[0]?.name ?? "",
    }));
  }

  function validate(): FieldErrors {
    const errors: FieldErrors = {};
    if (form.vendor_name.trim().length < 2) {
      errors.vendor_name = "Captura la razón social del proveedor.";
    }
    const rfc = form.vendor_rfc.trim();
    if (rfc.length < 12 || rfc.length > 13) {
      errors.vendor_rfc = "El RFC debe tener 12 o 13 caracteres.";
    }
    return errors;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const errors = validate();
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    setServerError(null);
    setSubmitting(true);
    try {
      const access = await createPortalAccess({
        client_name: form.client_name.trim(),
        filial_name: form.filial_name.trim() || null,
        vendor_name: form.vendor_name.trim(),
        vendor_rfc: form.vendor_rfc.trim().toUpperCase(),
        persona_type: form.persona_type,
        contract_reference: form.contract_reference.trim() || null,
      });
      writePortalSession({
        workspace_id: access.workspace_id,
        access_token: access.access_token,
        persona_type: access.persona_type as PersonaType,
        client_name: access.client_name,
        vendor_name: access.vendor_name,
        vendor_rfc: access.vendor_rfc,
        filial_name: access.filial_name,
        contract_reference: access.contract_reference,
        onboarding_completed_at: access.onboarding_completed_at,
      });
      router.push("/portal/onboarding");
    } catch (caught) {
      if (caught instanceof PortalApiError) {
        setServerError(
          `No pudimos crear tu acceso (${caught.status}). Intenta de nuevo o contacta soporte.`,
        );
      } else {
        setServerError("No pudimos crear tu acceso. Revisa tu conexión e intenta de nuevo.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-col gap-5"
      data-testid="provider-access-form"
      noValidate
    >
      <div className="flex items-center justify-end">
        <Badge variant="outline">Demo · sin auth de producción</Badge>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Cliente" htmlFor="client_name">
          <Select
            id="client_name"
            value={form.client_name}
            onChange={(event) => handleClientChange(event.target.value)}
          >
            {DEMO_CLIENTS.map((client) => (
              <option key={client.name} value={client.name}>
                {client.name}
              </option>
            ))}
          </Select>
        </Field>

        <Field label="Filial" htmlFor="filial_name">
          <Select
            id="filial_name"
            value={form.filial_name}
            onChange={(event) => updateField("filial_name", event.target.value)}
          >
            {selectedClient?.filiales.map((filial) => (
              <option key={filial.name} value={filial.name}>
                {filial.name}
              </option>
            ))}
          </Select>
        </Field>

        <Field
          label="Razón social del proveedor"
          htmlFor="vendor_name"
          required
          error={fieldErrors.vendor_name}
          className="sm:col-span-2"
        >
          <Input
            id="vendor_name"
            value={form.vendor_name}
            onChange={(event) => updateField("vendor_name", event.target.value)}
            placeholder="Servicios Especializados SA de CV"
            autoComplete="organization"
          />
        </Field>

        <Field
          label="RFC del proveedor"
          htmlFor="vendor_rfc"
          required
          error={fieldErrors.vendor_rfc}
          helper="12 caracteres (persona moral) o 13 (persona física)."
        >
          <Input
            id="vendor_rfc"
            value={form.vendor_rfc}
            onChange={(event) =>
              updateField("vendor_rfc", event.target.value.toUpperCase())
            }
            placeholder="ABC010203AB1"
            minLength={12}
            maxLength={13}
            className="font-mono uppercase tracking-wide"
          />
        </Field>

        <Field label="Tipo de persona" htmlFor="persona_type">
          <Select
            id="persona_type"
            value={form.persona_type}
            onChange={(event) =>
              updateField("persona_type", event.target.value as PersonaType)
            }
          >
            <option value="moral">Persona moral</option>
            <option value="fisica">Persona física</option>
          </Select>
        </Field>

        <Field
          label="Contrato"
          htmlFor="contract_reference"
          helper="Si tu cliente te dio un folio, captúralo. Opcional."
          className="sm:col-span-2"
        >
          <Input
            id="contract_reference"
            value={form.contract_reference}
            onChange={(event) => updateField("contract_reference", event.target.value)}
            placeholder="CTR-2026-001"
            className="font-mono"
          />
        </Field>
      </div>

      {serverError && (
        <Alert variant="error">
          <AlertTitle>No pudimos abrir tu espacio</AlertTitle>
          <AlertDescription>{serverError}</AlertDescription>
        </Alert>
      )}

      <Button type="submit" loading={submitting} className="w-full" size="lg">
        <span>Entrar a mi portal</span>
        {!submitting && <ArrowRight className="h-4 w-4" weight="bold" aria-hidden="true" />}
      </Button>

      <div className="flex flex-col gap-2 border-t border-[color:var(--border-subtle)] pt-4 text-xs">
        <Link
          href="/activate"
          className="inline-flex items-center justify-center gap-2 text-[color:var(--text-link)] hover:underline"
        >
          <Key className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
          <span>¿Tienes credenciales temporales? Activa tu cuenta aquí.</span>
        </Link>
        <p className="text-center text-[color:var(--text-tertiary)]">
          CheckWise no firma documentos. Revisión humana obligatoria.
        </p>
      </div>
    </form>
  );
}
