"use client";

import { Badge } from "@/components/ui/badge";
import type { ClientPlan } from "@/lib/api/client";
import { useClientPlan } from "@/lib/plan/plan-context";

function variantFor(
  plan: ClientPlan,
): "teal" | "success" | "secondary" | "destructive" {
  if (plan.plan === "demo") {
    // Demo whose deadline has passed but isn't frozen yet → flag it.
    if (plan.demo_expires_at && new Date(plan.demo_expires_at) <= new Date()) {
      return "destructive";
    }
    return "teal";
  }
  if (plan.plan === "legacy") return "secondary";
  return "success";
}

/** Small plan chip. Renders nothing without a plan. */
export function PlanBadge({ plan }: { plan: ClientPlan | null }) {
  if (!plan) return null;
  return <Badge variant={variantFor(plan)}>{plan.plan_label}</Badge>;
}

/** Context-aware chip for the client shell header (reads the plan provider). */
export function PlanBadgeConnected() {
  const { plan } = useClientPlan();
  return <PlanBadge plan={plan} />;
}
