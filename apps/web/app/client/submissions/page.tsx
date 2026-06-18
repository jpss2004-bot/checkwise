"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowsClockwise,
  ChatCircle,
  FileArrowDown,
  MagnifyingGlass,
} from "@phosphor-icons/react";

import { Surface } from "@/components/checkwise/dashboard/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable, type DataTableColumn } from "@/components/ui/data-table";
import { Select } from "@/components/ui/select";

import { ClientShell } from "../_shell";
import { VendorRef } from "@/components/checkwise/vendor-ref";
import { PeriodPicker } from "@/components/checkwise/period-picker";
import {
  fetchClientSubmissionDocumentBlob,
  listClientSubmissions,
  listClientVendors,
  type ClientSubmissionItem,
  type ClientVendorRow,
} from "@/lib/api/client";
import { INSTITUTION_LABELS } from "@/lib/api/portal";
import { statusLabel, statusVariant } from "@/lib/constants/statuses";
import { formatDateTime } from "@/lib/format/datetime";

// Filter dropdown order matches the reviewer workflow: actionable first,
// then resolved. Labels come from the canonical statusLabel() so this
// table reads the same word as the calendar, dashboard and reports —
// no local copy to drift (previously re-introduced raw "Rechazado" /
// "Prevalidado", 2026-06-10 vocabulary unification).
const STATUS_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: "", label: "Todos los estados" },
  // "En revisión" is a synthetic collapsed value: the backend expands it to
  // recibido / pendiente_revision / prevalidado (which all read "En revisión"
  // to the client). Filtering by the single raw pendiente_revision used to
  // hide ~2/3 of the in-review queue (audit P2.11).
  { value: "en_revision", label: "En revisión" },
  ...(
    [
      "requiere_aclaracion",
      "posible_mismatch",
      "rechazado",
      "aprobado",
      "vencido",
      "excepcion_legal",
      "no_aplica",
    ] as const
  ).map((value) => ({ value, label: statusLabel(value) })),
];

// Institution dropdown options. Mirrors the canonical INSTITUTION_LABELS
// map exported by the portal API client so any future institution
// addition flows through a single source of truth.
const INSTITUTION_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: "", label: "Todas las instituciones" },
  { value: "sat", label: INSTITUTION_LABELS.sat },
  { value: "imss", label: INSTITUTION_LABELS.imss },
  { value: "infonavit", label: INSTITUTION_LABELS.infonavit },
  { value: "stps_repse", label: INSTITUTION_LABELS.stps_repse },
  { value: "interno_cliente", label: INSTITUTION_LABELS.interno_cliente },
];

const PAGE_SIZE_OPTIONS = [25, 50, 100, 200, 500] as const;
const DEFAULT_LIMIT = 100;

type SubmissionFilters = {
  vendor_id: string;
  status: string;
  institution: string;
  period_key: string;
  limit: number;
};

// Seed the filter state from the URL so notification / calendar deep-links
// such as ``/client/submissions?vendor_id=…&status=rechazado`` land
// pre-filtered (repairs the alert→act loop). Falls back to sensible
// defaults when a param is absent or malformed.
function readFiltersFromUrl(
  sp: ReturnType<typeof useSearchParams>,
): SubmissionFilters {
  const limitRaw = Number(sp?.get("limit"));
  const limit = (PAGE_SIZE_OPTIONS as readonly number[]).includes(limitRaw)
    ? limitRaw
    : DEFAULT_LIMIT;
  return {
    vendor_id: sp?.get("vendor_id") ?? "",
    status: sp?.get("status") ?? "",
    institution: sp?.get("institution") ?? "",
    period_key: sp?.get("period_key") ?? sp?.get("period") ?? "",
    limit,
  };
}

