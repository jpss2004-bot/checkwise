"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Warning,
  ArrowRight,
  Calendar,
  CheckCircle,
  CaretLeft,
  CaretRight,
  Eye,
  FileText,
  CircleNotch,
  Lock,
  PencilSimple,
  ShieldCheck,
  CloudArrowUp,
  UserCheck,
} from "@phosphor-icons/react";

import { institutions, loadTypes, requirementGuides, requirements } from "@/lib/api/catalogs";

// Map an institution dropdown ``value`` (e.g. "sat") to the matching
// label used inside ``requirementGuides[].institution`` (e.g. "SAT") so
// the requirement dropdown can be filtered by the currently selected
// institution. The label form is what each guide entry stores; the
// value form is what the form state holds. Falls back to the value
// itself when no match is found, which keeps unknown future codes
// from silently emptying the list.
function requirementsForInstitution(institutionValue: string): string[] {
  const label =
    institutions.find((i) => i.value === institutionValue)?.label ?? institutionValue;
  return requirementGuides
    .filter((guide) => guide.institution === label)
    .map((guide) => guide.name);
}
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { RequirementStatusBadge } from "@/components/checkwise/portal/requirement-status-badge";
import { ValidationSignal } from "@/components/checkwise/validation-summary";
import { GroupedValidationSummary } from "@/components/checkwise/portal/grouped-validation-summary";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  checkDuplicateBySha256,
  type CalendarAcceptedDocument,
  type DuplicateCheck,
  type MatchFeedback,
  type RequirementStatus,
} from "@/lib/api/portal";
import { DocumentStatus } from "@/lib/constants/statuses";
import type { DocumentStateCode } from "@/lib/types";
import { readAdminSession } from "@/lib/session/admin";
import {
  fetchCurrentSession,
  readPortalSession,
  type PortalSession,
} from "@/lib/session/portal";

type SubmissionResponse = {
  submission_id: string;
  document_id: string;
  status: string;
  sha256: string;
  storage_key: string;
  validations: ValidationSignal[];
  validation_events?: Array<{
    event_type: string;
    result: string;
    severity: string;
    message?: string | null;
    confidence?: number | null;
  }>;
  inspection?: {
    is_pdf: boolean;
    is_corrupt: boolean;
    is_encrypted: boolean;
    page_count: number | null;
    text_char_count: number;
    has_text: boolean;
    is_probably_scanned: boolean;
  } | null;
  document_signals?: {
    detected_institution?: string | null;
    detected_document_type?: string | null;
    detected_rfcs: string[];
    detected_dates: string[];
    period_mentions: string[];
    requirement_match_confidence?: number | null;
    mismatch_reason?: string | null;
    anomaly_codes: string[];
  } | null;
  /** Soft match feedback (2026-06-11). Non-null = "this file probably
   *  isn't the requested document" — informational only; the upload is
   *  accepted and queued for normal review. Never blocks. */
  match_feedback?: MatchFeedback | null;
  message: string;
};

/** Per-file match feedback collected from the batch response so the
 *  confirmation view can show a compact warning row next to the file
 *  that triggered it. */
type BatchFileFeedback = {
  filename: string;
  feedback: MatchFeedback;
};

type IntakeForm = {
  client_name: string;
  vendor_name: string;
  vendor_rfc: string;
  contract_reference: string;
  period_code: string;
  load_type: string;
  institution_code: string;
  requirement_name: string;
  comments: string;
  // Canonical IDs introduced by the Reconciliation Patch. Both empty by
  // default; populated by deep-links from the calendar / onboarding and sent
  // to the backend so /submissions can bind to the catalog instead of
  // creating phantom requirements / periods.
  requirement_code: string;
  period_key: string;
};

const steps = ["Contexto", "Requisito", "Upload", "Prevalidación", "Confirmación"];
const maxUploadSizeBytes = 15 * 1024 * 1024;
// Stage 2.7-b — multi-file caps. Must mirror the backend constants in
// ``apps/api/app/api/v1/portal.py::MULTI_FILE_MAX_FILES`` and
// ``MULTI_FILE_TOTAL_BYTES_CAP``.
const MULTI_FILE_MAX_TOTAL_FILES = 5;
const MULTI_FILE_MAX_ADDITIONAL = MULTI_FILE_MAX_TOTAL_FILES - 1; // primary + N annexes
const MULTI_FILE_TOTAL_BYTES_CAP = 30 * 1024 * 1024;

// Provider-portal UX pass (2026-05-25) — every field defaults to an
// empty string. Previously the wizard pre-filled fake-looking values
// (``period_code: "2026-05"``, ``load_type: "mensual"``,
// ``institution_code: "sat"``, ``requirement_name: requirements[5]``)
// so a URL that didn't carry the full context surfaced as "wrong but
// plausible". With the calendar/onboarding/dashboard URL builders
// now threading the full triad, the prefill path is the single
// source of truth; the wizard no longer needs invented defaults.
const initialForm: IntakeForm = {
  client_name: "",
  vendor_name: "",
  vendor_rfc: "",
  contract_reference: "",
  period_code: "",
  load_type: "",
  institution_code: "",
  requirement_name: "",
  comments: "",
  requirement_code: "",
  period_key: "",
};

export type IntakeWizardPrefill = Partial<IntakeForm>;

export type IntakeLockedField = keyof IntakeForm;

/** Replaces the default "Ver mi calendario" success CTA. Used when the
 *  user opened the wizard from a flow that should continue elsewhere
 *  (currently: from /portal/onboarding → "Continuar con tu expediente"). */
export interface IntakeSuccessContinue {
  href: string;
  label: string;
  helper?: string;
}

const LOCKED_FIELD_LABELS: Record<IntakeLockedField, string> = {
  client_name: "Cliente",
  vendor_name: "Proveedor",
  vendor_rfc: "RFC proveedor",
  contract_reference: "Contrato",
  period_code: "Periodo",
  load_type: "Tipo de carga",
  institution_code: "Institución",
  requirement_name: "Requisito",
  comments: "Comentarios",
  // Canonical IDs — carried in state, never rendered as a locked field.
  requirement_code: "Código canónico",
  period_key: "Periodo canónico",
};

const LOCKED_FIELD_SOURCE: Partial<Record<IntakeLockedField, string>> = {
  client_name: "Viene de tu sesión",
  vendor_name: "Viene de tu sesión",
  vendor_rfc: "Viene de tu sesión",
  contract_reference: "Viene de tu sesión",
  period_code: "Viene del calendario",
  load_type: "Viene del expediente o calendario",
  institution_code: "Viene del expediente o calendario",
  requirement_name: "Viene del expediente o calendario",
};

