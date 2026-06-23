"use client";

/**
 * Phase 5 / Axis 2 — the client's business-acceptance control for one
 * submission. Renders the acceptance badge always (read), and — for an
 * Approver only (Viewers see the badge but no controls) — Accept / Reject /
 * Reset actions. Orthogonal to the compliance status (Axis 1); deciding here
 * never changes that.
 *
 * Override rule: accepting a non-valid doc, or rejecting a valid one,
 * contradicts CheckWise's verdict and needs a reason. The control opens an
 * inline reason field in exactly those cases (the backend 422s otherwise).
 */

import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  ClientAcceptance,
  clientAcceptanceLabel,
  clientAcceptanceVariant,
} from "@/lib/constants/statuses";
import {
  decideClientSubmission,
  type ClientDecisionAction,
} from "@/lib/api/client";
import { apiErrorDetail } from "@/lib/api/error-detail";
import { useClientApprover } from "@/lib/session/client-tier";

const VALID_COMPLIANCE = new Set(["aprobado", "excepcion_legal"]);

export function ClientAcceptanceControl({
  submissionId,
  acceptance,
  complianceStatus,
  clientId,
  onDecided,
}: {
  submissionId: string;
  /** "pending" | "accepted" | "rejected" */
  acceptance: string;
  /** Axis-1 compliance status, used only to decide whether a reason is required. */
  complianceStatus: string;
  clientId?: string;
  /** Called with the new acceptance state so the parent can update its row. */
  onDecided?: (newAcceptance: string) => void;
}) {
  const isApprover = useClientApprover();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // When set, an inline reason field is shown for this pending action.
  const [pendingReject, setPendingReject] = useState(false);
  const [pendingAcceptOverride, setPendingAcceptOverride] = useState(false);
  const [reason, setReason] = useState("");

  const current = acceptance || ClientAcceptance.PENDING;
  const isValid = VALID_COMPLIANCE.has(complianceStatus);

  async function decide(action: ClientDecisionAction, reasonText?: string | null) {
    setBusy(true);
    setError(null);
    try {
      const res = await decideClientSubmission(
        submissionId,
        { action, reason: reasonText ?? null },
        clientId ? { client_id: clientId } : undefined,
      );
      onDecided?.(res.new_acceptance);
      setPendingReject(false);
      setPendingAcceptOverride(false);
      setReason("");
    } catch (e) {
      setError(apiErrorDetail(e));
    } finally {
      setBusy(false);
    }
  }

  function onAccept() {
    // Accepting a non-valid doc is an override → require a reason inline.
    if (!isValid) {
      setPendingReject(false);
      setPendingAcceptOverride(true);
      return;
    }
    void decide("accept");
  }

  const badge = (
    <Badge variant={clientAcceptanceVariant(current)}>
      {clientAcceptanceLabel(current)}
    </Badge>
  );

  if (!isApprover) {
    // Viewers see the state, never the controls.
    return badge;
  }

  const reasonOpen = pendingReject || pendingAcceptOverride;

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-wrap items-center gap-1.5">
        {badge}
        {current !== ClientAcceptance.ACCEPTED ? (
          <Button
            variant="outline"
            size="sm"
            disabled={busy}
            onClick={onAccept}
          >
            Aceptar
          </Button>
        ) : null}
        {current !== ClientAcceptance.REJECTED ? (
          <Button
            variant="outline"
            size="sm"
            disabled={busy}
            onClick={() => {
              setPendingAcceptOverride(false);
              setPendingReject(true);
            }}
          >
            Rechazar
          </Button>
        ) : null}
        {current !== ClientAcceptance.PENDING ? (
          <Button
            variant="ghost"
            size="sm"
            disabled={busy}
            onClick={() => void decide("reset")}
          >
            Restablecer
          </Button>
        ) : null}
      </div>

      {reasonOpen ? (
        <div className="flex flex-wrap items-center gap-1.5">
          <Input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder={
              pendingAcceptOverride
                ? "Motivo: aceptas un documento no aprobado por CheckWise"
                : isValid
                  ? "Motivo: rechazas un documento aprobado por CheckWise"
                  : "Motivo (opcional)"
            }
            className="h-8 w-72 max-w-full text-[13px]"
          />
          <Button
            variant="default"
            size="sm"
            disabled={busy || ((pendingAcceptOverride || isValid) && !reason.trim())}
            onClick={() =>
              void decide(
                pendingAcceptOverride ? "accept" : "reject",
                reason.trim() || null,
              )
            }
          >
            Confirmar
          </Button>
          <Button
            variant="ghost"
            size="sm"
            disabled={busy}
            onClick={() => {
              setPendingReject(false);
              setPendingAcceptOverride(false);
              setReason("");
              setError(null);
            }}
          >
            Cancelar
          </Button>
        </div>
      ) : null}

      {error ? (
        <p className="text-[12px] text-[color:var(--status-error-text)]">{error}</p>
      ) : null}
    </div>
  );
}
