"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Warning,
  ArrowLeft,
  ArrowRight,
  Clock,
  Tray,
  SignOut,
} from "@phosphor-icons/react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { RequirementStatusBadge } from "@/components/checkwise/portal/requirement-status-badge";
import {
  EmptyState,
  ErrorState,
  Skeleton,
} from "@/components/checkwise/portal/state-surfaces";
import { INSTITUTION_LABELS } from "@/lib/api/portal";
import {
  clearAdminSession,
  readAdminSession,
  type AdminSession,
} from "@/lib/session/admin";
import {
  getReviewerQueue,
  ReviewerApiError,
  type QueueItem,
  type QueueResponse,
} from "@/lib/api/reviewer";

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
      <PageHeader
        eyebrow="Reviewer workbench"
        title="Documentos por revisar"
        description="Empieza por lo más viejo. Cada documento espera tu decisión humana — la automatización no aprueba ni rechaza nada."
        actions={
          <>
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
            >
              <SignOut className="h-4 w-4" aria-hidden />
              Cerrar sesión
            </Button>
          </>
        }
      />

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
          icon={Tray}
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
      className="cw-hover-lift block rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-4 transition-colors hover:bg-[color:var(--surface-hover)]"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <RequirementStatusBadge status={item.status} />
            {item.has_mismatch ? (
              <span className="inline-flex items-center gap-1 rounded-md border border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-bg)] px-2 py-0.5 text-xs text-[color:var(--status-warning-text)]">
                <Warning className="h-3 w-3" weight="fill" aria-hidden />
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
          <p className="truncate text-sm font-semibold text-[color:var(--text-primary)]">
            {item.requirement.name ?? "Documento sin requisito canónico"}
          </p>
          <p className="text-xs text-[color:var(--text-secondary)]">
            {institutionLabel}
            {item.period.period_key ? ` · ${item.period.period_key}` : ""}
          </p>
          <p className="truncate text-xs text-[color:var(--text-secondary)]">
            {item.provider.client_name} · {item.provider.vendor_name}
            {item.provider.vendor_rfc ? ` (${item.provider.vendor_rfc})` : ""}
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-start gap-2 sm:items-end">
          <span className="inline-flex items-center gap-1 text-xs text-[color:var(--text-tertiary)]">
            <Clock className="h-3 w-3" weight="bold" aria-hidden />
            {ageText}
          </span>
          <span className="inline-flex items-center gap-1 text-xs font-medium text-[color:var(--text-brand)]">
            Revisar
            <ArrowRight className="h-3.5 w-3.5" weight="bold" aria-hidden />
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
