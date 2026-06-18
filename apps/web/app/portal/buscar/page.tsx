"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useCallback } from "react";

import { PortalAppShell } from "@/components/checkwise/portal/portal-app-shell";
import { SearchResults } from "@/components/checkwise/search-results";
import { PageHeader } from "@/components/ui/page-header";
import { portalSearch, type SearchHit } from "@/lib/api/search";
import { withPortalSession } from "@/lib/session/with-portal-session";
import type { PortalSession } from "@/lib/session/portal";

/**
 * Portal-scope search. Backend scopes results to the active
 * workspace's vendor. Rows navigate to the per-submission detail at
 * /portal/submissions/[submission_id].
 */
function PortalBuscarInner({ session }: { session: PortalSession }) {
  return (
    <PortalAppShell session={session}>
      <main className="mx-auto max-w-6xl space-y-6 px-5 py-8">
        <PageHeader
          eyebrow="Buscar"
          title="Buscar en mi expediente"
          description="RFC, periodo (YYYY-Mxx) o folio dentro de tu workspace."
        />
        <Suspense fallback={null}>
          <PortalBuscarBody />
        </Suspense>
      </main>
    </PortalAppShell>
  );
}

function PortalBuscarBody() {
  const params = useSearchParams();
  const q = params?.get("q") ?? "";
  const run = useCallback((query: string) => portalSearch(query), []);
  const buildHref = useCallback(
    (hit: SearchHit) => `/portal/submissions/${hit.submission_id}`,
    [],
  );
  return (
    <SearchResults
      query={q}
      searchPath="/portal/buscar"
      runSearch={run}
      buildHref={buildHref}
      emptyHint="Escribe un periodo (por ejemplo 2026-M05) o un folio para encontrar una entrega de tu expediente."
    />
  );
}

export default withPortalSession(PortalBuscarInner);
