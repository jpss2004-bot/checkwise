"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowCounterClockwise,
  ArrowRight,
  Copy,
  Key,
  PaperPlaneTilt,
  Prohibit,
  UserPlus,
  Warning,
} from "@phosphor-icons/react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/ui/data-table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { SearchInput } from "@/components/ui/search-input";
import { Select } from "@/components/ui/select";

import { PlatformShell } from "../_shell";
import {
  AdminApiError,
  type AdminResetPasswordResponse,
  type AdminUserRow,
  listUsers,
  resetUserPassword,
  updateUserStatus,
} from "@/lib/api/admin";
import { roleLabel } from "@/lib/constants/labels";
import { formatDateTime } from "@/lib/format/datetime";

/**
 * /platform/users — listing + lifecycle surface for existing users
 * (P3 audit, 2026-06-10). Closes the write-only gap: until this page
 * the only user-management surface was /platform/users/new, so a
 * departed employee couldn't be disabled and a forgotten password
 * couldn't be reset without touching the database.
 *
 * Actions are intentionally minimal: reset password (new temp
 * password shown ONCE, mirrored from the provisioning flow) and
 * disable / reactivate. Edits to identity or memberships stay out of
 * scope — those flow through the org/vendor surfaces.
 */

const PAGE_LIMIT = 50;

type StatusFilter = "" | "active" | "disabled";

const ROLE_OPTIONS = [
  "operations_admin",
  "platform_admin",
  "client_admin",
  "client_viewer",
  "provider",
] as const;

type ConfirmState =
  | { kind: "reset"; user: AdminUserRow }
  | { kind: "status"; next: "active" | "disabled"; user: AdminUserRow };

/** Backend errors arrive as the raw response body — usually FastAPI's
 *  ``{"detail": "..."}`` envelope (Spanish on 409s). Unwrap it so the
 *  operator reads the sentence, not the JSON. */
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

function formatDate(iso: string): string {
  return formatDateTime(
    iso,
    { day: "2-digit", month: "short", year: "numeric" },
    iso,
  );
}

/** Same humanisation ladder the portal dashboard uses for recency. */
function formatLastLogin(iso: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const diffDays = Math.floor((Date.now() - date.getTime()) / 86_400_000);
  if (diffDays <= 0) return "Hoy";
  if (diffDays === 1) return "Ayer";
  if (diffDays < 7) return `Hace ${diffDays}d`;
  if (diffDays < 30) return `Hace ${Math.floor(diffDays / 7)} sem`;
  return formatDate(iso);
}

