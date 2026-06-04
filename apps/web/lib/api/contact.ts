/**
 * Public contact-form API client.
 *
 * Backed by `POST /api/v1/contact` (see backend `app/api/v1/contact.py`).
 *
 * Unauthenticated by design — the landing-page form is public. The
 * backend enforces per-IP rate limits (5 / hour) and field-length
 * validators; this client surfaces those errors to the caller.
 */

export type LeadInterest =
  | "client_admin"
  | "provider"
  | "internal_legal"
  | "exploring";

export interface ContactRequestPayload {
  name: string;
  company: string;
  email: string;
  interest: LeadInterest;
  message: string;
}

export interface ContactRequestSuccess {
  ok: true;
  request_id: string;
  created_at: string;
}

export interface ContactRequestFailure {
  ok: false;
  error: string;
  /** HTTP status if known — lets the form surface "too many requests" specifically. */
  status?: number;
}

export type ContactRequestResult = ContactRequestSuccess | ContactRequestFailure;

export const INTEREST_LABELS: Record<LeadInterest, string> = {
  client_admin: "Soy cliente y quiero auditar a mis proveedores",
  provider: "Soy proveedor y quiero entregar mi expediente",
  internal_legal: "Soy parte del equipo CheckWise",
  exploring: "Estoy explorando opciones para mi empresa",
};

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

/**
 * Map the LeadInterest enum to the `role` field the backend accepts.
 * Backend stores free-form strings up to 60 chars; we send the Spanish
 * label so the row is human-readable without joining a lookup table.
 */
function roleFromInterest(interest: LeadInterest): string {
  return INTEREST_LABELS[interest];
}

export async function submitContactRequest(
  payload: ContactRequestPayload,
): Promise<ContactRequestResult> {
  // Trim once on the client. The backend trims again as belt-and-braces.
  const name = payload.name.trim();
  const email = payload.email.trim();
  const company = payload.company.trim() || undefined;
  const message = payload.message.trim() || "(sin mensaje)";

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/api/v1/contact`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        email,
        company,
        role: roleFromInterest(payload.interest),
        message,
        source: "landing",
      }),
    });
  } catch {
    return {
      ok: false,
      error:
        "No pudimos contactar al servidor. Revisa tu conexión y vuelve a intentarlo.",
    };
  }

  if (res.status === 429) {
    let detail = "Demasiadas solicitudes desde tu conexión. Inténtalo más tarde.";
    try {
      const body = (await res.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    return { ok: false, error: detail, status: 429 };
  }

  if (res.status === 422) {
    let detail = "Revisa los campos e inténtalo de nuevo.";
    try {
      const body = (await res.json()) as {
        detail?: Array<{ msg?: string }> | string;
      };
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail) && body.detail[0]?.msg) {
        detail = body.detail[0].msg!;
      }
    } catch {
      /* ignore */
    }
    return { ok: false, error: detail, status: 422 };
  }

  if (!res.ok) {
    return {
      ok: false,
      error:
        "No pudimos enviar tu solicitud. Vuelve a intentarlo en unos minutos.",
      status: res.status,
    };
  }

  const body = (await res.json()) as {
    ok: boolean;
    request_id: string;
    created_at: string;
  };
  return {
    ok: true,
    request_id: body.request_id,
    created_at: body.created_at,
  };
}
