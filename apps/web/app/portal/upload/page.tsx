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
import {
  getCalendar,
  type CalendarAcceptedDocument,
} from "@/lib/api/portal";
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
  // Session 3 (2026-05-21) — catalog v2 signal. The calendar's
  // _calendar_upload_href appends ``&v2=1`` when the row carries
  // alternatives. Reading the URL avoids the cost of an extra catalog
  // fetch in v1 mode and gives the wizard a deterministic mode
  // switch.
  const isV2Mode = params.get("v2") === "1";
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

  // Session 3 — when in v2 mode, fetch the calendar to find the
  // matching row's ``accepts_documents`` list. The wizard then renders
  // an alternatives radio picker so the provider can declare which
  // doc type they're submitting (e.g. CFDI vs cédula vs comprobante
  // bancario). v1 mode skips the fetch entirely.
  const [acceptedDocuments, setAcceptedDocuments] = useState<
    CalendarAcceptedDocument[] | null
  >(null);

  useEffect(() => {
    if (!session || !isV2Mode || !requirementCode || !periodKey) {
      setAcceptedDocuments(null);
      return;
    }
    let cancelled = false;
    // Self-audit fix (2026-05-21) — parse the year from the row's
    // ``requirement_code``, NOT from ``period_key``. v2 codes have
    // shape ``REC-<INST>-<YYYY>-<MM>`` (or ``REC-SAT-<YYYY>-04-anual``)
    // where YYYY is the calendar year that contains the slot. The
    // period_key carries the COVERED period — which for January
    // carryover slots (IMSS Jan covers Dec prior year) points to the
    // prior year. Fetching the prior year's catalog would miss the
    // row entirely → empty alternatives list → broken picker.
    const codeParts = requirementCode.split("-");
    const yearFromCode = Number.parseInt(codeParts[2] ?? "", 10);
    const yearFromLabel = periodLabel
      ? Number.parseInt(periodLabel.slice(0, 4), 10)
      : NaN;
    const year =
      Number.isFinite(yearFromCode) && yearFromCode >= 2021
        ? yearFromCode
        : Number.isFinite(yearFromLabel) && yearFromLabel >= 2021
          ? yearFromLabel
          : new Date().getFullYear();
    getCalendar(session, year)
      .then((payload) => {
        if (cancelled) return;
        const row = payload.months
          .flatMap((m) => m.institutions.flatMap((inst) => inst.items))
          .find((item) => item.code === requirementCode);
        // Empty array if the row is missing (e.g. provider hand-edited
        // the URL with an unknown code) — the wizard renders a clear
        // "no alternatives loaded" message rather than half-state.
        setAcceptedDocuments(row?.accepts_documents ?? []);
      })
      .catch(() => {
        // Fetch failure → still show the wizard in v2 mode but with
        // an empty alternatives list. The wizard's render branch
        // surfaces the failure state to the provider.
        if (cancelled) return;
        setAcceptedDocuments([]);
      });
    return () => {
      cancelled = true;
    };
  }, [session, isV2Mode, requirementCode, periodKey, periodLabel]);

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
    // In v2 mode the wizard's alternatives picker drives
    // ``requirement_name``, so don't lock it from the URL — the URL
    // doesn't carry the picked alternative.
    if (requirementName && !isV2Mode) fields.push("requirement_name");
    if (institutionCode) fields.push("institution_code");
    if (loadType) fields.push("load_type");
    if (periodLabel) fields.push("period_code");
    return fields;
  }, [session, requirementName, institutionCode, loadType, periodLabel, isV2Mode]);

  if (!session) {
    return null;
  }

  return (
    <PortalAppShell session={session}>
      <main className="mx-auto max-w-7xl space-y-5 px-5 py-6">
        <PageHeader
          eyebrow="Carga guiada"
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
              {/* Stage 1 (BL-Stage1, 2026-05-20): this back-link button
                  was labeled "Calendario" but routed to /portal/dashboard.
                  Re-targeted to the actual calendar so the label and the
                  destination agree. */}
              <Button asChild variant="outline" size="sm">
                <Link href="/portal/calendar">
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
          acceptedDocuments={isV2Mode ? acceptedDocuments : undefined}
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
