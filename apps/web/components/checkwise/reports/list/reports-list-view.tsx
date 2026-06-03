"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ChangeEvent,
} from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  ChartLineUp,
  CircleNotch,
  FileText,
  FunnelSimple,
  MagnifyingGlass,
  Sparkle,
  Warning,
  X,
} from "@phosphor-icons/react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  REPORT_AUDIENCE_LABEL,
  REPORT_AUDIENCES,
  REPORT_STATUS_LABEL,
  REPORT_STATUSES,
  type ReportAudience,
  type ReportStatus,
} from "@/lib/reports/constants";
import {
  ReportsApiError,
  createReportFromPreset,
  listPresets,
  listReports,
  type ReportPresetSummary,
  type ReportSummary,
} from "@/lib/api/reports";

/**
 * Shared reports list view — R2.
 *
 * Renders the preset gallery + filter row + report table. Used by
 * /admin/reports and /client/reports route pages, which only differ
 * in which shell wraps this view and what href "Open report" points
 * to. (Both shells happen to route reports through the shared
 * <ReportEditor>, so the editor href is the role-scoped editor
 * route, e.g. /admin/reports/<id> or /client/reports/<id>.)
 *
 * Filter set (R2 v1):
 * - status: Borrador / Activo / Archivado / Todos
 * - audience: only shown when ``showAudienceFilter`` is true
 *   (admin only — client_admins see exactly one audience anyway)
 * - search: title-substring, case-insensitive, client-side
 *
 * Status + audience round-trip to the server via listReports() so
 * pagination stays correct. Search is client-side to keep the
 * keystroke loop instant.
 */
export interface ReportsListViewProps {
  role: "admin" | "client" | "portal";
  /** Where the row's open-report link routes to. */
  editorHrefBase: string;
  /** Where preset creation lands (mirrors editorHrefBase). */
  presetCreateRedirectBase: string;
  /** Title row copy. */
  eyebrowDescription: string;
  /** Show the audience filter dropdown. Default false for client/portal. */
  showAudienceFilter?: boolean;
  /**
   * Optional content rendered between the page header and the preset
   * gallery. Provider portal uses this to mount the Compliance Pulse
   * strip (P1.6) above the report list without forcing a session
   * dependency onto the shared view.
   */
  headerSlot?: React.ReactNode;
  /**
   * Optional opaque identifier (workspace_id, org_id, etc.) shown in
   * the preset-empty state so support can correlate a "no veo plantillas"
   * ticket with the backend's reports.presets_empty INFO log. The shared
   * view stays session-agnostic — callers wire whatever code makes sense
   * for their tier.
   */
  diagnosticCode?: string;
}

