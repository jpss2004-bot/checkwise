/**
 * Phase 7 / Slice N8b — notification preferences + phone-verification client.
 *
 * Thin wrappers around:
 *   - GET /api/v1/me/notification-preferences
 *   - PUT /api/v1/me/notification-preferences
 *   - POST /api/v1/me/phone/verify
 *   - POST /api/v1/me/phone/verify/confirm
 *
 * Auth: Bearer JWT from the admin session (same pattern as
 * `portal-session.ts`). Returns null on 401 / network failure so the
 * caller surfaces a generic "intenta de nuevo" message rather than
 * a thrown exception.
 */

const API_BASE_URL =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE_URL) ||
  "http://127.0.0.1:8000";

export type ContactPreference = "email" | "whatsapp" | "both";

export type NotificationCategory =
  | "renewal"
  | "reporting"
  | "verification"
  | "account"
  | "admin";

export interface CategoryMute {
  category: NotificationCategory;
  email_muted: boolean;
  whatsapp_muted: boolean;
}

export interface NotificationPreferencesResponse {
  contact_preference: ContactPreference;
  phone_e164: string | null;
  phone_verified: boolean;
  whatsapp_opt_in_at: string | null;
  categories: CategoryMute[];
}

export interface NotificationPreferencesUpdate {
  contact_preference?: ContactPreference;
  categories?: CategoryMute[];
}

export interface PhoneVerifyResponse {
  status: "sent" | "skipped" | "failed";
  expires_in_seconds: number;
  delivery_detail: string | null;
}

export interface PhoneConfirmResponse {
  phone_e164: string;
  phone_verified_at: string;
  whatsapp_opt_in_at: string;
}

function bearerHeader(): Record<string, string> {
  // FE-SEC-1: auth now rides the httpOnly session cookie (every fetch in
  // this module uses credentials:include); no localStorage bearer header.
  return {};
}

export async function fetchNotificationPreferences(): Promise<
  NotificationPreferencesResponse | null
> {
  try {
    const r = await fetch(
      `${API_BASE_URL}/api/v1/me/notification-preferences`,
      {
        method: "GET",
        credentials: "include",
        headers: { Accept: "application/json", ...bearerHeader() },
      },
    );
    if (!r.ok) return null;
    return (await r.json()) as NotificationPreferencesResponse;
  } catch {
    return null;
  }
}

export async function updateNotificationPreferences(
  payload: NotificationPreferencesUpdate,
): Promise<NotificationPreferencesResponse | null> {
  try {
    const r = await fetch(
      `${API_BASE_URL}/api/v1/me/notification-preferences`,
      {
        method: "PUT",
        credentials: "include",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          ...bearerHeader(),
        },
        body: JSON.stringify(payload),
      },
    );
    if (!r.ok) return null;
    return (await r.json()) as NotificationPreferencesResponse;
  } catch {
    return null;
  }
}

/**
 * Result tuple distinguishes "API said no" from "network error". The
 * UI handles them differently: a 429 is surfaced as a rate-limit
 * warning, a 422 as a phone-format hint, and a network error as a
 * generic retry message.
 */
export type PhoneVerifyOutcome =
  | { ok: true; data: PhoneVerifyResponse }
  | { ok: false; status: number; detail: string | null };

export async function requestPhoneVerification(
  phone: string,
): Promise<PhoneVerifyOutcome> {
  try {
    const r = await fetch(`${API_BASE_URL}/api/v1/me/phone/verify`, {
      method: "POST",
      credentials: "include",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        ...bearerHeader(),
      },
      body: JSON.stringify({ phone }),
    });
    if (!r.ok) {
      let detail: string | null = null;
      try {
        const body = await r.json();
        detail = typeof body?.detail === "string" ? body.detail : null;
      } catch {
        /* no JSON body */
      }
      return { ok: false, status: r.status, detail };
    }
    return { ok: true, data: (await r.json()) as PhoneVerifyResponse };
  } catch {
    return { ok: false, status: 0, detail: null };
  }
}

export type PhoneConfirmOutcome =
  | { ok: true; data: PhoneConfirmResponse }
  | { ok: false; status: number; detail: string | null };

export async function confirmPhoneVerification(
  phone: string,
  code: string,
): Promise<PhoneConfirmOutcome> {
  try {
    const r = await fetch(
      `${API_BASE_URL}/api/v1/me/phone/verify/confirm`,
      {
        method: "POST",
        credentials: "include",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          ...bearerHeader(),
        },
        body: JSON.stringify({ phone, code }),
      },
    );
    if (!r.ok) {
      let detail: string | null = null;
      try {
        const body = await r.json();
        detail = typeof body?.detail === "string" ? body.detail : null;
      } catch {
        /* no JSON body */
      }
      return { ok: false, status: r.status, detail };
    }
    return { ok: true, data: (await r.json()) as PhoneConfirmResponse };
  } catch {
    return { ok: false, status: 0, detail: null };
  }
}

export const CATEGORY_LABELS: Record<NotificationCategory, string> = {
  renewal: "Renovaciones REPSE",
  reporting: "Reportes periódicos",
  verification: "Revisión de documentos",
  account: "Cuenta y bienvenida",
  admin: "Soporte",
};

export const CATEGORY_DESCRIPTIONS: Record<NotificationCategory, string> = {
  renewal:
    "Documentos del expediente REPSE próximos a vencer o vencidos.",
  reporting:
    "Aperturas y cierres de ventanas de reporte mensual / bimestral / trimestral.",
  verification: "Aprobaciones, rechazos y aclaraciones de Legal Shelf.",
  account: "Invitaciones, restablecimientos y confirmaciones de cuenta.",
  admin: "Tickets de soporte y avisos operativos internos.",
};
