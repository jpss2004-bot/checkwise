/**
 * CheckWise · Portal session guard HOC
 *
 * Replaces the 4× duplicated session-check pattern across:
 *   - app/portal/onboarding/page.tsx
 *   - app/portal/dashboard/page.tsx
 *   - app/portal/calendar/page.tsx
 *   - app/portal/reports/page.tsx
 *   - app/portal/entra-a-tu-espacio/page.tsx (1.6)
 *
 * Usage (in Phase 4):
 *
 *   // page.tsx — before
 *   export default function DashboardPage() {
 *     const router = useRouter();
 *     const [session, setSession] = useState<PortalSession | null>(null);
 *     useEffect(() => {
 *       const s = readPortalSession();
 *       if (!s) { router.replace('/'); return; }
 *       setSession(s);
 *     }, [router]);
 *     if (!session) return null;
 *     return <DashboardView session={session} />;
 *   }
 *
 *   // page.tsx — after
 *   export default withPortalSession(function DashboardPage({ session }) {
 *     return <DashboardView session={session} />;
 *   });
 *
 * TODO[backend-integration]: Once real auth lands, this HOC should:
 *   1. Hit a /api/v1/portal/me endpoint to verify the session server-side.
 *   2. Strip the localStorage fallback.
 *   3. Move to a Next.js middleware so we don't ship the entire client.
 */

'use client';

import { useEffect, useState, type ComponentType } from 'react';
import { useRouter } from 'next/navigation';
import { readPortalSession, type PortalSession } from '@/lib/session/portal';

/**
 * Wrap a client page so it only renders when there's a valid portal session.
 * Redirects to `redirectTo` (default `/`) when no session is present.
 */
export function withPortalSession<P extends { session: PortalSession }>(
  Component: ComponentType<P>,
  options: { redirectTo?: string } = {}
) {
  const { redirectTo = '/' } = options;

  function GuardedComponent(props: Omit<P, 'session'>) {
    const router = useRouter();
    const [session, setSession] = useState<PortalSession | null>(null);
    const [checked, setChecked] = useState(false);

    useEffect(() => {
      const s = readPortalSession();
      if (!s) {
        router.replace(redirectTo);
        return;
      }
      setSession(s);
      setChecked(true);
    }, [router]);

    // Render nothing while we resolve session — prevents flash of public content.
    // Phase 2's <Skeleton> primitive can be slotted here per-page instead, but
    // the HOC stays content-agnostic.
    if (!checked || !session) return null;

    return <Component {...(props as unknown as P)} session={session} />;
  }

  GuardedComponent.displayName = `withPortalSession(${Component.displayName ?? Component.name ?? 'Anonymous'})`;
  return GuardedComponent;
}
