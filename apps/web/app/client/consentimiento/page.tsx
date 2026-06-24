"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ShieldCheck } from "@phosphor-icons/react";

import { BrandLogo } from "@/components/checkwise/brand-logo";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { acceptClientLegalConsent } from "@/lib/api/client";
import { readAdminSession } from "@/lib/session/admin";

const DOC_LINK_CLASS =
  "font-medium text-[color:var(--text-brand)] hover:underline";

/**
 * /client/consentimiento — client_admin legal-consent gate (v2+).
 *
 * Standalone screen (NOT wrapped in ClientShell, so the shell's consent
 * gate never redirects it to itself). The shell routes any un-consented
 * client_admin here; on acceptance we POST /client/legal-consent and
 * return them to the dashboard. Mirrors the provider gate on
 * /portal/entra-a-tu-espacio.
 */
export default function ClientConsentimientoPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [accepted, setAccepted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const session = readAdminSession();
    if (!session) {
      router.replace("/login");
      return;
    }
    if (
      !session.roles.includes("client_admin") &&
      !session.roles.includes("platform_admin") &&
      !session.roles.includes("operations_admin")
    ) {
      router.replace("/admin");
      return;
    }
    setReady(true);
  }, [router]);

  async function handleAccept() {
    if (!accepted) {
      setError("Marca la casilla para confirmar que aceptas los avisos legales.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await acceptClientLegalConsent();
      router.replace("/client/dashboard");
    } catch {
      setSubmitting(false);
      setError(
        "No pudimos registrar tu aceptación. Intenta de nuevo en unos segundos.",
      );
    }
  }

  if (!ready) return null;

  return (
    <main className="flex min-h-dvh flex-col bg-[color:var(--surface-page)]">
      <header className="border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)]">
        <div className="mx-auto flex max-w-3xl items-center gap-3 px-5 py-3">
          <BrandLogo size="md" />
          <span className="hidden h-6 w-px bg-[color:var(--border-subtle)] sm:block" />
          <p className="hidden font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-tertiary)] sm:block">
            Espacio del cliente
          </p>
        </div>
      </header>

      <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col justify-center gap-6 px-5 py-12">
        <div className="flex flex-col gap-2">
          <span className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-[color:var(--surface-brand-muted)] text-[color:var(--text-brand)]">
            <ShieldCheck className="h-5 w-5" weight="duotone" aria-hidden="true" />
          </span>
          <h1 className="text-2xl font-semibold tracking-tight text-[color:var(--text-primary)]">
            Actualizamos nuestros documentos legales
          </h1>
          <p className="text-sm text-[color:var(--text-secondary)]">
            Antes de continuar a tu panel necesitamos que confirmes que leíste
            y aceptas la versión vigente de los tres documentos. Tu aceptación
            queda registrada para auditoría.
          </p>
        </div>

        <section
          aria-labelledby="legal-consent-title"
          className="rounded-xl border border-[color:var(--border-default)] bg-[color:var(--surface-sunken)] p-5"
        >
          <h2
            id="legal-consent-title"
            className="text-sm font-semibold text-[color:var(--text-primary)]"
          >
            Avisos legales
          </h2>
          <label className="mt-4 flex items-start gap-3 text-sm text-[color:var(--text-primary)]">
            <Checkbox
              id="client-legal-consent-checkbox"
              checked={accepted}
              onCheckedChange={(value) => setAccepted(value === true)}
              aria-describedby="client-legal-consent-meta"
            />
            <span>
              Acepto el{" "}
              <Link
                href="/legal/privacidad"
                target="_blank"
                rel="noopener"
                className={DOC_LINK_CLASS}
              >
                aviso de privacidad
              </Link>
              , los{" "}
              <Link
                href="/legal/terminos"
                target="_blank"
                rel="noopener"
                className={DOC_LINK_CLASS}
              >
                términos de uso
              </Link>
              {" y el "}
              <Link
                href="/legal/consentimiento"
                target="_blank"
                rel="noopener"
                className={DOC_LINK_CLASS}
              >
                aviso de consentimiento
              </Link>
              {" de CheckWise."}
            </span>
          </label>
          <p
            id="client-legal-consent-meta"
            className="mt-3 text-[11px] text-[color:var(--text-tertiary)]"
          >
            Cada enlace abre el documento en una pestaña nueva. Versión vigente{" "}
            <code className="font-mono">v2</code> · efectiva desde el 3 de junio
            de 2026.
          </p>
          {error ? (
            <Alert variant="error" className="mt-4">
              <AlertTitle>No pudimos continuar</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}
          <div className="mt-5 flex justify-end">
            <Button
              type="button"
              onClick={handleAccept}
              loading={submitting}
              disabled={!accepted}
            >
              Aceptar y continuar
            </Button>
          </div>
        </section>
      </div>
    </main>
  );
}
