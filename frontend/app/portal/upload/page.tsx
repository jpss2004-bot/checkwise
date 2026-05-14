"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import {
  IntakeWizard,
  type IntakeLockedField,
  type IntakeWizardPrefill,
} from "@/components/checkwise/intake-wizard";
import { ProviderContextBar } from "@/components/checkwise/portal/provider-context-bar";
import { UploadWizardSkeleton } from "@/components/checkwise/portal/state-surfaces";
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

  const requirementName = params.get("requirement") ?? undefined;
  const requirementCode = params.get("requirement_code") ?? undefined;
  const institutionCode = params.get("institution") ?? undefined;
  const loadType = params.get("load_type") ?? undefined;
  const periodLabel = params.get("period_label") ?? undefined;
  const periodKey = params.get("period_key") ?? undefined;

  const prefill = useMemo<IntakeWizardPrefill | undefined>(() => {
    if (!session) return undefined;
    return {
      client_name: session.client_name,
      vendor_name: session.vendor_name,
      vendor_rfc: session.vendor_rfc,
      contract_reference: session.contract_reference ?? "",
      ...(requirementName ? { requirement_name: requirementName } : {}),
      ...(requirementCode ? { requirement_code: requirementCode } : {}),
      ...(institutionCode ? { institution_code: institutionCode } : {}),
      ...(loadType ? { load_type: loadType } : {}),
      ...(periodLabel ? { period_code: periodLabel } : {}),
      ...(periodKey ? { period_key: periodKey } : {}),
    };
  }, [
    session,
    requirementName,
    requirementCode,
    institutionCode,
    loadType,
    periodLabel,
    periodKey,
  ]);

  const lockedFields = useMemo<IntakeLockedField[]>(() => {
    if (!session) return [];
    const fields: IntakeLockedField[] = ["client_name", "vendor_name", "vendor_rfc"];
    if (session.contract_reference) fields.push("contract_reference");
    if (requirementName) fields.push("requirement_name");
    if (institutionCode) fields.push("institution_code");
    if (loadType) fields.push("load_type");
    if (periodLabel) fields.push("period_code");
    return fields;
  }, [session, requirementName, institutionCode, loadType, periodLabel]);

  if (!session) {
    return null;
  }

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
        <IntakeWizard prefill={prefill} lockedFields={lockedFields} />
      </main>
    </>
  );
}

export default function PortalUploadPage() {
  return (
    <Suspense
      fallback={
        <main className="mx-auto max-w-7xl space-y-5 px-5 py-6">
          <UploadWizardSkeleton />
        </main>
      }
    >
      <PortalUploadInner />
    </Suspense>
  );
}
