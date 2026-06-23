"use client";

import Link from "next/link";

import { UsageMeter } from "@/components/checkwise/plan/usage-meter";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { PLAN_CONTACT_HREF } from "@/lib/constants/plan-states";

/** Shown when adding a provider returns 409 provider_limit_reached. */
export function ProviderLimitModal({
  open,
  used,
  limit,
  onClose,
}: {
  open: boolean;
  used: number | null;
  limit: number | null;
  onClose: () => void;
}) {
  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) onClose();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Límite de proveedores alcanzado</DialogTitle>
          <DialogDescription>
            Tu plan llegó al máximo de proveedores activos. Archiva uno que no
            uses para liberar un espacio, o mejora tu plan para añadir más.
          </DialogDescription>
        </DialogHeader>
        {limit !== null ? (
          <UsageMeter used={used ?? limit} limit={limit} />
        ) : null}
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            Cerrar
          </Button>
          <Button asChild>
            <Link href={PLAN_CONTACT_HREF}>Mejorar mi plan</Link>
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
