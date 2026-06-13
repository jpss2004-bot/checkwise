"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  ArrowSquareOut,
  Buildings,
  Copy,
  Crown,
  IdentificationCard,
  Key,
  ListMagnifyingGlass,
  PaperPlaneTilt,
  Prohibit,
  ArrowCounterClockwise,
  Trash,
  Warning,
} from "@phosphor-icons/react";

import { Surface } from "@/components/checkwise/dashboard/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";

import { PlatformShell } from "../../_shell";
import {
  AdminApiError,
  type AdminResetPasswordResponse,
  type AdminUserDetail,
  getUser,
  resetUserPassword,
  updateUserStatus,
} from "@/lib/api/admin";
import { roleLabel } from "@/lib/constants/labels";

/**
 * /platform/users/[id] — full account picture (Phase 2 of the platform
 * rework). Until this page the only user surfaces were the directory
 * list and the create form; there was nowhere to see one user's
 * memberships, seat usage, and their slice of the audit trail in one
 * place. The lifecycle actions (reset password, disable / reactivate)
 * mirror the list view so an operator can act without bouncing back.
 *
 * Identity editing, role/membership changes, and account deletion land
 * in later phases — this page is their eventual home, so the soft-delete
 * state is already surfaced (read-only) here.
 */

/** FastAPI errors arrive as the raw body — usually ``{"detail": "..."}``
 *  (Spanish on 409s). Unwrap to the sentence. */
function apiErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error && err.message) {
    try {
      const parsed = JSON.parse(err.message) as { detail?: unknown };
      if (typeof parsed.detail === "string") return parsed.detail;
    } catch {
      // Not a JSON body — use the message as-is.
    }
    return err.message;
  }
  return fallback;
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString("es-MX", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("es-MX", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatLastLogin(iso: string | null): string {
  if (!iso) return "Nunca";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const diffDays = Math.floor((Date.now() - date.getTime()) / 86_400_000);
  if (diffDays <= 0) return "Hoy";
  if (diffDays === 1) return "Ayer";
  if (diffDays < 7) return `Hace ${diffDays}d`;
  if (diffDays < 30) return `Hace ${Math.floor(diffDays / 7)} sem`;
  return formatDate(iso);
}

const MEMBERSHIP_STATUS_LABEL: Record<string, string> = {
  active: "Activa",
  removed: "Retirada",
  disabled: "Desactivada",
};

/** Plain-Spanish gloss for the audit actions this page surfaces;
 *  unmapped codes fall back to the raw action so nothing is hidden. */
const ACTION_LABEL: Record<string, string> = {
  "admin.user.provisioned": "Cuenta creada",
  "admin.user_disabled": "Cuenta desactivada",
  "admin.user_reactivated": "Cuenta reactivada",
  "admin.user_password_reset": "Contraseña restablecida (admin)",
  "auth.password_reset_requested": "Solicitó restablecer contraseña",
  "auth.password_reset_completed": "Restableció su contraseña",
  "auth.password_changed": "Cambió su contraseña",
};

function actionLabel(action: string): string {
  return ACTION_LABEL[action] ?? action;
}

type ConfirmState =
  | { kind: "reset" }
  | { kind: "status"; next: "active" | "disabled" };

export default function PlatformUserDetailPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const userId = params?.id;

  const [user, setUser] = useState<AdminUserDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);

  const [confirm, setConfirm] = useState<ConfirmState | null>(null);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [resetResult, setResetResult] =
    useState<AdminResetPasswordResponse | null>(null);
  const [copied, setCopied] = useState(false);

  // Guard against a late response from a previous id overwriting the
  // current one if the operator navigates between detail pages quickly.
  const activeId = useRef<string | undefined>(userId);

  async function load() {
    if (!userId) return;
    activeId.current = userId;
    setLoading(true);
    setError(null);
    setNotFound(false);
    try {
      const data = await getUser(userId);
      if (activeId.current !== userId) return;
      setUser(data);
    } catch (err) {
      if (activeId.current !== userId) return;
      if (err instanceof AdminApiError && err.status === 401) {
        router.replace("/login");
        return;
      }
      if (err instanceof AdminApiError && err.status === 404) {
        setNotFound(true);
        setUser(null);
        return;
      }
      setError(apiErrorMessage(err, "Error al cargar el usuario."));
      setUser(null);
    } finally {
      if (activeId.current === userId) setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  async function onConfirmAction() {
    if (!confirm || !user) return;
    setConfirmBusy(true);
    setConfirmError(null);
    try {
      if (confirm.kind === "reset") {
        const result = await resetUserPassword(user.user_id);
        setUser((u) =>
          u ? { ...u, must_change_password: true } : u,
        );
        setConfirm(null);
        setCopied(false);
        setResetResult(result);
      } else {
        const updated = await updateUserStatus(user.user_id, confirm.next);
        setUser((u) => (u ? { ...u, status: updated.status } : u));
        setConfirm(null);
      }
    } catch (err) {
      if (err instanceof AdminApiError && err.status === 401) {
        router.replace("/login");
        return;
      }
      setConfirmError(apiErrorMessage(err, "No pudimos completar la acción."));
    } finally {
      setConfirmBusy(false);
    }
  }

  async function copyTempPassword() {
    if (!resetResult) return;
    try {
      await navigator.clipboard.writeText(resetResult.temp_password);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard blocked (localhost without HTTPS) — still on screen.
    }
  }

  const isDeleted = Boolean(user?.deleted_at);
  const isActive = user?.status === "active";

  return (
    <PlatformShell
      title={user ? user.full_name || user.email : "Usuario"}
      description={
        user
          ? "Identidad, organizaciones y actividad reciente de esta cuenta."
          : undefined
      }
      actions={
        <>
          <Button asChild size="sm" variant="outline">
            <Link href="/platform/users">
              <ArrowLeft className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
              Volver a usuarios
            </Link>
          </Button>
          {user && !isDeleted ? (
            <>
              <Button
                size="sm"
                variant="outline"
                disabled={!isActive}
                title={
                  !isActive
                    ? "Reactiva la cuenta para poder restablecer su contraseña."
                    : undefined
                }
                onClick={() => {
                  setConfirmError(null);
                  setConfirm({ kind: "reset" });
                }}
              >
                <Key className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
                Restablecer contraseña
              </Button>
              {isActive ? (
                <Button
                  size="sm"
                  variant="outline"
                  className="text-[color:var(--status-error-text)]"
                  onClick={() => {
                    setConfirmError(null);
                    setConfirm({ kind: "status", next: "disabled" });
                  }}
                >
                  <Prohibit className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
                  Desactivar
                </Button>
              ) : (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setConfirmError(null);
                    setConfirm({ kind: "status", next: "active" });
                  }}
                >
                  <ArrowCounterClockwise
                    className="h-3.5 w-3.5"
                    weight="bold"
                    aria-hidden="true"
                  />
                  Reactivar
                </Button>
              )}
            </>
          ) : null}
        </>
      }
    >
      {loading ? (
        <div className="space-y-4">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-40 w-full" />
        </div>
      ) : notFound ? (
        <Surface title="Usuario no encontrado" icon={IdentificationCard}>
          <p className="text-sm text-[color:var(--text-secondary)]">
            No existe una cuenta con ese identificador. Es posible que se haya
            eliminado.
          </p>
          <div className="mt-3">
            <Button asChild size="sm" variant="outline">
              <Link href="/platform/users">Volver a usuarios</Link>
            </Button>
          </div>
        </Surface>
      ) : error ? (
        <Surface title="Error" icon={Warning}>
          <p className="text-sm text-[color:var(--status-error-text)]">{error}</p>
          <div className="mt-3">
            <Button size="sm" variant="outline" onClick={() => load()}>
              Reintentar
            </Button>
          </div>
        </Surface>
      ) : user ? (
        <div className="space-y-5">
          {/* Status + roles strip */}
          <div className="flex flex-wrap items-center gap-2">
            {isDeleted ? (
              <Badge variant="secondary">Eliminado</Badge>
            ) : isActive ? (
              <Badge variant="success">Activo</Badge>
            ) : (
              <Badge variant="secondary">Desactivado</Badge>
            )}
            {user.must_change_password && !isDeleted ? (
              <span
                className="rounded-sm border border-[color:var(--border-subtle)] px-1.5 py-px font-mono text-[9px] uppercase tracking-wide text-[color:var(--text-tertiary)]"
                title="Aún no ha cambiado su contraseña temporal."
              >
                primer acceso pendiente
              </span>
            ) : null}
            {user.roles.length ? (
              user.roles.map((code) => (
                <Badge key={code} variant="outline">
                  {roleLabel(code)}
                </Badge>
              ))
            ) : (
              <span className="text-[12px] text-[color:var(--text-tertiary)]">
                sin roles activos
              </span>
            )}
          </div>

          {/* Soft-delete banner (read-only until Phase 5 restore). */}
          {isDeleted ? (
            <div className="flex items-start gap-2 rounded-md border border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-bg)] px-3 py-2.5 text-[12px] text-[color:var(--status-warning-text)]">
              <Trash className="mt-0.5 h-4 w-4 shrink-0" weight="fill" aria-hidden="true" />
              <div className="space-y-0.5">
                <p className="font-semibold">Cuenta eliminada</p>
                <p>
                  Eliminada el {formatDateTime(user.deleted_at)}
                  {user.deleted_by_email ? ` por ${user.deleted_by_email}` : ""}
                  {user.deletion_reason ? ` — ${user.deletion_reason}` : ""}.
                </p>
              </div>
            </div>
          ) : null}

          {/* Identity */}
          <Surface title="Identidad" icon={IdentificationCard}>
            <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
              <Field label="Correo" mono value={user.email} />
              <Field label="Teléfono" value={user.phone || "—"} />
              <Field label="Último acceso" value={formatLastLogin(user.last_login_at)} />
              <Field label="Alta" value={formatDate(user.created_at)} />
              <Field
                label="Última actualización"
                value={formatDateTime(user.updated_at)}
              />
              <Field
                label="ID"
                mono
                value={user.user_id}
              />
            </dl>
          </Surface>

          {/* Memberships */}
          <Surface title="Organizaciones" icon={Buildings}>
            {user.memberships.length === 0 ? (
              <p className="text-[12px] text-[color:var(--text-tertiary)]">
                Esta cuenta no pertenece a ninguna organización.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-[12px]">
                  <thead>
                    <tr className="border-b border-[color:var(--border-subtle)] text-left text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                      <th className="py-1.5 pr-3 font-medium">Organización</th>
                      <th className="py-1.5 pr-3 font-medium">Rol</th>
                      <th className="py-1.5 pr-3 font-medium">Asientos</th>
                      <th className="py-1.5 font-medium">Estatus</th>
                    </tr>
                  </thead>
                  <tbody>
                    {user.memberships.map((m) => (
                      <tr
                        key={m.membership_id}
                        className="border-b border-[color:var(--border-subtle)] last:border-0"
                      >
                        <td className="py-2 pr-3">
                          <span className="flex items-center gap-1.5">
                            <span className="font-medium text-[color:var(--text-primary)]">
                              {m.organization_name}
                            </span>
                            {m.is_primary ? (
                              <Crown
                                className="h-3.5 w-3.5 text-[color:var(--text-teal)]"
                                weight="fill"
                                aria-label="Titular principal"
                              />
                            ) : null}
                          </span>
                          <span className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                            {m.organization_kind}
                          </span>
                        </td>
                        <td className="py-2 pr-3">
                          <Badge variant="outline">{roleLabel(m.role)}</Badge>
                        </td>
                        <td className="py-2 pr-3 tabular-nums text-[color:var(--text-secondary)]">
                          {m.seat_limit != null
                            ? `${m.active_seats ?? 0} / ${m.seat_limit}`
                            : "—"}
                        </td>
                        <td className="py-2">
                          {m.status === "active" ? (
                            <Badge variant="success">
                              {MEMBERSHIP_STATUS_LABEL[m.status]}
                            </Badge>
                          ) : (
                            <Badge variant="secondary">
                              {MEMBERSHIP_STATUS_LABEL[m.status] ?? m.status}
                            </Badge>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Surface>

          {/* Activity */}
          <Surface
            title="Actividad reciente"
            icon={ListMagnifyingGlass}
            actions={
              <Button asChild size="sm" variant="ghost">
                <Link href="/platform/audit-log">
                  Ver Audit log
                  <ArrowSquareOut
                    className="h-3.5 w-3.5"
                    weight="bold"
                    aria-hidden="true"
                  />
                </Link>
              </Button>
            }
          >
            {user.recent_activity.length === 0 ? (
              <p className="text-[12px] text-[color:var(--text-tertiary)]">
                Sin eventos registrados para esta cuenta.
              </p>
            ) : (
              <>
                <ol className="space-y-2.5">
                  {user.recent_activity.map((ev) => {
                    const byThisUser = ev.actor_id === user.user_id;
                    return (
                      <li
                        key={ev.id}
                        className="flex items-start justify-between gap-3 border-b border-[color:var(--border-subtle)] pb-2.5 last:border-0 last:pb-0"
                      >
                        <div className="min-w-0">
                          <p className="text-[12px] font-medium text-[color:var(--text-primary)]">
                            {actionLabel(ev.action)}
                          </p>
                          <p className="text-[11px] text-[color:var(--text-tertiary)]">
                            {byThisUser
                              ? "por esta cuenta"
                              : `por ${ev.actor_email ?? ev.actor_type}`}
                          </p>
                        </div>
                        <time className="shrink-0 whitespace-nowrap font-mono text-[10px] tabular-nums text-[color:var(--text-tertiary)]">
                          {formatDateTime(ev.created_at)}
                        </time>
                      </li>
                    );
                  })}
                </ol>
                {user.activity_total > user.recent_activity.length ? (
                  <p className="mt-3 text-[11px] text-[color:var(--text-tertiary)]">
                    Mostrando {user.recent_activity.length} de {user.activity_total}{" "}
                    eventos. Usa el Audit log para ver el historial completo.
                  </p>
                ) : null}
              </>
            )}
          </Surface>
        </div>
      ) : null}

      {/* Confirm — reset / disable / reactivate */}
      <Dialog
        open={Boolean(confirm)}
        onOpenChange={(next) => {
          if (!next && !confirmBusy) setConfirm(null);
        }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>
              {confirm?.kind === "reset"
                ? "Restablecer contraseña"
                : confirm?.next === "disabled"
                  ? "Desactivar usuario"
                  : "Reactivar usuario"}
            </DialogTitle>
            <DialogDescription>
              {confirm && user ? (
                confirm.kind === "reset" ? (
                  <>
                    Se generará una contraseña temporal nueva para{" "}
                    <strong>{user.email}</strong>, se invalidará la actual y se
                    enviará por correo. La verás una sola vez en pantalla.
                  </>
                ) : confirm.next === "disabled" ? (
                  <>
                    <strong>{user.email}</strong> perderá el acceso a CheckWise
                    de inmediato. Sus datos y documentos se conservan; puedes
                    reactivar la cuenta cuando quieras.
                  </>
                ) : (
                  <>
                    <strong>{user.email}</strong> recuperará el acceso a
                    CheckWise con su contraseña actual.
                  </>
                )
              ) : null}
            </DialogDescription>
          </DialogHeader>

          {confirmError ? (
            <div className="flex items-start gap-2 rounded-md border border-[color:var(--status-error-border)] bg-[color:var(--status-error-bg)] px-3 py-2 text-[12px] text-[color:var(--status-error-text)]">
              <Warning className="mt-0.5 h-3.5 w-3.5 shrink-0" weight="fill" aria-hidden="true" />
              <span>{confirmError}</span>
            </div>
          ) : null}

          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => setConfirm(null)}
              disabled={confirmBusy}
            >
              Cancelar
            </Button>
            <Button
              type="button"
              variant={
                confirm?.kind === "status" && confirm.next === "disabled"
                  ? "destructive"
                  : "default"
              }
              loading={confirmBusy}
              onClick={onConfirmAction}
            >
              {confirm?.kind === "reset"
                ? "Restablecer"
                : confirm?.next === "disabled"
                  ? "Desactivar"
                  : "Reactivar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Reset result — temp password shown ONCE. */}
      <Dialog
        open={Boolean(resetResult)}
        onOpenChange={(next) => {
          if (!next) setResetResult(null);
        }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Key
                className="h-4 w-4 text-[color:var(--text-teal)]"
                weight="bold"
                aria-hidden="true"
              />
              Contraseña temporal generada
            </DialogTitle>
            <DialogDescription>
              {resetResult ? (
                <>
                  Para <strong>{resetResult.email}</strong>. Al entrar con esta
                  contraseña, el sistema le pedirá cambiarla inmediatamente.
                </>
              ) : null}
            </DialogDescription>
          </DialogHeader>

          {resetResult ? (
            <div className="space-y-3 text-sm">
              <div className="rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-page)] p-4">
                <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                  Se muestra una sola vez — guárdala antes de cerrar
                </p>
                <div className="mt-2 flex items-center justify-between gap-3">
                  <code className="select-all break-all font-mono text-lg font-semibold text-[color:var(--text-primary)]">
                    {resetResult.temp_password}
                  </code>
                  <Button
                    type="button"
                    size="sm"
                    variant={copied ? "default" : "outline"}
                    onClick={copyTempPassword}
                  >
                    <Copy className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
                    {copied ? "Copiada" : "Copiar"}
                  </Button>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Badge
                  variant={
                    resetResult.email_status === "sent" ? "success" : "warning"
                  }
                >
                  <PaperPlaneTilt className="h-3 w-3" weight="bold" aria-hidden="true" />
                  {resetResult.email_status === "sent"
                    ? "Correo enviado"
                    : `Correo: ${resetResult.email_status}`}
                </Badge>
                <span className="text-[11px] text-[color:var(--text-tertiary)]">
                  Si el correo no llegó, mándale la contraseña por WhatsApp.
                </span>
              </div>
              {resetResult.email_error ? (
                <p className="rounded-md border border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-bg)] p-3 text-[11px] text-[color:var(--status-warning-text)]">
                  Detalle del correo: {resetResult.email_error}
                </p>
              ) : null}
            </div>
          ) : null}

          <DialogFooter>
            <Button type="button" onClick={() => setResetResult(null)}>
              Listo, la guardé
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PlatformShell>
  );
}

function Field({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="min-w-0">
      <dt className="text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
        {label}
      </dt>
      <dd
        className={
          "mt-0.5 truncate text-[13px] text-[color:var(--text-primary)]" +
          (mono ? " font-mono text-[12px]" : "")
        }
        title={value}
      >
        {value}
      </dd>
    </div>
  );
}
