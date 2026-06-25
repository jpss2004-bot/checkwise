"use client";

import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ProviderLimitModal } from "@/components/checkwise/plan/provider-limit-modal";
import { ProviderRestoreModal } from "@/components/checkwise/plan/provider-restore-modal";
import { createClientProvider } from "@/lib/api/client";
import { parseClientErrorCode } from "@/lib/api/error-detail";
import { useUrlClientId } from "@/lib/workspace/use-url-client-id";

/**
 * Shared "add a provider" form for the client portal.
 *
 * Builds the full provider stack (User + Vendor + ProviderWorkspace) via
 * ``POST /client/providers`` and emails the invitation. The server is the
 * authoritative cap: a ``provider_limit_reached`` 409 opens the upgrade
 * modal, and a ``provider_archived`` 409 (the RFC already exists, archived)
 * opens the restore modal — we never duplicate that hard block client-side.
 *
 * Used by both ``/client/onboarding`` (Mis proveedores) and
 * ``/client/vendors`` (the portfolio list). Render only for Approvers; the
 * backend ``ClientApprover`` gate is the real boundary.
 */
export function AddProviderForm({
  onCreated,
}: {
  onCreated: (result: { contact_email: string; email_status: string }) => void;
}) {
  const urlClientId = useUrlClientId();
  const [vendorName, setVendorName] = useState("");
  const [vendorRfc, setVendorRfc] = useState("");
  const [personaType, setPersonaType] = useState<"moral" | "fisica">("moral");
  const [contactName, setContactName] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [contactPhone, setContactPhone] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [limitErr, setLimitErr] = useState<{
    used: number | null;
    limit: number | null;
  } | null>(null);
  const [restore, setRestore] = useState<{ vendor_id: string } | null>(null);

  async function handle(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setErr(null);
    try {
      const result = await createClientProvider(
        {
          vendor_name: vendorName.trim(),
          vendor_rfc: vendorRfc.trim().toUpperCase(),
          persona_type: personaType,
          contact_name: contactName.trim(),
          contact_email: contactEmail.trim().toLowerCase(),
          contact_phone: contactPhone.trim() || null,
        },
        urlClientId ? { client_id: urlClientId } : undefined,
      );
      onCreated(result);
      // Reset for the next entry — operators often add several in a row.
      setVendorName("");
      setVendorRfc("");
      setContactName("");
      setContactEmail("");
      setContactPhone("");
    } catch (error) {
      const parsed = parseClientErrorCode(error);
      if (parsed.code === "provider_limit_reached") {
        setLimitErr({ used: parsed.used ?? null, limit: parsed.limit ?? null });
      } else if (parsed.code === "provider_archived" && parsed.vendor_id) {
        setRestore({ vendor_id: parsed.vendor_id });
      } else {
        setErr(parsed.detail);
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <form
        onSubmit={handle}
        className="space-y-3 rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] p-3"
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="ap-name">Razón social del proveedor</Label>
            <Input
              id="ap-name"
              value={vendorName}
              onChange={(e) => setVendorName(e.target.value)}
              required
              placeholder="Servicios Especializados, S.A."
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="ap-rfc">RFC</Label>
            <Input
              id="ap-rfc"
              value={vendorRfc}
              onChange={(e) => setVendorRfc(e.target.value.toUpperCase())}
              minLength={12}
              maxLength={13}
              required
              className="font-mono"
              placeholder="ABC123456XYZ"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="ap-persona">Tipo de persona</Label>
            <select
              id="ap-persona"
              value={personaType}
              onChange={(e) =>
                setPersonaType(e.target.value as "moral" | "fisica")
              }
              className="h-9 w-full rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-2 text-sm"
            >
              <option value="moral">Persona moral</option>
              <option value="fisica">Persona física</option>
            </select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="ap-contact-phone">Teléfono (opcional)</Label>
            <Input
              id="ap-contact-phone"
              type="tel"
              value={contactPhone}
              onChange={(e) => setContactPhone(e.target.value)}
              autoComplete="tel"
              placeholder="+52 55 1234 5678"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="ap-contact-name">Nombre de contacto</Label>
            <Input
              id="ap-contact-name"
              value={contactName}
              onChange={(e) => setContactName(e.target.value)}
              required
              placeholder="Juan García"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="ap-contact-email">Correo del contacto</Label>
            <Input
              id="ap-contact-email"
              type="email"
              value={contactEmail}
              onChange={(e) => setContactEmail(e.target.value)}
              required
              autoComplete="email"
              placeholder="juan@proveedor.com"
            />
            <p className="text-[10px] text-[color:var(--text-tertiary)]">
              Aquí le enviaremos su invitación y credenciales temporales.
            </p>
          </div>
        </div>
        {err ? (
          <p className="text-xs text-[color:var(--status-error-text)]">{err}</p>
        ) : null}
        <div className="flex justify-end">
          <Button type="submit" loading={submitting} size="sm">
            Agregar y enviar invitación
          </Button>
        </div>
      </form>
      <ProviderLimitModal
        open={limitErr !== null}
        used={limitErr?.used ?? null}
        limit={limitErr?.limit ?? null}
        onClose={() => setLimitErr(null)}
      />
      <ProviderRestoreModal
        open={restore !== null}
        vendorId={restore?.vendor_id ?? null}
        clientId={urlClientId}
        onClose={() => setRestore(null)}
        onRestored={() => {
          setRestore(null);
          onCreated({ contact_email: "", email_status: "restored" });
        }}
      />
    </>
  );
}
