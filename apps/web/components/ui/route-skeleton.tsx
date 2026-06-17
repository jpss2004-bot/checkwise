import { Skeleton } from "@/components/ui/skeleton";

/**
 * Neutral route-transition fallback rendered by each authed area's
 * `loading.tsx`. Next wraps the page segment in a `<Suspense>` whose
 * fallback shows instantly on soft navigation (and during the initial
 * RSC fetch) — replacing the blank flash that used to sit between
 * clicking a nav item and the client shell remounting.
 *
 * Deliberately generic (a title block + stat cards + a list) so it
 * reads sensibly for any page in the area without claiming a specific
 * layout. Per DESIGN_SYSTEM §6.7 this is a skeleton, not a spinner —
 * spinners are reserved for inline actions.
 */
export function RouteSkeleton() {
  return (
    <div
      className="mx-auto w-full max-w-6xl px-4 py-6 sm:px-6 lg:px-8"
      aria-busy="true"
      aria-live="polite"
    >
      <span className="sr-only">Cargando…</span>
      <div className="space-y-2">
        <Skeleton className="h-7 w-64 max-w-[60%]" />
        <Skeleton className="h-4 w-96 max-w-[80%]" />
      </div>
      <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div
            key={i}
            className="rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-4"
          >
            <Skeleton className="h-3 w-5/12" />
            <Skeleton className="mt-3 h-7 w-2/12" />
            <Skeleton className="mt-2 h-3 w-7/12" />
          </div>
        ))}
      </div>
      <div className="mt-4 rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-4">
        <Skeleton className="h-4 w-3/12" />
        <div className="mt-4 space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="flex items-center justify-between gap-3">
              <div className="flex-1 space-y-2">
                <Skeleton className="h-3 w-6/12" />
                <Skeleton className="h-3 w-4/12" />
              </div>
              <Skeleton className="h-8 w-24" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
