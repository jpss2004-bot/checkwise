/**
 * Wise copilot — deterministic message engine.
 *
 * Pure functions that take the existing portal payloads (dashboard,
 * onboarding, session) and produce a small, ordered list of
 * personalized Spanish suggestions in casual "tú" voice for the
 * Wise dock. Three audience templates, picked automatically:
 *
 *   * "net_new"        — no submissions yet, expediente incomplete.
 *   * "mid_onboarding" — some uploads, expediente still incomplete.
 *   * "mature"         — expediente complete (onboarding_completed_at).
 *
 * No LLM, no fetches, no DOM — these helpers run server-or-client
 * and are trivially unit-testable. Every string is final-form
 * Spanish so callers render them as-is.
 */

import type {
  DashboardPayload,
  DashboardSuggestedAction,
  OnboardingItem,
  OnboardingSummary,
} from "@/lib/api/portal";
import type { PortalSession } from "@/lib/session/portal";

export type WiseAudience = "net_new" | "mid_onboarding" | "mature";

export type WiseMessageTone = "info" | "warning" | "success" | "brand";

/**
 * One renderable bubble inside the Wise dock. ``body`` is the line
 * of copy; everything else is optional context the dock uses to
 * style + link the row.
 */
export type WiseMessage = {
  id: string;
  /** Visual tone — drives the left-bar accent and icon. */
  tone: WiseMessageTone;
  /** 1–2 sentence Spanish body, casual ``tú``. */
  body: string;
  /** Optional CTA label rendered as a small button. */
  ctaLabel?: string;
  /** Where the CTA routes. Same URL convention as the dashboard's
   *  suggested-action hrefs (deep-linked into /portal/upload). */
  ctaHref?: string;
  /** Free-form meta chip rendered above the body — e.g. the
   *  requirement code or period key. */
  meta?: string;
  /** When a suggestion quotes the reviewer's literal note. */
  reviewerNote?: string;
};

/**
 * Classify a workspace into one of the three audience templates.
 *
 * Net-new is the strict zero-uploads case so the empty-state hero
 * always pairs with the right Wise voice; mid-onboarding kicks in
 * the moment the provider uploads anything but hasn't completed
 * onboarding; mature is post-completion.
 */
export function classifyAudience(args: {
  session: PortalSession;
  dashboard: DashboardPayload;
}): WiseAudience {
  const { session, dashboard } = args;
  if (session.onboarding_completed_at !== null) return "mature";
  const hasAnyUpload =
    (dashboard.recent_uploads ?? []).length > 0 ||
    dashboard.document_state_counts.uploaded > 0 ||
    dashboard.document_state_counts.in_review > 0 ||
    dashboard.document_state_counts.approved > 0;
  return hasAnyUpload ? "mid_onboarding" : "net_new";
}

/**
 * Build the ordered message list for the dock. Returns up to
 * ``limit`` items (default 3). Ordering:
 *
 *   1. A single audience-specific welcome/state line.
 *   2. Up to ``limit - 1`` suggestions derived from the existing
 *      ``suggested_actions`` payload, with reviewer notes inlined
 *      when present.
 *
 * If ``suggested_actions`` is empty and the user is already mature
 * + caught up, the welcome line is the only message — that's the
 * "estás al día" moment we want Wise to celebrate.
 */
export function buildWiseMessages(args: {
  session: PortalSession;
  dashboard: DashboardPayload;
  onboarding: OnboardingSummary | null;
  limit?: number;
}): { audience: WiseAudience; messages: WiseMessage[] } {
  const { session, dashboard, onboarding } = args;
  const limit = args.limit ?? 3;
  const audience = classifyAudience({ session, dashboard });
  const messages: WiseMessage[] = [];

  // 1. Welcome line — keyed off audience + workspace state.
  messages.push(welcomeMessage({ session, dashboard, onboarding, audience }));

  // 2. Suggestions from the dashboard's prioritized action list.
  const suggestions = (dashboard.suggested_actions ?? []).slice(
    0,
    Math.max(0, limit - 1),
  );
  for (const action of suggestions) {
    messages.push(suggestionToMessage(action));
  }

  return { audience, messages };
}

