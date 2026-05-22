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

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, FileText, FolderOpen } from "@phosphor-icons/react";

import { PortalAppShell } from "@/components/checkwise/portal/portal-app-shell";
import { RequirementStatusBadge } from "@/components/checkwise/portal/requirement-status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import {
  INSTITUTION_LABELS,
  MONTH_LABELS_ES,
  PortalApiError,
  listWorkspaceSubmissions,
  type RequirementStatus,
  type WorkspaceSubmissionListItem,
} from "@/lib/api/portal";
import { fetchCurrentSession, type PortalSession } from "@/lib/session/portal";

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
  const [items, setItems] = useState<WorkspaceSubmissionListItem[] | null>(null);
  const [errorKind, setErrorKind] = useState<"network" | null>(null);

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
        if (err instanceof PortalApiError && err.status !== 401) {
          setErrorKind("network");
        }
        setItems([]);
      });
    return () => {
      cancelled = true;
    };
  }, [session]);

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
            No pudimos cargar tu historial. Vuelve a intentarlo en unos segundos.
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
          <GroupedList groups={groupSubmissions(items)} />
        )}
      </main>
    </PortalAppShell>
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
      institutionLabel: INSTITUTION_LABELS[code] ?? code,
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
    .sort((a, b) => a.institutionLabel.localeCompare(b.institutionLabel, "es-MX"));
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
      return { year: Number(yearOnly[1]), monthIndex: submitted.getMonth() + 1 };
    }
  }
  const submitted = new Date(item.submitted_at);
  return { year: submitted.getFullYear(), monthIndex: submitted.getMonth() + 1 };
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

function GroupedList({ groups }: { groups: Grouped[] }) {
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
                          <Link
                            href={`/portal/submissions/${item.submission_id}`}
                            className="flex items-center gap-3 p-3 hover:bg-muted/30"
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
                            <RequirementStatusBadge
                              status={item.status as RequirementStatus}
                            />
                            <ArrowRight
                              className="h-4 w-4 shrink-0 text-muted-foreground"
                              aria-hidden="true"
                            />
                          </Link>
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
