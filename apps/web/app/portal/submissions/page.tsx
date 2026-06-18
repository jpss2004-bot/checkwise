"use client";

/**
 * Provider portal — submissions index.
 *
 * Jorge feedback (2026-05-21, /portal/dashboard): "ver los documentos
 * que se llevan cargados … ordenados por Institución, Mes y Año".
 *
 * Strictly read-only. The provider can browse what they uploaded, see
 * status at a glance, and drill into a row via the existing
 * /portal/submissions/[submission_id] detail page. We intentionally
 * surface no edit / delete / replace affordance on this page — Jorge
 * called out the risk of accidental alteration, and replacements
 * already have a first-class flow through the upload wizard.
 */

import { useEffect, useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, FileText, FolderOpen, Trash } from "@phosphor-icons/react";

import { PortalAppShell } from "@/components/checkwise/portal/portal-app-shell";
import { RequirementStatusBadge } from "@/components/checkwise/portal/requirement-status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { Select } from "@/components/ui/select";
import { toast } from "@/components/ui/toast";
import {
  INSTITUTION_LABELS,
  MONTH_LABELS_ES,
  PortalApiError,
  cancelWorkspaceSubmission,
  listWorkspaceSubmissions,
  type RequirementStatus,
  type WorkspaceSubmissionListItem,
} from "@/lib/api/portal";
import { fetchCurrentSession, type PortalSession } from "@/lib/session/portal";
import { statusLabel } from "@/lib/constants/statuses";

// "otros" is the synthetic bucket for submissions whose institution code is
// empty/unknown; it has no entry in INSTITUTION_LABELS, so resolve it to a
// proper Spanish label here rather than leaking the lowercase code to users.
function institutionLabel(code: string): string {
  if (code === "otros") return "Otros";
  return INSTITUTION_LABELS[code] ?? code;
}

type Grouped = {
  institutionCode: string;
  institutionLabel: string;
  years: Array<{
    year: number;
    months: Array<{
      monthIndex: number; // 1-12
      monthLabel: string;
      items: WorkspaceSubmissionListItem[];
    }>;
  }>;
};

export default function SubmissionsIndexPage() {
  const router = useRouter();
  const [session, setSession] = useState<PortalSession | null>(null);
  const [items, setItems] = useState<WorkspaceSubmissionListItem[] | null>(
    null,
  );
  const [errorKind, setErrorKind] = useState<"network" | null>(null);
  const [cancelingId, setCancelingId] = useState<string | null>(null);
  // CW-11 — client-side filters over the provider's own upload history
  // (the page previously offered no way to slice a long list).
  const [filterInstitution, setFilterInstitution] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [filterYear, setFilterYear] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetchCurrentSession().then((current) => {
      if (cancelled) return;
      if (!current) {
        router.replace("/");
        return;
      }
      setSession(current);
    });
    return () => {
      cancelled = true;
    };
  }, [router]);

  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    setErrorKind(null);
    listWorkspaceSubmissions(session)
      .then((r) => {
        if (!cancelled) setItems(r.items);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof PortalApiError && err.status === 401) {
          // Session expired/invalid — send the provider back to sign in
          // instead of showing a silent "no documents" empty state.
          router.replace("/");
          return;
        }
        if (err instanceof PortalApiError) {
          setErrorKind("network");
        }
        setItems([]);
      });
    return () => {
      cancelled = true;
    };
  }, [session, router]);

  const institutionOptions = useMemo(() => {
    const set = new Set<string>();
    for (const it of items ?? []) set.add(it.institution || "otros");
    return Array.from(set).sort((a, b) =>
      institutionLabel(a).localeCompare(institutionLabel(b), "es"),
    );
  }, [items]);

  const statusOptions = useMemo(() => {
    const set = new Set<string>();
    for (const it of items ?? []) set.add(it.status);
    return Array.from(set).sort((a, b) =>
      statusLabel(a).localeCompare(statusLabel(b), "es"),
    );
  }, [items]);

  const yearOptions = useMemo(() => {
    const set = new Set<number>();
    for (const it of items ?? []) set.add(extractYearMonth(it).year);
    return Array.from(set).sort((a, b) => b - a);
  }, [items]);

  const filteredItems = useMemo(() => {
    if (!items) return items;
    return items.filter((it) => {
      if (
        filterInstitution &&
        (it.institution || "otros") !== filterInstitution
      )
        return false;
      if (filterStatus && it.status !== filterStatus) return false;
      if (filterYear && String(extractYearMonth(it).year) !== filterYear)
        return false;
      return true;
    });
  }, [items, filterInstitution, filterStatus, filterYear]);

  async function handleCancel(item: WorkspaceSubmissionListItem) {
    if (!session || cancelingId) return;
    const confirmed = window.confirm(
      "Cancelar este envío eliminará el PDF y lo quitará de tu historial. Si solo necesitas cambiar el archivo, abre el detalle y usa Reemplazar archivo.",
    );
    if (!confirmed) return;
    setCancelingId(item.submission_id);
    try {
      await cancelWorkspaceSubmission(session, item.submission_id);
      setItems(
        (current) =>
          current?.filter((row) => row.submission_id !== item.submission_id) ??
          [],
      );
      toast.success("Envío cancelado", {
        description: "La obligación vuelve a quedar pendiente.",
      });
    } catch (err) {
      const description =
        err instanceof PortalApiError && err.status === 409
          ? "Este envío ya entró a revisión. Ábrelo para reemplazarlo si necesitas corregirlo."
          : "No pudimos cancelar el envío. Inténtalo de nuevo en unos segundos.";
      toast.error("No se pudo cancelar", { description });
    } finally {
      setCancelingId(null);
    }
  }

  if (!session) return null;

  return (
    <PortalAppShell session={session}>
      <main className="mx-auto max-w-7xl space-y-5 px-5 py-6">
        <PageHeader
          eyebrow="Historial"
          title="Documentos cargados"
          description="Todo lo que has subido, agrupado por institución, año y mes. Solo lectura — para reemplazar un documento, ábrelo y usa la opción de corregir."
        />

        {items === null ? (
          <p className="text-sm text-muted-foreground">Cargando documentos…</p>
        ) : errorKind === "network" ? (
          <p className="text-sm text-muted-foreground">
            No pudimos cargar tu historial. Vuelve a intentarlo en unos
            segundos.
          </p>
        ) : items.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-center gap-2 py-12 text-center">
              <FolderOpen
                className="h-8 w-8 text-muted-foreground"
                aria-hidden="true"
              />
              <p className="text-sm font-medium">
                Todavía no has cargado documentos.
              </p>
              <p className="max-w-md text-sm text-muted-foreground">
                Cuando subas tu primera evidencia desde el calendario o el
                expediente inicial, aparecerá aquí.
              </p>
              <Button asChild size="sm" className="mt-2">
                <Link href="/portal/calendar">Ver mi calendario</Link>
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-5">
            <ProviderSubmissionsFilters
              institutionOptions={institutionOptions}
              statusOptions={statusOptions}
              yearOptions={yearOptions}
              institution={filterInstitution}
              status={filterStatus}
              year={filterYear}
              onInstitution={setFilterInstitution}
              onStatus={setFilterStatus}
              onYear={setFilterYear}
              onClear={() => {
                setFilterInstitution("");
                setFilterStatus("");
                setFilterYear("");
              }}
            />
            {(filteredItems?.length ?? 0) === 0 ? (
              <p className="text-sm text-muted-foreground">
                Ningún documento coincide con los filtros.
              </p>
            ) : (
              <GroupedList
                groups={groupSubmissions(filteredItems ?? [])}
                cancelingId={cancelingId}
                onCancel={handleCancel}
              />
            )}
          </div>
        )}
      </main>
    </PortalAppShell>
  );
}

