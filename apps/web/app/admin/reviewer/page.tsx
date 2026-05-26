"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Warning,
  ArrowRight,
  CheckCircle,
  Clock,
  Tray,
  XCircle,
} from "@phosphor-icons/react";

import { AdminShell } from "../_shell";
import { VendorRef } from "@/components/checkwise/vendor-ref";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/ui/page-header";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select } from "@/components/ui/select";
import { RequirementStatusBadge } from "@/components/checkwise/portal/requirement-status-badge";
import {
  EmptyState,
  ErrorState,
  Skeleton,
} from "@/components/checkwise/portal/state-surfaces";
import { INSTITUTION_LABELS, type RequirementStatus } from "@/lib/api/portal";
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

type FilterKey = "all" | "in_review" | "mismatch" | "clarify";

const FILTER_LABEL: Record<FilterKey, string> = {
  all: "Todos",
  in_review: "Por revisar",
  mismatch: "Posible inconsistencia",
  clarify: "Aclaración",
};

const FILTER_STATUSES: Record<Exclude<FilterKey, "all" | "mismatch">, RequirementStatus[]> = {
  in_review: ["pendiente_revision", "prevalidado", "recibido"],
  clarify: ["requiere_aclaracion"],
};

function matchesFilter(item: QueueItem, filter: FilterKey): boolean {
  if (filter === "all") return true;
  if (filter === "mismatch") {
    return item.has_mismatch || item.status === "posible_mismatch";
  }
  return FILTER_STATUSES[filter].includes(item.status);
}

