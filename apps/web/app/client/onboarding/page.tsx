"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle,
  IdentificationCard,
  Info,
} from "@phosphor-icons/react";

import { ClientShell } from "../_shell";
import { Surface } from "@/components/checkwise/dashboard/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  getClientProfile,
  updateClientProfile,
  type ClientProfile,
} from "@/lib/api/client";

/**
 * /client/onboarding
 *
 * Junta 2026-05-23 — self-service alta de cliente. El admin
 * pre-carga RFC + email + nombre desde /admin/clients; el
 * client_admin entra aquí para completar el sector, domicilio
 * fiscal, teléfono y notas operativas. La primera vez que se
 * guarda el formulario el backend setea
 * ``onboarding_completed_at`` y el banner del dashboard se apaga.
 *
 * La página NO solicita PDFs (la junta lo definió explícitamente:
 * "No initial PDFs should be required from the client at this
 * stage."). Los documentos se cargan después, por proveedor, en
 * el calendario.
 */

export default function ClientOnboardingPage() {
  const router = useRouter();
  const [profile, setProfile] = useState<ClientProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [responsibleName, setResponsibleName] = useState("");
  const [industry, setIndustry] = useState("");
  const [fiscalAddress, setFiscalAddress] = useState("");
  const [phone, setPhone] = useState("");
  const [notes, setNotes] = useState("");
  // Item 8 — T&C acceptance is required on the first save. Returning
  // visits do not re-prompt (acceptance is already on file via the
  // audit row written when onboarding_completed_at first became set).
  const [termsAccepted, setTermsAccepted] = useState(false);

  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [justSaved, setJustSaved] = useState(false);

  // Initial load: prefill from the admin alta + any prior edits.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    getClientProfile()
      .then((data) => {
        if (cancelled) return;
        setProfile(data);
        setResponsibleName(data.responsible_name ?? "");
        setIndustry(data.industry ?? "");
        setFiscalAddress(data.fiscal_address ?? "");
        setPhone(data.phone ?? "");
        setNotes(data.notes ?? "");
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setLoadError(
          err instanceof Error
            ? err.message
            : "No pudimos cargar los datos de tu cliente.",
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!profile) return;
    setSaving(true);
    setSaveError(null);
    setJustSaved(false);
    try {
      const updated = await updateClientProfile({
        responsible_name: responsibleName.trim() || null,
        industry: industry.trim() || null,
        fiscal_address: fiscalAddress.trim() || null,
        phone: phone.trim() || null,
        notes: notes.trim() || null,
        terms_accepted: termsAccepted,
      });
      setProfile(updated);
      setJustSaved(true);
      // First-time completion → land them on the dashboard so they
      // see the freshly-cleared banner. Subsequent saves (returning
      // visit) keep them on the page so they can refine.
      const wasFirstTime = profile.onboarding_completed_at === null;
      if (wasFirstTime) {
        setTimeout(() => {
          router.push("/client/dashboard");
        }, 1500);
      }
    } catch (err) {
      setSaveError(
        err instanceof Error
          ? err.message
          : "No pudimos guardar tus cambios.",
      );
    } finally {
      setSaving(false);
    }
  }

  const isFirstTime = !!profile && profile.onboarding_completed_at === null;

  return (
    <ClientShell>
      <div className="space-y-6">
        <header className="space-y-3">
          <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-[color:var(--text-tertiary)]">
            <Link
              href="/client/dashboard"
              className="inline-flex items-center gap-1 hover:text-[color:var(--text-primary)]"
            >
              <ArrowLeft className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
              Volver al dashboard
            </Link>
          </div>
          <div className="flex items-start gap-3">
            <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[color:var(--surface-brand-muted)] text-[color:var(--text-brand)]">
              <IdentificationCard
                className="h-5 w-5"
                weight="bold"
                aria-hidden="true"
              />
            </div>
            <div>
              <h1 className="text-2xl font-semibold tracking-tight text-[color:var(--text-primary)]">
                {isFirstTime ? "Termina tu alta" : "Datos de tu empresa"}
              </h1>
              <p className="mt-1 max-w-3xl text-sm text-[color:var(--text-secondary)]">
                {isFirstTime
                  ? "Ya recibimos tu pago y nuestro equipo precargó los datos básicos. Completa estos campos para activar tu portafolio. No te pediremos archivos PDF en este paso."
                  : "Mantén actualizada la información operativa de tu empresa. Estos datos aparecen en los reportes y en el paquete para auditoría."}
              </p>
            </div>
          </div>
        </header>

        {loading ? (
          <Surface title="Cargando" icon={Info}>
            <p className="text-sm text-[color:var(--text-tertiary)]">
              Cargando los datos precargados por el equipo CheckWise…
            </p>
          </Surface>
        ) : loadError ? (
          <Surface title="No pudimos cargar tus datos" icon={Info}>
            <p className="text-sm text-[color:var(--status-error-text)]">
              {loadError}
            </p>
          </Surface>
        ) : profile ? (
          <>
            <Surface title="Datos precargados" icon={Info}>
              <p className="text-xs text-[color:var(--text-tertiary)]">
                Estos campos los precargó nuestro equipo después de tu
                pago. Si algo está mal, escríbenos por WhatsApp o
                correo y lo corregimos.
              </p>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <ReadOnlyField label="Razón social" value={profile.name} />
                <ReadOnlyField label="RFC" value={profile.rfc ?? "—"} mono />
                <ReadOnlyField label="Correo de contacto" value={profile.email ?? "—"} />
                <ReadOnlyField
                  label="Estado del alta"
                  value={
                    profile.onboarding_completed_at
                      ? "Completada"
                      : "Pendiente de completar"
                  }
                >
                  {profile.onboarding_completed_at ? (
                    <Badge variant="success">Lista</Badge>
                  ) : (
                    <Badge variant="warning">Falta tu información</Badge>
                  )}
                </ReadOnlyField>
              </div>
            </Surface>

            <form onSubmit={handleSubmit}>
              <Surface title="Información operativa" icon={IdentificationCard}>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-1">
                    <Label htmlFor="ob-responsible">
                      Responsable de cumplimiento
                    </Label>
                    <Input
                      id="ob-responsible"
                      value={responsibleName}
                      onChange={(e) => setResponsibleName(e.target.value)}
                      placeholder="Nombre del contacto principal"
                      autoComplete="name"
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="ob-industry">
                      Sector o giro principal
                    </Label>
                    <Input
                      id="ob-industry"
                      value={industry}
                      onChange={(e) => setIndustry(e.target.value)}
                      placeholder="Construcción, servicios, manufactura…"
                    />
                  </div>
                  <div className="space-y-1 sm:col-span-2">
                    <Label htmlFor="ob-address">Domicilio fiscal</Label>
                    <Textarea
                      id="ob-address"
                      value={fiscalAddress}
                      onChange={(e) => setFiscalAddress(e.target.value)}
                      placeholder="Calle, número, colonia, alcaldía/municipio, código postal, estado"
                      rows={3}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="ob-phone">Teléfono de contacto</Label>
                    <Input
                      id="ob-phone"
                      type="tel"
                      value={phone}
                      onChange={(e) => setPhone(e.target.value)}
                      placeholder="+52 55 1234 5678"
                      autoComplete="tel"
                    />
                  </div>
                  <div className="space-y-1 sm:col-span-2">
                    <Label htmlFor="ob-notes">Notas para tu equipo</Label>
                    <Textarea
                      id="ob-notes"
                      value={notes}
                      onChange={(e) => setNotes(e.target.value)}
                      placeholder="Cualquier detalle que quieras que el equipo CheckWise tenga a mano (zonas de trabajo, contactos secundarios, observaciones)."
                      rows={3}
                    />
                  </div>
                </div>
                {saveError ? (
                  <p className="mt-3 text-sm text-[color:var(--status-error-text)]">
                    {saveError}
                  </p>
                ) : null}
              </Surface>
            </form>

            {isFirstTime ? (
              <Surface title="Términos y privacidad" icon={Info}>
                <p className="text-sm text-[color:var(--text-secondary)]">
                  Para activar tu portafolio necesitamos que aceptes
                  nuestros términos. Léelos antes de marcar la casilla
                  — son cortos.
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button asChild variant="outline" size="sm">
                    <Link href="/legal/terminos" target="_blank">
                      Términos de uso
                    </Link>
                  </Button>
                  <Button asChild variant="outline" size="sm">
                    <Link href="/legal/privacidad" target="_blank">
                      Aviso de privacidad
                    </Link>
                  </Button>
                  <Button asChild variant="outline" size="sm">
                    <Link href="/legal/consentimiento" target="_blank">
                      Aviso de consentimiento
                    </Link>
                  </Button>
                </div>
                <label className="mt-4 flex items-start gap-2 text-sm text-[color:var(--text-primary)]">
                  <input
                    type="checkbox"
                    checked={termsAccepted}
                    onChange={(e) => setTermsAccepted(e.target.checked)}
                    className="mt-0.5 h-4 w-4 accent-[color:var(--interactive-primary)]"
                  />
                  <span>
                    He leído y acepto los términos de uso, el aviso de
                    privacidad y el aviso de consentimiento de CheckWise.
                  </span>
                </label>
              </Surface>
            ) : null}

            <div className="flex items-center justify-end gap-3">
              {justSaved ? (
                <p
                  className="inline-flex items-center gap-1.5 text-xs font-medium text-[color:var(--status-success-text)]"
                  role="status"
                >
                  <CheckCircle className="h-4 w-4" weight="fill" aria-hidden="true" />
                  Guardado
                </p>
              ) : null}
              <Button
                type="button"
                loading={saving}
                size="lg"
                disabled={
                  saving ||
                  (isFirstTime &&
                    (!termsAccepted ||
                      !responsibleName.trim() ||
                      !fiscalAddress.trim()))
                }
                onClick={(e) => handleSubmit(e as unknown as FormEvent)}
              >
                {isFirstTime ? "Activar mi portafolio" : "Guardar cambios"}
                {!saving ? (
                  <ArrowRight
                    className="h-4 w-4"
                    weight="bold"
                    aria-hidden="true"
                  />
                ) : null}
              </Button>
            </div>
          </>
        ) : null}
      </div>
    </ClientShell>
  );
}

function ReadOnlyField({
  label,
  value,
  mono,
  children,
}: {
  label: string;
  value: string;
  mono?: boolean;
  children?: React.ReactNode;
}) {
  return (
    <div className="space-y-1 rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] p-3">
      <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
        {label}
      </p>
      <div className="flex items-center justify-between gap-2">
        <p
          className={
            "text-sm font-medium text-[color:var(--text-primary)] " +
            (mono ? "font-mono" : "")
          }
        >
          {value}
        </p>
        {children}
      </div>
    </div>
  );
}