export default function ClientSubmissionsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  // ``?client_id`` is the inspection-scope param the shell threads through
  // nav; preserve it on every URL we write and pass it to the API so a
  // multi-client / internal user stays on the tenant they're viewing.
  const clientId = searchParams?.get("client_id") ?? "";
  const [rows, setRows] = useState<ClientSubmissionItem[] | null>(null);
  // True total from the API so the count is honest when the page is capped.
  const [total, setTotal] = useState(0);
  const [vendors, setVendors] = useState<ClientVendorRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Bumped by the table's "Reintentar" so a failed fetch can re-run even
  // when the URL (and therefore the filter params) hasn't changed.
  const [reloadKey, setReloadKey] = useState(0);
  const [filters, setFilters] = useState<SubmissionFilters>(() =>
    readFiltersFromUrl(searchParams),
  );

  // Load the vendor list ONCE so the dropdown can render names instead
  // of raw UUIDs. ``listClientVendors`` is the same endpoint the
  // vendors page uses, scoped to the active client.
  useEffect(() => {
    let cancelled = false;
    listClientVendors(clientId ? { client_id: clientId } : undefined)
      .then((data) => {
        if (cancelled) return;
        setVendors(data.items);
      })
      .catch(() => {
        // Non-fatal — the dropdown just shows the "all proveedores"
        // option and the table still renders.
      });
    return () => {
      cancelled = true;
    };
  }, [clientId]);

  // Single source of truth for fetching: re-run whenever the URL's filter
  // params change (mount, deep-link, Aplicar, page-size). Re-seeding the
  // form from the URL keeps the controls and the results in lockstep and
  // sidesteps the previous stale-closure page-size race.
  const spKey = searchParams?.toString() ?? "";
  useEffect(() => {
    const next = readFiltersFromUrl(searchParams);
    setFilters(next);
    let cancelled = false;
    setLoading(true);
    setError(null);
    listClientSubmissions({
      client_id: clientId || undefined,
      vendor_id: next.vendor_id || undefined,
      status: next.status || undefined,
      institution: next.institution || undefined,
      period_key: next.period_key || undefined,
      limit: next.limit,
    })
      .then((data) => {
        if (cancelled) return;
        setRows(data.items);
        setTotal(data.total ?? data.items.length);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(
          err instanceof Error ? err.message : "Error al cargar entregas.",
        );
        setRows(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spKey, clientId, reloadKey]);

  // Apply = write the active filters to the URL; the effect above does
  // the fetch. Preserves ``client_id`` and omits default/empty values so
  // shared URLs stay clean.
  const applyFilters = useCallback(
    (next: SubmissionFilters) => {
      const params = new URLSearchParams();
      if (clientId) params.set("client_id", clientId);
      if (next.vendor_id) params.set("vendor_id", next.vendor_id);
      if (next.status) params.set("status", next.status);
      if (next.institution) params.set("institution", next.institution);
      if (next.period_key) params.set("period_key", next.period_key);
      if (next.limit !== DEFAULT_LIMIT) params.set("limit", String(next.limit));
      const query = params.toString();
      router.replace(
        query ? `/client/submissions?${query}` : "/client/submissions",
        { scroll: false },
      );
    },
    [clientId, router],
  );

  const sortedVendors = [...vendors].sort((a, b) =>
    // Null-guard: a missing vendor_name from the API must not crash the
    // whole page (audit 2026-06-09).
    (a.vendor_name ?? "").localeCompare(b.vendor_name ?? "", "es"),
  );

  return (
    <ClientShell
      title="Entregas"
      description="Búsqueda y filtrado sobre todas las cargas hechas por los proveedores."
    >
      <div className="space-y-5">
        <Surface title="Filtros">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              applyFilters(filters);
            }}
            className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
          >
            <FilterField label="Proveedor">
              <Select
                value={filters.vendor_id}
                onChange={(e) =>
                  setFilters({ ...filters, vendor_id: e.target.value })
                }
              >
                <option value="">Todos los proveedores</option>
                {sortedVendors.map((v) => (
                  <option key={v.vendor_id} value={v.vendor_id}>
                    {v.vendor_name}
                  </option>
                ))}
              </Select>
            </FilterField>
            <FilterField label="Estado">
              <Select
                value={filters.status}
                onChange={(e) =>
                  setFilters({ ...filters, status: e.target.value })
                }
              >
                {STATUS_OPTIONS.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </Select>
            </FilterField>
            <FilterField label="Institución">
              <Select
                value={filters.institution}
                onChange={(e) =>
                  setFilters({ ...filters, institution: e.target.value })
                }
              >
                {INSTITUTION_OPTIONS.map((i) => (
                  <option key={i.value} value={i.value}>
                    {i.label}
                  </option>
                ))}
              </Select>
            </FilterField>
            <FilterField label="Periodo">
              <PeriodPicker
                value={filters.period_key}
                onChange={(periodKey) =>
                  setFilters({ ...filters, period_key: periodKey })
                }
              />
            </FilterField>
            <div className="sm:col-span-2 lg:col-span-4">
              <Button type="submit" size="sm" loading={loading}>
                <MagnifyingGlass className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
                Aplicar filtros
              </Button>
            </div>
          </form>
        </Surface>

        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)] px-4 py-2">
          <p className="font-mono text-[11px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
            {total > (rows?.length ?? 0)
              ? `Mostrando ${rows?.length ?? 0} de ${total} entregas`
              : `${rows?.length ?? 0} entregas mostradas`}
          </p>
          <label className="inline-flex items-center gap-2 text-[12px] text-[color:var(--text-secondary)]">
            <span className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
              Mostrar
            </span>
            <Select
              value={String(filters.limit)}
              onChange={(e) => {
                const nextLimit = Number(e.target.value) || DEFAULT_LIMIT;
                // Write the new size to the URL; the fetch effect re-runs
                // with the fresh value (no stale-closure race).
                applyFilters({ ...filters, limit: nextLimit });
              }}
              className="h-8 w-20 py-0 text-[12px]"
            >
              {PAGE_SIZE_OPTIONS.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </Select>
            <span className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
              por página
            </span>
          </label>
        </div>

        <DataTable<ClientSubmissionItem>
          items={rows}
          loading={loading}
          error={error}
          onRetry={() => setReloadKey((k) => k + 1)}
          columns={SUBMISSIONS_COLUMNS}
          rowKey={(row) => row.submission_id}
          mobileCards
          ariaLabel="Entregas del portafolio"
          emptyTitle="Sin entregas con esos filtros"
          emptyDescription="Modifica los filtros para ver más resultados."
          metaBadge={
            total > (rows?.length ?? 0)
              ? `${rows?.length ?? 0} de ${total}`
              : `${rows?.length ?? 0} entregas`
          }
          skeletonRows={8}
        />
      </div>
    </ClientShell>
  );
}

