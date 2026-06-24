"use client";

/**
 * /client/bandeja — the Approver's acceptance queue.
 *
 * A focused inbox of the providers' documents awaiting the client's
 * business-acceptance decision (Axis 2, ``client_acceptance = pending``).
 * Accepting / rejecting here is the client's call and is orthogonal to
 * CheckWise's compliance verdict (Axis 1, the ``status`` badge). Approvers
 * act; read-only Viewers see the queue without controls.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { CheckCircle, Tray } from "@phosphor-icons/react";

import { ClientShell } from "../_shell";
import { Surface } from "@/components/checkwise/dashboard/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { VendorRef } from "@/components/checkwise/vendor-ref";
import { ClientAcceptanceControl } from "@/components/checkwise/client/acceptance-control";
import {
  bulkDecideClientSubmissions,
  listClientSubmissions,
  type ClientSubmissionItem,
} from "@/lib/api/client";
import { statusLabel, statusVariant } from "@/lib/constants/statuses";
import { useUrlClientId } from "@/lib/workspace/use-url-client-id";
import { useClientApprover } from "@/lib/session/client-tier";
import { apiErrorDetail } from "@/lib/api/error-detail";
import { formatDateTime } from "@/lib/format/datetime";

// CheckWise validity states that make an acceptance the "aligned" (non-override)
// path — mirrors the backend _VALID_COMPLIANCE_STATES.
const VALID_COMPLIANCE = new Set(["aprobado", "excepcion_legal"]);

export default function ClientBandejaPage() {
  const urlClientId = useUrlClientId();
  const clientParam = urlClientId ? { client_id: urlClientId } : undefined;
  const isApprover = useClientApprover();

  const [rows, setRows] = useState<ClientSubmissionItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listClientSubmissions({
        ...(urlClientId ? { client_id: urlClientId } : {}),
        client_acceptance: "pending",
        limit: 200,
      });
      setRows(data.items);
    } catch (e) {
      setError(apiErrorDetail(e));
      setRows(null);
    } finally {
      setLoading(false);
    }
  }, [urlClientId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  // The "accept all" shortcut only offers the compliance-VALID pending docs —
  // accepting those is aligned (no reason needed). Rejections + overrides stay
  // a deliberate per-row act.
  const validPendingIds = useMemo(
    () =>
      (rows ?? [])
        .filter((r) => VALID_COMPLIANCE.has(r.status))
        .map((r) => r.submission_id),
    [rows],
  );

  async function acceptAllValid() {
    if (!validPendingIds.length) return;
    setBulkBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await bulkDecideClientSubmissions(
        { submission_ids: validPendingIds, action: "accept" },
        clientParam,
      );
      setNotice(
        `Aceptaste ${res.decided_count} documento${
          res.decided_count === 1 ? "" : "s"
        } válido${res.decided_count === 1 ? "" : "s"}.` +
          (res.failed_count ? ` ${res.failed_count} no se pudieron procesar.` : ""),
      );
      await reload();
    } catch (e) {
      setError(apiErrorDetail(e));
    } finally {
      setBulkBusy(false);
    }
  }

  const pendingCount = rows?.length ?? 0;

  return (
    <ClientShell
      title="Bandeja de aprobación"
      description="Documentos de tus proveedores que esperan tu aceptación. Aceptar o rechazar aquí es tu decisión de negocio — es independiente del dictamen de validez de CheckWise."
      actions={
        isApprover && validPendingIds.length > 0 ? (
          <Button size="sm" onClick={acceptAllValid} disabled={bulkBusy}>
            <CheckCircle className="h-4 w-4" weight="bold" aria-hidden="true" />
            {bulkBusy
              ? "Aceptando…"
              : `Aceptar ${validPendingIds.length} válido${
                  validPendingIds.length === 1 ? "" : "s"
                }`}
          </Button>
        ) : undefined
      }
    >
      <div className="space-y-5">
        {notice ? (
          <div
            role="status"
            className="rounded-lg border border-[color:var(--status-success-border)] bg-[color:var(--status-success-bg)] px-4 py-3 text-[13px] text-[color:var(--status-success-text)]"
          >
            {notice}
          </div>
        ) : null}

        {!isApprover ? (
          <div className="rounded-lg border border-[color:var(--status-info-border)] bg-[color:var(--status-info-bg)] px-4 py-3 text-[13px] text-[color:var(--status-info-text)]">
            Tu acceso es de Solo lectura. Solo un Aprobador puede aceptar o
            rechazar documentos; aquí ves los que están pendientes.
          </div>
        ) : null}

        <Surface
          title="Pendientes de aceptación"
          icon={Tray}
          description={
            rows
              ? `${pendingCount} documento${pendingCount === 1 ? "" : "s"} ${
                  pendingCount === 1 ? "espera" : "esperan"
                } tu decisión`
              : undefined
          }
        >
          {loading && !rows ? (
            <p className="text-[13px] text-[color:var(--text-secondary)]">
              Cargando…
            </p>
          ) : error ? (
            <p className="text-[13px] text-[color:var(--status-error-text)]">
              {error}
            </p>
          ) : rows && rows.length > 0 ? (
            <ul className="divide-y divide-[color:var(--border-subtle)]">
              {rows.map((r) => (
                <li
                  key={r.submission_id}
                  className="flex flex-wrap items-center gap-x-3 gap-y-2 py-3"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="truncate text-sm font-medium text-[color:var(--text-primary)]">
                        <VendorRef
                          vendorId={r.vendor_id}
                          vendorName={r.vendor_name}
                        />
                      </span>
                      <Badge variant={statusVariant(r.status)}>
                        {statusLabel(r.status)}
                      </Badge>
                    </div>
                    <span className="block truncate text-[12px] text-[color:var(--text-secondary)]">
                      {r.requirement_name ?? r.requirement_code ?? "Documento"}
                      {r.period_key
                        ? ` · ${r.period_key}`
                        : r.load_type === "alta_inicial"
                          ? " · Único"
                          : ""}
                      {` · ${formatDateTime(r.submitted_at, {
                        day: "2-digit",
                        month: "short",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}`}
                    </span>
                  </div>
                  <ClientAcceptanceControl
                    submissionId={r.submission_id}
                    acceptance={r.client_acceptance ?? "pending"}
                    complianceStatus={r.status}
                    clientId={urlClientId ?? undefined}
                    onDecided={() => {
                      // A decision moves the row off "pending" — drop it from
                      // the queue so the count + list stay accurate.
                      setRows((prev) =>
                        prev
                          ? prev.filter(
                              (x) => x.submission_id !== r.submission_id,
                            )
                          : prev,
                      );
                    }}
                  />
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-[13px] text-[color:var(--text-secondary)]">
              No hay documentos pendientes de tu aceptación.
            </p>
          )}
        </Surface>
      </div>
    </ClientShell>
  );
}
