/**
 * MOCK contact / demo request handler.
 *
 * Receives "Solicitar información" form submissions from the public
 * landing page and pretends to send them to the team. Today it just
 * fakes a 600 ms delay and returns success — no real CRM or email
 * integration.
 *
 * TODO[backend-integration]: replace with a POST to a real endpoint
 * (e.g. /api/v1/leads or a HubSpot / Slack webhook).
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

export interface ContactRequestResult {
  ok: boolean;
  request_id?: string;
  error?: string;
}

export const INTEREST_LABELS: Record<LeadInterest, string> = {
  client_admin: "Soy cliente y quiero auditar a mis proveedores",
  provider: "Soy proveedor y quiero entregar mi expediente",
  internal_legal: "Soy equipo legal / Legal Shelf",
  exploring: "Estoy explorando opciones para mi empresa",
};

export async function submitContactRequest(
  payload: ContactRequestPayload,
): Promise<ContactRequestResult> {
  await new Promise((resolve) => setTimeout(resolve, 600));

  if (!payload.email.includes("@") || payload.name.trim().length < 2) {
    return { ok: false, error: "Captura tu nombre y un correo válido." };
  }

  return {
    ok: true,
    request_id: `req-mock-${Math.random().toString(36).slice(2, 10)}`,
  };
}
