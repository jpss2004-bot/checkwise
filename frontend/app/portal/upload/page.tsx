"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { IntakeWizard } from "@/components/checkwise/intake-wizard";
import { ProviderContextBar } from "@/components/checkwise/portal/provider-context-bar";
import { Button } from "@/components/ui/button";
import { readPortalSession, type PortalSession } from "@/lib/portal-session";

function PortalUploadInner() {
  const router = useRouter();
  const params = useSearchParams();
  const [session, setSession] = useState<PortalSession | null>(null);

  useEffect(() => {
    const current = readPortalSession();
    if (!current) {
      router.replace("/");
      return;
    }
    setSession(current);
  }, [router]);

  const prefill = useMemo(() => {
    if (!session) return undefined;
    return {
      client_name: session.client_name,
      vendor_name: session.vendor_name,
      vendor_rfc: session.vendor_rfc,
      contract_reference: session.contract_reference ?? "",
      requirement_name: params.get("requirement") ?? undefined,
      institution_code: params.get("institution") ?? undefined,
      load_type: params.get("load_type") ?? undefined,
    };
  }, [session, params]);

  if (!session) {
    return null;
  }

  const periodLabel = params.get("period_label");

  return (
    <>
      <ProviderContextBar session={session} />
      <main className="mx-auto max-w-7xl space-y-5 px-5 py-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h1 className="text-2xl font-semibold">Carga documental</h1>
            <p className="text-sm text-muted-foreground">
              {periodLabel
                ? `Cargando ${periodLabel}`
                : "Carga el documento que falta para tu expediente o calendario REPSE."}
            </p>
          </div>
          <div className="flex gap-2">
            <Button asChild variant="outline" size="sm">
              <Link href="/portal/onboarding">
                <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                Expediente
              </Link>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link href="/portal/dashboard">
                <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                Calendario
              </Link>
            </Button>
          </div>
        </div>
        <IntakeWizard prefill={prefill} />
      </main>
    </>
  );
}

export default function PortalUploadPage() {
  return (
    <Suspense fallback={null}>
      <PortalUploadInner />
    </Suspense>
  );
}
