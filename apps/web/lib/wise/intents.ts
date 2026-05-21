/**
 * Wise copilot — intent matcher for the chat interaction.
 *
 * Pure, deterministic, framework-free. Given a free-text user prompt
 * (or the value of a quick-question chip) plus the same payloads the
 * passive dock already reads, classify the intent and produce one
 * short Spanish reply with an optional CTA.
 *
 * No LLM, no embeddings, no network. Compliance products can't ship
 * a copilot that hallucinates an upload URL — the answer is always
 * either a real ``suggested_action`` href, a real ``upcoming_deadline``
 * href, or the empty-state fallback.
 *
 * Intent vocabulary (Phase 2.a):
 *   * "next_action"   — "qué sigue", "qué hago", "siguiente", "ahora",
 *                       "qué debería hacer", "next".
 *   * "rejection"     — "rechaz", "observación", "por qué", "qué pasó",
 *                       "corregir".
 *   * "deadline"      — "vence", "vencimiento", "cuándo", "deadline",
 *                       "fecha".
 *   * "status"        — "estado", "cumplimiento", "estoy", "cómo voy",
 *                       "%".
 *   * "help"          — "ayuda", "hola", "?" — generic greeting.
 *   * "unknown"       — anything else, falls through to next_action.
 */

import type {
  DashboardPayload,
  DashboardSuggestedAction,
  DashboardUpcomingDeadline,
  OnboardingSummary,
} from "@/lib/api/portal";
import type { PortalSession } from "@/lib/session/portal";

import type { WiseMessage, WiseMessageTone } from "./messages";

export type WiseIntent =
  | "next_action"
  | "rejection"
  | "deadline"
  | "status"
  | "help"
  | "unknown";

/**
 * Classify a free-text prompt into one of the Phase 2.a intents.
 *
 * Matching is unicode-aware (strips diacritics first so "qué" and
 * "que" both match) and case-insensitive. Multiple keywords can
 * coexist in one prompt — the order below is the precedence: first
 * match wins, so "por qué está rechazado" routes to ``rejection``
 * rather than ``status`` even though it contains "qué".
 */
export function classifyIntent(prompt: string): WiseIntent {
  const normalized = normalize(prompt);
  if (!normalized) return "help";

  const matchers: { intent: WiseIntent; needles: readonly string[] }[] = [
    {
      intent: "rejection",
      needles: ["rechaz", "observacion", "corregir", "por que", "porque", "que paso"],
    },
    {
      intent: "deadline",
      needles: ["vence", "vencimiento", "deadline", "fecha", "cuando"],
    },
    {
      intent: "next_action",
      needles: [
        "que sigue",
        "que hago",
        "que hacer",
        "que debo",
        "que deberia",
        "siguiente",
        "ahora",
        "que continua",
        "next",
        "next step",
        "next action",
      ],
    },
    {
      intent: "status",
      needles: ["estado", "cumplimiento", "estoy", "como voy", "como estoy", "%"],
    },
    {
      intent: "help",
      needles: ["ayuda", "hola", "?", "help"],
    },
  ];

  for (const { intent, needles } of matchers) {
    for (const needle of needles) {
      if (normalized.includes(needle)) return intent;
    }
  }
  return "unknown";
}

/**
 * Build the Wise reply for a given intent and the current state.
 *
 * Every reply is a single short Spanish line — "directo, breve, en
 * lenguaje humano", with a CTA when there's a concrete next page to
 * land on.
 */
export function answerIntent(args: {
  intent: WiseIntent;
  session: PortalSession;
  dashboard: DashboardPayload;
  onboarding: OnboardingSummary | null;
}): WiseMessage {
  const { intent, dashboard, onboarding, session } = args;
  switch (intent) {
    case "next_action":
    case "unknown":
      return answerNextAction(dashboard, onboarding, session);
    case "rejection":
      return answerRejection(dashboard);
    case "deadline":
      return answerDeadline(dashboard);
    case "status":
      return answerStatus(dashboard);
    case "help":
      return answerHelp(dashboard);
  }
}

// ─── Per-intent answers ─────────────────────────────────────────────

function answerNextAction(
  dashboard: DashboardPayload,
  onboarding: OnboardingSummary | null,
  session: PortalSession,
): WiseMessage {
  const top = dashboard.suggested_actions[0] ?? null;
  if (top) {
    return reply({
      id: `wise-answer-next-${top.id}`,
      tone: top.priority === "high" ? "warning" : "info",
      body: `Tu siguiente paso: ${stripTrailingPunctuation(top.title)}. ${top.body}`,
      ctaLabel: ctaLabelFor(top),
      ctaHref: top.href,
      meta: top.requirement_code ?? top.period_key ?? undefined,
      reviewerNote: top.reviewer_note ?? undefined,
    });
  }
  // No suggested actions — try the onboarding checklist for a
  // first-doc anchor, otherwise celebrate.
  const firstOnboardingStep = pickFirstPendingRequired(onboarding);
  if (firstOnboardingStep) {
    return reply({
      id: "wise-answer-next-onboarding",
      tone: "brand",
      body: `Empieza por subir tu ${firstOnboardingStep.name}. Es uno de los documentos obligatorios de tu expediente.`,
      ctaLabel: "Subir documento",
      // Pass both code and human name so the intake wizard renders
      // the requested document (see intake-wizard 2026-05-21 fix).
      ctaHref: `/portal/upload?requirement_code=${encodeURIComponent(firstOnboardingStep.code)}&requirement=${encodeURIComponent(firstOnboardingStep.name)}&from=onboarding`,
      meta: firstOnboardingStep.code,
    });
  }
  return reply({
    id: "wise-answer-next-clear",
    tone: "success",
    body: `${friendlyVendorName(session.vendor_name)}, no tienes nada urgente. Cuando se acerque un vencimiento o un revisor pida algo, te aviso aquí.`,
  });
}