export default function ReviewerQueuePage() {
  const router = useRouter();
  const [session, setSession] = useState<AdminSession | null>(null);
  const [queue, setQueue] = useState<QueueResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [filter, setFilter] = useState<FilterKey>("all");
  // Institution filter — empty string means "all institutions" and
  // omits the query param so the backend returns every row. The
  // dropdown options are driven by INSTITUTION_LABELS so they stay in
  // sync with portal/calendar and client/submissions.
  const [institution, setInstitution] = useState<string>("");

  useEffect(() => {
    const current = readAdminSession();
    if (!current) {
      router.replace("/login");
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
    getReviewerQueue(session.access_token, {
      institution: institution || undefined,
    })
      .then((payload) => {
        if (!cancelled) setQueue(payload);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ReviewerApiError && err.status === 401) {
          clearAdminSession();
          router.replace("/login");
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
  }, [session, reloadKey, router, institution]);

  const retry = useCallback(() => setReloadKey((k) => k + 1), []);

  // F1: logout is now provided by the AdminShell header, so this
  // page no longer renders its own Cerrar sesión action.

  const items = useMemo(() => queue?.items ?? [], [queue]);
  const filteredItems = useMemo(
    () => items.filter((item) => matchesFilter(item, filter)),
    [items, filter],
  );

  const counts = useMemo<Record<FilterKey, number>>(() => {
    const acc: Record<FilterKey, number> = {
      all: items.length,
      in_review: 0,
      mismatch: 0,
      clarify: 0,
    };
    for (const item of items) {
      if (matchesFilter(item, "in_review")) acc.in_review += 1;
      if (matchesFilter(item, "mismatch")) acc.mismatch += 1;
      if (matchesFilter(item, "clarify")) acc.clarify += 1;
    }
    return acc;
  }, [items]);

  if (!session) return null;

  return (
    <AdminShell unframed>
      <div className="mx-auto max-w-6xl space-y-6 px-5 py-8">
        <PageHeader
          eyebrow="Reviewer workbench"
          title="Documentos por revisar"
          description="Empieza por lo más viejo. Cada documento espera tu decisión humana. La automatización no aprueba ni rechaza nada."
        />

      {/* Institution scope filter. Sits above the status tabs so the
          reviewer narrows by authority (SAT / IMSS / INFONAVIT / STPS)
          before drilling into Por revisar / Inconsistencia / Aclaración.
          Default "" means all institutions; the API call drops the
          query param entirely in that case. */}
      <div className="flex flex-wrap items-center gap-3">
        <label
          htmlFor="reviewer-institution"
          className="font-mono text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-tertiary)]"
        >
          Institución
        </label>
        <Select
          id="reviewer-institution"
          value={institution}
          onChange={(e) => setInstitution(e.target.value)}
          className="h-9 max-w-[260px] text-[13px]"
          aria-label="Filtrar bandeja por institución"
        >
          <option value="">Todas las instituciones</option>
          {Object.entries(INSTITUTION_LABELS).map(([code, label]) => (
            <option key={code} value={code}>
              {label}
            </option>
          ))}
        </Select>
        {institution ? (
          <button
            type="button"
            onClick={() => setInstitution("")}
            className="font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-teal)] underline-offset-2 hover:underline"
          >
            Limpiar
          </button>
        ) : null}
      </div>

      {/* Phase 9 / Slice 9A — rolling 7-day stat strip. Renders even
          when the actionable queue is empty so the reviewer always
          sees what got cleared this week. Hidden during the initial
          load so it doesn't flash 0 before the real numbers arrive. */}
      {queue ? (
        <section
          aria-label="Estado de la semana"
          className="grid gap-3 sm:grid-cols-2"
        >
          <CounterCard
            icon={CheckCircle}
            tone="success"
            label="Aprobados (últimos 7 días)"
            value={queue.approved_last_7d_count}
          />
          <CounterCard
            icon={XCircle}
            tone="destructive"
            label="Rechazados (últimos 7 días)"
            value={queue.rejected_last_7d_count}
          />
        </section>
      ) : null}

      {loading ? (
        <QueueTableSkeleton />
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
        <section
          aria-label="Cola de documentos por revisar"
          className="cw-fade-up rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-xs"
        >
          <header className="flex flex-wrap items-center justify-between gap-3 border-b border-[color:var(--border-subtle)] px-5 py-3">
            <Tabs value={filter} onValueChange={(v) => setFilter(v as FilterKey)}>
              <TabsList>
                {(["all", "in_review", "mismatch", "clarify"] as FilterKey[]).map(
                  (key) => (
                    <TabsTrigger key={key} value={key}>
                      <span>{FILTER_LABEL[key]}</span>
                      <span className="ml-1.5 font-mono text-[10px] tabular-nums opacity-70">
                        {counts[key]}
                      </span>
                    </TabsTrigger>
                  ),
                )}
              </TabsList>
            </Tabs>
            <Badge variant="outline" className="whitespace-nowrap">
              FIFO · más viejos primero
            </Badge>
          </header>

          {filteredItems.length === 0 ? (
            <div className="px-5 py-10">
              <EmptyState
                icon={Tray}
                title={`Sin resultados en "${FILTER_LABEL[filter]}"`}
                description="Cambia el filtro para ver otros documentos en la cola."
                variant="muted"
              />
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[160px]">Estado</TableHead>
                  <TableHead>Documento</TableHead>
                  <TableHead>Institución · periodo</TableHead>
                  <TableHead>Proveedor</TableHead>
                  <TableHead className="w-[120px]">Edad</TableHead>
                  <TableHead className="w-[40px]" aria-label="Acción" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredItems.map((item) => (
                  <QueueTableRow
                    key={item.submission_id}
                    item={item}
                    onOpen={() => router.push(`/admin/reviewer/${item.submission_id}`)}
                  />
                ))}
              </TableBody>
            </Table>
          )}
        </section>
      )}
      </div>
    </AdminShell>
  );
}

function QueueTableRow({
  item,
  onOpen,
}: {
  item: QueueItem;
  onOpen: () => void;
}) {
  const ageText = formatAge(item.age_hours);
  const institutionLabel = item.requirement.institution
    ? INSTITUTION_LABELS[item.requirement.institution] ?? item.requirement.institution
    : "—";

  return (
    <TableRow
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen();
        }
      }}
      tabIndex={0}
      role="link"
      aria-label={`Abrir ${item.requirement.name ?? "documento"} de ${item.provider.vendor_name}`}
      className="cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[color:var(--border-focus)]/40"
    >
      <TableCell>
        <div className="flex flex-col gap-1.5">
          <RequirementStatusBadge status={item.status} />
          {item.has_mismatch ? (
            <span className="inline-flex w-max items-center gap-1 rounded-sm border border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-bg)] px-1.5 py-0.5 text-[10px] font-medium text-[color:var(--status-warning-text)]">
              <Warning className="h-3 w-3" weight="fill" aria-hidden />
              Mismatch
            </span>
          ) : null}
        </div>
      </TableCell>

      <TableCell>
        <p className="font-medium leading-tight text-[color:var(--text-primary)]">
          {item.requirement.name ?? "Documento sin requisito canónico"}
        </p>
        {item.signal_count > 0 ? (
          <p className="mt-1 text-[11px] text-[color:var(--text-tertiary)]">
            {item.signal_count} señal{item.signal_count === 1 ? "" : "es"} automátic
            {item.signal_count === 1 ? "a" : "as"}
          </p>
        ) : null}
      </TableCell>

      <TableCell>
        <p className="text-[color:var(--text-primary)]">{institutionLabel}</p>
        {item.period.period_key ? (
          <p className="font-mono text-[11px] tabular-nums text-[color:var(--text-tertiary)]">
            {item.period.period_key}
          </p>
        ) : null}
      </TableCell>

      <TableCell>
        <p
          className="font-medium text-[color:var(--text-primary)]"
          onClick={(e) => e.stopPropagation()}
        >
          {item.provider.vendor_id ? (
            <VendorRef
              vendorId={item.provider.vendor_id}
              vendorName={item.provider.vendor_name}
              clientId={item.provider.client_id ?? undefined}
            />
          ) : (
            item.provider.vendor_name
          )}
        </p>
        <p className="text-[11px] text-[color:var(--text-tertiary)]">
          {item.provider.client_name}
          {item.provider.vendor_rfc ? (
            <span className="ml-1 font-mono">· {item.provider.vendor_rfc}</span>
          ) : null}
        </p>
      </TableCell>

      <TableCell>
        <span className="inline-flex items-center gap-1 font-mono text-[11px] tabular-nums text-[color:var(--text-secondary)]">
          <Clock className="h-3 w-3" weight="bold" aria-hidden />
          {ageText}
        </span>
      </TableCell>

      <TableCell className="text-right">
        <ArrowRight
          className="ml-auto h-4 w-4 text-[color:var(--text-tertiary)] transition-transform duration-fast group-hover:translate-x-0.5"
          weight="bold"
          aria-hidden
        />
      </TableCell>
    </TableRow>
  );
}

