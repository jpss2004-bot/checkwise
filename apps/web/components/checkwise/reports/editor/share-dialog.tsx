"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Check,
  Copy,
  LinkSimple,
  ShareNetwork,
  Trash,
} from "@phosphor-icons/react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/toast";
import {
  ReportsApiError,
  createReportShare,
  listReportShares,
  revokeReportShare,
  type CreateReportShareResponse,
  type ReportShare,
} from "@/lib/api/reports";

/**
 * Phase 10D — share-link manager dialog.
 *
 * Three states the user moves through:
 *   1. Form: pick expiry + optional password, submit.
 *   2. Just-minted: the freshly-issued URL is shown ONCE with a
 *      copy button. Closing the dialog or going to the list view
 *      hides it permanently (the raw token is never re-fetched).
 *   3. List: existing shares for this report, with revoke buttons.
 *      Tokens are NOT in this view — only metadata + audit counters.
 *
 * Expiry quick-picks: 7d / 30d / 90d / never / custom. Default is
 * 30 days per the locked Phase 10D product decision.
 *
 * Password is optional. Minimum 4 chars enforced by the backend; we
 * surface the constraint in helper text. When set, the recipient
 * must POST to /unlock with the password before the consume route
 * returns HTML.
 */

const EXPIRY_QUICK_PICKS = [
  { label: "7 días", days: 7 },
  { label: "30 días", days: 30 },
  { label: "90 días", days: 90 },
] as const;

type View = "form" | "list";

