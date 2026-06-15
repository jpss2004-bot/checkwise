/**
 * Internal feedback API client.
 *
 * Two backends, same response shape:
 *
 * - ``submitFeedback(token, payload)`` → ``POST /api/v1/feedback``.
 *   Requires a JWT. Used by the launcher when mounted inside an
 *   authenticated shell.
 *
 * - ``submitPublicFeedback(payload)`` → ``POST /api/v1/feedback/public``.
 *   Anonymous; the backend identifies the submitter by peppered
 *   IP-hash and an *optional* reply-back email. Used by the launcher
 *   when mounted on the public landing page.
 *
 * Both surface 429 / 413 / 415 (and 401 on the auth route) as tagged
 * errors so the launcher can show the right Spanish toast copy.
 */

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export type FeedbackKind = "bug" | "improvement";

export interface FeedbackPayload {
  kind: FeedbackKind;
  description: string;
  url: string;
  path: string;
  viewport: string;
  userAgent: string;
  consoleLogs: string;
  screenshot?: Blob | null;
}

export interface FeedbackSuccess {
  ok: true;
  delivered: boolean;
}

export interface FeedbackFailure {
  ok: false;
  error: string;
  status?: number;
}

export type FeedbackResult = FeedbackSuccess | FeedbackFailure;

export async function submitFeedback(
  _token: string,
  payload: FeedbackPayload,
): Promise<FeedbackResult> {
  const body = new FormData();
  body.append("type", payload.kind);
  body.append("description", payload.description);
  body.append("url", payload.url);
  body.append("path", payload.path);
  body.append("viewport", payload.viewport);
  body.append("user_agent", payload.userAgent);
  body.append("console_logs", payload.consoleLogs);
  if (payload.screenshot) {
    body.append("screenshot", payload.screenshot, "screenshot.png");
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/api/v1/feedback`, {
      method: "POST",
      // FE-SEC-1: reporter attribution via the httpOnly session cookie.
      credentials: "include",
      body,
    });
  } catch {
    return {
      ok: false,
      error: "No pudimos contactar al servidor. Revisa tu conexión.",
    };
  }

  if (res.status === 429) {
    return {
      ok: false,
      error: "Demasiados reportes. Espera un minuto antes de enviar otro.",
      status: 429,
    };
  }
  if (res.status === 413) {
    return {
      ok: false,
      error: "La captura es demasiado grande (máximo 5 MB).",
      status: 413,
    };
  }
  if (res.status === 415) {
    return {
      ok: false,
      error: "La captura debe ser una imagen PNG.",
      status: 415,
    };
  }
  if (res.status === 401) {
    return {
      ok: false,
      error: "Tu sesión expiró. Vuelve a iniciar sesión.",
      status: 401,
    };
  }

  if (!res.ok) {
    let detail = "No pudimos enviar tu reporte. Intenta de nuevo.";
    try {
      const data = (await res.json()) as { detail?: string };
      if (typeof data.detail === "string") detail = data.detail;
    } catch {
      /* ignore */
    }
    return { ok: false, error: detail, status: res.status };
  }

  const data = (await res.json()) as { ok: boolean; delivered: boolean };
  return { ok: true, delivered: data.delivered };
}

// ─── Public (unauthenticated) submission ─────────────────────────

export interface PublicFeedbackPayload extends FeedbackPayload {
  /** Optional reply-back email the submitter chose to share. */
  contactEmail?: string;
}

/**
 * Submit a feedback report from the public landing page.
 *
 * No Authorization header. The backend rate-limits at 5 reports per
 * hour per IP-hash (vs 10/min/user on the authed route), surfacing
 * 429 to the client. 413/415 still fire on screenshot validation.
 */
export async function submitPublicFeedback(
  payload: PublicFeedbackPayload,
): Promise<FeedbackResult> {
  const body = new FormData();
  body.append("type", payload.kind);
  body.append("description", payload.description);
  body.append("url", payload.url);
  body.append("path", payload.path);
  body.append("viewport", payload.viewport);
  body.append("user_agent", payload.userAgent);
  body.append("console_logs", payload.consoleLogs);
  if (payload.contactEmail) {
    body.append("contact_email", payload.contactEmail);
  }
  if (payload.screenshot) {
    body.append("screenshot", payload.screenshot, "screenshot.png");
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/api/v1/feedback/public`, {
      method: "POST",
      body,
    });
  } catch {
    return {
      ok: false,
      error: "No pudimos contactar al servidor. Revisa tu conexión.",
    };
  }

  if (res.status === 429) {
    return {
      ok: false,
      error:
        "Demasiados reportes desde tu conexión. Inténtalo de nuevo en una hora.",
      status: 429,
    };
  }
  if (res.status === 413) {
    return {
      ok: false,
      error: "La captura es demasiado grande (máximo 5 MB).",
      status: 413,
    };
  }
  if (res.status === 415) {
    return {
      ok: false,
      error: "La captura debe ser una imagen PNG.",
      status: 415,
    };
  }

  if (!res.ok) {
    let detail = "No pudimos enviar tu reporte. Intenta de nuevo.";
    try {
      const data = (await res.json()) as { detail?: string };
      if (typeof data.detail === "string") detail = data.detail;
    } catch {
      /* ignore */
    }
    return { ok: false, error: detail, status: res.status };
  }

  const data = (await res.json()) as { ok: boolean; delivered: boolean };
  return { ok: true, delivered: data.delivered };
}
