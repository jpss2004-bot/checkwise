"use client";

import { RouteError } from "@/components/ui/route-error";

/**
 * Root segment error boundary. Before this existed, a thrown render/fetch
 * error on the public, auth, or marketing routes (everything under app/
 * that isn't /admin, /client, /platform, /portal — which have their own
 * boundaries) bubbled to Next's default English error page (audit
 * public-auth "No root error boundary"). Now those failures are contained
 * with a Spanish retry surface and the user keeps the chrome.
 */
export default function RootError(props: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return <RouteError {...props} />;
}
