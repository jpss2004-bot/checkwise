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

/**
 * File downloads (ZIPs, large PDFs) can legitimately take longer than a JSON
 * read, so they get their own, more generous ceiling — but they MUST still be
 * bounded. Without it a stalled R2/zip stream leaves the "Descargando…" button
 * spinning forever with no recovery (perf audit P1-5).
 */
const DOWNLOAD_TIMEOUT_MS = 120_000;

export class DownloadError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "DownloadError";
  }
}

/**
 * Extract a filename from a ``Content-Disposition`` header value.
 *
 * Tightened to anchor on the token/quoted-string and stop at ``;`` so an
 * unquoted or RFC5987 header like
 * ``attachment; filename=a.zip; filename*=UTF-8''a%20final.zip`` no longer
 * greedily captures everything after ``filename=`` to end-of-line.
 * Returns ``undefined`` when no filename token is present.
 */
export function parseContentDispositionFilename(
  disposition: string,
): string | undefined {
  const match = /filename\*?=(?:UTF-8''|")?([^";]+)"?/i.exec(disposition);
  return match?.[1];
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
  if (!session?.access_token) {
    throw new DownloadError(401, "No active staff session.");
  }
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), DOWNLOAD_TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch(url, {
      headers: { Authorization: `Bearer ${session.access_token}` },
      credentials: "include",
      signal: controller.signal,
    });
  } catch {
    if (controller.signal.aborted) {
      throw new DownloadError(
        0,
        "La descarga tardó demasiado. Inténtalo de nuevo.",
      );
    }
    throw new DownloadError(0, "No pudimos contactar al servidor.");
  } finally {
    clearTimeout(timeoutId);
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
  const filename = parseContentDispositionFilename(disp) ?? fallbackFilename;
  saveBlob(await response.blob(), filename);
}