export function ReportsListView({
  role,
  editorHrefBase,
  presetCreateRedirectBase,
  eyebrowDescription,
  showAudienceFilter = false,
  headerSlot,
  diagnosticCode,
}: ReportsListViewProps) {
  const router = useRouter();
  const [presets, setPresets] = useState<ReportPresetSummary[] | null>(null);
  const [presetsError, setPresetsError] = useState<string | null>(null);
  const [reports, setReports] = useState<ReportSummary[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState<string | null>(null);

  // ─── Filter state ────────────────────────────────────────────
  const [statusFilter, setStatusFilter] = useState<ReportStatus | "all">("all");
  const [audienceFilter, setAudienceFilter] = useState<ReportAudience | "all">(
    "all",
  );
  const [search, setSearch] = useState("");
  // P2-a (2026-05-20): sort control. The shared list view sorts
  // updated_at desc server-side; we offer client-side reordering on
  // top of that so a provider with several drafts can switch between
  // "newest first" and "A→Z" without paging.
  const [sortBy, setSortBy] = useState<
    "updated_desc" | "updated_asc" | "title_asc"
  >("updated_desc");

  // ─── Preset gallery — loaded once ──────────────────────────
  useEffect(() => {
    let cancelled = false;
    setPresetsError(null);
    listPresets()
      .then((p) => {
        if (cancelled) return;
        setPresets(p.items);
        setPresetsError(null);
      })
      .catch((e: ReportsApiError) => {
        if (cancelled) return;
        // Stage 1 (BL-008): a 401/403 means the user genuinely has no
        // access — we surface that in the page-level access banner.
        // Any other failure (5xx, network, parse) is a real fault that
        // used to be silently swallowed into "tu rol todavía no tiene
        // plantillas asignadas." We now flag it inline so testers can
        // tell broken from intentionally empty.
        if (e.status === 401 || e.status === 403) {
          setError("No tienes acceso al motor de reportes.");
        } else {
          setPresetsError(
            "No pudimos cargar las plantillas. Vuelve a intentarlo en unos segundos.",
          );
        }
        setPresets([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // ─── Report list — reloads on filter change ────────────────
  useEffect(() => {
    let cancelled = false;
    setReports(null);
    listReports({
      status: statusFilter === "all" ? undefined : statusFilter,
      audience: audienceFilter === "all" ? undefined : audienceFilter,
      limit: 100,
    })
      .then((r) => {
        if (cancelled) return;
        setReports(r.items);
        setTotal(r.total);
      })
      .catch((e: ReportsApiError) => {
        if (cancelled) return;
        setError(
          e.status === 401 || e.status === 403
            ? "No tienes acceso al motor de reportes."
            : `No pudimos cargar reportes: ${e.message}`,
        );
        setReports([]);
      });
    return () => {
      cancelled = true;
    };
  }, [statusFilter, audienceFilter]);

  // ─── Client-side title search + sort ───────────────────────
  const filteredReports = useMemo(() => {
    if (!reports) return null;
    const q = search.trim().toLowerCase();
    const matched = q
      ? reports.filter((r) => r.title.toLowerCase().includes(q))
      : reports;
    if (sortBy === "updated_desc") return matched;
    const sorted = [...matched];
    if (sortBy === "updated_asc") {
      sorted.sort(
        (a, b) =>
          new Date(a.updated_at).getTime() - new Date(b.updated_at).getTime(),
      );
    } else if (sortBy === "title_asc") {
      sorted.sort((a, b) =>
        a.title.localeCompare(b.title, "es-MX", { sensitivity: "base" }),
      );
    }
    return sorted;
  }, [reports, search, sortBy]);

  // R1 (one-click select-and-generate): preset cards used to drop the
  // user on a blank editor — they had to write/confirm a prompt and
  // press a second button. The editor already understands
  // ``?autogenerate=1`` (it pulls global.recommended_prompt and fires
  // startGeneration on mount), so we just append the flag on the
  // redirect. Single click → populated canvas.
  const onUsePreset = useCallback(
    async (preset: ReportPresetSummary) => {
      if (creating) return;
      setCreating(preset.id);
      try {
        // No-customization flow: the server generates the populated version
        // inline (hybrid AI + deterministic fallback) while the loading
        // overlay shows, then we land on the finished read-only report —
        // no ?autogenerate=1, no client-side editing.
        const r = await createReportFromPreset(preset.id, true);
        router.push(`${presetCreateRedirectBase}/${r.id}`);
      } catch (e) {
        setCreating(null);
        setError(
          e instanceof ReportsApiError
            ? e.message
            : "Error creando el reporte.",
        );
      }
    },
    [creating, router, presetCreateRedirectBase],
  );

  const clearFilters = useCallback(() => {
    setStatusFilter("all");
    setAudienceFilter("all");
    setSearch("");
    setSortBy("updated_desc");
  }, []);

  const hasActiveFilter =
    statusFilter !== "all" ||
    audienceFilter !== "all" ||
    search.trim() !== "" ||
    sortBy !== "updated_desc";

  // ─── Render ────────────────────────────────────────────────
  return (
    <main className="mx-auto max-w-7xl space-y-6 px-5 py-5">
      {creating ? (
        <div
          className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-4 bg-[color:var(--surface-base)]/80 backdrop-blur-sm"
          role="status"
          aria-live="polite"
        >
          <CircleNotch
            className="h-8 w-8 animate-spin text-[color:var(--text-ai)]"
            weight="bold"
            aria-hidden="true"
          />
          <div className="text-center">
            <p className="text-[14px] font-semibold text-[color:var(--text-primary)]">
              Generando tu reporte…
            </p>
            <p className="mt-1 text-[12px] text-[color:var(--text-secondary)]">
              Estamos preparando el reporte con los datos más recientes de tu portafolio.
            </p>
          </div>
        </div>
      ) : null}
      <header className="cw-fade-up space-y-1">
        <p className="cw-eyebrow">
          {role === "admin"
            ? "Admin · CheckWise"
            : role === "client"
              ? "Cliente · CheckWise"
              : "Centro de cumplimiento"}
        </p>
        <h1 className="text-[26px] font-semibold leading-tight tracking-tight text-[color:var(--text-primary)]">
          Reportes
        </h1>
        <p className="max-w-prose text-[13px] text-[color:var(--text-secondary)]">
          {eyebrowDescription}
        </p>
      </header>

      {headerSlot}

      {error && (
        <Alert variant="warning">
          <AlertTitle className="flex items-center gap-2">
            <Warning className="h-4 w-4" weight="bold" aria-hidden="true" />
            No se pudieron cargar los reportes
          </AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <section className="space-y-3">
        <header className="flex items-baseline justify-between">
          <h2 className="text-[14px] font-semibold tracking-tight text-[color:var(--text-primary)]">
            {role === "admin"
              ? "Plantillas operativas"
              : role === "client"
                ? "Plantillas para dirección"
                : "Plantillas"}
          </h2>
          <span className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
            {presets ? `${presets.length} disponibles` : "—"}
          </span>
        </header>

        {presetsError ? (
          <Alert variant="warning">
            <AlertTitle className="flex items-center gap-2">
              <Warning className="h-4 w-4" weight="bold" aria-hidden="true" />
              No pudimos cargar las plantillas
            </AlertTitle>
            <AlertDescription className="flex flex-wrap items-center justify-between gap-3">
              <span>{presetsError}</span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  setPresets(null);
                  setPresetsError(null);
                  listPresets()
                    .then((p) => {
                      setPresets(p.items);
                      setPresetsError(null);
                    })
                    .catch((e: ReportsApiError) => {
                      if (e.status === 401 || e.status === 403) {
                        setError("No tienes acceso al motor de reportes.");
                      } else {
                        setPresetsError(
                          "No pudimos cargar las plantillas. Vuelve a intentarlo en unos segundos.",
                        );
                      }
                      setPresets([]);
                    });
                }}
              >
                Reintentar
              </Button>
            </AlertDescription>
          </Alert>
        ) : null}

        {presets === null ? (
          <div className="flex items-center gap-2 py-6 text-[12px] text-[color:var(--text-tertiary)]">
            <CircleNotch
              className="h-4 w-4 animate-spin"
              weight="bold"
              aria-hidden="true"
            />
            Cargando plantillas…
          </div>
        ) : presets.length === 0 ? (
          <div className="space-y-2 rounded-md border border-dashed border-[color:var(--border-subtle)] px-4 py-6 text-[12px] text-[color:var(--text-tertiary)]">
            <p>
              Aún no hay reportes disponibles para tu cuenta. Si crees que es
              un error, contáctanos.
            </p>
            {diagnosticCode ? (
              <p className="font-mono text-[11px] text-[color:var(--text-tertiary)]">
                Código de soporte:{" "}
                <span className="select-all text-[color:var(--text-secondary)]">
                  {diagnosticCode}
                </span>
              </p>
            ) : null}
          </div>
        ) : (
          // F4 (2026-05-19 visual audit): first preset is the recommended
          // starting point. Visually distinguishing it gives the user a
          // clear "empieza aquí" without an explicit instruction.
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            {presets.map((p, i) => (
              <PresetCard
                key={p.id}
                preset={p}
                featured={i === 0}
                creating={creating === p.id}
                disabled={creating !== null && creating !== p.id}
                onUse={() => onUsePreset(p)}
              />
            ))}
          </div>
        )}
      </section>

      <section className="space-y-3">
        <header className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-[14px] font-semibold tracking-tight text-[color:var(--text-primary)]">
            Reportes recientes
          </h2>
          <span className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
            {reports
              ? filteredReports && filteredReports.length !== reports.length
                ? `${filteredReports.length} de ${total} · filtrado`
                : `${reports.length} de ${total}`
              : "—"}
          </span>
        </header>

        <FilterBar
          search={search}
          onSearchChange={setSearch}
          statusFilter={statusFilter}
          onStatusChange={setStatusFilter}
          audienceFilter={audienceFilter}
          onAudienceChange={setAudienceFilter}
          showAudienceFilter={showAudienceFilter}
          sortBy={sortBy}
          onSortChange={setSortBy}
          hasActive={hasActiveFilter}
          onClear={clearFilters}
        />

        {reports === null ? (
          <div className="flex items-center gap-2 py-6 text-[12px] text-[color:var(--text-tertiary)]">
            <CircleNotch
              className="h-4 w-4 animate-spin"
              weight="bold"
              aria-hidden="true"
            />
            Cargando reportes…
          </div>
        ) : filteredReports && filteredReports.length === 0 ? (
          <EmptyReports hasFilter={hasActiveFilter} onClear={clearFilters} />
        ) : (
          <div className="overflow-hidden border-t border-b border-[color:var(--border-default)]">
            <table className="min-w-full text-[13px]">
              <thead>
                <tr className="border-b border-[color:var(--border-subtle)]">
                  <th className="cw-eyebrow py-2 pr-4 text-left">Título</th>
                  <th className="cw-eyebrow py-2 pr-4 text-left">Audiencia</th>
                  <th className="cw-eyebrow py-2 pr-4 text-left">Estado</th>
                  <th className="cw-eyebrow py-2 pr-4 text-left">Actualizado</th>
                  <th className="cw-eyebrow py-2 text-right">Abrir</th>
                </tr>
              </thead>
              <tbody>
                {filteredReports!.map((r) => (
                  <ReportRow
                    key={r.id}
                    report={r}
                    editorHref={`${editorHrefBase}/${r.id}`}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}

// ─── Sub-components ────────────────────────────────────────────

function FilterBar({
  search,
  onSearchChange,
  statusFilter,
  onStatusChange,
  audienceFilter,
  onAudienceChange,
  showAudienceFilter,
  sortBy,
  onSortChange,
  hasActive,
  onClear,
}: {
  search: string;
  onSearchChange: (v: string) => void;
  statusFilter: ReportStatus | "all";
  onStatusChange: (v: ReportStatus | "all") => void;
  audienceFilter: ReportAudience | "all";
  onAudienceChange: (v: ReportAudience | "all") => void;
  showAudienceFilter: boolean;
  sortBy: "updated_desc" | "updated_asc" | "title_asc";
  onSortChange: (v: "updated_desc" | "updated_asc" | "title_asc") => void;
  hasActive: boolean;
  onClear: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] px-3 py-2">
      <FunnelSimple
        className="h-4 w-4 text-[color:var(--text-tertiary)]"
        weight="bold"
        aria-hidden="true"
      />

      {/* Search */}
      <label className="flex flex-1 min-w-[180px] items-center gap-2">
        <MagnifyingGlass
          className="h-3.5 w-3.5 text-[color:var(--text-tertiary)]"
          weight="bold"
          aria-hidden="true"
        />
        <input
          type="search"
          value={search}
          onChange={(e: ChangeEvent<HTMLInputElement>) =>
            onSearchChange(e.target.value)
          }
          placeholder="Buscar por título…"
          className="w-full border-0 bg-transparent text-[12px] text-[color:var(--text-primary)] outline-none placeholder:text-[color:var(--text-tertiary)]"
          aria-label="Buscar por título"
        />
      </label>

      {/* Status */}
      <SelectField
        label="Estado"
        value={statusFilter}
        onChange={(v) => onStatusChange(v as ReportStatus | "all")}
        options={[
          { value: "all", label: "Todos" },
          ...REPORT_STATUSES.map((s) => ({
            value: s,
            label: REPORT_STATUS_LABEL[s],
          })),
        ]}
      />

      {/* Audience — admin only */}
      {showAudienceFilter && (
        <SelectField
          label="Audiencia"
          value={audienceFilter}
          onChange={(v) => onAudienceChange(v as ReportAudience | "all")}
          options={[
            { value: "all", label: "Todas" },
            ...REPORT_AUDIENCES.map((a) => ({
              value: a,
              label: REPORT_AUDIENCE_LABEL[a],
            })),
          ]}
        />
      )}

      {/* Sort — P2-a (2026-05-20). Replaces the slot left by the
          provider-hidden Audiencia filter; for admins it sits to the
          right of the audience dropdown. Pure client-side reorder
          on top of the server's updated_at desc default. */}
      <SelectField
        label="Orden"
        value={sortBy}
        onChange={(v) =>
          onSortChange(v as "updated_desc" | "updated_asc" | "title_asc")
        }
        options={[
          { value: "updated_desc", label: "Recientes" },
          { value: "updated_asc", label: "Antiguos" },
          { value: "title_asc", label: "Título A→Z" },
        ]}
      />

      {hasActive && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={onClear}
          title="Limpiar filtros"
        >
          <X className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
          Limpiar
        </Button>
      )}
    </div>
  );
}

function SelectField({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <label className="flex items-center gap-1.5 text-[11px] text-[color:var(--text-tertiary)]">
      <span className="cw-eyebrow">{label}</span>
      <select
        value={value}
        onChange={(e: ChangeEvent<HTMLSelectElement>) => onChange(e.target.value)}
        className="rounded-sm border border-[color:var(--border-default)] bg-[color:var(--surface-page)] px-2 py-1 text-[12px] text-[color:var(--text-primary)] outline-none focus:border-[color:var(--border-focus)]"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function PresetCard({
  preset,
  featured,
  creating,
  disabled,
  onUse,
}: {
  preset: ReportPresetSummary;
  featured?: boolean;
  creating: boolean;
  disabled: boolean;
  onUse: () => void;
}) {
  return (
    <article
      className={
        featured
          ? "relative flex h-full flex-col gap-2 rounded-md border-2 border-[color:var(--text-ai)] bg-[color:var(--surface-raised)] p-4 shadow-[var(--shadow-md)] ring-1 ring-[color:var(--text-ai)]/15"
          : "flex h-full flex-col gap-2 rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-4 shadow-[var(--shadow-sm)]"
      }
    >
      {featured ? (
        <span className="absolute -top-2 left-3 inline-flex items-center gap-1 rounded-full bg-[color:var(--text-ai)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white">
          <Sparkle className="h-3 w-3" weight="fill" aria-hidden="true" />
          Empieza aquí
        </span>
      ) : null}
      <div className="flex items-center gap-2 text-[color:var(--text-ai)]">
        <Sparkle className="h-3.5 w-3.5" weight="fill" aria-hidden="true" />
        <span className="cw-eyebrow text-[color:var(--text-ai)]">
          {REPORT_AUDIENCE_LABEL[preset.audience]}
        </span>
      </div>
      <h3 className="text-[14px] font-semibold leading-tight text-[color:var(--text-primary)]">
        {preset.title}
      </h3>
      <p className="text-[12px] leading-relaxed text-[color:var(--text-secondary)]">
        {preset.description}
      </p>
      <Button
        type="button"
        size="sm"
        variant="default"
        className="mt-auto"
        onClick={onUse}
        disabled={disabled || creating}
      >
        {creating ? (
          <CircleNotch
            className="h-3.5 w-3.5 animate-spin"
            weight="bold"
            aria-hidden="true"
          />
        ) : (
          <Sparkle className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
        )}
        {creating ? "Generando…" : "Generar reporte"}
      </Button>
    </article>
  );
}

function ReportRow({
  report,
  editorHref,
}: {
  report: ReportSummary;
  editorHref: string;
}) {
  return (
    <tr className="border-b border-[color:var(--border-subtle)] last:border-0 hover:bg-[color:var(--surface-hover)]">
      <td className="py-3 pr-4">
        <Link
          href={editorHref}
          className="flex items-center gap-2 text-[13px] font-medium text-[color:var(--text-primary)] hover:underline"
        >
          <FileText
            className="h-4 w-4 text-[color:var(--text-tertiary)]"
            weight="regular"
            aria-hidden="true"
          />
          {report.title}
        </Link>
        {report.description && (
          <p className="mt-0.5 text-[11px] text-[color:var(--text-tertiary)]">
            {report.description}
          </p>
        )}
      </td>
      <td className="py-3 pr-4 text-[12px] text-[color:var(--text-secondary)]">
        {REPORT_AUDIENCE_LABEL[report.audience as ReportAudience]}
      </td>
      <td className="py-3 pr-4">
        <Badge variant={report.status === "active" ? "success" : "outline"}>
          {REPORT_STATUS_LABEL[report.status]}
        </Badge>
      </td>
      <td className="py-3 pr-4 font-mono text-[11px] text-[color:var(--text-tertiary)]">
        {new Date(report.updated_at).toLocaleString("es-MX", {
          dateStyle: "medium",
          timeStyle: "short",
        })}
      </td>
      <td className="py-3 text-right">
        <Link
          href={editorHref}
          aria-label={`Abrir ${report.title}`}
          className="inline-flex items-center justify-center rounded-sm p-1 text-[color:var(--text-tertiary)] hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--text-primary)]"
        >
          <ArrowRight className="h-4 w-4" weight="bold" aria-hidden="true" />
        </Link>
      </td>
    </tr>
  );
}

function EmptyReports({
  hasFilter,
  onClear,
}: {
  hasFilter: boolean;
  onClear: () => void;
}) {
  return (
    <div className="rounded-md border border-dashed border-[color:var(--border-subtle)] py-12 text-center">
      <ChartLineUp
        className="mx-auto mb-2 h-6 w-6 text-[color:var(--text-ai)]"
        weight="regular"
        aria-hidden="true"
      />
      <p className="text-[14px] font-semibold text-[color:var(--text-primary)]">
        {hasFilter ? "Ningún reporte coincide" : "Aún no hay reportes"}
      </p>
      <p className="mx-auto mt-2 max-w-md text-[12px] text-[color:var(--text-secondary)]">
        {hasFilter
          ? "Ajusta los filtros o usa una plantilla para crear el primero."
          : "Usa una de las plantillas arriba para crear el primero."}
      </p>
      {hasFilter && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="mt-4"
          onClick={onClear}
        >
          <X className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
          Limpiar filtros
        </Button>
      )}
    </div>
  );
}