// ─── Welcome lines ──────────────────────────────────────────────────

function welcomeMessage(args: {
  session: PortalSession;
  dashboard: DashboardPayload;
  onboarding: OnboardingSummary | null;
  audience: WiseAudience;
}): WiseMessage {
  const { session, dashboard, onboarding, audience } = args;
  const vendorName = friendlyVendorName(session.vendor_name);

  if (audience === "net_new") {
    const firstStep = pickFirstOnboardingStep(onboarding);
    const remaining = onboarding?.summary.total_required ?? null;
    return {
      id: "wise-welcome-net-new",
      tone: "brand",
      body:
        firstStep && remaining
          ? `Hola ${vendorName}. Aún no subes documentos. Empieza con tu ${firstStep.name} — desbloquea ${remaining - 1} obligaciones más de tu expediente inicial.`
          : `Hola ${vendorName}. Aún no subes documentos. Vamos paso a paso: el checklist de abajo tiene las cargas que necesitas para arrancar tu cumplimiento.`,
      ctaLabel: firstStep ? "Subir documento" : undefined,
      // Carry both the canonical code AND the human name so the
      // wizard renders the doc the user actually asked about —
      // without the name the wizard silently defaults to a
      // different requirement (see intake-wizard 2026-05-21 fix).
      ctaHref: firstStep
        ? `/portal/upload?requirement_code=${encodeURIComponent(firstStep.code)}&requirement=${encodeURIComponent(firstStep.name)}&from=onboarding`
        : undefined,
      meta: firstStep?.code,
    };
  }

  if (audience === "mid_onboarding") {
    const needs = dashboard.onboarding_summary.needs_action;
    const inReview = dashboard.onboarding_summary.in_review;
    const pct = dashboard.onboarding_summary.completion_pct;
    if (needs === 0 && inReview > 0) {
      return {
        id: "wise-welcome-mid-review",
        tone: "info",
        body: `${vendorName}, ya enviaste todo tu expediente (${pct}% avanzado). ${inReview} ${inReview === 1 ? "documento está" : "documentos están"} en revisión legal — te aviso cuando se aprueben.`,
      };
    }
    return {
      id: "wise-welcome-mid",
      tone: needs > 0 ? "warning" : "info",
      body:
        needs > 0
          ? `${vendorName}, vas al ${pct}% de tu expediente. Te ${needs === 1 ? "queda" : "quedan"} ${needs} ${needs === 1 ? "documento" : "documentos"} por atender — los listo abajo.`
          : `${vendorName}, vas al ${pct}% de tu expediente. Sigue así — abajo te dejo lo que conviene atender después.`,
    };
  }

  // mature
  const pendingActions = dashboard.suggested_actions.length;
  const compliance = dashboard.semaphore.compliance_pct;
  const matureNeedsAction = dashboard.onboarding_summary.needs_action;
  const matureNext = dashboard.upcoming_deadlines[0] ?? null;
  if (pendingActions === 0) {
    // Phase 2.c (2026-05-21) — the previous "no hay acciones
    // urgentes" copy fired even when ``summary.needs_action`` was
    // > 0, which contradicted the metadata strip ("Por atender: 5").
    // Mature workspaces with recurring obligations that are MISSING
    // produce 0 suggested_actions (the backend suppresses missing-
    // onboarding entries once initial onboarding is closed), but
    // those MISSING items still feed ``summary.needs_action``. Now
    // we name the discrepancy explicitly so Wise + the strip agree.
    if (matureNeedsAction > 0) {
      const deadlineLine = matureNext
        ? ` El próximo vence ${formatDueLine(matureNext.due_in_days)}.`
        : "";
      return {
        id: "wise-welcome-mature-pending",
        tone: "info",
        body: `${vendorName}, tu cumplimiento está al ${compliance}% y tienes ${matureNeedsAction} ${matureNeedsAction === 1 ? "documento pendiente" : "documentos pendientes"} por subir.${deadlineLine} Abre el calendario o pregúntame "¿qué sigue?".`,
        ctaLabel: "Ver calendario",
        ctaHref: "/portal/calendar",
      };
    }
    return {
      id: "wise-welcome-mature-clear",
      tone: "success",
      body: `${vendorName}, tu cumplimiento está al ${compliance}% y no hay acciones urgentes. Te aviso aquí cuando se acerque un vencimiento o un revisor pida algo.`,
    };
  }
  return {
    id: "wise-welcome-mature",
    tone: pendingActions > 2 ? "warning" : "info",
    body: matureNext
      ? `${vendorName}, tienes ${pendingActions} ${pendingActions === 1 ? "tarea pendiente" : "tareas pendientes"} y el próximo vencimiento es ${formatDueLine(matureNext.due_in_days)}. Vamos a por la primera.`
      : `${vendorName}, tienes ${pendingActions} ${pendingActions === 1 ? "tarea pendiente" : "tareas pendientes"}. Vamos a por la primera.`,
  };
}