export function ShareDialog({
  reportId,
  variant = "ghost",
}: {
  reportId: string;
  // R2 (promoted CTAs): the editor passes "default" once the report
  // has rendered content so "Compartir" reads as a primary action
  // instead of disappearing into the ghost-button toolbar.
  variant?: "ghost" | "default" | "outline";
}) {
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<View>("form");
  const [expiryDays, setExpiryDays] = useState<number | "never">(30);
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [justMinted, setJustMinted] = useState<CreateReportShareResponse | null>(null);
  const [existing, setExisting] = useState<ReportShare[]>([]);
  const [loadingList, setLoadingList] = useState(false);

  // Reset state every time the dialog re-opens so a previously shown
  // raw token doesn't bleed across opens.
  useEffect(() => {
    if (open) {
      setView("form");
      setJustMinted(null);
      setPassword("");
      setExpiryDays(30);
    }
  }, [open]);

  const fetchList = useCallback(async () => {
    setLoadingList(true);
    try {
      const list = await listReportShares(reportId);
      setExisting(list.items);
    } catch (err) {
      toast.error(
        err instanceof ReportsApiError
          ? err.message
          : "No pudimos cargar los enlaces existentes.",
      );
    } finally {
      setLoadingList(false);
    }
  }, [reportId]);

  // Pre-fetch the list once when the dialog opens so the user can
  // jump to "Ver enlaces existentes" without a spinner.
  useEffect(() => {
    if (open) fetchList();
  }, [open, fetchList]);

  const computedExpiresAt = useMemo(() => {
    if (expiryDays === "never") return undefined;
    const expires = new Date();
    expires.setDate(expires.getDate() + expiryDays);
    return expires.toISOString();
  }, [expiryDays]);

  const onSubmit = useCallback(async () => {
    if (submitting) return;
    if (password && password.length < 4) {
      toast.error("La contraseña debe tener al menos 4 caracteres.");
      return;
    }
    setSubmitting(true);
    try {
      const result = await createReportShare(reportId, {
        expires_at: computedExpiresAt,
        password: password || undefined,
      });
      setJustMinted(result);
      // Move the new row into the existing list so closing the
      // banner immediately shows it.
      setExisting((prev) => [result.share, ...prev]);
      toast.success("Enlace generado.");
    } catch (err) {
      const message =
        err instanceof ReportsApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "No pudimos generar el enlace.";
      toast.error(message);
    } finally {
      setSubmitting(false);
    }
  }, [computedExpiresAt, password, reportId, submitting]);

  const onCopy = useCallback(async () => {
    if (!justMinted) return;
    try {
      await navigator.clipboard.writeText(justMinted.url);
      toast.success("URL copiada al portapapeles.");
    } catch {
      toast.error("No pudimos copiar al portapapeles. Cópialo manualmente.");
    }
  }, [justMinted]);

  const onRevoke = useCallback(
    async (share: ReportShare) => {
      try {
        await revokeReportShare(share.id);
        toast.success("Enlace revocado.");
        await fetchList();
      } catch (err) {
        toast.error(
          err instanceof ReportsApiError
            ? err.message
            : "No pudimos revocar el enlace.",
        );
      }
    },
    [fetchList],
  );

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button
          type="button"
          variant={variant}
          size="sm"
          title="Generar un enlace público para compartir este reporte sin login"
        >
          <ShareNetwork className="h-4 w-4" weight="bold" aria-hidden="true" />
          Compartir
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Compartir reporte</DialogTitle>
          <DialogDescription>
            Genera un enlace público para enviar el reporte a alguien
            sin que tenga que iniciar sesión. El destinatario verá el
            HTML del reporte.
          </DialogDescription>
        </DialogHeader>

        {/* View switcher — pill toggles */}
        <div className="flex gap-1 rounded-md bg-[color:var(--surface-sunken)] p-1">
          <button
            type="button"
            onClick={() => setView("form")}
            className={
              "flex-1 rounded-sm px-3 py-1.5 text-[13px] font-medium transition-colors " +
              (view === "form"
                ? "bg-[color:var(--surface-page)] text-[color:var(--text-primary)] shadow-sm"
                : "text-[color:var(--text-secondary)] hover:text-[color:var(--text-primary)]")
            }
          >
            Generar nuevo
          </button>
          <button
            type="button"
            onClick={() => setView("list")}
            className={
              "flex-1 rounded-sm px-3 py-1.5 text-[13px] font-medium transition-colors " +
              (view === "list"
                ? "bg-[color:var(--surface-page)] text-[color:var(--text-primary)] shadow-sm"
                : "text-[color:var(--text-secondary)] hover:text-[color:var(--text-primary)]")
            }
          >
            Existentes ({existing.length})
          </button>
        </div>

        {view === "form" && (
          <div className="space-y-4">
            {justMinted ? (
              <div className="rounded-md border border-[color:var(--status-success-border)] bg-[color:var(--status-success-bg)] p-4">
                <p className="mb-2 flex items-center gap-2 text-[13px] font-semibold text-[color:var(--status-success-text)]">
                  <Check className="h-4 w-4" weight="bold" aria-hidden="true" />
                  Enlace generado. Cópialo ahora — no podrás verlo de nuevo.
                </p>
                <div className="flex items-center gap-2">
                  <Input
                    readOnly
                    value={justMinted.url}
                    className="font-mono text-[12px]"
                    onFocus={(e) => e.currentTarget.select()}
                  />
                  <Button
                    type="button"
                    size="sm"
                    variant="default"
                    onClick={onCopy}
                  >
                    <Copy className="h-4 w-4" weight="bold" aria-hidden="true" />
                    Copiar
                  </Button>
                </div>
                <p className="mt-2 text-[12px] text-[color:var(--text-secondary)]">
                  {justMinted.share.has_password
                    ? "Recuerda enviar la contraseña por un canal aparte."
                    : "Cualquiera con el enlace puede ver el reporte."}
                </p>
              </div>
            ) : (
              <>
                <div className="space-y-2">
                  <Label>Caducidad</Label>
                  <div className="flex flex-wrap gap-2">
                    {EXPIRY_QUICK_PICKS.map((pick) => (
                      <button
                        key={pick.days}
                        type="button"
                        onClick={() => setExpiryDays(pick.days)}
                        className={
                          "rounded-md border px-3 py-1.5 text-[12px] font-medium transition-colors " +
                          (expiryDays === pick.days
                            ? "border-[color:var(--border-brand)] bg-[color:var(--surface-brand-muted)] text-[color:var(--text-brand)]"
                            : "border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] text-[color:var(--text-secondary)] hover:border-[color:var(--border-default)]")
                        }
                      >
                        {pick.label}
                      </button>
                    ))}
                    <button
                      type="button"
                      onClick={() => setExpiryDays("never")}
                      className={
                        "rounded-md border px-3 py-1.5 text-[12px] font-medium transition-colors " +
                        (expiryDays === "never"
                          ? "border-[color:var(--border-brand)] bg-[color:var(--surface-brand-muted)] text-[color:var(--text-brand)]"
                          : "border-[color:var(--border-subtle)] bg-[color:var(--surface-page)] text-[color:var(--text-secondary)] hover:border-[color:var(--border-default)]")
                      }
                    >
                      Sin caducidad
                    </button>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="share-password">
                    Contraseña (opcional)
                  </Label>
                  <Input
                    id="share-password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Mínimo 4 caracteres"
                    minLength={4}
                  />
                  <p className="text-[11px] text-[color:var(--text-tertiary)]">
                    Si la asignas, envía la contraseña por un canal
                    aparte (no la incluyas en el mismo correo que el
                    enlace).
                  </p>
                </div>

                <Button
                  type="button"
                  variant="default"
                  className="w-full"
                  disabled={submitting}
                  onClick={onSubmit}
                >
                  <LinkSimple
                    className="h-4 w-4"
                    weight="bold"
                    aria-hidden="true"
                  />
                  {submitting ? "Generando…" : "Generar enlace"}
                </Button>
              </>
            )}
          </div>
        )}

        {view === "list" && (
          <div className="space-y-2">
            {loadingList && (
              <p className="text-[12px] text-[color:var(--text-tertiary)]">
                Cargando…
              </p>
            )}
            {!loadingList && existing.length === 0 && (
              <p className="rounded-md border border-dashed border-[color:var(--border-subtle)] p-4 text-center text-[12px] text-[color:var(--text-secondary)]">
                No hay enlaces para este reporte. Genera uno en la
                pestaña anterior.
              </p>
            )}
            {!loadingList &&
              existing.map((share) => (
                <ShareRow
                  key={share.id}
                  share={share}
                  onRevoke={() => onRevoke(share)}
                />
              ))}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function ShareRow({
  share,
  onRevoke,
}: {
  share: ReportShare;
  onRevoke: () => void;
}) {
  const revoked = share.revoked_at !== null;
  const expired =
    share.expires_at !== null && new Date(share.expires_at) <= new Date();
  const inactive = revoked || expired;
  return (
    <div
      className={
        "flex items-center justify-between gap-3 rounded-md border p-3 " +
        (inactive
          ? "border-[color:var(--border-subtle)] bg-[color:var(--surface-sunken)] opacity-60"
          : "border-[color:var(--border-subtle)] bg-[color:var(--surface-page)]")
      }
    >
      <div className="min-w-0 flex-1 space-y-0.5">
        <div className="flex items-center gap-2 text-[12px]">
          <span className="font-mono font-medium text-[color:var(--text-primary)]">
            #{share.id.slice(0, 8)}
          </span>
          {share.has_password && (
            <span className="rounded-sm bg-[color:var(--surface-brand-muted)] px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[color:var(--text-brand)]">
              Con contraseña
            </span>
          )}
          {revoked && (
            <span className="rounded-sm bg-[color:var(--status-error-bg)] px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[color:var(--status-error-text)]">
              Revocado
            </span>
          )}
          {expired && !revoked && (
            <span className="rounded-sm bg-[color:var(--status-warning-bg)] px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[color:var(--status-warning-text)]">
              Vencido
            </span>
          )}
        </div>
        <p className="text-[11px] text-[color:var(--text-tertiary)]">
          {share.access_count} {share.access_count === 1 ? "vista" : "vistas"}
          {share.last_accessed_at &&
            ` · última ${new Date(share.last_accessed_at).toLocaleDateString("es-MX")}`}
          {share.expires_at &&
            ` · vence ${new Date(share.expires_at).toLocaleDateString("es-MX")}`}
        </p>
      </div>
      {!inactive && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={onRevoke}
          title="Revocar este enlace inmediatamente"
        >
          <Trash className="h-4 w-4" weight="bold" aria-hidden="true" />
          Revocar
        </Button>
      )}
    </div>
  );
}