// ---------------------------------------------------------------------------
// Filters (CW-11)
// ---------------------------------------------------------------------------

function ProviderSubmissionsFilters({
  institutionOptions,
  statusOptions,
  yearOptions,
  institution,
  status,
  year,
  onInstitution,
  onStatus,
  onYear,
  onClear,
}: {
  institutionOptions: string[];
  statusOptions: string[];
  yearOptions: number[];
  institution: string;
  status: string;
  year: string;
  onInstitution: (value: string) => void;
  onStatus: (value: string) => void;
  onYear: (value: string) => void;
  onClear: () => void;
}) {
  const hasFilters = Boolean(institution || status || year);
  return (
    <div className="flex flex-wrap items-end gap-3 rounded-lg border border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)] px-4 py-3">
      <FilterControl label="Institución">
        <Select
          value={institution}
          onChange={(e) => onInstitution(e.target.value)}
        >
          <option value="">Todas</option>
          {institutionOptions.map((code) => (
            <option key={code} value={code}>
              {institutionLabel(code)}
            </option>
          ))}
        </Select>
      </FilterControl>
      <FilterControl label="Estado">
        <Select value={status} onChange={(e) => onStatus(e.target.value)}>
          <option value="">Todos</option>
          {statusOptions.map((value) => (
            <option key={value} value={value}>
              {statusLabel(value)}
            </option>
          ))}
        </Select>
      </FilterControl>
      <FilterControl label="Año">
        <Select value={year} onChange={(e) => onYear(e.target.value)}>
          <option value="">Todos</option>
          {yearOptions.map((y) => (
            <option key={y} value={String(y)}>
              {y}
            </option>
          ))}
        </Select>
      </FilterControl>
      {hasFilters ? (
        <Button type="button" size="sm" variant="ghost" onClick={onClear}>
          Limpiar
        </Button>
      ) : null}
    </div>
  );
}

