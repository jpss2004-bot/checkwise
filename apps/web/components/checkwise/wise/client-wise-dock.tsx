"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { ArrowRight, PaperPlaneTilt, Sparkle } from "@phosphor-icons/react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  postClientWiseAsk,
  postClientWiseEvent,
  type ClientWiseAskCta,
  type ClientWisePageContext,
} from "@/lib/api/client";
import {
  WiseDockHeader,
  WiseDockShell,
} from "@/components/checkwise/wise/wise-dock-shell";

/**
 * Wise — cliente (buyer) copilot dock.
 *
 * Sibling of ``apps/web/components/checkwise/portal/wise-dock.tsx``.
 * Mounted in ``ClientShell`` so it's available across every
 * ``/client/*`` route the buyer touches (Resumen, Proveedores,
 * Calendario, Entregas, Notificaciones, Metadata, Reportes,
 * Actividad).
 *
 * Architecture differences vs. the portal dock:
 *
 *   • LLM-only conversation. There's no deterministic intent matcher
 *     here — the cliente surface's questions ("¿qué proveedores están
 *     en riesgo?", "¿qué vence este mes?", "¿por qué Cobre está
 *     rojo?") span the whole portfolio, which the keyword router
 *     can't answer without re-implementing the portal's
 *     ``answerIntent`` over a portfolio model. The backend
 *     ``ask_wise_for_client`` already returns instant responses
 *     (Haiku) grounded in the portfolio context, so the
 *     LLM-only path stays under ~1s round-trip in practice.
 *   • No client-side pre-fetch of dashboard/onboarding state. The
 *     backend assembles the portfolio context per call.
 *   • Reuses the same surface-agnostic ``WiseDockShell`` (chrome) +
 *     ``WiseDockHeader`` (default header layout) as the portal dock,
 *     so the two surfaces feel coherent.
 *
 * Phase 5 (2026-06-02) — landed alongside the cliente Reportes
 * redesign as M1 of the 2026-06 user-testing tenant readiness work.
 */

const STORAGE_KEY = "wise.dock.client.collapsed";

const CLIENT_QUICK_QUESTIONS: { id: string; label: string; prompt: string }[] = [
  {
    id: "vendors-at-risk",
    label: "Proveedores en riesgo",
    prompt: "¿Qué proveedores están en riesgo este mes?",
  },
  {
    id: "next-due",
    label: "Próximo a vencer",
    prompt: "¿Qué se vence pronto en mi portafolio?",
  },
  {
    id: "portfolio-status",
    label: "¿Cómo va el portafolio?",
    prompt: "Resúmeme el estado del portafolio en una frase.",
  },
  {
    id: "what-changed",
    label: "¿Qué cambió hoy?",
    prompt: "¿Qué documentos cambiaron de estado en los últimos días?",
  },
];

interface ClientWiseDockProps {
  className?: string;
}

type ChatTurn =
  | { kind: "wise"; id: string; tone: "brand" | "info" | "warning"; body: string; ctaLabel?: string; ctaHref?: string }
  | { kind: "user"; id: string; text: string };