const SUBMISSIONS_COLUMNS: DataTableColumn<ClientSubmissionItem>[] = [
  {
    id: "when",
    header: "Cuándo",
    width: "140px",
    cell: (row) => (
      <span className="font-mono text-[11px] tabular-nums text-[color:var(--text-secondary)]">
        {formatDateTime(row.submitted_at, {
          day: "2-digit",
          month: "short",
          hour: "2-digit",
          minute: "2-digit",
        })}
      </span>
    ),
  },
  {
    id: "vendor",
    header: "Proveedor",
    cell: (row) => (
      <p className="text-[13px] font-medium text-[color:var(--text-primary)]">
        <VendorRef vendorId={row.vendor_id} vendorName={row.vendor_name} />
      </p>
    ),
  },
  {
    id: "institution",
    header: "Institución",
    width: "120px",
    cell: (row) => (
      <span className="text-[12px] text-[color:var(--text-secondary)]">
        {row.institution
          ? INSTITUTION_LABELS[row.institution] ?? row.institution
          : "—"}
      </span>
    ),
  },
  {
    id: "requirement",
    header: "Requisito",
    cell: (row) => (
      <span className="text-[12px] text-[color:var(--text-primary)]">
        {row.requirement_name ?? row.requirement_code ?? "—"}
      </span>
    ),
  },
  {
    id: "period",
    header: "Periodo",
    width: "100px",
    cell: (row) => (
      <span className="font-mono text-[11px] tabular-nums">
        {row.period_key ?? "—"}
      </span>
    ),
  },
  {
    id: "status",
    header: "Estado",
    width: "140px",
    cell: (row) => (
      <Badge variant={statusVariant(row.status)}>
        {statusLabel(row.status)}
      </Badge>
    ),
  },
  {
    id: "file",
    header: "Archivo / Nota",
    cell: (row) => (
      <div className="text-[11px]">
        {row.filename ? (
          <SubmissionFileButton
            submissionId={row.submission_id}
            filename={row.filename}
          />
        ) : null}
        {row.reviewer_note ? (
          <p className="mt-0.5 flex items-center gap-1 truncate text-[color:var(--text-secondary)]">
            <ChatCircle
              className="h-3 w-3 shrink-0 text-[color:var(--text-tertiary)]"
              weight="bold"
              aria-hidden
            />
            {row.reviewer_note}
          </p>
        ) : null}
        {!row.filename && !row.reviewer_note ? "—" : null}
      </div>
    ),
  },
  {
    id: "lineage",
    header: "Intentos",
    width: "200px",
    cell: (row) => (
      <LineageBadges
        supersedes={row.supersedes_submission_id}
        supersededBy={row.superseded_by_submission_id}
      />
    ),
  },
];

