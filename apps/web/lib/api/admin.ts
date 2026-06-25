/**
 * Phase 7 — typed wrapper over the admin operations API.
 *
 * Every endpoint requires an ``internal_admin`` JWT (issued by
 * ``POST /api/v1/auth/login``). Auth is JWT-first (in-memory bearer),
 * cookie-fallback (``credentials: "include"``) — see
 * ``lib/session/admin.ts``.
 */

import { adminAuthHeader } from "@/lib/session/admin";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export class AdminApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "AdminApiError";
  }
}

async function fetchJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers ?? {});
  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }
  // JWT-first when we still hold the in-memory token; otherwise the
  // httpOnly cookie (credentials:include) authenticates. A fully
  // logged-out call simply 401s from the server and the caller routes
  // to /login.
  const auth = adminAuthHeader();
  if (auth.Authorization && !headers.has("Authorization")) {
    headers.set("Authorization", auth.Authorization);
  }
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new AdminApiError(response.status, detail || response.statusText);
  }
  if (response.status === 204) return undefined as unknown as T;
  return (await response.json()) as T;
}

// ---------------------------------------------------------------------------
// Overview
// ---------------------------------------------------------------------------

export type AdminOverview = {
  clients_total: number;
  vendors_total: number;
  active_workspaces_total: number;
  pending_reviews_total: number;
  rejected_or_correction_total: number;
  recent_submissions_total: number;
  recent_audit_events_total: number;
};

export async function getAdminOverview(): Promise<AdminOverview> {
  return fetchJson<AdminOverview>("/api/v1/admin/overview");
}

// ---------------------------------------------------------------------------
// Clients
// ---------------------------------------------------------------------------

export type AdminClient = {
  id: string;
  name: string;
  rfc: string | null;
  email: string | null;
  responsible_name: string | null;
  status: string;
  created_at: string | null;
  updated_at: string | null;
};

type ListResponse<T> = { items: T[]; total: number };

export async function listClients(params?: {
  search?: string;
  limit?: number;
  offset?: number;
}): Promise<ListResponse<AdminClient>> {
  const qs = new URLSearchParams();
  if (params?.search) qs.set("search", params.search);
  if (params?.limit !== undefined) qs.set("limit", String(params.limit));
  if (params?.offset !== undefined) qs.set("offset", String(params.offset));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return fetchJson(`/api/v1/admin/clients${suffix}`);
}

export async function getClient(id: string): Promise<AdminClient> {
  return fetchJson(`/api/v1/admin/clients/${id}`);
}

