"use client";

import Link from "next/link";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { PLAN_CONTACT_HREF } from "@/lib/constants/plan-states";
import { useClientPlan } from "@/lib/plan/plan-context";

/** Whole days until ``expiresAt`` (negative once past). Exported for testing. */
export function daysUntil(expiresAt: string, now: number = Date.now()): number {
  return Math.ceil((new Date(expiresAt).getTime() - now) / 86_400_000);
}

/**
 * Demo-deadline banner. Hidden when there's no deadline, more than 30 days
 * remain, or the demo has already expired (the upgrade wall handles that).
 * Warns inside 7 days, informs between 8–30.
 */
export function DemoCountdown({ expiresAt }: { expiresAt: string | null }) {
  if (!expiresAt) return null;
  const days = daysUntil(expiresAt);
  if (days > 30 || days <= 0) return null;
  return (
    <Alert variant={days <= 7 ? "warning" : "info"}>
      <AlertTitle>
        Tu demo de CheckWise termina en {days} {days === 1 ? "día" : "días"}
      </AlertTitle>
      <AlertDescription>
        Conserva toda tu información al mejorar tu plan.{" "}
        <Link href={PLAN_CONTACT_HREF} className="font-medium underline">
          Contactar a CheckWise
        </Link>
      </AlertDescription>
    </Alert>
  );
}

/** Context-aware banner for the client shell (reads the plan provider). Owns
 *  its width container, and renders nothing outside the 1–30 day window so the
 *  shell never shows an empty band. */
export function DemoCountdownConnected() {
  const { plan } = useClientPlan();
  const expiresAt = plan?.demo_expires_at ?? null;
  if (!expiresAt) return null;
  const days = daysUntil(expiresAt);
  if (days > 30 || days <= 0) return null;
  return (
    <div className="mx-auto max-w-7xl px-5 pt-3">
      <DemoCountdown expiresAt={expiresAt} />
    </div>
  );
}
