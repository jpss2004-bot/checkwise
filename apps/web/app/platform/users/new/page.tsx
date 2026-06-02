"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowRight,
  Buildings,
  CheckCircle,
  Copy,
  IdentificationCard,
  PaperPlaneTilt,
  Storefront,
  type Icon,
} from "@phosphor-icons/react";

import { Surface } from "@/components/checkwise/dashboard/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { PlatformShell } from "../../_shell";
import {
  listClients,
  provisionUser,
  type AdminClient,
  type ProvisionUserResponse,
} from "@/lib/api/admin";

/**
 * /admin/users/new — unified add-user flow (item 8 v2).
 *
 * One form. Role selector switches the field set. On submit the
 * backend mints a User + the role-specific stack (Client + Org +
 * Membership for client_admin; Vendor + Workspace for provider) and
 * emails a welcome with the freshly-generated temp password. The
 * confirmation surface shows the same plaintext password once — the
 * admin can hand it to the recipient via WhatsApp if the email
 * skipped (typical in dev without SMTP).
 */

type Role = "client" | "provider";

export default function AdminNewUserPage() {
  const [role, setRole] = useState<Role>("client");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");

  // Client-only fields
  const [clientName, setClientName] = useState("");
  const [clientRfc, setClientRfc] = useState("");

  // Provider-only fields
  const [vendorName, setVendorName] = useState("");
  const [vendorRfc, setVendorRfc] = useState("");
  const [personaType, setPersonaType] = useState<"moral" | "fisica">("moral");
  const [contactPhone, setContactPhone] = useState("");
  const [parentClientId, setParentClientId] = useState("");

  // Async state
  const [clients, setClients] = useState<AdminClient[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [errMsg, setErrMsg] = useState<string | null>(null);
  const [result, setResult] = useState<ProvisionUserResponse | null>(null);
  const [copied, setCopied] = useState(false);

  // Load the client list once — providers need a parent client to
  // anchor under. Non-fatal if the request fails (the dropdown stays
  // empty and the form returns 422 from the backend).
  useEffect(() => {
    listClients()
      .then((data) => setClients(data.items))
      .catch(() => setClients([]));
  }, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setErrMsg(null);
    try {
      const payload =
        role === "client"
          ? {
              full_name: fullName.trim(),
              email: email.trim().toLowerCase(),
              role: "client" as const,
              client_name: clientName.trim(),
              client_rfc: clientRfc.trim().toUpperCase() || null,
            }
          : {
              full_name: fullName.trim(),
              email: email.trim().toLowerCase(),
              role: "provider" as const,
              vendor_name: vendorName.trim(),
              vendor_rfc: vendorRfc.trim().toUpperCase(),
              persona_type: personaType,
              contact_phone: contactPhone.trim() || null,
              parent_client_id: parentClientId,
            };
      const response = await provisionUser(payload);
      setResult(response);
      // Reset just the identity fields so the admin can chain another
      // alta without re-typing the parent client.
      setFullName("");
      setEmail("");
      setClientName("");
      setClientRfc("");
      setVendorName("");
      setVendorRfc("");
      setContactPhone("");
      // Scroll the page back to the top so the success surface is
      // immediately in view; long forms otherwise leave the admin
      // wondering if the submit fired at all.
      if (typeof window !== "undefined") {
        window.scrollTo({ top: 0, behavior: "smooth" });
      }
    } catch (err) {
      setErrMsg(
        err instanceof Error ? err.message : "No pudimos crear el usuario.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function copyTempPassword() {
    if (!result) return;
    try {
      await navigator.clipboard.writeText(result.temp_password);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard API blocked (sometimes happens in localhost without
      // HTTPS) — the password is still visible on screen.
    }
  }

  return (
    <PlatformShell
      title="Nuevo usuario"
      description="Crea una cuenta nueva de cliente o proveedor. CheckWise genera una contraseña temporal, la muestra una vez en pantalla y la envía por correo."
      actions={
        <Button asChild size="sm" variant="outline">
          <Link href="/admin/clients">
            <ArrowLeft className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
            Volver a clientes
          </Link>
        </Button>
      }
    >
      <div className="space-y-6">
        {!result && (
          <Surface title="Tipo de cuenta" icon={IdentificationCard}>
            <div className="flex flex-wrap gap-2">
              <RoleButton
                active={role === "client"}
                onClick={() => setRole("client")}
                icon={Buildings}
                label="Cliente"
                caption="Una empresa que contrata proveedores REPSE y que recibe el cumplimiento agregado."
              />
              <RoleButton
                active={role === "provider"}
                onClick={() => setRole("provider")}
                icon={Storefront}
                label="Proveedor"
                caption="Una empresa proveedora REPSE que sube documentos en su espacio."
              />
            </div>
          </Surface>
        )}

        {!result && (
        <form onSubmit={handleSubmit} className="space-y-6">
          <Surface title="Datos de acceso" icon={IdentificationCard}>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1">
                <Label htmlFor="usr-name">Nombre completo</Label>
                <Input
                  id="usr-name"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  required
                  placeholder={role === "client" ? "María Pérez" : "Juan García"}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="usr-email">Correo electrónico</Label>
                <Input
                  id="usr-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoComplete="email"
                  placeholder="contacto@empresa.com"
                />
                <p className="text-[10px] text-[color:var(--text-tertiary)]">
                  Aquí enviaremos el correo de bienvenida con la contraseña
                  temporal.
                </p>
              </div>
            </div>
          </Surface>

          {role === "client" ? (
            <Surface title="Empresa cliente" icon={Buildings}>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1">
                  <Label htmlFor="cli-name">Razón social</Label>
                  <Input
                    id="cli-name"
                    value={clientName}
                    onChange={(e) => setClientName(e.target.value)}
                    required
                    placeholder="Acero del Norte, S.A. de C.V."
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="cli-rfc">RFC (opcional)</Label>
                  <Input
                    id="cli-rfc"
                    value={clientRfc}
                    onChange={(e) => setClientRfc(e.target.value.toUpperCase())}
                    maxLength={13}
                    className="font-mono"
                    placeholder="ABC123456XYZ"
                  />
                </div>
              </div>
            </Surface>
          ) : (
            <Surface title="Empresa proveedora" icon={Storefront}>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1">
                  <Label htmlFor="ven-name">Razón social del proveedor</Label>
                  <Input
                    id="ven-name"
                    value={vendorName}
                    onChange={(e) => setVendorName(e.target.value)}
                    required
                    placeholder="Servicios Especializados, S.A."
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="ven-rfc">RFC del proveedor</Label>
                  <Input
                    id="ven-rfc"
                    value={vendorRfc}
                    onChange={(e) => setVendorRfc(e.target.value.toUpperCase())}
                    maxLength={13}
                    minLength={12}
                    required
                    className="font-mono"
                    placeholder="ABC123456XYZ"
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="ven-persona">Tipo de persona</Label>
                  <select
                    id="ven-persona"
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
                  <Label htmlFor="ven-phone">Teléfono (opcional)</Label>
                  <Input
                    id="ven-phone"
                    type="tel"
                    value={contactPhone}
                    onChange={(e) => setContactPhone(e.target.value)}
                    autoComplete="tel"
                    placeholder="+52 55 1234 5678"
                  />
                </div>
                <div className="space-y-1 sm:col-span-2">
                  <Label htmlFor="ven-parent">Cliente al que pertenece</Label>
                  <select
                    id="ven-parent"
                    value={parentClientId}
                    onChange={(e) => setParentClientId(e.target.value)}
                    required
                    className="h-9 w-full rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-2 text-sm"
                  >
                    <option value="">Selecciona un cliente…</option>
                    {clients.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                        {c.rfc ? ` · ${c.rfc}` : ""}
                      </option>
                    ))}
                  </select>
                  <p className="text-[10px] text-[color:var(--text-tertiary)]">
                    El proveedor verá los documentos REPSE pendientes que ese
                    cliente espera de él.
                  </p>
                </div>
              </div>
            </Surface>
          )}

          {errMsg ? (
            <p className="rounded-md border border-[color:var(--status-error-border)] bg-[color:var(--status-error-bg)] p-3 text-sm text-[color:var(--status-error-text)]">
              {errMsg}
            </p>
          ) : null}

          <div className="flex justify-end">
            <Button type="submit" loading={submitting} size="lg">
              Crear y enviar credenciales
              {!submitting ? (
                <ArrowRight
                  className="h-4 w-4"
                  weight="bold"
                  aria-hidden="true"
                />
              ) : null}
            </Button>
          </div>
        </form>
        )}

        {result ? (
          <div className="space-y-4">
            <div className="rounded-md border border-[color:var(--status-success-border)] bg-[color:var(--status-success-bg)] p-5 shadow-sm">
              <div className="flex items-start gap-3">
                <CheckCircle
                  className="mt-0.5 h-6 w-6 shrink-0 text-[color:var(--status-success-text)]"
                  weight="fill"
                  aria-hidden="true"
                />
                <div className="min-w-0 flex-1">
                  <p className="text-base font-semibold text-[color:var(--status-success-text)]">
                    Credenciales generadas
                  </p>
                  <p className="mt-0.5 text-sm text-[color:var(--text-primary)]">
                    Cuenta creada para <strong>{result.email}</strong> como{" "}
                    <strong>
                      {result.role === "client" ? "cliente" : "proveedor"}
                    </strong>
                    .
                  </p>
                </div>
                <Badge
                  variant={result.email_status === "sent" ? "success" : "warning"}
                >
                  <PaperPlaneTilt
                    className="h-3 w-3"
                    weight="bold"
                    aria-hidden="true"
                  />
                  {result.email_status === "sent"
                    ? "Correo enviado"
                    : `Correo: ${result.email_status}`}
                </Badge>
              </div>
            </div>

            <Surface title="Contraseña temporal" icon={IdentificationCard}>
              <div className="space-y-3 text-sm">
                <div className="rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-page)] p-4">
                  <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                    Se muestra una sola vez — guárdala antes de salir
                  </p>
                  <div className="mt-2 flex items-center justify-between gap-3">
                    <code className="select-all break-all font-mono text-lg font-semibold text-[color:var(--text-primary)]">
                      {result.temp_password}
                    </code>
                    <Button
                      type="button"
                      size="sm"
                      variant={copied ? "default" : "outline"}
                      onClick={copyTempPassword}
                    >
                      <Copy className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
                      {copied ? "Copiada" : "Copiar"}
                    </Button>
                  </div>
                </div>
                <p className="text-xs text-[color:var(--text-tertiary)]">
                  Al entrar con esa contraseña, el sistema le pedirá cambiarla
                  inmediatamente. Si el correo no llegó, mándale la contraseña
                  por WhatsApp y dile que entre en{" "}
                  <code>{result.login_url}</code>.
                </p>
                {result.email_error ? (
                  <p className="rounded-md border border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-bg)] p-3 text-[11px] text-[color:var(--status-warning-text)]">
                    Detalle del correo: {result.email_error}
                  </p>
                ) : null}
              </div>
            </Surface>

            <div className="flex flex-wrap items-center justify-end gap-2">
              <Button asChild size="sm" variant="outline">
                <Link href="/admin/clients">
                  <ArrowLeft className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
                  Volver a clientes
                </Link>
              </Button>
              <Button
                type="button"
                size="sm"
                onClick={() => {
                  setResult(null);
                  setErrMsg(null);
                  setCopied(false);
                  if (typeof window !== "undefined") {
                    window.scrollTo({ top: 0, behavior: "smooth" });
                  }
                }}
              >
                Crear otro usuario
                <ArrowRight className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
              </Button>
            </div>
          </div>
        ) : null}
      </div>
    </PlatformShell>
  );
}

function RoleButton({
  active,
  onClick,
  icon: IconComponent,
  label,
  caption,
}: {
  active: boolean;
  onClick: () => void;
  icon: Icon;
  label: string;
  caption: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={
        "flex max-w-[300px] flex-1 items-start gap-3 rounded-md border p-3 text-left transition " +
        (active
          ? "border-[color:var(--interactive-primary)] bg-[color:var(--surface-brand-muted)]"
          : "border-[color:var(--border-default)] bg-[color:var(--surface-raised)] hover:border-[color:var(--border-strong)]")
      }
    >
      <span
        className={
          "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md " +
          (active
            ? "bg-[color:var(--interactive-primary)] text-[color:var(--text-inverse)]"
            : "bg-[color:var(--surface-sunken)] text-[color:var(--text-secondary)]")
        }
      >
        <IconComponent className="h-4 w-4" weight="bold" aria-hidden="true" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-[color:var(--text-primary)]">
          {label}
        </p>
        <p className="mt-0.5 text-[12px] text-[color:var(--text-secondary)]">
          {caption}
        </p>
      </div>
    </button>
  );
}