export function IntakeWizard({
  prefill,
  lockedFields,
  successContinue,
  supersedesSubmissionId,
  acceptedDocuments,
  replaceWarning,
}: {
  prefill?: IntakeWizardPrefill;
  lockedFields?: IntakeLockedField[];
  successContinue?: IntakeSuccessContinue;
  /** Phase 3 — when the wizard was opened via the "reupload" CTA on a
   *  rejected / clarification / mismatch / expired submission, this
   *  carries the id of the prior submission so the workspace POST can
   *  include ``supersedes_submission_id``. Backend validates eligibility
   *  + tenancy and writes the replacement audit trail. Ignored on the
   *  legacy /api/v1/submissions path. */
  supersedesSubmissionId?: string;
  /** Session 3 (2026-05-21) — catalog v2 alternatives. Non-undefined
   *  enables alternatives mode: the wizard renders a radio picker
   *  for the provider to declare which acceptable doc type they're
   *  submitting. ``requirement_name`` then flows from the picker, not
   *  from URL/prefill. ``null`` means "still loading"; ``[]`` means
   *  "v2 mode but the catalog fetch failed or the row is unknown" —
   *  the wizard surfaces that explicitly. ``undefined`` (default)
   *  means v1 / legacy behavior. */
  acceptedDocuments?: CalendarAcceptedDocument[] | null;
  /** Audit Tier 1 (2026-06-09) — set to the slot's current state code
   *  when it already holds a settled / in-flight document (``approved`` /
   *  ``in_review`` / ``uploaded``). The wizard then requires an explicit
   *  acknowledgement before the re-upload supersedes it. ``null``
   *  (default) = empty or actionable slot, no warning. */
  replaceWarning?: DocumentStateCode | null;
} = {}) {
  const apiBaseUrl = useMemo(
    () => process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000",
    [],
  );
  const demoModeEnabled = process.env.NEXT_PUBLIC_DEMO_MODE === "true";
  // Stage 2.7-b — multi-file upload feature flag. Mirrors the backend
  // ``settings.MULTI_FILE_UPLOAD_ENABLED`` setting. Default flipped to
  // ON on 2026-05-25 ahead of the first paying pilot because contract
  // + anexo uploads are material for REPSE evidence. Set
  // ``NEXT_PUBLIC_MULTI_FILE_UPLOAD_ENABLED=false`` to roll back to
  // the legacy single-file path without redeploying.
  const multiFileEnabledRaw =
    process.env.NEXT_PUBLIC_MULTI_FILE_UPLOAD_ENABLED !== "false";
  // Session 3 (2026-05-21) — catalog v2 alternatives mode hides the
  // multi-file annex picker. The Stage 2.7-b "primary + annexes"
  // framing implies a hierarchy that doesn't fit v2's peer-evidence
  // semantics (alternatives are independent ways to satisfy the same
  // obligation). A provider who wants to upload "both" simply
  // submits twice — the slot accumulates the alternatives through
  // the compatibility join on the backend.
  const multiFileEnabled = multiFileEnabledRaw && acceptedDocuments === undefined;
  // Session 3 self-audit fix (2026-05-21) — when the wizard mounts
  // in v2 alternatives mode, clear ``requirement_name`` so the v1
  // default ("Opinión de cumplimiento SAT positiva", from
  // ``initialForm``) can't silently carry through to submit. The
  // alternatives radio picker drives the field; until the provider
  // picks, the form holds an empty string and the submit guard below
  // refuses to advance.
  const v2Mode = acceptedDocuments !== undefined;
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<IntakeForm>(() => {
    const base = { ...initialForm, ...(prefill ?? {}) };
    if (v2Mode) {
      base.requirement_name = "";
    }
    // Bug fix (2026-05-21): when a deep-link supplies a
    // ``requirement_code`` (canonical id) but no ``requirement_name``
    // (human label), the spread above would silently fall back to
    // ``initialForm.requirement_name`` — an arbitrary 6th catalog
    // entry — and the wizard would render that wrong document as the
    // selected one. Clearing the name here forces the wizard to
    // either resolve from the local guide catalog (via the existing
    // ``requirementGuide`` effect) or surface an empty selector
    // instead of misleading the provider into uploading against the
    // wrong slot. The canonical ``requirement_code`` is preserved.
    const hasCode = Boolean(prefill?.requirement_code);
    const hasName = Boolean(prefill?.requirement_name);
    if (hasCode && !hasName) {
      base.requirement_name = "";
    }
    return base;
  });
  const [file, setFile] = useState<File | null>(null);
  // Audit Tier 1 — explicit acknowledgement before a re-upload replaces a
  // settled/in-flight document in this slot. Only gates submit when
  // ``replaceWarning`` is set.
  const [replaceAck, setReplaceAck] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  // Stage 2.7-b — additional files (annexes). Empty by default; only
  // populated when the multi-file flag is on AND the user opts to
  // attach more than one document for the same requirement+period.
  const [additionalFiles, setAdditionalFiles] = useState<File[]>([]);
  const [additionalFilesError, setAdditionalFilesError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [result, setResult] = useState<SubmissionResponse | null>(null);
  // Soft match feedback per batch file (2026-06-11). Empty for single
  // uploads (the single path reads ``result.match_feedback`` directly)
  // and for batches where every file matched.
  const [batchFeedback, setBatchFeedback] = useState<BatchFileFeedback[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [unlockedOverride, setUnlockedOverride] = useState(false);
  const [filePreviewUrl, setFilePreviewUrl] = useState<string | null>(null);
  const [duplicateCheck, setDuplicateCheck] = useState<DuplicateCheck | null>(null);
  const [duplicateChecking, setDuplicateChecking] = useState(false);

  const lockedSet = useMemo(() => {
    if (unlockedOverride) return new Set<IntakeLockedField>();
    const effective = (lockedFields ?? []).filter((field) => {
      const value = form[field];
      return typeof value === "string" && value.trim().length > 0;
    });
    return new Set<IntakeLockedField>(effective);
  }, [lockedFields, form, unlockedOverride]);

  // Resolve the requirement guide for the right-side context panel and
  // step 2's "Requisito esperado" card. Two paths:
  //
  //   1. Exact name match in our local catalog (legacy, when the
  //      requirement was picked from the wizard's own dropdown).
  //   2. Synthesize from URL/form context when the name was supplied
  //      from outside the wizard (e.g. /portal/onboarding sends
  //      backend names like "Contrato original y anexos" or
  //      "Acta constitutiva..." which won't match the local catalog).
  //
  // Without (2) the panel always defaulted to requirementGuides[0]
  // (the SAT CSF entry) regardless of what the user clicked, which
  // is exactly the bug the user reported.
  const selectedRequirement = useMemo(() => {
    const exact = requirementGuides.find(
      (requirement) => requirement.name === form.requirement_name,
    );
    if (exact) return exact;
    if (form.requirement_name) {
      const institutionLabel =
        institutions.find((i) => i.value === form.institution_code)?.label ??
        form.institution_code ??
        "—";
      const frequencyLabel =
        loadTypes.find((l) => l.value === form.load_type)?.label ??
        form.load_type ??
        "—";
      return {
        name: form.requirement_name,
        institution: institutionLabel,
        risk: "Alto",
        frequency: frequencyLabel,
        why:
          "Este documento forma parte de tu expediente REPSE. Sigue las " +
          "indicaciones del expediente para asegurarte de subir la versión correcta.",
        validExample:
          "PDF oficial vigente correspondiente al documento solicitado, " +
          "legible y emitido a nombre del proveedor.",
        rejectionCauses: [
          "archivo ilegible o protegido con contraseña",
          "documento de otro proveedor",
          "versión vencida o desactualizada",
        ],
      };
    }
    return requirementGuides[0];
  }, [form.requirement_name, form.institution_code, form.load_type]);

  function updateField(field: keyof IntakeForm, value: string) {
    setForm((current) => {
      const next = { ...current, [field]: value };
      // When the institution changes, snap requirement_name to the first
      // option scoped to the new institution so the dropdown doesn't
      // hold a value from the prior institution's catalog (Jorge
      // feedback 2026-05-21). If the current value is still valid under
      // the new institution we keep it.
      if (field === "institution_code") {
        const scoped = requirementsForInstitution(value);
        if (scoped.length > 0 && !scoped.includes(current.requirement_name)) {
          next.requirement_name = scoped[0]!;
        }
      }
      return next;
    });
    setError(null);
  }

  function selectFile(nextFile: File | null) {
    setFileError(null);
    setDuplicateCheck(null);
    // Revoke the previous preview URL before replacing it.
    if (filePreviewUrl) {
      URL.revokeObjectURL(filePreviewUrl);
      setFilePreviewUrl(null);
    }
    if (!nextFile) {
      setFile(null);
      return;
    }
    if (!nextFile.name.toLowerCase().endsWith(".pdf")) {
      setFile(null);
      setFileError("Solo se aceptan archivos PDF en esta fase.");
      return;
    }
    if (nextFile.size === 0) {
      setFile(null);
      setFileError("El archivo está vacío.");
      return;
    }
    if (nextFile.size > maxUploadSizeBytes) {
      setFile(null);
      setFileError("El PDF excede el máximo de 15 MB.");
      return;
    }
    setFile(nextFile);
    setError(null);
    // Generate an in-memory preview URL for the iframe.
    try {
      const url = URL.createObjectURL(nextFile);
      setFilePreviewUrl(url);
    } catch {
      // Older browsers — preview unavailable but upload still works.
      setFilePreviewUrl(null);
    }
    // Re-validate aggregate size now that the primary file changed.
    validateMultiFileAggregate(nextFile, additionalFiles);
    // Fire-and-forget duplicate pre-check against the workspace.
    void runDuplicatePreCheck(nextFile);
  }

  function validateMultiFileAggregate(
    primary: File | null,
    annexes: File[],
  ): boolean {
    if (!multiFileEnabled) {
      setAdditionalFilesError(null);
      return true;
    }
    const total =
      (primary?.size ?? 0) + annexes.reduce((acc, f) => acc + f.size, 0);
    if (total > MULTI_FILE_TOTAL_BYTES_CAP) {
      const cap = MULTI_FILE_TOTAL_BYTES_CAP / (1024 * 1024);
      setAdditionalFilesError(
        `Los archivos suman más de ${cap} MB en total. Reduce el tamaño o sube en varias entregas.`,
      );
      return false;
    }
    setAdditionalFilesError(null);
    return true;
  }

  function addAdditionalFiles(picked: FileList | File[] | null) {
    if (!picked || !multiFileEnabled) return;
    const incoming = Array.from(picked);
    const accepted: File[] = [];
    let rejection: string | null = null;
    for (const candidate of incoming) {
      if (!candidate.name.toLowerCase().endsWith(".pdf")) {
        rejection = "Solo se aceptan archivos PDF en esta fase.";
        continue;
      }
      if (candidate.size === 0) {
        rejection = "Uno de los archivos está vacío.";
        continue;
      }
      if (candidate.size > maxUploadSizeBytes) {
        rejection = "Algún archivo excede el máximo individual de 15 MB.";
        continue;
      }
      accepted.push(candidate);
    }
    const merged = [...additionalFiles, ...accepted].slice(
      0,
      MULTI_FILE_MAX_ADDITIONAL,
    );
    if (
      additionalFiles.length + accepted.length >
      MULTI_FILE_MAX_ADDITIONAL
    ) {
      rejection = `Solo se permiten hasta ${MULTI_FILE_MAX_ADDITIONAL} archivos adicionales por entrega.`;
    }
    setAdditionalFiles(merged);
    if (rejection) {
      setAdditionalFilesError(rejection);
      return;
    }
    validateMultiFileAggregate(file, merged);
  }

  function removeAdditionalFile(index: number) {
    setAdditionalFiles((current) => {
      const next = current.filter((_, idx) => idx !== index);
      validateMultiFileAggregate(file, next);
      return next;
    });
  }

  async function runDuplicatePreCheck(target: File) {
    // Cache-first; fall back to a backend round-trip so the wizard
    // works on a deep-linked refresh where the cache is empty.
    const session = readPortalSession() ?? (await fetchCurrentSession());
    if (!session) return;
    setDuplicateChecking(true);
    try {
      const hash = await sha256OfFile(target);
      const result = await checkDuplicateBySha256(session, hash);
      setDuplicateCheck(result);
    } catch {
      // Pre-check is advisory; failures must not block the provider.
      setDuplicateCheck(null);
    } finally {
      setDuplicateChecking(false);
    }
  }

  // Clean up the preview blob URL on unmount or wizard reset.
  useEffect(() => {
    return () => {
      if (filePreviewUrl) URL.revokeObjectURL(filePreviewUrl);
    };
  }, [filePreviewUrl]);

  async function useDemoFile() {
    setFileError(null);
    setError(null);
    try {
      const response = await fetch("/samples/checkwise-demo-document.pdf");
      if (!response.ok) {
        throw new Error(
          "No pudimos cargar el PDF de muestra. Sube tu propio archivo o intenta de nuevo.",
        );
      }
      const blob = await response.blob();
      selectFile(
        new File([blob], "checkwise-demo-document.pdf", {
          type: "application/pdf",
        }),
      );
    } catch (demoFileError) {
      setFile(null);
      setFileError(
        demoFileError instanceof Error
          ? demoFileError.message
          : "No pudimos cargar el PDF de muestra.",
      );
    }
  }

  function validateStep(targetStep: number): string | null {
    if (targetStep === 0) {
      if (form.client_name.trim().length < 2) {
        return "Captura el cliente para mantener trazabilidad de la evidencia.";
      }
      if (form.vendor_name.trim().length < 2) {
        return "Captura el proveedor que entrega la evidencia.";
      }
      const vendorRfc = form.vendor_rfc.trim();
      if (vendorRfc.length < 12 || vendorRfc.length > 13) {
        return "Captura un RFC de proveedor de 12 o 13 caracteres.";
      }
      if (form.period_code.trim().length < 4) {
        return "Captura el periodo que debe cubrir el documento.";
      }
      // Session 3 self-audit fix (2026-05-21) — block advance in v2
      // alternatives mode until the provider picks a radio. Without
      // this guard, the form's empty ``requirement_name`` (cleared at
      // mount when v2Mode is true) would flow into submit and the
      // backend would receive a blank doc-type label. The picker's
      // own UX surfaces the available alternatives; this is just the
      // structural floor.
      if (v2Mode && acceptedDocuments && acceptedDocuments.length > 0) {
        const picked = form.requirement_name.trim();
        if (!picked) {
          return "Elige qué documento estás subiendo antes de continuar.";
        }
        const validNames = new Set(acceptedDocuments.map((doc) => doc.name));
        if (!validNames.has(picked)) {
          return "Selecciona uno de los documentos aceptados para esta obligación.";
        }
      }
    }

    if (targetStep === 2 && !file) {
      return "Selecciona el PDF de evidencia antes de confirmar la carga.";
    }

    return null;
  }

  function handleContinue() {
    const validationError = validateStep(step);
    if (validationError) {
      setError(validationError);
      return;
    }
    setError(null);
    setStep((current) => current + 1);
  }

  async function handleSubmit(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();

    // Belt-and-suspenders for the replace-warning gate: the submit button
    // is disabled until acknowledged, but a stray Enter key could still
    // fire form submit. Bail out the same way (audit Tier 1).
    if (replaceWarning && !replaceAck) {
      return;
    }

    for (const targetStep of [0, 2]) {
      const validationError = validateStep(targetStep);
      if (validationError) {
        setError(validationError);
        setStep(targetStep);
        return;
      }
    }

    setIsSubmitting(true);
    setResult(null);
    setBatchFeedback([]);
    setError(null);

    const normalizedForm: IntakeForm = {
      ...form,
      client_name: form.client_name.trim(),
      vendor_name: form.vendor_name.trim(),
      vendor_rfc: form.vendor_rfc.trim().toUpperCase(),
      contract_reference: form.contract_reference.trim(),
      period_code: form.period_code.trim(),
      comments: form.comments.trim(),
    };

    // Phase 1 — Tenant-safe upload. When the provider has an authenticated
    // portal session we route through the workspace-scoped endpoint, which
    // derives client/vendor/contract from the backend session and ignores
    // any browser-posted identity. The legacy /api/v1/submissions path is
    // kept for callers without a session (importer, dev workflows, demos
    // that don't log in).
    const session: PortalSession | null =
      readPortalSession() ?? (await fetchCurrentSession());

    const body = new FormData();
    let endpoint: string;
    // Stage 2.7-b — multi-file batch path. Active only when the flag is
    // on, the session is authenticated, and the user attached at least
    // one annex. The legacy single-file path is preserved verbatim for
    // every other case.
    const useBatchEndpoint =
      multiFileEnabled && session !== null && additionalFiles.length > 0;
    if (useBatchEndpoint && session) {
      if (!validateMultiFileAggregate(file, additionalFiles)) {
        setError(
          additionalFilesError ??
            "Los archivos suman más de lo permitido. Reduce el tamaño o sube en varias entregas.",
        );
        setIsSubmitting(false);
        return;
      }
      endpoint = `${apiBaseUrl}/api/v1/portal/workspaces/${session.workspace_id}/submissions/batch`;
      body.set("period_code", normalizedForm.period_code);
      body.set("period_key", normalizedForm.period_key);
      body.set("load_type", normalizedForm.load_type);
      body.set("institution_code", normalizedForm.institution_code);
      body.set("requirement_name", normalizedForm.requirement_name);
      body.set("requirement_code", normalizedForm.requirement_code);
      body.set("comments", normalizedForm.comments);
      body.set("initial_status", DocumentStatus.PENDIENTE_REVISION);
      body.append("files", file as File);
      for (const annex of additionalFiles) {
        body.append("files", annex);
      }
      if (supersedesSubmissionId) {
        body.set("supersedes_submission_id", supersedesSubmissionId);
      }
    } else if (session) {
      endpoint = `${apiBaseUrl}/api/v1/portal/workspaces/${session.workspace_id}/submissions`;
      body.set("period_code", normalizedForm.period_code);
      body.set("period_key", normalizedForm.period_key);
      body.set("load_type", normalizedForm.load_type);
      body.set("institution_code", normalizedForm.institution_code);
      body.set("requirement_name", normalizedForm.requirement_name);
      body.set("requirement_code", normalizedForm.requirement_code);
      body.set("comments", normalizedForm.comments);
      body.set("initial_status", DocumentStatus.PENDIENTE_REVISION);
      body.set("file", file as File);
      // Phase 3 — replacement lineage. Only the workspace endpoint
      // accepts this; the legacy /api/v1/submissions path silently
      // ignores extra fields.
      if (supersedesSubmissionId) {
        body.set("supersedes_submission_id", supersedesSubmissionId);
      }
    } else {
      endpoint = `${apiBaseUrl}/api/v1/submissions`;
      Object.entries(normalizedForm).forEach(([key, value]) => body.set(key, value));
      body.set("initial_status", DocumentStatus.PENDIENTE_REVISION);
      body.set("file", file as File);
    }

    const headers = new Headers();
    if (session) {
      const adminSession = readAdminSession();
      if (adminSession?.access_token) {
        headers.set("Authorization", `Bearer ${adminSession.access_token}`);
      }
      if (session.access_token && session.access_token !== "cookie-managed") {
        headers.set("X-Workspace-Token", session.access_token);
      }
    }

    try {
      const response = await fetch(endpoint, {
        method: "POST",
        body,
        headers,
        credentials: session ? "include" : "same-origin",
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(formatApiError(payload));
      }

      if (useBatchEndpoint) {
        // The batch endpoint returns 1 Submission with N Documents.
        // Map the first document into the SubmissionResponse shape the
        // success view expects, so the existing step-4 confirmation
        // works without a parallel branch. A small banner inside the
        // confirmation view summarizes "+N annexes" so the provider
        // sees that all attached files were accepted.
        type DocumentBatchEntry = {
          document_id: string;
          original_filename: string;
          sha256: string;
          storage_key: string;
          status: string;
          inspection?: SubmissionResponse["inspection"];
          document_signals?: SubmissionResponse["document_signals"];
          validations: ValidationSignal[];
          validation_events?: SubmissionResponse["validation_events"];
          match_feedback?: MatchFeedback | null;
        };
        type MultiSubmissionResponse = {
          submission_id: string;
          status: string;
          documents: DocumentBatchEntry[];
          message: string;
        };
        const batch = (await response.json()) as MultiSubmissionResponse;
        const primary = batch.documents[0];
        const flattenedValidations = batch.documents.flatMap(
          (doc) => doc.validations ?? [],
        );
        const flattenedEvents = batch.documents.flatMap(
          (doc) => doc.validation_events ?? [],
        );
        // Soft match feedback is kept per-file (with the filename) so
        // the confirmation can point at the exact file instead of the
        // flattened primary-document view. Intentionally NOT copied into
        // the flattened result's ``match_feedback`` to avoid rendering
        // the same warning twice.
        setBatchFeedback(
          batch.documents.flatMap((doc) =>
            doc.match_feedback
              ? [{ filename: doc.original_filename, feedback: doc.match_feedback }]
              : [],
          ),
        );
        setResult({
          submission_id: batch.submission_id,
          document_id: primary.document_id,
          status: batch.status,
          sha256: primary.sha256,
          storage_key: primary.storage_key,
          validations: flattenedValidations,
          validation_events: flattenedEvents,
          inspection: primary.inspection ?? null,
          document_signals: primary.document_signals ?? null,
          message:
            batch.message ||
            `Carga recibida con ${batch.documents.length} documentos.`,
        });
      } else {
        setResult((await response.json()) as SubmissionResponse);
      }
      setStep(4);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Error inesperado.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <CardTitle>Intake documental nativo</CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              Cada carga queda ligada a cliente, proveedor, periodo, institución, requisito,
              archivo, validación y revisión humana.
            </p>
          </div>
          <Badge variant="outline">PDF-only</Badge>
        </div>
        <div className="mt-5 grid gap-2 sm:grid-cols-5">
          {steps.map((label, index) => (
            <div
              key={label}
              className={`rounded-md border px-3 py-2 text-xs ${
                index === step
                  ? "border-primary bg-primary text-primary-foreground"
                  : index < step
                    ? "border-[color:var(--status-success-border)] bg-[color:var(--status-success-bg)] text-[color:var(--status-success-text)]"
                    : "border-border bg-white text-muted-foreground"
              }`}
            >
              <span className="font-semibold">{index + 1}.</span> {label}
            </div>
          ))}
        </div>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} data-testid="native-intake-form">
          {step === 0 ? (
            <ContextStep
              form={form}
              updateField={updateField}
              lockedSet={lockedSet}
              canUnlock={(lockedFields?.length ?? 0) > 0}
              unlocked={unlockedOverride}
              onToggleUnlock={() => setUnlockedOverride((current) => !current)}
              acceptedDocuments={acceptedDocuments}
            />
          ) : null}
          {step === 1 ? <RequirementStep requirement={selectedRequirement} /> : null}
          {step === 2 ? (
            <UploadStep
              file={file}
              fileError={fileError}
              onFileSelected={selectFile}
              onUseDemoFile={demoModeEnabled ? useDemoFile : undefined}
              comments={form.comments}
              onCommentsChange={(value) => updateField("comments", value)}
              filePreviewUrl={filePreviewUrl}
              duplicateCheck={duplicateCheck}
              duplicateChecking={duplicateChecking}
              requirement={selectedRequirement}
              multiFileEnabled={multiFileEnabled}
              additionalFiles={additionalFiles}
              additionalFilesError={additionalFilesError}
              onAdditionalFilesAdded={addAdditionalFiles}
              onAdditionalFileRemoved={removeAdditionalFile}
              multiFileMaxAdditional={MULTI_FILE_MAX_ADDITIONAL}
              multiFileTotalBytesCap={MULTI_FILE_TOTAL_BYTES_CAP}
            />
          ) : null}
          {step === 3 ? (
            <PrevalidationStep
              form={form}
              file={file}
              requirement={selectedRequirement}
              duplicateCheck={duplicateCheck}
            />
          ) : null}
          {step === 4 ? (
            <ConfirmationStep
              result={result}
              error={error}
              successContinue={successContinue}
              batchFeedback={batchFeedback}
            />
          ) : null}

          {step === 3 && replaceWarning ? (
            <div
              role="alert"
              className="mt-5 rounded-md border border-amber-300 bg-amber-50 p-4"
            >
              <div className="flex gap-3">
                <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-amber-500 text-white">
                  <Warning className="h-4 w-4" aria-hidden="true" />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-amber-900">
                    {replaceWarning === "approved"
                      ? "Este requisito ya tiene un documento aprobado"
                      : "Este requisito ya tiene un documento en revisión"}
                  </p>
                  <p className="mt-1 text-sm text-amber-900/80">
                    {replaceWarning === "approved"
                      ? "Si subes este archivo, reemplazará al documento aprobado y el requisito volverá a revisión."
                      : "Si subes este archivo, reemplazará al documento que ya está en revisión."}
                  </p>
                  <label className="mt-3 flex items-start gap-2 text-sm font-medium text-amber-900">
                    <Checkbox
                      checked={replaceAck}
                      onCheckedChange={(value) => setReplaceAck(value === true)}
                      className="mt-0.5"
                      aria-label="Confirmar que entiendo el reemplazo"
                    />
                    <span>
                      Entiendo que esto reemplaza el documento actual de este
                      requisito.
                    </span>
                  </label>
                </div>
              </div>
            </div>
          ) : null}

          {error && step !== 4 ? (
            <div
              role="alert"
              className="mt-5 rounded-md border border-amber-300 bg-amber-50 p-4"
            >
              <div className="flex gap-3">
                <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-amber-500 text-white">
                  <Warning className="h-4 w-4" aria-hidden="true" />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-amber-900">
                    {step === 3
                      ? "No pudimos enviar tu documento"
                      : "Revisa este paso antes de continuar"}
                  </p>
                  <p className="mt-1 text-sm text-amber-900/80">{error}</p>
                  {step === 3 ? (
                    <p className="mt-1 text-xs text-amber-900/70">
                      Tu archivo y los datos siguen aquí. Puedes volver a intentarlo.
                    </p>
                  ) : null}
                </div>
              </div>
            </div>
          ) : null}

          <div className="mt-6 flex flex-col gap-3 border-t border-border pt-5 sm:flex-row sm:items-center sm:justify-between">
            <Button
              type="button"
              variant="outline"
              disabled={step === 0 || isSubmitting}
              onClick={() => setStep((current) => Math.max(0, current - 1))}
              className="active:scale-[0.98]"
            >
              <CaretLeft className="h-4 w-4" aria-hidden="true" />
              Atrás
            </Button>

            {step < 3 ? (
              <Button
                type="button"
                data-testid="continue-step"
                onClick={handleContinue}
                className="active:scale-[0.98]"
              >
                Continuar
                <CaretRight className="h-4 w-4" aria-hidden="true" />
              </Button>
            ) : step === 3 ? (
              <Button
                type="submit"
                data-testid="submit-submission"
                disabled={isSubmitting || (!!replaceWarning && !replaceAck)}
                className="active:scale-[0.98]"
              >
                {isSubmitting ? (
                  <CircleNotch className="h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  <CloudArrowUp className="h-4 w-4" aria-hidden="true" />
                )}
                {isSubmitting ? "Enviando…" : "Enviar a revisión"}
              </Button>
            ) : (
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setResult(null);
                  setBatchFeedback([]);
                  setFile(null);
                  setStep(0);
                }}
                className="active:scale-[0.98]"
              >
                Nueva carga
              </Button>
            )}
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function ContextStep({
  form,
  updateField,
  lockedSet,
  canUnlock,
  unlocked,
  onToggleUnlock,
  acceptedDocuments,
}: {
  form: IntakeForm;
  updateField: (field: keyof IntakeForm, value: string) => void;
  lockedSet: Set<IntakeLockedField>;
  canUnlock: boolean;
  unlocked: boolean;
  onToggleUnlock: () => void;
  /** Session 3 (2026-05-21) — catalog v2 alternatives. ``undefined``
   *  means the wizard is in legacy v1 mode (show the free-form
   *  requirement dropdown). ``null`` means v2 mode but the calendar
   *  fetch is still in flight (show a small loading state). ``[]``
   *  means v2 mode but the fetch failed or the URL points at an
   *  unknown row (surface an explicit error). A non-empty array
   *  drives the alternatives radio picker. */
  acceptedDocuments?: CalendarAcceptedDocument[] | null;
}) {
  const v2Mode = acceptedDocuments !== undefined;
  const lockedItems = Array.from(lockedSet);
  const lockedItemDisplay = (field: IntakeLockedField): string => {
    if (field === "load_type") {
      return loadTypes.find((option) => option.value === form.load_type)?.label ?? form.load_type;
    }
    if (field === "institution_code") {
      return (
        institutions.find((option) => option.value === form.institution_code)?.label ??
        form.institution_code
      );
    }
    return form[field] ?? "";
  };

  return (
    <section className="space-y-4">
      <StepHeading title="Contexto regulatorio" />

      {lockedItems.length > 0 ? (
        <div className="rounded-md border border-primary/20 bg-primary/5 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex items-start gap-2">
              <Lock className="mt-0.5 h-4 w-4 text-primary" aria-hidden="true" />
              <div className="min-w-0">
                <p className="text-sm font-semibold text-primary">
                  Contexto bloqueado para evitar errores
                </p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  Estos datos vienen de tu sesión y del calendario REPSE. Si necesitas cambiarlos,
                  desbloquéalos abajo.
                </p>
              </div>
            </div>
          </div>
          <dl className="mt-3 grid gap-2 sm:grid-cols-2">
            {lockedItems.map((field) => (
              <div
                key={field}
                className="rounded-md border border-primary/15 bg-white px-3 py-2"
                data-locked-field={field}
              >
                <dt className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-muted-foreground">
                  <Lock className="h-3 w-3" aria-hidden="true" />
                  {LOCKED_FIELD_LABELS[field]}
                </dt>
                <dd className="mt-0.5 break-words text-sm font-medium text-foreground">
                  {lockedItemDisplay(field)}
                </dd>
                {LOCKED_FIELD_SOURCE[field] ? (
                  <p className="mt-0.5 text-[11px] text-muted-foreground">
                    {LOCKED_FIELD_SOURCE[field]}
                  </p>
                ) : null}
              </div>
            ))}
          </dl>
        </div>
      ) : null}

      {canUnlock ? (
        <button
          type="button"
          onClick={onToggleUnlock}
          className="inline-flex items-center gap-1.5 text-xs font-medium text-primary underline-offset-4 hover:underline"
        >
          <PencilSimple className="h-3 w-3" aria-hidden="true" />
          {unlocked ? "Volver a bloquear el contexto" : "Necesito cambiar algo del contexto"}
        </button>
      ) : null}

      <div className="grid gap-4 md:grid-cols-2">
        {!lockedSet.has("client_name") ? (
          <Field label="Cliente" htmlFor="client_name">
            <Input
              id="client_name"
              value={form.client_name}
              onChange={(event) => updateField("client_name", event.target.value)}
              placeholder="Cliente o filial"
              required
            />
          </Field>
        ) : null}
        {!lockedSet.has("vendor_name") ? (
          <Field label="Proveedor" htmlFor="vendor_name">
            <Input
              id="vendor_name"
              value={form.vendor_name}
              onChange={(event) => updateField("vendor_name", event.target.value)}
              placeholder="Razón social del proveedor"
              required
            />
          </Field>
        ) : null}
        {!lockedSet.has("vendor_rfc") ? (
          <Field label="RFC proveedor" htmlFor="vendor_rfc">
            <Input
              id="vendor_rfc"
              value={form.vendor_rfc}
              onChange={(event) => updateField("vendor_rfc", event.target.value.toUpperCase())}
              placeholder="ABC010203AB1"
              minLength={12}
              maxLength={13}
              required
            />
          </Field>
        ) : null}
        {!lockedSet.has("contract_reference") ? (
          <Field label="Contrato, si aplica" htmlFor="contract_reference">
            <Input
              id="contract_reference"
              value={form.contract_reference}
              onChange={(event) => updateField("contract_reference", event.target.value)}
              placeholder="Referencia interna"
            />
          </Field>
        ) : null}
        {!lockedSet.has("period_code") ? (
          <Field label="Periodo" htmlFor="period_code">
            <Input
              id="period_code"
              value={form.period_code}
              onChange={(event) => updateField("period_code", event.target.value)}
              placeholder="2026-05 / Ene-Abr 2026"
              required
            />
          </Field>
        ) : null}
        {!lockedSet.has("load_type") ? (
          <Field label="Tipo de carga" htmlFor="load_type">
            <Select
              id="load_type"
              value={form.load_type}
              onChange={(event) => updateField("load_type", event.target.value)}
            >
              {loadTypes.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </Field>
        ) : null}
        {!lockedSet.has("institution_code") ? (
          <Field label="Institución" htmlFor="institution_code">
            <Select
              id="institution_code"
              value={form.institution_code}
              onChange={(event) => updateField("institution_code", event.target.value)}
            >
              {institutions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </Field>
        ) : null}
        {/* Session 3 (2026-05-21) — alternatives picker for catalog
            v2 rows. Replaces the free-form requirement dropdown when
            the wizard is opened from a v2 calendar row (?v2=1). The
            provider declares which acceptable doc type they're
            uploading; that becomes ``form.requirement_name`` and
            flows into the submission write path verbatim, so the
            backend records exactly which alternative was satisfied. */}
        {v2Mode ? (
          <AlternativesPicker
            acceptedDocuments={acceptedDocuments ?? null}
            value={form.requirement_name}
            onChange={(name) => updateField("requirement_name", name)}
          />
        ) : !lockedSet.has("requirement_name") ? (
          <Field label="Requisito / documento" htmlFor="requirement_name">
            {(() => {
              // Jorge feedback (2026-05-21, /portal/upload): "En el
              // dropdown menu solo me deben aparecer las opciones acorde
              // a la institución seleccionada." Filter requirements by
              // the currently selected institution; fall back to the
              // full catalog only if filtering would leave nothing
              // (e.g. an institution we don't yet have guides for) so
              // the user still has a usable list.
              const scoped = requirementsForInstitution(form.institution_code);
              const options = scoped.length > 0 ? scoped : requirements;
              const valueOutOfScope =
                form.requirement_name &&
                !options.includes(form.requirement_name);
              return (
                <Select
                  id="requirement_name"
                  value={form.requirement_name}
                  onChange={(event) =>
                    updateField("requirement_name", event.target.value)
                  }
                >
                  {valueOutOfScope ? (
                    <option value={form.requirement_name}>
                      {form.requirement_name}
                    </option>
                  ) : null}
                  {options.map((requirement) => (
                    <option key={requirement} value={requirement}>
                      {requirement}
                    </option>
                  ))}
                </Select>
              );
            })()}
          </Field>
        ) : null}
      </div>
    </section>
  );
}


/**
 * Session 3 (2026-05-21) — catalog v2 alternatives radio picker.
 *
 * Renders one radio button per accepted doc type for a v2 row. The
 * provider picks which doc type they're submitting; that choice
 * becomes the submission's ``requirement_name``. The slot's
 * ``requirement_code`` stays the v2 collapsed code (e.g.
 * ``REC-IMSS-2026-01``); the alternative name disambiguates within
 * that slot at reviewer time.
 *
 * Three states:
 *   - ``null``  → still loading (catalog fetch in flight). Show a
 *     small "Cargando..." block instead of an empty picker.
 *   - ``[]``    → v2 mode but the fetch failed or the URL references
 *     an unknown row. Show an explicit error pointing the provider
 *     back to the calendar.
 *   - ``[...]`` → render the radio picker.
 */
function AlternativesPicker({
  acceptedDocuments,
  value,
  onChange,
}: {
  acceptedDocuments: CalendarAcceptedDocument[] | null;
  value: string;
  onChange: (name: string) => void;
}) {
  if (acceptedDocuments === null) {
    return (
      <div
        className="rounded-md border border-border bg-muted/40 p-4 text-sm text-muted-foreground"
        aria-busy="true"
      >
        Cargando los documentos aceptados para esta obligación…
      </div>
    );
  }
  if (acceptedDocuments.length === 0) {
    return (
      <div
        className="rounded-md border border-destructive/40 bg-destructive/5 p-4 text-sm"
        role="alert"
      >
        <p className="font-medium text-destructive">
          No pudimos cargar los documentos aceptados.
        </p>
        <p className="mt-1 text-muted-foreground">
          Vuelve al{" "}
          <Link
            href="/portal/calendar"
            className="font-medium text-destructive underline"
          >
            calendario
          </Link>{" "}
          y abre esta obligación nuevamente.
        </p>
      </div>
    );
  }
  return (
    <fieldset className="space-y-3">
      <legend className="text-sm font-medium text-[color:var(--text-primary)]">
        ¿Qué documento estás subiendo?
      </legend>
      <p className="text-xs text-muted-foreground">
        Esta obligación se satisface con cualquiera de los siguientes
        comprobantes. Elige el que corresponde al archivo que vas a subir;
        si tienes más de uno, súbelos en entregas separadas.
      </p>
      <div className="space-y-2">
        {acceptedDocuments.map((doc) => {
          const fieldId = `requirement-${doc.name.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}`;
          const isSelected = value === doc.name;
          return (
            <label
              key={doc.name}
              htmlFor={fieldId}
              className={`flex cursor-pointer items-start gap-3 rounded-md border p-3 transition-colors ${
                isSelected
                  ? "border-primary bg-primary/5"
                  : "border-border bg-white hover:bg-muted/40"
              }`}
            >
              <input
                id={fieldId}
                type="radio"
                name="requirement-alternative"
                value={doc.name}
                checked={isSelected}
                onChange={() => onChange(doc.name)}
                className="mt-1"
              />
              <span className="flex-1">
                <span className="block text-sm font-medium text-[color:var(--text-primary)]">
                  {doc.name}
                </span>
                {doc.anatomy ? (
                  <span className="mt-1 block text-xs text-muted-foreground">
                    {doc.anatomy}
                  </span>
                ) : null}
              </span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

function RequirementStep({ requirement }: { requirement: (typeof requirementGuides)[number] }) {
  return (
    <section className="space-y-4">
      <StepHeading title="Requisito esperado" />
      <div className="rounded-md border border-border bg-muted/40 p-5">
        <div className="flex flex-wrap items-center gap-2">
          <Badge>{requirement.institution}</Badge>
          <Badge variant="warning">Riesgo {requirement.risk}</Badge>
          <Badge variant="outline">{requirement.frequency}</Badge>
        </div>
        <h3 className="mt-4 text-xl font-semibold">{requirement.name}</h3>
        <p className="mt-3 text-sm text-muted-foreground">{requirement.why}</p>
        <div className="mt-5 grid gap-4 md:grid-cols-2">
          <div>
            <p className="text-sm font-semibold">Ejemplo válido</p>
            <p className="mt-1 text-sm text-muted-foreground">{requirement.validExample}</p>
          </div>
          <div>
            <p className="text-sm font-semibold">Causas comunes de rechazo</p>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
              {requirement.rejectionCauses.map((cause) => (
                <li key={cause}>{cause}</li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}

function UploadStep({
  file,
  fileError,
  onFileSelected,
  onUseDemoFile,
  comments,
  onCommentsChange,
  filePreviewUrl,
  duplicateCheck,
  duplicateChecking,
  requirement,
  multiFileEnabled,
  additionalFiles,
  additionalFilesError,
  onAdditionalFilesAdded,
  onAdditionalFileRemoved,
  multiFileMaxAdditional,
  multiFileTotalBytesCap,
}: {
  file: File | null;
  fileError: string | null;
  onFileSelected: (file: File | null) => void;
  onUseDemoFile?: () => void;
  comments: string;
  onCommentsChange: (value: string) => void;
  filePreviewUrl: string | null;
  duplicateCheck: DuplicateCheck | null;
  duplicateChecking: boolean;
  requirement: (typeof requirementGuides)[number];
  multiFileEnabled: boolean;
  additionalFiles: File[];
  additionalFilesError: string | null;
  onAdditionalFilesAdded: (picked: FileList | File[] | null) => void;
  onAdditionalFileRemoved: (index: number) => void;
  multiFileMaxAdditional: number;
  multiFileTotalBytesCap: number;
}) {
  return (
    <section className="space-y-4">
      <StepHeading title="Sube el documento" />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-4">
          <label
            htmlFor="native-file"
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              onFileSelected(event.dataTransfer.files?.[0] ?? null);
            }}
            className="flex min-h-[180px] cursor-pointer flex-col items-center justify-center rounded-md border border-dashed border-[color:var(--border-brand)] bg-[color:var(--surface-teal-muted)]/40 p-6 text-center transition-colors hover:bg-[color:var(--surface-teal-muted)]/70"
          >
            <CloudArrowUp className="h-9 w-9 text-[color:var(--text-brand)]" aria-hidden="true" />
            <p className="mt-3 text-sm font-semibold text-[color:var(--text-primary)]">
              Arrastra o selecciona el PDF
            </p>
            <p className="mt-1 text-sm text-[color:var(--text-secondary)]">
              Solo PDF, máximo 15 MB. No subas archivos protegidos con contraseña.
            </p>
            <input
              id="native-file"
              type="file"
              accept=".pdf,application/pdf"
              className="sr-only"
              onChange={(event) =>
                onFileSelected(event.target.files?.[0] ?? null)
              }
            />
          </label>

          {file ? (
            <div className="rounded-md border border-border bg-white p-3 text-sm">
              <div className="flex items-center gap-2 font-medium">
                <FileText className="h-4 w-4 text-primary" aria-hidden="true" />
                {file.name}
              </div>
              <p className="mt-1 text-muted-foreground">
                {Math.ceil(file.size / 1024)} KB
              </p>
            </div>
          ) : null}

          {duplicateChecking ? (
            <div className="flex items-center gap-2 rounded-md border border-border bg-muted/40 p-3 text-xs text-muted-foreground">
              <CircleNotch className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
              Verificando si ya habías subido este mismo archivo…
            </div>
          ) : null}

          {duplicateCheck?.exists ? (
            <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
              <div className="flex items-start gap-2">
                <Warning
                  className="mt-0.5 h-4 w-4 shrink-0 text-amber-700"
                  aria-hidden="true"
                />
                <div className="min-w-0">
                  <p className="font-medium">Ya habías subido este archivo</p>
                  <p className="mt-1 text-xs">
                    Detectamos una carga anterior con el mismo contenido
                    {duplicateCheck.filename ? ` (${duplicateCheck.filename})` : ""}
                    {duplicateCheck.requirement_name
                      ? ` para "${duplicateCheck.requirement_name}"`
                      : ""}
                    {duplicateCheck.status
                      ? ` con estado "${duplicateCheck.status}"`
                      : ""}
                    . Puedes continuar si es a propósito; si no, revisa la carga
                    anterior.
                  </p>
                  {duplicateCheck.submission_id ? (
                    <Link
                      href={`/portal/submissions/${duplicateCheck.submission_id}`}
                      className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-amber-900 underline"
                    >
                      Ver carga anterior
                      <ArrowRight className="h-3 w-3" aria-hidden="true" />
                    </Link>
                  ) : null}
                </div>
              </div>
            </div>
          ) : null}

          {filePreviewUrl ? (
            <div className="overflow-hidden rounded-md border border-border bg-muted/30">
              <div className="flex items-center gap-2 border-b border-border bg-white px-3 py-2 text-xs font-medium text-muted-foreground">
                <Eye className="h-3.5 w-3.5" aria-hidden="true" />
                Vista previa del PDF
              </div>
              <iframe
                src={filePreviewUrl}
                title="Vista previa del PDF seleccionado"
                className="block h-[420px] w-full"
              />
            </div>
          ) : null}

          {/* Stage 2.7-b — additional-files (annex) picker. Flag-gated.
              Sits below the primary dropzone so the single-file flow
              stays the canonical happy path; providers who need to
              attach contract+annex see this section as additive. */}
          {multiFileEnabled ? (
            <section
              className="rounded-md border border-dashed border-border bg-muted/30 p-4"
              aria-label="Archivos adicionales para esta entrega"
            >
              <header className="mb-3 flex flex-col gap-1">
                <p className="text-sm font-semibold text-[color:var(--text-primary)]">
                  ¿Necesitas adjuntar más archivos a esta misma entrega?
                </p>
                <p className="text-xs text-muted-foreground">
                  Para casos como contrato + anexos, sube hasta{" "}
                  {multiFileMaxAdditional} archivos adicionales en PDF. Todos
                  juntos no pueden superar{" "}
                  {Math.round(multiFileTotalBytesCap / (1024 * 1024))} MB.
                </p>
              </header>
              <label
                htmlFor="native-additional-files"
                className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-border bg-white px-3 py-2 text-sm font-medium text-[color:var(--text-primary)] hover:bg-muted/50"
              >
                <CloudArrowUp className="h-4 w-4" aria-hidden="true" />
                Añadir archivos adicionales
              </label>
              <input
                id="native-additional-files"
                type="file"
                accept=".pdf,application/pdf"
                multiple
                className="sr-only"
                onChange={(event) => {
                  onAdditionalFilesAdded(event.target.files);
                  // Reset the input so re-picking the same file fires.
                  event.target.value = "";
                }}
              />
              {additionalFiles.length > 0 ? (
                <ul className="mt-3 divide-y divide-border rounded-md border border-border bg-white">
                  {additionalFiles.map((annex, idx) => (
                    <li
                      key={`${annex.name}-${idx}-${annex.size}`}
                      className="flex items-center justify-between gap-3 px-3 py-2 text-sm"
                    >
                      <div className="flex min-w-0 items-center gap-2">
                        <FileText
                          className="h-4 w-4 shrink-0 text-primary"
                          aria-hidden="true"
                        />
                        <span className="truncate" title={annex.name}>
                          {annex.name}
                        </span>
                        <span className="shrink-0 text-xs text-muted-foreground">
                          {Math.ceil(annex.size / 1024)} KB
                        </span>
                      </div>
                      <button
                        type="button"
                        className="shrink-0 text-xs font-medium text-destructive underline"
                        onClick={() => onAdditionalFileRemoved(idx)}
                        aria-label={`Quitar ${annex.name}`}
                      >
                        Quitar
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
              {additionalFilesError ? (
                <p className="mt-3 text-sm text-destructive">
                  {additionalFilesError}
                </p>
              ) : null}
            </section>
          ) : null}

          {fileError ? (
            <p className="text-sm text-destructive">{fileError}</p>
          ) : null}

          {onUseDemoFile ? (
            <div className="flex flex-col gap-1.5">
              <Button
                type="button"
                variant="outline"
                className="w-fit"
                data-testid="use-demo-pdf"
                onClick={onUseDemoFile}
              >
                <FileText className="h-4 w-4" aria-hidden="true" />
                Usar PDF de muestra
              </Button>
              <p className="text-xs text-muted-foreground">
                Adjunta un PDF de prueba etiquetado como demostración para
                recorrer el flujo sin tu archivo real.
              </p>
            </div>
          ) : null}

          <Field label="Comentarios o aclaraciones" htmlFor="comments">
            <Textarea
              id="comments"
              value={comments}
              onChange={(event) => onCommentsChange(event.target.value)}
              placeholder="Ej. El documento cubre el periodo de mayo 2026; el acuse fue emitido el día..."
            />
          </Field>
        </div>

        <aside className="space-y-3" aria-label="Guía del requisito">
          <RequirementGuideCard requirement={requirement} />
        </aside>
      </div>
    </section>
  );
}

function RequirementGuideCard({
  requirement,
}: {
  requirement: (typeof requirementGuides)[number];
}) {
  return (
    <div className="space-y-3 rounded-md border border-border bg-white p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">{requirement.institution}</Badge>
        <Badge variant="outline">{requirement.frequency}</Badge>
      </div>
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Qué necesitamos
        </p>
        <h3 className="mt-1 text-sm font-semibold">{requirement.name}</h3>
        <p className="mt-1 text-xs text-muted-foreground">{requirement.why}</p>
      </div>
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Ejemplo válido
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          {requirement.validExample}
        </p>
      </div>
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Causas comunes de rechazo
        </p>
        <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-muted-foreground">
          {requirement.rejectionCauses.map((cause) => (
            <li key={cause}>{cause}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function PrevalidationStep({
  form,
  file,
  requirement,
  duplicateCheck,
}: {
  form: IntakeForm;
  file: File | null;
  requirement: (typeof requirementGuides)[number];
  duplicateCheck: DuplicateCheck | null;
}) {
  return (
    <section className="space-y-4">
      <StepHeading title="Revisa antes de enviar" />
      <div className="grid gap-4 md:grid-cols-2">
        <ReviewItem label="Cliente" value={form.client_name || "Pendiente"} />
        <ReviewItem
          label="Proveedor / RFC"
          value={`${form.vendor_name || "Pendiente"} / ${form.vendor_rfc || "-"}`}
        />
        <ReviewItem label="Periodo" value={form.period_code} />
        <ReviewItem label="Requisito" value={requirement.name} />
        <ReviewItem label="Archivo" value={file?.name ?? "Sin archivo"} />
        <ReviewItem label="Estado inicial" value="pendiente_revision" />
      </div>

      {duplicateCheck?.exists ? (
        <div className="rounded-md border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
          <div className="flex items-start gap-2">
            <Warning
              className="mt-0.5 h-4 w-4 shrink-0 text-amber-700"
              aria-hidden="true"
            />
            <div>
              <p className="font-medium">Este archivo ya existe en tu expediente</p>
              <p className="mt-1 text-xs">
                Si es a propósito (re-envío para corregir) puedes continuar. Si no,
                regresa y elige el archivo correcto.
              </p>
            </div>
          </div>
        </div>
      ) : null}

      <div className="rounded-md border border-primary/25 bg-primary/5 p-4">
        <p className="text-xs font-medium uppercase tracking-wide text-primary">
          Lo que sigue al enviar
        </p>
        <ol className="mt-2 space-y-2 text-sm">
          <li className="flex items-start gap-2">
            <ShieldCheck
              className="mt-0.5 h-4 w-4 shrink-0 text-primary"
              aria-hidden="true"
            />
            <span>
              Validamos que el archivo se haya recibido completo, que sea
              un PDF que se pueda leer y que no esté duplicado. Nada se
              aprueba automáticamente.
            </span>
          </li>
          <li className="flex items-start gap-2">
            <UserCheck
              className="mt-0.5 h-4 w-4 shrink-0 text-primary"
              aria-hidden="true"
            />
            <span>
              Pasa a revisión humana del equipo de cumplimiento. La aprobación
              final siempre es humana.
            </span>
          </li>
          <li className="flex items-start gap-2">
            <Calendar
              className="mt-0.5 h-4 w-4 shrink-0 text-primary"
              aria-hidden="true"
            />
            <span>
              Puedes consultar el estado en tu calendario o en el detalle del
              documento cuando termine la revisión.
            </span>
          </li>
        </ol>
      </div>
    </section>
  );
}

function ConfirmationStep({
  result,
  error,
  successContinue,
  batchFeedback,
}: {
  result: SubmissionResponse | null;
  error: string | null;
  successContinue?: IntakeSuccessContinue;
  /** Per-file soft match feedback from the batch endpoint. Empty/absent
   *  for single uploads or when every file matched. */
  batchFeedback?: BatchFileFeedback[];
}) {
  if (error) {
    return (
      <div
        role="alert"
        className="rounded-md border border-amber-300 bg-amber-50 p-5"
      >
        <div className="flex gap-3">
          <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-amber-500 text-white">
            <Warning className="h-4 w-4" aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-amber-900">
              No pudimos enviar tu documento
            </p>
            <p className="mt-1 text-sm text-amber-900/80">{error}</p>
            <p className="mt-1 text-xs text-amber-900/70">
              Tu archivo y los datos siguen aquí. Vuelve al paso anterior para reintentar.
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (!result) {
    return (
      <div className="rounded-md border border-border bg-muted/40 p-4 text-sm text-muted-foreground">
        Envía la carga para ver el resultado de prevalidación.
      </div>
    );
  }

  const isMismatch = Boolean(result.document_signals?.mismatch_reason);
  const isClarification = result.status === DocumentStatus.REQUIERE_ACLARACION;
  const isAttention = isMismatch || isClarification;
  const heroTone = isAttention
    ? "border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-bg)]"
    : "border-[color:var(--status-success-border)] bg-[color:var(--status-success-bg)]";
  const heroIconBg = isAttention
    ? "bg-[color:var(--status-warning-text)] text-[color:var(--text-inverse)]"
    : "bg-[color:var(--status-success-text)] text-[color:var(--text-inverse)]";
  const HeroIcon = isAttention ? Warning : CheckCircle;
  const heroHeadline = isMismatch
    ? "Recibimos tu documento, pero detectamos una posible inconsistencia"
    : isClarification
      ? "Recibimos tu documento, pero necesitamos una aclaración"
      : "Recibimos tu documento";
  const heroSubcopy = isMismatch
    ? "Tu archivo entró al sistema y queda como evidencia, pero el revisor humano lo verá con una alerta. Si subiste el documento equivocado, vuelve a cargar el correcto."
    : isClarification
      ? "El documento entró al sistema, pero el revisor humano necesita más información antes de aprobarlo."
      : "Tu archivo entró al sistema y pasó las prevalidaciones automáticas iniciales. El revisor humano dará el dictamen final.";

  return (
    <section className="space-y-5">
      <div className={`cw-fade-up rounded-md border p-5 ${heroTone}`}>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex gap-3">
            <div
              className={`cw-success-ring mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${heroIconBg}`}
              aria-hidden="true"
            >
              {isAttention ? (
                <HeroIcon className="h-5 w-5" aria-hidden="true" />
              ) : (
                <AnimatedCheck />
              )}
            </div>
            <div className="min-w-0">
              <p className="text-base font-semibold">{heroHeadline}</p>
              <p className="mt-1 text-sm text-muted-foreground">{heroSubcopy}</p>
            </div>
          </div>
          <RequirementStatusBadge status={result.status as RequirementStatus} />
        </div>
      </div>

      {/* Soft match feedback (2026-06-11). Informational only — the
          upload SUCCEEDED and is queued for normal review, so this is a
          warning Alert next to the success hero, never an error and
          never a new blocking state. Renders nothing when the backend
          sent no feedback. */}
      {result.match_feedback ? (
        <Alert variant="warning" className="cw-fade-up">
          <div className="min-w-0">
            <AlertTitle>Revisa el archivo</AlertTitle>
            <AlertDescription>{result.match_feedback.warning_es}</AlertDescription>
          </div>
        </Alert>
      ) : null}
      {batchFeedback && batchFeedback.length > 0 ? (
        <Alert variant="warning" className="cw-fade-up">
          <div className="min-w-0 flex-1">
            <AlertTitle>
              {batchFeedback.length === 1
                ? "Revisa uno de tus archivos"
                : "Revisa algunos de tus archivos"}
            </AlertTitle>
            <ul className="mt-2 space-y-2">
              {batchFeedback.map((entry, idx) => (
                <li
                  key={`${entry.filename}-${idx}`}
                  className="flex items-start gap-2 text-[13px] leading-5"
                >
                  <FileText
                    className="mt-0.5 h-4 w-4 shrink-0"
                    aria-hidden="true"
                  />
                  <span className="min-w-0">
                    <span className="font-semibold break-words">
                      {entry.filename}
                    </span>
                    <span className="opacity-90"> — {entry.feedback.warning_es}</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </Alert>
      ) : null}

      <div className="cw-fade-up rounded-md border border-primary/25 bg-primary/5 p-5">
        <p className="text-xs font-medium uppercase tracking-wide text-primary">
          Lo que sigue
        </p>
        <ol className="cw-stagger mt-3 space-y-3 text-sm">
          <li className="flex items-start gap-3">
            <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
              1
            </span>
            <div>
              <p className="font-medium">Validaciones iniciales</p>
              <p className="text-xs text-muted-foreground">
                Revisamos que el archivo sea un PDF legible, no esté
                duplicado y no esté protegido con contraseña. Ya
                corrieron al recibir tu archivo.
              </p>
            </div>
          </li>
          <li className="flex items-start gap-3">
            <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
              2
            </span>
            <div>
              <p className="font-medium">Revisión humana del equipo de cumplimiento</p>
              <p className="text-xs text-muted-foreground">
                Una persona autorizada decide aprobar, rechazar o pedir aclaración.
                La automatización no aprueba.
              </p>
            </div>
          </li>
          <li className="flex items-start gap-3">
            <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
              3
            </span>
            <div>
              <p className="font-medium">Verás el resultado en tu calendario</p>
              <p className="text-xs text-muted-foreground">
                Si te piden corregir algo, te llevaremos al detalle del documento
                con la razón exacta.
              </p>
            </div>
          </li>
        </ol>
        <div className="mt-5 flex flex-wrap gap-2">
          {successContinue ? (
            <Button asChild className="active:scale-[0.98]">
              <Link href={successContinue.href}>
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
                {successContinue.label}
              </Link>
            </Button>
          ) : (
            <Button asChild className="active:scale-[0.98]">
              <Link href="/portal/dashboard">
                <Calendar className="h-4 w-4" aria-hidden="true" />
                Ver mi calendario
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </Link>
            </Button>
          )}
          <Button asChild variant="outline" className="active:scale-[0.98]">
            <Link href={`/portal/submissions/${result.submission_id}`}>
              <FileText className="h-4 w-4" aria-hidden="true" />
              Ver detalle del documento
            </Link>
          </Button>
        </div>
        {successContinue?.helper && (
          <p className="mt-3 text-xs text-muted-foreground">
            {successContinue.helper}
          </p>
        )}
      </div>

      <GroupedValidationSummary
        validations={result.validations}
        surface="wizard"
      />
    </section>
  );
}

function StepHeading({ title }: { title: string }) {
  return (
    <div className="flex items-center gap-2">
      <ShieldCheck className="h-5 w-5 text-primary" aria-hidden="true" />
      <h2 className="text-lg font-semibold">{title}</h2>
    </div>
  );
}

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
    </div>
  );
}

function ReviewItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border bg-white p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 break-words text-sm font-medium">{value}</p>
    </div>
  );
}

async function sha256OfFile(file: File): Promise<string> {
  const buf = await file.arrayBuffer();
  const hash = await crypto.subtle.digest("SHA-256", buf);
  return Array.from(new Uint8Array(hash))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function formatApiError(payload: unknown): string {
  if (!payload || typeof payload !== "object" || !("detail" in payload)) {
    return "No fue posible registrar la carga.";
  }

  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string") {
    return detail;
  }

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (!item || typeof item !== "object") {
          return null;
        }
        const detailItem = item as { loc?: unknown; msg?: unknown };
        const message = typeof detailItem.msg === "string" ? detailItem.msg : null;
        const location =
          Array.isArray(detailItem.loc)
            ? detailItem.loc.filter((part: unknown): part is string => typeof part === "string").join(" > ")
            : null;
        return [location, message].filter(Boolean).join(": ");
      })
      .filter(Boolean);

    if (messages.length > 0) {
      return messages.join(" · ");
    }
  }

  return "No fue posible registrar la carga.";
}

// Confirmation hero check mark. The path stroke draws in (via the
// .cw-draw-check selector in globals.css) right after the success ring
// pops, giving the moment a real "done" beat without animating layout.
function AnimatedCheck() {
  return (
    <svg
      className="cw-draw-check h-5 w-5"
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        d="M5 12.5 L10 17.5 L19 7.5"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