function FilterControl({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="space-y-1">
      <label className="block text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </label>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Grouping
// ---------------------------------------------------------------------------

function groupSubmissions(items: WorkspaceSubmissionListItem[]): Grouped[] {
  // institution → year → month → items
  const byInstitution = new Map<
    string,
    Map<number, Map<number, WorkspaceSubmissionListItem[]>>
  >();

  for (const item of items) {
    const { year, monthIndex } = extractYearMonth(item);
    const inst = item.institution || "otros";
    let years = byInstitution.get(inst);
    if (!years) {
      years = new Map();
      byInstitution.set(inst, years);
    }
    let months = years.get(year);
    if (!months) {
      months = new Map();
      years.set(year, months);
    }
    let bucket = months.get(monthIndex);
    if (!bucket) {
      bucket = [];
      months.set(monthIndex, bucket);
    }
    bucket.push(item);
  }

  // Sort institutions by their label so the order is stable for users;
  // years descending (newest first); months descending; items by
  // submitted_at desc within a month.
  return Array.from(byInstitution.entries())
    .map(([code, years]) => ({
      institutionCode: code,
      institutionLabel: institutionLabel(code),
      years: Array.from(years.entries())
        .sort((a, b) => b[0] - a[0])
        .map(([year, months]) => ({
          year,
          months: Array.from(months.entries())
            .sort((a, b) => b[0] - a[0])
            .map(([monthIndex, monthItems]) => ({
              monthIndex,
              monthLabel: MONTH_LABELS_ES[monthIndex] ?? `Mes ${monthIndex}`,
              items: monthItems
                .slice()
                .sort(
                  (a, b) =>
                    new Date(b.submitted_at).getTime() -
                    new Date(a.submitted_at).getTime(),
                ),
            })),
        })),
    }))
    .sort((a, b) =>
      a.institutionLabel.localeCompare(b.institutionLabel, "es-MX"),
    );
}

function extractYearMonth(item: WorkspaceSubmissionListItem): {
  year: number;
  monthIndex: number;
} {
  // period_key shapes: "2026-M04", "2026-Q1", "2026", or null. Prefer
  // the period when it carries a month; otherwise fall back to the
  // submission timestamp so every row groups somewhere reasonable.
  if (item.period_key) {
    const match = item.period_key.match(/^(\d{4})-M(\d{2})$/);
    if (match) {
      return { year: Number(match[1]), monthIndex: Number(match[2]) };
    }
    const yearOnly = item.period_key.match(/^(\d{4})/);
    if (yearOnly) {
      const submitted = new Date(item.submitted_at);
      return {
        year: Number(yearOnly[1]),
        monthIndex: submitted.getMonth() + 1,
      };
    }
  }
  const submitted = new Date(item.submitted_at);
  return {
    year: submitted.getFullYear(),
    monthIndex: submitted.getMonth() + 1,
  };
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

function GroupedList({
  groups,
  cancelingId,
  onCancel,
}: {
  groups: Grouped[];
  cancelingId: string | null;
  onCancel: (item: WorkspaceSubmissionListItem) => void;
}) {
  return (
    <div className="space-y-6">
      {groups.map((group) => (
        <Card key={group.institutionCode}>
          <CardHeader>
            <CardTitle>{group.institutionLabel}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            {group.years.map((yearBlock) => (
              <div key={yearBlock.year} className="space-y-3">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {yearBlock.year}
                </h3>
                {yearBlock.months.map((monthBlock) => (
                  <div
                    key={`${yearBlock.year}-${monthBlock.monthIndex}`}
                    className="space-y-1.5"
                  >
                    <p className="text-xs font-medium text-foreground">
                      {monthBlock.monthLabel}
                    </p>
                    <ul className="divide-y divide-border rounded-md border border-border bg-white">
                      {monthBlock.items.map((item) => (
                        <li key={item.submission_id}>
                          <div className="flex flex-wrap items-center gap-x-2 gap-y-2 p-3 hover:bg-muted/30">
                            <Link
                              href={`/portal/submissions/${item.submission_id}`}
                              className="flex min-w-0 flex-1 basis-48 items-center gap-3"
                            >
                              <FileText
                                className="h-4 w-4 shrink-0 text-muted-foreground"
                                aria-hidden="true"
                              />
                              <div className="min-w-0 flex-1">
                                <p className="truncate text-sm font-medium text-foreground">
                                  {item.requirement_name}
                                </p>
                                <p className="truncate text-xs text-muted-foreground">
                                  {item.filename ?? "Sin archivo"}
                                  {item.period_key
                                    ? ` · ${item.period_key}`
                                    : ""}
                                </p>
                              </div>
                              <ArrowRight
                                className="h-4 w-4 shrink-0 text-muted-foreground"
                                aria-hidden="true"
                              />
                            </Link>
                            <RequirementStatusBadge
                              status={item.status as RequirementStatus}
                            />
                            {item.can_cancel ? (
                              <Button
                                type="button"
                                variant="destructive"
                                size="sm"
                                className="shrink-0"
                                loading={cancelingId === item.submission_id}
                                onClick={() => onCancel(item)}
                              >
                                <Trash className="h-4 w-4" aria-hidden="true" />
                                Cancelar
                              </Button>
                            ) : null}
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            ))}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
