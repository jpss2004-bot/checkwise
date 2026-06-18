"use client";

import { useState, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * App-wide client providers.
 *
 * - {@link QueryClientProvider} is the real fetch-cache layer. Before this the
 *   app had only the hand-rolled in-flight de-dupe in `lib/api/request-cache`
 *   (0ms TTL by default — it coalesced concurrent reads but never *cached*), so
 *   every navigation re-hit the network and lists felt slow on every visit.
 *   With React Query, a read stays fresh for `staleTime` and lingers for
 *   `gcTime`, so returning to a list paints instantly from cache.
 * - {@link TooltipProvider} moved here from the server `layout.tsx` so it lives
 *   under the same single client boundary.
 *
 * The QueryClient is created once per browser session via `useState` so it is
 * never recreated on re-render (which would silently drop the whole cache).
 */
export function AppProviders({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // Serve cached data for 60s before it's considered stale; a remount
            // within that window paints with zero network round-trips.
            staleTime: 60_000,
            // Keep unused query data for 5min so back-navigation is instant.
            gcTime: 5 * 60_000,
            // The product exposes explicit retry / refresh affordances; the
            // surprise refetch on tab-focus is more jarring than helpful here.
            refetchOnWindowFocus: false,
            retry: 1,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={300} skipDelayDuration={150}>
        {children}
      </TooltipProvider>
    </QueryClientProvider>
  );
}
