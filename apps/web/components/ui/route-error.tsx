"use client";

import { useEffect } from "react";

import { ErrorState } from "@/components/checkwise/portal/state-surfaces";

/**
 * Shared body for each authed area's `error.tsx`. Next route error
 * boundaries are always Client Components and receive `{ error, reset }`.
 *
 * Before these boundaries existed, a thrown render/fetch error anywhere
 * under `/admin`, `/client`, `/platform`, or `/portal` bubbled to the
 * global boundary and white-screened the whole app. Now the failure is
 * contained to the segment with a retry path, and the user keeps the
 * surrounding chrome.
 *
 * `error.digest` correlates this client error with the server log line
 * for the same render, so we surface it to the console for support.
 */
export function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Route error boundary:", error);
  }, [error]);

  return (
    <div className="mx-auto max-w-2xl px-6 py-16">
      <ErrorState
        title="Algo salió mal en esta sección"
        description="No pudimos mostrar el contenido. Vuelve a intentarlo; si el problema persiste, escríbenos."
        onRetry={reset}
      />
    </div>
  );
}