function answerRejection(dashboard: DashboardPayload): WiseMessage {
  const rejected = dashboard.suggested_actions.find(
    (a) => a.priority === "high" && a.reviewer_note,
  );
  if (rejected) {
    return reply({
      id: `wise-answer-rejection-${rejected.id}`,
      tone: "warning",
      body: `${stripTrailingPunctuation(rejected.title)}. Esto fue lo que pidió el revisor:`,
      ctaLabel: ctaLabelFor(rejected),
      ctaHref: rejected.href,
      meta: rejected.requirement_code ?? rejected.period_key ?? undefined,
      reviewerNote: rejected.reviewer_note ?? undefined,
    });
  }
  // No reviewer-note rejection but there might be a needs-action item
  // anyway (rejected/needs_correction without a persisted note yet).
  const actionable = dashboard.suggested_actions.find((a) => a.priority === "high");
  if (actionable) {
    return reply({
      id: `wise-answer-rejection-noted-${actionable.id}`,
      tone: "warning",
      body: `Tienes un documento por corregir: ${stripTrailingPunctuation(actionable.title)}. ${actionable.body}`,
      ctaLabel: ctaLabelFor(actionable),
      ctaHref: actionable.href,
      meta: actionable.requirement_code ?? actionable.period_key ?? undefined,
    });
  }
  return reply({
    id: "wise-answer-rejection-clear",
    tone: "success",
    body: "No tienes documentos rechazados ni observaciones pendientes ahora mismo.",
  });
}

function answerDeadline(dashboard: DashboardPayload): WiseMessage {
  const next = dashboard.upcoming_deadlines[0] ?? null;
  if (next) {
    return reply({
      id: `wise-answer-deadline-${next.id}`,
      tone:
        next.due_in_days != null && next.due_in_days <= 3
          ? "warning"
          : next.due_in_days != null && next.due_in_days <= 7
            ? "info"
            : "info",
      body: `Tu próximo vencimiento es ${humanDeadline(next)} — ${next.title}.`,
      ctaLabel: "Ver obligación",
      ctaHref: next.href,
      meta: next.period_key ?? undefined,
    });
  }
  return reply({
    id: "wise-answer-deadline-clear",
    tone: "success",
    body: "No tienes vencimientos próximos. Estás cubierto los próximos 30 días.",
  });
}

function answerStatus(dashboard: DashboardPayload): WiseMessage {
  const pct = dashboard.semaphore.compliance_pct;
  const onTrack = dashboard.semaphore.on_track;
  const total = dashboard.semaphore.total_tracked;
  const tone: WiseMessageTone =
    dashboard.semaphore.level === "green"
      ? "success"
      : dashboard.semaphore.level === "yellow"
        ? "info"
        : "warning";
  return reply({
    id: "wise-answer-status",
    tone,
    body: `Tu cumplimiento está al ${pct}% (${onTrack} de ${total} obligaciones al día). ${dashboard.semaphore.reason}`,
  });
}

function answerHelp(dashboard: DashboardPayload): WiseMessage {
  const open = dashboard.suggested_actions.length;
  return reply({
    id: "wise-answer-help",
    tone: "brand",
    body:
      open > 0
        ? `Puedes preguntarme "¿qué sigue?", "¿por qué está rechazado mi documento?" o "¿cuándo vence el próximo?". Tienes ${open} ${open === 1 ? "tarea" : "tareas"} ahora.`
        : 'Puedes preguntarme "¿qué sigue?", "¿cuándo vence el próximo?" o "¿cómo voy?". Por ahora estás al día.',
  });
}

// ─── Quick-question chips ──────────────────────────────────────────

/** Pre-canned questions surfaced as clickable chips above the input.
 *  Each chip submits its ``prompt`` through the same intent pipeline
 *  the free-text input uses — no parallel codepath. */
export type WiseQuickQuestion = {
  id: string;
  label: string;
  prompt: string;
};

export const WISE_QUICK_QUESTIONS: readonly WiseQuickQuestion[] = [
  { id: "qq-next", label: "¿Qué sigue?", prompt: "¿Qué sigue?" },
  {
    id: "qq-rejection",
    label: "¿Por qué está rechazado?",
    prompt: "¿Por qué está rechazado mi documento?",
  },
  {
    id: "qq-deadline",
    label: "¿Cuándo vence el próximo?",
    prompt: "¿Cuándo vence el próximo?",
  },
  { id: "qq-status", label: "¿Cómo voy?", prompt: "¿Cómo voy?" },
] as const;

// ─── Helpers ────────────────────────────────────────────────────────

function reply(message: WiseMessage): WiseMessage {
  return message;
}

function normalize(input: string): string {
  // Lowercase, NFD-decompose, strip combining diacritical marks (U+0300
  // through U+036F) so "qué" matches "que" and "cómo" matches "como"
  // from the keyword tables.
  return input
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .trim();
}

function stripTrailingPunctuation(input: string): string {
  return input.replace(/[.!?¡¿\s]+$/u, "");
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

function pickFirstPendingRequired(
  onboarding: OnboardingSummary | null,
): { code: string; name: string } | null {
  if (!onboarding) return null;
  for (const section of onboarding.sections) {
    for (const item of section.items) {
      if (!item.required) continue;
      if (item.status === "pendiente") return { code: item.code, name: item.name };
    }
  }
  return null;
}

function humanDeadline(next: DashboardUpcomingDeadline): string {
  const days = next.due_in_days;
  if (days == null) return "próximamente";
  if (days < 0) return `vencido hace ${Math.abs(days)} días`;
  if (days === 0) return "hoy";
  if (days === 1) return "mañana";
  return `en ${days} días`;
}

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
