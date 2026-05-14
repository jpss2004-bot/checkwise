"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  ClipboardList,
  Clock3,
  Inbox,
  LogOut,
} from "lucide-react";

import { BrandLogo } from "@/components/checkwise/brand-logo";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { RequirementStatusBadge } from "@/components/checkwise/portal/requirement-status-badge";
import {
  EmptyState,
  ErrorState,
  Skeleton,
} from "@/components/checkwise/portal/state-surfaces";
import { INSTITUTION_LABELS } from "@/lib/portal-client";
import {
  clearAdminSession,
  readAdminSession,
  type AdminSession,
} from "@/lib/admin-session";
import {
  getReviewerQueue,
  ReviewerApiError,
  type QueueItem,
  type QueueResponse,
} from "@/lib/reviewer-client";

const REVIEWER_ROLES = ["reviewer", "internal_admin"] as const;

export default function ReviewerQueuePage() {
  const router = useRouter();
  const [session, setSession] = useState<AdminSession | null>(null);
  const [queue, setQueue] = useState<QueueResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    const current = readAdminSession();
    if (!current) {
      router.replace("/admin/login");
      return;
    }
    if (!current.roles.some((r) => (REVIEWER_ROLES as readonly string[]).includes(r))) {
      router.replace("/admin");
      return;
    }
    setSession(current);
  }, [router]);

  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    getReviewerQueue(session.access_token)
      .then((payload) => {
        if (!cancelled) setQueue(payload);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ReviewerApiError && err.status === 401) {
          clearAdminSession();
          router.replace("/admin/login");
          return;
        }
        setError("No pudimos cargar la bandeja.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [session, reloadKey, router]);

  const retry = useCallback(() => setReloadKey((k) => k + 1), []);

  function onLogout() {
    clearAdminSession();
    router.replace("/admin/login");
  }

  if (!session) return null;

  const items = queue?.items ?? [];

  return (
    <main className="mx-auto max-w-6xl space-y-6 px-5 py-8">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-2">
          <div className="flex items-center gap-3">
            <BrandLogo variant="compact" size="md" />
            <span className="hidden h-5 w-px bg-border sm:block" />
            <p className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              <ClipboardList className="h-4 w-4 text-primary" aria-hidden />
              Bandeja de revisión
            </p>
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Documentos por revisar
          </h1>
          <p className="text-sm text-muted-foreground">
            Empieza por lo más viejo. Cada documento espera tu decisión
            humana — la automatización no aprueba ni rechaza nada.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button asChild variant="outline" size="sm">
            <Link href="/admin">
              <ArrowLeft className="h-4 w-4" aria-hidden />
              Inicio
            </Link>
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onLogout}
            className="active:scale-[0.98]"
          >
            <LogOut className="h-4 w-4" aria-hidden />
            Cerrar sesión
          </Button>
        </div>
      </header>

      {loading ? (
        <QueueSkeleton />
      ) : error ? (
        <ErrorState
          title="No pudimos cargar la bandeja"
          description="Tu conexión pudo haberse interrumpido. Tu sesión sigue activa."
          onRetry={retry}
        />
      ) : items.length === 0 ? (
        <EmptyState
          icon={Inbox}
          title="No hay documentos por revisar"
          description="Cuando un proveedor cargue documentación nueva, aparecerá aquí en orden de llegada."
          variant="muted"
        />
      ) : (
        <Card>
          <CardHeader>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <CardTitle>{items.length} en cola</CardTitle>
              <Badge variant="outline" className="whitespace-nowrap">
                Orden FIFO · más viejos primero
              </Badge>
            </div>
          </CardHeader>
          <CardContent>
            <ul className="space-y-3">
              {items.map((item) => (
                <li key={item.submission_id}>
                  <QueueRow item={item} />
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </main>
  );
}

function QueueRow({ item }: { item: QueueItem }) {
  const ageText = formatAge(item.age_hours);
  const institutionLabel = item.requirement.institution
    ? INSTITUTION_LABELS[item.requirement.institution] ?? item.requirement.institution
    : "—";
  return (
    <Link
      href={`/admin/reviewer/${item.submission_id}`}
      className="block rounded-md border border-border bg-white p-4 transition-colors hover:bg-muted/40 active:scale-[0.995]"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <RequirementStatusBadge status={item.status} />
            {item.has_mismatch ? (
              <span className="inline-flex items-center gap-1 rounded-md border border-amber-300 bg-amber-50 px-2 py-0.5 text-xs text-amber-800">
                <AlertTriangle className="h-3 w-3" aria-hidden />
                Posible mismatch
              </span>
            ) : null}
            {item.signal_count > 0 ? (
              <span className="text-xs text-muted-foreground">
                {item.signal_count} señal{item.signal_count === 1 ? "" : "es"} automátic
                {item.signal_count === 1 ? "a" : "as"}
              </span>
            ) : null}
          </div>
          <p className="truncate text-sm font-semibold">
            {item.requirement.name ?? "Documento sin requisito canónico"}
          </p>
          <p className="text-xs text-muted-foreground">
            {institutionLabel}
            {item.period.period_key ? ` · ${item.period.period_key}` : ""}
          </p>
          <p className="truncate text-xs text-muted-foreground">
            {item.provider.client_name} · {item.provider.vendor_name}
            {item.provider.vendor_rfc ? ` (${item.provider.vendor_rfc})` : ""}
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-start gap-2 sm:items-end">
          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
            <Clock3 className="h-3 w-3" aria-hidden />
            {ageText}
          </span>
          <span className="inline-flex items-center gap-1 text-xs font-medium text-primary">
            Revisar
            <ArrowRight className="h-3.5 w-3.5" aria-hidden />
          </span>
        </div>
      </div>
    </Link>
  );
}

function QueueSkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-4 w-3/12" />
      </CardHeader>
      <CardContent className="space-y-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="rounded-md border border-border bg-white p-4">
            <Skeleton className="h-3 w-2/12" />
            <Skeleton className="mt-3 h-4 w-7/12" />
            <Skeleton className="mt-2 h-3 w-5/12" />
            <Skeleton className="mt-2 h-3 w-8/12" />
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function formatAge(hours: number): string {
  if (hours < 1) return "menos de 1 hora";
  if (hours < 24) return hours === 1 ? "hace 1 hora" : `hace ${hours} horas`;
  const days = Math.floor(hours / 24);
  return days === 1 ? "hace 1 día" : `hace ${days} días`;
}
