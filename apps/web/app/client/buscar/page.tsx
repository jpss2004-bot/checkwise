"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useCallback } from "react";

import { ClientShell } from "../_shell";
import { SearchResults } from "@/components/checkwise/search-results";
import { PageHeader } from "@/components/ui/page-header";
import { clientSearch, type SearchHit } from "@/lib/api/search";

/**
 * Client-scope search. Backend scopes results to the client_admin
 * user's clients. Rows navigate to the vendor detail page since
 * /client doesn't have a per-submission detail surface.
 */
export default function ClientBuscarPage() {
  return (
    <ClientShell unframed>
      <div className="mx-auto max-w-6xl space-y-6 px-5 py-8">
        <PageHeader
          eyebrow="Buscar"
          title="Búsqueda en tu portafolio"
          description="RFC, periodo (YYYY-Mxx) o folio. Solo verás resultados dentro de tus clientes."
        />
        <Suspense fallback={null}>
          <ClientBuscarBody />
        </Suspense>
      </div>
    </ClientShell>
  );
}

function ClientBuscarBody() {
  const params = useSearchParams();
  const q = params?.get("q") ?? "";
  const run = useCallback((query: string) => clientSearch(query), []);
  const buildHref = useCallback(
    (hit: SearchHit) => `/client/vendors/${hit.vendor_id}`,
    [],
  );
  return (
    <SearchResults
      query={q}
      searchPath="/client/buscar"
      runSearch={run}
      buildHref={buildHref}
      emptyHint="Escribe el RFC de uno de tus proveedores, un periodo (por ejemplo 2026-M05) o un folio."
    />
  );
}