export function ClientWiseDock({ className }: ClientWiseDockProps) {
  const [turns, setTurns] = React.useState<ChatTurn[]>(() => [
    {
      kind: "wise",
      id: "wise-greet-client",
      tone: "brand",
      body: "Hola, soy Wise. Pregúntame lo que quieras sobre el cumplimiento de tu portafolio.",
    },
  ]);
  const [inputValue, setInputValue] = React.useState("");
  const scrollRef = React.useRef<HTMLDivElement | null>(null);
  const pageContext = useDerivedClientPageContext();
  const clientId = useClientIdFromUrl();

  // Auto-scroll to the bottom whenever a new turn lands.
  React.useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [turns]);

  const submitPrompt = React.useCallback(
    (prompt: string) => {
      const trimmed = prompt.trim();
      if (!trimmed) return;
      const userTurnId = `user-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      const userTurn: ChatTurn = { kind: "user", id: userTurnId, text: trimmed };

      void postClientWiseEvent(
        "wise.question_asked",
        {
          route: pageContext.route,
          prompt: trimmed.slice(0, 200),
        },
        { client_id: clientId },
      );

      // Pending bubble so the dock feels responsive while Haiku replies.
      const placeholderId = `wise-pending-${userTurnId}`;
      const placeholder: ChatTurn = {
        kind: "wise",
        id: placeholderId,
        tone: "info",
        body: "Pensando…",
      };
      setTurns((prev) => [...prev, userTurn, placeholder]);

      // No contextual CTAs from the frontend — the backend's nav CTAs
      // cover every cliente surface and contextual CTAs would require
      // a per-page assembler the cliente shell doesn't have yet.
      const ctas: ClientWiseAskCta[] = [];

      postClientWiseAsk(trimmed, ctas, pageContext, { client_id: clientId })
        .then((response) => {
          setTurns((prev) =>
            prev.map((turn) =>
              turn.kind === "wise" && turn.id === placeholderId
                ? {
                    kind: "wise",
                    id: `wise-llm-${userTurnId}`,
                    tone: response.source === "llm" ? "brand" : "info",
                    body: response.body,
                    ctaLabel: response.cta_label ?? undefined,
                    ctaHref: response.cta_href ?? undefined,
                  }
                : turn,
            ),
          );
        })
        .catch(() => {
          setTurns((prev) =>
            prev.map((turn) =>
              turn.kind === "wise" && turn.id === placeholderId
                ? {
                    kind: "wise",
                    id: `wise-error-${userTurnId}`,
                    tone: "warning",
                    body: "Tuve un problema al responder. Intenta de nuevo en un momento.",
                  }
                : turn,
            ),
          );
        });
    },
    [clientId, pageContext],
  );

  return (
    <WiseDockShell
      storageKey={STORAGE_KEY}
      defaultCollapsed={false}
      ariaLabel="Wise — copiloto del portafolio"
      fabAriaLabel="Abrir Wise · Portafolio"
      className={className}
      onFirstRender={() => {
        void postClientWiseEvent(
          "wise.first_render",
          { route: pageContext.route },
          { client_id: clientId },
        );
      }}
      onOpen={() => {
        void postClientWiseEvent(
          "wise.opened",
          { route: pageContext.route },
          { client_id: clientId },
        );
      }}
      onClose={() => {
        void postClientWiseEvent(
          "wise.collapsed",
          { route: pageContext.route },
          { client_id: clientId },
        );
      }}
      renderHeader={(close) => (
        <WiseDockHeader title="Wise" pill="Portafolio" onClose={close} />
      )}
      renderBody={() => <DockBody turns={turns} scrollRef={scrollRef} />}
      renderComposer={() => (
        <DockComposer
          inputValue={inputValue}
          onInputChange={setInputValue}
          onSubmit={(prompt) => {
            submitPrompt(prompt);
            setInputValue("");
          }}
        />
      )}
    />
  );
}

// ─── Body ──────────────────────────────────────────────────────────

const TONE_BAR = {
  brand: "bg-[color:var(--text-teal)]",
  info: "bg-[color:var(--status-info-text)]",
  warning: "bg-[color:var(--status-warning-text)]",
} as const;

function DockBody({
  turns,
  scrollRef,
}: {
  turns: ChatTurn[];
  scrollRef: React.RefObject<HTMLDivElement | null>;
}) {
  return (
    <div ref={scrollRef} className="flex-1 overflow-y-auto px-5 py-4">
      <ul className="space-y-3" aria-live="polite">
        {turns.map((turn) =>
          turn.kind === "wise" ? (
            <li key={turn.id}>
              <article className="relative overflow-hidden rounded-xl border border-white/10 bg-white/[0.04] p-3.5">
                <span
                  aria-hidden="true"
                  className={cn("absolute inset-y-0 left-0 w-1", TONE_BAR[turn.tone])}
                />
                <div className="space-y-2 pl-2">
                  <p className="text-[13px] leading-[1.5] text-white">{turn.body}</p>
                  {turn.ctaLabel && turn.ctaHref ? (
                    <Button
                      asChild
                      size="sm"
                      className="bg-[color:var(--text-teal)] text-[color:var(--surface-brand)] hover:bg-[color:var(--text-teal)]/90"
                    >
                      <Link href={turn.ctaHref}>
                        <span>{turn.ctaLabel}</span>
                        <ArrowRight className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
                      </Link>
                    </Button>
                  ) : null}
                </div>
              </article>
            </li>
          ) : (
            <li key={turn.id} className="flex justify-end">
              <p className="max-w-[78%] rounded-2xl rounded-br-md bg-[color:var(--text-teal)] px-3.5 py-2 text-[13px] leading-snug text-[color:var(--surface-brand)]">
                {turn.text}
              </p>
            </li>
          ),
        )}
      </ul>
    </div>
  );
}

// ─── Composer (quick chips + text input) ──────────────────────────

function DockComposer({
  inputValue,
  onInputChange,
  onSubmit,
}: {
  inputValue: string;
  onInputChange: (value: string) => void;
  onSubmit: (prompt: string) => void;
}) {
  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSubmit(inputValue);
  };
  return (
    <footer className="border-t border-white/10 bg-[color:var(--surface-brand)]/95 px-4 py-3">
      <div className="mb-2 flex flex-wrap gap-1.5">
        {CLIENT_QUICK_QUESTIONS.map((q) => (
          <button
            key={q.id}
            type="button"
            onClick={() => onSubmit(q.prompt)}
            className="inline-flex items-center rounded-full border border-white/15 bg-white/[0.04] px-2.5 py-1 text-[11px] text-white/80 transition-colors hover:border-[color:var(--text-teal)]/60 hover:bg-[color:var(--text-teal)]/15 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--text-teal)]/60"
          >
            {q.label}
          </button>
        ))}
      </div>
      <form onSubmit={handleSubmit} className="flex items-center gap-2">
        <label htmlFor="client-wise-input" className="sr-only">
          Pregúntale a Wise
        </label>
        <input
          id="client-wise-input"
          type="text"
          autoComplete="off"
          value={inputValue}
          onChange={(event) => onInputChange(event.target.value)}
          placeholder="Pregúntale a Wise…"
          className="flex-1 rounded-full border border-white/15 bg-white/[0.06] px-3.5 py-1.5 text-[13px] text-white placeholder:text-white/40 focus:border-[color:var(--text-teal)]/60 focus:outline-none focus:ring-2 focus:ring-[color:var(--text-teal)]/40"
        />
        <button
          type="submit"
          aria-label="Enviar"
          disabled={inputValue.trim().length === 0}
          className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-[color:var(--text-teal)] text-[color:var(--surface-brand)] transition-all hover:bg-[color:var(--text-teal)]/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--text-teal)]/40 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <PaperPlaneTilt className="h-4 w-4" weight="fill" aria-hidden="true" />
        </button>
      </form>
    </footer>
  );
}

// ─── Helpers: page-context + client-id derivation ─────────────────

const CLIENT_PAGE_LABELS: { match: RegExp; label: string }[] = [
  { match: /^\/client\/dashboard$/, label: "Resumen del portafolio" },
  { match: /^\/client\/vendors$/, label: "Proveedores" },
  { match: /^\/client\/vendors\/[^/]+$/, label: "Detalle de proveedor" },
  { match: /^\/client\/calendar$/, label: "Calendario REPSE" },
  { match: /^\/client\/submissions$/, label: "Entregas" },
  { match: /^\/client\/submissions\/[^/]+$/, label: "Detalle de entrega" },
  { match: /^\/client\/notifications$/, label: "Notificaciones" },
  { match: /^\/client\/metadata$/, label: "Metadatos" },
  { match: /^\/client\/reports$/, label: "Reportes" },
  { match: /^\/client\/reports\/[^/]+$/, label: "Reporte" },
  { match: /^\/client\/activity$/, label: "Actividad" },
  { match: /^\/client\/auditoria$/, label: "Auditoría" },
  { match: /^\/client\/buscar$/, label: "Búsqueda" },
  { match: /^\/client\/configuracion$/, label: "Configuración" },
  { match: /^\/client\/onboarding$/, label: "Onboarding del cliente" },
];

function labelForClientRoute(route: string): string {
  for (const entry of CLIENT_PAGE_LABELS) {
    if (entry.match.test(route)) return entry.label;
  }
  return route.startsWith("/client/") ? "Vista del cliente" : route;
}

function useDerivedClientPageContext(): ClientWisePageContext {
  const pathname = usePathname();
  const params = useSearchParams();
  return React.useMemo(() => {
    const route = pathname || "/client";
    const label = labelForClientRoute(route);
    const ctx: ClientWisePageContext = { route, page_label: label };

    // Pull common task ids out of the URL so Wise knows what's on
    // screen without each page having to pass them in.
    const periodKey = params.get("period_key");
    if (periodKey) ctx.period_key = periodKey;

    // Vendor detail page embeds the id in the path.
    const vendorMatch = /^\/client\/vendors\/([^/]+)$/.exec(route);
    if (vendorMatch) ctx.vendor_id = vendorMatch[1];

    // Report editor page embeds the report id in the path.
    const reportMatch = /^\/client\/reports\/([^/]+)$/.exec(route);
    if (reportMatch) ctx.report_id = reportMatch[1];

    return ctx;
  }, [pathname, params]);
}

function useClientIdFromUrl(): string | undefined {
  const params = useSearchParams();
  return params.get("client_id") ?? undefined;
}
