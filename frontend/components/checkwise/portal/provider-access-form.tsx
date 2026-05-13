"use client";

import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, ArrowRight, Loader2, ShieldCheck } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { DEMO_CLIENTS } from "@/lib/demo-clients";
import { createPortalAccess, PortalApiError } from "@/lib/portal-client";
import {
  writePortalSession,
  type PersonaType,
} from "@/lib/portal-session";

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

export function ProviderAccessForm() {
  const router = useRouter();
  const [form, setForm] = useState<FormState>(initialState);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedClient = useMemo(
    () => DEMO_CLIENTS.find((c) => c.name === form.client_name) ?? DEMO_CLIENTS[0],
    [form.client_name],
  );

  function updateField<K extends keyof FormState>(field: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function handleClientChange(name: string) {
    const client = DEMO_CLIENTS.find((c) => c.name === name);
    setForm((current) => ({
      ...current,
      client_name: name,
      filial_name: client?.filiales[0]?.name ?? "",
    }));
  }

  function validate(): string | null {
    if (form.vendor_name.trim().length < 2) return "Captura la razón social del proveedor.";
    const rfc = form.vendor_rfc.trim();
    if (rfc.length < 12 || rfc.length > 13) return "El RFC debe tener 12 o 13 caracteres.";
    return null;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }
    setError(null);
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
        setError(`No fue posible iniciar sesión demo (${caught.status}).`);
      } else {
        setError("No fue posible iniciar sesión demo.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card className="mx-auto max-w-2xl">
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-primary" aria-hidden="true" />
            <CardTitle>Acceso de proveedor</CardTitle>
          </div>
          <Badge variant="outline">Demo · sin autenticación de producción</Badge>
        </div>
        <p className="mt-2 text-sm text-muted-foreground">
          Captura el contexto de trabajo (cliente, filial, proveedor) para abrir tu espacio de
          cumplimiento REPSE. En esta fase la sesión vive como demo segura en este dispositivo.
        </p>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-5" data-testid="provider-access-form">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="client_name">Cliente</Label>
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
            </div>
            <div className="space-y-2">
              <Label htmlFor="filial_name">Filial</Label>
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
            </div>
            <div className="space-y-2">
              <Label htmlFor="vendor_name">Razón social del proveedor</Label>
              <Input
                id="vendor_name"
                value={form.vendor_name}
                onChange={(event) => updateField("vendor_name", event.target.value)}
                placeholder="Servicios Especializados SA de CV"
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="vendor_rfc">RFC proveedor</Label>
              <Input
                id="vendor_rfc"
                value={form.vendor_rfc}
                onChange={(event) =>
                  updateField("vendor_rfc", event.target.value.toUpperCase())
                }
                placeholder="ABC010203AB1"
                minLength={12}
                maxLength={13}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="persona_type">Tipo de persona</Label>
              <Select
                id="persona_type"
                value={form.persona_type}
                onChange={(event) =>
                  updateField("persona_type", event.target.value as PersonaType)
                }
              >
                <option value="moral">Persona Moral</option>
                <option value="fisica">Persona Física</option>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="contract_reference">Contrato (opcional)</Label>
              <Input
                id="contract_reference"
                value={form.contract_reference}
                onChange={(event) => updateField("contract_reference", event.target.value)}
                placeholder="CTR-2026-001"
              />
            </div>
          </div>

          {error ? (
            <div className="rounded-md border border-destructive/30 bg-red-50 p-3 text-sm text-destructive">
              <div className="flex gap-2">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                <span>{error}</span>
              </div>
            </div>
          ) : null}

          <Button type="submit" disabled={submitting} className="w-full md:w-auto">
            {submitting ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            )}
            Entrar al espacio del proveedor
          </Button>

          <p className="text-xs text-muted-foreground">
            CheckWise no firma legalmente documentos. La revisión humana sigue siendo obligatoria
            para el cumplimiento REPSE.
          </p>
        </form>
      </CardContent>
    </Card>
  );
}
