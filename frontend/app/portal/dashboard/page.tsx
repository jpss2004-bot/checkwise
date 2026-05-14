"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { ComplianceCalendar } from "@/components/checkwise/portal/compliance-calendar";
import { ProviderContextBar } from "@/components/checkwise/portal/provider-context-bar";
import {
  DashboardSkeleton,
  ErrorState,
} from "@/components/checkwise/portal/state-surfaces";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  getCalendar,
  getOnboarding,
  type CalendarPayload,
  type OnboardingSummary,
} from "@/lib/api/portal";
import { readPortalSession, type PortalSession } from "@/lib/session/portal";

const DEFAULT_YEAR = 2026;

export default function DashboardPage() {
  const router = useRouter();
  const [session, setSession] = useState<PortalSession | null>(null);
  const [onboarding, setOnboarding] = useState<OnboardingSummary | null>(null);
  const [calendar, setCalendar] = useState<CalendarPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    const current = readPortalSession();
    if (!current) {
      router.replace("/");
      return;
    }
    setSession(current);
  }, [router]);

  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([getOnboarding(session), getCalendar(session, DEFAULT_YEAR)])
      .then(([ob, cal]) => {
        if (cancelled) return;
        setOnboarding(ob);
        setCalendar(cal);
      })
      .catch(() => {
        if (!cancelled) setError("No fue posible cargar el dashboard.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [session, reloadKey]);

  const retry = useCallback(() => setReloadKey((k) => k + 1), []);

  if (!session) {
    return null;
  }

  const isComplete = onboarding?.summary.completed ?? false;

  return (
    <>
      <ProviderContextBar
        session={session}
        onboardingPct={onboarding?.summary.completion_pct ?? null}
      />
      <main className="mx-auto max-w-7xl space-y-5 px-5 py-6">
        {!loading && !error && !isComplete ? (
          <Card>
            <CardHeader>
              <CardTitle>Expediente inicial pendiente</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm text-muted-foreground">
              <p>
                Aún faltan documentos del expediente corporativo. Puedes ver el calendario para
                planear, pero te recomendamos completar primero el alta inicial:
              </p>
              <div className="flex gap-2">
                <Button asChild variant="outline">
                  <Link href="/portal/onboarding">
                    <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                    Ir a expediente
                  </Link>
                </Button>
              </div>
            </CardContent>
          </Card>
        ) : null}

        {loading ? (
          <DashboardSkeleton />
        ) : error ? (
          <ErrorState
            title="No pudimos cargar el calendario"
            description="Tu conexión pudo haberse interrumpido o el servicio respondió tarde. Tu sesión sigue activa."
            onRetry={retry}
          />
        ) : calendar ? (
          <ComplianceCalendar data={calendar} />
        ) : null}
      </main>
    </>
  );
}