// ─── Suggestion → message ───────────────────────────────────────────

function suggestionToMessage(action: DashboardSuggestedAction): WiseMessage {
  const tone: WiseMessageTone =
    action.priority === "high"
      ? "warning"
      : action.priority === "medium"
        ? "info"
        : "info";
  return {
    id: `wise-suggestion-${action.id}`,
    tone,
    body: action.body,
    ctaLabel: ctaLabelFor(action),
    ctaHref: action.href,
    meta: action.requirement_code ?? action.period_key ?? undefined,
    reviewerNote: action.reviewer_note ?? undefined,
  };
}

const ACTION_CTA_LABEL: Record<DashboardSuggestedAction["type"], string> = {
  reupload: "Corregir carga",
  clarify: "Responder observación",
  verify_mismatch: "Verificar documento",
  complete_onboarding: "Subir documento",
  upcoming: "Subir documento",
  regularize: "Regularizar",
};

function ctaLabelFor(action: DashboardSuggestedAction): string {
  return ACTION_CTA_LABEL[action.type] ?? "Abrir";
}

// ─── Helpers ────────────────────────────────────────────────────────

/**
 * Pick the first required onboarding doc that's still missing.
 *
 * The onboarding payload is grouped into sections (e.g. "Identidad",
 * "Fiscal"); we walk in catalog order and return the first required
 * + ``pendiente`` slot. Returns null if the payload isn't loaded or
 * the provider has already touched every required doc.
 */
function pickFirstOnboardingStep(
  onboarding: OnboardingSummary | null,
): OnboardingItem | null {
  if (!onboarding) return null;
  for (const section of onboarding.sections) {
    for (const item of section.items) {
      if (!item.required) continue;
      if (item.status === "pendiente") return item;
    }
  }
  return null;
}

/**
 * Strip "S.A. de C.V." style suffixes so Wise can address the
 * provider by a short, conversational name in the welcome line.
 * Falls back to the full name when no obvious suffix matches.
 */
function friendlyVendorName(full: string): string {
  const suffixes = [
    " S.A. DE C.V.",
    " SA DE CV",
    " S DE RL DE CV",
    " S. DE R.L. DE C.V.",
    " S.A.S.",
    " SAS",
    " S.A.",
    " SA",
  ];
  const upper = full.toUpperCase();
  for (const suffix of suffixes) {
    if (upper.endsWith(suffix)) {
      return full.slice(0, full.length - suffix.length).trim();
    }
  }
  return full;
}

function formatDueLine(days: number | null | undefined): string {
  if (days === null || days === undefined) return "próximamente";
  if (days < 0) return `vencido hace ${Math.abs(days)}d`;
  if (days === 0) return "hoy";
  if (days === 1) return "mañana";
  return `en ${days} días`;
}
