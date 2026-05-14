"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, FolderOpen } from "lucide-react";

import { OnboardingChecklist } from "@/components/checkwise/portal/onboarding-checklist";
import { ProviderContextBar } from "@/components/checkwise/portal/provider-context-bar";
import {
  EmptyState,
  ErrorState,
  OnboardingSkeleton,
} from "@/components/checkwise/portal/state-surfaces";
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
  }, [session, reloadKey]);

  const retry = useCallback(() => setReloadKey((k) => k + 1), []);

  if (!session) {
    return null;
  }

  const completed = data?.summary.completed ?? false;
  const sectionCount = data?.sections.length ?? 0;

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
          <OnboardingSkeleton />
        ) : error ? (
          <ErrorState
            title="No pudimos cargar tu expediente"
            description="Tu conexión pudo haberse interrumpido. No perdiste nada: tu sesión sigue activa y puedes reintentarlo."
            onRetry={retry}
          />
        ) : data && sectionCount > 0 ? (
          <OnboardingChecklist data={data} />
        ) : data ? (
          <EmptyState
            icon={FolderOpen}
            title="Tu expediente aún no tiene secciones"
            description="Estamos configurando los requisitos para tu workspace. Vuelve en unos minutos o avísanos si esto persiste."
            variant="muted"
          />
        ) : null}
      </main>
    </>
  );
}
