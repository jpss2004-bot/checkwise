"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
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
import { Button } from "@/components/ui/button";
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
  getReviewerQueueFacets,
  ReviewerApiError,
  type QueueFacets,
  type QueueItem,
  type QueueResponse,
} from "@/lib/api/reviewer";

const REVIEWER_ROLES = ["reviewer", "internal_admin"] as const;

// Audit fix 2026-06-10 — the queue used to cap at the backend's default
// 50 rows with no hint that more existed. We now request the backend
// maximum per page and paginate with the keyset cursor.
const PAGE_LIMIT = 100;

const FILTER_KEYS = ["all", "in_review", "mismatch", "clarify"] as const;

type FilterKey = (typeof FILTER_KEYS)[number];

const FILTER_LABEL: Record<FilterKey, string> = {
  all: "Todos",
  in_review: "Pendiente de revisión",
  mismatch: "Posible inconsistencia",
  clarify: "Aclaración",
};

/**
 * Audit fix 2026-06-10 — tabs now filter SERVER-side via the queue
 * endpoint's ``status`` param, so counts and pagination are truthful
 * instead of being computed over a truncated page.
 *
 * The param accepts a single status, so:
 * - "Todos" omits it (backend default = every actionable status:
 *   recibido + pendiente_revision + prevalidado + posible_mismatch).
 * - "Pendiente de revisión" narrows to ``pendiente_revision`` (the
 *   old client-side tab also swept in recibido/prevalidado; those
 *   remain visible under "Todos").
 * - "Aclaración" narrows to ``requiere_aclaracion`` — which the
 *   default queue intentionally excludes, so this tab now actually
 *   shows those rows (it was always empty before).
 * - "Posible inconsistencia" has NO server equivalent because it
 *   keys off the per-item ``has_mismatch`` inspection flag, not just
 *   the status — it stays a client-side filter over LOADED items and
 *   is labeled as such.
 */
const FILTER_SERVER_STATUS: Partial<Record<FilterKey, RequirementStatus>> = {
  in_review: "pendiente_revision",
  clarify: "requiere_aclaracion",
};

function isMismatchItem(item: QueueItem): boolean {
  return item.has_mismatch || item.status === "posible_mismatch";
}

function parseFilterParam(raw: string | null): FilterKey {
  return (FILTER_KEYS as readonly string[]).includes(raw ?? "")
    ? (raw as FilterKey)
    : "all";
}

// Phase A document revalidation — authenticity-risk filter. Empty
// string = "Todos" (param omitted, backend returns every row).
const RISK_VALUES = ["clean", "suspicious", "high_risk"] as const;

type RiskKey = (typeof RISK_VALUES)[number];

const RISK_LABEL: Record<RiskKey, string> = {
  clean: "Limpio",
  suspicious: "Sospechoso",
  high_risk: "Alto riesgo",
};

function parseRiskParam(raw: string | null): RiskKey | "" {
  return (RISK_VALUES as readonly string[]).includes(raw ?? "")
    ? (raw as RiskKey)
    : "";
}

const RFC_VALUES = [
  "match",
  "homoclave_mismatch",
  "mismatch",
  "absent",
  "no_expected",
] as const;

type RfcKey = NonNullable<QueueItem["rfc_alignment"]>;

const RFC_LABEL: Record<RfcKey, string> = {
  match: "Coincide",
  homoclave_mismatch: "Homoclave dudosa",
  mismatch: "No coincide",
  absent: "No detectado",
  no_expected: "Sin RFC esperado",
};

function parseRfcParam(raw: string | null): RfcKey | "" {
  return (RFC_VALUES as readonly string[]).includes(raw ?? "")
    ? (raw as RfcKey)
    : "";
}

// SLA aging thresholds (hours). <72h is on target, 72h–168h is at
// risk (amber), >168h (7 days) is out of SLA (red).
const SLA_WARNING_HOURS = 72;
const SLA_BREACH_HOURS = 168;

