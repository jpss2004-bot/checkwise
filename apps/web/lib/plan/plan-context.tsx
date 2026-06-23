"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import {
  getClientPlan,
  invalidateClientPlan,
  type ClientPlan,
} from "@/lib/api/client";

type PlanContextValue = {
  plan: ClientPlan | null;
  loading: boolean;
  /** Non-null only on a fetch failure — consumers fail open (hide plan UI). */
  error: string | null;
  refresh: () => void;
};

const PlanContext = createContext<PlanContextValue | null>(null);

/**
 * The single fetch point for GET /client/plan. Mounts once per shell, exposes
 * the plan via context, and refreshes on demand (the add/archive/restore
 * mutations also invalidate the dedupe cache). Fail-open: a read error leaves
 * ``plan = null`` so the plan UI hides rather than blocking the console.
 */
export function ClientPlanProvider({
  clientId,
  children,
}: {
  clientId?: string | null;
  children: ReactNode;
}) {
  const [plan, setPlan] = useState<ClientPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const refresh = useCallback(() => {
    invalidateClientPlan(clientId ?? undefined);
    setReloadKey((k) => k + 1);
  }, [clientId]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getClientPlan(clientId ? { client_id: clientId } : undefined)
      .then((p) => {
        if (!cancelled) {
          setPlan(p);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setPlan(null);
          setError(err instanceof Error ? err.message : "plan_error");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [clientId, reloadKey]);

  return (
    <PlanContext.Provider value={{ plan, loading, error, refresh }}>
      {children}
    </PlanContext.Provider>
  );
}

/** Read the current client plan. Returns inert defaults outside a provider. */
export function useClientPlan(): PlanContextValue {
  return (
    useContext(PlanContext) ?? {
      plan: null,
      loading: false,
      error: null,
      refresh: () => {},
    }
  );
}
