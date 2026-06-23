"use client";

/**
 * Client seat management UI.
 *
 * UI over the `/client/users` seat API. Any Approver (`client_admin`) of the
 * org — and CheckWise support staff — creates, disables, removes, resets and
 * re-tiers seats within the org's `seat_limit`; read-only Viewers get a
 * roster without mutation affordances. The tier split is enforced
 * server-side; hiding controls here is a UX nicety, not the boundary.
 */

import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  ArrowClockwise,
  Key,
  Trash,
  UserPlus,
  Users,
  Warning,
} from "@phosphor-icons/react";

import { ClientShell } from "../../_shell";
import { Surface } from "@/components/checkwise/dashboard/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import {
  createClientUser,
  listClientUsers,
  removeClientUser,
  resetClientUserPassword,
  updateClientUserRole,
  updateClientUserStatus,
  type ClientUserItem,
  type ClientUsersList,
} from "@/lib/api/client";
import { useUrlClientId } from "@/lib/workspace/use-url-client-id";
import { apiErrorDetail as errorDetail } from "@/lib/api/error-detail";

type TempCredential = {
  email: string;
  temp_password: string;
  email_status: string;
  reinstated?: boolean;
};

// A one-time credential reveal (create + reset both return a temp password).
function CredentialNotice({
  cred,
  onDismiss,
}: {
  cred: TempCredential;
  onDismiss: () => void;
}) {
  // Backend EmailDeliveryResult emits "sent" | "failed" | "skipped".
  const emailed = cred.email_status === "sent";
  return (
    <div className="rounded-lg border border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-bg)] p-3 text-[13px]">
      <p className="font-medium text-[color:var(--status-warning-text)]">
        Contraseña temporal para {cred.email}
      </p>
      <p className="mt-1 text-[color:var(--text-secondary)]">
        Se muestra una sola vez. {emailed
          ? "También la enviamos por correo."
          : "El correo no se pudo enviar — compártela tú directamente."}{" "}
        El usuario deberá cambiarla en su primer inicio de sesión.
      </p>
      <code className="mt-2 block select-all rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)] px-3 py-2 font-mono text-sm text-[color:var(--text-primary)]">
        {cred.temp_password}
      </code>
      <div className="mt-2 flex justify-end">
        <Button variant="ghost" size="sm" onClick={onDismiss}>
          Entendido
        </Button>
      </div>
    </div>
  );
}

function statusBadge(user: ClientUserItem) {
  if (user.status !== "active") {
    return <Badge variant="secondary">Desactivado</Badge>;
  }
  if (user.pending_first_login) {
    return <Badge variant="warning">Pendiente de activación</Badge>;
  }
  return <Badge variant="success">Activo</Badge>;
}

