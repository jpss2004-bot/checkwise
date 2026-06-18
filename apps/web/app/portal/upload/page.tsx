"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  CalendarBlank,
  CloudArrowUp,
  FileText,
  Info,
} from "@phosphor-icons/react";

import {
  IntakeWizard,
  type IntakeLockedField,
  type IntakeWizardPrefill,
} from "@/components/checkwise/intake-wizard";
import { PortalAppShell } from "@/components/checkwise/portal/portal-app-shell";
import { UploadWizardSkeleton } from "@/components/checkwise/portal/state-surfaces";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import {
  getCalendar,
  getOnboarding,
  getSlotState,
  statusToDocumentStateCode,
  type CalendarAcceptedDocument,
  type OnboardingItem,
} from "@/lib/api/portal";
import type { DocumentStateCode } from "@/lib/types";
import { fetchCurrentSession, type PortalSession } from "@/lib/session/portal";

// Slot states where re-uploading replaces something already settled or
// in flight — the provider should confirm before knocking it back to
// review (audit Tier 1, 2026-06-09). Actionable states (missing /
// rejected / expired …) are where a re-upload is the expected action,
// so they raise no warning.
const REPLACE_WARNING_STATES: ReadonlySet<DocumentStateCode> = new Set([
  "approved",
  "in_review",
  "uploaded",
]);

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
  // CW-07 — the human period label + deadline the calendar threads into the
  // upload URL, so the wizard shows which period the provider is resolving and
  // when it is due. Display-only — not part of the submitted form.
  const periodHuman = params.get("period_human") ?? undefined;
  const deadlineIso = params.get("deadline") ?? undefined;
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
  const [minimumDocuments, setMinimumDocuments] = useState<
    "one" | "all" | null
  >(null);
  // CW-08 — catalog guidance for the requirement being uploaded from the
  // expediente (onboarding). Null until fetched / when not an onboarding flow.
  const [onboardingGuide, setOnboardingGuide] = useState<OnboardingItem | null>(
    null,
  );
  // §3.2 — pending initial-expediente documents, used to turn the
  // no-requirement empty state into a one-click launcher instead of a
  // dead-end bounce.
  const [pendingPicker, setPendingPicker] = useState<OnboardingItem[]>([]);

  useEffect(() => {
    if (!session || !isV2Mode || !requirementCode || !periodKey) {
      setAcceptedDocuments(null);
      setMinimumDocuments(null);
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
        setMinimumDocuments(row?.minimum_documents ?? null);
      })
      .catch(() => {
        // Fetch failure → still show the wizard in v2 mode but with
        // an empty alternatives list. The wizard's render branch
        // surfaces the failure state to the provider.
        if (cancelled) return;
        setAcceptedDocuments([]);
        setMinimumDocuments(null);
      });
    return () => {
      cancelled = true;
    };
  }, [session, isV2Mode, requirementCode, periodKey, periodLabel]);

  // Replace-warning probe: ask the backend what (if anything) currently
  // occupies this slot, so the wizard can confirm before a re-upload
  // supersedes a settled/in-flight document. Non-fatal — on any failure
  // we simply omit the warning rather than block the upload.
  const [replaceWarning, setReplaceWarning] =
    useState<DocumentStateCode | null>(null);
  useEffect(() => {
    if (!session || !requirementCode) {
      setReplaceWarning(null);
      return;
    }
    let cancelled = false;
    getSlotState(session, {
      requirement_code: requirementCode,
      period_key: periodKey,
    })
      .then((slot) => {
        if (cancelled) return;
        if (!slot.current_status) {
          setReplaceWarning(null);
          return;
        }
        const code = statusToDocumentStateCode(slot.current_status);
        setReplaceWarning(REPLACE_WARNING_STATES.has(code) ? code : null);
      })
      .catch(() => {
        if (!cancelled) setReplaceWarning(null);
      });
    return () => {
      cancelled = true;
    };
  }, [session, requirementCode, periodKey]);

  // CW-08 — when opened from the expediente (onboarding), fetch the catalog
  // guidance for this requirement so the upload checklist shows what the
  // document must contain + common errors. Skipped for calendar/recurring.
  useEffect(() => {
    if (!session || !cameFromOnboarding || !requirementCode) {
      setOnboardingGuide(null);
      return;
    }
    let cancelled = false;
    getOnboarding(session)
      .then((payload) => {
        if (cancelled) return;
        const match = payload.sections
          .flatMap((section) => section.items)
          .find((item) => item.code === requirementCode);
        setOnboardingGuide(match ?? null);
      })
      .catch(() => {
        if (!cancelled) setOnboardingGuide(null);
      });
    return () => {
      cancelled = true;
    };
  }, [session, cameFromOnboarding, requirementCode]);

  // §3.2 — when opened WITHOUT a requirement, fetch the pending initial
  // documents so the empty state can offer them as one-click deep links
  // (a launcher) instead of just bouncing the user away. Recurring
  // obligations stay on the calendar (the CTA in the empty state).
  useEffect(() => {
    if (!session || requirementCode) {
      setPendingPicker([]);
      return;
    }
    let cancelled = false;
    getOnboarding(session)
      .then((payload) => {
        if (cancelled) return;
        setPendingPicker(
          payload.sections
            .flatMap((section) => section.items)
            .filter((item) => item.required && item.submission_id === null),
        );
      })
      .catch(() => {
        if (!cancelled) setPendingPicker([]);
      });
    return () => {
      cancelled = true;
    };
  }, [session, requirementCode]);

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
    const fields: IntakeLockedField[] = [
      "client_name",
      "vendor_name",
      "vendor_rfc",
    ];
    if (session.contract_reference) fields.push("contract_reference");
    // In v2 mode the wizard's alternatives picker drives
    // ``requirement_name``, so don't lock it from the URL — the URL
    // doesn't carry the picked alternative.
    if (requirementName && !isV2Mode) fields.push("requirement_name");
    if (institutionCode) fields.push("institution_code");
    if (loadType) fields.push("load_type");
    if (periodLabel) fields.push("period_code");
    return fields;
  }, [
    session,
    requirementName,
    institutionCode,
    loadType,
    periodLabel,
    isV2Mode,
  ]);

  if (!session) {
    // While the session resolves (and before any redirect fires), keep the
    // portal frame visible and show the same skeleton used by the Suspense
    // fallback, so the real fetch wait has a perceptible loading state
    // instead of a blank screen.
    return (
      <main className="mx-auto max-w-7xl space-y-5 px-5 py-6">
        <UploadWizardSkeleton />
      </main>
    );
  }

  // Provider-portal UX pass (2026-05-25) — when /portal/upload is
  // opened without a ``requirement_code`` in the URL, we used to drop
  // the user straight into the wizard with the intake form's hardcoded
  // defaults (sat / mensual / 6th catalog entry) pre-filled. That
  // surfaced as plausible-but-wrong context. Now the page renders a
  // safe empty state that bounces the user to the calendar instead.
  if (!requirementCode) {
    return (
      <PortalAppShell session={session}>
        <main className="mx-auto max-w-3xl space-y-5 px-5 py-6">
          <PageHeader
            eyebrow="Carga guiada"
            title="Carga documental"
            description="Antes de subir un archivo necesitamos saber a qué documento corresponde."
            actions={
              <Button asChild variant="outline" size="sm">
                <Link href="/portal/dashboard">
                  <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                  Volver al inicio
                </Link>
              </Button>
            }
          />
          <section
            className="rounded-xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-6 shadow-sm sm:p-8"
            aria-label="Elige un documento para subir"
          >
            {pendingPicker.length > 0 ? (
              <>
                <header className="mb-4 flex items-start gap-3">
                  <span
                    className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[color:var(--surface-brand-muted)]"
                    aria-hidden="true"
                  >
                    <CloudArrowUp
                      className="h-5 w-5 text-[color:var(--text-brand)]"
                      weight="duotone"
                    />
                  </span>
                  <div className="min-w-0">
                    <h2 className="text-base font-semibold text-[color:var(--text-primary)]">
                      Elige qué documento subir
                    </h2>
                    <p className="mt-1 text-[13px] text-[color:var(--text-secondary)]">
                      Estos son los documentos iniciales que aún te faltan.
                      Elige uno y abrimos la carga con el contexto ya resuelto.
                    </p>
                  </div>
                </header>
                <ul className="space-y-2">
                  {pendingPicker.map((item) => {
                    const params = new URLSearchParams({
                      requirement: item.name,
                      requirement_code: item.code,
                      institution: item.institution,
                      load_type: "alta_inicial",
                      from: "onboarding",
                    });
                    return (
                      <li key={item.code}>
                        <Link
                          href={`/portal/upload?${params.toString()}`}
                          className="group flex items-center gap-3 rounded-lg border border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] px-4 py-3 transition-colors hover:border-[color:var(--border-brand)] hover:bg-[color:var(--surface-brand-muted)]/40"
                        >
                          <FileText
                            className="h-5 w-5 shrink-0 text-[color:var(--text-brand)]"
                            aria-hidden="true"
                          />
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-sm font-medium text-[color:var(--text-primary)]">
                              {item.name}
                            </span>
                            {item.note ? (
                              <span className="block truncate text-xs text-[color:var(--text-tertiary)]">
                                {item.note}
                              </span>
                            ) : null}
                          </span>
                          <ArrowRight
                            className="h-4 w-4 shrink-0 text-[color:var(--text-tertiary)] transition-transform group-hover:translate-x-0.5 group-hover:text-[color:var(--text-brand)]"
                            weight="bold"
                            aria-hidden="true"
                          />
                        </Link>
                      </li>
                    );
                  })}
                </ul>
                <div className="mt-5 border-t border-[color:var(--border-subtle)] pt-4">
                  <p className="text-xs text-[color:var(--text-secondary)]">
                    ¿Buscas una obligación recurrente (IMSS, SAT, INFONAVIT,
                    STPS)? Elígela desde tu calendario.
                  </p>
                  <Button asChild variant="outline" size="sm" className="mt-2">
                    <Link href="/portal/calendar">
                      <CalendarBlank className="h-4 w-4" aria-hidden="true" />
                      Ir al calendario
                    </Link>
                  </Button>
                </div>
              </>
            ) : (
              <>
                <header className="mb-3 flex items-start gap-3">
                  <span
                    className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[color:var(--surface-brand-muted)]"
                    aria-hidden="true"
                  >
                    <CalendarBlank
                      className="h-5 w-5 text-[color:var(--text-brand)]"
                      weight="duotone"
                    />
                  </span>
                  <div className="min-w-0">
                    <h2 className="text-base font-semibold text-[color:var(--text-primary)]">
                      Elige desde dónde subir
                    </h2>
                    <p className="mt-1 text-[13px] text-[color:var(--text-secondary)]">
                      Para que tu archivo quede asignado al cliente, periodo,
                      institución y requisito correctos, elige el documento
                      desde tu calendario (obligaciones recurrentes) o tu
                      expediente (documentos iniciales).
                    </p>
                  </div>
                </header>
                <div className="mt-5 flex flex-wrap items-center justify-end gap-2 border-t border-[color:var(--border-subtle)] pt-4">
                  <Button asChild variant="outline" size="sm">
                    <Link href="/portal/onboarding">Ir al expediente</Link>
                  </Button>
                  <Button asChild size="lg">
                    <Link href="/portal/calendar">
                      <span>Seleccionar desde calendario</span>
                      <ArrowRight
                        className="h-4 w-4"
                        weight="bold"
                        aria-hidden="true"
                      />
                    </Link>
                  </Button>
                </div>
              </>
            )}
          </section>
          <Alert variant="info">
            <AlertTitle>¿Por qué no muestro un formulario?</AlertTitle>
            <AlertDescription>
              Cargar un documento sin contexto puede dejarlo asignado al
              cliente, periodo o institución equivocados. Pasar por el
              calendario te garantiza que el archivo entra al expediente que
              esperas.
            </AlertDescription>
          </Alert>
        </main>
      </PortalAppShell>
    );
  }

  return (
    <PortalAppShell session={session}>
      <main className="mx-auto max-w-7xl space-y-5 px-5 py-6">
        <PageHeader
          eyebrow="Carga guiada"
          title="Carga documental"
          description={
            periodLabel
              ? `Estás resolviendo la obligación del periodo ${periodHuman ?? periodLabel}. Confirmamos contexto, validamos el archivo y te avisamos qué pasa después.`
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
                <Link href="/portal/calendar">
                  <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                  Calendario
                </Link>
              </Button>
            </>
          }
        />
        <UploadContextSummary cameFromOnboarding={cameFromOnboarding} />
        <IntakeWizard
          prefill={prefill}
          lockedFields={lockedFields}
          successContinue={successContinue}
          supersedesSubmissionId={supersedesSubmissionId}
          acceptedDocuments={isV2Mode ? acceptedDocuments : undefined}
          minimumDocuments={isV2Mode ? minimumDocuments : undefined}
          replaceWarning={replaceWarning}
          periodLabel={periodHuman ?? periodLabel}
          deadlineIso={deadlineIso}
          onboardingGuide={onboardingGuide}
          showActaNote={
            session.persona_type === "moral" &&
            !!onboardingGuide &&
            /contrato/i.test(onboardingGuide.name)
          }
        />
      </main>
    </PortalAppShell>
  );
}

