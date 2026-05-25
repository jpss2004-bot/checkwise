"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useCallback } from "react";

import { AdminShell } from "../_shell";
import { SearchResults } from "@/components/checkwise/search-results";
import { PageHeader } from "@/components/ui/page-header";
import { adminSearch, type SearchHit } from "@/lib/api/search";

/**
 * Admin-scope search page. Lists every submission that matched, with
 * each row linking to the existing /admin/reviewer/{id} detail view.
 */
export default function AdminBuscarPage() {
  return (
    <AdminShell unframed>
      <div className="mx-auto max-w-6xl space-y-6 px-5 py-8">
        <PageHeader
          eyebrow="Buscar"
          title="Búsqueda global"
          description="RFC, periodo (YYYY-Mxx) o folio. CheckWise detecta el tipo automáticamente. Toca un resultado para abrir el detalle."
        />
        <Suspense fallback={null}>
          <AdminBuscarBody />
        </Suspense>
      </div>
    </AdminShell>
  );
}

function AdminBuscarBody() {
  const params = useSearchParams();
  const q = params?.get("q") ?? "";
  const run = useCallback((query: string) => adminSearch(query), []);
  const buildHref = useCallback(
    (hit: SearchHit) => `/admin/reviewer/${hit.submission_id}`,
    [],
  );
  return (
    <SearchResults
      query={q}
      runSearch={run}
      buildHref={buildHref}
      emptyHint="Empieza por un RFC, un periodo como 2026-M05, o un folio para encontrar la entrega en cualquier cliente."
    />
  );
}