export async function updateClient(
  id: string,
  body: Partial<{
    name: string;
    rfc: string | null;
    email: string | null;
    responsible_name: string | null;
    status: string;
  }>,
): Promise<AdminClient> {
  return fetchJson(`/api/v1/admin/clients/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

// ---------------------------------------------------------------------------
// Organizations — plan / demo lifecycle (Phase B)
// ---------------------------------------------------------------------------

export type AdminOrgPlan = {
  id: string;
  name: string;
  kind: string;
  plan: string | null;
  provider_limit: number | null;
  demo_expires_at: string | null;
  status: string;
  capabilities: Record<string, boolean>;
};

export type AdminOrgUpdateBody = Partial<{
  plan: string;
  provider_limit: number | null;
  status: string;
}>;

/** Provision a fresh 14-day demo on a client organization. */
export async function startClientDemo(orgId: string): Promise<AdminOrgPlan> {
  return fetchJson(`/api/v1/admin/organizations/${orgId}/start-demo`, {
    method: "POST",
  });
}

/** Upgrade/downgrade a plan, set a per-tenant provider-limit override, or
 *  reactivate a frozen org (``status: 'active'``). */
export async function updateClientOrg(
  orgId: string,
  body: AdminOrgUpdateBody,
): Promise<AdminOrgPlan> {
  return fetchJson(`/api/v1/admin/organizations/${orgId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

/** Read a client's plan + usage (also yields ``organization_id`` for the
 *  mutations above). Uses the client-plan endpoint with ``?client_id=`` —
 *  authorized for ``internal_admin`` via the break-glass scope. */
export async function getAdminClientPlan(
  clientId: string,
): Promise<import("./client").ClientPlan> {
  return fetchJson(
    `/api/v1/client/plan?client_id=${encodeURIComponent(clientId)}`,
  );
}

// Per-tenant entitlements + billing seam (Phase D).

export type AdminEntitlement = {
  key: string;
  enabled: boolean;
  expires_at: string | null;
  note: string | null;
};

export async function listEntitlements(
  orgId: string,
): Promise<AdminEntitlement[]> {
  return fetchJson(`/api/v1/admin/organizations/${orgId}/entitlements`);
}

export async function grantEntitlement(
  orgId: string,
  key: string,
  body: { enabled: boolean; note?: string | null },
): Promise<AdminEntitlement> {
  return fetchJson(
    `/api/v1/admin/organizations/${orgId}/entitlements/${encodeURIComponent(key)}`,
    { method: "PUT", body: JSON.stringify(body) },
  );
}

export async function revokeEntitlement(
  orgId: string,
  key: string,
): Promise<{ key: string; removed: boolean }> {
  return fetchJson(
    `/api/v1/admin/organizations/${orgId}/entitlements/${encodeURIComponent(key)}`,
    { method: "DELETE" },
  );
}

export type AdminBilling = {
  organization_id: string;
  provider: string;
  customer_id: string | null;
  subscription_id: string | null;
  status: string;
  current_period_end: string | null;
};

export async function getBilling(orgId: string): Promise<AdminBilling> {
  return fetchJson(`/api/v1/admin/organizations/${orgId}/billing`);
}

export async function updateBilling(
  orgId: string,
  body: Partial<{ provider: string; status: string; plan: string }>,
): Promise<AdminBilling> {
  return fetchJson(`/api/v1/admin/organizations/${orgId}/billing`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

// ---------------------------------------------------------------------------
// Metadata rulebook catalog (P2-09) — operational documentation surface
// ---------------------------------------------------------------------------

export type MetadataCatalogField = {
  key: string;
  label: string;
  /** How THIS doc type uses the field: required / conditional / optional. */
  requirement_level: string;
  description: string;
  extraction_methods: string[];
  human_review_required: boolean;
};

export type MetadataCatalogDocType = {
  code: string;
  name: string;
  institution: string;
  frequency: string;
  hierarchy: string;
  category: string;
  human_review_required: boolean;
  legal_approval_allowed: boolean;
  fields: MetadataCatalogField[];
};

export type MetadataCatalog = {
  rulebook_title: string;
  rulebook_version: string;
  rulebook_source: string;
  /** extraction-method code → plain-Spanish description. */
  extraction_methods: Record<string, string>;
  document_types: MetadataCatalogDocType[];
};

export async function getMetadataCatalog(): Promise<MetadataCatalog> {
  return fetchJson("/api/v1/admin/metadata/catalog");
}

// ---------------------------------------------------------------------------
// Calendar radar (P2-07) — forward operational view across the portfolio
// ---------------------------------------------------------------------------

export type CalendarRadarDeadline = {
  vendor_id: string;
  vendor_name: string;
  client_id: string | null;
  title: string;
  institution: string;
  period_key: string | null;
  due_in_days: number;
  state: string;
  href: string | null;
};

export type CalendarRadar = {
  as_of: string;
  upcoming: CalendarRadarDeadline[];
  urgency_buckets: Record<string, number>;
  urgency_bands: { key: string; label: string; max_days: number | null }[];
  awaiting_review_total: number;
  vendors_scanned: number;
  truncated: boolean;
};

export async function getAdminCalendarRadar(params?: {
  client_id?: string;
  institution?: string;
  top?: number;
}): Promise<CalendarRadar> {
  const qs = new URLSearchParams();
  if (params?.client_id) qs.set("client_id", params.client_id);
  if (params?.institution) qs.set("institution", params.institution);
  if (params?.top !== undefined) qs.set("top", String(params.top));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return fetchJson(`/api/v1/admin/calendar/radar${suffix}`);
}

// ---------------------------------------------------------------------------
// Calendar grid (P0 rework) — the time-anchored clients×months calendar
// ---------------------------------------------------------------------------

export type AdminCalendarRow = {
  id: string;
  name: string;
  semaphore_level: "red" | "yellow" | "green" | string;
  compliance_pct: number;
  overdue_count: number;
  due_soon_count: number;
};

export type AdminCalendarCellInst = { count: number; worst_risk: string };

export type AdminCalendarCell = {
  row_id: string;
  month: number;
  count: number;
  /** One of the six ordered calendar risks. */
  worst_risk: string;
  /** Per-institution {count, worst_risk} — lets the grid recolor by one
   *  authority client-side without a refetch. */
  by_institution: Record<string, AdminCalendarCellInst>;
};

export type AdminCalendarMonthForecast = {
  month: number;
  total: number;
  by_institution: Record<string, number>;
};

export type AdminCalendarMonthStatus = {
  month: number;
  expected: number;
  delivered: number;
  /** institution -> { expected, delivered } */
  by_institution: Record<string, { expected: number; delivered: number }>;
};

export type AdminCalendarObligation = {
  client_id: string;
  client_name: string;
  vendor_id: string;
  vendor_name: string;
  requirement_name: string;
  institution: string;
  period_key: string | null;
  period_label: string;
  deadline_iso: string;
  due_month: number;
  due_in_days: number;
  status: string;
  risk_level: string;
};

export type AdminCalendarGrid = {
  as_of: string;
  year: number;
  /** "clients" at the top level, "providers" when drilled into one client. */
  level: "clients" | "providers";
  client_id: string | null;
  client_name: string | null;
  rows: AdminCalendarRow[];
  cells: AdminCalendarCell[];
  month_totals: number[];
  forecast: AdminCalendarMonthForecast[];
  /** Per-month expected-vs-delivered gap (drives the cheap month summary). */
  month_status: AdminCalendarMonthStatus[];
  triage: { overdue_total: number; due_7d_total: number };
  /** Obligation rows — populated only for a drilled client (?client_id). The
   *  overview no longer returns the cross-portfolio month dump. */
  obligations: AdminCalendarObligation[];
  clients_total: number;
  clients_scanned: number;
  truncated: boolean;
  /** ISO time the overview snapshot was computed, or null when the response is
   *  live (cold cache, a forced refresh, or a per-client drill). */
  snapshot_at: string | null;
};

export async function getAdminCalendarGrid(params?: {
  year?: number;
  client_id?: string;
  month?: number;
  /** Force a synchronous snapshot rebuild before serving (the "Actualizar" action). */
  refresh?: boolean;
}): Promise<AdminCalendarGrid> {
  const qs = new URLSearchParams();
  if (params?.year !== undefined) qs.set("year", String(params.year));
  if (params?.client_id) qs.set("client_id", params.client_id);
  if (params?.month !== undefined) qs.set("month", String(params.month));
  if (params?.refresh) qs.set("refresh", "true");
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return fetchJson(`/api/v1/admin/calendar/grid${suffix}`);
}

// Renewals lane — date-precise obligations the 17th-of-month grid can't model.

export type AdminRenewalContract = {
  client_id: string;
  client_name: string;
  vendor_id: string;
  vendor_name: string;
  end_date: string;
  days_until: number;
  status: "overdue" | "due_soon" | "upcoming";
  repse_folio: string | null;
};

export type AdminRenewalCredential = {
  client_id: string | null;
  client_name: string | null;
  vendor_id: string;
  vendor_name: string;
  title: string;
  requirement_code: string;
  status: "overdue" | "due_soon";
};

export type AdminRenewals = {
  as_of: string;
  contracts: AdminRenewalContract[];
  credentials: AdminRenewalCredential[];
  vendors_scanned: number;
  truncated: boolean;
};

export async function getAdminCalendarRenewals(params?: {
  horizon_days?: number;
}): Promise<AdminRenewals> {
  const qs = new URLSearchParams();
  if (params?.horizon_days !== undefined)
    qs.set("horizon_days", String(params.horizon_days));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return fetchJson(`/api/v1/admin/calendar/renewals${suffix}`);
}

/**
 * Item 8 v2 — unified user provisioning. Replaces the older
 * createClient + provisionClient pair. One endpoint mints a temp
 * password, bcrypts it onto a fresh User, sends the welcome email,
 * and wires up either:
 *   * role=client → Client + Organization + Membership(client_admin)
 *   * role=provider → Vendor + ProviderWorkspace anchored under
 *     ``parent_client_id``
 * The ``temp_password`` plaintext is returned ONCE for the admin
 * confirmation screen. Email-delivery status surfaces so the UI
 * can warn when SMTP skipped.
 */
/**
 * The account-type axis of user provisioning ("which kind of account
 * are we minting"). This is distinct from ``MembershipRole`` (the RBAC
 * role a user holds) — it's the provisioning form's selector. Derived
 * from ``ProvisionUserBody`` so the form, the request body, and the
 * response all read from ONE source of truth instead of redeclaring the
 * union (audit F5). ``admin`` mints staff; ``client``/``provider`` mint
 * the tenant-side stacks.
 */
export type ProvisionRole = ProvisionUserBody["role"];

export type ProvisionUserBody = {
  full_name: string;
  email: string;
  role: "client" | "provider" | "admin";
  // client-only
  client_name?: string;
  client_rfc?: string | null;
  // provider-only
  vendor_name?: string;
  vendor_rfc?: string;
  persona_type?: "moral" | "fisica";
  contact_phone?: string | null;
  parent_client_id?: string;
};

export type ProvisionUserResponse = {
  user_id: string;
  role: "client" | "provider" | "admin";
  email: string;
  temp_password: string;
  login_url: string;
  email_status: string;
  email_error: string | null;
  client_id: string | null;
  organization_id: string | null;
  vendor_id: string | null;
  workspace_id: string | null;
};

export async function provisionUser(
  body: ProvisionUserBody,
): Promise<ProvisionUserResponse> {
  return fetchJson("/api/v1/admin/users", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Summary of the pre-existing account returned in the 409 body when
 *  provisioning hits a duplicate email (Phase 3 resolver). */
export type ProvisionConflictUser = {
  user_id: string;
  full_name: string;
  email: string;
  status: string;
  roles: string[];
};

/** If ``err`` is the duplicate-email 409 from ``provisionUser``, unwrap
 *  the existing-account summary so the form can offer guided actions
 *  (open / reactivate / reset) instead of a dead-end error. Returns null
 *  for any other error shape. */
export function provisionConflictUser(
  err: unknown,
): ProvisionConflictUser | null {
  if (!(err instanceof AdminApiError) || err.status !== 409) return null;
  try {
    const parsed = JSON.parse(err.message) as {
      detail?: { existing_user?: ProvisionConflictUser };
    };
    return parsed.detail?.existing_user ?? null;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// User management (P3 audit, 2026-06-10) — list / disable / reset-password
// for EXISTING users. Until this, provisioning was a write-only door: no
// surface could list users, disable a departed employee, or reset a
// forgotten password.
// ---------------------------------------------------------------------------

export type AdminUserRow = {
  user_id: string;
  email: string;
  full_name: string;
  status: string;
  /** True while the user hasn't rotated their temp password. */
  must_change_password: boolean;
  last_login_at: string | null;
  created_at: string;
  /** Set when the account is soft-deleted (migration 0042). */
  deleted_at?: string | null;
  /** Distinct active membership roles, sorted. Includes the synthetic
   *  "provider" role for ProviderWorkspace owners (who hold no membership). */
  roles: string[];
  organizations: { id: string; name: string; kind: string }[];
  /** Provider logins this account owns (P1-05); empty for non-providers. */
  provider_workspaces?: {
    vendor_id: string;
    vendor_name: string;
    client_id: string | null;
    client_name: string | null;
  }[];
};

export type AdminUsersList = {
  items: AdminUserRow[];
  /** Real count for the q/status/role filters, independent of limit. */
  total: number;
};

export async function listUsers(params?: {
  q?: string;
  status?: "active" | "disabled";
  role?: string;
  include_deleted?: boolean;
  limit?: number;
  offset?: number;
}): Promise<AdminUsersList> {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== undefined && value !== null && value !== "") {
      qs.set(key, String(value));
    }
  }
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return fetchJson(`/api/v1/admin/users${suffix}`);
}

export async function updateUserStatus(
  userId: string,
  status: "active" | "disabled",
): Promise<{ user_id: string; status: string }> {
  return fetchJson(`/api/v1/admin/users/${userId}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

/** ``temp_password`` is plaintext, returned ONCE for the admin's
 *  confirmation screen — the backend stores only the bcrypt hash. */
export type AdminResetPasswordResponse = {
  user_id: string;
  email: string;
  temp_password: string;
  email_status: string;
  email_error: string | null;
};

export async function resetUserPassword(
  userId: string,
): Promise<AdminResetPasswordResponse> {
  return fetchJson(`/api/v1/admin/users/${userId}/reset-password`, {
    method: "POST",
  });
}

/** One membership row on the user-detail page. ``seat_limit`` /
 *  ``active_seats`` are populated only for ``client``-kind orgs (the
 *  3-seat model); null on internal / vendor orgs. */
export type AdminUserMembership = {
  membership_id: string;
  organization_id: string;
  organization_name: string;
  organization_kind: string;
  role: string;
  is_primary: boolean;
  status: string;
  seat_limit: number | null;
  active_seats: number | null;
};

/** Full account picture for /platform/users/[id] (Phase 2). Reuses
 *  ``AdminAuditLogItem`` for the user's own audit slice. */
export type AdminUserDetail = {
  user_id: string;
  email: string;
  full_name: string;
  status: string;
  must_change_password: boolean;
  phone: string | null;
  last_login_at: string | null;
  created_at: string;
  updated_at: string;
  /** Soft-delete provenance (migration 0042); all null on a live account. */
  deleted_at: string | null;
  deleted_by_user_id: string | null;
  deleted_by_email: string | null;
  deletion_reason: string | null;
  roles: string[];
  /** All memberships (active + removed + disabled), active first. */
  memberships: AdminUserMembership[];
  /** The user's own audit slice — events targeting them OR by them. */
  recent_activity: AdminAuditLogItem[];
  /** Real count, so the UI can link to the full explorer when it overflows. */
  activity_total: number;
};

export async function getUser(
  userId: string,
  params?: { activity_limit?: number },
): Promise<AdminUserDetail> {
  const qs = new URLSearchParams();
  if (params?.activity_limit !== undefined) {
    qs.set("activity_limit", String(params.activity_limit));
  }
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return fetchJson(`/api/v1/admin/users/${userId}${suffix}`);
}

/** Result of a PATCH identity edit (Phase 3). ``notification_status`` is
 *  the combined old+new change-email delivery status, null when the
 *  email didn't change. */
export type AdminUserIdentityResponse = {
  user_id: string;
  full_name: string;
  email: string;
  phone: string | null;
  email_changed: boolean;
  notification_status: string | null;
};

/** Edit a user's name / email / phone. Send only the fields you want to
 *  change. An email change must land on a free address (409 otherwise)
 *  and notifies both the old and new addresses. */
export async function updateUserIdentity(
  userId: string,
  body: { full_name?: string; email?: string; phone?: string | null },
): Promise<AdminUserIdentityResponse> {
  return fetchJson(`/api/v1/admin/users/${userId}/identity`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

/** A grantable membership role and the org kind it belongs in.
 *  Role-model redesign: client_admin (client) + platform_admin /
 *  operations_admin (internal staff). */
export type MembershipRoleCode =
  | "client_admin"
  | "platform_admin"
  | "operations_admin";

export type AdminMembershipResponse = {
  user_id: string;
  membership_id: string;
  organization_id: string;
  role: string;
  status: string;
  is_primary: boolean;
};

/** Grant a role to a user within an org. 409 if duplicate / seat cap hit,
 *  422 if the role doesn't match the org kind. */
export async function grantMembership(
  userId: string,
  body: { organization_id: string; role: MembershipRoleCode },
): Promise<AdminMembershipResponse> {
  return fetchJson(`/api/v1/admin/users/${userId}/memberships`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Revoke a role (soft — status='removed'). 409 if it's the active owner. */
export async function revokeMembership(
  userId: string,
  membershipId: string,
): Promise<AdminMembershipResponse> {
  return fetchJson(
    `/api/v1/admin/users/${userId}/memberships/${membershipId}`,
    { method: "DELETE" },
  );
}

/** Make this membership the org's Primary Account Owner (client orgs). */
export async function promoteMembership(
  userId: string,
  membershipId: string,
): Promise<AdminMembershipResponse> {
  return fetchJson(
    `/api/v1/admin/users/${userId}/memberships/${membershipId}`,
    { method: "PATCH", body: JSON.stringify({ is_primary: true }) },
  );
}

/** What a soft-delete would affect (Phase 5) — for the confirm modal. */
export type AdminUserDeletionPreview = {
  user_id: string;
  email: string;
  already_deleted: boolean;
  active_memberships: number;
  /** Client orgs the user is the active Primary Owner of (orphaned on delete). */
  primary_of_orgs: string[];
  /** Provider workspaces owned by this user (orphaned on delete). */
  owned_workspaces: number;
  /** Only remaining active internal_admin — a warning, not a block. */
  is_last_internal_admin: boolean;
};

export type AdminUserDeleteResponse = {
  user_id: string;
  status: string;
  deleted_at: string | null;
};

export async function getUserDeletionPreview(
  userId: string,
): Promise<AdminUserDeletionPreview> {
  return fetchJson(`/api/v1/admin/users/${userId}/deletion-preview`);
}

/** Soft-delete a user (recoverable). Refuses self-delete / double-delete. */
export async function deleteUser(
  userId: string,
  reason?: string,
): Promise<AdminUserDeleteResponse> {
  return fetchJson(`/api/v1/admin/users/${userId}`, {
    method: "DELETE",
    body: JSON.stringify({ reason: reason ?? null }),
  });
}

/** Reverse a soft-delete. Roles are not auto-restored — re-grant them. */
export async function restoreUser(
  userId: string,
): Promise<AdminUserDeleteResponse> {
  return fetchJson(`/api/v1/admin/users/${userId}/restore`, {
    method: "POST",
  });
}

// ---------------------------------------------------------------------------
// Vendors
// ---------------------------------------------------------------------------

export type AdminVendor = {
  id: string;
  client_id: string;
  /** Owning client's name, denormalised by the API so the roster renders
   *  without loading the whole clients catalog. Null if the link is missing. */
  client_name: string | null;
  name: string;
  rfc: string;
  contact_name: string | null;
  contact_email: string | null;
  repse_id: string | null;
  persona_type: "moral" | "fisica" | null;
  status: string;
  created_at: string | null;
  updated_at: string | null;
};

export async function listVendors(params?: {
  client_id?: string;
  search?: string;
  limit?: number;
  offset?: number;
}): Promise<ListResponse<AdminVendor>> {
  const qs = new URLSearchParams();
  if (params?.client_id) qs.set("client_id", params.client_id);
  if (params?.search) qs.set("search", params.search);
  if (params?.limit !== undefined) qs.set("limit", String(params.limit));
  if (params?.offset !== undefined) qs.set("offset", String(params.offset));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return fetchJson(`/api/v1/admin/vendors${suffix}`);
}

export async function getVendor(id: string): Promise<AdminVendor> {
  return fetchJson(`/api/v1/admin/vendors/${id}`);
}

/**
 * Optional filter set passed to the admin-side vendor expediente ZIP
 * endpoint. Mirrors the client-side ``ClientVendorExpedienteFilters``
 * so the three surfaces (provider, client_admin, internal_admin)
 * share the same filter shape.
 */
export type AdminVendorExpedienteFilters = {
  status?: string | null;
  period_key?: string | null;
  institution?: string | null;
};

/**
 * Absolute URL of the admin-side vendor expediente ZIP endpoint.
 * Mirrors ``clientVendorExpedienteZipUrl`` but enters through the
 * /admin/* surface with the ``internal_admin`` gate; LegalShelf
 * staff need cross-client visibility for audits and incident
 * response. The URL is followed as a top-level navigation
 * (``<a target="_blank">``) so the bearer cookie carries; the
 * backend writes an ``admin.vendor_expediente_downloaded`` audit
 * row before streaming begins.
 */
export function adminVendorExpedienteZipUrl(
  vendorId: string,
  filters: AdminVendorExpedienteFilters = {},
): string {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.period_key) params.set("period_key", filters.period_key);
  if (filters.institution) params.set("institution", filters.institution);
  const qs = params.toString();
  const base = `${API_BASE_URL}/api/v1/admin/vendors/${encodeURIComponent(vendorId)}/expediente.zip`;
  return qs ? `${base}?${qs}` : base;
}

export async function createVendor(body: {
  client_id: string;
  name: string;
  rfc: string;
  contact_name?: string | null;
  contact_email?: string | null;
  repse_id?: string | null;
  persona_type?: "moral" | "fisica" | null;
  status?: string;
}): Promise<AdminVendor> {
  return fetchJson("/api/v1/admin/vendors", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateVendor(
  id: string,
  body: Partial<{
    name: string;
    contact_name: string | null;
    contact_email: string | null;
    repse_id: string | null;
    persona_type: "moral" | "fisica" | null;
    status: string;
  }>,
): Promise<AdminVendor> {
  return fetchJson(`/api/v1/admin/vendors/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

// ---------------------------------------------------------------------------
// Workspaces
// ---------------------------------------------------------------------------

export type AdminWorkspace = {
  id: string;
  client_id: string;
  vendor_id: string;
  contract_id: string | null;
  owner_user_id: string | null;
  persona_type: string;
  display_name: string | null;
  filial_name: string | null;
  onboarding_completed_at: string | null;
  status: string;
  created_at: string | null;
  updated_at: string | null;
};

export async function listWorkspaces(params?: {
  client_id?: string;
  vendor_id?: string;
}): Promise<ListResponse<AdminWorkspace>> {
  const qs = new URLSearchParams();
  if (params?.client_id) qs.set("client_id", params.client_id);
  if (params?.vendor_id) qs.set("vendor_id", params.vendor_id);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return fetchJson(`/api/v1/admin/workspaces${suffix}`);
}

export async function getWorkspace(id: string): Promise<AdminWorkspace> {
  return fetchJson(`/api/v1/admin/workspaces/${id}`);
}

export async function updateWorkspace(
  id: string,
  body: Partial<{
    status: string;
    owner_user_id: string | null;
    display_name: string | null;
    filial_name: string | null;
  }>,
): Promise<AdminWorkspace> {
  return fetchJson(`/api/v1/admin/workspaces/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

// ---------------------------------------------------------------------------
// Metadata workbook exports
// ---------------------------------------------------------------------------

export type MetadataExportItem = {
  id: string;
  submission_id: string;
  document_id: string | null;
  client_id: string | null;
  result: "completed" | "skipped" | "failed" | string;
  severity: string;
  document_type_code: string | null;
  client_name: string | null;
  vendor_name: string | null;
  requirement_name: string | null;
  period_key: string | null;
  original_filename: string | null;
  output_path: string | null;
  latest_path: string | null;
  master_path: string | null;
  file_exists: boolean;
  preview_available: boolean;
  master_available: boolean;
  reason: string | null;
  created_at: string;
};

export type MetadataExportList = {
  items: MetadataExportItem[];
  /** Real count of matching rows (P3 — was len(items)). */
  total: number;
  limit: number;
  offset: number;
};

export type MetadataExportSheetPreview = {
  name: string;
  rows: string[][];
};

export type MetadataExportPreview = {
  export: MetadataExportItem;
  sheets: MetadataExportSheetPreview[];
};

export type ClientMasterMetadataPreview = {
  client_id: string;
  client_name: string;
  master_path: string;
  sheets: MetadataExportSheetPreview[];
};

export type ClientMetadataDocument = {
  cliente: string;
  proveedor: string;
  periodo: string;
  nombre_documento: string;
  tipo_documento: string;
  subtipo: string;
  institucion: string;
  fecha_principal: string;
  participantes: string;
  descripcion: string;
  anexos: string;
  etiquetas: string;
  archivo_pdf: string;
};

export type ClientMetadataResponse = {
  client: AdminClient;
  master_available: boolean;
  master_path: string | null;
  documents: ClientMetadataDocument[];
};

export async function listMetadataExports(params?: {
  result?: "completed" | "skipped" | "failed";
  limit?: number;
  offset?: number;
}): Promise<MetadataExportList> {
  const qs = new URLSearchParams();
  if (params?.result) qs.set("result", params.result);
  if (params?.limit !== undefined) qs.set("limit", String(params.limit));
  if (params?.offset !== undefined) qs.set("offset", String(params.offset));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return fetchJson(`/api/v1/admin/metadata-exports${suffix}`);
}

export async function getMetadataExportPreview(
  id: string,
): Promise<MetadataExportPreview> {
  return fetchJson(`/api/v1/admin/metadata-exports/${id}`);
}

export async function downloadMetadataExport(id: string): Promise<Blob> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/admin/metadata-exports/${id}/download`,
    { headers: { ...adminAuthHeader() }, credentials: "include" },
  );
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new AdminApiError(response.status, detail || response.statusText);
  }
  return response.blob();
}

export async function getClientMasterMetadataPreview(
  clientId: string,
): Promise<ClientMasterMetadataPreview> {
  return fetchJson(`/api/v1/admin/metadata-exports/clients/${clientId}/master`);
}

export async function downloadClientMasterMetadata(
  clientId: string,
): Promise<Blob> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/admin/metadata-exports/clients/${clientId}/master/download`,
    { headers: { ...adminAuthHeader() }, credentials: "include" },
  );
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new AdminApiError(response.status, detail || response.statusText);
  }
  return response.blob();
}

export async function getClientMetadata(
  clientId: string,
): Promise<ClientMetadataResponse> {
  return fetchJson(`/api/v1/admin/clients/${clientId}/metadata`);
}

// ---------------------------------------------------------------------------
// Requirements
// ---------------------------------------------------------------------------

export type AdminRequirementVersion = {
  id: string;
  version: number;
  legal_basis: string | null;
  applicability_rule: string | null;
  minimum_validation: string | null;
  automatic_signals: string | null;
  human_review_required: boolean;
  missing_state: string | null;
  temporal_rule: string | null;
  source_url: string | null;
  implementation_notes: string | null;
  required: boolean;
  effective_from: string | null;
  effective_to: string | null;
};

export type AdminRequirement = {
  id: string;
  code: string;
  name: string;
  institution_id: string;
  load_type: string;
  frequency: string;
  risk_level: string;
  is_active: boolean;
  current_version: number;
  version: AdminRequirementVersion | null;
  created_at: string | null;
  updated_at: string | null;
};

// ---------------------------------------------------------------------------
// Ops-console rollup (P2 audit, 2026-06-10) — the aggregate data the admin
// dashboard renders: per-client semáforo rollup, queue health, 7-day
// throughput, named vendors at risk, and operational inbox counts.
// ---------------------------------------------------------------------------

export type RollupClientRow = {
  client_id: string;
  client_name: string;
  vendors_total: number;
  green_count: number;
  yellow_count: number;
  red_count: number;
  compliance_pct: number;
  missing_required_total: number;
  pending_reviews_total: number;
  due_soon_total: number;
};

export type RollupQueueHealth = {
  pending_total: number;
  /** Age in hours of the oldest pending submission; null when empty. */
  oldest_age_hours: number | null;
  /** Exclusive buckets: under_24h <24h · h24_to_72h 24–72h ·
   *  over_72h 72h–7d · over_7d >7d. */
  age_buckets: {
    under_24h: number;
    h24_to_72h: number;
    over_72h: number;
    over_7d: number;
  };
};

export type RollupVendorAtRisk = {
  vendor_id: string;
  vendor_name: string;
  client_id: string;
  client_name: string;
  semaphore_level: "green" | "yellow" | "red";
  compliance_pct: number;
  missing_required_count: number;
  rejected_or_correction_count: number;
  last_activity_at: string | null;
};

export type AdminRollup = {
  /** Worst first: red_count desc, then compliance_pct asc. */
  clients: RollupClientRow[];
  queue: RollupQueueHealth;
  throughput: { approved_last_7d: number; rejected_last_7d: number };
  /** Top 8 red/yellow vendors only (empty when all green). */
  vendors_at_risk: RollupVendorAtRisk[];
  inbox: {
    contact_requests_pending: number;
    correction_requests_pending: number;
    feedback_reports_new: number;
  };
};

export async function getRollup(): Promise<AdminRollup> {
  return fetchJson("/api/v1/admin/rollup");
}

export type ClientComplianceVendorRow = {
  vendor_id: string;
  vendor_name: string;
  vendor_rfc: string | null;
  workspace_id: string;
  workspace_status: string;
  semaphore_level: "green" | "yellow" | "red";
  compliance_pct: number;
  missing_required_count: number;
  rejected_or_correction_count: number;
  pending_reviews_count: number;
  due_soon_count: number;
  last_activity_at: string | null;
};

export type ClientCompliance = {
  client_id: string;
  client_name: string;
  /** Red → yellow → green, compliance_pct asc within level. */
  vendors: ClientComplianceVendorRow[];
};

export async function getClientCompliance(
  clientId: string,
): Promise<ClientCompliance> {
  return fetchJson(`/api/v1/admin/clients/${clientId}/compliance`);
}

/** Institution catalog row for form dropdowns (P0 audit fix — the
 *  requirements form previously demanded a raw institution UUID). */
export type AdminInstitution = {
  id: string;
  code: string;
  name: string;
};

export async function listInstitutions(): Promise<{
  items: AdminInstitution[];
}> {
  return fetchJson("/api/v1/admin/institutions");
}

export async function listRequirements(params?: {
  institution_id?: string;
  is_active?: boolean;
}): Promise<ListResponse<AdminRequirement>> {
  const qs = new URLSearchParams();
  if (params?.institution_id) qs.set("institution_id", params.institution_id);
  if (params?.is_active !== undefined) qs.set("is_active", String(params.is_active));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return fetchJson(`/api/v1/admin/requirements${suffix}`);
}

export async function getRequirement(id: string): Promise<AdminRequirement> {
  return fetchJson(`/api/v1/admin/requirements/${id}`);
}

export async function createRequirement(body: {
  code: string;
  name: string;
  institution_id: string;
  load_type: string;
  frequency: string;
  risk_level?: string;
  is_active?: boolean;
  legal_basis?: string | null;
  applicability_rule?: string | null;
  minimum_validation?: string | null;
  automatic_signals?: string | null;
  human_review_required?: boolean;
  missing_state?: string | null;
  temporal_rule?: string | null;
  source_url?: string | null;
  implementation_notes?: string | null;
  required?: boolean;
}): Promise<AdminRequirement> {
  return fetchJson("/api/v1/admin/requirements", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function updateRequirement(
  id: string,
  body: Partial<{
    name: string;
    institution_id: string;
    load_type: string;
    frequency: string;
    risk_level: string;
    is_active: boolean;
  }>,
): Promise<AdminRequirement> {
  return fetchJson(`/api/v1/admin/requirements/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

// ---------------------------------------------------------------------------
// Periods + calendar
// ---------------------------------------------------------------------------

export type AdminPeriod = {
  id: string;
  code: string;
  period_key: string | null;
  year: number | null;
  month: number | null;
  period_type: string;
  starts_on: string | null;
  ends_on: string | null;
  due_on: string | null;
};

export async function listPeriods(params?: {
  year?: number;
  period_type?: string;
  limit?: number;
}): Promise<ListResponse<AdminPeriod>> {
  const qs = new URLSearchParams();
  if (params?.year !== undefined) qs.set("year", String(params.year));
  if (params?.period_type) qs.set("period_type", params.period_type);
  if (params?.limit !== undefined) qs.set("limit", String(params.limit));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return fetchJson(`/api/v1/admin/periods${suffix}`);
}

export type AdminCalendarMonth = {
  month: number;
  expected_total: number;
  institutions: { institution: string; expected: number }[];
};

export type AdminCalendar = {
  metadata: { source: string; version: string };
  year: number;
  persona_type: "moral" | "fisica";
  months: AdminCalendarMonth[];
};

export async function getAdminCalendar(params?: {
  year?: number;
  persona_type?: "moral" | "fisica";
}): Promise<AdminCalendar> {
  const qs = new URLSearchParams();
  if (params?.year !== undefined) qs.set("year", String(params.year));
  if (params?.persona_type) qs.set("persona_type", params.persona_type);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return fetchJson(`/api/v1/admin/calendar${suffix}`);
}

// ---------------------------------------------------------------------------
// Audit log
// ---------------------------------------------------------------------------

export type AdminAuditLogItem = {
  id: string;
  actor_id: string | null;
  /** Resolved user email for actor_id, null when the actor isn't a
   *  user row (P3 audit fix — the page previously showed raw UUIDs). */
  actor_email: string | null;
  actor_type: string;
  action: string;
  entity_type: string;
  entity_id: string;
  /** Resolved human name for the target entity (P1-06b) — client/vendor/report
   *  name or user email; null for types without a name (falls back to the id). */
  entity_label?: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  event_metadata: Record<string, unknown> | null;
  /** Best-effort originating IP (migration 0043); null on system events. */
  ip_address?: string | null;
  user_agent?: string | null;
  created_at: string;
};

export type AdminAuditLogResponse = {
  items: AdminAuditLogItem[];
  /** Real count of rows matching the filters (P3 — was len(items)). */
  total: number;
  limit: number;
  offset: number;
};

export async function listAuditLog(params?: {
  actor_id?: string;
  actor_type?: string;
  /** Case-insensitive PREFIX match (e.g. "admin.user" matches
   *  admin.user_disabled). */
  action?: string;
  entity_type?: string;
  entity_id?: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
}): Promise<AdminAuditLogResponse> {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== undefined && value !== null && value !== "") {
      qs.set(key, String(value));
    }
  }
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return fetchJson(`/api/v1/admin/audit-log${suffix}`);
}

// ---------------------------------------------------------------------------
// Contact requests (P0-3 follow-up)
// ---------------------------------------------------------------------------

export type ContactRequestStatus =
  | "new"
  | "reviewed"
  | "contacted"
  | "closed";

export interface AdminContactRequest {
  id: string;
  name: string;
  email: string;
  company: string | null;
  role: string | null;
  message: string;
  source: string;
  status: ContactRequestStatus;
  ip_hash: string | null;
  user_agent: string | null;
  created_at: string;
  updated_at: string;
}

export interface AdminContactRequestList {
  items: AdminContactRequest[];
  total: number;
  limit: number;
  offset: number;
}

export async function listContactRequests(params?: {
  status?: ContactRequestStatus;
  limit?: number;
  offset?: number;
}): Promise<AdminContactRequestList> {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value === undefined || value === null) continue;
    const asString = String(value);
    if (!asString) continue;
    qs.set(key, asString);
  }
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return fetchJson(`/api/v1/admin/contact-requests${suffix}`);
}

export async function updateContactRequestStatus(
  id: string,
  status: ContactRequestStatus,
): Promise<AdminContactRequest> {
  return fetchJson(`/api/v1/admin/contact-requests/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

// ---------------------------------------------------------------------------
// Provider correction requests (Stage 2.7-a admin triage)
// ---------------------------------------------------------------------------

export type CorrectionRequestStatus = "pending" | "approved" | "rejected";

export interface AdminCorrectionRequest {
  id: string;
  status: CorrectionRequestStatus;
  workspace_id: string;
  vendor_id: string | null;
  vendor_name: string | null;
  vendor_rfc: string | null;
  client_id: string | null;
  client_name: string | null;
  user_id: string;
  user_email: string | null;
  user_name: string | null;
  field: string;
  current_value: string;
  proposed_value: string;
  reason: string;
  message: string | null;
  submitted_at: string;
  resolved_at: string | null;
  resolved_by_user_id: string | null;
  resolution_note: string | null;
}

export interface AdminCorrectionRequestList {
  items: AdminCorrectionRequest[];
  total: number;
  limit: number;
  offset: number;
}

export async function listCorrectionRequests(params?: {
  status?: CorrectionRequestStatus;
  limit?: number;
  offset?: number;
}): Promise<AdminCorrectionRequestList> {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value === undefined || value === null) continue;
    const asString = String(value);
    if (!asString) continue;
    qs.set(key, asString);
  }
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return fetchJson(`/api/v1/admin/correction-requests${suffix}`);
}

export async function approveCorrectionRequest(
  id: string,
  note?: string,
): Promise<AdminCorrectionRequest> {
  return fetchJson(`/api/v1/admin/correction-requests/${id}/approve`, {
    method: "POST",
    body: JSON.stringify({ note: note?.trim() || null }),
  });
}

export async function rejectCorrectionRequest(
  id: string,
  note?: string,
): Promise<AdminCorrectionRequest> {
  return fetchJson(`/api/v1/admin/correction-requests/${id}/reject`, {
    method: "POST",
    body: JSON.stringify({ note: note?.trim() || null }),
  });
}

// ---------------------------------------------------------------------------
// Feedback reports (bug + improvement reports from the Reportar launcher)
// ---------------------------------------------------------------------------

export type FeedbackKind = "bug" | "improvement";
export type FeedbackSource = "authenticated" | "public";
export type FeedbackStatus =
  | "new"
  | "triaged"
  | "in_progress"
  | "resolved"
  | "wont_fix";
export type FeedbackSlackDeliveryStatus =
  | "pending"
  | "sent"
  | "failed"
  | "skipped";

export interface AdminFeedbackReport {
  id: string;
  kind: FeedbackKind;
  description: string;
  source: FeedbackSource;
  is_public: boolean;
  status: FeedbackStatus;
  url: string | null;
  path: string | null;
  viewport: string | null;
  user_agent: string | null;
  console_logs: string | null;
  user_id: string | null;
  user_email: string | null;
  user_full_name: string | null;
  user_roles: string | null;
  contact_email: string | null;
  ip_hash: string | null;
  screenshot_storage_key: string | null;
  screenshot_size_bytes: number | null;
  /** Presigned download URL — populated on detail responses when the
   *  storage backend supports pre-signing (S3/R2). Null on local. */
  screenshot_url: string | null;
  slack_message_ts: string | null;
  slack_delivery_status: FeedbackSlackDeliveryStatus;
  slack_delivery_error: string | null;
  resolution_note: string | null;
  triaged_by_user_id: string | null;
  triaged_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AdminFeedbackReportList {
  items: AdminFeedbackReport[];
  total: number;
  limit: number;
  offset: number;
}

export async function listFeedbackReports(params?: {
  status?: FeedbackStatus;
  kind?: FeedbackKind;
  source?: FeedbackSource;
  limit?: number;
  offset?: number;
}): Promise<AdminFeedbackReportList> {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value === undefined || value === null) continue;
    const asString = String(value);
    if (!asString) continue;
    qs.set(key, asString);
  }
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return fetchJson(`/api/v1/admin/feedback-reports${suffix}`);
}

export async function getFeedbackReport(
  id: string,
): Promise<AdminFeedbackReport> {
  return fetchJson(`/api/v1/admin/feedback-reports/${id}`);
}

export async function updateFeedbackReportStatus(
  id: string,
  payload: { status: FeedbackStatus; resolution_note?: string | null },
): Promise<AdminFeedbackReport> {
  return fetchJson(`/api/v1/admin/feedback-reports/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}
