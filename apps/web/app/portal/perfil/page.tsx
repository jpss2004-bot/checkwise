"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, IdentificationCard, Sparkle } from "@phosphor-icons/react";

import { ProfileContactForm } from "@/components/checkwise/workspace/profile-contact-form";
import { PortalAppShell } from "@/components/checkwise/portal/portal-app-shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { withPortalSession } from "@/lib/session/with-portal-session";
import type { PortalSession } from "@/lib/session/portal";

/**
 * /portal/perfil
 *
 * Dedicated profile-edit page. Hosts only the editable contact /
 * internal fields (nombre, apellido, teléfono, cargo, canal). The
 * tenant-identity surface lives on ``/portal/entra-a-tu-espacio`` —
 * splitting the two prevents the "Mi espacio / Mi perfil" confusion
 * the 2026-05-25 UX pass flagged.
 *
 * The save CTA reads "Guardar y volver a mi espacio" and routes back
 * to ``/portal/entra-a-tu-espacio`` after a successful PATCH so the
 * provider lands on the workspace summary rather than getting stuck
 * in the form.
 */
function PerfilInner({ session }: { session: PortalSession }) {
  const router = useRouter();

  return (
    <PortalAppShell session={session}>
      <main className="relative min-h-[calc(100dvh-3.5rem)] bg-[color:var(--surface-page)]">
        <div className="mx-auto flex max-w-3xl flex-col gap-6 px-5 py-10 lg:py-14">
          <header className="cw-fade-up flex flex-col gap-2">
            <Badge variant="teal" className="self-start rounded-full px-3 py-1">
              <Sparkle className="h-3 w-3" weight="fill" aria-hidden="true" />
              Mi perfil
            </Badge>
            <h1 className="text-3xl font-semibold tracking-tight text-[color:var(--text-primary)]">
              Edita tu información de contacto
            </h1>
            <p className="max-w-prose text-[15px] text-[color:var(--text-secondary)]">
              Actualiza tu nombre, teléfono, cargo y canal preferido. Estos
              datos solo se usan para que el equipo de CheckWise pueda
              contactarte cuando haya algo que confirmar de tu expediente.
            </p>
          </header>

          <div className="cw-fade-up">
            <Button asChild variant="ghost" size="sm">
              <Link href="/portal/entra-a-tu-espacio">
                <ArrowLeft className="h-4 w-4" weight="bold" aria-hidden="true" />
                <span>Volver a mi espacio</span>
              </Link>
            </Button>
          </div>

          <ProfileContactForm
            session={session}
            onSaved={() => router.push("/portal/entra-a-tu-espacio")}
          />

          <Alert variant="info">
            <AlertTitle className="flex items-center gap-2">
              <IdentificationCard
                className="h-4 w-4"
                weight="bold"
                aria-hidden="true"
              />
              ¿Necesitas corregir RFC o razón social?
            </AlertTitle>
            <AlertDescription>
              Esos campos quedan bloqueados al alta del workspace. Desde tu
              espacio, abre la sección &quot;Solicitar cambio&quot; para
              enviar una corrección que el equipo revisa antes de
              aplicarla.
            </AlertDescription>
          </Alert>
        </div>
      </main>
    </PortalAppShell>
  );
}

export default withPortalSession(PerfilInner);
