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
  PencilSimple,
  Plus,
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

import { PlatformShell } from "../../_shell";
import {
  AdminApiError,
  type AdminResetPasswordResponse,
  type AdminUserDeletionPreview,
  type AdminUserDetail,
  type MembershipRoleCode,
  deleteUser,
  getUser,
  getUserDeletionPreview,
  grantMembership,
  promoteMembership,
  resetUserPassword,
  restoreUser,
  revokeMembership,
  updateUserIdentity,
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

/** Roles grantable per org kind — mirrors the backend's _ROLE_ORG_KIND
 *  guard so the form never offers a combination the API would 422. */
const ROLES_BY_KIND: Record<string, MembershipRoleCode[]> = {
  client: ["client_admin"],
  internal: ["internal_admin", "reviewer", "platform_admin"],
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

  // Edit-identity dialog
  const [editOpen, setEditOpen] = useState(false);
  const [editBusy, setEditBusy] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editEmail, setEditEmail] = useState("");
  const [editPhone, setEditPhone] = useState("");
  // Transient banner after a successful email change (delivery status).
  const [emailNotice, setEmailNotice] = useState<string | null>(null);

  // Membership editor (Phase 4)
  const [memberBusy, setMemberBusy] = useState<string | null>(null); // membership_id | "grant"
  const [memberError, setMemberError] = useState<string | null>(null);
  const [grantOrgId, setGrantOrgId] = useState("");
  const [grantRole, setGrantRole] = useState<MembershipRoleCode | "">("");

  function membershipApiError(err: unknown, fallback: string) {
    if (err instanceof AdminApiError && err.status === 401) {
      router.replace("/login");
      return;
    }
    setMemberError(apiErrorMessage(err, fallback));
  }

  async function runMembership(
    key: string,
    fn: () => Promise<unknown>,
    fallback: string,
  ) {
    setMemberBusy(key);
    setMemberError(null);
    try {
      await fn();
      await load(); // re-fetch the full picture (roles, seats, primary)
    } catch (err) {
      membershipApiError(err, fallback);
    } finally {
      setMemberBusy(null);
    }
  }

  // Delete / restore (Phase 5)
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deletePreview, setDeletePreview] =
    useState<AdminUserDeletionPreview | null>(null);
  const [deleteReason, setDeleteReason] = useState("");
  const [deleteConfirm, setDeleteConfirm] = useState("");
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [restoreBusy, setRestoreBusy] = useState(false);

  async function openDelete() {
    if (!user) return;
    setDeleteError(null);
    setDeleteReason("");
    setDeleteConfirm("");
    setDeletePreview(null);
    setDeleteOpen(true);
    try {
      setDeletePreview(await getUserDeletionPreview(user.user_id));
    } catch {
      // Preview is advisory — the modal still works without it.
    }
  }

  async function onConfirmDelete() {
    if (!user) return;
    setDeleteBusy(true);
    setDeleteError(null);
    try {
      await deleteUser(user.user_id, deleteReason.trim() || undefined);
      setDeleteOpen(false);
      await load();
    } catch (err) {
      if (err instanceof AdminApiError && err.status === 401) {
        router.replace("/login");
        return;
      }
      setDeleteError(apiErrorMessage(err, "No pudimos eliminar la cuenta."));
    } finally {
      setDeleteBusy(false);
    }
  }

  async function onRestore() {
    if (!user) return;
    setRestoreBusy(true);
    try {
      await restoreUser(user.user_id);
      await load();
    } catch (err) {
      if (err instanceof AdminApiError && err.status === 401) {
        router.replace("/login");
        return;
      }
      setEmailNotice(null);
      setError(apiErrorMessage(err, "No pudimos restaurar la cuenta."));
    } finally {
      setRestoreBusy(false);
    }
  }

  function openEdit() {
    if (!user) return;
    setEditError(null);
    setEditName(user.full_name);
    setEditEmail(user.email);
    setEditPhone(user.phone ?? "");
    setEditOpen(true);
  }

  async function onSubmitEdit() {
    if (!user) return;
    const body: { full_name?: string; email?: string; phone?: string | null } =
      {};
    const name = editName.trim();
    const email = editEmail.trim().toLowerCase();
    const phone = editPhone.trim();
    if (name !== user.full_name) body.full_name = name;
    if (email !== user.email) body.email = email;
    if (phone !== (user.phone ?? "")) body.phone = phone || null;
    if (Object.keys(body).length === 0) {
      setEditOpen(false);
      return;
    }
    setEditBusy(true);
    setEditError(null);
    try {
      const updated = await updateUserIdentity(user.user_id, body);
      setUser((u) =>
        u
          ? {
              ...u,
              full_name: updated.full_name,
              email: updated.email,
              phone: updated.phone,
            }
          : u,
      );
      setEditOpen(false);
      if (updated.email_changed) {
        setEmailNotice(
          updated.notification_status === "sent"
            ? "Correo actualizado. Avisamos a la dirección anterior y a la nueva."
            : updated.notification_status === "skipped"
              ? "Correo actualizado. No se enviaron avisos (correo no configurado)."
              : "Correo actualizado. Algún aviso no pudo enviarse; verifica con la persona.",
        );
      }
    } catch (err) {
      if (err instanceof AdminApiError && err.status === 401) {
        router.replace("/login");
        return;
      }
      setEditError(apiErrorMessage(err, "No pudimos guardar los cambios."));
    } finally {
      setEditBusy(false);
    }
  }

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

  // Grant-role form options: the user's distinct orgs, and for the
  // chosen org the roles valid for its kind that they don't already hold.
  const orgOptions = user
    ? Array.from(
        new Map(
          user.memberships.map((m) => [m.organization_id, m]),
        ).values(),
      )
    : [];
  const grantOrg = orgOptions.find((o) => o.organization_id === grantOrgId);
  const grantRoleChoices: MembershipRoleCode[] =
    grantOrg && user
      ? (ROLES_BY_KIND[grantOrg.organization_kind] ?? []).filter(
          (role) =>
            !user.memberships.some(
              (m) =>
                m.organization_id === grantOrg.organization_id &&
                m.role === role &&
                m.status === "active",
            ),
        )
      : [];

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
              <Button size="sm" variant="outline" onClick={openEdit}>
                <PencilSimple
                  className="h-3.5 w-3.5"
                  weight="bold"
                  aria-hidden="true"
                />
                Editar
              </Button>
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
              <Button
                size="sm"
                variant="outline"
                className="text-[color:var(--status-error-text)]"
                onClick={openDelete}
              >
                <Trash className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
                Eliminar
              </Button>
            </>
          ) : null}
          {user && isDeleted ? (
            <Button size="sm" loading={restoreBusy} onClick={onRestore}>
              <ArrowCounterClockwise
                className="h-3.5 w-3.5"
                weight="bold"
                aria-hidden="true"
              />
              Restaurar cuenta
            </Button>
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

          {/* Email-change confirmation notice (dismissible). */}
          {emailNotice ? (
            <div className="flex items-start justify-between gap-2 rounded-md border border-[color:var(--status-success-border)] bg-[color:var(--status-success-bg)] px-3 py-2.5 text-[12px] text-[color:var(--status-success-text)]">
              <span>{emailNotice}</span>
              <button
                type="button"
                onClick={() => setEmailNotice(null)}
                className="shrink-0 font-medium underline-offset-2 hover:underline"
              >
                Cerrar
              </button>
            </div>
          ) : null}

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
                      <th className="py-1.5 pr-3 font-medium">Estatus</th>
                      <th className="py-1.5 font-medium text-right">Acciones</th>
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
                        <td className="py-2 pr-3">
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
                        <td className="py-2 text-right">
                          {isDeleted ? null : m.is_primary ? (
                            <span className="text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                              Titular
                            </span>
                          ) : m.status === "active" ? (
                            <span className="flex justify-end gap-1 whitespace-nowrap">
                              {m.organization_kind === "client" &&
                              m.role === "client_admin" ? (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  loading={memberBusy === m.membership_id}
                                  onClick={() =>
                                    runMembership(
                                      m.membership_id,
                                      () =>
                                        promoteMembership(
                                          user.user_id,
                                          m.membership_id,
                                        ),
                                      "No pudimos transferir la titularidad.",
                                    )
                                  }
                                  title="Hacer titular de la organización"
                                >
                                  <Crown
                                    className="h-3.5 w-3.5"
                                    weight="bold"
                                    aria-hidden="true"
                                  />
                                  Hacer titular
                                </Button>
                              ) : null}
                              <Button
                                variant="ghost"
                                size="sm"
                                className="text-[color:var(--status-error-text)]"
                                loading={memberBusy === m.membership_id}
                                onClick={() =>
                                  runMembership(
                                    m.membership_id,
                                    () =>
                                      revokeMembership(
                                        user.user_id,
                                        m.membership_id,
                                      ),
                                    "No pudimos quitar el rol.",
                                  )
                                }
                              >
                                <Trash
                                  className="h-3.5 w-3.5"
                                  weight="bold"
                                  aria-hidden="true"
                                />
                                Quitar
                              </Button>
                            </span>
                          ) : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {memberError ? (
              <div className="mt-3 flex items-start gap-2 rounded-md border border-[color:var(--status-error-border)] bg-[color:var(--status-error-bg)] px-3 py-2 text-[12px] text-[color:var(--status-error-text)]">
                <Warning className="mt-0.5 h-3.5 w-3.5 shrink-0" weight="fill" aria-hidden="true" />
                <span>{memberError}</span>
              </div>
            ) : null}

            {/* Grant a role within an org the user already belongs to. */}
            {!isDeleted && orgOptions.length > 0 ? (
              <div className="mt-4 flex flex-wrap items-end gap-2 border-t border-[color:var(--border-subtle)] pt-4">
                <label className="flex flex-col gap-1 text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                  Organización
                  <Select
                    value={grantOrgId}
                    onChange={(e) => {
                      setGrantOrgId(e.target.value);
                      setGrantRole("");
                      setMemberError(null);
                    }}
                    className="h-9 text-[12px]"
                  >
                    <option value="">Selecciona…</option>
                    {orgOptions.map((o) => (
                      <option key={o.organization_id} value={o.organization_id}>
                        {o.organization_name}
                      </option>
                    ))}
                  </Select>
                </label>
                <label className="flex flex-col gap-1 text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
                  Rol a agregar
                  <Select
                    value={grantRole}
                    onChange={(e) =>
                      setGrantRole(e.target.value as MembershipRoleCode | "")
                    }
                    disabled={!grantOrg || grantRoleChoices.length === 0}
                    className="h-9 text-[12px]"
                  >
                    <option value="">
                      {grantOrg && grantRoleChoices.length === 0
                        ? "Sin roles disponibles"
                        : "Selecciona…"}
                    </option>
                    {grantRoleChoices.map((role) => (
                      <option key={role} value={role}>
                        {roleLabel(role)}
                      </option>
                    ))}
                  </Select>
                </label>
                <Button
                  size="sm"
                  loading={memberBusy === "grant"}
                  disabled={!grantOrgId || !grantRole}
                  onClick={() =>
                    runMembership(
                      "grant",
                      () =>
                        grantMembership(user.user_id, {
                          organization_id: grantOrgId,
                          role: grantRole as MembershipRoleCode,
                        }),
                      "No pudimos agregar el rol.",
                    ).then(() => {
                      setGrantRole("");
                    })
                  }
                >
                  <Plus className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
                  Agregar rol
                </Button>
              </div>
            ) : null}
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

      {/* Delete (soft, recoverable) */}
      <Dialog
        open={deleteOpen}
        onOpenChange={(next) => {
          if (!next && !deleteBusy) setDeleteOpen(false);
        }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Eliminar cuenta</DialogTitle>
            <DialogDescription>
              {user ? (
                <>
                  Se eliminará la cuenta de <strong>{user.email}</strong>. Es
                  reversible: podrás restaurarla después. Sus roles se quitan y
                  deberán reasignarse al restaurar.
                </>
              ) : null}
            </DialogDescription>
          </DialogHeader>

          {deletePreview &&
          (deletePreview.primary_of_orgs.length > 0 ||
            deletePreview.owned_workspaces > 0 ||
            deletePreview.is_last_internal_admin) ? (
            <div className="space-y-1 rounded-md border border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-bg)] px-3 py-2.5 text-[12px] text-[color:var(--status-warning-text)]">
              <p className="font-semibold">Esto también afecta:</p>
              <ul className="list-inside list-disc space-y-0.5">
                {deletePreview.primary_of_orgs.map((name) => (
                  <li key={name}>
                    Titular de <strong>{name}</strong> — quedará sin titular.
                  </li>
                ))}
                {deletePreview.owned_workspaces > 0 ? (
                  <li>
                    {deletePreview.owned_workspaces} espacio(s) de proveedor
                    quedarán sin dueño.
                  </li>
                ) : null}
                {deletePreview.is_last_internal_admin ? (
                  <li>Es el último administrador interno activo.</li>
                ) : null}
              </ul>
            </div>
          ) : null}

          <div className="space-y-3">
            <div className="space-y-1">
              <Label htmlFor="del-reason">Motivo (opcional)</Label>
              <Input
                id="del-reason"
                value={deleteReason}
                onChange={(e) => setDeleteReason(e.target.value)}
                placeholder="Cuenta duplicada, baja, etc."
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="del-confirm">
                Escribe <strong>ELIMINAR</strong> para confirmar
              </Label>
              <Input
                id="del-confirm"
                value={deleteConfirm}
                onChange={(e) => setDeleteConfirm(e.target.value)}
                placeholder="ELIMINAR"
                autoComplete="off"
              />
            </div>
          </div>

          {deleteError ? (
            <div className="flex items-start gap-2 rounded-md border border-[color:var(--status-error-border)] bg-[color:var(--status-error-bg)] px-3 py-2 text-[12px] text-[color:var(--status-error-text)]">
              <Warning className="mt-0.5 h-3.5 w-3.5 shrink-0" weight="fill" aria-hidden="true" />
              <span>{deleteError}</span>
            </div>
          ) : null}

          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => setDeleteOpen(false)}
              disabled={deleteBusy}
            >
              Cancelar
            </Button>
            <Button
              type="button"
              variant="destructive"
              loading={deleteBusy}
              disabled={deleteConfirm.trim() !== "ELIMINAR"}
              onClick={onConfirmDelete}
            >
              Eliminar cuenta
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit identity */}
      <Dialog
        open={editOpen}
        onOpenChange={(next) => {
          if (!next && !editBusy) setEditOpen(false);
        }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Editar identidad</DialogTitle>
            <DialogDescription>
              Corrige el nombre, el correo o el teléfono. Si cambias el correo,
              avisaremos tanto a la dirección anterior como a la nueva.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3">
            <div className="space-y-1">
              <Label htmlFor="edit-name">Nombre completo</Label>
              <Input
                id="edit-name"
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                placeholder="María Pérez"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="edit-email">Correo electrónico</Label>
              <Input
                id="edit-email"
                type="email"
                value={editEmail}
                onChange={(e) => setEditEmail(e.target.value)}
                autoComplete="email"
                placeholder="contacto@empresa.com"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="edit-phone">Teléfono (opcional)</Label>
              <Input
                id="edit-phone"
                type="tel"
                value={editPhone}
                onChange={(e) => setEditPhone(e.target.value)}
                autoComplete="tel"
                placeholder="+52 55 1234 5678"
              />
            </div>
          </div>

          {editError ? (
            <div className="flex items-start gap-2 rounded-md border border-[color:var(--status-error-border)] bg-[color:var(--status-error-bg)] px-3 py-2 text-[12px] text-[color:var(--status-error-text)]">
              <Warning className="mt-0.5 h-3.5 w-3.5 shrink-0" weight="fill" aria-hidden="true" />
              <span>{editError}</span>
            </div>
          ) : null}

          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => setEditOpen(false)}
              disabled={editBusy}
            >
              Cancelar
            </Button>
            <Button type="button" loading={editBusy} onClick={onSubmitEdit}>
              Guardar cambios
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

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