function UploadContextSummary({
  cameFromOnboarding,
}: {
  cameFromOnboarding: boolean;
}) {
  const sourceLabel = cameFromOnboarding ? "expediente" : "calendario";
  return (
    <section
      aria-labelledby="upload-context-summary-title"
      className="rounded-xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-5 shadow-sm sm:p-6"
    >
      <header className="flex items-start gap-3">
        <span
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[color:var(--surface-brand-muted)]"
          aria-hidden="true"
        >
          <Info
            className="h-4 w-4 text-[color:var(--text-brand)]"
            weight="duotone"
          />
        </span>
        <div className="min-w-0">
          <h2
            id="upload-context-summary-title"
            className="text-[14px] font-semibold text-[color:var(--text-primary)]"
          >
            Contexto rellenado automáticamente
          </h2>
          <p className="mt-1 text-[12.5px] leading-relaxed text-[color:var(--text-secondary)]">
            Estos datos vienen del documento que seleccionaste en el{" "}
            {sourceLabel}. Así evitamos errores de cliente, periodo, institución
            o requisito.
          </p>
          <p className="mt-1.5 text-[11.5px] text-[color:var(--text-tertiary)]">
            Si esta información no corresponde al documento que quieres subir,
            vuelve al {sourceLabel} y selecciona el requisito correcto.
          </p>
        </div>
      </header>
    </section>
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
