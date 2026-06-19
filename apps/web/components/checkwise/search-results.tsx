"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowRight, MagnifyingGlass } from "@phosphor-icons/react";

import { Badge } from "@/components/ui/badge";
import { SearchInput } from "@/components/ui/search-input";
import { INSTITUTION_LABELS } from "@/lib/api/portal";
import { statusLabel } from "@/lib/constants/statuses";
import type {
  SearchHit,
  SearchMatchType,
  SearchResponse,
} from "@/lib/api/search";

/**
 * Shared search-results surface used by all three role pages
 * (admin/buscar, client/buscar, portal/buscar). Differences across
 * roles are limited to:
 *   - which fetcher runs (passed as ``runSearch``)
 *   - how a row's "open" CTA navigates (``buildHref(hit)``)
 *   - the empty-state copy (``emptyHint``)
 *
 * Everything else (input echo, matched-by tag, status pill, table
 * layout) is shared so the experience reads consistently across roles.
 */
export function SearchResults({
  query,
  runSearch,
  buildHref,
  emptyHint,
  searchPath,
}: {
  query: string;
  runSearch: (q: string) => Promise<SearchResponse>;
  buildHref: (hit: SearchHit) => string;
  emptyHint?: string;
  /** Base path of this portal's search page (e.g. "/admin/buscar"). When set,
   *  an always-visible search box renders above the results so users can search
   *  and refine directly here — critical on mobile, where the header search bar
   *  is hidden. */
  searchPath?: string;
}) {
  const router = useRouter();
  const [draft, setDraft] = useState(query);
  const [data, setData] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Keep the box in sync with the URL-driven query (back/forward, header search).
  useEffect(() => {
    setDraft(query);
  }, [query]);

  useEffect(() => {
    if (!query.trim()) {
      setData({ query: "", matched_by: "folio", total: 0, items: [] });
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    runSearch(query)
      .then((payload) => {
        if (!cancelled) setData(payload);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message ?? "No pudimos buscar.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [query, runSearch]);

  const body = renderBody();

  return (
    <div className="space-y-4">
      {searchPath ? (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const trimmed = draft.trim();
            if (trimmed) {
              router.push(`${searchPath}?q=${encodeURIComponent(trimmed)}`);
            }
          }}
        >
          <SearchInput
            value={draft}
            onValueChange={setDraft}
            placeholder="Buscar por nombre, RFC, folio o periodo…"
            ariaLabel="Buscar por nombre de proveedor, RFC, folio o periodo"
            className="max-w-md"
          />
        </form>
      ) : null}
      {body}
    </div>
  );

  function renderBody() {
    if (!query.trim()) {
      return (
        <EmptyShell hint={emptyHint ?? "Escribe arriba para empezar a buscar."} />
      );
    }
    if (loading) {
      return (
        <p className="text-[13px] text-[color:var(--text-tertiary)]">Buscando…</p>
      );
    }
    if (error) {
      return (
        <div
          role="alert"
          className="rounded-md border border-[color:var(--status-error-border)] bg-[color:var(--status-error-bg)] px-3 py-2 text-[13px] text-[color:var(--status-error-text)]"
        >
          {error}
        </div>
      );
    }
    if (!data || data.total === 0) {
      return (
        <EmptyShell
          hint={`Sin resultados para "${query}". Intenta con el nombre del proveedor, un RFC, un periodo (YYYY-Mxx) o un folio.`}
        />
      );
    }

    return (
      <section aria-label="Resultados de búsqueda" className="space-y-4">
        <header className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <p className="text-[13px] text-[color:var(--text-secondary)]">
            <strong className="text-[color:var(--text-primary)]">
              {data.total}
            </strong>{" "}
            {data.total === 1 ? "resultado" : "resultados"} para
          </p>
          <span className="font-mono text-[12.5px] font-semibold text-[color:var(--text-primary)]">
            “{query}”
          </span>
          <MatchedByPill matched={data.matched_by} />
          {data.items.length < data.total ? (
            <span className="text-[12px] text-[color:var(--text-tertiary)]">
              mostrando los primeros {data.items.length}
            </span>
          ) : null}
        </header>

        <ul className="divide-y divide-[color:var(--border-subtle)] overflow-hidden rounded-lg border border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)]">
          {data.items.map((hit) => (
          <li key={hit.submission_id} className="px-4 py-3">
            <Link
              href={buildHref(hit)}
              className="group flex flex-wrap items-center justify-between gap-3 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)] focus-visible:ring-offset-2"
            >
              <div className="min-w-0 flex-1">
                <p className="text-[14px] font-semibold leading-tight text-[color:var(--text-primary)] group-hover:underline group-focus-visible:underline">
                  {hit.vendor_name}
                </p>
                <p className="mt-0.5 truncate text-[12.5px] text-[color:var(--text-secondary)]">
                  {hit.client_name}
                  {hit.requirement_name ? ` · ${hit.requirement_name}` : ""}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-3 text-[12px] text-[color:var(--text-tertiary)]">
                {hit.period_key ? (
                  <span className="font-mono">{hit.period_key}</span>
                ) : null}
                {hit.institution_code ? (
                  <span className="font-mono uppercase tracking-[0.12em]">
                    {INSTITUTION_LABELS[hit.institution_code] ??
                      hit.institution_code}
                  </span>
                ) : null}
                <StatusPill status={hit.status} />
                <ArrowRight
                  className="h-3.5 w-3.5 text-[color:var(--text-tertiary)] transition-transform duration-200 group-hover:translate-x-0.5 group-hover:text-[color:var(--text-primary)]"
                  weight="bold"
                  aria-hidden="true"
                />
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </section>
    );
  }
}

function EmptyShell({ hint }: { hint: string }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)] px-6 py-12 text-center">
      <MagnifyingGlass
        className="h-6 w-6 text-[color:var(--text-tertiary)]"
        weight="duotone"
        aria-hidden="true"
      />
      <p className="max-w-[42ch] text-[13px] text-[color:var(--text-secondary)]">
        {hint}
      </p>
    </div>
  );
}

function MatchedByPill({ matched }: { matched: SearchMatchType }) {
  const labels: Record<SearchMatchType, string> = {
    rfc: "RFC",
    period: "Periodo",
    folio: "Folio",
    name: "Nombre",
  };
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-[color:var(--border-ai)] bg-[color:var(--surface-teal-muted)] px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.16em] text-[color:var(--text-teal)]">
      <span>Coincide por</span>
      <span className="font-semibold">{labels[matched]}</span>
    </span>
  );
}

function StatusPill({ status }: { status: string }) {
  // Status pulled from the central dictionary so all surfaces stay in
  // sync. Kept as a compact outline badge so the row's primary value
  // (vendor + requirement) still dominates.
  return (
    <Badge variant="outline" className="text-[10.5px]">
      {statusLabel(status)}
    </Badge>
  );
}
