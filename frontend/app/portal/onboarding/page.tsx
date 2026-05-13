"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertCircle, ArrowRight, Loader2 } from "lucide-react";

import { OnboardingChecklist } from "@/components/checkwise/portal/onboarding-checklist";
import { ProviderContextBar } from "@/components/checkwise/portal/provider-context-bar";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getOnboarding, type OnboardingSummary } from "@/lib/portal-client";
import { readPortalSession, type PortalSession } from "@/lib/portal-session";

export default function OnboardingPage() {
  const router = useRouter();
  const [session, setSession] = useState<PortalSession | null>(null);
  const [data, setData] = useState<OnboardingSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

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
    getOnboarding(session)
      .then((payload) => {
        if (!cancelled) setData(payload);
      })
      .catch(() => {
        if (!cancelled) setError("No fue posible cargar el expediente.");
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

  const completed = data?.summary.completed ?? false;

  return (
    <>
      <ProviderContextBar session={session} />
      <main className="mx-auto max-w-7xl space-y-5 px-5 py-6">
        <Card>
          <CardHeader>
            <CardTitle>Bienvenido a tu espacio de cumplimiento</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-muted-foreground">
            <p>
              Antes de entrar al calendario recurrente necesitamos asegurarnos de tener tu
              expediente inicial. Este expediente vive como referencia única para todas tus
              cargas mensuales, bimestrales y cuatrimestrales.
            </p>
            <p>
              La revisión legal sigue siendo humana: aquí solo registramos lo recibido,
              prevalidamos y abrimos trazabilidad.
            </p>
            <div className="flex gap-2">
              <Button asChild variant={completed ? "default" : "outline"}>
                <Link href="/portal/dashboard">
                  {completed ? "Ir al calendario REPSE" : "Ver calendario REPSE (preliminar)"}
                  <ArrowRight className="h-4 w-4" aria-hidden="true" />
                </Link>
              </Button>
            </div>
          </CardContent>
        </Card>

        {loading ? (
          <div className="flex items-center gap-2 rounded-md border border-border bg-white p-4 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            Cargando expediente…
          </div>
        ) : error ? (
          <div className="rounded-md border border-destructive/30 bg-red-50 p-3 text-sm text-destructive">
            <div className="flex gap-2">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <span>{error}</span>
            </div>
          </div>
        ) : data ? (
          <OnboardingChecklist data={data} />
        ) : null}
      </main>
    </>
  );
}
