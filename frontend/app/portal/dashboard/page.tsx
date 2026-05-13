"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertCircle, ArrowLeft, Loader2 } from "lucide-react";

import { ComplianceCalendar } from "@/components/checkwise/portal/compliance-calendar";
import { ProviderContextBar } from "@/components/checkwise/portal/provider-context-bar";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  getCalendar,
  getOnboarding,
  type CalendarPayload,
  type OnboardingSummary,
} from "@/lib/portal-client";
import { readPortalSession, type PortalSession } from "@/lib/portal-session";

const DEFAULT_YEAR = 2026;

export default function DashboardPage() {
  const router = useRouter();
  const [session, setSession] = useState<PortalSession | null>(null);
  const [onboarding, setOnboarding] = useState<OnboardingSummary | null>(null);
  const [calendar, setCalendar] = useState<CalendarPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
  }, [session]);

  if (!session) {
    return null;
  }

  const isComplete = onboarding?.summary.completed ?? false;

  return (
    <>
      <ProviderContextBar session={session} />
      <main className="mx-auto max-w-7xl space-y-5 px-5 py-6">
        {!isComplete ? (
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
          <div className="flex items-center gap-2 rounded-md border border-border bg-white p-4 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            Cargando calendario…
          </div>
        ) : error ? (
          <div className="rounded-md border border-destructive/30 bg-red-50 p-3 text-sm text-destructive">
            <div className="flex gap-2">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <span>{error}</span>
            </div>
          </div>
        ) : calendar ? (
          <ComplianceCalendar data={calendar} />
        ) : null}
      </main>
    </>
  );
}