// Entregas is the system of record for "what did this provider deliver";
// a Legal Director / auditor must be able to OPEN the file from here to
// verify it instead of leaving for the vendor expediente (audit P2.12).
// The filename is a button that fetches the authenticated blob (the staff
// JWT can't ride a plain navigation) and opens it in a new tab.
function SubmissionFileButton({
  submissionId,
  filename,
}: {
  submissionId: string;
  filename: string;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  async function open() {
    if (busy) return;
    setBusy(true);
    setErr(null);
    try {
      const url = await fetchClientSubmissionDocumentBlob(submissionId);
      const win = window.open(url, "_blank", "noopener,noreferrer");
      if (!win) setErr("Permite las ventanas emergentes para abrir el archivo.");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "No se pudo abrir el archivo.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div>
      <button
        type="button"
        onClick={open}
        disabled={busy}
        title={`Abrir ${filename}`}
        className="flex max-w-full items-center gap-1 truncate rounded-sm text-left text-[color:var(--text-link)] hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)] focus-visible:ring-offset-1 disabled:opacity-60"
      >
        <FileArrowDown className="h-3 w-3 shrink-0" weight="bold" aria-hidden />
        <span className="truncate">{busy ? "Abriendo…" : filename}</span>
      </button>
      {err ? (
        <p
          role="alert"
          className="mt-0.5 text-[10px] text-[color:var(--status-error-text)]"
        >
          {err}
        </p>
      ) : null}
    </div>
  );
}

function FilterField({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block space-y-1">
      <span className="block font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
        {label}
      </span>
      {children}
    </label>
  );
}

// Phase 3 / Slice 3A — the previous version of this cell displayed the
// truncated supersedes/superseded_by submission UUIDs ("↓ a1b2c3d4"),
// which are operational identifiers a client should never need. The
// canonical fact we want to surface is "this is a re-upload" or "this
// was already replaced" — show that in plain Spanish.
function LineageBadges({
  supersedes,
  supersededBy,
}: {
  supersedes: string | null;
  supersededBy: string | null;
}) {
  if (!supersedes && !supersededBy) {
    return <span className="text-[color:var(--text-tertiary)]">—</span>;
  }
  return (
    <div className="flex flex-col gap-1">
      {supersedes ? (
        <span className="inline-flex w-fit items-center gap-1 rounded-full bg-[color:var(--surface-sunken)] px-2 py-0.5 text-[10px] font-medium text-[color:var(--text-secondary)]">
          <ArrowsClockwise
            className="h-3 w-3 shrink-0"
            weight="bold"
            aria-hidden="true"
          />
          Reemplaza intento anterior
        </span>
      ) : null}
      {supersededBy ? (
        <span className="inline-flex w-fit items-center gap-1 rounded-full bg-[color:var(--surface-sunken)] px-2 py-0.5 text-[10px] font-medium text-[color:var(--text-secondary)]">
          <ArrowsClockwise
            className="h-3 w-3 shrink-0"
            weight="bold"
            aria-hidden="true"
          />
          Reemplazado por intento posterior
        </span>
      ) : null}
    </div>
  );
}