export default function ClientSeatsPage() {
  const urlClientId = useUrlClientId();
  const clientParam = urlClientId ? { client_id: urlClientId } : undefined;

  const [data, setData] = useState<ClientUsersList | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Add-user form.
  const [newName, setNewName] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newRole, setNewRole] = useState<"client_admin" | "client_viewer">(
    "client_viewer",
  );
  const [createBusy, setCreateBusy] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Per-row state.
  const [busyUserId, setBusyUserId] = useState<string | null>(null);
  const [rowError, setRowError] = useState<string | null>(null);
  const [confirmRemoveId, setConfirmRemoveId] = useState<string | null>(null);

  // One-time credential reveal (shared by create + reset).
  const [credential, setCredential] = useState<TempCredential | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      setData(await listClientUsers(clientParam));
    } catch (err) {
      setLoadError(errorDetail(err));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlClientId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const canManage = data?.can_manage ?? false;
  const seatsAvailable = data?.seats_available ?? 0;

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setCreateError(null);
    setCredential(null);
    setCreateBusy(true);
    try {
      const res = await createClientUser(
        { full_name: newName.trim(), email: newEmail.trim(), role: newRole },
        clientParam,
      );
      setCredential({
        email: res.email,
        temp_password: res.temp_password,
        email_status: res.email_status,
        reinstated: res.reinstated,
      });
      setNewName("");
      setNewEmail("");
      setNewRole("client_viewer");
      await reload();
    } catch (err) {
      setCreateError(errorDetail(err));
    } finally {
      setCreateBusy(false);
    }
  }

  async function runRowAction(userId: string, fn: () => Promise<void>) {
    setRowError(null);
    setBusyUserId(userId);
    try {
      await fn();
    } catch (err) {
      setRowError(errorDetail(err));
    } finally {
      setBusyUserId(null);
    }
  }

  return (
    <ClientShell
      title="Usuarios y accesos"
      description="Administra quién puede entrar al portal de tu empresa. Un Aprobador agrega usuarios (Aprobadores o de Solo lectura) hasta el límite de tu plan; los perfiles de Solo lectura solo consultan."
    >
      <div className="space-y-5">
        {loadError ? (
          <div
            role="alert"
            className="flex items-center gap-2 rounded-lg border border-[color:var(--status-error-border)] bg-[color:var(--status-error-bg)] px-4 py-3 text-[13px] text-[color:var(--status-error-text)]"
          >
            <Warning className="h-4 w-4 shrink-0" weight="fill" />
            {loadError}
          </div>
        ) : null}

        <Surface
          title="Usuarios del portal"
          icon={Users}
          description={
            data
              ? `${data.seats_used} de ${data.seat_limit} usuarios${
                  seatsAvailable > 0
                    ? ` · ${seatsAvailable} disponible${seatsAvailable === 1 ? "" : "s"}`
                    : " · sin lugares libres"
                }`
              : undefined
          }
        >
          {loading && !data ? (
            <p className="text-[13px] text-[color:var(--text-secondary)]">Cargando…</p>
          ) : data && data.users.length > 0 ? (
            <ul className="divide-y divide-[color:var(--border-subtle)]">
              {data.users.map((user) => {
                const busy = busyUserId === user.user_id;
                const isConfirming = confirmRemoveId === user.user_id;
                return (
                  <li
                    key={user.user_id}
                    className="flex flex-wrap items-center gap-x-3 gap-y-2 py-3"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="truncate text-sm font-medium text-[color:var(--text-primary)]">
                          {user.full_name}
                        </span>
                        {user.is_primary ? (
                          <Badge variant="brand">Titular</Badge>
                        ) : user.role === "client_admin" ? (
                          <Badge variant="info">Aprobador</Badge>
                        ) : (
                          <Badge variant="outline">Solo lectura</Badge>
                        )}
                        {statusBadge(user)}
                      </div>
                      <span className="block truncate font-mono text-[11px] text-[color:var(--text-secondary)]">
                        {user.email}
                      </span>
                    </div>

                    {canManage && !user.is_primary ? (
                      <div className="flex flex-wrap items-center gap-1.5">
                        {/* Tier toggle. An Approver (or staff) can promote a
                            Viewer to Approver and demote an Approver back. */}
                        {user.status === "active" &&
                        user.role === "client_viewer" ? (
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={busy}
                            onClick={() =>
                              runRowAction(user.user_id, async () => {
                                await updateClientUserRole(
                                  user.user_id,
                                  "client_admin",
                                  clientParam,
                                );
                                await reload();
                              })
                            }
                          >
                            Hacer Aprobador
                          </Button>
                        ) : null}
                        {user.status === "active" &&
                        user.role === "client_admin" ? (
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={busy}
                            onClick={() =>
                              runRowAction(user.user_id, async () => {
                                await updateClientUserRole(
                                  user.user_id,
                                  "client_viewer",
                                  clientParam,
                                );
                                await reload();
                              })
                            }
                          >
                            Hacer Solo lectura
                          </Button>
                        ) : null}
                        {user.status === "active" ? (
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={busy}
                            onClick={() =>
                              runRowAction(user.user_id, async () => {
                                await updateClientUserStatus(
                                  user.user_id,
                                  "disabled",
                                  clientParam,
                                );
                                await reload();
                              })
                            }
                          >
                            Desactivar
                          </Button>
                        ) : (
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={busy}
                            onClick={() =>
                              runRowAction(user.user_id, async () => {
                                await updateClientUserStatus(
                                  user.user_id,
                                  "active",
                                  clientParam,
                                );
                                await reload();
                              })
                            }
                          >
                            <ArrowClockwise className="h-3.5 w-3.5" weight="bold" />
                            Reactivar
                          </Button>
                        )}
                        {user.status === "active" ? (
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={busy}
                            onClick={() =>
                              runRowAction(user.user_id, async () => {
                                const res = await resetClientUserPassword(
                                  user.user_id,
                                  clientParam,
                                );
                                setCreateError(null);
                                setCredential({
                                  email: res.email,
                                  temp_password: res.temp_password,
                                  email_status: res.email_status,
                                });
                              })
                            }
                          >
                            <Key className="h-3.5 w-3.5" weight="bold" />
                            Restablecer
                          </Button>
                        ) : null}
                        {isConfirming ? (
                          <span className="flex items-center gap-1.5">
                            <Button
                              variant="destructive"
                              size="sm"
                              disabled={busy}
                              onClick={() =>
                                runRowAction(user.user_id, async () => {
                                  await removeClientUser(user.user_id, clientParam);
                                  setConfirmRemoveId(null);
                                  await reload();
                                })
                              }
                            >
                              Confirmar
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              disabled={busy}
                              onClick={() => setConfirmRemoveId(null)}
                            >
                              Cancelar
                            </Button>
                          </span>
                        ) : (
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={busy}
                            aria-label={`Quitar a ${user.full_name}`}
                            onClick={() => {
                              setRowError(null);
                              setConfirmRemoveId(user.user_id);
                            }}
                          >
                            <Trash className="h-3.5 w-3.5" weight="bold" />
                          </Button>
                        )}
                      </div>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="text-[13px] text-[color:var(--text-secondary)]">
              No hay usuarios todavía.
            </p>
          )}

          {rowError ? (
            <p className="mt-3 text-[12px] text-[color:var(--status-error-text)]">
              {rowError}
            </p>
          ) : null}
        </Surface>

        {credential ? (
          <CredentialNotice cred={credential} onDismiss={() => setCredential(null)} />
        ) : null}

        {canManage ? (
          <Surface title="Agregar usuario" icon={UserPlus}>
            {seatsAvailable <= 0 ? (
              <p className="text-[13px] text-[color:var(--text-secondary)]">
                Has alcanzado el máximo de {data?.seat_limit} usuarios. Quita
                uno para liberar un lugar.
              </p>
            ) : (
              <form onSubmit={handleCreate} className="space-y-3">
                <p className="text-[12px] text-[color:var(--text-secondary)]">
                  Elige el nivel de acceso. Un <strong>Aprobador</strong>{" "}
                  administra el portafolio, los proveedores y al equipo; un
                  perfil de <strong>Solo lectura</strong> únicamente consulta.
                </p>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-1">
                    <Label htmlFor="seat-name">Nombre completo</Label>
                    <Input
                      id="seat-name"
                      value={newName}
                      onChange={(e) => setNewName(e.target.value)}
                      placeholder="Ana Martínez"
                      required
                      minLength={2}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="seat-email">Correo</Label>
                    <Input
                      id="seat-email"
                      type="email"
                      value={newEmail}
                      onChange={(e) => setNewEmail(e.target.value)}
                      placeholder="ana@empresa.com"
                      required
                    />
                  </div>
                  <div className="space-y-1 sm:col-span-2">
                    <Label htmlFor="seat-role">Nivel de acceso</Label>
                    <Select
                      id="seat-role"
                      value={newRole}
                      onChange={(e) =>
                        setNewRole(
                          e.target.value as "client_admin" | "client_viewer",
                        )
                      }
                    >
                      <option value="client_viewer">
                        Solo lectura — solo consulta
                      </option>
                      <option value="client_admin">
                        Aprobador — administra el portafolio y al equipo
                      </option>
                    </Select>
                  </div>
                </div>
                {createError ? (
                  <p className="text-[12px] text-[color:var(--status-error-text)]">
                    {createError}
                  </p>
                ) : null}
                <div className="flex justify-end">
                  <Button type="submit" size="sm" disabled={createBusy}>
                    <UserPlus className="h-4 w-4" weight="bold" />
                    {createBusy ? "Agregando…" : "Agregar usuario"}
                  </Button>
                </div>
              </form>
            )}
          </Surface>
        ) : data ? (
          <p className="text-[12px] text-[color:var(--text-tertiary)]">
            Tu acceso es de Solo lectura. Solo un Aprobador puede administrar
            los usuarios.
          </p>
        ) : null}
      </div>
    </ClientShell>
  );
}