function ageSla(hours: number): { className: string; title: string } {
  if (hours > SLA_BREACH_HOURS) {
    return {
      className: "text-[color:var(--status-error-text)]",
      title: "Fuera de SLA: más de 7 días esperando decisión",
    };
  }
  if (hours >= SLA_WARNING_HOURS) {
    return {
      className: "text-[color:var(--status-warning-text)]",
      title: "En riesgo: entre 3 y 7 días esperando decisión",
    };
  }
  return {
    className: "text-[color:var(--text-secondary)]",
    title: "Dentro del objetivo: menos de 3 días en cola",
  };
}

export default function ReviewerQueuePage() {
  // useSearchParams must live under a Suspense boundary so Next can
  // statically prerender the shell (same pattern as /admin/buscar).
  return (
    <AdminShell unframed>
      <Suspense fallback={null}>
        <ReviewerQueueBody />
      </Suspense>
    </AdminShell>
  );
}

function ReviewerQueueBody() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [session, setSession] = useState<AdminSession | null>(null);
  const [queue, setQueue] = useState<QueueResponse | null>(null);
  const [facets, setFacets] = useState<QueueFacets | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  // Audit fix 2026-06-10 — tab + institution seed from the URL so
  // back-navigation from a decision screen restores the filters
  // instead of resetting to "Todos / todas las instituciones".
  const [filter, setFilter] = useState<FilterKey>(() =>
    parseFilterParam(searchParams?.get("tab") ?? null),
  );
  // Institution filter — empty string means "all institutions" and
  // omits the query param so the backend returns every row. The
  // dropdown options are driven by INSTITUTION_LABELS so they stay in
  // sync with portal/calendar and client/submissions.
  const [institution, setInstitution] = useState<string>(
    () => searchParams?.get("institution") ?? "",
  );
  // Phase A — authenticity-risk filter. Server-side (the queue
  // endpoint's ``risk`` param), URL-persisted like tab/institution.
  const [risk, setRisk] = useState<RiskKey | "">(() =>
    parseRiskParam(searchParams?.get("risk") ?? null),
  );
  const [rfc, setRfc] = useState<RfcKey | "">(() =>
    parseRfcParam(searchParams?.get("rfc") ?? null),
  );
  const [clientId, setClientId] = useState<string>(
    () => searchParams?.get("client_id") ?? "",
  );
  const [vendorId, setVendorId] = useState<string>(
    () => searchParams?.get("vendor_id") ?? "",
  );
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadMoreError, setLoadMoreError] = useState(false);
  // Display-only sort. The server always returns oldest-first (FIFO);
  // "más recientes" just reverses the LOADED rows client-side.
  const [newestFirst, setNewestFirst] = useState(false);

  const serverStatus = FILTER_SERVER_STATUS[filter];
  const visibleVendors = useMemo(() => {
    const vendors = facets?.vendors ?? [];
    return clientId
      ? vendors.filter((vendor) => vendor.client_id === clientId)
      : vendors;
  }, [clientId, facets]);

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
    getReviewerQueueFacets(session.access_token)
      .then((payload) => {
        if (!cancelled) setFacets(payload);
      })
      .catch((err) => {
        if (err instanceof ReviewerApiError && err.status === 401) {
          clearAdminSession();
          router.replace("/login");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [session, router]);

  useEffect(() => {
    if (!clientId || !vendorId || visibleVendors.some((v) => v.id === vendorId)) {
      return;
    }
    setVendorId("");
  }, [clientId, vendorId, visibleVendors]);

  // Mirror tab + institution + risk/provider/client into the URL (replace, not push,
  // so the history stack stays one entry per page visit).
  useEffect(() => {
    const params = new URLSearchParams();
    if (filter !== "all") params.set("tab", filter);
    if (institution) params.set("institution", institution);
    if (risk) params.set("risk", risk);
    if (rfc) params.set("rfc", rfc);
    if (clientId) params.set("client_id", clientId);
    if (vendorId) params.set("vendor_id", vendorId);
    const qs = params.toString();
    router.replace(`/admin/reviewer${qs ? `?${qs}` : ""}`, { scroll: false });
  }, [clientId, filter, institution, rfc, risk, router, vendorId]);

  // First page fetch. Depends on `serverStatus` (not `filter`) so
  // toggling between "Todos" and the client-side mismatch filter
  // reuses the already-loaded pages instead of refetching; changing
  // to a server-filtered tab resets the list + cursor and refetches.
  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setLoadMoreError(false);
    getReviewerQueue(session.access_token, {
      status: serverStatus,
      institution: institution || undefined,
      risk: risk || undefined,
      rfc: rfc || undefined,
      client_id: clientId || undefined,
      vendor_id: vendorId || undefined,
      limit: PAGE_LIMIT,
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
  }, [clientId, session, reloadKey, router, institution, serverStatus, risk, rfc, vendorId]);

  const retry = useCallback(() => setReloadKey((k) => k + 1), []);

  // Next-page fetch — APPENDS to the loaded list under the same
  // filters; the scroll position is untouched. The functional update
  // only merges when the cursor we requested is still the queue's
  // current cursor, so a tab/institution change that races a slow
  // load-more can't splice a stale page into the fresh list.
  const loadMore = useCallback(() => {
    if (!session || !queue?.next_cursor || loadingMore) return;
    const requestedCursor = queue.next_cursor;
    setLoadingMore(true);
    setLoadMoreError(false);
    getReviewerQueue(session.access_token, {
      status: serverStatus,
      institution: institution || undefined,
      risk: risk || undefined,
      rfc: rfc || undefined,
      client_id: clientId || undefined,
      vendor_id: vendorId || undefined,
      limit: PAGE_LIMIT,
      cursor: requestedCursor,
    })
      .then((payload) => {
        setQueue((prev) =>
          prev && prev.next_cursor === requestedCursor
            ? { ...payload, items: [...prev.items, ...payload.items] }
            : prev,
        );
      })
      .catch((err) => {
        if (err instanceof ReviewerApiError && err.status === 401) {
          clearAdminSession();
          router.replace("/login");
          return;
        }
        setLoadMoreError(true);
      })
      .finally(() => setLoadingMore(false));
  }, [clientId, session, queue, loadingMore, serverStatus, institution, risk, rfc, vendorId, router]);

  // F1: logout is now provided by the AdminShell header, so this
  // page no longer renders its own Cerrar sesión action.

  const items = useMemo(() => queue?.items ?? [], [queue]);
  const filteredItems = useMemo(
    () => (filter === "mismatch" ? items.filter(isMismatchItem) : items),
    [items, filter],
  );
  const displayItems = useMemo(
    () => (newestFirst ? [...filteredItems].reverse() : filteredItems),
    [filteredItems, newestFirst],
  );

  if (!session) return null;

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-5 py-8">
      <PageHeader
        eyebrow="Mesa de revisión"
        title="Documentos por revisar"
        description="Empieza por lo más viejo. Cada documento espera tu decisión humana. La automatización no aprueba ni rechaza nada."
      />

      {/* Institution scope filter. Sits above the status tabs so the
          reviewer narrows by authority (SAT / IMSS / INFONAVIT / STPS)
          before drilling into Pendiente / Inconsistencia / Aclaración.
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
        {/* Phase A — authenticity-risk filter. Server-side via the
            queue endpoint's ``risk`` param; "" means all rows. */}
        <label
          htmlFor="reviewer-risk"
          className="font-mono text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-tertiary)]"
        >
          Riesgo
        </label>
        <Select
          id="reviewer-risk"
          value={risk}
          onChange={(e) => setRisk(parseRiskParam(e.target.value))}
          className="h-9 max-w-[180px] text-[13px]"
          aria-label="Filtrar bandeja por riesgo de autenticidad"
        >
          <option value="">Todos</option>
          <option value="high_risk">{RISK_LABEL.high_risk}</option>
          <option value="suspicious">{RISK_LABEL.suspicious}</option>
          <option value="clean">{RISK_LABEL.clean}</option>
        </Select>
        <label
          htmlFor="reviewer-client"
          className="font-mono text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-tertiary)]"
        >
          Cliente
        </label>
        <Select
          id="reviewer-client"
          value={clientId}
          onChange={(e) => setClientId(e.target.value)}
          className="h-9 max-w-[240px] text-[13px]"
          aria-label="Filtrar bandeja por cliente"
        >
          <option value="">Todos los clientes</option>
          {(facets?.clients ?? []).map((client) => (
            <option key={client.id} value={client.id}>
              {client.name}
            </option>
          ))}
        </Select>
        <label
          htmlFor="reviewer-vendor"
          className="font-mono text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-tertiary)]"
        >
          Proveedor
        </label>
        <Select
          id="reviewer-vendor"
          value={vendorId}
          onChange={(e) => setVendorId(e.target.value)}
          className="h-9 max-w-[280px] text-[13px]"
          aria-label="Filtrar bandeja por proveedor"
        >
          <option value="">Todos los proveedores</option>
          {visibleVendors.map((vendor) => (
            <option key={vendor.id} value={vendor.id}>
              {vendor.rfc ? `${vendor.name} · ${vendor.rfc}` : vendor.name}
            </option>
          ))}
        </Select>
        <label
          htmlFor="reviewer-rfc"
          className="font-mono text-[10px] uppercase tracking-[0.2em] text-[color:var(--text-tertiary)]"
        >
          RFC
        </label>
        <Select
          id="reviewer-rfc"
          value={rfc}
          onChange={(e) => setRfc(parseRfcParam(e.target.value))}
          className="h-9 max-w-[210px] text-[13px]"
          aria-label="Filtrar bandeja por resultado RFC"
        >
          <option value="">Todos</option>
          {RFC_VALUES.map((value) => (
            <option key={value} value={value}>
              {RFC_LABEL[value]}
            </option>
          ))}
        </Select>
        {institution || risk || rfc || clientId || vendorId ? (
          <button
            type="button"
            onClick={() => {
              setInstitution("");
              setRisk("");
              setRfc("");
              setClientId("");
              setVendorId("");
            }}
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
      ) : (
        <section
          aria-label="Cola de documentos por revisar"
          className="cw-fade-up rounded-lg border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] shadow-xs"
        >
          <header className="flex flex-wrap items-center justify-between gap-3 border-b border-[color:var(--border-subtle)] px-5 py-3">
            <Tabs value={filter} onValueChange={(v) => setFilter(v as FilterKey)}>
              <TabsList>
                {FILTER_KEYS.map((key) => (
                  <TabsTrigger
                    key={key}
                    value={key}
                    title={
                      key === "mismatch"
                        ? "Filtra sobre los documentos ya cargados"
                        : undefined
                    }
                  >
                    <span>{FILTER_LABEL[key]}</span>
                    {/* Only the ACTIVE tab shows a count: the server
                        count for that filter (or, for the client-side
                        mismatch filter, the matches among loaded rows).
                        Inactive tabs show none — we no longer fake
                        per-tab totals from a truncated page. */}
                    {filter === key && queue ? (
                      <span className="ml-1.5 font-mono text-[10px] tabular-nums opacity-70">
                        {key === "mismatch" ? filteredItems.length : queue.total}
                      </span>
                    ) : null}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
            <button
              type="button"
              onClick={() => setNewestFirst((v) => !v)}
              title='El orden "más recientes" se aplica sobre los documentos cargados; el servidor entrega lo más viejo primero.'
              className="inline-flex items-center whitespace-nowrap rounded-full border border-[color:var(--border-default)] px-2.5 py-0.5 text-[11px] font-medium text-[color:var(--text-secondary)] transition-colors duration-fast hover:border-[color:var(--border-strong)] hover:text-[color:var(--text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]/40"
            >
              {newestFirst
                ? "Más recientes primero (cargados)"
                : "Más viejos primero"}
            </button>
          </header>

          {displayItems.length === 0 ? (
            <div className="px-5 py-10">
              {filter === "all" && items.length === 0 ? (
                <EmptyState
                  icon={Tray}
                  title="No hay documentos por revisar"
                  description="Cuando un proveedor cargue documentación nueva, aparecerá aquí en orden de llegada."
                  variant="muted"
                />
              ) : (
                <EmptyState
                  icon={Tray}
                  title={`Sin resultados en "${FILTER_LABEL[filter]}"`}
                  description={
                    filter === "mismatch"
                      ? "Ningún documento cargado tiene posible inconsistencia. Carga más documentos o cambia el filtro."
                      : "Cambia el filtro para ver otros documentos en la cola."
                  }
                  variant="muted"
                />
              )}
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[160px]">Estado</TableHead>
                  <TableHead
                    className="w-[110px]"
                    title="Riesgo de autenticidad según el análisis forense del PDF"
                  >
                    Riesgo
                  </TableHead>
                  <TableHead
                    className="w-[130px]"
                    title="Comparación advisory entre RFC detectado y RFC del proveedor"
                  >
                    RFC
                  </TableHead>
                  <TableHead>Documento</TableHead>
                  <TableHead>Institución · periodo</TableHead>
                  <TableHead>Proveedor</TableHead>
                  <TableHead
                    className="w-[120px]"
                    title="Tiempo en cola. Ámbar: más de 3 días. Rojo: más de 7 días."
                  >
                    Edad
                  </TableHead>
                  <TableHead className="w-[40px]" aria-label="Acción" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {displayItems.map((item) => (
                  <QueueTableRow
                    key={item.submission_id}
                    item={item}
                    onOpen={() => router.push(`/admin/reviewer/${item.submission_id}`)}
                  />
                ))}
              </TableBody>
            </Table>
          )}

          {/* Truthful pagination footer: X = rows actually loaded,
              Y = the server's real total under the current filters. */}
          {queue && items.length > 0 ? (
            <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-[color:var(--border-subtle)] px-5 py-3">
              <div className="space-y-0.5">
                <p className="text-[12px] tabular-nums text-[color:var(--text-secondary)]">
                  Mostrando {items.length} de {queue.total} documentos
                  {filter === "mismatch"
                    ? ` · ${filteredItems.length} con posible inconsistencia entre los cargados`
                    : ""}
                </p>
                <p className="text-[11px] text-[color:var(--text-tertiary)]">
                  Edad:{" "}
                  <span className="text-[color:var(--status-warning-text)]">
                    ámbar
                  </span>{" "}
                  más de 3 días ·{" "}
                  <span className="text-[color:var(--status-error-text)]">
                    rojo
                  </span>{" "}
                  más de 7 días en cola
                </p>
              </div>
              {queue.next_cursor ? (
                <div className="flex items-center gap-3">
                  {loadMoreError ? (
                    <span className="text-[12px] text-[color:var(--status-error-text)]">
                      No pudimos cargar más. Intenta de nuevo.
                    </span>
                  ) : null}
                  <Button
                    variant="outline"
                    size="sm"
                    loading={loadingMore}
                    onClick={loadMore}
                  >
                    Cargar más
                  </Button>
                </div>
              ) : null}
            </footer>
          ) : null}
        </section>
      )}
    </div>
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
  const ageSlaTone = ageSla(item.age_hours);
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
      className={`cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[color:var(--border-focus)]/40${
        item.authenticity_risk === "high_risk"
          ? " bg-[color:var(--status-error-bg)]"
          : ""
      }`}
    >
      {/* Phase A — high-risk rows get a left accent so they pop while
          scanning; the bg tint above keeps the whole row warm. The
          accent lives on the first CELL (not the <tr>) because
          border-collapse swallows row-level side borders. */}
      <TableCell
        className={
          item.authenticity_risk === "high_risk"
            ? "border-l-2 border-l-[color:var(--status-error-border)]"
            : undefined
        }
      >
        <div className="flex flex-col gap-1.5">
          <RequirementStatusBadge status={item.status} />
          {item.has_mismatch ? (
            <span className="inline-flex w-max items-center gap-1 rounded-sm border border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-bg)] px-1.5 py-0.5 text-[10px] font-medium text-[color:var(--status-warning-text)]">
              <Warning className="h-3 w-3" weight="fill" aria-hidden />
              Posible inconsistencia
            </span>
          ) : null}
        </div>
      </TableCell>

      <TableCell>
        <RiskBadge risk={item.authenticity_risk} />
      </TableCell>

      <TableCell>
        <RfcBadge alignment={item.rfc_alignment} />
      </TableCell>

      <TableCell>
        <p className="font-medium leading-tight text-[color:var(--text-primary)]">
          {item.requirement.name ?? "Documento sin requisito canónico"}
        </p>
        {item.signal_count > 0 ? (
          <p className="mt-1 text-[11px] text-[color:var(--text-tertiary)]">
            {item.signal_count === 1
              ? "1 señal automática"
              : `${item.signal_count} señales automáticas`}
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
              surface="admin"
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
        {/* SLA aging — amber past 72h, red past 168h (7 days). The
            title carries the meaning for hover/assistive tech. */}
        <span
          title={ageSlaTone.title}
          className={`inline-flex items-center gap-1 font-mono text-[11px] tabular-nums ${ageSlaTone.className}`}
        >
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

/**
 * Phase A — compact authenticity-risk badge for queue rows. Clean rows
 * stay visually QUIET (outline badge with a small success dot) so the
 * eye only catches the warning/destructive states; "—" for rows the
 * fail-open analyzer never touched.
 */
function RiskBadge({ risk }: { risk: QueueItem["authenticity_risk"] }) {
  if (!risk) {
    return (
      <span
        className="text-[color:var(--text-tertiary)]"
        title="Sin análisis forense"
        aria-label="Sin análisis forense"
      >
        —
      </span>
    );
  }
  if (risk === "clean") {
    return (
      <Badge variant="outline" className="whitespace-nowrap">
        <span
          aria-hidden
          className="h-1.5 w-1.5 shrink-0 rounded-full bg-[color:var(--status-success-text)]"
        />
        {RISK_LABEL.clean}
      </Badge>
    );
  }
  return (
    <Badge
      variant={risk === "high_risk" ? "destructive" : "warning"}
      className="whitespace-nowrap"
    >
      <span
        aria-hidden
        className={`h-1.5 w-1.5 shrink-0 rounded-full ${
          risk === "high_risk"
            ? "bg-[color:var(--status-error-text)]"
            : "bg-[color:var(--status-warning-text)]"
        }`}
      />
      {RISK_LABEL[risk]}
    </Badge>
  );
}

function RfcBadge({ alignment }: { alignment: QueueItem["rfc_alignment"] }) {
  if (!alignment) {
    return (
      <span
        className="text-[color:var(--text-tertiary)]"
        title="Sin comparación RFC"
        aria-label="Sin comparación RFC"
      >
        —
      </span>
    );
  }
  if (alignment === "match") {
    return (
      <Badge variant="success" className="whitespace-nowrap">
        {RFC_LABEL[alignment]}
      </Badge>
    );
  }
  if (alignment === "mismatch") {
    return (
      <Badge variant="destructive" className="whitespace-nowrap">
        {RFC_LABEL[alignment]}
      </Badge>
    );
  }
  if (alignment === "homoclave_mismatch") {
    return (
      <Badge variant="warning" className="whitespace-nowrap">
        {RFC_LABEL[alignment]}
      </Badge>
    );
  }
  return (
    <Badge variant="secondary" className="whitespace-nowrap">
      {RFC_LABEL[alignment]}
    </Badge>
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
