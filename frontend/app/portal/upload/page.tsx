"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft } from "@phosphor-icons/react";

import {
  IntakeWizard,
  type IntakeLockedField,
  type IntakeWizardPrefill,
} from "@/components/checkwise/intake-wizard";
import { PortalAppShell } from "@/components/checkwise/portal/portal-app-shell";
import { UploadWizardSkeleton } from "@/components/checkwise/portal/state-surfaces";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { fetchCurrentSession, type PortalSession } from "@/lib/session/portal";

function PortalUploadInner() {
  const router = useRouter();
  const params = useSearchParams();
  const [session, setSession] = useState<PortalSession | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchCurrentSession().then((current) => {
      if (cancelled) return;
      if (!current) {
        router.replace("/");
        return;
      }
      setSession(current);
    });
    return () => {
      cancelled = true;
    };
  }, [router]);

  const requirementName = params.get("requirement") ?? undefined;
  const requirementCode = params.get("requirement_code") ?? undefined;
  const institutionCode = params.get("institution") ?? undefined;
  const loadType = params.get("load_type") ?? undefined;
  const periodLabel = params.get("period_label") ?? undefined;
  const periodKey = params.get("period_key") ?? undefined;
  // Phase 3 — replacement lineage. The submission-detail page sets
  // ``replaces=<prior_submission_id>`` when the user clicks the
  // "corregir / volver a cargar" CTA. Thread it through to the wizard
  // so the new upload POSTs ``supersedes_submission_id`` and the
  // backend can link the new attempt to the prior one.
  const supersedesSubmissionId = params.get("replaces") ?? undefined;
  // When the user opened the wizard from /portal/onboarding, the
  // success state should send them back there instead of dumping them
  // into the dashboard, so they can continue with the next mandatory
  // document. We thread a successContinue prop into the wizard.
  const cameFromOnboarding = params.get("from") === "onboarding";
  const successContinue = cameFromOnboarding
    ? {
        href: "/portal/onboarding",
        label: "Continuar con tu expediente",
        helper:
          "Vuelve al expediente inicial y sigue con el siguiente documento obligatorio.",
      }
    : undefined;

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
    <PortalAppShell session={session}>
      <main className="mx-auto max-w-7xl space-y-5 px-5 py-6">
        <PageHeader
          eyebrow="Guided upload resolver"
          title="Carga documental"
          description={
            periodLabel
              ? `Estás resolviendo la obligación del periodo ${periodLabel}. Confirmamos contexto, validamos el archivo y te avisamos qué pasa después.`
              : "Resuelve una obligación específica: confirmamos contexto, validamos el archivo y te decimos qué pasa después de subir."
          }
          actions={
            <>
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
            </>
          }
        />
        <IntakeWizard
          prefill={prefill}
          lockedFields={lockedFields}
          successContinue={successContinue}
          supersedesSubmissionId={supersedesSubmissionId}
        />
      </main>
    </PortalAppShell>
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
