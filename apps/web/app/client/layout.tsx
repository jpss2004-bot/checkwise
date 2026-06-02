import type { ReactNode } from "react";

// 2026-06-02 — force dynamic rendering for every ``/client/*`` route.
//
// The cliente shell (``_shell.tsx``) reads ``?client_id=<uuid>`` from
// the URL at the top level via ``useUrlClientId`` (which delegates to
// ``useSearchParams``). Next 15's static prerender requires every
// ``useSearchParams`` call to sit inside a ``<Suspense>`` boundary;
// pushing the call from the shell down into a Suspense-wrapped child
// would be an invasive refactor of the shell's data flow (the
// per-page ``getClientMe(...)`` request shape depends on
// ``urlClientId`` synchronously). Marking the layout dynamic skips
// the prerender step entirely, matching how the portal-side
// PortalAppShell is already consumed in practice. The pages are still
// server-rendered + cached at the edge; only the build-time
// static-export pass is disabled.
export const dynamic = "force-dynamic";

export default function ClientLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