export default function PlatformUsersPage() {
  const router = useRouter();
  const [rows, setRows] = useState<AdminUserRow[] | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("");
  const [roleFilter, setRoleFilter] = useState("");
  const [includeDeleted, setIncludeDeleted] = useState(false);

  // Action dialogs
  const [confirm, setConfirm] = useState<ConfirmState | null>(null);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [resetResult, setResetResult] =
    useState<AdminResetPasswordResponse | null>(null);
  const [copied, setCopied] = useState(false);

  function buildParams(eff: {
    q: string;
    status: StatusFilter;
    role: string;
    includeDeleted: boolean;
  }): Parameters<typeof listUsers>[0] {
    const params: Parameters<typeof listUsers>[0] = { limit: PAGE_LIMIT };
    if (eff.q.trim()) params.q = eff.q.trim();
    if (eff.status) params.status = eff.status;
    if (eff.role) params.role = eff.role;
    if (eff.includeDeleted) params.include_deleted = true;
    return params;
  }

  async function refresh(
    overrides: {
      q?: string;
      status?: StatusFilter;
      role?: string;
      includeDeleted?: boolean;
    } = {},
  ) {
    setLoading(true);
    setError(null);
    const eff = {
      q: overrides.q !== undefined ? overrides.q : q,
      status: overrides.status !== undefined ? overrides.status : statusFilter,
      role: overrides.role !== undefined ? overrides.role : roleFilter,
      includeDeleted:
        overrides.includeDeleted !== undefined
          ? overrides.includeDeleted
          : includeDeleted,
    };
    try {
      const data = await listUsers(buildParams(eff));
      setRows(data.items);
      setTotal(data.total);
    } catch (err) {
      if (err instanceof AdminApiError && err.status === 401) {
        router.replace("/login");
        return;
      }
      setError(apiErrorMessage(err, "Error al cargar los usuarios."));
      setRows(null);
    } finally {
      setLoading(false);
    }
  }

  async function loadMore() {
    if (!rows) return;
    setLoadingMore(true);
    try {
      const data = await listUsers({
        ...buildParams({
          q,
          status: statusFilter,
          role: roleFilter,
          includeDeleted,
        }),
        offset: rows.length,
      });
      setRows((current) => (current ? [...current, ...data.items] : data.items));
      setTotal(data.total);
    } catch (err) {
      if (err instanceof AdminApiError && err.status === 401) {
        router.replace("/login");
        return;
      }
      setError(apiErrorMessage(err, "Error al cargar más usuarios."));
    } finally {
      setLoadingMore(false);
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Debounced search — refetch ~300ms after the operator stops typing.
  // The first render is skipped (the mount effect already fetched).
  const searchInitialized = useRef(false);
  useEffect(() => {
    if (!searchInitialized.current) {
      searchInitialized.current = true;
      return;
    }
    const timer = setTimeout(() => refresh({ q }), 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  async function onConfirmAction() {
    if (!confirm) return;
    setConfirmBusy(true);
    setConfirmError(null);
    try {
      if (confirm.kind === "reset") {
        const result = await resetUserPassword(confirm.user.user_id);
        // The reset re-arms the must-change flag — reflect it in place.
        setRows((current) =>
          current
            ? current.map((row) =>
                row.user_id === result.user_id
                  ? { ...row, must_change_password: true }
                  : row,
              )
            : current,
        );
        setConfirm(null);
        setCopied(false);
        setResetResult(result);
      } else {
        const updated = await updateUserStatus(
          confirm.user.user_id,
          confirm.next,
        );
        // If a status filter is active and the row no longer matches,
        // drop it (same rule contact-requests applies); otherwise patch
        // the row in place so no refetch is needed.
        if (statusFilter && updated.status !== statusFilter) {
          setRows((current) =>
            current
              ? current.filter((row) => row.user_id !== updated.user_id)
              : current,
          );
          setTotal((t) => Math.max(0, t - 1));
        } else {
          setRows((current) =>
            current
              ? current.map((row) =>
                  row.user_id === updated.user_id
                    ? { ...row, status: updated.status }
                    : row,
                )
              : current,
          );
        }
        setConfirm(null);
      }
    } catch (err) {
      if (err instanceof AdminApiError && err.status === 401) {
        router.replace("/login");
        return;
      }
      // 409s carry the backend's Spanish detail (self-disable, reset on
      // a disabled account) — surface it inside the dialog.
      setConfirmError(
        apiErrorMessage(err, "No pudimos completar la acción."),
      );
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
      // Clipboard API blocked (localhost without HTTPS) — the password
      // is still visible on screen.
    }
  }

  const anyFilterActive = Boolean(q.trim() || statusFilter || roleFilter);

  return (
    <PlatformShell
      title="Usuarios"
      description="Todas las cuentas del sistema: clientes, proveedores y equipo interno. Desde aquí puedes restablecer contraseñas y desactivar o reactivar cuentas."
      actions={
        <Button asChild size="sm">
          <Link href="/platform/users/new">
            <UserPlus className="h-4 w-4" weight="bold" aria-hidden="true" />
            Nuevo usuario
            <ArrowRight className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
          </Link>
        </Button>
      }
    >
      <section className="space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-[11px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
            Buscar
            <SearchInput
              value={q}
              onValueChange={setQ}
              placeholder="Nombre o correo"
              ariaLabel="Buscar usuario por nombre o correo"
              className="w-56"
              inputClassName="h-9 text-[12px]"
            />
          </label>

          <label className="flex flex-col gap-1 text-[11px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
            Estatus
            <Select
              value={statusFilter}
              onChange={(e) => {
                const next = e.target.value as StatusFilter;
                setStatusFilter(next);
                refresh({ status: next });
              }}
              className="h-9 text-[12px]"
            >
              <option value="">Todos</option>
              <option value="active">Activos</option>
              <option value="disabled">Desactivados</option>
            </Select>
          </label>

          <label className="flex flex-col gap-1 text-[11px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
            Rol
            <Select
              value={roleFilter}
              onChange={(e) => {
                const next = e.target.value;
                setRoleFilter(next);
                refresh({ role: next });
              }}
              className="h-9 text-[12px]"
            >
              <option value="">Todos</option>
              {ROLE_OPTIONS.map((code) => (
                <option key={code} value={code}>
                  {roleLabel(code)}
                </option>
              ))}
            </Select>
          </label>

          <label className="flex items-center gap-1.5 text-[11px] text-[color:var(--text-secondary)]">
            <input
              type="checkbox"
              checked={includeDeleted}
              onChange={(e) => {
                const next = e.target.checked;
                setIncludeDeleted(next);
                refresh({ includeDeleted: next });
              }}
              className="h-3.5 w-3.5 rounded border-[color:var(--border-default)]"
            />
            Incluir eliminados
          </label>

          <div className="ml-auto font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
            {loading
              ? "Cargando…"
              : rows
                ? `${rows.length} de ${total}${anyFilterActive ? " (filtrado)" : ""}`
                : "—"}
          </div>
        </div>

        <DataTable<AdminUserRow>
          items={loading ? null : rows}
          loading={loading}
          error={error}
          onRetry={() => refresh()}
          rowKey={(row) => row.user_id}
          ariaLabel="Usuarios del sistema"
          emptyTitle={
            anyFilterActive
              ? "No hay usuarios con estos filtros"
              : "Aún no hay usuarios"
          }
          emptyDescription={
            anyFilterActive
              ? "Ajusta la búsqueda o vuelve a “Todos”."
              : "Da de alta el primer usuario desde “Nuevo usuario”."
          }
          columns={[
            {
              id: "full_name",
              header: "Nombre",
              cell: (row) => (
                <Link
                  href={`/platform/users/${row.user_id}`}
                  className="font-medium text-[color:var(--text-primary)] underline-offset-2 hover:text-[color:var(--text-brand)] hover:underline"
                >
                  {row.full_name || row.email}
                </Link>
              ),
            },
            {
              id: "email",
              header: "Correo",
              cell: (row) => (
                <span className="font-mono text-[11px] text-[color:var(--text-secondary)]">
                  {row.email}
                </span>
              ),
            },
            {
              id: "roles",
              header: "Roles",
              cell: (row) =>
                row.roles.length ? (
                  <span className="flex flex-wrap gap-1">
                    {row.roles.map((code) => (
                      <Badge key={code} variant="outline">
                        {roleLabel(code)}
                      </Badge>
                    ))}
                  </span>
                ) : (
                  <span className="text-[color:var(--text-tertiary)]">—</span>
                ),
            },
            {
              id: "organizations",
              header: "Organización / Proveedor",
              cell: (row) => {
                if (row.organizations.length) {
                  return (
                    <span className="inline-flex items-center gap-1.5 text-[12px] text-[color:var(--text-secondary)]">
                      <span className="max-w-[200px] truncate">
                        {row.organizations[0].name}
                      </span>
                      {row.organizations.length > 1 ? (
                        <Badge
                          variant="secondary"
                          title={row.organizations
                            .slice(1)
                            .map((org) => org.name)
                            .join(", ")}
                        >
                          +{row.organizations.length - 1}
                        </Badge>
                      ) : null}
                    </span>
                  );
                }
                // Provider accounts hold no membership/org — show the vendor
                // they own (P1-05) with a deep link to the vendor entity, plus
                // the client the vendor belongs to.
                const ws = row.provider_workspaces ?? [];
                if (ws.length) {
                  const first = ws[0];
                  return (
                    <span className="inline-flex items-center gap-1.5 text-[12px] text-[color:var(--text-secondary)]">
                      <Link
                        href={`/admin/vendors/${first.vendor_id}`}
                        className="max-w-[180px] truncate text-[color:var(--text-link)] hover:underline"
                      >
                        {first.vendor_name}
                      </Link>
                      {first.client_name ? (
                        <span className="text-[color:var(--text-tertiary)]">
                          · {first.client_name}
                        </span>
                      ) : null}
                      {ws.length > 1 ? (
                        <Badge
                          variant="secondary"
                          title={ws
                            .slice(1)
                            .map((w) => w.vendor_name)
                            .join(", ")}
                        >
                          +{ws.length - 1}
                        </Badge>
                      ) : null}
                    </span>
                  );
                }
                return (
                  <span className="text-[color:var(--text-tertiary)]">—</span>
                );
              },
            },
            {
              id: "status",
              header: "Estatus",
              width: "180px",
              cell: (row) => (
                <span className="flex flex-wrap items-center gap-1">
                  {row.deleted_at ? (
                    <Badge variant="secondary">Eliminado</Badge>
                  ) : row.status === "active" ? (
                    <Badge variant="success">Activo</Badge>
                  ) : (
                    <Badge variant="secondary">Desactivado</Badge>
                  )}
                  {!row.deleted_at && row.must_change_password ? (
                    <span
                      className="rounded-sm border border-[color:var(--border-subtle)] px-1 py-px font-mono text-[9px] uppercase tracking-wide text-[color:var(--text-tertiary)]"
                      title="Aún no ha cambiado su contraseña temporal."
                    >
                      primer acceso pendiente
                    </span>
                  ) : null}
                </span>
              ),
            },
            {
              id: "last_login_at",
              header: "Último acceso",
              width: "120px",
              cell: (row) => (
                <span className="font-mono text-[11px] tabular-nums text-[color:var(--text-secondary)]">
                  {formatLastLogin(row.last_login_at)}
                </span>
              ),
            },
            {
              id: "created_at",
              header: "Alta",
              width: "120px",
              cell: (row) => (
                <span className="font-mono text-[11px] tabular-nums text-[color:var(--text-secondary)]">
                  {formatDate(row.created_at)}
                </span>
              ),
            },
            {
              id: "actions",
              header: "Acciones",
              width: "240px",
              cell: (row) => (
                <span className="flex items-center gap-1 whitespace-nowrap">
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={row.status !== "active"}
                    title={
                      row.status !== "active"
                        ? "Reactiva la cuenta para poder restablecer su contraseña."
                        : undefined
                    }
                    onClick={() => {
                      setConfirmError(null);
                      setConfirm({ kind: "reset", user: row });
                    }}
                  >
                    <Key className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
                    Restablecer contraseña
                  </Button>
                  {row.status === "active" ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-[color:var(--status-error-text)]"
                      onClick={() => {
                        setConfirmError(null);
                        setConfirm({ kind: "status", next: "disabled", user: row });
                      }}
                    >
                      <Prohibit
                        className="h-3.5 w-3.5"
                        weight="bold"
                        aria-hidden="true"
                      />
                      Desactivar
                    </Button>
                  ) : (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setConfirmError(null);
                        setConfirm({ kind: "status", next: "active", user: row });
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
                </span>
              ),
            },
          ]}
        />

        {rows && rows.length > 0 ? (
          <div className="flex items-center justify-between gap-3">
            <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
              Mostrando {rows.length} de {total}
            </p>
            {rows.length < total ? (
              <Button
                variant="outline"
                size="sm"
                onClick={loadMore}
                loading={loadingMore}
              >
                Cargar más
              </Button>
            ) : null}
          </div>
        ) : null}
      </section>

      {/* Confirm dialog — reset password / disable / reactivate */}
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
              {confirm ? (
                confirm.kind === "reset" ? (
                  <>
                    Se generará una contraseña temporal nueva para{" "}
                    <strong>{confirm.user.email}</strong>, se invalidará la
                    actual y se enviará por correo. La verás una sola vez en
                    pantalla.
                  </>
                ) : confirm.next === "disabled" ? (
                  <>
                    <strong>{confirm.user.email}</strong> perderá el acceso a
                    CheckWise de inmediato. Sus datos y documentos se
                    conservan; puedes reactivar la cuenta cuando quieras.
                  </>
                ) : (
                  <>
                    <strong>{confirm.user.email}</strong> recuperará el acceso
                    a CheckWise con su contraseña actual.
                  </>
                )
              ) : null}
            </DialogDescription>
          </DialogHeader>

          {confirmError ? (
            <div className="flex items-start gap-2 rounded-md border border-[color:var(--status-error-border)] bg-[color:var(--status-error-bg)] px-3 py-2 text-[12px] text-[color:var(--status-error-text)]">
              <Warning
                className="mt-0.5 h-3.5 w-3.5 shrink-0"
                weight="fill"
                aria-hidden="true"
              />
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

      {/* Reset result dialog — the temp password is shown ONCE. */}
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
                  <PaperPlaneTilt
                    className="h-3 w-3"
                    weight="bold"
                    aria-hidden="true"
                  />
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
