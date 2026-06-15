/**
 * Shared authenticated file download for the staff surfaces
 * (admin + client). Audit 2026-06-12.
 *
 * Top-level navigations (``<a href>`` / ``window.open``) cannot carry
 * the staff JWT — browsers never attach custom headers to navigations,
 * and the admin/client surfaces have no session cookie — so ZIP links
 * built that way reached the API unauthenticated and died with 401.
 * Staff-side file downloads must go through this helper instead:
 * fetch with the Bearer header, read the body as a Blob, and trigger
 * the save via a temporary object-URL anchor.
 *
 * The provider portal keeps its cookie-based navigation path
 * (``lib/api/portal.ts``) — its endpoints accept the session cookie.
 */

import { readAdminSession } from "@/lib/session/admin";

export class DownloadError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "DownloadError";
  }
}

/** Trigger a browser save dialog for an in-memory Blob. */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Delay revocation: Safari aborts the save if the URL dies too soon.
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

/**
 * GET ``url`` with the staff JWT and save the response as a file.
 *
 * The server-provided ``Content-Disposition`` filename wins when the
 * browser can read it (requires ``Access-Control-Expose-Headers`` on
 * cross-origin responses); ``fallbackFilename`` covers the rest.
 */
export async function downloadAuthenticatedFile(
  url: string,
  fallbackFilename: string,
): Promise<void> {
  const session = readAdminSession();
  if (!session) {
    throw new DownloadError(401, "No active staff session.");
  }
  let response: Response;
  try {
    // FE-SEC-1: auth via the httpOnly session cookie.
    response = await fetch(url, { credentials: "include" });
  } catch {
    throw new DownloadError(0, "No pudimos contactar al servidor.");
  }
  if (!response.ok) {
    const raw = await response.text().catch(() => "");
    // FastAPI errors arrive as {"detail": "..."} — surface the Spanish
    // detail, not the JSON envelope.
    let detail = raw;
    try {
      const parsed = JSON.parse(raw) as { detail?: unknown };
      if (typeof parsed.detail === "string") detail = parsed.detail;
    } catch {
      // Not JSON — keep the raw body.
    }
    throw new DownloadError(response.status, detail || response.statusText);
  }
  const disp = response.headers.get("Content-Disposition") || "";
  const match = /filename="?([^"]+)"?/i.exec(disp);
  const filename = match?.[1] ?? fallbackFilename;
  saveBlob(await response.blob(), filename);
}