function QueueTableSkeleton() {
  return (
    <section
      aria-busy="true"
      className="rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-xs"
    >
      <header className="flex flex-wrap items-center gap-2 border-b border-[color:var(--border-subtle)] px-5 py-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-7 w-24 rounded-md" />
        ))}
      </header>
      <div className="divide-y divide-[color:var(--border-subtle)]">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="grid grid-cols-12 items-center gap-3 px-5 py-3">
            <Skeleton className="col-span-2 h-5 w-24" />
            <Skeleton className="col-span-3 h-4 w-full" />
            <Skeleton className="col-span-3 h-4 w-3/4" />
            <Skeleton className="col-span-3 h-4 w-2/3" />
            <Skeleton className="col-span-1 h-4 w-12" />
          </div>
        ))}
      </div>
    </section>
  );
}

function formatAge(hours: number): string {
  if (hours < 1) return "<1h";
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  return `${days}d`;
}

// Phase 9 / Slice 9A — single-counter card for the stat strip above
// the queue. Reads as a glanceable "this week" indicator without
// inviting a click — the reviewer's real work still lives in the
// FIFO queue below.
function CounterCard({
  icon: Icon,
  tone,
  label,
  value,
}: {
  icon: typeof CheckCircle;
  tone: "success" | "destructive";
  label: string;
  value: number;
}) {
  const toneClass =
    tone === "success"
      ? "border-[color:var(--status-success-border)] bg-[color:var(--status-success-bg)] text-[color:var(--status-success-text)]"
      : "border-[color:var(--status-error-border)] bg-[color:var(--status-error-bg)] text-[color:var(--status-error-text)]";
  return (
    <div
      className={
        "flex items-center gap-3 rounded-lg border p-4 shadow-xs " + toneClass
      }
    >
      <Icon className="h-6 w-6 shrink-0" weight="fill" aria-hidden />
      <div className="min-w-0">
        <p className="font-mono text-[10px] uppercase tracking-wide opacity-80">
          {label}
        </p>
        <p className="text-2xl font-semibold tabular-nums">{value}</p>
      </div>
    </div>
  );
}
