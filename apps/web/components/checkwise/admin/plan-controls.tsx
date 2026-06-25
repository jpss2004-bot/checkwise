"use client";

import { useState } from "react";

import { PlanBadge } from "@/components/checkwise/plan/plan-badge";
import { UsageMeter } from "@/components/checkwise/plan/usage-meter";
import { Surface } from "@/components/checkwise/dashboard/stat-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { toast } from "@/components/ui/toast";
import { startClientDemo, updateClientOrg } from "@/lib/api/admin";
import type { ClientPlan } from "@/lib/api/client";
import { apiErrorDetail } from "@/lib/api/error-detail";

const PLAN_OPTIONS = [
  { value: "demo", label: "Demo" },
  { value: "standard", label: "Estándar (30)" },
  { value: "growth", label: "Crecimiento (50)" },
  { value: "enterprise", label: "Empresarial (personalizado)" },
  { value: "legacy", label: "Plan actual (sin límite)" },
];

/**
 * Internal-admin controls for a client's plan: start a 14-day demo, change the
 * tier, or set a per-tenant provider-limit override. ``plan`` carries the
 * organization_id the mutations target.
 */
export function AdminPlanControls({
  plan,
  onChanged,
}: {
  plan: ClientPlan | null;
  onChanged: () => void;
}) {
  const orgId = plan?.organization_id ?? null;
  const [planValue, setPlanValue] = useState(plan?.plan ?? "standard");
  const [limitValue, setLimitValue] = useState(
    plan?.provider_limit != null ? String(plan.provider_limit) : "",
  );
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  if (!orgId) {
    return (
      <Surface title="Plan y demo">
        <p className="text-sm text-[color:var(--text-secondary)]">
          No se pudo cargar el plan de este cliente.
        </p>
      </Surface>
    );
  }

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setErr(null);
    try {
      await fn();
      toast.success("Plan actualizado.");
      onChanged();
    } catch (e) {
      const detail = apiErrorDetail(e);
      setErr(detail);
      toast.error(detail);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Surface title="Plan y demo">
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          {plan ? <PlanBadge plan={plan} /> : null}
          {plan?.demo_expires_at ? (
            <span className="text-xs text-[color:var(--text-secondary)]">
              Demo termina el{" "}
              {new Date(plan.demo_expires_at).toLocaleDateString("es-MX")}
            </span>
          ) : null}
        </div>
        {plan ? (
          <UsageMeter used={plan.providers_used} limit={plan.provider_limit} />
        ) : null}

        <div className="flex flex-wrap items-end gap-3">
          <Button
            variant="outline"
            size="sm"
            loading={busy}
            onClick={() => run(() => startClientDemo(orgId))}
          >
            Iniciar demo (14 días)
          </Button>
        </div>

        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs text-[color:var(--text-secondary)]">
            Plan
            <Select
              value={planValue}
              onChange={(e) => setPlanValue(e.target.value)}
              className="w-56"
            >
              {PLAN_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </Select>
          </label>
          <label className="flex flex-col gap-1 text-xs text-[color:var(--text-secondary)]">
            Límite de proveedores (vacío = predeterminado del plan)
            <Input
              type="number"
              min={0}
              value={limitValue}
              onChange={(e) => setLimitValue(e.target.value)}
              className="w-56"
            />
          </label>
          <Button
            size="sm"
            loading={busy}
            onClick={() =>
              run(() =>
                updateClientOrg(orgId, {
                  plan: planValue,
                  provider_limit:
                    limitValue.trim() === "" ? null : Number(limitValue),
                }),
              )
            }
          >
            Guardar
          </Button>
        </div>

        {err ? (
          <p className="text-xs text-[color:var(--status-error-text)]">{err}</p>
        ) : null}
      </div>
    </Surface>
  );
}
