"use client";

import { useCallback, useEffect, useState } from "react";

import { Surface } from "@/components/checkwise/dashboard/stat-card";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { toast } from "@/components/ui/toast";
import {
  getBilling,
  grantEntitlement,
  listEntitlements,
  revokeEntitlement,
  updateBilling,
  type AdminBilling,
  type AdminEntitlement,
} from "@/lib/api/admin";
import type { ClientPlan } from "@/lib/api/client";
import { apiErrorDetail } from "@/lib/api/error-detail";

const CAPABILITY_LABELS: Record<string, string> = {
  export_audit_package: "Exportar paquete de auditoría",
  bulk_export: "Exportación masiva",
  download_documents: "Descargar documentos",
};

const PROVIDER_OPTIONS = [
  { value: "manual", label: "Manual" },
  { value: "stripe", label: "Stripe (no conectado)" },
];
const STATUS_OPTIONS = ["none", "trialing", "active", "past_due", "canceled"];

/**
 * Internal-admin per-tenant entitlement overrides + the billing seam
 * (Phase D). Toggling a capability writes an override; "usar valor del plan"
 * removes it. Billing is the provider-agnostic seam (Stripe is not wired).
 */
export function AdminEntitlementsControls({
  plan,
  onChanged,
}: {
  plan: ClientPlan | null;
  onChanged: () => void;
}) {
  const orgId = plan?.organization_id ?? null;
  const [overrides, setOverrides] = useState<AdminEntitlement[]>([]);
  const [billing, setBilling] = useState<AdminBilling | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    if (!orgId) return;
    try {
      const [ents, bill] = await Promise.all([
        listEntitlements(orgId),
        getBilling(orgId),
      ]);
      setOverrides(ents);
      setBilling(bill);
    } catch {
      /* fail-open: leave the panels empty rather than blocking the page */
    }
  }, [orgId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  if (!orgId || !plan) return null;

  const overrideKeys = new Set(overrides.map((e) => e.key));
  const caps = plan.capabilities as Record<string, boolean>;

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    try {
      await fn();
      toast.success("Actualizado.");
      await refresh();
      onChanged();
    } catch (e) {
      toast.error(apiErrorDetail(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Surface title="Capacidades y facturación">
      <div className="space-y-5">
        <div className="space-y-2">
          <p className="text-xs font-medium text-[color:var(--text-secondary)]">
            Capacidades (override por cliente)
          </p>
          {Object.keys(CAPABILITY_LABELS).map((key) => (
            <div
              key={key}
              className="flex flex-wrap items-center justify-between gap-2"
            >
              <label className="flex items-center gap-2 text-sm text-[color:var(--text-primary)]">
                <input
                  type="checkbox"
                  checked={Boolean(caps[key])}
                  disabled={busy}
                  onChange={(e) =>
                    run(() =>
                      grantEntitlement(orgId, key, { enabled: e.target.checked }),
                    )
                  }
                />
                {CAPABILITY_LABELS[key]}
              </label>
              {overrideKeys.has(key) ? (
                <Button
                  variant="link"
                  size="sm"
                  disabled={busy}
                  onClick={() => run(() => revokeEntitlement(orgId, key))}
                >
                  Usar valor del plan
                </Button>
              ) : (
                <span className="text-xs text-[color:var(--text-tertiary)]">
                  valor del plan
                </span>
              )}
            </div>
          ))}
        </div>

        <div className="space-y-2">
          <p className="text-xs font-medium text-[color:var(--text-secondary)]">
            Facturación
          </p>
          {billing ? (
            <div className="flex flex-wrap items-end gap-3">
              <label className="flex flex-col gap-1 text-xs text-[color:var(--text-secondary)]">
                Proveedor
                <Select
                  value={billing.provider}
                  disabled={busy}
                  onChange={(e) =>
                    run(() => updateBilling(orgId, { provider: e.target.value }))
                  }
                  className="w-44"
                >
                  {PROVIDER_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </Select>
              </label>
              <label className="flex flex-col gap-1 text-xs text-[color:var(--text-secondary)]">
                Estado
                <Select
                  value={billing.status}
                  disabled={busy}
                  onChange={(e) =>
                    run(() => updateBilling(orgId, { status: e.target.value }))
                  }
                  className="w-44"
                >
                  {STATUS_OPTIONS.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </Select>
              </label>
            </div>
          ) : (
            <p className="text-xs text-[color:var(--text-tertiary)]">
              Sin datos de facturación.
            </p>
          )}
        </div>
      </div>
    </Surface>
  );
}
