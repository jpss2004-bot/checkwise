"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { toast } from "@/components/ui/toast";
import { reactivateClientProvider } from "@/lib/api/client";
import { apiErrorDetail } from "@/lib/api/error-detail";

/**
 * Shown when adding a provider returns 409 provider_archived: offer to restore
 * the existing archived vendor instead of creating a duplicate.
 */
export function ProviderRestoreModal({
  open,
  vendorId,
  clientId,
  onClose,
  onRestored,
}: {
  open: boolean;
  vendorId: string | null;
  clientId?: string | null;
  onClose: () => void;
  onRestored: () => void;
}) {
  const [busy, setBusy] = useState(false);

  async function restore() {
    if (!vendorId) return;
    setBusy(true);
    try {
      await reactivateClientProvider(
        vendorId,
        clientId ? { client_id: clientId } : undefined,
      );
      toast.success("Proveedor restaurado.");
      onRestored();
    } catch (err) {
      toast.error(apiErrorDetail(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o && !busy) onClose();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Proveedor archivado</DialogTitle>
          <DialogDescription>
            Ya tienes un proveedor con ese RFC en tu cartera, pero está
            archivado. ¿Restaurarlo en lugar de crear uno nuevo?
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancelar
          </Button>
          <Button onClick={restore} loading={busy}>
            Restaurar proveedor
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
